# 🪶 agy-hud

A sleek, seamless, pastel HUD statusline for **Google Antigravity CLI (`agy`)**.

[English](README.md) | [中文说明](#-中文说明)

```text
[3.8 Flash High] │ my-app git:(main*)
Context          41% │ 5h          82% (4h 12m) │ Usage Weekly          65% (1d 15h)
>> bypass permissions on (shift+tab to cycle) · idle
```

---

## ✨ Features

- 🎨 **Apple & Linear Pastel Palette** — High-taste, muted pastel colorway (soft lime green, baby blue, warm amber, lavender) replacing harsh, high-saturation neon colors.
- 🧊 **100% Solid Seamless Bars** — Uses 24-bit ANSI background blocks on space cells. **Zero vertical character gap lines**, rendering smooth, solid progress blocks in all modern terminals (Warp, iTerm2, Kitty, Ghostty, Alacritty).
- ⏳ **Dual Quota Monitoring** — Tracks rolling **5-Hour** and **Weekly** quotas with dynamic countdown timers (`(4h 12m)`, `(1d 15h)`). Automatically maps both Google native models and Claude/GPT 3P models.
- 🧠 **Context Window Metrics** — Real-time context usage percentage and automatic color shifts (lime green `< 70%`, warm amber `70% - 85%`, coral red `≥ 85%`).
- 📁 **Workspace & Git Detection** — Fast direct filesystem inspection of `.git/HEAD` for branch name and uncommitted dirty changes (`*`).
- 🛡️ **Execution & Permission Mode** — Displays current agent security posture (`>> bypass permissions on`, `sandbox mode`, etc.).
- 🪶 **Zero External Dependencies** — Written in pure Python 3 standard library (`sys`, `os`, `json`, `subprocess`). Sub-millisecond execution with no noticeable CLI latency.

---

## 🚀 Quick Start

### 1. Installation

Clone the repository and run the installer:

```bash
git clone https://github.com/MaxHaiCom/agy-hud.git
cd agy-hud
python3 install.py
```

The installer will:
1. Copy `statusline.py` to `~/.gemini/antigravity-cli/statusline.py`.
2. Create a timestamped backup of your `~/.gemini/antigravity-cli/settings.json`.
3. Configure the `"statusLine"` hook in `settings.json`.
4. Output a live preview.

### 2. Manual Configuration

Alternatively, copy `statusline.py` to `~/.gemini/antigravity-cli/` and edit `~/.gemini/antigravity-cli/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.gemini/antigravity-cli/statusline.py"
  }
}
```

---

## 🔍 Preview & Testing

Preview the rendering directly from your terminal:

```bash
python3 statusline.py --preview
```

---

## 🗑️ Uninstallation

To remove the statusline hook and revert to the built-in default:

```bash
python3 uninstall.py
```

---

<br>

# 🇨🇳 中文说明

专为 **Google Antigravity CLI (`agy`)** 设计的极简克制、无缝浅色调（Pastel）HUD 状态栏。

### ✨ 核心亮点

1. **淡雅低饱和配色（Apple / Linear 质感）**：告别刺眼的廉价荧光霓虹色，采用柔和浅绿、婴儿浅蓝、薰衣草浅紫等极简高质感色系。
2. **纯色无缝进度条（彻底消除字符间隙）**：通过 24-bit ANSI 背景色渲染空格实现，**彻底杜绝传统字符进度条的竖条细线间隙**，在 Warp / iTerm2 / Ghostty 等终端下呈现一整块连贯的圆润色块。
3. **5h 与周度双配额监控**：实时计算滚动 5 小时与周度剩余额度，并精确计算重置倒计时（例如 `(4h 12m)`、`(1d 15h)`）。自动适配 Gemini 原生模型与 Claude/GPT 3P 模型。
4. **实时 Context 占用**：精确展示上下文窗口用量比例，多阶段预警换色（绿色 `< 70%`、暖黄 `70% - 85%`、珊瑚红 `≥ 85%`）。
5. **当前模式与权限提醒**：直观展示当前执行状态（如 `>> bypass permissions on`、`sandbox mode` 等）。
6. **零外部依赖**：纯 Python 3 标准库单文件实现，毫秒级快速启动，绝不拖慢终端交互。

### 🚀 安装与使用

```bash
git clone https://github.com/MaxHaiCom/agy-hud.git
cd agy-hud
python3 install.py
```

---

## 📄 License

[MIT License](LICENSE) © 2026 MaxHaiCom
