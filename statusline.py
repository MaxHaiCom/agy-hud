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
from typing import Dict, Any, Tuple, Optional

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


def render_hud(data: Dict[str, Any]) -> str:
    """Renders the complete 3-line pastel HUD for Antigravity CLI."""
    sep = f"{FG_SEP} │ {C_RESET}"

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

    line1 = f"{FG_MODEL}[{clean_model}]{C_RESET}{sep}{FG_FOLDER}{folder_name}{C_RESET}{git_str}"

    # === Line 2: Context Gauge & Quota Gauges ===
    line2_parts = []

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

    ctx_bar = make_solid_bar(ctx_pct, width=8, fill_rgb=c_ctx_fill, track_rgb=c_ctx_track)
    line2_parts.append(f"{FG_LABEL}Context{C_RESET} {ctx_bar} {c_ctx_text}{ctx_pct:.0f}%{C_RESET}")

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

    # Format 5h Quota
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
            dur_str = f" {FG_LABEL}(resets in {format_duration(sec)}){C_RESET}" if sec else ""
            if used_pct >= 90:
                q_fill, q_track, q_text = BG_CRIT_FILL, BG_CRIT_TRACK, FG_CRIT_TEXT
            elif used_pct >= 75:
                q_fill, q_track, q_text = BG_WARN_FILL, BG_WARN_TRACK, FG_WARN_TEXT
            else:
                q_fill, q_track, q_text = BG_USAGE_FILL, BG_USAGE_TRACK, FG_USAGE_TEXT
            bar_5h = make_solid_bar(used_pct, width=8, fill_rgb=q_fill, track_rgb=q_track)
            line2_parts.append(f"{FG_LABEL}5h{C_RESET} {bar_5h} {q_text}{used_pct:.0f}%{C_RESET}{dur_str}")

    # Format Weekly Quota
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
            dur_str = f" {FG_LABEL}(resets in {format_duration(sec)}){C_RESET}" if sec else ""
            if used_pct >= 90:
                q_fill, q_track, q_text = BG_CRIT_FILL, BG_CRIT_TRACK, FG_CRIT_TEXT
            elif used_pct >= 75:
                q_fill, q_track, q_text = BG_WARN_FILL, BG_WARN_TRACK, FG_WARN_TEXT
            else:
                q_fill, q_track, q_text = BG_USAGE_FILL, BG_USAGE_TRACK, FG_USAGE_TEXT
            bar_wk = make_solid_bar(used_pct, width=8, fill_rgb=q_fill, track_rgb=q_track)
            line2_parts.append(f"{FG_LABEL}Usage Weekly{C_RESET} {bar_wk} {q_text}{used_pct:.0f}%{C_RESET}{dur_str}")

    line2 = sep.join(line2_parts)

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

    line3 = f"{mode_str} {FG_LABEL}(shift+tab to cycle) · {agent_state}{C_RESET}"

    return f"{line1}\n{line2}\n{line3}"


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--preview", "-p", "--test", "-t"):
        # Sample preview data mimicking actual Antigravity payload
        preview_data = {
            "model": {
                "id": "gemini-3.8-flash-high",
                "display_name": "Gemini 3.8 Flash (High)",
            },
            "cwd": os.getcwd(),
            "agent_state": "idle",
            "permission_mode": "bypass permissions on",
            "context_window": {
                "total_input_tokens": 410000,
                "total_output_tokens": 12000,
                "context_window_size": 1000000,
                "used_percentage": 41.0,
            },
            "quota": {
                "gemini-5h": {
                    "remaining_fraction": 0.82,
                    "reset_in_seconds": 15120,
                },
                "gemini-weekly": {
                    "remaining_fraction": 0.35,
                    "reset_in_seconds": 140400,
                },
            },
        }
        print(render_hud(preview_data))
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
