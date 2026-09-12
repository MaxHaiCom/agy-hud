#!/usr/bin/env python3
"""
Installer for agy-hud.
Automates backup of Antigravity settings and configuration of statusLine hook.
"""

import os
import sys
import json
import shutil
import time

SETTINGS_PATH = os.path.expanduser("~/.gemini/antigravity-cli/settings.json")
DEST_SCRIPT_PATH = os.path.expanduser("~/.gemini/antigravity-cli/statusline.py")
SOURCE_SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statusline.py")


def main():
    print("\x1b[1;38;2;208;209;254m[agy-hud]\x1b[0m Installing seamless pastel statusline for Antigravity CLI...")

    if not os.path.isfile(SOURCE_SCRIPT_PATH):
        print(f"\x1b[31mError:\x1b[0m Cannot find source statusline.py at {SOURCE_SCRIPT_PATH}")
        sys.exit(1)

    # 1. Ensure target directory exists
    os.makedirs(os.path.dirname(DEST_SCRIPT_PATH), exist_ok=True)

    # 2. Copy statusline.py
    shutil.copy2(SOURCE_SCRIPT_PATH, DEST_SCRIPT_PATH)
    os.chmod(DEST_SCRIPT_PATH, 0o755)
    print(f"✓ Installed statusline script to {DEST_SCRIPT_PATH}")

    # 3. Update settings.json safely
    settings = {}
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                settings = json.load(f)
            # Create timestamped backup
            ts = int(time.time())
            bak_path = f"{SETTINGS_PATH}.bak.{ts}"
            shutil.copy2(SETTINGS_PATH, bak_path)
            print(f"✓ Backed up existing settings to {bak_path}")
        except Exception as e:
            print(f"\x1b[33mWarning:\x1b[0m Could not parse existing settings ({e}), creating fresh configuration.")

    # Inject statusLine config
    statusline_cmd = f"python3 {DEST_SCRIPT_PATH}"
    settings["statusLine"] = {
        "type": "command",
        "command": statusline_cmd
    }

    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    print(f"✓ Configured 'statusLine' in {SETTINGS_PATH}")

    # 4. Run test preview
    print("\n\x1b[1;38;2;180;250;114m[agy-hud Live Preview]\x1b[0m")
    os.system(f"python3 {DEST_SCRIPT_PATH} --preview")
    print("\n\x1b[32m✔ Installation complete!\x1b[0m Next time you start `agy`, your HUD will render above the prompt.")


if __name__ == "__main__":
    main()
