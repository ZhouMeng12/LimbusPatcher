"""顶栏「单颗状态药丸」+ 状态总览面板。

设计意图（见 DESIGN_SYSTEM.md §5）
----------------------------------
改版前顶栏并排挂着 5 颗 chip（保存 / 环境 / 应用 / 待确认 / 补译），信息等价、
没有主次，用户每次都要逐个读完才知道「现在到底有没有问题」。改版后收敛成**一颗**
药丸：默认只显示**最需要注意的那一条**（按 错误 > 警告 > 提示 > 正常 > 中性 排序），
点击才弹开完整清单。

用法::

    pill = StatusPill()
    pill.set_rows([
        StatusRow("env", "环境", "环境正常", "ok"),
        StatusRow("pending", "待确认", "37 条待确认", "warn"),
        ...
    ])
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from . import theme

#: 语气 → 严重度（数字越大越该被用户先看到）
TONE_ORDER: dict[str, int] = {"err": 4, "warn": 3, "info": 2, "ok": 1, "none": 0}

#: 语气 → 颜色 token 名
TONE_TOKEN: dict[str, str] = {
    "err": "ERROR",
    "warn": "WARNING",
    "info": "INFO",
    "ok": "SUCCESS",
    "none": "TEXT_FAINT",
}

#: 语气 → 面板里的中文说明
TONE_HINT: dict[str, str] = {
    "err": "需要马上处理",
    "warn": "建议关注",
    "info": "仅供参考",
    "ok": "正常",
    "none": "无",
}


@dataclass(frozen=True)
class StatusRow:
    """一条状态。``tone`` ∈ {"err","warn","info","ok","none"}。"""

    key: str
    label: str
    value: str
    tone: str = "none"
    hint: str = ""

    @property
    def urgency(self) -> int:
        return TONE_ORDER.get(self.tone, 0)

    def color(self) -> str:
        return getattr(theme, TONE_TOKEN.get(self.tone, "TEXT_FAINT"))


def _rgba(color: str, alpha: float) -> str:
    """``#rrggbb`` → ``rgba(r, g, b, a)``；已经是 rgba 的原样返回。"""
    c = color.strip()
    if c.startswith("rgba"):
        return c
    if c.startswith("#") and len(c) == 7:
        r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
        return f"rgba({r}, {g}, {b}, {alpha})"
    return c


def _dot(color: str, size: int = 8) -> QLabel:
    """状态圆点。巴士主题下圆角为 0，自然变成方块，跟直角语言一致。"""
    d = QLabel()
    d.setFixedSize(size, size)
    radius = max(0, int(theme.RADIUS_PILL) // 2)
    d.setStyleSheet(
        f"background: {color}; border-radius: {radius}px; border: none;"
    )
    return d


class StatusPopover(QFrame):
    """药丸点开后弹出的完整状态清单。"""

    def __init__(self, rows: list[StatusRow], parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("popover")
        self.setFrameShape(QFrame.Shape.NoFrame)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)

        head = QLabel("当前状态")
        head.setObjectName("popTitle")
        lay.addWidget(head)
        lay.addSpacing(6)

        for row in rows:
            item = QFrame()
            item.setObjectName("srow")
            rl = QHBoxLayout(item)
            rl.setContentsMargins(0, 5, 0, 5)
            rl.setSpacing(8)
            name = QLabel(row.label)
            name.setObjectName("dim")
            name.setFixedWidth(62)
            rl.addWidget(name)
            rl.addWidget(_dot(row.color()))
            val = QLabel(row.value)
            val.setStyleSheet(f"color: {row.color()}; font-weight: 600;")
            rl.addWidget(val)
            rl.addStretch(1)
            item.setToolTip(row.hint or TONE_HINT.get(row.tone, ""))
            lay.addWidget(item)

    def popup_below(self, anchor: QWidget) -> None:
        """贴在 anchor 下方弹出；越界时向左/向上收。"""
        self.adjustSize()
        pos = anchor.mapToGlobal(QPoint(0, anchor.height() + 6))
        win = anchor.window()
        if win is not None:
            g = win.geometry()
            if pos.x() + self.width() > g.right():
                pos.setX(max(g.left() + 8, g.right() - self.width() - 8))
        scr = anchor.screen()
        if scr is not None:
            avail = scr.availableGeometry()
            if pos.y() + self.height() > avail.bottom():
                pos.setY(anchor.mapToGlobal(QPoint(0, -self.height() - 6)).y())
        self.move(pos)
        self.show()


class StatusPill(QFrame):
    """单颗状态药丸：默认只显示最需要注意的一条，点击弹出全部。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pill")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rows: list[StatusRow] = []
        self._pop: StatusPopover | None = None
        self.setFixedHeight(28)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(7)
        self._dot = _dot(theme.TEXT_FAINT)
        self._text = QLabel("—")
        self._text.setStyleSheet("font-weight: 600; background: transparent;")
        # U+25BC（实心三角）：不要用 U+25BE，它在 YaHei / Segoe UI 与 Qt 兜底字体里缺字形。
        self._chev = QLabel("▼")
        self._chev.setObjectName("faint")
        lay.addWidget(self._dot)
        lay.addWidget(self._text)
        lay.addWidget(self._chev)

    # ---------- 数据 ----------

    def set_rows(self, rows: list[StatusRow]) -> None:
        self._rows = list(rows)
        self._refresh()

    @property
    def rows(self) -> list[StatusRow]:
        return list(self._rows)

    def top_row(self) -> StatusRow | None:
        """最需要注意的那一条（严重度最高；同级取靠前的）。"""
        if not self._rows:
            return None
        return max(self._rows, key=lambda r: r.urgency)

    def _refresh(self) -> None:
        row = self.top_row()
        if row is None:
            self._text.setText("—")
            self._dot.setStyleSheet(f"background: {theme.TEXT_FAINT}; border: none;")
            self._paint_skin(theme.TEXT_DIM, "none")
            self.setToolTip("")
            return
        color = row.color()
        self._text.setText(row.value)
        self._text.setStyleSheet(f"color: {theme.TEXT}; font-weight: 600; background: transparent;")
        radius = max(0, int(theme.RADIUS_PILL) // 2)
        self._dot.setStyleSheet(f"background: {color}; border-radius: {radius}px; border: none;")
        self._paint_skin(color, row.tone)
        hint = row.hint or TONE_HINT.get(row.tone, "")
        summary = "；".join(f"{r.label} {r.value}" for r in self._rows)
        self.setToolTip(f"{summary}" + (f"\n{hint}" if hint else ""))

    def _paint_skin(self, color: str, tone: str) -> None:
        """照原型 ``.pill.ok/.warn/.err/.mute``：同色系的半透明底 + 描边。"""
        r = max(0, int(theme.RADIUS_PILL) // 2)
        if tone in ("ok", "warn", "err"):
            self.setStyleSheet(
                f"QFrame#pill {{ background: {_rgba(color, 0.13)};"
                f" border: 1px solid {_rgba(color, 0.34)}; border-radius: {r}px; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame#pill {{ background: {theme.SURFACE_2};"
                f" border: 1px solid {theme.BORDER}; border-radius: {r}px; }}"
            )

    # ---------- 交互 ----------

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_popover()
            event.accept()
            return
        super().mousePressEvent(event)

    def toggle_popover(self) -> None:
        if self._pop is not None and self._pop.isVisible():
            self._pop.hide()
            return
        if not self._rows:
            return
        if self._pop is not None:          # 上一份已隐藏的浮层，别留着堆积
            self._pop.deleteLater()
        self._pop = StatusPopover(self._rows, self.window())
        self._pop.popup_below(self)
