# -*- coding: utf-8 -*-
"""
桌宠的界面：点击弹出的状态卡片（InfoCard）和右键菜单（PetMenu），共用一套主题。
- 自动跟随 Windows 的浅色/深色（config.json 里 "theme": "auto" | "light" | "dark"）
- 额度用圆环显示；立绘从卡片顶部探出来；形态用缩略图切换
- 可选的美术资源放在程序目录的 ui 文件夹（没有也能正常显示），见 README
"""
import os
import time

from PySide6.QtCore import (Qt, QTimer, QRectF, QPointF, Signal, QPropertyAnimation, QVariantAnimation,
                            QEasingCurve, QSize, QRect)
from PySide6.QtGui import (QColor, QPainter, QPainterPath, QPixmap, QFont, QPen, QLinearGradient,
                           QBrush, QFontMetrics)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
                               QAbstractButton, QSizePolicy)

import usage_info

FONT = "Microsoft YaHei UI"

THEMES = {
    "light": dict(bg="#FCF8F3", bg2="#F3EAE0", ink="#2B211C", sub="#8E7F74", line="#EADFD3",
                  track="#EEE4D9", accent="#D97757", accent2="#F0A27F", hover="#F3E6D8",
                  good="#5FA86F", warn="#E09A4A", bad="#D2514A", shadow=(90, 50, 30)),
    "dark": dict(bg="#272522", bg2="#34312D", ink="#F4EFE8", sub="#A89F95", line="#3D3A35",
                 track="#43403B", accent="#E0805C", accent2="#F0A27F", hover="#3A3733",
                 good="#6FBF80", warn="#E8A858", bad="#E4645C", shadow=(0, 0, 0)),
}
T = dict(THEMES["light"])


def system_is_dark():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except Exception:
        return False


def apply_theme(name="auto"):
    if name not in THEMES:
        name = "dark" if system_is_dark() else "light"
    T.clear()
    T.update(THEMES[name])
    return name


def col(key, alpha=None):
    c = QColor(T[key])
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def level_color(used):
    return T["good"] if used < 60 else T["warn"] if used < 85 else T["bad"]


def pill_qss():
    return f"""
    QPushButton {{ font-family: '{FONT}'; font-size: 12px; color: {T['ink']}; background: {T['bg2']};
                  border: none; border-radius: 14px; padding: 7px 12px; }}
    QPushButton:hover {{ background: {T['hover']}; color: {T['accent']}; }}
    QPushButton:checked {{ background: {T['accent']}; color: white; }}
    """


def paint_card_background(p, w, h, top, radius=18):
    """阴影 + 圆角底板（top 是底板顶边，上面留给探出来的立绘）"""
    sr, sg, sb = T["shadow"]
    body = QRectF(14, top, w - 28, h - top - 18)
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(9):                                  # 手画一层柔和阴影，比 QGraphicsEffect 省
        a = int(16 * (1 - i / 9.0))
        p.setBrush(QColor(sr, sg, sb, a))
        p.drawRoundedRect(body.adjusted(-i, -i + 4, i, i + 4), radius + i, radius + i)
    path = QPainterPath()
    path.addRoundedRect(body, radius, radius)
    p.fillPath(path, col("bg"))
    p.setPen(QPen(col("line"), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(body, radius, radius)
    return body, path


def circle_avatar(pm: QPixmap, size, ring=None):
    """立绘上半部分裁成圆形头像"""
    px = size * 2
    side = int(min(pm.width(), pm.height()) * 0.68)            # 取脸所在的那一块
    crop = pm.copy(int((pm.width() - side) / 2), int(pm.height() * 0.10), side, side).scaled(
        px, px, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(px, px)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(3, 3, px - 6, px - 6)
    p.fillPath(path, col("bg2"))
    p.setClipPath(path)
    p.drawPixmap(0, 0, crop)
    p.setClipping(False)
    if ring:
        p.setPen(QPen(QColor(ring), 5))
        p.drawEllipse(3, 3, px - 6, px - 6)
    p.end()
    out.setDevicePixelRatio(2)
    return out


def load_badge(ui_dir, fallback=None):
    """Claude 的小图标：ui/clawd.png；没有就用像素机器人形态的待机图（fallback）；都没有返回 None。
    会先裁掉四周的透明边，这样按高度缩放时图标不会显得很小。"""
    from PIL import Image
    from PySide6.QtGui import QImage
    for p in (os.path.join(ui_dir or "", "clawd.png"), fallback):
        if p and os.path.exists(p):
            try:
                im = Image.open(p).convert("RGBA")
                box = im.getchannel("A").getbbox()
                if box:
                    im = im.crop(box)
                qimg = QImage(im.tobytes("raw", "RGBA"), im.width, im.height, im.width * 4,
                              QImage.Format.Format_RGBA8888).copy()
                return QPixmap.fromImage(qimg)
            except Exception:
                continue
    return None


def draw_badge(p, pm, x, y, h):
    """把图标按高度 h 画在 (x, y)，返回占用的宽度"""
    if pm is None:
        return 0
    w = pm.width() * h / pm.height()
    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawPixmap(QRectF(x, y, w, h), pm, QRectF(pm.rect()))
    p.restore()
    return w


# ---------------------------------------------------------------- 小部件
class Ring(QWidget):
    """圆环额度表：中间是剩余百分比，下面是名称和重置时间"""

    def __init__(self, title):
        super().__init__()
        self.title = title
        self.used = None
        self.note = ""
        self.shown = 0.0
        self.setFixedSize(132, 146)
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(600)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, v):
        self.shown = float(v)
        self.update()

    def replay(self):
        """重新从 0 播放一遍圆环动画（卡片每次弹出时调用）"""
        if self.used is not None:
            self.anim.stop()
            self.shown = 0.0
            self.anim.setStartValue(0.0)
            self.anim.setEndValue(float(self.used))
            self.anim.start()

    def set(self, used, note):
        self.note = note
        if used != self.used:
            self.anim.stop()
            self.anim.setStartValue(self.shown)
            self.anim.setEndValue(0.0 if used is None else float(used))
            self.used = used
            self.anim.start()
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r, wd = self.width() / 2, 56, 43, 10
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        p.setPen(QPen(col("track"), wd, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawEllipse(rect)
        if self.used is not None:
            c = QColor(level_color(self.used))
            pen = QPen(c, wd, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            span = -int(self.shown * 3.6 * 16)
            if abs(span) < 40 and self.used > 0:
                span = -40
            p.drawArc(rect, 90 * 16, span)
            big = f"{max(0.0, 100.0 - self.used):.0f}%"
            p.setPen(col("ink"))
            f = QFont(FONT, 15)
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(cx - r, cy - 20, 2 * r, 28), Qt.AlignmentFlag.AlignCenter, big)
            p.setPen(col("sub"))
            p.setFont(QFont(FONT, 8))
            p.drawText(QRectF(cx - r, cy + 5, 2 * r, 14), Qt.AlignmentFlag.AlignCenter, "剩余")
        else:
            p.setPen(col("sub"))
            p.setFont(QFont(FONT, 14))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "—")
        p.setPen(col("ink"))
        f = QFont(FONT, 9)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 112, self.width(), 16), Qt.AlignmentFlag.AlignCenter, self.title)
        p.setPen(col("sub"))
        p.setFont(QFont(FONT, 8))
        p.drawText(QRectF(0, 128, self.width(), 14), Qt.AlignmentFlag.AlignCenter, self.note)
        p.end()


class Thumb(QAbstractButton):
    """形态缩略图：圆形头像 + 名字，当前形态有强调色圆环"""

    def __init__(self, fid, name, pm, size=46):
        super().__init__()
        self.fid, self.name, self.size_ = fid, name, size
        self.pm = pm
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(size + 22, size + 28)
        self.hover = False

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col("hover"))
            p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 12, 12)
        s = self.size_
        x = (self.width() - s) / 2
        if self.pm is not None:
            av = circle_avatar(self.pm, s, T["accent"] if self.isChecked() else None)
            p.drawPixmap(QRectF(x, 5, s, s).toRect(), av)
        else:
            p.setBrush(col("bg2"))
            p.setPen(QPen(col("accent"), 2.5) if self.isChecked() else Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(x + 1.5, 6.5, s - 3, s - 3))
        p.setPen(col("accent") if self.isChecked() else col("sub"))
        f = QFont(FONT, 8)
        f.setBold(self.isChecked())
        p.setFont(f)
        p.drawText(QRectF(0, s + 8, self.width(), 16), Qt.AlignmentFlag.AlignCenter,
                   QFontMetrics(f).elidedText(self.name, Qt.TextElideMode.ElideRight, self.width() - 4))
        p.end()


class Section(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setStyleSheet(f"color: {T['accent']}; font-family: '{FONT}'; font-size: 10px;"
                           f"font-weight: 700; letter-spacing: 2px; background: transparent;")


class Switch(QAbstractButton):
    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(38, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col("accent") if self.isChecked() else col("track"))
        p.drawRoundedRect(QRectF(0, 0, 38, 22), 11, 11)
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(18 if self.isChecked() else 3, 3, 16, 16))
        p.end()


class Row(QAbstractButton):
    """菜单里的一行：左边文字，可选右边开关/提示"""
    toggled_by_user = Signal(bool)

    def __init__(self, text, switch=False, danger=False, hint=""):
        super().__init__()
        self.text_, self.hint, self.danger = text, hint, danger
        self.has_switch = switch
        self.hover = False
        self.on = False
        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._clicked)

    def set_on(self, v):
        self.on = bool(v)
        self.update()

    def _clicked(self):
        if self.has_switch:
            self.on = not self.on
            self.toggled_by_user.emit(self.on)
            self.update()

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col("hover"))
            p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 10, 10)
        p.setPen(col("bad") if self.danger else col("ink"))
        p.setFont(QFont(FONT, 10))
        p.drawText(QRectF(12, 0, self.width() - 70, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text_)
        if self.has_switch:
            x = self.width() - 12 - 38
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col("accent") if self.on else col("track"))
            p.drawRoundedRect(QRectF(x, (self.height() - 22) / 2, 38, 22), 11, 11)
            p.setBrush(QColor("white"))
            p.drawEllipse(QRectF(x + (18 if self.on else 3), (self.height() - 22) / 2 + 3, 16, 16))
        elif self.hint:
            p.setPen(col("sub"))
            p.setFont(QFont(FONT, 8))
            p.drawText(QRectF(0, 0, self.width() - 12, self.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, self.hint)
        p.end()


class Line(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(9)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setPen(QPen(col("line"), 1))
        p.drawLine(10, 4, self.width() - 10, 4)
        p.end()


def fade_in(w, ms=140):
    w.setWindowOpacity(0.0)
    a = QPropertyAnimation(w, b"windowOpacity", w)
    a.setDuration(ms)
    a.setStartValue(0.0)
    a.setEndValue(1.0)
    a.setEasingCurve(QEasingCurve.Type.OutCubic)
    w._fade = a
    a.start()


# ---------------------------------------------------------------- 状态卡片
class InfoCard(QWidget):
    """点击桌宠弹出的小卡片：额度圆环。形态/动作/设置都在右键菜单里，这里只放最常看的。"""
    WIDTH = 300
    TOP = 34            # 立绘探出卡片的高度
    HEAD = 68           # 彩色头部的高度

    def __init__(self, ui_dir=None):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                 | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus
                 | Qt.WindowType.NoDropShadowWindowHint)
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedWidth(self.WIDTH)
        self.badge = load_badge(ui_dir)
        self.portrait = None
        self.banner = None
        if ui_dir and os.path.exists(os.path.join(ui_dir, "card_header.png")):
            self.banner = QPixmap(os.path.join(ui_dir, "card_header.png"))
        self.name, self.sub = "Claude", ""
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)
        self.inside = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14 + 14, self.TOP + self.HEAD + 8, 14 + 14, 18 + 14)
        lay.setSpacing(8)
        rings = QHBoxLayout()
        rings.setSpacing(0)
        self.ring5 = Ring("5 小时")
        self.ring7 = Ring("7 天")
        rings.addStretch(1)
        rings.addWidget(self.ring5)
        rings.addStretch(1)
        rings.addWidget(self.ring7)
        rings.addStretch(1)
        lay.addLayout(rings)
        self.usage_note = QLabel("")
        self.usage_note.setWordWrap(True)
        self.usage_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.usage_note)
        self.restyle()

    def restyle(self):
        self.usage_note.setStyleSheet(f"color: {T['sub']}; font-family: '{FONT}'; font-size: 10px;"
                                      "background: transparent;")
        self.update()

    def set_portrait(self, pm: QPixmap):
        self.portrait = pm
        self.update()

    def update_data(self, usage, form_name):
        now = time.time()
        self.name = "Claude"
        self.sub = time.strftime("%m月%d日 %H:%M")

        def note(reset):
            return f"约 {usage_info.fmt_clock(reset)} 重置" if reset and reset > now else ""

        if usage.missing or not usage.known():
            self.ring5.set(None, "")
            self.ring7.set(None, "")
            self.usage_note.setText("没找到额度记录文件，可在 config.json 里用 usage_file 指定路径")
        else:
            self.ring5.set(usage.five, note(usage.five_reset))
            self.ring7.set(usage.seven, note(usage.seven_reset))
            self.usage_note.setText("")           # 数据来源之类的说明不显示，只在读不到时才提示
        self.usage_note.setVisible(bool(self.usage_note.text()))
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        body, path = paint_card_background(p, self.width(), self.height(), self.TOP)
        head = QRectF(body.x(), body.y(), body.width(), self.HEAD)
        p.save()
        p.setClipPath(path)
        p.setClipRect(head, Qt.ClipOperation.IntersectClip)
        if self.banner is not None:
            p.drawPixmap(head.toRect(), self.banner.scaled(head.size().toSize(),
                         Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        else:
            g = QLinearGradient(head.topLeft(), head.bottomRight())
            g.setColorAt(0.0, QColor(T["accent"]))
            g.setColorAt(1.0, QColor(T["accent2"]))
            p.fillRect(head, QBrush(g))
            p.setPen(Qt.PenStyle.NoPen)                          # 头部加几个淡淡的圆，不那么平
            p.setBrush(QColor(255, 255, 255, 28))
            p.drawEllipse(QPointF(head.left() + 50, head.bottom() - 4), 46, 46)
            p.drawEllipse(QPointF(head.center().x() + 20, head.top() + 6), 30, 30)
        p.restore()
        # 立绘从头部探出来：取立绘顶部的方形区域（头+上半身），顶部超出卡片，底部在头部下沿被切掉
        if self.portrait is not None:
            sq = self.portrait.width()
            sh = min(sq, self.portrait.height())                 # 宽图（像素机器人）取整张，高图取顶部方块
            side = 112 if self.portrait.height() >= sq else 92
            x = head.right() - side * 0.92
            y = head.top() - self.TOP + 2 + (112 - side * sh / sq if sh < sq else 0) * 0.5
            p.save()
            c = QPainterPath()
            c.addRect(QRectF(0, 0, self.width(), head.bottom()))
            p.setClipPath(c)
            p.drawPixmap(QRectF(x, y, side, side * sh / sq), self.portrait, QRectF(0, 0, sq, sh))
            p.restore()
        p.setPen(QColor("white"))
        f = QFont(FONT, 13)
        f.setBold(True)
        p.setFont(f)
        bw = draw_badge(p, self.badge, head.x() + 16, head.y() + 13, 26)
        tx = head.x() + 16 + (bw + 8 if bw else 0)
        p.drawText(QRectF(tx, head.y() + 12, 170, 26), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.name)
        p.setPen(QColor(255, 255, 255, 220))
        p.setFont(QFont(FONT, 8))
        p.drawText(QRectF(head.x() + 16, head.y() + 38, 180, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.sub)
        p.end()

    def enterEvent(self, e):
        self.inside = True
        self.hide_timer.stop()

    def leaveEvent(self, e):
        self.inside = False
        self.hide_timer.start(1200)           # 鼠标移开就很快收起来

    def popup(self, seconds=4.0):
        was = self.isVisible()
        self.show()
        self.raise_()
        if not was:
            fade_in(self)
            self.ring5.replay()
            self.ring7.replay()
        if not self.inside:
            self.hide_timer.start(int(seconds * 1000))
