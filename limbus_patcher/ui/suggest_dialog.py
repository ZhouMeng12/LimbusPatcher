"""自动建议对应的确认对话框：列出「wiki 原句 → 零协记录」的建议，逐条勾选后批量应用。

构造时不做任何 exec（由调用方决定何时 show/exec），便于离屏测试与自动化。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import theme


class SuggestDialog(QDialog):
    """result_value: 选中的建议列表（每项同 StoryEdit.suggest_matches 的返回元素）。"""

    def __init__(self, parent, suggestions: list[dict], scope_label: str = ""):
        super().__init__(parent)
        self.setWindowTitle("自动建议对应")
        self.resize(980, 680)
        self.result_value: list[dict] | None = None
        self._suggestions = list(suggestions or [])
        self._boxes: list[QCheckBox] = []

        lay = QVBoxLayout(self)
        head = QLabel("按文本相似度自动匹配到的对应（默认全选，取消勾选可跳过个别条目）")
        head.setObjectName("title")
        lay.addWidget(head)
        self.summary = QLabel("")
        self.summary.setObjectName("dim")
        lay.addWidget(self.summary)

        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        self.rows = QVBoxLayout(inner)
        self.rows.setContentsMargins(4, 4, 4, 4)
        self.rows.setSpacing(4)
        for s in self._suggestions:
            percent = round(float(s.get("similarity", 0)) * 100)
            box = QCheckBox(f"[{percent}%] 记录 {s.get('record')} · {s.get('page', '')}")
            box.setChecked(True)
            box.setToolTip("wiki：" + str(s.get("text", "")))
            detail = QLabel(
                "  wiki：" + _short(s.get("text", ""))
                + "\n  零协：" + _short(s.get("content", ""))
            )
            detail.setObjectName("dim")
            detail.setWordWrap(True)
            row = QVBoxLayout()
            row.setSpacing(0)
            row.addWidget(box)
            row.addWidget(detail)
            holder = QWidget()
            holder.setLayout(row)
            holder.setStyleSheet(f"background: {theme.PANEL}; border-radius: 4px;")
            self.rows.addWidget(holder)
            self._boxes.append(box)
        self.rows.addStretch(1)
        area.setWidget(inner)
        lay.addWidget(area, 1)

        btns = QHBoxLayout()
        self.all_btn = QPushButton("全选")
        self.none_btn = QPushButton("全不选")
        cancel = QPushButton("取消")
        ok = QPushButton("应用选中的对应")
        ok.setObjectName("primary")
        btns.addWidget(self.all_btn)
        btns.addWidget(self.none_btn)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

        self._scope_label = scope_label
        self.all_btn.clicked.connect(lambda: self._set_all(True))
        self.none_btn.clicked.connect(lambda: self._set_all(False))
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._accept)
        for box in self._boxes:
            box.toggled.connect(lambda _on: self._update_summary())
        self._update_summary()

    # ---- 状态 ----

    def selected(self) -> list[dict]:
        return [s for s, box in zip(self._suggestions, self._boxes) if box.isChecked()]

    def _set_all(self, on: bool) -> None:
        for box in self._boxes:
            box.setChecked(bool(on))

    def _update_summary(self) -> None:
        n = len(self.selected())
        scope = f"{self._scope_label} · " if self._scope_label else ""
        high = sum(1 for s in self.selected() if float(s.get("similarity", 0)) >= 0.99)
        self.summary.setText(
            f"{scope}建议 {len(self._suggestions)} 条，已选 {n} 条"
            + (f"（其中完全一致 {high} 条）" if high else "")
        )

    def _accept(self) -> None:
        self.result_value = self.selected()
        self.accept()


def _short(text: str, limit: int = 60) -> str:
    s = (text or "").replace("\n", " ").strip()
    return s if len(s) <= limit else s[:limit] + "…"
