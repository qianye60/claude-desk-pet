# -*- coding: utf-8 -*-
"""
皮肤（形态）加载。

一个“形态”就是一个文件夹里的一组立绘：
    skin/            旧版位置，作为第一个形态
    skins/<名字>/    每个子文件夹是一个形态，右键菜单或状态面板里可以切换

每个形态文件夹里：
    sit.png 或 idle.png   平时的样子（必须）
    blink / happy / cheer / wave / pout / worried / working / sleep / drag .png   都是可选的
    同一个表情可以有多张，写成 name_说明.png（比如 working_写笔记.png），会随机用
    skin.json  {"name": "显示名", "persona": "这个形态的 AI 人格描述", "height": 220, "edge": 1.0, "head": 0.15}
               切换形态时 AI 的人格（说话风格）也会跟着换

缺哪张图就按顺序往下找替代：
    cheer/wave -> happy -> 平时；pout -> worried -> 平时；working/worried/happy/drag -> 平时；sleep -> blink -> 平时
"""
import os
import json

from PIL import Image, ImageDraw


STATES = {
    # 状态: 可接受的文件名前缀
    "sit": ("sit", "idle"),
    "blink": ("blink",),
    "happy": ("happy",),
    "cheer": ("cheer",),
    "wave": ("wave",),
    "pout": ("pout",),
    "worried": ("worried",),
    "working": ("working",),
    "sleep": ("sleep",),
    "drag": ("drag",),
}

FALLBACK = {
    "cheer": ("happy",), "wave": ("happy",), "pout": ("worried",), "sleep": ("blink",),
}


class Form:
    """一个加载好的形态：states[状态] = [PIL 图（物理像素尺寸）...]"""

    def __init__(self, fid, name, states, edge_y, head_y, char_w, char_h, persona=""):
        self.id, self.name = fid, name
        self.persona = persona
        self.scale = 1.0
        self.states = states
        self.edge_y, self.head_y = edge_y, head_y
        self.char_w, self.char_h = char_w, char_h

    def resolve(self, state):
        """返回实际有图的状态名（按 FALLBACK 往下找，最后落到 sit）"""
        seen = [state]
        i = 0
        while i < len(seen):
            s = seen[i]
            if s in self.states and self.states[s]:
                return s
            for nxt in FALLBACK.get(s, ()):
                if nxt not in seen:
                    seen.append(nxt)
            i += 1
        return "sit"


# ---------------------------------------------------------------- 发现形态
def _meta_of(folder):
    meta = {"height": 200, "edge": 1.0, "head": 0.15}
    mp = os.path.join(folder, "skin.json")
    if os.path.exists(mp):
        try:
            with open(mp, "r", encoding="utf-8") as f:
                meta.update(json.load(f))
        except Exception as e:
            print("skin.json 读取失败：", mp, e)
    return meta


def _has_base(folder):
    return any(os.path.exists(os.path.join(folder, n + ".png")) or _variants(folder, n)
               for n in STATES["sit"])


def discover(base_dir):
    """返回 [(id, 显示名, 文件夹)]；一个都没有就是空列表（由调用方提示用户放图）"""
    out = []
    order = {"skins/pixel": 0, "skin": 1, "skins/yujie": 2}
    legacy = os.path.join(base_dir, "skin")
    if os.path.isdir(legacy) and _has_base(legacy):
        out.append(("skin", _meta_of(legacy).get("name", "元气少女"), legacy))
    root = os.path.join(base_dir, "skins")
    if os.path.isdir(root):
        for d in sorted(os.listdir(root)):
            p = os.path.join(root, d)
            if os.path.isdir(p) and _has_base(p):
                out.append(("skins/" + d, _meta_of(p).get("name", d), p))
    out.sort(key=lambda f: order.get(f[0], 9))      # 像素机器人在最左，然后是可爱、御姐，其余按名字
    return out


def tagline_of(folder):
    return _meta_of(folder).get("tagline", "") if folder else ""


# ---------------------------------------------------------------- 加载
def _variants(folder, name):
    """name.png 在前，再加所有 name_xxx.png（按文件名排序）"""
    res = []
    p = os.path.join(folder, name + ".png")
    if os.path.exists(p):
        res.append(p)
    try:
        res += [os.path.join(folder, f) for f in sorted(os.listdir(folder))
                if f.lower().startswith(name + "_") and f.lower().endswith(".png")]
    except OSError:
        pass
    return res


def _clean(im):
    """四角是不透明白色就从四角抠掉白底；再把 alpha 很低的杂点清零（否则会挡住鼠标点击）"""
    w, h = im.size
    corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    px = im.load()
    if all(px[c][3] > 250 and min(px[c][:3]) > 235 for c in corners):
        for c in corners:
            if im.getpixel(c)[3] != 0:
                ImageDraw.floodfill(im, c, (255, 255, 255, 0), thresh=60)
    r, g, b, a = im.split()
    a = a.point(lambda v: 0 if v < 8 else v)
    im.putalpha(a)
    return im


def _bbox(im):
    return im.getchannel("A").getbbox()


def load(fid, name, folder, cfg, dpr, scale=1.0):
    meta = _meta_of(folder)
    height = float(meta["height"]) * scale

    paths = {}
    for state, names in STATES.items():
        found = []
        for n in names:
            found = _variants(folder, n)
            if found:
                break
        if state == "sit":
            found = found[:1]
        if found:
            paths[state] = found

    raw = {state: [_clean(Image.open(p).convert("RGBA")) for p in ps] for state, ps in paths.items()}
    allim = [im for ims in raw.values() for im in ims]

    # 同一画布尺寸的图用同一个取景框裁掉透明边，切换表情时人物不会跳
    if len({im.size for im in allim}) == 1:
        boxes = [b for b in map(_bbox, allim) if b]
        if boxes:
            box = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                   max(b[2] for b in boxes), max(b[3] for b in boxes))
            raw = {s: [im.crop(box) for im in ims] for s, ims in raw.items()}
    else:
        raw = {s: [im.crop(_bbox(im)) if _bbox(im) else im for im in ims] for s, ims in raw.items()}

    ref = raw["sit"][0]
    h = max(1, int(round(height * dpr)))
    w = max(1, int(round(ref.width * h / ref.height)))

    resample = Image.NEAREST if meta.get("pixel") else Image.LANCZOS   # 像素风放大不模糊

    def fit(im):
        return im.resize((w, h), resample)   # 所有图缩成和 sit 一样的像素尺寸，切换不跳

    states = {s: [fit(im) for im in ims] for s, ims in raw.items()}
    form = Form(fid, name, states, height * float(meta["edge"]), height * float(meta["head"]),
                w / dpr, h / dpr, persona=str(meta.get("persona", "")))
    form.scale = scale
    return form



def thumbnail(folder, px):
    """菜单里的形态缩略图：取 sit/idle 那张，裁掉透明边（返回 PIL 图，物理像素 px×px 的方图）"""
    for n in STATES["sit"]:
        v = _variants(folder, n)
        if v:
            im = _clean(Image.open(v[0]).convert("RGBA"))
            box = _bbox(im)
            if box:
                im = im.crop(box)
            if im.height > im.width * 1.2:                       # 全身立绘：缩略图取头和上半身那一块
                im = im.crop((0, 0, im.width, im.width))
            side = max(im.width, im.height)
            canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            canvas.paste(im, ((side - im.width) // 2, 0))      # 顶端对齐，头像取上半身
            pixel = _meta_of(folder).get("pixel")
            return canvas.resize((px, px), Image.NEAREST if pixel else Image.LANCZOS)
    return None
