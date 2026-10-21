# -*- coding: utf-8 -*-
"""
从 GitHub 下载 Ancean/claude-musume（MIT 许可）的角色立绘到 skin 文件夹。
用法：python get_skin.py
只下载本程序用得到的图（idle / blink / happy / sleep / drag）和 LICENSE，
并写入 skin.json（已存在则不覆盖）。
"""
import os
import sys
import json
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SKIN_DIR = os.path.join(BASE_DIR, "skin")
RAW = "https://raw.githubusercontent.com/Ancean/claude-musume/main/"

FILES = [
    ("LICENSE", "LICENSE"),
    ("buddy-art/idle.png", "idle.png"),
    ("buddy-art/blink.png", "blink.png"),
    ("buddy-art/happy.png", "happy.png"),
    ("buddy-art/sleep.png", "sleep.png"),
    ("buddy-art/drag.png", "drag.png"),
    # 更多形态/动作用到的图
    ("buddy-art/wave.png", "wave.png"),
    ("buddy-art/pout.png", "pout.png"),
    ("buddy-art/worried.png", "worried.png"),
    ("buddy-art/cheer.png", "cheer.png"),
    ("buddy-art/working.png", "working.png"),
    ("buddy-art/working_托腮.png", "working_托腮.png"),
    ("buddy-art/working_写笔记.png", "working_写笔记.png"),
]
DEFAULT_META = {"name": "元气少女", "tagline": "元气 · 爱撒娇", "persona": '你是住在电脑桌面 Claude 窗口边上的一只小桌宠，是个活泼可爱、有点小幽默的少女形象，陪主人写代码、聊天。说话简短自然，每句不超过 24 个汉字，口语化，偶尔撒个娇。',
                "height": 220, "edge": 1.0, "head": 0.15}


def download(remote, local):
    dest = os.path.join(SKIN_DIR, local)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print("已存在，跳过：", local)
        return True
    try:
        req = urllib.request.Request(RAW + urllib.parse.quote(remote), headers={"User-Agent": "claude-pet"})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            f.write(r.read())
        print("已下载：", local, os.path.getsize(dest), "bytes")
        return True
    except Exception as e:
        print("下载失败：", remote, e)
        return False


def main():
    os.makedirs(SKIN_DIR, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as ex:   # 单张下载很慢，并行下
        ok = all(list(ex.map(lambda rl: download(*rl), FILES)))
    meta = os.path.join(SKIN_DIR, "skin.json")
    if not os.path.exists(meta):
        with open(meta, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_META, f, indent=2)
    print("完成" if ok else "有文件下载失败，请检查网络后重试")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
