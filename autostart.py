# -*- coding: utf-8 -*-
"""python autostart.py on|off  —— 开启/关闭"打开 Claude 时自动叫出桌宠" """
import os
import sys
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import claude_win as cw  # noqa: E402

on = len(sys.argv) > 1 and sys.argv[1].lower() == "on"
cfg_path = os.path.join(BASE_DIR, "config.json")
cfg = {}
if os.path.exists(cfg_path):
    with open(cfg_path, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)
cfg["follow_claude"] = on
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
cw.set_autostart(on, BASE_DIR)
print("Auto-follow Claude: " + ("ON" if on else "OFF"))
