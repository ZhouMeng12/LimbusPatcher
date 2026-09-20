"""补译文件对话框：管理「零协包里没有、由本工具生成」的文件（如新章节剧情）。

能做：看清单 / 逐条启用停用 / 移除 / 打开目录 / 添加文件。
说明：启用中的补译文件会随「应用到游戏」写进副本包；停用后下次应用会从副本包移除。
     零协包里的同名文件永远优先，补译文件不会顶掉官方译文。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..supplement import validate_json_file
from .dialogs import confirm, info, safe_exec, warn

COL_ON, COL_REL, COL_RECORDS, COL_NOTE = range(4)


class SupplementDialog(QDialog):
    """补译文件管理。"""

    def __init__(self, parent, ctx):
        super().__init__(parent)
        self.ctx = ctx
        self.pack = ctx.supplement
        self.changed = False

        self.setWindowTitle("补译文件")
        self.resize(880, 520)
        lay = QVBoxLayout(self)
        head = QLabel("补译文件（零协包里没有的文件，例如还没汉化的新章节）")
        head.setObjectName("title")
        lay.addWidget(head)
        tip = QLabel(
            "· 启用中的文件会随「应用到游戏」写进副本包；停用后下次应用会把它从副本包移除。\n"
            "· 零协包里已有同名文件时以零协为准（补译文件不会顶掉官方译文，应用时会提示）。\n"
            "· 文件放在 <数据目录>/supplement/<零协包内的相对路径>，例如 supplement/StoryData/S1000B.json。"
        )
        tip.setObjectName("dim")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["启用", "文件（相对零协包）", "记录数", "说明"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_ON, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(COL_ON, 52)
        hh.setSectionResizeMode(COL_REL, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(COL_RECORDS, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(COL_RECORDS, 70)
        hh.setSectionResizeMode(COL_NOTE, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.table, 1)

        self.status = QLabel("")
        self.status.setObjectName("dim")
        lay.addWidget(self.status)

        btns = QHBoxLayout()
        self.add_btn = QPushButton("添加文件…")
        self.all_on = QPushButton("全部启用")
        self.all_off = QPushButton("全部停用")
        self.remove_btn = QPushButton("移除选中")
        self.open_btn = QPushButton("打开目录")
        close = QPushButton("关闭")
        btns.addWidget(self.add_btn)
        btns.addWidget(self.all_on)
        btns.addWidget(self.all_off)
        btns.addWidget(self.remove_btn)
        btns.addWidget(self.open_btn)
        btns.addStretch(1)
        btns.addWidget(close)
        lay.addLayout(btns)

        self.add_btn.clicked.connect(self._add)
        self.all_on.clicked.connect(lambda: self._set_all(True))
        self.all_off.clicked.connect(lambda: self._set_all(False))
        self.remove_btn.clicked.connect(self._remove)
        self.open_btn.clicked.connect(lambda: self._open_dir())
        close.clicked.connect(self.accept)
        self._reload()

    # ---------- 表格 ----------

    def _reload(self) -> None:
        files = self.pack.files()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.setRowCount(len(files))
        for row, f in enumerate(files):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Checked if f.enabled else Qt.CheckState.Unchecked)
            self.table.setItem(row, COL_ON, chk)
            rel_item = QTableWidgetItem(f.rel)
            rel_item.setToolTip(str(f.path))
            self.table.setItem(row, COL_REL, rel_item)
            self.table.setItem(row, COL_RECORDS, QTableWidgetItem(str(f.records)))
            self.table.setItem(row, COL_NOTE, QTableWidgetItem(f.note))
        self.table.blockSignals(False)
        total, on = self.pack.count()
        if not total:
            self.status.setText("还没有补译文件。可用「添加文件…」导入（文件名要与零协包内的相对路径一致，"
                                "例如 StoryData/S1000B.json）。")
        else:
            self.status.setText(f"共 {total} 个文件，{on} 个已启用；"
                                f"启用后点主界面「应用到游戏」才会写进副本包。")

    def _rel_at(self, row: int) -> str:
        item = self.table.item(row, COL_REL)
        return item.text() if item else ""

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != COL_ON:
            return
        rel = self._rel_at(item.row())
        if not rel:
            return
        on = item.checkState() == Qt.CheckState.Checked
        if self.pack.set_enabled(rel, on):
            self.changed = True
            self._reload()

    def _set_all(self, enabled: bool) -> None:
        n = self.pack.set_all_enabled(enabled)
        if n:
            self.changed = True
        self._reload()

    def _remove(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        rels = [self._rel_at(r) for r in rows if self._rel_at(r)]
        if not rels:
            warn(self, "没有选中", "先在上表里选一行（可多选）。")
            return
        if not confirm(self, "移除补译文件",
                       "将删除这些补译文件（" + "、".join(rels[:5]) + "…）以及它们在副本包里的副本。\n"
                       "文件本身的译文若没有别的备份就找不回来了。", ok_label="移除"):
            return
        for rel in rels:
            self.pack.remove(rel)
        self.changed = True
        self._reload()

    def _add(self) -> None:
        paths, _f = QFileDialog.getOpenFileNames(self, "选择要作为补译文件导入的 JSON", "", "JSON (*.json)")
        if not paths:
            return
        ok_n, bad = 0, []
        for raw in paths:
            src = Path(raw)
            ok, err = validate_json_file(src)
            if not ok:
                bad.append(f"{src.name}: {err}")
                continue
            rel = _guess_rel(src)
            if not rel:
                bad.append(f"{src.name}: 无法判断它在零协包里的位置（请把文件放到 StoryData/ 之类的目录下，"
                           f"或手动复制到 supplement/ 对应目录）")
                continue
            added, msg = self.pack.add(rel, src, note="手动添加")
            if added:
                ok_n += 1
            else:
                bad.append(msg)
        self.changed = bool(ok_n) or self.changed
        self._reload()
        text = f"已导入 {ok_n} 个补译文件。"
        if bad:
            text += "\n未导入：\n" + "\n".join(bad[:5])
        info(self, "导入补译文件", text, next_action="点「应用到游戏」后才会生效。")

    def _open_dir(self) -> None:
        self.pack.root.mkdir(parents=True, exist_ok=True)
        import os

        try:
            os.startfile(self.pack.root)  # type: ignore[attr-defined]
        except OSError:
            info(self, "打开目录", str(self.pack.root))


def _guess_rel(src: Path) -> str:
    """猜补译文件在零协包里的相对路径：优先用文件的父目录名（StoryData/xxx.json）。"""
    parent = src.parent.name
    if parent and parent.lower() not in ("", "zh", "out", "translate", "supplement"):
        return f"{parent}/{src.name}"
    return ""


def open_supplement_dialog(parent, ctx) -> bool:
    dlg = SupplementDialog(parent, ctx)
    safe_exec(dlg)
    return dlg.changed
