"""顶栏品牌区 —— 原型 ``.brand`` 的 Qt 落地。

原型对应：
    ``<div class="logo">邊</div>`` + ``<div class="brand-name">…</div>``
    + ``<span class="savedot">``

其中 logo 的金色方块在「巴士」主题带 10px 斜切角（原型 ``--cut``），
在「简约」主题是直角方块（``--cut:0``）。斜切用 ``QPainterPath`` 画，
不用 QSS ``border-radius``（圆角画不出直角里的斜切口）。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from . import theme


class LogoMark(QWidget):
    """品牌金方块 + 可选的角部斜切 + 单字「邊」。"""

    def __init__(self, text: str = "邊", size: int = 28, parent: QWidget | None = None):
        super().__init__(parent)
        self._text = text
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, _event) -> None:  # noqa: N802 —— 保持 Qt 命名
        # 颜色在绘制时取，跟随当前主题（切换主题会重建窗口，这里只是双保险）
        cut = int(theme.LOGO_CUT)
        w = self.width()
        h = self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        path = QPainterPath()
        if cut > 0:
            path.moveTo(cut, 0)
            path.lineTo(w, 0)
            path.lineTo(w, h - cut)
            path.lineTo(w - cut, h)
            path.lineTo(0, h)
            path.lineTo(0, cut)
            path.closeSubpath()
        else:
            path.addRect(0, 0, w, h)
        p.fillPath(path, QColor(theme.ACCENT))

        font = QFont(self.font())
        font.setBold(True)
        font.setPixelSize(14)
        p.setFont(font)
        p.setPen(QColor(theme.ON_ACCENT))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)


class SaveDot(QLabel):
    """品牌名后面的小圆点：有未落盘改动时由主窗口换成警示色。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("saveDot")
        self.setFixedSize(6, 6)
        self.setToolTip("已保存")

    def set_state(self, saved: bool) -> None:
        color = theme.SUCCESS if saved else theme.WARNING
        self.setStyleSheet(f"background: {color}; border-radius: 3px;")
        self.setToolTip("已保存" if saved else "有未保存修改")


class MoreButton(QPushButton):
    """顶栏最右的「更多操作」按钮（原型 ``#moreBtn``）。

    原型里那三颗点是 SVG，不是文字。这里也**画**出来：U+22EF（居中省略号）
    在 Microsoft YaHei UI / Segoe UI / SimHei 里都没有字形，会被渲染成豆腐块；
    U+2026（省略号）虽有字形但贴在基线上、位置偏低。自己画最稳。
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ghostIcon")
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("更多操作")

    def paintEvent(self, event) -> None:  # noqa: N802 —— 保持 Qt 命名
        super().paintEvent(event)       # 先让 QSS 画底与描边
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.TEXT if self.underMouse() else theme.TEXT_DIM))
        cy = self.height() / 2
        for cx in (9.0, 14.0, 19.0):
            p.drawEllipse(QPointF(cx, cy), 1.6, 1.6)
        p.end()
