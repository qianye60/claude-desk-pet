# -*- coding: utf-8 -*-
"""右键菜单（PetMenu）、调教卡片（TrainCard）、聊天输入框（ChatBox）。样式和主题都来自 ui.py。

设计思路：菜单像一个小控制台——顶部三张形态卡片，中间三个常用大按钮，下面是开关；
调教卡片只留两个滑块、描边小标签和一个开关，不堆实心大按钮。
"""
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QSize
from PySide6.QtGui import QPainter, QFont, QGuiApplication, QColor, QPen, QPainterPath, QFontMetrics
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QLineEdit,
                               QAbstractButton)

from ui import (T, FONT, col, paint_card_background, fade_in, draw_badge, Row, Line)


def _tint(key, a):
    c = QColor(T[key])
    c.setAlpha(a)
    return c


def _place(win, gx, gy):
    """把窗口放在锚点 (gx, gy) 的上方，并限制在屏幕内"""
    win.adjustSize()
    sc = QGuiApplication.screenAt(win.mapToGlobal(win.rect().topLeft())) or QGuiApplication.primaryScreen()
    ag = sc.availableGeometry()
    x = min(max(gx - win.width() // 2, ag.left()), ag.right() - win.width() + 1)
    y = min(max(gy - win.height(), ag.top()), ag.bottom() - win.height() + 1)
    win.move(int(x), int(y))


class _Popup(QWidget):
    """点到外面自动关闭的圆角卡片"""
    RADIUS = 18

    def __init__(self, width):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup
                 | Qt.WindowType.NoDropShadowWindowHint)
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedWidth(width)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_card_background(p, self.width(), self.height(), 14, radius=self.RADIUS)
        p.end()


def _label(text, size=10, key="sub", bold=False):
    l = QLabel(text)
    l.setStyleSheet(f"color: {T[key]}; font-family: '{FONT}'; font-size: {size}px;"
                    f"font-weight: {700 if bold else 400}; background: transparent;")
    return l


# ---------------------------------------------------------------- 小部件
class FormCard(QAbstractButton):
    """形态卡片：立绘头像 + 名字 + 气质标签；缺图时是虚线框"""
    W, H = 84, 138

    def __init__(self, fid, name, pm, tagline="", missing=False):
        super().__init__()
        self.fid, self.name, self.pm, self.tagline, self.missing = fid, name, pm, tagline, missing
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self.W, self.H)
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
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        w = self.width()
        if self.missing:
            p.setPen(QPen(col("line"), 1.6, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 14, 14)
            p.setPen(col("accent") if self.hover else col("sub"))
            p.setFont(QFont(FONT, 22))
            p.drawText(QRectF(0, 14, w, 50), Qt.AlignmentFlag.AlignCenter, "+")
            f = QFont(FONT, 10)
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(0, 82, w, 20), Qt.AlignmentFlag.AlignCenter, self.name)
            p.setFont(QFont(FONT, 8))
            p.setPen(col("sub"))
            p.drawText(QRectF(4, 102, w - 8, 30), int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap),
                       "放入立绘\nskins\\yujie")
            p.end()
            return
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col("hover") if self.hover else col("bg2"))
        p.drawRoundedRect(r, 14, 14)
        area = QRectF(7, 7, w - 14, 72)
        clip = QPainterPath()
        clip.addRoundedRect(area, 10, 10)
        p.save()
        p.setClipPath(clip)
        p.fillPath(clip, _tint("accent", 40))
        if self.pm is not None:
            if self.pm.width() > self.pm.height() * 1.1:          # 宽图（像素机器人）：完整放进去，四周留白
                s = min(area.width() / self.pm.width(), area.height() / self.pm.height()) * 0.78
                pw, ph = self.pm.width() * s, self.pm.height() * s
                top = area.center().y() - ph / 2
            else:                                                  # 立绘：横向铺满，高出的部分裁掉（保留头部）
                s = max(area.width() / self.pm.width(), 0.0)
                pw, ph = self.pm.width() * s, self.pm.height() * s
                top = area.top()
            p.drawPixmap(QRectF(area.center().x() - pw / 2, top, pw, ph), self.pm, QRectF(self.pm.rect()))
        p.restore()
        p.setPen(col("ink"))
        f = QFont(FONT, 10)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 82, w, 22), Qt.AlignmentFlag.AlignCenter,
                   QFontMetrics(f).elidedText(self.name, Qt.TextElideMode.ElideRight, w - 6))
        p.setPen(col("sub"))
        f2 = QFont(FONT, 8)
        p.setFont(f2)
        p.drawText(QRectF(3, 105, w - 6, 24), Qt.AlignmentFlag.AlignCenter,
                   QFontMetrics(f2).elidedText(self.tagline, Qt.TextElideMode.ElideRight, w - 8))
        if self.isChecked():                                  # 选中：强调色边 + 右上角对勾
            p.setPen(QPen(col("accent"), 2.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 14, 14)
            c = QPointF(w - 17, 17)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col("accent"))
            p.drawEllipse(c, 9, 9)
            p.setPen(QPen(QColor("white"), 1.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPolyline([QPointF(c.x() - 4, c.y()), QPointF(c.x() - 1, c.y() + 3.2), QPointF(c.x() + 4.2, c.y() - 3)])
        p.end()


class BigTile(QAbstractButton):
    """常用功能大按钮：标题 + 一行小字"""

    def __init__(self, title, hint):
        super().__init__()
        self.title, self.hint = title, hint
        self.hover = False
        self.setFixedHeight(54)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_tint("accent", 34) if self.hover else col("bg2"))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 14, 14)
        p.setPen(col("accent") if self.hover else col("ink"))
        f = QFont(FONT, 11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 9, self.width(), 22), Qt.AlignmentFlag.AlignCenter, self.title)
        p.setPen(col("sub"))
        p.setFont(QFont(FONT, 8))
        p.drawText(QRectF(0, 31, self.width(), 16), Qt.AlignmentFlag.AlignCenter, self.hint)
        p.end()


class SmallBtn(QAbstractButton):
    """次要按钮：描边小标签（也用作“爱说的内容”的开关标签）"""

    def __init__(self, text, checkable=False, checked=False):
        super().__init__()
        self.text_ = text
        self.setCheckable(checkable)
        self.setChecked(checked)
        self.hover = False
        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return QSize(QFontMetrics(QFont(FONT, 10)).horizontalAdvance(self.text_) + 28, 30)

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.8, 0.8, self.width() - 1.6, self.height() - 1.6)
        on = self.isChecked()
        if on:
            p.setBrush(_tint("accent", 40))
            p.setPen(QPen(col("accent"), 1.2))
        else:
            p.setBrush(_tint("accent", 24) if self.hover else Qt.BrushStyle.NoBrush)
            p.setPen(QPen(col("line"), 1.2))
        p.drawRoundedRect(r, 15, 15)
        p.setPen(col("accent") if (on or self.hover) else col("sub"))
        f = QFont(FONT, 10)
        f.setBold(on)
        p.setFont(f)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.text_)
        p.end()


class Header(QWidget):
    def __init__(self, title, sub="", badge=None):
        super().__init__()
        self.title, self.sub, self.badge = title, sub, badge
        self.setFixedHeight(40 if sub else 28)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bw = draw_badge(p, self.badge, 2, 3, 22)
        x = 2 + (bw + 8 if bw else 0)
        p.setPen(col("ink"))
        f = QFont(FONT, 13)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(x, 0, self.width() - x, 26), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.title)
        if self.sub:
            p.setPen(col("sub"))
            p.setFont(QFont(FONT, 9))
            p.drawText(QRectF(x, 24, self.width() - x, 16), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.sub)
        p.end()


# ---------------------------------------------------------------- 右键菜单
class PetMenu(_Popup):
    triggered = Signal(str, object)     # (动作名, 参数)

    def __init__(self, forms, current, state, badge=None):
        """forms: [(id, 名字, QPixmap 或 None, 标签, 是否缺图)]，最多显示 3 个形态"""
        super().__init__(304)
        self.RADIUS = 18
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14 + 14, 14 + 12, 14 + 14, 18 + 12)
        lay.setSpacing(10)
        lay.addWidget(Header("Claude", "", badge))

        fr = QHBoxLayout()
        fr.setSpacing(8)
        for fid, name, pm, tagline, missing in forms[:3]:
            b = FormCard(fid, name, pm, tagline, missing)
            b.setChecked(fid == current)
            b.clicked.connect(lambda _c=False, f=fid: self._emit("form", f))
            fr.addWidget(b)
        fr.addStretch(1)
        lay.addLayout(fr)

        tiles = QHBoxLayout()
        tiles.setSpacing(8)
        for title, hint, key in (("额度", "5 小时 · 7 天", "card"), ("聊天", "跟她说话", "chat"), ("调教", "养成性格", "train")):
            t = BigTile(title, hint)
            t.clicked.connect(lambda _c=False, k=key: self._emit(k, None))
            tiles.addWidget(t)
        lay.addLayout(tiles)

        pos = QHBoxLayout()
        pos.setSpacing(8)
        for text, key in (("回到 Claude 窗口", "perch"), ("去任务栏", "taskbar")):
            b = SmallBtn(text)
            b.clicked.connect(lambda _c=False, k=key: self._emit(k, None))
            pos.addWidget(b)
        pos.addStretch(1)
        lay.addLayout(pos)

        lay.addWidget(Line())
        rows = QVBoxLayout()
        rows.setSpacing(0)
        for text, key in (("跟随 Claude 启动和退出", "follow"), ("安静模式", "quiet"), ("精确额度（官方接口）", "accurate")):
            r = Row(text, switch=True)
            r.set_on(state.get(key))
            r.setFixedHeight(28)
            r.toggled_by_user.connect(lambda v, k=key: self._emit(k, v, close=False))
            rows.addWidget(r)
        lay.addLayout(rows)
        lay.addWidget(Line())
        q = Row("退出", danger=True)
        q.setFixedHeight(28)
        q.clicked.connect(lambda _c=False: self._emit("quit", None))
        lay.addWidget(q)

    def _emit(self, key, arg, close=True):
        self.triggered.emit(key, arg)
        if close:
            self.close()

    def popup_at(self, gx, gy):
        self.adjustSize()
        sc = QGuiApplication.screenAt(self.mapToGlobal(self.rect().topLeft())) or QGuiApplication.primaryScreen()
        ag = sc.availableGeometry()
        x = min(max(gx, ag.left()), ag.right() - self.width() + 1)
        y = gy - self.height() + 18
        if y < ag.top():
            y = gy - 14
        y = min(max(y, ag.top()), ag.bottom() - self.height() + 1)
        self.move(int(x), int(y))
        self.show()
        fade_in(self, 110)


# ---------------------------------------------------------------- 调教卡片
def slider_qss():
    return f"""
    QSlider::groove:horizontal {{ height: 6px; background: {T['track']}; border-radius: 3px; }}
    QSlider::sub-page:horizontal {{ background: {T['accent']}; border-radius: 3px; }}
    QSlider::handle:horizontal {{ background: white; border: 2px solid {T['accent']};
                                  width: 14px; height: 14px; margin: -6px 0; border-radius: 9px; }}
    """


class TrainCard(_Popup):
    """调教卡片：两个滑块 + 爱说的内容（描边小标签）+ 自主行为开关 + 对刚说的那句表态"""
    changed = Signal(str, object)       # "talk"/"lively"/"pool:名"/"snoop"/"like"/"ban"

    def __init__(self, train, pools, last_line, snoop_on=False):
        super().__init__(308)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14 + 16, 14 + 14, 14 + 16, 18 + 14)
        lay.setSpacing(10)
        lay.addWidget(Header("调教", "像养宠物一样，慢慢调成你喜欢的样子"))

        for key, label, val, lo, hi in (("talk", "话多程度", train.talk, "安静", "话痨"),
                                         ("lively", "活泼程度", train.lively, "乖巧", "好动")):
            box = QVBoxLayout()
            box.setSpacing(5)
            row = QHBoxLayout()
            row.addWidget(_label(label, 12, "ink", True))
            row.addStretch(1)
            row.addWidget(_label(f"{lo} · {hi}", 9))
            box.addLayout(row)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(0, 20)
            sl.setValue(int(round(val * 10)))
            sl.setStyleSheet(slider_qss())
            sl.setCursor(Qt.CursorShape.PointingHandCursor)
            sl.valueChanged.connect(lambda v, k=key: self.changed.emit(k, v / 10.0))
            box.addWidget(sl)
            lay.addLayout(box)

        lay.addWidget(_label("爱说的内容", 11, "ink", True))
        wrap = QVBoxLayout()
        wrap.setSpacing(6)
        row = None
        for i, (key, label) in enumerate(pools):
            if i % 3 == 0:
                row = QHBoxLayout()
                row.setSpacing(6)
                wrap.addLayout(row)
            b = SmallBtn(label, checkable=True, checked=train.pool_weight(key) > 0)
            b.toggled.connect(lambda on, k=key: self.changed.emit("pool:" + k, on))
            row.addWidget(b)
        if row is not None:
            row.addStretch(1)
        lay.addLayout(wrap)

        lay.addWidget(Line())
        sn = Row("自己翻文件夹并点评", switch=True)
        sn.set_on(snoop_on)
        sn.setFixedHeight(28)
        sn.toggled_by_user.connect(lambda v: self.changed.emit("snoop", v))
        lay.addWidget(sn)
        note = _label("条件合适时她会看看桌面、文档、视频里的文件名，调侃两句。只看文件名、不看内容，"
                      "文件名会发给 AI；每天最多 3 次。", 9)
        note.setWordWrap(True)
        lay.addWidget(note)

        if last_line:
            lay.addWidget(Line())
            lay.addWidget(_label("刚才那句", 11, "ink", True))
            q = _label("“" + last_line + "”", 11, "ink")
            q.setWordWrap(True)
            lay.addWidget(q)
            br = QHBoxLayout()
            br.setSpacing(8)
            for text, key in (("喜欢，多说点", "like"), ("别再说这句", "ban")):
                b = SmallBtn(text)
                b.clicked.connect(lambda _c=False, k=key: (self.changed.emit(k, last_line), self.close()))
                br.addWidget(b)
            br.addStretch(1)
            lay.addLayout(br)

    def popup_near(self, gx, gy):
        _place(self, gx, gy)
        self.show()
        fade_in(self, 120)


# ---------------------------------------------------------------- 聊天输入框
class ChatBox(_Popup):
    sent = Signal(str)

    def __init__(self, placeholder="跟她说点什么，回车发送"):
        super().__init__(300)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14 + 12, 14 + 8, 14 + 12, 18 + 8)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setMaxLength(120)
        self.edit.setStyleSheet(f"""
            QLineEdit {{ background: {T['bg2']}; color: {T['ink']}; border: none; border-radius: 14px;
                         padding: 8px 14px; font-family: '{FONT}'; font-size: 13px; }}""")
        self.edit.returnPressed.connect(self._send)
        lay.addWidget(self.edit)

    def _send(self):
        t = self.edit.text().strip()
        if t:
            self.sent.emit(t)
        self.close()

    def popup_near(self, gx, gy):
        _place(self, gx, gy)
        self.show()
        fade_in(self, 100)
        self.activateWindow()
        self.edit.setFocus()
