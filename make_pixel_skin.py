# -*- coding: utf-8 -*-
"""
生成「像素机器人」形态（skins/pixel）：Claude 的橙色小机器人，按像素格子画出一整套姿势。
用法：python make_pixel_skin.py
想换成自己的像素图：直接把同名 PNG 放进 skins/pixel 覆盖即可（保持同样的画布大小）。
"""
import os
import json

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "skins", "pixel")
W, H, SCALE = 44, 36, 10                    # 画布（格子数）和放大倍数

ORANGE = (215, 119, 87, 255)
ORANGE_ANGRY = (230, 98, 72, 255)
EYE = (36, 26, 22, 255)
BOOK = (112, 72, 52, 255)
PAGE = (244, 230, 206, 255)
DROP = (126, 190, 240, 255)
BLUSH = (244, 150, 150, 255)
QMARK = (255, 214, 130, 255)

PERSONA = ("你是住在电脑桌面 Claude 窗口边上的一只像素小机器人，是 Claude 的小助手形象：话不多，"
           "安静、冷幽默、偶尔笨拙地卖个萌，爱用程序员的口吻吐槽（比如“编译通过了，奇迹”）。"
           "说话极简，每句不超过 20 个汉字，不撒娇，不用颜文字。")

# 部件（格子坐标，闭区间）
BODY = (6, 10, 29, 26)                      # 24 x 17
ARM_L, ARM_R = (2, 19, 5, 22), (30, 19, 33, 22)
EYE_L, EYE_R = (10, 14, 11, 17), (24, 14, 25, 17)
LEGS = [(8, 27, 9, 31), (11, 27, 12, 31), (22, 27, 23, 31), (25, 27, 26, 31)]


def rect(d, box, color, dx=0, dy=0):
    x0, y0, x1, y1 = box
    d.rectangle([x0 + dx, y0 + dy, x1 + dx, y1 + dy], fill=color)


def px(d, pts, color, dx=0, dy=0):
    for x, y in pts:
        d.point((x + dx, y + dy), fill=color)


def draw(state):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    body_color = ORANGE_ANGRY if state == "pout" else ORANGE
    body_dy = 1 if state == "sleep" else 0
    # 手臂：每只手是一串连在身体上的小方块（举手时斜着一节一节往上，不会悬空）
    arm_l = [ARM_L]
    arm_r = [ARM_R]
    legs = list(LEGS)
    up_l = [(3, 15, 5, 18), (1, 11, 3, 14)]            # 左手举高
    up_r = [(30, 15, 32, 18), (32, 11, 34, 14)]        # 右手举高
    mid_l = [(2, 16, 5, 19)]                           # 手稍微抬起
    mid_r = [(30, 16, 33, 19)]
    if state == "happy":
        arm_l, arm_r = mid_l, mid_r
    elif state == "cheer":
        arm_l, arm_r = up_l, up_r
    elif state == "wave":
        arm_r = up_r
    elif state == "drag":
        arm_l, arm_r = up_l, up_r
        legs = [(7, 27, 8, 31), (10, 27, 11, 31), (23, 27, 24, 31), (27, 27, 28, 31)]
    elif state == "worried":
        arm_l, arm_r = [(2, 21, 5, 24)], [(30, 21, 33, 24)]
    elif state == "laugh":
        arm_l, arm_r = mid_l, mid_r
    elif state == "tease":
        arm_r = [(30, 16, 33, 19), (31, 12, 34, 15)]       # 一只手举到“嘴边”
    elif state == "yawn":
        arm_l, arm_r = up_l, up_r
    elif state == "think":
        arm_r = [(30, 16, 33, 19)]

    for l in legs:
        rect(d, l, ORANGE, dy=body_dy)
    rect(d, BODY, body_color, dy=body_dy)
    for box in arm_l + arm_r:
        rect(d, box, ORANGE, dy=body_dy)

    # 眼睛
    if state in ("blink", "sleep"):
        rect(d, (9, 16, 12, 16), EYE, dy=body_dy)
        rect(d, (23, 16, 26, 16), EYE, dy=body_dy)
    elif state in ("happy", "cheer"):
        for cx in (10, 24):                       # ^ ^
            px(d, [(cx, 15), (cx + 1, 15), (cx - 1, 16), (cx + 2, 16)], EYE)
    elif state == "pout":
        px(d, [(9, 14), (10, 15), (11, 16), (12, 16), (10, 14), (11, 15)], EYE)
        px(d, [(26, 14), (25, 15), (24, 16), (23, 16), (25, 14), (24, 15)], EYE)
    elif state == "worried":
        rect(d, EYE_L, EYE, dy=1)
        rect(d, EYE_R, EYE, dy=1)
        px(d, [(9, 13), (10, 12), (11, 12)], EYE)           # 八字眉
        px(d, [(26, 13), (25, 12), (24, 12)], EYE)
        rect(d, (28, 11, 29, 13), DROP)                     # 汗滴
        px(d, [(28, 14)], DROP)
    elif state == "working":
        rect(d, EYE_L, EYE, dy=1)                           # 低头看书
        rect(d, EYE_R, EYE, dy=1)
    elif state == "laugh":
        for cx in (10, 24):                                 # 大笑：^ ^，眼睛更弯更粗
            px(d, [(cx - 1, 16), (cx, 15), (cx + 1, 15), (cx + 2, 16), (cx, 16), (cx + 1, 16)], EYE)
    elif state == "shy":
        rect(d, (9, 16, 12, 16), EYE)                       # 害羞：眯眼 + 腮红
        rect(d, (23, 16, 26, 16), EYE)
        rect(d, (7, 19, 10, 20), BLUSH)
        rect(d, (25, 19, 28, 20), BLUSH)
    elif state == "tease":
        rect(d, (9, 16, 12, 16), EYE)                       # 坏笑：左眼眯、右眼眨
        px(d, [(24, 15), (25, 15), (23, 16), (26, 16)], EYE)
    elif state == "think":
        rect(d, (10, 12, 11, 15), EYE)                      # 看向右上方
        rect(d, (24, 12, 25, 15), EYE)
        px(d, [(31, 3), (32, 2), (33, 3), (33, 4), (32, 5), (32, 6), (32, 8)], QMARK)   # ？
    elif state == "yawn":
        rect(d, (9, 16, 12, 16), EYE)
        rect(d, (23, 16, 26, 16), EYE)
        rect(d, (16, 20, 19, 23), (96, 52, 40, 255))        # 张大的嘴
    elif state == "drag":
        rect(d, (9, 13, 11, 17), EYE)
        rect(d, (24, 13, 26, 17), EYE)
    else:
        rect(d, EYE_L, EYE)
        rect(d, EYE_R, EYE)

    if state == "working":                                  # 抱着一本小书
        rect(d, (11, 20, 24, 26), BOOK)
        rect(d, (11, 20, 24, 20), PAGE)
        rect(d, (17, 21, 18, 26), (84, 52, 38, 255))
    return im.resize((W * SCALE, H * SCALE), Image.NEAREST)


def main():
    os.makedirs(OUT, exist_ok=True)
    states = {"sit": "sit", "blink": "blink", "happy": "happy", "cheer": "cheer", "wave": "wave",
              "pout": "pout", "worried": "worried", "working": "working", "sleep": "sleep", "drag": "drag",
              "shy": "shy", "tease": "tease", "laugh": "laugh", "think": "think", "yawn": "yawn"}
    for name, st in states.items():
        draw(st).save(os.path.join(OUT, name + ".png"))
    meta = os.path.join(OUT, "skin.json")
    if not os.path.exists(meta):
        with open(meta, "w", encoding="utf-8") as f:
            json.dump({"name": "像素机器人", "tagline": "安静 · 冷幽默", "persona": PERSONA,
                       "height": 118, "edge": 1.0, "head": 0.3, "pixel": True},
                      f, ensure_ascii=False, indent=2)
    print("已生成", len(states), "张到", OUT)


if __name__ == "__main__":
    main()
