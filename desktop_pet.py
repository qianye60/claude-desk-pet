# -*- coding: utf-8 -*-
"""
Claude Desktop 桌宠
- 自动找到 Claude Desktop 窗口：上方放得下就站在窗口上边缘，放不下（贴顶/最大化）就坐窗口右下角
- 立绘是静态图，用程序做出“活”的感觉：呼吸、摇摆、悬停倾斜、点击压扁弹回、拖动钟摆、落地压扁
- 多套形态（skins/ 文件夹）可在右键菜单或状态卡片里切换
- 点击弹出额度卡片，右键菜单里切换形态、做动作
- Claude 窗口最小化/关闭时会掉到任务栏上，窗口回来后自己爬回去；很久不理它会睡着
依赖：pip install PySide6 pillow
"""
import sys
import os
import json
import math
import time
import random
import ctypes

from PIL import Image
from PySide6.QtCore import Qt, QTimer, QPoint, QRect, QRectF, QPointF
from PySide6.QtGui import (QImage, QPixmap, QPainter, QColor, QFont, QFontMetrics, QPainterPath,
                           QPen, QGuiApplication, QAction, QIcon, QPolygonF,
                           QTransform, QCursor)
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon

import skins
import usage_info
import lines
from lines import LINES, greeting
import ui
import ui_menu
import snoop
from training import Training, POOLS, ACTIONS as TRAIN_ACTIONS
from ai_brain import AiBrain

IS_WIN = sys.platform == "win32"

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_CONFIG = {
    "form": "",                      # 当前形态（右键菜单里切换后自动记住）
    "perch_position": 0.35,          # 坐在窗口上边的位置（0=最左，1=最右）
    "always_on_top": False,          # true=永远在最上层；false=只比Claude窗口高一层，被别的窗口挡住时也会被挡住
    "quiet": False,                  # 安静模式：不主动说话
    "chat_interval_seconds": [45, 100],
    "sleep_after_seconds": 180,
    "claude_process_names": ["claude.exe"],
    "follow_claude": True,           # Claude 关掉时桌宠也跟着退出（开机哨兵也看这一项）
    "click_opens_panel": True,       # 点击桌宠弹出状态卡片
    "work_with_claude": True,        # 你在 Claude 窗口里打字时，她会拿出本子陪你“工作”
    "usage_file": "",                # 额度记录文件路径，留空自动查找
    "accurate_usage": False,         # true=用官方接口查精确额度（见 usage_api.py）
    "theme": "auto",                 # 界面主题：auto 跟随系统 / light / dark
    "ai_enabled": True,              # 通过本机的 Claude Code 命令行让她生成台词、陪你聊天
    "ai_model": "claude-haiku-5-5",  # AI 用的模型：Haiku 5.5 又快又省；想换就改成 sonnet / opus 等
    "snoop_enabled": True,           # 允许“翻翻我的文件夹”（只看文件名，第一次会让你确认）
    "snoop_consent": False,          # 你确认过之后会自动变成 true
    "snoop_folders": [],             # 留空 = 桌面、文档、视频
}

cw = None
if IS_WIN:
    import claude_win as cw


# ---------------------------------------------------------------- 配置 / 统计
def load_config():
    path = os.path.join(BASE_DIR, "config.json")
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                cfg.update(json.load(f))
        except Exception as e:
            print("config.json 读取失败，使用默认设置：", e)
    else:
        save_config(cfg)
    return cfg


def save_config(cfg):
    try:
        with open(os.path.join(BASE_DIR, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print("config.json 保存失败：", e)


def pil_to_pixmap(im, dpr):
    im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    qimg = QImage(data, im.width, im.height, im.width * 4, QImage.Format.Format_RGBA8888).copy()
    pm = QPixmap.fromImage(qimg)
    pm.setDevicePixelRatio(dpr)
    return pm


# ---------------------------------------------------------------- 桌宠窗口
class Pet(QWidget):
    BUBBLE_W = 200
    PAD_X = 26              # 角色左右留的余量（摇摆、倾斜时不被裁掉）
    TOP_PAD = 44            # 角色上方留的余量（蹦起、拉伸时不被裁掉）
    BOT_PAD = 8
    DOCK_OVERHANG = 0.4     # 右下角模式下最多有多少比例的身体伸到窗口右边框外
    DOCK_MARGIN = 4         # 右下角模式下脚底离窗口下边缘的距离

    def __init__(self, cfg, forms, form, dpr):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                 | Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        if not IS_WIN or cfg.get("always_on_top"):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Claude Pet")

        self.cfg = cfg
        self.dpr = dpr
        self.forms = forms
        self.form_cache = {form.id: form}
        self.finder = cw.ClaudeFinder(cfg["claude_process_names"]) if IS_WIN else None
        self.claude = None          # (hwnd, L, T, R, B) 逻辑坐标
        self.mode = "free"          # perch / free / fall / drag
        self.side = "left"          # 气泡在角色哪一边
        self.ax, self.ay = 0.0, 0.0  # 锚点：角色"坐"的那个点的全局坐标
        self.vy = 0.0
        self.perch_frac = float(cfg.get("perch_position", 0.35))
        self.lost = False
        self.user_free = False
        self.fall_by_user = False
        self.quiet = bool(cfg.get("quiet", False))
        self.z_state = None
        self.next_z = 0.0
        self.docked = False         # 窗口上方没空间，改坐在窗口右下角

        now = time.monotonic()
        self.say_text, self.say_until, self.last_say = "", 0.0, 0.0
        self.activity = None        # (状态名, 结束时刻)：挥手/欢呼/鼓脸/担心/工作/开心...
        self.blink_until, self.next_blink = 0.0, now + 2.0
        self.next_chat = now + random.uniform(*cfg["chat_interval_seconds"])
        self.next_ambient = now + random.uniform(20, 45)
        self.last_interact = now
        self.sleeping = False
        self.next_snore = 0.0
        self.prev_claude_fg = False
        self.work_until = 0.0
        self.click_times = []
        self.last_card_toggle = 0.0
        self.press_g = None
        self.press_win = None
        self.dragging = False
        self.seen_claude = False
        self.miss_count = 0
        self.next_exist_check = 0.0
        self.leaving = False

        # 动画状态
        self.q, self.qv, self.qt = 0.0, 0.0, 0.0      # 压扁(+)/拉伸(-)弹簧：位置、速度、目标
        self.hy, self.hv = 0.0, 0.0                    # 蹦起的高度/速度
        self.tilt = 0.0                                # 悬停时头朝鼠标倾斜
        self.pend, self.pendv = 0.0, 0.0               # 拖动钟摆角度/角速度
        self.drag_vx = 0.0
        self.last_drag = None
        self.hover_since = None
        self.last_hover_say = 0.0
        self.cur_state, self.cur_idx = "sit", 0
        self.next_variant = 0.0
        self.last_tick = now
        self.paint_key = None
        self.tr = (0.0, 1.0, 1.0)                      # 当前绘制变换：角度、sx、sy
        self.pivot_top = False

        # 额度 / 统计
        self.usage_reader = usage_info.UsageReader(cfg.get("usage_file") or None,
                                                   use_api=bool(cfg.get("accurate_usage", False)))
        self.usage = self.usage_reader.read()
        self.next_usage = now + 20
        self.last_five = self.usage.five
        self.quota_warned = False

        # 调教 / AI / 聊天
        self.train = Training(BASE_DIR)
        self.ai = AiBrain(BASE_DIR, cfg.get("ai_model", "claude-haiku-5-5"), bool(cfg.get("ai_enabled", True)))
        self.next_ai_check = now + 45
        self.last_line = None            # (最近一句自言自语, 说的时刻)，用来“别再说这句”
        self.thinking_until = 0.0
        self.next_snoop_check = now + 120
        self.last_snoop = -1e9
        self.snoop_day, self.snoop_count = "", 0
        self.started = now
        self.popups = []

        self.set_form(form, keep_pos=False)
        self.thumb_cache = {}
        self.menu = None
        ui_dir = os.path.join(BASE_DIR, "ui")
        self.badge = ui.load_badge(ui_dir, os.path.join(BASE_DIR, "skins", "pixel", "sit.png"))
        self.card = ui.InfoCard(ui_dir)
        self.card.set_portrait(self.pix["sit"][0])

        self._build_tray()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    # ---------- 形态
    def set_form(self, form, keep_pos=True):
        self.form = form
        self.pix = {s: [pil_to_pixmap(im, self.dpr) for im in ims] for s, ims in form.states.items()}
        self.char_w, self.char_h = form.char_w, form.char_h
        self.edge_y, self.head_y = form.edge_y, form.head_y
        self.setFixedSize(int(self.BUBBLE_W + self.char_w + 2 * self.PAD_X),
                          int(self.TOP_PAD + self.char_h + self.BOT_PAD))
        self.cur_state, self.cur_idx = "sit", 0
        self.paint_key = None
        self.cfg["form"] = form.id
        if hasattr(self, "ai"):
            self.ai.set_persona(form.persona, form.id)       # 切换形态，AI 的人格也跟着换
        if keep_pos and self.ax:
            self.move_anchor(self.ax, self.ay)

    def switch_form(self, fid):
        if fid == self.form.id:
            return
        info = next((f for f in self.forms if f[0] == fid), None)
        if not info:
            return
        try:
            form = self.form_cache.get(fid) or skins.load(info[0], info[1], info[2], self.cfg, self.dpr)
        except Exception as e:
            log_error(e)
            self.say("换装失败了…看看 pet.log")
            return
        self.form_cache[fid] = form
        self.set_form(form)
        save_config(self.cfg)
        self.card.set_portrait(self.pix["sit"][0])
        self.say(f"换成「{form.name}」啦～")
        self.act("cheer", 1.6)
        self.kick(0.16)

    # ---------- 坐标
    def char_x(self):
        return self.BUBBLE_W + self.PAD_X if self.side == "left" else self.PAD_X

    def anchor_x(self):
        return self.char_x() + self.char_w / 2

    def edge_win(self):
        return self.TOP_PAD + self.edge_y

    @staticmethod
    def screen_for(x, y):
        s = QGuiApplication.screenAt(QPoint(int(x), int(y)))
        if s:
            return s
        best, dist = None, None
        for sc in QGuiApplication.screens():
            g = sc.geometry()
            d = 0 if g.left() <= x <= g.right() else min(abs(x - g.left()), abs(x - g.right()))
            if dist is None or d < dist:
                best, dist = sc, d
        return best or QGuiApplication.primaryScreen()

    @staticmethod
    def to_logical(l, t, r, b):
        """Win32 物理像素 -> Qt 逻辑坐标"""
        cx, cy = (l + r) / 2, (t + b) / 2
        target = None
        for s in QGuiApplication.screens():
            g, d = s.geometry(), s.devicePixelRatio()
            if g.x() <= cx < g.x() + g.width() * d and g.y() <= cy < g.y() + g.height() * d:
                target = s
                break
        target = target or QGuiApplication.primaryScreen()
        g, d = target.geometry(), target.devicePixelRatio()

        def conv(px, py):
            return g.x() + (px - g.x()) / d, g.y() + (py - g.y()) / d

        L, T = conv(l, t)
        R, B = conv(r, b)
        return L, T, R, B

    def floor_y(self, x):
        return self.screen_for(x, self.ay).availableGeometry().bottom() + 1

    def move_anchor(self, gx, gy):
        ag = self.screen_for(gx, gy).availableGeometry()
        side = "left" if gx - self.char_w / 2 - self.BUBBLE_W >= ag.left() else "right"
        if side != self.side:
            self.side = side
            self.paint_key = None
        x = int(round(gx - self.anchor_x()))
        y = int(round(gy - self.edge_win()))
        if x != self.x() or y != self.y():
            self.move(x, y)
        self.ax, self.ay = gx, gy

    # ---------- 启动 / 退出
    def start(self):
        self.show()
        c = self._read_claude()
        if c:
            self.claude = c
            self.mode = "perch"
            self._follow()
        else:
            self._go_taskbar(user=False)
            self.lost = True
        self.say(greeting())
        self.act("wave", 2.4)
        self.last_tick = time.monotonic()
        self.timer.start(33)

    def shutdown(self):
        self.card.hide()

    # ---------- 主循环
    def _read_claude(self):
        if not self.finder:
            return None
        r = self.finder.get()
        if not r:
            return None
        hwnd, (l, t, rr, b) = r
        return (hwnd,) + self.to_logical(l, t, rr, b)

    def tick(self):
        now = time.monotonic()
        dt = min(0.05, max(0.001, now - self.last_tick))
        self.last_tick = now
        try:
            self._tick(now, dt)
        except Exception as e:      # 一帧出错不要让整个桌宠停掉
            log_error(e)

    def _tick(self, now, dt):
        self.claude = self._read_claude()
        c = self.claude

        if self.mode == "perch":
            if not c:
                self.lost = True
                self.say(random.choice(LINES["lost"]))
                self.act("worried", 3.0)
                self._start_fall(by_user=False)
            else:
                self._follow()
        elif self.mode == "free":
            if c and self.lost and not self.user_free:
                self.lost = False
                self._perch_at(c[1] + self.perch_frac * (c[3] - c[1]))
                self.say(random.choice(LINES["found"]))
                self.act("cheer", 1.6)
                self.hop(240)
            else:
                ag = self.screen_for(self.ax, self.ay).availableGeometry()
                gx = min(max(self.ax, ag.left() + self.char_w / 2), ag.right() - self.char_w / 2)
                self.move_anchor(gx, self.floor_y(gx))
        elif self.mode == "fall":
            self._fall_step()

        self._check_follow(now)
        self._update_zorder(now)
        self._behaviour(now)
        self._animate(now, dt)
        if self.card.isVisible():
            self._card_tick(now)

    def _check_follow(self, now):
        """Claude 彻底关掉（最小化不算）后，桌宠道别退出"""
        if not self.finder or self.leaving or now < self.next_exist_check:
            return
        self.next_exist_check = now + 3.0
        if self.finder.exists():
            self.seen_claude = True
            self.miss_count = 0
            return
        self.miss_count += 1
        if self.cfg.get("follow_claude", True) and self.seen_claude and self.miss_count >= 2:
            self.leaving = True
            self.sleeping = False
            self.say(random.choice(LINES["bye"]), 3)
            self.act("wave", 2.8)
            QTimer.singleShot(2800, QApplication.quit)

    def _follow(self):
        _, L, T, R, B = self.claude
        half = self.char_w / 2
        scr = self.screen_for((L + R) / 2, T + 10)
        sg, ag = scr.geometry(), scr.availableGeometry()
        # 窗口上方放得下整个角色就站在上边缘；放不下（窗口贴顶/最大化）就改坐右下角。
        # 带一点滞回，避免拖动窗口时在两种位置之间来回跳
        room = T - self.edge_y - sg.top()
        if self.docked:
            self.docked = room < 24
        else:
            self.docked = room < 0
        if not self.docked:
            gx = L + self.perch_frac * (R - L)
            if R - L > self.char_w:
                gx = min(max(gx, L + half), R - half)
            else:
                gx = (L + R) / 2
            self.move_anchor(gx, T)
        else:
            # 右下角输入框右边的空位：窗口右边外面还有屏幕空间时，让角色骑在右边框上，少挡内容
            over = max(0.0, min(self.char_w * self.DOCK_OVERHANG, sg.right() + 1 - R))
            gx = max(R - half + over, L + half)
            gy = min(B - self.DOCK_MARGIN, ag.bottom() + 1)
            self.move_anchor(gx, gy)

    def _perch_at(self, gx):
        _, L, T, R, B = self.claude
        self.perch_frac = min(max((gx - L) / max(1, R - L), 0.0), 1.0)
        self.mode = "perch"
        self.user_free = False
        self.lost = False
        self._follow()

    def _start_fall(self, by_user):
        self.mode = "fall"
        self.vy = 0.0
        self.fall_by_user = by_user

    def _fall_step(self):
        self.vy = min(self.vy + 1.6, 40.0)
        ny = self.ay + self.vy
        c = self.claude
        if c and not self.docked and c[1] + 10 <= self.ax <= c[3] - 10 and self.ay <= c[2] <= ny:
            self._perch_at(self.ax)
            self.say(random.choice(LINES["back"]))
            self.act("happy", 0.9)
            self.kick(0.14)
            return
        floor = self.floor_y(self.ax)
        if ny >= floor:
            self.mode = "free"
            self.user_free = self.fall_by_user
            self.move_anchor(self.ax, floor)
            self.kick(0.16)                      # 落地压扁
            if self.fall_by_user:
                self.say(random.choice(LINES["land"]))
        else:
            self.move_anchor(self.ax, ny)

    def _go_taskbar(self, user=True):
        scr = self.screen_for(self.ax, self.ay) if self.ax else QGuiApplication.primaryScreen()
        ag = scr.availableGeometry()
        gx = ag.right() - self.char_w / 2 - 40
        self.mode = "free"
        self.user_free = user
        self.ay = ag.bottom()
        self.move_anchor(gx, ag.bottom() + 1)

    def _update_zorder(self, now):
        if not IS_WIN or self.cfg.get("always_on_top") or now < self.next_z:
            return
        self.next_z = now + 0.1
        me = int(self.winId())
        if self.mode == "perch" and self.claude:
            if self.z_state != "normal":
                cw.set_topmost(me, False)
                self.z_state = "normal"
            cw.place_just_above(me, self.claude[0])
        elif self.z_state != "top":
            cw.set_topmost(me, True)
            self.z_state = "top"

    # ---------- 行为
    def say(self, text, dur=None, track=False):
        """说话（气泡）。track=True 的是自言自语/AI 台词，可以在菜单里对它“别再说”"""
        now = time.monotonic()
        if len(text) > 80:
            text = text[:79] + "…"
        self.say_text = text
        self.say_until = now + (dur or max(2.5, len(text) * 0.22 + 1.5))
        self.last_say = now
        if track:
            self.last_line = (text, now)

    def last_spoken(self):
        """90 秒内说的最后一句自言自语，没有就是 None"""
        if self.last_line and time.monotonic() - self.last_line[1] < 90:
            return self.last_line[0]
        return None

    def act(self, state, dur=1.5):
        """做一个动作/表情：state 是 wave/cheer/pout/worried/working/happy"""
        self.activity = (state, time.monotonic() + dur)
        if state in ("happy", "cheer"):
            self.hop(230)

    def kick(self, amount):
        """压扁一下再弹回（弹簧）"""
        self.q, self.qv = amount, 0.0

    def hop(self, v=260):
        if self.mode in ("perch", "free") and self.hy <= 0:
            self.hv = v

    def stretch(self):
        self.qt = -0.07
        self.say(random.choice(LINES["stretch"]))
        QTimer.singleShot(900, lambda: setattr(self, "qt", 0.0))

    def _behaviour(self, now):
        settled = self.mode in ("perch", "free")
        # 眨眼
        if now > self.next_blink:
            self.blink_until = now + 0.14
            self.next_blink = now + random.uniform(2.0, 6.0)
        # 犯困
        if settled and not self.sleeping and now - self.last_interact > self.cfg["sleep_after_seconds"]:
            self.sleeping = True
            self.say("Zz…", 3)
            self.next_snore = now + 12
        if self.sleeping and now > self.next_snore:
            if not self.quiet:
                self.say("Zzz…", 3)
            self.next_snore = now + random.uniform(10, 18)
        # 自言自语（频率受“话多程度”调教影响，调到 0 就不主动说）
        talk = self.train.talk
        if settled and not self.sleeping and not self.quiet and talk > 0.05 and now > self.next_chat:
            if now > self.say_until:
                line = lines.idle_line(self.train, self.ai)
                if line:
                    self.say(line, track=True)
                    self.run_act(self.ai.pending_act)
                    self.ai.pending_act = "none"
            self.next_chat = now + random.uniform(*self.cfg["chat_interval_seconds"]) / max(0.25, talk)
        # 随机小动作：让她闲着也不呆（频率受“活泼程度”影响）
        lively = self.train.lively
        if settled and not self.sleeping and not self.activity and lively > 0.05 and now > self.next_ambient:
            self._ambient()
            self.next_ambient = now + random.uniform(25, 70) / max(0.25, lively)
        # AI：台词快用完或太久没更新时，后台批量生成一批
        if now > self.next_ai_check:
            self.next_ai_check = now + 60
            self._ai_maintain()
        self._ai_results(now)
        self._maybe_snoop(now)
        # Claude 窗口相关
        if IS_WIN and self.claude:
            is_fg = cw.foreground() == int(self.claude[0])
            if (is_fg and not self.prev_claude_fg and not self.sleeping and not self.quiet
                    and now - self.last_say > 25 and random.random() < 0.3):
                self.say(random.choice(LINES["claude_focus"]))
            self.prev_claude_fg = is_fg
            if self.cfg.get("work_with_claude", True) and settled and is_fg and cw.idle_seconds() < 6:
                self.work_until = now + 5
                if self.sleeping:
                    self.sleeping = False
                    self.last_interact = now
        # 额度监测
        if now > self.next_usage:
            self.next_usage = now + 20
            self.usage = self.usage_reader.read()
            self._watch_quota()
        # 悬停
        self._hover(now)

    def _ambient(self):
        names = ["wave", "cheer", "working", "stretch", "hop", "worried"]
        base = [3, 2, 3, 2, 2, 0.5]
        weights = [b * self.train.action_weight(n) for n, b in zip(names, base)]
        if sum(weights) <= 0:
            return                                  # 动作全被你调教关了
        choice = random.choices(names, weights=weights)[0]
        if choice == "stretch":
            self.stretch()
        elif choice == "hop":
            self.hop(220)
            self.kick(0.08)
        elif choice == "working":
            self.act("working", random.uniform(8, 14))
        else:
            self.act(choice, 2.0)

    def _watch_quota(self):
        five = self.usage.five
        if five is None:
            return
        if self.last_five is not None and five <= self.last_five - 5 and not self.quiet:
            self.say(random.choice(LINES["quota_reset"]))
            self.act("cheer", 2.0)
        if five >= 85 and not self.quota_warned:
            self.quota_warned = True
            if not self.quiet:
                self.say(random.choice(LINES["quota_low"]))
            self.act("worried", 4.0)
        elif five < 70:
            self.quota_warned = False
        self.last_five = five

    # ---------- AI：台词、聊天、翻文件夹
    def ai_context(self):
        t = time.localtime()
        part = ("凌晨" if t.tm_hour < 5 else "早上" if t.tm_hour < 11 else "中午" if t.tm_hour < 14
                else "下午" if t.tm_hour < 18 else "晚上")
        week = "一二三四五六日"[t.tm_wday]
        s = f"现在是星期{week}{part} {time.strftime('%H:%M')}，主人正在用 Claude"
        if self.usage.five is not None:
            s += f"，5 小时额度已用 {self.usage.five:.0f}%"
        return s

    def _ai_maintain(self):
        ai = self.ai
        if not ai.available or ai.busy or self.quiet or self.train.pool_weight("ai") <= 0:
            return
        stale = time.time() - ai.updated > 6 * 3600
        if len(ai.lines) < 4 or stale:
            ai.refill(self.ai_context(), liked=self.train.d["liked"], banned=self.train.d["banned"])

    def _ai_results(self, now):
        for tag, text, act in self.ai.pop_results():
            self.thinking_until = 0.0
            if tag == "chat" and text:
                self.say(text, dur=max(5.0, len(text) * 0.3 + 2.5))
                self.run_act(act if act != "none" else "happy")
            elif tag == "snoop" and text:
                self.say(text, dur=max(8.0, len(text) * 0.3 + 3.0))
                self.run_act(act if act != "none" else "happy")
            elif tag in ("chat_fail", "snoop_fail"):
                self.say("唔…脑子没转过来，等会儿再试试？" if self.ai.available
                         else "我还没接上 AI：需要先装好并登录 Claude Code 命令行～", dur=4.5)

    def _beside_x(self, width):
        """弹窗放在她身体旁边的中心 x（优先左边，左边没位置放右边），这样不会盖住她的脸"""
        ag = self.screen_for(self.ax, self.ay).availableGeometry()
        left = self.ax - self.char_w / 2 - width / 2 + 10
        if left - width / 2 >= ag.left():
            return left
        return self.ax + self.char_w / 2 + width / 2 - 10

    def open_chat(self):
        if not self.ai.available:
            self.say("要先装好并登录 Claude Code 命令行，我才能陪你聊～", dur=4.5)
            return
        box = ui_menu.ChatBox()
        box.sent.connect(self.send_chat)
        self.popups.append(box)
        gx = self._beside_x(300)
        box.popup_near(gx, self.ay - self.char_h * 0.28)

    def send_chat(self, text):
        self.last_interact = time.monotonic()
        self.sleeping = False
        if self.ai.chat(text, self.ai_context()):
            self.thinking_until = time.monotonic() + 120
            self.say("嗯…让我想想", dur=3.0)

    def open_train(self):
        card = ui_menu.TrainCard(self.train, POOLS, self.last_spoken(),
                                 snoop_on=bool(self.cfg.get("snoop_consent", False)))
        card.changed.connect(self.on_train)
        self.popups.append(card)
        card.popup_near(self._beside_x(308), self.ay - 4)

    def on_train(self, key, val):
        t = self.train
        if key == "talk":
            t.set_talk(val)
        elif key == "lively":
            t.set_lively(val)
        elif key == "snoop":
            self.cfg["snoop_consent"] = bool(val)
            save_config(self.cfg)
            self.say("好，我会偶尔翻翻你的文件夹，只看文件名哦～" if val else "好，不翻你的文件夹了")
        elif key.startswith("pool:"):
            t.toggle_pool(key[5:], bool(val))
        elif key.startswith("action:"):
            t.toggle_action(key[7:], bool(val))
        elif key == "like":
            t.like(val)
            self.say("好耶，这句以后多说～", track=False)
            self.act("happy", 1.2)
        elif key == "ban":
            t.ban(val)
            self.say("好，这句再也不说了", track=False)
            self.act("worried", 1.5)

    def ban_last(self):
        line = self.last_spoken()
        if line:
            self.train.ban(line)
            self.last_line = None
            self.say("好，这句再也不说了", track=False)
            self.act("worried", 1.5)

    def _maybe_snoop(self, now):
        """自主翻文件夹：只有你在调教里打开了开关才会发生，并且要满足条件：
        刚启动 15 分钟后、距离上次 ≥ 3 小时、你最近 5 分钟内有操作（人在电脑前）、她不在睡觉/安静、
        每天最多 3 次，再加一点随机，所以不会很规律。"""
        if now < self.next_snoop_check:
            return
        self.next_snoop_check = now + 60
        if not (self.cfg.get("snoop_enabled", True) and self.cfg.get("snoop_consent", False)):
            return
        today = time.strftime("%Y-%m-%d")
        if self.snoop_day != today:
            self.snoop_day, self.snoop_count = today, 0
        if (self.snoop_count >= 3 or now - self.started < 900 or now - self.last_snoop < 3 * 3600
                or self.sleeping or self.quiet or self.mode not in ("perch", "free") or self.ai.busy
                or not self.ai.available or self.card.isVisible()):
            return
        if IS_WIN and cw.idle_seconds() > 300:
            return
        if random.random() < 0.12:
            self.run_snoop()

    def run_snoop(self):
        now = time.monotonic()
        self.last_snoop = now
        self.snoop_count += 1
        folders = self.cfg.get("snoop_folders") or snoop.default_folders()
        self.say("嘿嘿，我看看你都存了些啥…", dur=3)
        self.thinking_until = now + 180
        import threading

        def run():
            listing, total = snoop.scan(folders)
            if not total:
                self.ai.results.append(("snoop", "翻了一圈，什么都没翻到，你也太干净了吧", "happy"))
                return
            self.ai.snoop(listing, total, self.ai_context())
        threading.Thread(target=run, daemon=True).start()

    def _char_rect_global(self):
        x0 = self.x() + self.char_x()
        y0 = self.y() + self.TOP_PAD
        return QRectF(x0 + self.char_w * 0.12, y0, self.char_w * 0.76, self.char_h)

    def _hover(self, now):
        pos = QCursor.pos()
        r = self._char_rect_global()
        over = (self.mode in ("perch", "free") and not self.dragging
                and r.contains(QPointF(pos.x(), pos.y())))
        if over:
            cx = r.center().x()
            self._tilt_target = max(-1.0, min(1.0, (pos.x() - cx) / (r.width() / 2))) * 3.0
            if self.hover_since is None:
                self.hover_since = now
            elif (now - self.hover_since > 1.2 and now - self.last_hover_say > 20 and not self.quiet
                  and not self.sleeping and now > self.say_until and not self.card.isVisible()):
                self.last_hover_say = now
                self.say(random.choice(LINES["hover"]), 2.0)
        else:
            self._tilt_target = 0.0
            self.hover_since = None

    _tilt_target = 0.0

    # ---------- 动画
    def _wanted_state(self, now):
        if self.mode in ("drag", "fall"):
            return "drag"
        if self.activity and now < self.activity[1]:
            return self.activity[0]
        if now < self.thinking_until:
            return "working"            # 等 AI 回话时她拿出本子“想一想”
        if self.sleeping:
            return "sleep"
        if now < self.work_until:
            return "working"
        return "blink" if now < self.blink_until else "sit"

    def _animate(self, now, dt):
        if self.activity and now >= self.activity[1]:
            self.activity = None
        want = self._wanted_state(now)
        state = self.form.resolve(want)
        n = len(self.pix[state])
        if state != self.cur_state:
            self.cur_state = state
            self.cur_idx = random.randrange(n) if n > 1 and state not in ("sit", "blink") else 0
            self.next_variant = now + 5.0
        elif n > 1 and want == "working" and now > self.next_variant:
            self.cur_idx = (self.cur_idx + 1) % n      # 工作姿势几张图轮着来
            self.next_variant = now + 5.0

        # 物理
        steps = max(1, int(dt / 0.008))
        h = dt / steps
        free = self.mode in ("perch", "free")
        for _ in range(steps):
            # 压扁/拉伸弹簧
            a = -180.0 * (self.q - self.qt) - 11.0 * self.qv
            self.qv += a * h
            self.q += self.qv * h
            # 蹦起
            if self.hy > 0 or self.hv > 0:
                self.hv -= 1500.0 * h
                self.hy += self.hv * h
                if self.hy <= 0:
                    land_v = self.hv
                    self.hy, self.hv = 0.0, 0.0
                    if land_v < -80:
                        self.kick(0.10)
            # 钟摆
            target = 0.0
            if self.mode == "drag":
                target = max(-22.0, min(22.0, self.drag_vx / 45.0))
            pa = -70.0 * (self.pend - target) - 5.0 * self.pendv
            self.pendv += pa * h
            self.pend += self.pendv * h
        if not free:
            self.hy = self.hv = 0.0
        if self.mode == "drag":
            self.drag_vx *= math.exp(-dt * 6.0)        # 鼠标停了，速度自然衰减
        self.tilt += (self._tilt_target - self.tilt) * min(1.0, dt * 8.0)

        # 合成变换：呼吸 + 摇摆 + 悬停倾斜 + 钟摆 + 压扁
        slow = self.sleeping
        breath = math.sin(2 * math.pi * now / (4.5 if slow else 3.0))
        sway = 0.0 if (slow or not free) else math.sin(2 * math.pi * now / 4.3 + 1.3) * 1.0
        angle = sway + self.tilt + self.pend
        sy = (1.0 - self.q) * (1.0 + (0.012 if slow else 0.01) * breath)
        sx = 1.0 + 0.7 * self.q
        self.pivot_top = self.mode == "drag" or abs(self.pend) > 0.4 or abs(self.pendv) > 2.0

        text = self.say_text if now < self.say_until else ""
        if self.card.isVisible():
            text = ""
        key = (self.cur_state, self.cur_idx, text, self.side, round(angle * 20), round(sx * 400),
               round(sy * 400), round(self.hy), self.pivot_top)
        if key != self.paint_key:
            self.paint_key = key
            self.tr = (angle, sx, sy)
            self.bubble_text = text
            self.update()

    bubble_text = ""
    bubble_rect = None

    # ---------- 状态卡片
    def refresh_card(self):
        self.usage = self.usage_reader.read()
        self.card.update_data(self.usage, self.form.name)

    def place_card(self):
        """卡片的位置：坐在窗口右下角时弹在她头顶上方（避开 Claude 的输入框和发送按钮），
        否则放在她左边（实在放不下放右边）"""
        c = self.card
        c.adjustSize()
        w, h = c.width(), c.height()
        sc = self.screen_for(self.ax, self.ay).availableGeometry()
        cx0 = self.x() + self.char_x()
        cx1 = cx0 + self.char_w
        if self.docked and self.mode == "perch":
            x = cx1 - w + 14 + self.char_w * 0.1            # 右边与她对齐
            y = self.y() + self.TOP_PAD - h + 30              # 卡片底边落在她头顶附近
        else:
            x = cx0 - w + 14 + self.char_w * 0.2
            if x < sc.left():
                x = cx1 - 14 - self.char_w * 0.2
            y = self.ay - h + 18
        x = min(max(x, sc.left()), sc.right() - w + 1)
        y = min(max(y, sc.top()), sc.bottom() - h + 1)
        c.move(int(x), int(y))

    def _card_tick(self, now):
        if int(now * 2) != getattr(self, "_card_sec", None):    # 每 0.5 秒刷新一次内容
            self._card_sec = int(now * 2)
            self.refresh_card()
        self.place_card()

    def toggle_card(self):
        if self.card.isVisible():
            self.card.hide()
            return
        self.refresh_card()
        self.place_card()
        self.card.popup()
        self.paint_key = None

    # ---------- 交互
    def on_click(self):
        now = time.monotonic()
        self.last_interact = now
        if self.sleeping:
            self.sleeping = False
            self.say(random.choice(LINES["wake"]))
            self.act("happy", 0.9)
            self.kick(0.12)
            return
        self.click_times = [t for t in self.click_times if now - t < 3] + [now]
        spam = len(self.click_times) >= 5
        if spam:
            self.click_times = []
            self.say(random.choice(LINES["poke"]))
            self.act("pout", 3.0)
            self.kick(0.18)
        else:
            self.say(random.choice(LINES["click"]))
            self.act("happy", 1.0)
            self.kick(0.16)
            if (self.cfg.get("click_opens_panel", True) and now - self.last_card_toggle > 1.2
                    and len(self.click_times) < 3):
                self.last_card_toggle = now
                self.toggle_card()

    def on_drop(self):
        self.last_interact = time.monotonic()
        c = self.claude
        if c and not self.docked and c[1] + 10 <= self.ax <= c[3] - 10 and abs(self.ay - c[2]) < 28:
            self._perch_at(self.ax)
            self._remember_spot()
            self.act("happy", 0.9)
            self.kick(0.14)
        elif c and self.docked and abs(self.ax - (c[3] - self.char_w / 2)) < self.char_w and abs(self.ay - c[4]) < 60:
            self._perch_at(self.ax)
            self.say(random.choice(LINES["back"]))
            self.act("happy", 0.9)
            self.kick(0.14)
        else:
            self._start_fall(by_user=True)

    def _remember_spot(self):
        """你把她放在窗口上边的哪个位置，她就记住，以后都坐那儿"""
        old = float(self.cfg.get("perch_position", 0.35))
        if abs(self.perch_frac - old) > 0.03:
            self.cfg["perch_position"] = round(self.perch_frac, 3)
            save_config(self.cfg)
            self.say("记住啦，以后就坐这儿～")
        else:
            self.say(random.choice(LINES["back"]))

    def menu_perch(self):
        self.sleeping = False
        self.last_interact = time.monotonic()
        if self.claude:
            _, L, T, R, B = self.claude
            self._perch_at(L + float(self.cfg.get("perch_position", 0.35)) * (R - L))
            self.say(random.choice(LINES["back"]))
            self.act("happy", 1.0)
        else:
            self.say(LINES["no_claude"][0])

    def menu_taskbar(self):
        self.sleeping = False
        self.last_interact = time.monotonic()
        self._go_taskbar(user=True)
        self.say("在这儿坐一会儿～")

    def toggle_follow(self, checked):
        self.cfg["follow_claude"] = checked
        save_config(self.cfg)
        try:
            cw.set_autostart(checked, BASE_DIR)
        except Exception as e:
            self.say("设置开机自启失败了…")
            log_error(e)
            return
        if checked:
            self.say("以后打开 Claude 我就会自己出来～")
        else:
            self.say("好，以后要手动叫我啦")

    def toggle_quiet(self, checked):
        self.quiet = checked
        self.cfg["quiet"] = checked
        save_config(self.cfg)
        self.say("那我安静待着～" if checked else "我又可以说话啦！")

    def run_act(self, name):
        """做一个动作。动作只由条件（额度、空闲、拖动…）和 AI 触发，不提供手动按钮"""
        if not name or name == "none":
            return
        if name == "stretch":
            self.stretch()
        elif name == "hop":
            self.hop(260)
            self.kick(0.10)
        elif name == "working":
            self.act("working", 6.0)
        elif name in ("wave", "cheer", "happy", "pout", "worried"):
            self.act(name, 2.4)

    # ---------- 鼠标
    def mousePressEvent(self, e):
        if (e.button() == Qt.MouseButton.LeftButton and self.bubble_text and self.bubble_rect is not None
                and self.bubble_rect.contains(e.position())):
            self.say_until = 0.0            # 点一下气泡就让它消失，免得盖住 Claude 的内容
            self.paint_key = None
            self.press_g = None
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self.press_g = e.globalPosition().toPoint()
            self.press_win = self.pos()
            self.dragging = False

    def mouseMoveEvent(self, e):
        if self.press_g is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        g = e.globalPosition().toPoint()
        d = g - self.press_g
        if not self.dragging and d.manhattanLength() > 5:
            self.dragging = True
            self.mode = "drag"
            self.sleeping = False
            self.last_drag = (time.monotonic(), g.x())
            self.say(random.choice(LINES["drag"]))
            self.card.hide()
        if self.dragging:
            now = time.monotonic()
            if self.last_drag:
                dtm = max(0.004, now - self.last_drag[0])
                inst = (g.x() - self.last_drag[1]) / dtm
                self.drag_vx = 0.6 * self.drag_vx + 0.4 * inst
            self.last_drag = (now, g.x())
            np = self.press_win + d
            self.move(np)
            self.ax = np.x() + self.anchor_x()
            self.ay = np.y() + self.edge_win()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self.press_g is None:
            return
        if self.dragging:
            self.dragging = False
            self.on_drop()
        else:
            self.on_click()
        self.press_g = None

    def thumbs(self):
        """菜单里的形态卡片 [(id, 名字, QPixmap, 标签, 是否缺图)]；御姐没放图时给一个虚线占位"""
        out = []
        for fid, name, folder in self.forms:
            if fid not in self.thumb_cache:
                im = skins.thumbnail(folder, 200) if folder else None
                self.thumb_cache[fid] = pil_to_pixmap(im, 1.0) if im else None
            out.append((fid, name, self.thumb_cache[fid], skins.tagline_of(folder), False))
        if not any(f[0] == "skins/yujie" for f in self.forms):
            out.append(("missing:yujie", "成熟御姐", None, "", True))
        return out

    def contextMenuEvent(self, e):
        state = {"follow": bool(self.cfg.get("follow_claude", True)) and (not IS_WIN or cw.autostart_enabled()),
                 "quiet": self.quiet, "accurate": bool(self.cfg.get("accurate_usage", False))}
        self.card.hide()
        self.menu = ui_menu.PetMenu(self.thumbs(), self.form.id, state, self.badge)
        self.menu.triggered.connect(self.on_menu)
        p = e.globalPos()
        self.menu.popup_at(p.x(), p.y())

    def on_menu(self, key, arg):
        if key == "form":
            if str(arg).startswith("missing:"):
                self.say("御姐形态还没有立绘～把图放进 skins\\yujie 文件夹就能用了，提示词在 docs 里", dur=7)
            else:
                self.switch_form(arg)
        elif key == "card":
            QTimer.singleShot(60, self.toggle_card)
        elif key == "hello":
            self.say(greeting())
            self.act("wave", 2.2)
        elif key == "chat":
            QTimer.singleShot(80, self.open_chat)
        elif key == "train":
            QTimer.singleShot(80, self.open_train)
        elif key == "perch":
            self.menu_perch()
        elif key == "taskbar":
            self.menu_taskbar()
        elif key == "follow":
            self.toggle_follow(bool(arg))
        elif key == "quiet":
            self.toggle_quiet(bool(arg))
        elif key == "accurate":
            self.toggle_accurate(bool(arg))
        elif key == "quit":
            QApplication.quit()

    def toggle_accurate(self, on):
        self.cfg["accurate_usage"] = on
        save_config(self.cfg)
        self.usage_reader = usage_info.UsageReader(self.cfg.get("usage_file") or None, use_api=on)
        self.usage = self.usage_reader.read()
        self.say("好，额度改用官方接口查（读不到会退回本地记录）" if on else "好，额度只看本地记录啦")

    def _build_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if self.badge is not None:
            icon_pm = self.badge
        else:
            pm = self.pix["sit"][0]
            w = pm.width()
            icon_pm = pm.copy(QRect(int(w * 0.15), 0, int(w * 0.7), int(w * 0.7)))
        self.tray = QSystemTrayIcon(QIcon(icon_pm), self)
        self.tray.setToolTip("Claude")
        self.tray_menu = QMenu()
        a = QAction("状态卡片", self.tray_menu)
        a.triggered.connect(self.toggle_card)
        self.tray_menu.addAction(a)
        a = QAction("叫它回来", self.tray_menu)
        a.triggered.connect(self.menu_perch)
        self.tray_menu.addAction(a)
        a = QAction("去任务栏上坐着", self.tray_menu)
        a.triggered.connect(self.menu_taskbar)
        self.tray_menu.addAction(a)
        self.tray_menu.addSeparator()
        a = QAction("退出", self.tray_menu)
        a.triggered.connect(QApplication.quit)
        self.tray_menu.addAction(a)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(lambda r: self.toggle_card()
                                    if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    # ---------- 绘制
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        lst = self.pix[self.cur_state]
        pm = lst[self.cur_idx % len(lst)]
        angle, sx, sy = self.tr
        cx = self.char_x() + self.char_w / 2
        # 平时以脚底为支点；被拎起/刚松手时以头顶为支点，像挂着的钟摆
        py = (self.TOP_PAD - self.hy) if self.pivot_top else (self.edge_win() - self.hy)
        t = QTransform()
        t.translate(cx, py)
        t.rotate(angle)
        t.scale(sx, sy)
        t.translate(-cx, -py)
        p.setTransform(t)
        p.drawPixmap(QPointF(self.char_x(), self.TOP_PAD - self.hy), pm)
        p.resetTransform()
        if self.bubble_text:
            self._draw_bubble(p, self.bubble_text)
        p.end()

    def _draw_bubble(self, p, text):
        font = QFont("Microsoft YaHei UI", 9)
        p.setFont(font)
        fm = QFontMetrics(font)
        maxw = self.BUBBLE_W - 34
        flags = int(Qt.AlignmentFlag.AlignLeft) | int(Qt.TextFlag.TextWordWrap)
        br = fm.boundingRect(QRect(0, 0, maxw, 400), flags, text)
        bw, bh = br.width() + 22, br.height() + 14
        cy = self.TOP_PAD + self.head_y - self.hy * 0.5
        tail = 9
        if self.side == "left":
            bx = self.char_x() + self.char_w * 0.2 - tail - bw
        else:
            bx = self.char_x() + self.char_w * 0.8 + tail
        bx = min(max(bx, 2), self.width() - bw - 2)
        by = min(max(cy - bh / 2, 2), self.height() - bh - 2)
        ty = min(max(cy, by + 10), by + bh - 10)

        path = QPainterPath()
        path.addRoundedRect(QRectF(bx, by, bw, bh), 10, 10)
        tri = QPainterPath()
        if self.side == "left":
            tri.addPolygon(QPolygonF([QPointF(bx + bw - 2, ty - 6), QPointF(bx + bw + tail, ty),
                                      QPointF(bx + bw - 2, ty + 6)]))
        else:
            tri.addPolygon(QPolygonF([QPointF(bx + 2, ty - 6), QPointF(bx - tail, ty),
                                      QPointF(bx + 2, ty + 6)]))
        path = path.united(tri)
        self.bubble_rect = QRectF(bx - tail, by, bw + tail * 2, bh)
        p.setPen(QPen(QColor(217, 119, 87), 1.6))
        p.setBrush(QColor(255, 252, 248, 245))
        p.drawPath(path)
        p.setPen(QColor(72, 50, 40))
        p.drawText(QRect(int(bx + 11), int(by + 7), br.width() + 2, br.height() + 2), flags, text)


def log_error(e):
    import traceback
    try:
        with open(os.path.join(BASE_DIR, "pet.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + repr(e) + "\n")
            f.write(traceback.format_exc() + "\n")
    except OSError:
        pass


def main():
    if IS_WIN and not cw.single_instance(cw.PET_MUTEX):
        return  # 已经有一只在跑了
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    cfg = load_config()
    ui.apply_theme(cfg.get("theme", "auto"))
    lines.load_extra(BASE_DIR)
    dpr = app.primaryScreen().devicePixelRatio()
    forms = skins.discover(BASE_DIR)
    if not forms:
        msg = ("没有找到角色图片。\n\n请先运行 get_skin.py 下载角色立绘，\n"
               "或把立绘放进 skins\\<名字> 文件夹（需要 sit.png 或 idle.png，详见 README）。")
        if IS_WIN:
            ctypes.windll.user32.MessageBoxW(0, msg, "Claude", 0x10)
        else:
            print(msg)
        return
    wanted = cfg.get("form") or forms[0][0]
    info = next((f for f in forms if f[0] == wanted), forms[0])
    form = skins.load(info[0], info[1], info[2], cfg, dpr)
    pet = Pet(cfg, forms, form, dpr)
    pet.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        log_error(e)
        raise
