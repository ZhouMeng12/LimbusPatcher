"""手动建立对应对话框：为一句未对齐的 wiki 台词挑选零协本地记录（或标记跳过）。"""
from __future__ import annotations

import difflib

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from ..storybook import norm_text
from . import theme


def _similarity(wiki_key: str, content: str) -> float:
    """归一化文本上的相似度（0~1）；任一为空串时视为 0。"""
    cand_key = norm_text(content or "")
    if not wiki_key or not cand_key:
        return 0.0
    ratio = difflib.SequenceMatcher(None, wiki_key, cand_key, autojunk=False).ratio()
    return min(1.0, max(0.0, ratio))


class ManualMatchDialog(QDialog):
    """result: ("record", idx) / ("skip", None) / None（取消）。"""

    def __init__(self, parent, wiki_text: str, file: str, candidates: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("建立对应")
        self.resize(760, 560)
        self.result_value: tuple[str, int | None] | None = None
        self._candidates = candidates
        self._wiki_key = norm_text(wiki_text or "")
        # (候选, 是否已被占用, 相似度)：相似度只算一次，过滤时复用。
        self._rows: list[tuple[dict, bool, float]] = [
            (c, bool(c["used"]), _similarity(self._wiki_key, c["content"])) for c in candidates
        ]

        lay = QVBoxLayout(self)
        head = QLabel("wiki 台词（未对齐）")
        head.setObjectName("dim")
        wiki = QLabel(wiki_text)
        wiki.setWordWrap(True)
        wiki.setStyleSheet(f"color: {theme.TEXT}; background: {theme.PANEL}; padding: 8px; border-radius: 4px;")
        src = QLabel(f"零协文件：{file} —— 请从下方选择对应记录（可用记录置顶，同组按相似度排序）")
        src.setObjectName("dim")

        self.search = QLineEdit()
        self.search.setPlaceholderText("过滤记录内容…")
        self.listw = QListWidget()
        self.listw.itemDoubleClicked.connect(lambda _i: self._accept_record())

        btns = QHBoxLayout()
        self.skip_btn = QPushButton("标记为无法对应（跳过）")
        self.clear_btn = QPushButton("清除手动对应")
        cancel = QPushButton("取消")
        ok = QPushButton("建立对应")
        ok.setObjectName("primary")
        btns.addWidget(self.skip_btn)
        btns.addWidget(self.clear_btn)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(ok)

        lay.addWidget(head)
        lay.addWidget(wiki)
        lay.addWidget(src)
        lay.addWidget(self.search)
        lay.addWidget(self.listw, 1)
        lay.addLayout(btns)

        self._fill()
        self.search.textChanged.connect(self._fill)
        ok.clicked.connect(self._accept_record)
        cancel.clicked.connect(self.reject)
        self.skip_btn.clicked.connect(self._accept_skip)
        self.clear_btn.clicked.connect(self._accept_clear)

    def _fill(self) -> None:
        q = self.search.text().strip().lower()
        self.listw.clear()
        rows = [
            r
            for r in self._rows
            if not q or q in r[0]["content"].lower() or q in str(r[0]["record"])
        ]
        # 未被占用优先；同组内按相似度降序（稳定排序：同分保持原有顺序）。
        rows.sort(key=lambda r: (r[1], -r[2]))
        for c, used, sim in rows:
            who = f"{c['teller']}：" if c["teller"] else ""
            tag = "｜已被占用" if used else ""
            it = QListWidgetItem(f"[{c['record']}] {round(sim * 100)}% {who}{c['content'][:80]}{tag}")
            it.setData(Qt.ItemDataRole.UserRole, c["record"])
            if used:
                it.setForeground(QColor(theme.TEXT_DIM))
            self.listw.addItem(it)

    def _accept_record(self) -> None:
        it = self.listw.currentItem()
        if it is None:
            return
        self.result_value = ("record", int(it.data(Qt.ItemDataRole.UserRole)))
        self.accept()

    def _accept_skip(self) -> None:
        self.result_value = ("skip", None)
        self.accept()

    def _accept_clear(self) -> None:
        self.result_value = ("clear", None)
        self.accept()
