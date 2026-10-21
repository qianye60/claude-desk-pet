# -*- coding: utf-8 -*-
"""
翻翻文件夹（需要你确认才会开始）：只读取文件名、类型、大小、修改时间，从不读文件内容。
这些文件名会通过 Claude Code 命令行发给 AI，让她挑几个有意思的调侃一下。

- 默认只看桌面、文档、视频三个文件夹，最多往下两层（config.json 的 snoop_folders 可以改）
- 隐藏文件、系统文件、程序/依赖目录会跳过；名字里带 password / token / secret / key / .env / 证件 等的不会发出去
- 想关掉：config.json 里 "snoop_enabled": false
"""
import os
import time
import random

SKIP_DIRS = {"node_modules", ".git", "__pycache__", "venv", ".venv", "site-packages", "AppData", "$RECYCLE.BIN",
             "System Volume Information", "My Music", "My Pictures", "My Videos"}
SENSITIVE = ("password", "passwd", "secret", "token", "credential", "private", "id_rsa", ".env", ".pem",
             ".key", "keystore", "apikey", "api_key", "密码", "口令", "密钥", "私钥", "身份证", "银行卡", "护照",
             "账号", "账户", "验证码", "助记词", "wallet")
KIND = {
    "video": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts", ".rmvb"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".psd"},
    "doc": {".doc", ".docx", ".pdf", ".txt", ".md", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".epub"},
    "code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".html", ".css", ".json", ".sql", ".vue"},
    "archive": {".zip", ".rar", ".7z", ".tar", ".gz", ".iso"},
    "app": {".exe", ".msi", ".lnk", ".url"},
}


def default_folders():
    home = os.path.expanduser("~")
    return [os.path.join(home, "Desktop"), os.path.join(home, "Documents"), os.path.join(home, "Videos")]


def _kind(name, is_dir):
    if is_dir:
        return "文件夹"
    ext = os.path.splitext(name)[1].lower()
    for k, exts in KIND.items():
        if ext in exts:
            return {"video": "视频", "image": "图片", "doc": "文档", "code": "代码",
                    "archive": "压缩包", "app": "程序/快捷方式"}[k]
    return "其他"


def _ok(name):
    low = name.lower()
    return not name.startswith(".") and not any(s in low for s in SENSITIVE)


def scan(folders, max_items=70, depth=2):
    """返回 (摘要文本, 条目数)。只含文件名/类型/大小/修改时间，不含内容"""
    items = []
    for root in folders:
        root = os.path.expanduser(root)
        if not os.path.isdir(root):
            continue
        label = os.path.basename(root.rstrip("\\/")) or root
        stack = [(root, 0)]
        count = 0
        while stack and count < 400:
            cur, d = stack.pop()
            try:
                with os.scandir(cur) as it:
                    entries = list(it)
            except OSError:
                continue
            for e in entries:
                try:
                    if e.name in SKIP_DIRS or not _ok(e.name):
                        continue
                    isdir = e.is_dir(follow_symlinks=False)
                    st = e.stat(follow_symlinks=False)
                    count += 1
                    rel = os.path.relpath(e.path, root)
                    items.append((st.st_mtime, label, rel, _kind(e.name, isdir), st.st_size, isdir))
                    if isdir and d + 1 < depth:
                        stack.append((e.path, d + 1))
                except OSError:
                    continue
    if not items:
        return "", 0
    items.sort(key=lambda x: -x[0])
    recent = items[:max_items // 2]
    rest = items[max_items // 2:]
    random.shuffle(rest)                       # 再随机抽一些旧的，别只看最近的
    pick = recent + rest[:max_items - len(recent)]
    lines = []
    for mt, label, rel, kind, size, isdir in pick:
        size_s = "" if isdir else (f"{size / 1048576:.0f}MB" if size >= 1048576 else f"{size / 1024:.0f}KB")
        age = int((time.time() - mt) // 86400)
        lines.append(f"[{label}] {rel}（{kind}{'，' + size_s if size_s else ''}，{age}天前）")
    return "\n".join(lines), len(items)
