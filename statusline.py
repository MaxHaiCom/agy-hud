#!/usr/bin/env python3
"""
agy-hud: A sleek, seamless pastel HUD statusline for Google Antigravity CLI (agy).
Features:
- Solid, contiguous progress bars (zero gap lines, 100% smooth blocks).
- Softer, low-saturation pastel palette matching Linear / Apple aesthetics.
- Real-time 5h rolling & Weekly quota countdowns (dual pool: Gemini & Claude/3P).
- Context window token consumption and percentage gauge.
- Project folder name, Git branch & uncommitted status (*).
- Permission / mode indicator (bypass permissions, read-all, sandbox, etc.).
- Zero external dependencies (standard library only).
"""

import sys
import os
import json
import time
import subprocess
import re
import unicodedata
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List

# --- Palette: Exact Soft Pastel Colors (Linear / Apple Dark Mode) ---
# ANSI 24-bit TrueColor sequences
C_RESET = "\x1b[0m"
C_BOLD = "\x1b[1m"
C_DIM = "\x1b[2m"

# Text colors
FG_MODEL = "\x1b[38;2;208;209;254m"      # Soft Lavender (#d0d1fe)
FG_FOLDER = "\x1b[38;2;230;235;245m"     # Crisp Pearl White (#e6ebf5)
FG_GIT = "\x1b[38;2;217;130;245m"        # Pastel Orchid (#d982f5)
FG_LABEL = "\x1b[38;2;130;135;145m"      # Soft Slate Gray (#828791)
FG_SEP = "\x1b[38;2;65;72;85m"           # Subdued Slate Separator (#414855)
FG_CTX_TEXT = "\x1b[38;2;180;250;114m"   # Pastel Lime Green (#b4fa72)
FG_USAGE_TEXT = "\x1b[38;2;193;227;254m" # Pastel Baby Blue (#c1e3fe)
FG_WARN_TEXT = "\x1b[38;2;255;214;102m"  # Pastel Warm Amber (#ffd666)
FG_CRIT_TEXT = "\x1b[38;2;255;135;135m"  # Pastel Coral Red (#ff8787)

# Bar Background Colors (RGB tuples for solid blocks with spaces)
BG_CTX_FILL = (180, 250, 114)     # Lime Green fill
BG_CTX_TRACK = (32, 45, 23)       # Dark Olive track
BG_USAGE_FILL = (193, 227, 254)   # Baby Blue fill
BG_USAGE_TRACK = (44, 57, 67)     # Dark Slate track
BG_WARN_FILL = (255, 214, 102)    # Warm Amber fill
BG_WARN_TRACK = (58, 48, 24)      # Dark Amber track
BG_CRIT_FILL = (255, 135, 135)    # Coral Red fill
BG_CRIT_TRACK = (60, 30, 30)      # Dark Maroon track


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")


def strip_ansi(s: str) -> str:
    """Strip all ANSI escape codes."""
    return ANSI_RE.sub("", s)


def char_width(ch: str) -> int:
    """Calculate the terminal display width of a single character."""
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("W", "F"):
        return 2
    if unicodedata.category(ch) in ("Mn", "Me", "Cf") and ch != " ":
        return 0
    if ord(ch) >= 0x1F300:
        return 2
    return 1


def visual_length(s: str) -> int:
    """Compute visual width in terminal cells, ignoring ANSI escape codes."""
    plain = strip_ansi(s)
    return sum(char_width(ch) for ch in plain)


def slice_visible(s: str, max_w: int) -> str:
    """Slice string up to max_w visual cells, preserving ANSI codes."""
    if max_w <= 0:
        return ""
    result = []
    w = 0
    i = 0
    while i < len(s):
        m = ANSI_RE.match(s, i)
        if m:
            result.append(m.group(0))
            i = m.end()
            continue
        ch = s[i]
        cw = char_width(ch)
        if w + cw > max_w:
            break
        result.append(ch)
        w += cw
        i += 1
    return "".join(result)


def truncate_to_width(s: str, max_w: int) -> str:
    """Truncate string to max_w visual cells with ellipsis, preserving ANSI colors."""
    if max_w <= 0 or visual_length(s) <= max_w:
        return s
    suffix = "..." if max_w >= 3 else "." * max_w
    keep = max(0, max_w - len(suffix))
    sliced = slice_visible(s, keep)
    return f"{sliced}{C_RESET}{suffix}"


def get_terminal_width(fallback: int = 80) -> int:
    """
    Detect active terminal columns reliably across macOS, Linux, and Windows.
    Queries /dev/tty first (works even when stdin/stdout are redirected into a pipe).
    """
    # 1. Process environment variables (allows explicit COLUMNS override)
    env_cols = os.environ.get("COLUMNS")
    if env_cols:
        try:
            val = int(env_cols)
            if val > 0:
                return val
        except ValueError:
            pass

    # 2. Direct /dev/tty query (handles pipe redirection in CLI wrappers)
    try:
        with open("/dev/tty", "r") as tty:
            cols = os.get_terminal_size(tty.fileno()).columns
            if cols > 0:
                return cols
    except Exception:
        pass

    # 3. Standard file descriptors
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            if stream and hasattr(stream, "fileno"):
                cols = os.get_terminal_size(stream.fileno()).columns
                if cols > 0:
                    return cols
        except Exception:
            pass

    # 4. shutil fallback
    try:
        import shutil
        cols = shutil.get_terminal_size().columns
        if cols > 0:
            return cols
    except Exception:
        pass

    return fallback


def get_adaptive_bar_width(term_width: int) -> int:
    """Adaptive progress bar width based on terminal columns."""
    if term_width >= 85:
        return 8
    if term_width >= 60:
        return 6
    return 4


def make_solid_bar(
    pct: float,
    width: int = 8,
    fill_rgb: Tuple[int, int, int] = BG_USAGE_FILL,
    track_rgb: Tuple[int, int, int] = BG_USAGE_TRACK,
) -> str:
    """
    Renders a 100% solid, seamless rectangular bar with zero vertical line gaps.
    Uses ANSI 24-bit background color escape codes on space characters.
    """
    pct = max(0.0, min(100.0, float(pct)))
    filled_cells = max(0, min(width, round(pct / 100.0 * width)))
    empty_cells = width - filled_cells

    f_block = f"\x1b[48;2;{fill_rgb[0]};{fill_rgb[1]};{fill_rgb[2]}m" + (" " * filled_cells)
    e_block = f"\x1b[48;2;{track_rgb[0]};{track_rgb[1]};{track_rgb[2]}m" + (" " * empty_cells)
    return f"{f_block}{e_block}{C_RESET}"


def format_duration(seconds: Optional[int]) -> str:
    """Format seconds into concise reset countdown: 4h 12m, 1d 15h, or 25m."""
    if seconds is None or seconds <= 0:
        return ""
    mins = int(seconds) // 60
    days = mins // (24 * 60)
    mins %= 24 * 60
    hours = mins // 60
    mins %= 60

    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def format_tokens(num: float) -> str:
    """Format token count: 24.5k, 1.2M, etc."""
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}k"
    return str(int(num))


def clean_model_name(raw_name: str) -> str:
    """Clean model display name to keep it concise and elegant."""
    if not raw_name:
        return "Gemini"
    name = raw_name.replace("Google", "").replace("Gemini", "").strip()
    name = name.replace("Claude", "").strip()
    name = name.replace("(Thinking)", "Thinking").replace("(High)", "High").replace("(Medium)", "Med").replace("(Low)", "Low")
    name = " ".join(name.split())
    if not name:
        name = raw_name
    return name


def detect_git_info(cwd: str) -> Tuple[str, bool]:
    """
    Ultra-fast git branch and dirty status detection.
    Walks up to find .git and reads HEAD without heavy subprocesses.
    """
    if not cwd:
        return "", False
    try:
        cur = os.path.abspath(cwd)
    except Exception:
        return "", False

    branch = ""
    is_dirty = False

    for _ in range(8):
        git_dir = os.path.join(cur, ".git")
        if os.path.isdir(git_dir):
            head_file = os.path.join(git_dir, "HEAD")
            if os.path.isfile(head_file):
                try:
                    with open(head_file, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read().strip()
                        if content.startswith("ref: refs/heads/"):
                            branch = content[len("ref: refs/heads/"):]
                        elif len(content) >= 7:
                            branch = content[:7]
                except Exception:
                    pass
            break
        elif os.path.isfile(git_dir):
            # Git worktree / submodule pointer
            try:
                with open(git_dir, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().strip()
                    if content.startswith("gitdir:"):
                        real_dir = content[len("gitdir:"):].strip()
                        if not os.path.isabs(real_dir):
                            real_dir = os.path.join(cur, real_dir)
                        head_file = os.path.join(real_dir, "HEAD")
                        if os.path.isfile(head_file):
                            with open(head_file, "r", encoding="utf-8", errors="ignore") as hf:
                                hcontent = hf.read().strip()
                                if hcontent.startswith("ref: refs/heads/"):
                                    branch = hcontent[len("ref: refs/heads/"):]
                                elif len(hcontent) >= 7:
                                    branch = hcontent[:7]
            except Exception:
                pass
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent

    # Fast dirty check via git diff-index (timeout 100ms)
    if branch:
        try:
            res = subprocess.run(
                ["git", "--no-optional-locks", "status", "--porcelain=v1"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=0.15
            )
            if res.returncode == 0 and res.stdout.strip():
                is_dirty = True
        except Exception:
            pass

    return branch, is_dirty



# --- Cross-Process Multi-Window Quota Synchronization ---
CACHE_DIR = os.path.expanduser("~/.cache/agy-hud")
CACHE_FILE = os.path.join(CACHE_DIR, "quota_cache.json")


def _read_quota_cache() -> Dict[str, Any]:
    try:
        if os.path.isfile(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {}


def _write_quota_cache(data: Dict[str, Any]) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp_file = f"{CACHE_FILE}.tmp.{os.getpid()}"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp_file, CACHE_FILE)
    except Exception:
        pass


def extract_reset_timestamp(item: Optional[Dict[str, Any]], now: float) -> Optional[float]:
    """Extract absolute reset timestamp (epoch seconds) using reset_time or reset_in_seconds."""
    if not isinstance(item, dict):
        return None
    rt = item.get("reset_time")
    if rt and isinstance(rt, str):
        try:
            clean_rt = rt.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_rt)
            ts = dt.timestamp()
            if ts > 0:
                return ts
        except Exception:
            pass
    raw_sec = item.get("reset_in_seconds")
    if raw_sec is not None:
        try:
            s = float(raw_sec)
            if s > 0:
                return now + s
        except Exception:
            pass
    if "reset_at" in item and item["reset_at"] is not None:
        try:
            ts = float(item["reset_at"])
            if ts > 0:
                return ts
        except Exception:
            pass
    return None


def _prune_expired_pools(pools: Dict[str, Any], now: float) -> bool:
    """Evict expired or zombie quota cache entries across all pools."""
    changed = False
    for pool_name, pool_data in list(pools.items()):
        if not isinstance(pool_data, dict):
            continue
        # 5h check (max ttl 5 hours)
        if "5h" in pool_data and isinstance(pool_data["5h"], dict):
            item = pool_data["5h"]
            rec = item.get("recorded_at") or 0
            rst = item.get("reset_at")
            if (now - rec > 18000) or (rst and rst <= (now - 30)) or (not rst and (now - rec > 300)):
                del pool_data["5h"]
                changed = True
        # weekly check (max ttl 7 days)
        if "weekly" in pool_data and isinstance(pool_data["weekly"], dict):
            item = pool_data["weekly"]
            rec = item.get("recorded_at") or 0
            rst = item.get("reset_at")
            if (now - rec > 604800) or (rst and rst <= (now - 30)) or (not rst and (now - rec > 300)):
                del pool_data["weekly"]
                changed = True
        if not pool_data:
            del pools[pool_name]
            changed = True
    return changed


def reconcile_quota_item(
    item_in: Optional[Dict[str, Any]],
    cached_item: Optional[Dict[str, Any]],
    now: float,
    max_ttl: float = 18000.0
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Reconciles a single quota metric (e.g. 5h or weekly) between incoming stdin data
    and cross-process cached state.
    Returns: (resolved_item, updated_cache_item)

    Key Principles:
    1. Incoming stdin is the direct authoritative source from the active Antigravity CLI / Google API.
    2. Local cache exists only to bridge concurrent token consumption across peer terminal windows
       in the EXACT SAME active reset cycle (when a peer consumed more tokens: c_rem < in_rem).
    3. If incoming data has an active reset cycle, and the cached item has a different cycle
       (|in_reset_at - c_reset_at| > 1800), incoming ALWAYS wins and overwrites stale/polluted cache.
    4. Cache must never lock out incoming authoritative data.
    """
    # 1. Parse incoming item
    in_valid = False
    in_rem = None
    in_sec = None
    in_reset_at = None

    if isinstance(item_in, dict):
        if "remaining_fraction" in item_in and item_in["remaining_fraction"] is not None:
            try:
                in_rem = max(0.0, min(1.0, float(item_in["remaining_fraction"])))
                in_valid = True
            except Exception:
                pass
        elif "used_percentage" in item_in and item_in["used_percentage"] is not None:
            try:
                in_rem = max(0.0, min(1.0, 1.0 - (float(item_in["used_percentage"]) / 100.0)))
                in_valid = True
            except Exception:
                pass

        in_reset_at = extract_reset_timestamp(item_in, now)
        raw_sec = item_in.get("reset_in_seconds")
        if raw_sec is not None:
            try:
                s = float(raw_sec)
                if s >= 0:
                    in_sec = int(s)
            except Exception:
                pass
        elif in_reset_at and in_reset_at > now:
            in_sec = max(0, int(in_reset_at - now))

    # 2. Parse and validate cached item with strict TTL and reset checks
    c_valid = False
    c_rem = None
    c_reset_at = None
    c_recorded_at = None

    if isinstance(cached_item, dict):
        if "remaining_fraction" in cached_item and cached_item["remaining_fraction"] is not None:
            try:
                c_rem = max(0.0, min(1.0, float(cached_item["remaining_fraction"])))
                c_valid = True
            except Exception:
                pass

        c_reset_at = extract_reset_timestamp(cached_item, now)
        c_recorded_at = cached_item.get("recorded_at") or now

        # Strict invalidation checks:
        if (now - c_recorded_at) > max_ttl:
            c_valid = False
        if c_reset_at and c_reset_at <= (now - 30):
            c_valid = False
        if not c_reset_at and (now - c_recorded_at) > 300:
            c_valid = False

    # Case 1: Neither valid
    if not in_valid and not c_valid:
        return item_in, None

    # Case 2: Only cache is valid (incoming payload has no quota fields)
    if not in_valid and c_valid:
        cur_sec = max(0, int(c_reset_at - now)) if c_reset_at else 0
        resolved = {
            "remaining_fraction": c_rem,
            "reset_in_seconds": cur_sec
        }
        return resolved, cached_item

    # Case 3: Only incoming is valid (cache expired, empty, or uninitialized)
    if in_valid and not c_valid:
        resolved = {
            "remaining_fraction": in_rem,
            "reset_in_seconds": in_sec
        }
        new_cache = {
            "remaining_fraction": in_rem,
            "reset_at": in_reset_at,
            "recorded_at": now
        }
        return resolved, new_cache

    # Case 4: Both appear valid
    # 4a. If reset cycles differ (|in_reset_at - c_reset_at| > 1800), incoming authoritative cycle wins!
    if in_reset_at and c_reset_at and abs(in_reset_at - c_reset_at) > 1800:
        resolved = {
            "remaining_fraction": in_rem,
            "reset_in_seconds": in_sec
        }
        new_cache = {
            "remaining_fraction": in_rem,
            "reset_at": in_reset_at,
            "recorded_at": now
        }
        return resolved, new_cache

    # 4b. Same cycle: check peer consumption
    target_reset_at = in_reset_at or c_reset_at
    target_sec = in_sec if in_sec is not None else (max(0, int(target_reset_at - now)) if target_reset_at else None)

    if in_rem is not None and c_rem is not None:
        if c_rem < in_rem - 0.005:
            # Peer terminal window consumed more tokens in the same active cycle
            resolved = {
                "remaining_fraction": c_rem,
                "reset_in_seconds": target_sec
            }
            updated_cache = {
                "remaining_fraction": c_rem,
                "reset_at": target_reset_at,
                "recorded_at": now
            }
            return resolved, updated_cache

    # Otherwise incoming is equal or has consumed more
    resolved = {
        "remaining_fraction": in_rem,
        "reset_in_seconds": target_sec
    }
    new_cache = {
        "remaining_fraction": in_rem,
        "reset_at": target_reset_at,
        "recorded_at": now
    }
    return resolved, new_cache


def sync_shared_quotas(
    q_5h: Optional[Dict[str, Any]],
    q_wk: Optional[Dict[str, Any]],
    is_3p: bool = False,
    allow_write: bool = True
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Synchronizes quotas across multiple CLI windows via local cache.
    Prevents concurrent sessions from displaying stale quota gauges.
    """
    try:
        now = time.time()
        pool_key = "3p" if is_3p else "gemini"
        cache = _read_quota_cache()
        pools = cache.get("pools", {})
        if not isinstance(pools, dict):
            pools = {}

        # Prune expired entries from all pools first
        cache_changed = _prune_expired_pools(pools, now)

        pool_cache = pools.get(pool_key, {})
        if not isinstance(pool_cache, dict):
            pool_cache = {}

        c_5h = pool_cache.get("5h")
        c_wk = pool_cache.get("weekly")

        # 5h quota max ttl = 5 hours (18000s); weekly max ttl = 7 days (604800s)
        res_5h, new_c_5h = reconcile_quota_item(q_5h, c_5h, now, max_ttl=18000.0)
        res_wk, new_c_wk = reconcile_quota_item(q_wk, c_wk, now, max_ttl=604800.0)

        if new_c_5h is not None and new_c_5h != c_5h:
            pool_cache["5h"] = new_c_5h
            cache_changed = True
        if new_c_wk is not None and new_c_wk != c_wk:
            pool_cache["weekly"] = new_c_wk
            cache_changed = True

        if cache_changed and allow_write:
            pools[pool_key] = pool_cache
            cache["pools"] = pools
            cache["updated_at"] = now
            _write_quota_cache(cache)

        return res_5h, res_wk
    except Exception:
        # Failsafe: if sync fails, return original data unaltered
        return q_5h, q_wk



def detect_permission_mode(data: Dict[str, Any]) -> str:
    """Extract or infer current agent execution/permission mode."""
    # 1. From payload if provided
    mode = data.get("permission_mode") or data.get("effective_permission_mode")
    if mode:
        m = str(mode).lower()
        if "bypass" in m or "danger" in m:
            return "bypass permissions on"
        if "sandbox" in m:
            return "sandbox mode"
        if "strict" in m:
            return "strict permissions"
        return f"mode: {mode}"

    # 2. Check settings.json permissions
    settings_path = os.path.expanduser("~/.gemini/antigravity-cli/settings.json")
    if os.path.isfile(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                perms = cfg.get("permissions", {})
                allow = perms.get("allow", [])
                if "*" in allow or "all" in allow:
                    return "bypass permissions on"
                if any("read_file(*)" in str(p) for p in allow):
                    return "bypass permissions on (read-all)"
                if cfg.get("sandbox"):
                    return "sandbox mode"
        except Exception:
            pass

    return "standard permissions"


def render_hud(data: Dict[str, Any], sync_cache: bool = True, term_width: Optional[int] = None) -> str:
    """
    Renders the sleek pastel HUD for Antigravity CLI.
    Supports responsive auto-wrapping / adaptive multi-line layout based on terminal width:
    - Wide (>= 100 cols): Single-line compact gauges.
    - Narrow / Normal (< 100 cols): Multi-line stacked gauges with aligned labels (matching claude-hud).
    - Compact countdowns and adaptive bar width to prevent any overflow or character clipping.
    """
    if term_width is None:
        term_width = data.get("terminal_width") or data.get("columns")
    if term_width is None:
        term_width = get_terminal_width()
    term_width = max(20, int(term_width))

    sep = f"{FG_SEP} │ {C_RESET}"
    bar_width = get_adaptive_bar_width(term_width)

    # === Line 1: [Model] │ Folder git:(branch*) ===
    model_obj = data.get("model") or {}
    raw_model = (
        model_obj.get("display_name")
        or model_obj.get("id")
        or data.get("model_name")
        or "Gemini 3.8 Flash"
    )
    clean_model = clean_model_name(raw_model)

    cwd = data.get("cwd") or (data.get("workspace") or {}).get("current_dir") or os.getcwd()
    folder_name = os.path.basename(os.path.abspath(cwd)) or "workspace"

    branch, is_dirty = detect_git_info(cwd)
    dirty_mark = "*" if is_dirty else ""
    git_str = f" {FG_GIT}git:({branch}{dirty_mark}){C_RESET}" if branch else ""

    badge = f"{FG_MODEL}[{clean_model}]{C_RESET}"
    folder_git = f"{FG_FOLDER}{folder_name}{C_RESET}{git_str}"
    line1_combined = f"{badge}{sep}{folder_git}"

    line1_items = []
    if visual_length(line1_combined) <= term_width:
        line1_items.append(line1_combined)
    else:
        line1_items.append(truncate_to_width(badge, term_width))
        line1_items.append(truncate_to_width(folder_git, term_width))

    # === Line 2: Context Gauge & Quota Gauges ===
    # 1. Context Window
    cw = data.get("context_window") or {}
    ctx_pct = cw.get("used_percentage")
    if ctx_pct is None:
        in_tok = cw.get("total_input_tokens") or 0
        out_tok = cw.get("total_output_tokens") or 0
        size = cw.get("context_window_size") or 1_000_000
        ctx_pct = ((in_tok + out_tok) / size * 100) if size > 0 else 0.0
    ctx_pct = float(ctx_pct)

    # Colorize context based on threshold
    if ctx_pct >= 85:
        c_ctx_fill, c_ctx_track, c_ctx_text = BG_CRIT_FILL, BG_CRIT_TRACK, FG_CRIT_TEXT
    elif ctx_pct >= 70:
        c_ctx_fill, c_ctx_track, c_ctx_text = BG_WARN_FILL, BG_WARN_TRACK, FG_WARN_TEXT
    else:
        c_ctx_fill, c_ctx_track, c_ctx_text = BG_CTX_FILL, BG_CTX_TRACK, FG_CTX_TEXT

    ctx_bar = make_solid_bar(ctx_pct, width=bar_width, fill_rgb=c_ctx_fill, track_rgb=c_ctx_track)

    # 2. Quotas: 5h and Weekly
    quotas = data.get("quota") or data.get("quotas") or {}
    model_id = str(model_obj.get("id") or "").lower()
    is_3p = any(k in model_id for k in ("claude", "gpt", "3p"))

    # Map keys
    k_5h = "3p-5h" if is_3p and "3p-5h" in quotas else ("gemini-5h" if "gemini-5h" in quotas else "five_hour")
    k_wk = "3p-weekly" if is_3p and "3p-weekly" in quotas else ("gemini-weekly" if "gemini-weekly" in quotas else "weekly")

    q_5h = quotas.get(k_5h) or quotas.get("five_hour") or quotas.get("5h")
    q_wk = quotas.get(k_wk) or quotas.get("weekly") or quotas.get("7d")

    # If quotas dict contains generic remaining_fraction
    if not q_5h and not q_wk and isinstance(quotas, dict):
        for k, v in quotas.items():
            if not isinstance(v, dict):
                continue
            kl = k.lower()
            if "5h" in kl or "five" in kl:
                q_5h = v
            elif "week" in kl or "7d" in kl:
                q_wk = v

    # Reconcile quotas across multiple terminal windows via persistent cache
    session_id = data.get("session_id") or data.get("conversation_id")
    allow_cache_write = bool(session_id)
    if sync_cache:
        q_5h, q_wk = sync_shared_quotas(q_5h, q_wk, is_3p=is_3p, allow_write=allow_cache_write)

    info_5h = None
    if isinstance(q_5h, dict):
        rem_frac = q_5h.get("remaining_fraction")
        if rem_frac is not None:
            used_pct = (1.0 - float(rem_frac)) * 100.0
        elif "used_percentage" in q_5h:
            used_pct = float(q_5h["used_percentage"])
        else:
            used_pct = None

        if used_pct is not None:
            used_pct = max(0.0, min(100.0, used_pct))
            sec = q_5h.get("reset_in_seconds")
            info_5h = (used_pct, sec)

    info_wk = None
    if isinstance(q_wk, dict):
        rem_frac = q_wk.get("remaining_fraction")
        if rem_frac is not None:
            used_pct = (1.0 - float(rem_frac)) * 100.0
        elif "used_percentage" in q_wk:
            used_pct = float(q_wk["used_percentage"])
        else:
            used_pct = None

        if used_pct is not None:
            used_pct = max(0.0, min(100.0, used_pct))
            sec = q_wk.get("reset_in_seconds")
            info_wk = (used_pct, sec)

    def _quota_colors(u_pct: float) -> Tuple[Tuple[int, int, int], Tuple[int, int, int], str]:
        if u_pct >= 90:
            return BG_CRIT_FILL, BG_CRIT_TRACK, FG_CRIT_TEXT
        elif u_pct >= 75:
            return BG_WARN_FILL, BG_WARN_TRACK, FG_WARN_TEXT
        else:
            return BG_USAGE_FILL, BG_USAGE_TRACK, FG_USAGE_TEXT

    def _format_dur(sec_val: Optional[int], is_compact: bool) -> str:
        if not sec_val or sec_val <= 0:
            return ""
        d_text = format_duration(sec_val)
        if not d_text:
            return ""
        if is_compact:
            return f" {FG_LABEL}({d_text}){C_RESET}"
        return f" {FG_LABEL}(resets in {d_text}){C_RESET}"

    # Single-line candidate (with full resets label)
    inline_gauges = [
        f"{FG_LABEL}Context{C_RESET} {ctx_bar} {c_ctx_text}{ctx_pct:.0f}%{C_RESET}"
    ]

    if info_5h:
        u_5h, sec_5h = info_5h
        qf5, qt5, qtxt5 = _quota_colors(u_5h)
        b_5h = make_solid_bar(u_5h, width=bar_width, fill_rgb=qf5, track_rgb=qt5)
        d_5h = _format_dur(sec_5h, is_compact=False)
        inline_gauges.append(f"{FG_LABEL}5h{C_RESET} {b_5h} {qtxt5}{u_5h:.0f}%{C_RESET}{d_5h}")

    if info_wk:
        u_wk, sec_wk = info_wk
        qfw, qtw, qtxtw = _quota_colors(u_wk)
        b_wk = make_solid_bar(u_wk, width=bar_width, fill_rgb=qfw, track_rgb=qtw)
        d_wk = _format_dur(sec_wk, is_compact=False)
        inline_gauges.append(f"{FG_LABEL}Weekly{C_RESET} {b_wk} {qtxtw}{u_wk:.0f}%{C_RESET}{d_wk}")

    gauge_combined = sep.join(inline_gauges)
    gauge_lines = []

    if visual_length(gauge_combined) <= term_width:
        gauge_lines.append(gauge_combined)
    else:
        # Stacked mode with aligned labels (claude-hud style):
        # Labels: "Context" (7), "Usage  " (7), "Weekly " (7)
        label_w = 7
        is_compact_dur = (term_width < 50)

        l_ctx = FG_LABEL + "Context".ljust(label_w) + C_RESET
        gauge_lines.append(f"{l_ctx} {ctx_bar} {c_ctx_text}{ctx_pct:.0f}%{C_RESET}")

        if info_5h:
            u_5h, sec_5h = info_5h
            qf5, qt5, qtxt5 = _quota_colors(u_5h)
            b_5h = make_solid_bar(u_5h, width=bar_width, fill_rgb=qf5, track_rgb=qt5)
            d_5h = _format_dur(sec_5h, is_compact=is_compact_dur)
            l_5h = FG_LABEL + "Usage".ljust(label_w) + C_RESET
            gauge_lines.append(f"{l_5h} {b_5h} {qtxt5}{u_5h:.0f}%{C_RESET}{d_5h}")

        if info_wk:
            u_wk, sec_wk = info_wk
            qfw, qtw, qtxtw = _quota_colors(u_wk)
            b_wk = make_solid_bar(u_wk, width=bar_width, fill_rgb=qfw, track_rgb=qtw)
            d_wk = _format_dur(sec_wk, is_compact=is_compact_dur)
            l_wk = FG_LABEL + "Weekly".ljust(label_w) + C_RESET
            gauge_lines.append(f"{l_wk} {b_wk} {qtxtw}{u_wk:.0f}%{C_RESET}{d_wk}")

    # === Line 3: >> Mode (shift+tab to cycle) · Agent State ===
    perm_mode = detect_permission_mode(data)
    agent_state = data.get("agent_state") or "idle"

    # Mode text styling
    if "bypass" in perm_mode:
        mode_str = f"\x1b[38;2;255;120;120m>> {perm_mode}{C_RESET}"
    elif "sandbox" in perm_mode:
        mode_str = f"\x1b[38;2;120;200;255m>> {perm_mode}{C_RESET}"
    else:
        mode_str = f"\x1b[38;2;180;180;180m>> {perm_mode}{C_RESET}"

    hint_str = f"{FG_LABEL}(shift+tab to cycle){C_RESET}"
    state_str = f"{FG_LABEL}· {agent_state}{C_RESET}"
    line3_full = f"{mode_str} {hint_str} {state_str}"

    mode_lines = []
    if visual_length(line3_full) <= term_width:
        mode_lines.append(line3_full)
    else:
        part_a = mode_str
        part_b = f"{hint_str} {state_str}"
        if term_width >= 50 and visual_length(part_a) <= term_width and visual_length(part_b) <= term_width:
            mode_lines.append(part_a)
            mode_lines.append(part_b)
        else:
            short_line3 = f"{mode_str} {state_str}"
            if visual_length(short_line3) <= term_width:
                mode_lines.append(short_line3)
            else:
                mode_lines.append(truncate_to_width(short_line3, term_width))

    all_lines = line1_items + gauge_lines + mode_lines
    final_lines = [truncate_to_width(l, term_width) for l in all_lines]
    return "\n".join(final_lines)


def main():
    if len(sys.argv) > 1 and any(arg in ("--preview", "-p", "--test", "-t") for arg in sys.argv):
        target_w = None
        for idx, arg in enumerate(sys.argv):
            if arg in ("--width", "-w") and idx + 1 < len(sys.argv):
                try:
                    target_w = int(sys.argv[idx + 1])
                except ValueError:
                    pass

        # Sample preview data mimicking actual Antigravity payload
        preview_data = {
            "model": {
                "id": "gemini-3.8-flash-high",
                "display_name": "Gemini 3.8 Flash (High)",
            },
            "cwd": os.getcwd(),
            "agent_state": "idle",
            "permission_mode": "bypass permissions on (read-all)",
            "context_window": {
                "total_input_tokens": 41000,
                "total_output_tokens": 1200,
                "context_window_size": 1000000,
                "used_percentage": 4.0,
            },
            "quota": {
                "gemini-5h": {
                    "remaining_fraction": 0.86,
                    "reset_in_seconds": 14400,
                },
                "gemini-weekly": {
                    "remaining_fraction": 0.22,
                    "reset_in_seconds": 38000,
                },
            },
        }
        print(render_hud(preview_data, sync_cache=False, term_width=target_w))
        return

    try:
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            # Fallback if invoked with empty stdin
            print(render_hud({}))
            return
        data = json.loads(raw)
        if not isinstance(data, dict):
            print(render_hud({}))
            return
        print(render_hud(data))
    except Exception:
        # Failsafe: never crash the statusline
        print(render_hud({}))


if __name__ == "__main__":
    main()
