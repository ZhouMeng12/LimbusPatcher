"""中间列表：搜索框 + 动态筛选 + 结果模型/委托（高亮、右键、键盘导航）。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPointF, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QClipboard,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
    QTextCharFormat,
    QTextLayout,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .. import categories as _categories
from ..categories import category_label
from ..search import SCOPE_LABELS, SearchHit

STATUS_UNMODIFIED = "unmodified"
STATUS_MODIFIED = "modified"
STATUS_PENDING = "pending"
STATUS_MISSING = "missing"

_STATUS_LABELS = {
    STATUS_UNMODIFIED: "未修改",
    STATUS_MODIFIED: "已修改",
    STATUS_PENDING: "待确认",
    STATUS_MISSING: "已失效",
}
_STATUS_TOKENS = {
    STATUS_UNMODIFIED: "STATUS_NONE",
    STATUS_MODIFIED: "ACCENT",
    STATUS_PENDING: "WARNING",
    STATUS_MISSING: "ERROR",
}


def status_color(status: str) -> QColor:
    """状态色 = 左侧 2px 色条的颜色。

    必须**按当前主题实时解析**：模块级缓存在换主题后会留下旧主题的颜色
    （切换主题只重建窗口，不重载模块）。
    """
    return QColor(getattr(theme, _STATUS_TOKENS.get(status, "STATUS_NONE")))

# 章节/赛季/种类筛选的显示场景
_CHAPTER_CATS = {"main_story", "event", "railway", "mirror"}
_SEASON_CATS = {"identity", "ego"}


@dataclass
class HitView:
    hit: SearchHit
    status: str = STATUS_UNMODIFIED
    favorite: bool = False
    custom: str | None = None
    dup_count: int = 1
    english_hit: bool = False  # 命中来自英文基线（列表里显示「英文命中」标记）
    role_label: str = ""  # 实体角色徽标（技能/剧情/语音/本体）
    header: str = ""      # 非空 = 分组标题行（人格一览按赛季/获取方式分组时插入）

    @property
    def is_header(self) -> bool:
        return bool(self.header)


class EntryListModel(QAbstractListModel):
    """hit 列表模型。data() 直接返回 HitView（Qt.UserRole）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hits: list[HitView] = []
        self._highlight = ""

    def set_hits(self, hits: list[HitView]) -> None:
        self.beginResetModel()
        self._hits = hits
        self.endResetModel()

    def set_highlight(self, text: str) -> None:
        self._highlight = text
        self.layoutChanged.emit()

    @property
    def highlight(self) -> str:
        return self._highlight

    def hits(self) -> list[HitView]:
        """当前列表里的全部行（一键替换的「当前列表」范围用）。"""
        return list(self._hits)

    def hit_at(self, row: int) -> HitView | None:
        if 0 <= row < len(self._hits):
            return self._hits[row]
        return None

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._hits)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._hits)):
            return None
        if role == Qt.ItemDataRole.UserRole:
            return self._hits[index.row()]
        return None


def _draw_rich_text(painter: QPainter, rect: QRect, text: str, font: QFont, base: QColor, hl: QColor, hl_word: str) -> None:
    """绘制单行文本，命中词用强调色高亮。"""
    text = text.replace("\n", " ")
    fm = QFontMetrics(font)
    text = fm.elidedText(text, Qt.TextElideMode.ElideRight, rect.width())
    if not hl_word:
        painter.setFont(font)
        painter.setPen(base)
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        return
    layout = QTextLayout(text, font)
    layout.setCacheEnabled(True)
    fmt = QTextCharFormat()
    fmt.setForeground(hl)
    fmt.setFontWeight(QFont.Weight.Bold)
    ranges = []
    for m in re.finditer(re.escape(hl_word), text, re.IGNORECASE):
        fr = QTextLayout.FormatRange()
        fr.start = m.start()
        fr.length = m.end() - m.start()
        fr.format = fmt
        ranges.append(fr)
    if ranges:
        layout.setFormats(ranges)
    layout.beginLayout()
    y = rect.top() + (rect.height() - fm.height()) / 2
    line = layout.createLine()
    line.setLineWidth(rect.width())
    layout.endLayout()
    painter.save()
    painter.setPen(base)
    layout.draw(painter, QPointF(rect.left(), y))
    painter.restore()


class EntryDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        view = index.data(Qt.ItemDataRole.UserRole)
        if view is not None and getattr(view, "is_header", False):
            return QSize(0, 30)
        return QSize(0, 44)

    def paint(self, painter: QPainter, option, index) -> None:
        hit: HitView = index.data(Qt.ItemDataRole.UserRole)
        if hit is not None and hit.is_header:
            self._paint_header(painter, option, hit)
            return
        rect: QRect = option.rect.adjusted(0, 1, 0, -1)  # 2px 行间隔
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(rect, QColor(theme.SELECTION))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, QColor(theme.HOVER))

        # 左侧 2px 状态色条（原型 .row::before）：上下各内缩 5px。
        bar = QColor(theme.ACCENT) if selected else status_color(hit.status)
        if hit.favorite:
            bar = QColor(theme.ACCENT)
        painter.fillRect(QRect(rect.left(), rect.top() + 5, 2, max(0, rect.height() - 10)), bar)

        text = hit.custom if hit.custom is not None else hit.hit.text
        meta_parts = [category_label(hit.hit.category)]
        if hit.hit.chapter:
            meta_parts.append(hit.hit.chapter)
        if hit.hit.character:
            meta_parts.append(hit.hit.character)
        if hit.hit.season_label:
            s = hit.hit.season_label
            if hit.hit.acq_label:
                s += f"·{hit.hit.acq_label}"
            meta_parts.append(s)
        if hit.hit.kind_label:
            meta_parts.append(hit.hit.kind_label)
        if getattr(hit.hit, "source", "llc") == "supplement":
            meta_parts.append("补译")
        if hit.english_hit:
            meta_parts.append("英文命中")
        if hit.dup_count > 1:
            meta_parts.append(f"重复 {hit.dup_count} 处")
        if hit.favorite:
            meta_parts.append("★ 收藏")
        # 状态文字并入 meta 行（原型 .row .m 的写法），不再单独占右侧
        meta_parts.append(_STATUS_LABELS[hit.status])
        meta = " · ".join(meta_parts)

        # 文本区：左边距 11px（= 2px 色条 + 9px 间隔，对应原型 padding-left:11px）
        left = rect.left() + 11
        right_pad = 10
        width = rect.width() - 11 - right_pad

        name_font = QFont(option.font)
        meta_font = QFont(option.font)
        meta_font.setPointSizeF(max(8.0, option.font.pointSizeF() - 1.5))
        name_fm = QFontMetrics(name_font)

        # 角色胶囊徽标（原型 .row .t .rl）：先给徽标留位，再把标题按剩余宽度省略
        role = hit.role_label or ""
        badge_w = (name_fm.horizontalAdvance(role) + 14) if role else 0
        title_w = width - (badge_w + 6 if badge_w else 0)

        model = index.model()
        hl_word = model.highlight if isinstance(model, EntryListModel) else ""
        _draw_rich_text(painter, QRect(left, rect.top() + 4, max(10, title_w), 20),
                        text, name_font, QColor(theme.TEXT), QColor(theme.ACCENT), hl_word)

        if role:
            plain = name_fm.elidedText(text.replace("\n", " "), Qt.TextElideMode.ElideRight, max(10, title_w))
            bx = left + name_fm.horizontalAdvance(plain) + 6
            self._paint_badge(painter, bx, rect.top() + 5, role, name_font)

        painter.setFont(meta_font)
        painter.setPen(QColor(theme.TEXT_DIM))
        meta_rect = QRect(left, rect.top() + 25, width, 17)
        meta_elided = QFontMetrics(meta_font).elidedText(meta, Qt.TextElideMode.ElideRight, meta_rect.width())
        painter.drawText(meta_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, meta_elided)

    def _paint_badge(self, painter: QPainter, x: int, y: int, text: str, base_font: QFont) -> None:
        """角色胶囊徽标：s3 底 + 描边 + 全圆头 + 10px 字。"""
        font = QFont(base_font)
        font.setPointSizeF(max(7.5, base_font.pointSizeF() - 2.0))
        font.setBold(True)
        fm = QFontMetrics(font)
        w = fm.horizontalAdvance(text) + 10
        h = 15
        box = QRect(x, y, w, h)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.setBrush(QColor(theme.SURFACE_3))
        radius = int(theme.RADIUS_PILL)
        radius = h // 2 if radius > h else max(0, radius)
        painter.drawRoundedRect(box, radius, radius)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT_DIM))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


    def _paint_header(self, painter: QPainter, option, hit: HitView) -> None:
        """分组标题：左侧色条 + 强调色粗体（不可点击、没有状态点）。"""
        rect: QRect = option.rect
        painter.fillRect(rect, QColor(theme.HOVER))
        painter.fillRect(QRect(rect.left(), rect.top() + 5, 3, rect.height() - 10), QColor(theme.ACCENT))
        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(theme.ACCENT))
        painter.drawText(rect.adjusted(14, 0, -12, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         QFontMetrics(font).elidedText(hit.header, Qt.TextElideMode.ElideRight,
                                                       rect.width() - 26))


class ListPanel(QFrame):
    """中间：搜索 / 筛选 / 条目列表。

    继承 ``QFrame``（而不是 ``QWidget``）是有意的：``theme.QSS`` 里面板的样式
    规则是 ``QFrame#panel``，纯 ``QWidget`` 子类**不会**套用背景/描边/圆角
    （Qt 的样式表只对会自绘背景的控件生效）。改成 QFrame 后它才真的是一张卡片。
    """

    search_requested = Signal(str)  # text
    filters_changed = Signal()
    hit_activated = Signal(object)  # HitView
    favorite_requested = Signal(object, bool)  # (ref, favorite)
    source_requested = Signal(object)  # ref
    batch_restore_requested = Signal(list)  # [ref]（多选：批量还原为原文）
    batch_favorite_requested = Signal(list, bool)  # ([ref], favorite)（多选：批量收藏）
    entity_requested = Signal(str)  # entity_key（实体一览里「查看该实体」）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索原文 / 英文 / 自定义文本 / KeyID（范围可选）…")
        self.search_edit.setClearButtonEnabled(True)

        # 人格/E.G.O 实体选择器 + 内容类型（仅在实体上下文里显示）
        self.entity_combo = QComboBox()
        self.entity_combo.setMinimumWidth(210)
        self.entity_combo.setToolTip("选择人格 / E.G.O（按罪人与游戏内序号排列）")
        self.entity_combo.hide()
        self.content_combo = QComboBox()
        self.content_combo.setMinimumWidth(96)
        self.content_combo.setToolTip("查看该实体的：本体 / 技能 / 剧情 / 语音")
        self.content_combo.hide()

        self.scope_combo = QComboBox()
        self.scope_combo.setFixedWidth(104)
        self.scope_combo.setToolTip("搜索范围：原文（零协）/ 英文（游戏基线）/ 自定义 / 全部")
        for key, label in SCOPE_LABELS.items():
            self.scope_combo.addItem(label, key)

        row1 = QHBoxLayout()
        self.status_combo = QComboBox()
        self.status_combo.addItem("全部状态", "")
        for key, label in _STATUS_LABELS.items():
            self.status_combo.addItem(label, key)
        self.status_combo.addItem("收藏", "favorite")
        self.category_combo = QComboBox()
        self.category_combo.addItem("全部分类", "all")
        for key, label in _categories.CATEGORIES.items():
            self.category_combo.addItem(label, key)
        row1.addWidget(self.search_edit, 3)
        row1.addWidget(self.scope_combo)
        row1.addWidget(self.status_combo, 1)
        row1.addWidget(self.category_combo, 1)

        row2 = QHBoxLayout()
        self.chapter_combo = QComboBox()
        self.chapter_combo.addItem("全部章节", "")
        self.level_combo = QComboBox()
        self.level_combo.addItem("全部关卡", "")
        self.season_combo = QComboBox()
        self.season_combo.addItem("全部赛季", "")
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("全部种类", "")
        # 人格/EGO 一览的分组方式（仅「全部」时可见）
        self.group_combo = QComboBox()
        self.group_combo.setMinimumWidth(104)
        self.group_combo.setToolTip("把人格 / E.G.O 一览按赛季或获取方式分组显示")
        for key, label in (("", "不分组"), ("season", "按赛季"), ("acq", "按获取方式")):
            self.group_combo.addItem(label, key)
        self.group_combo.hide()
        row2.addWidget(self.group_combo)
        row2.addWidget(self.entity_combo)
        row2.addWidget(self.content_combo)
        row2.addWidget(self.chapter_combo, 1)
        row2.addWidget(self.level_combo, 1)
        row2.addWidget(self.season_combo, 1)
        row2.addWidget(self.kind_combo, 1)

        self.count_label = QLabel("")
        self.count_label.setObjectName("dim")

        self.view = QListView()
        self.view.setUniformItemSizes(True)
        # 多选：Ctrl/Shift 选多条后可右键批量还原/收藏（见 _batch_menu）
        self.view.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        self.view.setItemDelegate(EntryDelegate(self.view))
        self.view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self.search_edit)
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addWidget(self.count_label)
        layout.addWidget(self.view, 1)

        self.model = EntryListModel(self)
        self.view.setModel(self.model)
        self.view.selectionModel().currentChanged.connect(self._on_current_changed)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(lambda: self.search_requested.emit(self.search_edit.text()))
        self.search_edit.textChanged.connect(lambda _t: self._debounce.start())
        for combo in (self.status_combo, self.category_combo,
                      self.chapter_combo, self.level_combo, self.season_combo, self.kind_combo,
                      self.group_combo):
            combo.currentIndexChanged.connect(lambda *_a: self.filters_changed.emit())

    # ---- 取值 ----

    def set_entities(self, entities: list[dict], current: str | None = None,
                     all_label: str = "全部") -> None:
        """填充人格/E.G.O 选择器；第一项是「全部」（data 为空串）。"""
        self.entity_combo.blockSignals(True)
        self.entity_combo.clear()
        if entities:
            self.entity_combo.addItem(f"{all_label}（{len(entities)}）", "")
        for e in entities or []:
            seq = e.get("seq") or 0
            title = (e.get("title") or "").replace(chr(10), " ")
            label = f"{e.get('name') or ''} · 第{seq}" + (f"（{title}）" if title else "")
            self.entity_combo.addItem(label, e.get("entity_key"))
        idx = self.entity_combo.findData(current) if current else 0
        self.entity_combo.setCurrentIndex(max(idx, 0))
        self.entity_combo.blockSignals(False)
        self.entity_combo.setVisible(bool(entities))

    def current_entity(self) -> str | None:
        data = self.entity_combo.currentData() if self.entity_combo.isVisible() else None
        return data or None  # 空串 = 「全部」

    def set_contents(self, choices: list[tuple[str, str]], current: str | None = None) -> None:
        self.content_combo.blockSignals(True)
        self.content_combo.clear()
        for key, label in choices or []:
            self.content_combo.addItem(label, key)
        idx = self.content_combo.findData(current) if current else 0
        self.content_combo.setCurrentIndex(max(idx, 0))
        self.content_combo.blockSignals(False)
        self.content_combo.setVisible(bool(choices))

    def current_content(self) -> str:
        return (self.content_combo.currentData() or "all") if self.content_combo.isVisible() else "all"

    def set_entity_context(self, entities: list[dict] | None, choices: list[tuple[str, str]] | None,
                           entity: str | None = None, content: str | None = None,
                           all_label: str = "全部") -> None:
        """一次性设置实体上下文（entities 为空则隐藏两个下拉）。"""
        if entities:
            self.set_entities(entities, entity, all_label)
            self.set_contents(choices or [("all", "全部")], content)
            return
        for combo in (self.entity_combo, self.content_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.blockSignals(False)
            combo.hide()

    def current_scope(self) -> str:
        return self.scope_combo.currentData() or "original"

    def set_scope(self, scope: str) -> None:
        idx = self.scope_combo.findData(scope)
        self.scope_combo.blockSignals(True)
        self.scope_combo.setCurrentIndex(max(idx, 0))
        self.scope_combo.blockSignals(False)

    def current_category(self) -> str:
        return self.category_combo.currentData() or "all"

    def current_chapter(self) -> str:
        return self.chapter_combo.currentData() or ""

    def current_level(self) -> str:
        return self.level_combo.currentData() or ""

    def current_season(self) -> str:
        return self.season_combo.currentData() or ""

    def current_kind(self) -> str:
        return self.kind_combo.currentData() or ""

    def current_group(self) -> str:
        """当前分组方式（只在实体一览里生效；显隐由主界面控制，这里不受可见性影响）。"""
        return self.group_combo.currentData() or ""

    def current_status(self) -> str:
        return self.status_combo.currentData() or ""

    # ---- 数据填充 ----

    def set_hits(self, hits: list[HitView], truncated: bool = False, note: str = "") -> None:
        """note：分组 / 标注进度等附加说明（跟在条数后面）。分组标题行不计入条数。"""
        self.model.set_hits(hits)
        n = sum(1 for v in hits if not getattr(v, "is_header", False))
        extra = f"　·　{note}" if note else ""
        headers = len(hits) - n
        extra += f"　·　{headers} 个分组标题" if headers else ""
        if truncated:
            self.count_label.setText(f"共显示 {n} 条（已达上限，请细化关键词或筛选）{extra}")
        elif not n:
            self.count_label.setText("未找到匹配文本 —— 可清除筛选或放宽关键词")
        else:
            self.count_label.setText(f"共 {n} 条{extra}")

    def set_chapters(self, chapters: list[tuple[str, str]]) -> None:
        self._refill(self.chapter_combo, "全部章节", chapters)

    def set_levels(self, levels: list[tuple[str, str]]) -> None:
        self._refill(self.level_combo, "全部关卡", levels)

    def set_seasons(self, seasons: list[tuple[str, str]]) -> None:
        self._refill(self.season_combo, "全部赛季", seasons)

    def set_kinds(self, kinds: list[tuple[str, str]]) -> None:
        self._refill(self.kind_combo, "全部种类", kinds)

    def set_filter_visibility(self, category_key: str) -> None:
        """按导航场景动态显隐第二排筛选。"""
        cat = category_key
        if cat.startswith("sinner:"):
            parts = cat.split(":")
            if len(parts) > 2:
                cat = parts[2]
            else:
                cat = "identity"  # 罪人节点默认人格/EGO 场景
        chapter_ok = cat in _CHAPTER_CATS or cat == "all"
        season_ok = cat in _SEASON_CATS
        kind_ok = cat == "enemy"
        self.chapter_combo.setVisible(chapter_ok)
        self.level_combo.setVisible(chapter_ok)
        self.season_combo.setVisible(season_ok)
        self.kind_combo.setVisible(kind_ok)
        self.group_combo.setVisible(False)  # 默认隐藏，由主界面在实体一览里打开

    def _refill(self, combo: QComboBox, first_label: str, items: list[tuple[str, str]]) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(first_label, "")
        for key, label in items:
            combo.addItem(label, key)
        idx = combo.findData(current)
        combo.setCurrentIndex(max(idx, 0))
        combo.blockSignals(False)

    # ---- 交互 ----

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        hit = current.data(Qt.ItemDataRole.UserRole)
        if hit is not None and not hit.is_header:  # 分组标题不可激活
            self.hit_activated.emit(hit)

    def selected_hits(self) -> list:
        """当前选中的条目（多选时按行号排序）。"""
        rows = sorted(i.row() for i in self.view.selectionModel().selectedRows())
        out = []
        for row in rows:
            view = self.model.hit_at(row)
            if view is not None and not view.is_header:
                out.append(view)
        return out

    def _on_context_menu(self, pos) -> None:
        index = self.view.indexAt(pos)
        hit = index.data(Qt.ItemDataRole.UserRole)
        if hit is None or hit.is_header:
            return
        selection = self.selected_hits()
        if len(selection) > 1 and any(v is hit for v in selection):
            self._batch_menu(selection, pos)  # 右键落在多选范围内 → 批量菜单
            return
        menu = QMenu(self)
        act_entity = None
        if getattr(hit, "role", "") in ("identity", "ego") and getattr(hit, "entity_key", None):
            act_entity = menu.addAction("查看该人格 / E.G.O 的全部内容")
            menu.addSeparator()
        act_copy = menu.addAction("复制文本")
        act_open = menu.addAction("在编辑器中打开")
        act_fav = menu.addAction("★ 收藏" if hit.favorite else "☆ 收藏")
        act_src = menu.addAction("显示来源文件")
        chosen = menu.exec(self.view.mapToGlobal(pos))
        if act_entity is not None and chosen is act_entity and hit.entity_key:
            self.entity_requested.emit(str(hit.entity_key))
        elif chosen is act_copy:
            QApplication.clipboard().setText(hit.custom if hit.custom is not None else hit.hit.text)
        elif chosen is act_open:
            self.hit_activated.emit(hit)
        elif chosen is act_fav:
            self.favorite_requested.emit(hit.hit.ref, not hit.favorite)
        elif chosen is act_src:
            self.source_requested.emit(hit.hit.ref)

    def _batch_menu(self, selection: list, pos) -> None:
        """多选批量操作：还原为原文 / 收藏 / 取消收藏 / 复制。"""
        n = len(selection)
        modified = [v for v in selection if v.custom is not None]
        menu = QMenu(self)
        act_restore = menu.addAction(f"批量还原为原文（{len(modified)} / {n} 条已修改）")
        act_restore.setEnabled(bool(modified))
        menu.addSeparator()
        act_fav = menu.addAction(f"批量加入收藏（{n} 条）")
        act_unfav = menu.addAction(f"批量取消收藏（{n} 条）")
        menu.addSeparator()
        act_copy = menu.addAction(f"复制这 {n} 条文本")
        chosen = menu.exec(self.view.mapToGlobal(pos))
        if chosen is act_restore:
            self.batch_restore_requested.emit([v.hit.ref for v in modified])
        elif chosen is act_fav:
            self.batch_favorite_requested.emit([v.hit.ref for v in selection], True)
        elif chosen is act_unfav:
            self.batch_favorite_requested.emit([v.hit.ref for v in selection], False)
        elif chosen is act_copy:
            lines = [(v.custom if v.custom is not None else v.hit.text) for v in selection]
            QApplication.clipboard().setText("\n".join(lines))
