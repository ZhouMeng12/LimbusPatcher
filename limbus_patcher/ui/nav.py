"""左侧导航：工作台 + 原版界面分区。

改版要点（DESIGN_SYSTEM.md §5）
------------------------------
1. **信息架构重排**：按《边狱巴士》原版的界面结构分区 —— 剧院 / 镜牢 / 人格 /
   E.G.O / RPG 剧情 / 关卡与敌人 / 系统与设置（见 ``categories.NAV_ZONES``）。
2. **工作台置顶**：全部文本 / 最近修改 / 待确认 / 我的收藏 / 补译文本，
   跨分区的任务入口集中在一处。
3. **补齐可达性**：改版前「图鉴与战斗」「剧情」两组只露出了 人格图鉴 / 敌方图鉴 /
   剧本模式，人格、E.G.O、技能、镜牢、异想体等十几类**在导航里根本点不到**
   （只能从列表的分类下拉里找）。现在全部可达。
4. **分区默认收起**：只展开「工作台」，先让用户扫分区名；选中条目时自动展开
   其所属分区。

信号与键值保持兼容：仍然只发 ``category_selected(key)``。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from . import theme
from .. import categories as _categories

#: 分区在导航中的显示名覆盖（避免与分区名或其它入口重名）
_NAV_LABELS: dict[str, str] = {"sinner": "罪人资料"}


class NavPanel(QFrame):
    """左侧：工作台 + 原版分区导航。

    继承 ``QFrame`` 而不是 ``QWidget``：``theme.QSS`` 的面板规则是
    ``QFrame#panel``，纯 ``QWidget`` 子类拿不到背景/描边/圆角。
    """

    category_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
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
        #: 每次 set_counts 后缓存，供面包屑/测试查询
        self._zone_headers: dict[str, QTreeWidgetItem] = {}

    # ---------- 构件 ----------

    def _make(self, text: str, key: str | None, bold: bool = False,
              color: str | None = None) -> QTreeWidgetItem:
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
        it = self._make(text, None, bold=True, color=theme.ACCENT)
        it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        return it

    def _count_for(self, key: str, counts: dict[str, int],
                   role_counts: dict[str, int] | None,
                   entity_counts: dict[str, int] | None) -> int:
        """按导航键取计数。虚拟入口（role:/entities:）与「剧本模式」另行汇总。"""
        if key == "script":
            return sum(counts.get(k, 0) for k in _categories.STORY_MEMBER_KEYS)
        if key.startswith("role:"):
            return (role_counts or {}).get(key.split(":", 1)[1], 0)
        if key.startswith("entities:"):
            return (entity_counts or {}).get(key.split(":", 1)[1], 0)
        return counts.get(key, 0)

    def _leaf(self, parent: QTreeWidgetItem, key: str, label: str,
              counts: dict[str, int], role_counts, entity_counts) -> QTreeWidgetItem:
        label = _NAV_LABELS.get(key, label)
        n = self._count_for(key, counts, role_counts, entity_counts)
        text = f"    {label}" + (f"  ({n:,})" if n else "")
        it = self._make(text, key)
        parent.addChild(it)
        self._cats[key] = it
        return it

    # ---------- 数据 ----------

    def set_counts(self, counts: dict[str, int], sinner_counts: dict[str, int] | None = None,
                   role_counts: dict[str, int] | None = None,
                   entity_counts: dict[str, int] | None = None) -> None:
        """counts: 分类 id → 文件数；sinner_counts: 罪人码 → 人格/EGO 文件数；
        role_counts: 实体角色 → 条目数；entity_counts: 实体种类 → 实体数。"""
        del sinner_counts  # 罪人下拉已并入「人格」分区的「人格一览」实体视图
        self.tree.clear()
        self._cats = {}
        self._zone_headers = {}

        # 工作台（置顶）
        head = self._group_header("工作台")
        self.tree.addTopLevelItem(head)
        self._zone_headers["workbench"] = head
        for key, label in _categories.NAV_WORKBENCH:
            self._leaf(head, key, label, counts, role_counts, entity_counts)
        head.setExpanded(True)

        # 六个原版分区 + RPG 剧情
        for zid, zlabel, leaves in _categories.NAV_ZONES:
            zhead = self._group_header(zlabel)
            self.tree.addTopLevelItem(zhead)
            self._zone_headers[zid] = zhead
            for key, label in leaves:
                self._leaf(zhead, key, label, counts, role_counts, entity_counts)
            zhead.setExpanded(zid in _categories.NAV_DEFAULT_EXPANDED)

        self.tree.setCurrentItem(self._cats.get("all"))

    def zone_label_of(self, key: str) -> str:
        """导航键所属分区名（面包屑用）。"""
        found = _categories.nav_zone_of(key)
        return found[0] if found else ""

    def set_current(self, key: str) -> None:
        it = self._cats.get(key)
        if it is not None:
            self.tree.setCurrentItem(it)
            parent = it.parent()
            if parent is not None:
                parent.setExpanded(True)  # 展开所在分区，避免选中了却看不见

    def _on_click(self, item: QTreeWidgetItem, _column: int) -> None:
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key:
            self.category_selected.emit(key)
