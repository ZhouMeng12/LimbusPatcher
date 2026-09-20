"""左侧导航：快捷入口 + 分组树（罪人→人格/E.G.O 二级结构）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from . import theme
from .. import categories as _categories
from ..categories import PSEUDO_CATEGORIES, SINNER_CODES

# 分类在导航中的显示名覆盖（避免与罪人树重名）
_NAV_LABELS: dict[str, str] = {"sinner": "罪人资料"}


class NavPanel(QWidget):
    category_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("分类与快捷入口")
        title.setObjectName("dim")
        layout.addWidget(title)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.itemClicked.connect(self._on_click)
        layout.addWidget(self.tree)
        self._cats: dict[str, QTreeWidgetItem] = {}

    def _make(self, text: str, key: str | None, bold: bool = False, color: str | None = None) -> QTreeWidgetItem:
        it = QTreeWidgetItem([text])
        if key is not None:
            it.setData(0, Qt.ItemDataRole.UserRole, key)
        f = it.font(0)
        f.setBold(bold)
        it.setFont(0, f)
        if color:
            it.setForeground(0, QColor(color))
        return it

    def _group_header(self, text: str) -> QTreeWidgetItem:
        it = self._make(text, None, bold=True, color=theme.ACCENT_DARK)
        it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        return it

    def set_counts(self, counts: dict[str, int], sinner_counts: dict[str, int] | None = None,
                   role_counts: dict[str, int] | None = None,
                   entity_counts: dict[str, int] | None = None) -> None:
        """counts: 分类 id → 文件数；sinner_counts: 罪人码 → 人格/EGO 文件数；
        role_counts: 实体角色 → 条目数；entity_counts: 实体种类 → 实体数。"""
        self.tree.clear()
        self._cats = {}
        for key, label in PSEUDO_CATEGORIES.items():
            it = self._make(f"  {label}", key, bold=True)
            self.tree.addTopLevelItem(it)
            self._cats[key] = it

        for gid, (g_label, members) in _categories.CATEGORY_GROUPS.items():
            header = self._group_header(g_label)
            self.tree.addTopLevelItem(header)
            if gid == "battle":
                # 图鉴与战斗组：只保留「人格图鉴」「敌方图鉴」两个入口
                it = self._make("    人格图鉴", "codex", bold=True)
                header.addChild(it)
                self._cats["codex"] = it
                it2 = self._make("    敌方图鉴", "enemy_codex", bold=True)
                header.addChild(it2)
                self._cats["enemy_codex"] = it2
                continue  # 其余项（罪人树 / 分类）不再放入本组
            for key in members:
                if gid == "story":
                    # 剧情组：所有子分类合并为一个"剧本模式"入口
                    if key == members[0]:
                        total = sum(counts.get(k, 0) for k in members)
                        it = self._make(f"    剧本模式  ({total})", "script", bold=True)
                        header.addChild(it)
                        self._cats["script"] = it
                    continue
                n = counts.get(key, 0)
                label = _NAV_LABELS.get(key, _categories.CATEGORIES[key])
                text = f"    {label}"
                if n:
                    text += f"  ({n})"
                it = self._make(text, key)
                header.addChild(it)
                self._cats[key] = it
            header.setExpanded(gid != "battle")

        self.tree.setCurrentItem(self._cats.get("all"))

    def _add_sinner_tree(self, parent: QTreeWidgetItem, counts: dict[str, int], sinner_counts: dict[str, int] | None) -> None:
        """罪人 → 人格/E.G.O 二级节点，并挂上跨罪人的实体入口。"""
        root = self._make(f"    罪人（{counts.get('identity', 0) + counts.get('ego', 0)} 文件）", "sinner:all", bold=True)
        parent.addChild(root)
        self._cats["sinner:all"] = root
        sinner_counts = sinner_counts or {}
        for code in sorted(SINNER_CODES, key=lambda c: int(c)):
            name = SINNER_CODES[code]
            n = sinner_counts.get(code, 0)
            node = self._make(f"        {name}{f'（{n}）' if n else ''}", f"sinner:{code}")
            root.addChild(node)
            self._cats[f"sinner:{code}"] = node
            node.addChild(self._make("            人格", f"sinner:{code}:identity"))
            node.addChild(self._make("            E.G.O", f"sinner:{code}:ego"))
            self._cats[f"sinner:{code}:identity"] = node.child(0)
            self._cats[f"sinner:{code}:ego"] = node.child(1)

    def _add_entity_entries(self, parent: QTreeWidgetItem, counts: dict[str, int],
                            entity_counts: dict[str, int] | None) -> None:
        """人格 / E.G.O 的实体入口：一览页 + 技能 / 剧情 / 语音跨罪人聚合。"""
        entity_counts = entity_counts or {}
        rows = [
            ("        人格一览", "entities:personality", entity_counts.get("personality", 0)),
            ("        人格技能", "role:identity_skill", counts.get("identity_skill", 0)),
            ("        人格剧情", "role:identity_story", counts.get("identity_story", 0)),
            ("        人格语音", "role:identity_voice", counts.get("identity_voice", 0)),
            ("        E.G.O 一览", "entities:ego", entity_counts.get("ego", 0)),
            ("        E.G.O 技能", "role:ego_skill", counts.get("ego_skill", 0)),
            ("        E.G.O 语音", "role:ego_voice", counts.get("ego_voice", 0)),
        ]
        for label, key, n in rows:
            it = self._make(label + (f"  ({n})" if n else ""), key)
            parent.addChild(it)
            self._cats[key] = it

    def set_current(self, key: str) -> None:
        it = self._cats.get(key)
        if it is not None:
            self.tree.setCurrentItem(it)

    def _on_click(self, item: QTreeWidgetItem, _column: int) -> None:
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key:
            self.category_selected.emit(key)
