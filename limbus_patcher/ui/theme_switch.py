"""顶栏「风格 · XX」按钮 + 其浮层里的嵌套分段切换器。

与原型一一对应
--------------
原型顶栏右侧是一颗 ``#themeBtn``（文案 ``风格 · 巴士``），点开才弹出
``#themePop``：标题「界面风格」+ ``1 + (1+1)`` 的分段控件 ——

* 左半「巴士」：直接选中该风格；
* 右半「简约」：点一下**不提交**，而是把右半原地换成「亮 / 暗」两格，
  再点亮暗才提交并重建界面。

旧版把 ``[巴士][简约 ▼]`` 两格直接摆在顶栏上，和原型不符（原型顶栏只有
一颗按钮），因此这里改回「单按钮 + 浮层」。
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import theme

#: 分组定义：左「巴士」不可展开，右「简约」展开出暗/亮。
_BUS = theme.THEME_GROUPS[0]
_MINI = theme.THEME_GROUPS[1]

#: 浮层里分段控件的尺寸（原型 ``.switch{width:236px;height:44px;padding:3px}``）。
_SWITCH_W = 236
_SWITCH_H = 40


def style_label(theme_id: str) -> str:
    """``风格 · XX`` 里的 ``XX``：巴士 / 简约 · 暗 / 简约 · 亮。"""
    tid = theme.resolve_theme(theme_id)
    if tid == "bus":
        return _BUS["label"]
    tone = dict(_MINI["children"]).get(tid, "")
    return f"{_MINI['label']} · {tone}" if tone else _MINI["label"]


class StylePopover(QFrame):
    """原型 ``#themePop``：标题 + 分段切换器 + 说明。"""

    style_picked = Signal(str)

    def __init__(self, current: str = "", parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("stylePop")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._current = theme.resolve_theme(current or theme.current_mode())
        self._tone_shown = False        # 右半是否已从「简约」展开成「亮 / 暗」

        lay = QVBoxLayout(self)
        lay.setContentsMargins(11, 11, 11, 11)
        lay.setSpacing(8)

        title = QLabel("界面风格")
        title.setObjectName("popTitle")
        lay.addWidget(title)

        track = QFrame()
        track.setObjectName("switchTrack")
        track.setFixedSize(_SWITCH_W, _SWITCH_H)
        tlay = QHBoxLayout(track)
        tlay.setContentsMargins(3, 3, 3, 3)
        tlay.setSpacing(0)
        self._tlay = tlay

        self._bus_btn = QPushButton(_BUS["label"])
        self._bus_btn.setObjectName("segOpt")
        self._bus_btn.setCheckable(True)
        self._bus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bus_btn.setToolTip(_BUS["hint"])
        self._bus_btn.clicked.connect(lambda _c=False: self._pick_bus())
        tlay.addWidget(self._bus_btn, 1)

        # 右半：巴士选中时是单格「简约」；简约选中时换成「亮 / 暗」两格
        self._mini_btn = QPushButton(_MINI["label"])
        self._mini_btn.setObjectName("segOpt")
        self._mini_btn.setCheckable(True)
        self._mini_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mini_btn.setToolTip(f"{_MINI['hint']}（点开选暗/亮）")
        self._mini_btn.clicked.connect(lambda _c=False: self._show_tone())
        tlay.addWidget(self._mini_btn, 1)

        self._tone_btns: dict[str, QPushButton] = {}
        # 展示顺序照原型 `.tone-menu`：亮在左、暗在右（THEME_GROUPS 里是「默认的暗」在前）
        for tid, label in reversed(_MINI["children"]):
            b = QPushButton(label)
            b.setObjectName("segOpt")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, t=tid: self._pick_tone(t))
            b.hide()
            tlay.addWidget(b, 1)
            self._tone_btns[tid] = b

        lay.addWidget(track)

        hint = QLabel("切换风格会重建界面，未保存的编辑内容不会丢。")
        hint.setObjectName("faint")
        hint.setWordWrap(True)
        hint.setFixedWidth(_SWITCH_W)
        lay.addWidget(hint)

        self._sync()

    # ---------- 状态 ----------

    def set_current(self, theme_id: str) -> None:
        self._current = theme.resolve_theme(theme_id)
        self._tone_shown = False
        self._sync()

    def _sync(self) -> None:
        cur = self._current
        is_mini = cur.startswith("mini")
        # 右半何时显示「亮 / 暗」：已点开（_tone_shown）或当前就是简约
        shown = self._tone_shown or is_mini
        self._bus_btn.setChecked(cur == "bus" and not shown)
        self._mini_btn.setChecked(is_mini)
        self._mini_btn.setVisible(not shown)
        preview = cur if is_mini else "mini-dark"   # 还没选：预览默认的「简约 · 暗」
        for tid, b in self._tone_btns.items():
            b.setVisible(shown)
            b.setChecked(tid == preview)
        # 宽度比例照原型：未展开 = 巴士/简约 各一半；展开 = 巴士一半、亮暗各四分之一。
        # 用固定宽度而不是 stretch —— QBoxLayout 的 stretch 只分配"多余空间"，
        # 各格 sizeHint 接近时算出来仍是三等分，跟原型比例不符。
        inner = _SWITCH_W - 6
        half = inner // 2
        self._bus_btn.setFixedWidth(half)
        self._mini_btn.setFixedWidth(inner - half)
        tones = list(self._tone_btns.values())
        if tones:
            each = (inner - half) // len(tones)
            for b in tones:
                b.setFixedWidth(each)

    # ---------- 交互 ----------

    def _show_tone(self) -> None:
        """点「简约」：只把右半换成「亮 / 暗」，**不提交、也不改 _current**。"""
        self._tone_shown = True
        self._sync()

    def _pick_bus(self) -> None:
        if self._current == "bus":
            self._sync()
            return                      # 已经是巴士：不重复发信号
        self._current = "bus"
        self._tone_shown = False
        self._sync()
        self.style_picked.emit("bus")

    def _pick_tone(self, tid: str) -> None:
        if self._current == tid:
            self._sync()
            return                      # 已经是该亮暗：不重复发信号
        self._current = tid
        self._sync()
        self.style_picked.emit(tid)


class ThemeSwitcher(QPushButton):
    """顶栏那颗 ``风格 · XX`` 按钮（原型 ``#themeBtn``）。"""

    theme_selected = Signal(str)

    def __init__(self, current: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._current = theme.resolve_theme(current or theme.current_mode())
        self._pop: StylePopover | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(28)          # 与原型 .btn 及「应用到游戏」等高
        self.setToolTip("切换界面风格（切换后会重建界面）")
        self.clicked.connect(lambda _c=False: self.toggle_popover())
        self.set_current(self._current)

    # ---------- 状态 ----------

    @property
    def current(self) -> str:
        return self._current

    def set_current(self, theme_id: str) -> None:
        self._current = theme.resolve_theme(theme_id)
        self.setText(f"风格 · {style_label(self._current)}")
        if self._pop is not None:
            self._pop.set_current(self._current)

    # ---------- 交互 ----------

    def toggle_popover(self) -> None:
        if self._pop is not None and self._pop.isVisible():
            self._close_popover()
            return
        self._open_popover()

    def _open_popover(self) -> None:
        pop = StylePopover(self._current, self.window())
        pop.style_picked.connect(self._on_picked)
        self._pop = pop
        pop.adjustSize()
        pos = self.mapToGlobal(QPoint(0, self.height() + 6))
        win = self.window()
        if win is not None:
            g = win.geometry()
            if pos.x() + pop.width() > g.right():
                pos.setX(max(g.left() + 8, g.right() - pop.width() - 8))
        pop.move(pos)
        pop.show()

    def _close_popover(self) -> None:
        if self._pop is not None:
            self._pop.hide()
        self._pop = None

    def _on_picked(self, theme_id: str) -> None:
        # 主窗口会重建界面，本控件随之销毁；先断开引用再发信号，避免悬空。
        pop, self._pop = self._pop, None
        if pop is not None:
            pop.hide()
        self._current = theme.resolve_theme(theme_id)
        self.setText(f"风格 · {style_label(self._current)}")
        self.theme_selected.emit(self._current)
