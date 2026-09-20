"""首次启动引导卡片（三步引导条）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme


class OnboardingPage(QWidget):
    scan_requested = Signal()
    manual_requested = Signal()
    retry_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.addStretch(1)

        # 三步引导条
        steps = QFrame()
        steps.setObjectName("panel")
        steps.setFixedWidth(520)
        steps_layout = QHBoxLayout(steps)
        steps_layout.setContentsMargins(20, 10, 20, 10)
        self._step_labels: list[QLabel] = []
        for i, (num, text) in enumerate(
            [("1", "选择游戏目录"), ("2", "建立文本索引"), ("3", "应用并进游戏选择语言包")], start=1
        ):
            lbl = QLabel(f"{num} · {text}")
            lbl.setObjectName("chip")
            color = theme.ACCENT_DARK if i == 1 else theme.BORDER
            lbl.setStyleSheet(theme.CHIP_QSS.format(color=color))
            steps_layout.addWidget(lbl)
            if i < 3:
                arrow = QLabel("→")
                arrow.setObjectName("dim")
                steps_layout.addWidget(arrow)
        steps_layout.addStretch(1)
        steps_layout.insertStretch(0, 1)

        card = QFrame()
        card.setObjectName("panel")
        card.setFixedWidth(520)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(40, 36, 40, 36)
        inner.setSpacing(14)

        title = QLabel("尚未找到《边狱巴士》汉化目录")
        title.setObjectName("h1")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("本工具将读取零协会汉化（LLC_zh-CN），只写入独立的补丁副本，不会修改原始汉化文件。")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setObjectName("dim")

        btn_scan = QPushButton("自动扫描 Steam 库")
        btn_scan.setObjectName("primary")
        btn_scan.setMinimumHeight(38)
        btn_manual = QPushButton("手动选择游戏目录")
        btn_manual.setMinimumHeight(38)
        btn_retry = QPushButton("重新检测已选择的目录")
        btn_retry.setMinimumHeight(34)

        note = QLabel("零协汉化可通过零协工具箱安装；安装后回到这里点击「重新检测」。")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setObjectName("dim")

        inner.addWidget(title)
        inner.addWidget(sub)
        inner.addSpacing(8)
        inner.addWidget(btn_scan)
        inner.addWidget(btn_manual)
        inner.addWidget(btn_retry)
        inner.addSpacing(6)
        inner.addWidget(note)

        h = QHBoxLayout()
        h.addStretch(1)
        col = QVBoxLayout()
        col.setSpacing(10)
        col.addWidget(steps)
        col.addWidget(card)
        h.addLayout(col)
        h.addStretch(1)
        outer.addLayout(h)
        outer.addStretch(1)

        btn_scan.clicked.connect(self.scan_requested)
        btn_manual.clicked.connect(self.manual_requested)
        btn_retry.clicked.connect(self.retry_requested)

    def set_message(self, text: str) -> None:
        pass  # 保留扩展点：引导页文案动态化
