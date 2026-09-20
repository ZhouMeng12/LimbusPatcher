"""批量建立对应：从某一行起，把连续的未对齐行按序对应到零协记录。

- ``plan_batch``：纯函数，负责“从起始记录起顺序分配（跳过已占用/空内容记录）”的决策。
- ``BatchMatchDialog``：左侧待对应行（默认最多 10 条，数量可调）+ 右侧候选记录（未占用置顶）。
  构造中不做任何 exec（由调用方决定何时 exec）。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from . import theme
from .dialogs import is_headless

DEFAULT_BATCH_COUNT = 10


def plan_batch(items: list[dict], start_record: int, count: int, used_records=(),
               records: list[dict] | None = None) -> list[tuple[str, int]]:
    """顺序分配：items 依次对应到 start_record 起的可用记录，返回 [(key, record)]。

    - 只处理带 ``key`` 的行（场景行会被忽略）；
    - ``used_records`` 中已被占用的记录会跳过；
    - 传入 ``records``（``StoryEdit.candidates`` 的结果）时，空内容记录也会跳过；
    - 可用记录不足时按实际数量返回（结果可能少于 ``count``）。
    """
    used = {int(r) for r in (used_records or ()) if r is not None}
    want = max(0, int(count))
    keys = [it.get("key") for it in items if isinstance(it, dict) and it.get("key")][:want]
    if not keys or want <= 0:
        return []
    start = int(start_record)
    if records is None:
        # 无候选清单：从 start 起连续取，跳过已占用记录（used 有限，必然终止）
        avail: list[int] = []
        r = start
        while len(avail) < len(keys):
            if r not in used:
                avail.append(r)
            r += 1
    else:
        avail = sorted(
            int(c["record"]) for c in records
            if isinstance(c.get("record"), int)
            and str(c.get("content") or "").strip()
            and int(c["record"]) not in used
            and int(c["record"]) >= start
        )[: len(keys)]
    return [(k, rec) for k, rec in zip(keys, avail)]


class BatchMatchDialog(QDialog):
    """result_value: (start_record, count) / None（取消）。"""

    def __init__(self, parent, items: list[dict], candidates: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("批量建立对应")
        self.resize(920, 620)
        self.result_value: tuple[int, int] | None = None
        self._items = [it for it in (items or []) if isinstance(it, dict) and it.get("key")]
        self._candidates = [c for c in (candidates or []) if isinstance(c, dict)]

        lay = QVBoxLayout(self)
        head = QLabel("从该行起连续的未对齐行 —— 按顺序对应到零协记录")
        head.setObjectName("title")
        lay.addWidget(head)

        body = QHBoxLayout()

        # ---- 左：待对应行 + 数量 ----
        left = QVBoxLayout()
        left_head = QLabel("待对应行（按序）")
        left_head.setObjectName("dim")
        left.addWidget(left_head)
        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("对应条数"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, max(1, len(self._items)))
        self.count_spin.setValue(min(DEFAULT_BATCH_COUNT, max(1, len(self._items))))
        self.count_spin.setToolTip(f"默认 {DEFAULT_BATCH_COUNT} 条，可调整")
        count_row.addWidget(self.count_spin)
        count_row.addStretch(1)
        left.addLayout(count_row)
        self.items_list = QListWidget()
        self.items_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        left.addWidget(self.items_list, 1)

        # ---- 右：候选记录 ----
        right = QVBoxLayout()
        right_head = QLabel("零协记录（未被占用的置顶）")
        right_head.setObjectName("dim")
        right.addWidget(right_head)
        self.cands_list = QListWidget()
        right.addWidget(self.cands_list, 1)

        body.addLayout(left, 3)
        body.addLayout(right, 4)
        lay.addLayout(body, 1)

        self.hint_label = QLabel("")
        self.hint_label.setObjectName("dim")
        lay.addWidget(self.hint_label)

        btns = QHBoxLayout()
        cancel = QPushButton("取消")
        self.ok_btn = QPushButton("建立对应")
        self.ok_btn.setObjectName("primary")
        self.ok_btn.setEnabled(False)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(self.ok_btn)
        lay.addLayout(btns)

        self._fill_items()
        self._fill_candidates()
        self._update_hint()

        cancel.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._accept)
        self.count_spin.valueChanged.connect(self._on_count_changed)
        self.cands_list.currentItemChanged.connect(lambda *_a: self._update_hint())
        self.cands_list.itemDoubleClicked.connect(lambda _i: self._accept())

    # ---- 填充 ----

    def _fill_items(self) -> None:
        self.items_list.clear()
        for n, it in enumerate(self._items[: self.count_spin.value()], 1):
            who = f"{it.get('speaker')}：" if it.get("speaker") else ""
            row = QListWidgetItem(f"{n}. {who}{str(it.get('text') or '')[:90]}")
            row.setData(Qt.ItemDataRole.UserRole, it.get("key"))
            self.items_list.addItem(row)

    def _fill_candidates(self) -> None:
        self.cands_list.clear()
        rows = sorted(self._candidates, key=lambda c: (bool(c.get("used")), int(c.get("record") or 0)))
        for c in rows:
            who = f"{c.get('teller')}：" if c.get("teller") else ""
            tag = "｜已被占用" if c.get("used") else ""
            it = QListWidgetItem(f"[{c.get('record')}] {who}{str(c.get('content') or '')[:80]}{tag}")
            it.setData(Qt.ItemDataRole.UserRole, int(c.get("record") or 0))
            if c.get("used"):
                it.setForeground(QColor(theme.TEXT_DIM))
            self.cands_list.addItem(it)

    # ---- 交互 ----

    def _on_count_changed(self, _value: int) -> None:
        self._fill_items()
        self._update_hint()

    def _update_hint(self) -> None:
        n = self.count_spin.value()
        it = self.cands_list.currentItem()
        self.ok_btn.setEnabled(it is not None)
        if it is None:
            self.hint_label.setText(f"请在右侧选择起始记录（本次将分配 {n} 条）")
        else:
            self.hint_label.setText(
                f"从记录 [{it.data(Qt.ItemDataRole.UserRole)}] 起按序分配 {n} 条（自动跳过已占用与空内容记录）"
            )

    def selected_record(self) -> int | None:
        it = self.cands_list.currentItem()
        if it is None:
            return None
        return int(it.data(Qt.ItemDataRole.UserRole))

    def _accept(self) -> None:
        rec = self.selected_record()
        if rec is None:
            return
        self.result_value = (rec, self.count_spin.value())
        self.accept()

    # ---- 免模态（无头）安全 ----

    def exec_safe(self) -> int:
        """免模态时直接返回 0（reject），否则等价于 ``exec()``。调用方应优先用它。"""
        if is_headless():
            return 0
        return self.exec()

    def exec(self) -> int:
        """免模态模式下不进入事件循环，立即返回 0（reject）。"""
        if is_headless():
            return 0
        return super().exec()
