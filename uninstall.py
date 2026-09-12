#!/usr/bin/env python3
"""
Uninstaller for agy-hud.
Reverts Antigravity statusLine settings to default.
"""

import os
import sys
import json

SETTINGS_PATH = os.path.expanduser("~/.gemini/antigravity-cli/settings.json")
DEST_SCRIPT_PATH = os.path.expanduser("~/.gemini/antigravity-cli/statusline.py")


def main():
    print("\x1b[1;38;2;208;209;254m[agy-hud]\x1b[0m Uninstalling statusline...")

    # 1. Remove statusLine key from settings.json
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                settings = json.load(f)
            if "statusLine" in settings:
                del settings["statusLine"]
                with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                    json.dump(settings, f, indent=2, ensure_ascii=False)
                print(f"✓ Removed 'statusLine' from {SETTINGS_PATH}")
        except Exception as e:
            print(f"Warning: Could not update settings: {e}")

    # 2. Remove script file
    if os.path.isfile(DEST_SCRIPT_PATH):
        try:
            os.remove(DEST_SCRIPT_PATH)
            print(f"✓ Removed {DEST_SCRIPT_PATH}")
        except Exception as e:
            print(f"Warning: Could not delete script: {e}")

    print("\x1b[32m✔ agy-hud uninstalled successfully.\x1b[0m Antigravity CLI has reverted to its built-in statusline.")


if __name__ == "__main__":
    main()
