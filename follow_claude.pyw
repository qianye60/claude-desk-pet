# -*- coding: utf-8 -*-
"""
常驻小哨兵：登录 Windows 时自动运行，不加载界面库，很省资源。
每 3 秒看一次 Claude Desktop 的窗口，窗口从无到有时把桌宠叫出来。
桌宠自己负责在 Claude 关掉后退出。
"""
import os
import sys
import json
import time
import subprocess
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import claude_win as cw  # noqa: E402


def read_config():
    try:
        with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def launch_pet():
    subprocess.Popen([cw.pythonw_path(), os.path.join(BASE_DIR, "desktop_pet.py"), "--follow"],
                     cwd=BASE_DIR, creationflags=0x08000000)


def main():
    if not cw.single_instance(cw.SENTINEL_MUTEX):
        return
    cfg = read_config()
    finder = cw.ClaudeFinder(cfg.get("claude_process_names", ["claude.exe"]))
    was_open = False
    while True:
        cfg = read_config()
        if not cfg.get("follow_claude", True):
            return  # 在菜单里关掉了跟随，哨兵也下班
        is_open = finder.exists()
        if is_open and not was_open and not cw.instance_running(cw.PET_MUTEX):
            launch_pet()
        was_open = is_open
        time.sleep(3)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(os.path.join(BASE_DIR, "follow.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S\n") + traceback.format_exc() + "\n")
