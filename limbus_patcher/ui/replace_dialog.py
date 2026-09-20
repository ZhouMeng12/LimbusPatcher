"""一键替换（批量查找替换）对话框。

范围（由调用方给出，用户看到什么就替换什么）：
- 当前列表：列表里筛选出来的命中；
- 某个人格 / E.G.O：图鉴详情页里点「一键替换」；
- 全库：不带范围直接开（会先在索引里按查找词预筛）。

安全设计：
- 只写方案（零协原文文件一个字节都不动）；
- 先预览再应用，表格里可以逐条取消勾选；
- 每条改动都进历史记录；另外顶部保留「撤销上次替换」一键回退这一次批量操作。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .. import replace as repl
from .dialogs import info, safe_exec, warn

COL_CHECK, COL_LABEL, COL_BEFORE, COL_AFTER = range(4)


class ReplaceDialog(QDialog):
    """查找 / 替换（批量）。"""

    def __init__(self, parent, ctx, scope_label: str = "全库", hits=None, entity_key: str | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.hits = hits
        self.entity_key = entity_key
        self.scope_label = scope_label
        self.items: list[repl.ReplaceItem] = []
        self.applied: list[repl.ReplaceItem] = []
        self.saved = False

        self.setWindowTitle("一键替换")
        self.resize(1000, 640)

        lay = QVBoxLayout(self)
        head = QLabel(f"一键替换 · 范围：{scope_label}")
        head.setObjectName("title")
        lay.addWidget(head)
        tip = QLabel(
            "只替换「方案」里的自定义文本，零协原文文件不会被改动；替换后仍需点「应用到游戏」才会生效。\n"
            "先点「预览」，确认无误再「应用」。"
        )
        tip.setObjectName("dim")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("查找"))
        self.find_edit = QLineEdit()
        row1.addWidget(self.find_edit, 1)
        row1.addWidget(QLabel("替换为"))
        self.repl_edit = QLineEdit()
        row1.addWidget(self.repl_edit, 1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        self.case_box = QCheckBox("区分大小写")
        self.case_box.setChecked(True)
        self.regex_box = QCheckBox("正则表达式")
        self.whole_box = QCheckBox("整段完全匹配")
        row2.addWidget(self.case_box)
        row2.addWidget(self.regex_box)
        row2.addWidget(self.whole_box)
        row2.addSpacing(12)
        row2.addWidget(QLabel("替换"))
        self.source_combo = QComboBox()
        for key, label in ((repl.SOURCE_BOTH, "两者都替换"), (repl.SOURCE_ORIGINAL, "只替换零协原文"),
                           (repl.SOURCE_CUSTOM, "只替换自定义文本")):
            self.source_combo.addItem(label, key)
        self.source_combo.setToolTip(
            "两者都替换：改过的条目在自定义文本上替换，没改过的按原文替换后写入方案\n"
            "只替换零协原文：一律按原文算，会覆盖这条已有的自定义改动"
        )
        row2.addWidget(self.source_combo)
        row2.addStretch(1)
        self.preview_btn = QPushButton("预览")
        self.preview_btn.setObjectName("primary")
        row2.addWidget(self.preview_btn)
        lay.addLayout(row2)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "位置", "替换前", "替换后"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_CHECK, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(COL_CHECK, 32)
        hh.setSectionResizeMode(COL_LABEL, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(COL_LABEL, 320)
        hh.setSectionResizeMode(COL_BEFORE, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(COL_AFTER, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)

        tools = QHBoxLayout()
        self.all_btn = QPushButton("全选")
        self.none_btn = QPushButton("全不选")
        self.status = QLabel("还没有预览结果")
        self.status.setObjectName("dim")
        tools.addWidget(self.all_btn)
        tools.addWidget(self.none_btn)
        tools.addWidget(self.status, 1)
        lay.addLayout(tools)

        btns = QHBoxLayout()
        self.undo_btn = QPushButton("撤销上次替换")
        self.undo_btn.setEnabled(False)
        close = QPushButton("关闭")
        self.apply_btn = QPushButton("应用到方案")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.setEnabled(False)
        btns.addWidget(self.undo_btn)
        btns.addStretch(1)
        btns.addWidget(close)
        btns.addWidget(self.apply_btn)
        lay.addLayout(btns)

        self.preview_btn.clicked.connect(self._preview)
        self.find_edit.returnPressed.connect(self._preview)
        self.all_btn.clicked.connect(lambda: self._check_all(Qt.CheckState.Checked))
        self.none_btn.clicked.connect(lambda: self._check_all(Qt.CheckState.Unchecked))
        self.apply_btn.clicked.connect(self._apply)
        self.undo_btn.clicked.connect(self._undo)
        close.clicked.connect(self.reject)

    # ---------- 规则 / 预览 ----------

    def rule(self) -> repl.ReplaceRule:
        return repl.ReplaceRule(
            find=self.find_edit.text(),
            repl=self.repl_edit.text(),
            regex=self.regex_box.isChecked(),
            case_sensitive=self.case_box.isChecked(),
            source=self.source_combo.currentData(),
            whole=self.whole_box.isChecked(),
        )

    def _preview(self) -> None:
        rule = self.rule()
        err = rule.validate()
        if err:
            warn(self, "规则不完整", err)
            return
        if rule.source == repl.SOURCE_ORIGINAL and rule.repl == rule.find:
            warn(self, "没有变化", "查找与替换内容相同，替换后不会有任何改动。")
            return
        self.items = repl.plan_scope(self.ctx, rule, hits=self.hits, entity_key=self.entity_key,
                                     limit=repl.PREVIEW_ROWS)
        self._fill_table()
        if not self.items:
            self.status.setText("没有命中（换个词试试，或确认范围选对了）")
            self.apply_btn.setEnabled(False)
            return
        self.status.setText(f"命中 {len(self.items)} 条"
                            + ("（已达预览上限，建议缩小范围）" if len(self.items) >= repl.PREVIEW_ROWS else ""))
        self.apply_btn.setEnabled(True)

    def _fill_table(self) -> None:
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.items))
        for r, item in enumerate(self.items):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(r, COL_CHECK, chk)
            label = QTableWidgetItem(item.label + ("　[已改过]" if item.custom_before is not None else ""))
            label.setToolTip(item.label)
            self.table.setItem(r, COL_LABEL, label)
            before = QTableWidgetItem(_one_line(item.current))
            before.setToolTip(item.current)
            self.table.setItem(r, COL_BEFORE, before)
            after = QTableWidgetItem(_one_line(item.after))
            after.setToolTip(item.after)
            self.table.setItem(r, COL_AFTER, after)

    def _check_all(self, state: Qt.CheckState) -> None:
        for r in range(self.table.rowCount()):
            self.table.item(r, COL_CHECK).setCheckState(state)

    def _checked(self) -> list[repl.ReplaceItem]:
        out = []
        for r, item in enumerate(self.items):
            it = self.table.item(r, COL_CHECK)
            if it is not None and it.checkState() == Qt.CheckState.Checked:
                out.append(item)
        return out

    # ---------- 应用 / 撤销 ----------

    def _apply(self) -> None:
        chosen = [i for i in self._checked() if i.after != i.current]
        if not chosen:
            warn(self, "没有可替换的条目", "请先预览，并至少勾选一条有变化的条目。")
            return
        ok, errors = repl.apply_items(self.ctx, chosen)
        if ok:
            self.ctx.save_profile()
            self.saved = True
        self.applied = list(chosen)
        self.undo_btn.setEnabled(True)
        text = f"已替换 {ok} 条，写进了方案。"
        if errors:
            text += f"\n失败 {len(errors)} 条：" + "\n".join(errors[:5])
        info(self, "替换完成", text, next_action="点主界面的「应用到游戏」才会生效。")
        self.status.setText(text.splitlines()[0])

    def _undo(self) -> None:
        if not self.applied:
            return
        n = repl.undo_items(self.ctx, self.applied)
        self.ctx.save_profile()
        self.applied = []
        self.undo_btn.setEnabled(False)
        info(self, "已撤销", f"这次批量替换的 {n} 条改动已还原。")


def _one_line(text: str, limit: int = 160) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def open_replace_dialog(parent, ctx, scope_label: str = "全库", hits=None,
                        entity_key: str | None = None) -> bool:
    """打开一键替换对话框，返回是否有改动被保存。"""
    dlg = ReplaceDialog(parent, ctx, scope_label=scope_label, hits=hits, entity_key=entity_key)
    safe_exec(dlg)
    return dlg.saved
