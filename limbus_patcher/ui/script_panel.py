"""剧本模式面板：说话人左 · 文本右长条 · 场景行 · ruby 注音 + 富文本自绘 · 点行编辑。

由 main_window 在主线剧情场景下替换中间列表；点某行回到右侧编辑器。
显示按零协原文渲染（颜色 / 字号 / 高亮底 / 粗体 / 下划线 / 斜体 / 注音），
但控件持有与编辑框一致的原始文本，标签一个都不丢。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import richtext
from . import theme

_RUBY_RE = re.compile(r"<ruby=([^>]*)>([^<]*)</ruby>")

# 键盘焦点行的强调样式：整行换底色 + 左侧强调色竖条
_FOCUSED_QSS = (
    f"QFrame#panel {{ background: {theme.SELECTION}; border: 1px solid {theme.ACCENT_DARK};"
    f" border-left: 3px solid {theme.ACCENT}; border-radius: 6px; }}"
)

_KEY_HINT = ("↑/↓ 移动焦点 · Enter 打开或建立对应 · S 标记跳过 · Delete 删除该行 · "
             "Ctrl+↑/↓ 上一条/下一条未对齐；右键可批量对应 / 删除")


def parse_ruby(text: str) -> list[tuple]:
    """text → [(kind, reading, base)]；kind: 'plain'|'ruby'。

    ruby 标签保留为注音；其余游戏富文本标签（<color=…>/<i>/<size=…> 等）从显示文本中去除。
    """
    out: list[tuple] = []
    pos = 0
    for m in _RUBY_RE.finditer(text):
        if m.start() > pos:
            plain = re.sub(r"<[^>]*>", "", text[pos : m.start()])
            if plain:
                out.append(("plain", "", plain))
        out.append(("ruby", m.group(1), m.group(2)))
        pos = m.end()
    if pos < len(text):
        plain = re.sub(r"<[^>]*>", "", text[pos:])
        if plain:
            out.append(("plain", "", plain))
    if not out:
        plain = re.sub(r"<[^>]*>", "", text)
        out.append(("plain", "", plain))
    return out


def measure_ruby_width(segments: list[tuple], base_font: QFont) -> int:
    fm = QFontMetrics(base_font)
    return sum(fm.horizontalAdvance(b) for _k, _r, b in segments)


@dataclass
class _Span:
    """自绘用的一段文本：正文 + 注音 + 折算后的样式（颜色 / 字号 / 底色 / 粗体…）。

    无格式标签时用 parse_ruby 的结果构造（行为与旧版一致），
    有格式时用 richtext.parse + effective_style 折算（见 _spans_from_richtext）。
    """

    kind: str = "plain"            # plain | ruby
    reading: str = ""              # ruby 注音读法
    text: str = ""                 # 正文本体
    color: str | None = None       # 文字色 #rrggbb
    size_percent: float | None = None   # 字号百分比
    background: str | None = None  # 底色（<mark>）
    bold: bool = False
    underline: bool = False
    italic: bool = False
    strike: bool = False


def _spans_from_plain(text: str) -> list[_Span]:
    """无格式标签的快路径：沿用 parse_ruby（渲染结果与旧版完全一致）。"""
    return [_Span(kind=k, reading=r, text=b) for k, r, b in parse_ruby(text)]


def _spans_from_richtext(text: str) -> list[_Span]:
    """richtext.parse 的结果 → 自绘片段（富文本样式已折算成具体值）。"""
    spans: list[_Span] = []
    for seg in richtext.parse(text):
        style = richtext.effective_style(seg)
        spans.append(_Span(
            kind="ruby" if seg.kind == "ruby" else "plain",
            reading=seg.reading,
            text=seg.text,
            color=style.color,
            size_percent=style.size_percent,
            background=style.background,
            bold=style.bold,
            underline=style.underline,
            italic=style.italic,
            strike=style.strike,
        ))
    return spans


class RubyTextWidget(QWidget):
    """自绘文本：ruby 注音（正文上方小字）+ 游戏富文本格式，自动换行。

    - ruby：沿用自绘注音，注音小字画在正文字上方（网页样式）；
    - color / size / mark / b / u / i / s：按 richtext 解析结果逐段设置画笔颜色与字体，
      <mark> 先铺一层底色；
    - 没有格式标签（richtext.has_format 为假）时走 parse_ruby 老路径，渲染与旧版一致；
    - 控件里的 text() 始终是零协原始文本（标签不丢），显示与存储彻底分开。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._spans: list[_Span] = []
        self._text = ""
        self._color = theme.TEXT
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy().Expanding)

    def set_text(self, text: str, color: str | None = None) -> None:
        self._text = text or ""
        self._color = color or theme.TEXT
        # 只要有 '<' 就走 richtext 解析：它认得游戏标签，也会把「认不出的 <...>」原样当文字。
        # 旧的 parse_ruby 快路径用 `<[^>]*>` 一概删除，会把但丁的内心台词（<……那就向大海去吧……>）
        # 整段吃掉 —— 文本不显示，控件高度还会一起塌掉，整行跟着点不中。
        self._spans = (_spans_from_richtext(self._text) if "<" in self._text
                       else _spans_from_plain(self._text))
        if not self._spans:  # 兜底：任何情况下都留一个空片段，别让高度算成 0
            self._spans = [_Span(kind="plain", reading="", text="")]
        self.updateGeometry()
        self.update()

    def text(self) -> str:
        return self._text

    # ---------- 字体与排版 ----------

    def _ruby_font(self) -> QFont:
        """注音小字：正文的 62%（不低于 7pt）。"""
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, self.font().pointSizeF() * 0.62))
        return font

    def _font_for(self, span: _Span) -> QFont:
        """按片段样式算字体：在当前字体上叠加，保留外部设置（如已删除行的删除线）。"""
        font = QFont(self.font())
        if span.size_percent:
            base = self.font().pointSizeF()
            if base > 0:
                font.setPointSizeF(max(7.0, base * span.size_percent / 100.0))
        font.setBold(font.bold() or span.bold)
        font.setUnderline(font.underline() or span.underline)
        font.setItalic(font.italic() or span.italic)
        font.setStrikeOut(font.strikeOut() or span.strike)
        return font

    def _line_height(self, line: list[_Span]) -> int:
        if not line:
            return QFontMetrics(self.font()).height()
        return max(QFontMetrics(self._font_for(s)).height() for s in line)

    def _wrap(self, width: int) -> list[list[_Span]]:
        lines: list[list[_Span]] = [[]]
        cur = 0
        for span in self._spans:
            w = QFontMetrics(self._font_for(span)).horizontalAdvance(span.text)
            if cur > 0 and cur + w > width:
                lines.append([])
                cur = 0
            lines[-1].append(span)
            cur += w
        return lines

    def sizeHint(self) -> QSize:
        margin = 4
        ruby_h = QFontMetrics(self._ruby_font()).height()
        lines = self._wrap(max(80, self.width() - margin * 2)) if self.width() > 60 else [list(self._spans)]
        h = margin * 2
        for line in lines:
            h += self._line_height(line)
            if any(s.kind == "ruby" and s.reading for s in line):
                h += ruby_h
        return QSize(200, max(24, h))

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ruby_font = self._ruby_font()
        ruby_h = QFontMetrics(ruby_font).height()
        margin = 4
        top = margin
        for line in self._wrap(max(40, self.width() - margin * 2)):
            fonts = [self._font_for(s) for s in line]
            metrics = [QFontMetrics(f) for f in fonts]
            asc = max((fm.ascent() for fm in metrics), default=QFontMetrics(self.font()).ascent())
            desc = max((fm.descent() for fm in metrics), default=QFontMetrics(self.font()).descent())
            # ruby 段需要把整行抬升注音的高度
            rise = ruby_h if any(s.kind == "ruby" and s.reading for s in line) else 0
            baseline = top + rise + asc
            x = margin
            for span, font, fm in zip(line, fonts, metrics):
                w = fm.horizontalAdvance(span.text)
                if span.background:  # <mark>：先铺底色再写字
                    painter.fillRect(QRect(x, baseline - asc, w, asc + desc), QColor(span.background))
                if span.kind == "ruby" and span.reading:
                    painter.setFont(ruby_font)
                    painter.setPen(QColor(theme.TEXT_DIM))
                    painter.drawText(QRect(x, baseline - asc, w, rise + asc),
                                     Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                                     span.reading)
                painter.setFont(font)
                painter.setPen(QColor(span.color or self._color))
                painter.drawText(x, baseline, span.text)
                x += w
            top = baseline + desc
        painter.end()


class ScriptLineRow(QFrame):
    """一行对话。item 为剧本 items 里的原始 dict（用于建立对应/批量对应）。"""

    clicked_line = Signal(object)  # 自身
    context_requested = Signal(object, object)  # (自身, globalPos)

    def __init__(self, speaker: str | None, title: str | None, text: str, wiki_only: bool,
                 skipped: bool = False, deleted: bool = False, parent=None, item: dict | None = None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.item: dict = item if item is not None else {}
        self.wiki_only = bool(wiki_only)
        self.skipped = bool(skipped)
        self.deleted = bool(deleted)
        self._focused = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(10)

        who_col = QWidget()
        wl = QVBoxLayout(who_col)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)
        who_col.setFixedWidth(104)
        title_label = QLabel(title or "")
        title_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        title_label.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 10px; background: transparent;")
        name = speaker if speaker else "旁白"
        sp = QLabel(name)
        sp.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        color = theme.ACCENT if speaker else theme.TEXT_DIM
        sp.setStyleSheet(f"color: {color}; font-weight: 600; background: transparent;")
        sp.setWordWrap(True)
        if title:
            wl.addWidget(title_label)
        wl.addWidget(sp)
        wl.addStretch(1)

        self.text_widget = RubyTextWidget()
        self.text_widget.set_text(text, theme.TEXT if not wiki_only and not deleted else theme.TEXT_DIM)
        if deleted:  # 删除线 + 灰字：一眼能看出这行已从剧本里移除
            struck = self.text_widget.font()
            struck.setStrikeOut(True)
            self.text_widget.setFont(struck)
            self.setToolTip("已删除：该行不参与剧本显示。\n勾选顶栏「显示已删除」后右键可「恢复该行」。")
        if wiki_only and not deleted:
            tip = (
                "未对齐：本地汉化与 wiki 措辞不同。\n"
                "单击此行可手动建立与零协记录的对应（建立后即可编辑）；右键可从该行起批量对应。"
            )
            if skipped:
                tip += "\n（已标记跳过）"
            self.setToolTip(tip)
        lay.addWidget(who_col, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.text_widget, 1)

        # 子控件对鼠标透明：点击一律落到整行（ScriptLineRow.mousePressEvent），
        # 避免文本为空/很窄时点在子控件上「像点不动」。
        for child in (who_col, title_label, sp, self.text_widget):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    # ---- 状态 ----

    @property
    def is_unaligned(self) -> bool:
        """未对齐行：wiki 独有、未跳过、未删除（可建立对应/跳过/删除）。"""
        return self.wiki_only and not self.skipped and not self.deleted

    @property
    def is_aligned(self) -> bool:
        """已对齐行：有本地记录下标，可进编辑器。"""
        return not self.wiki_only and not self.deleted and isinstance(self.item.get("record"), int)

    @property
    def is_deleted(self) -> bool:
        return self.deleted

    @property
    def is_deletable(self) -> bool:
        """可删除：wiki 行（有 key）且不是已对齐行；已删除的行不再可删。"""
        return bool(self.item.get("key")) and not self.deleted and not self.is_aligned

    @property
    def focused(self) -> bool:
        return self._focused

    def set_focused(self, on: bool) -> None:
        """键盘焦点高亮（左侧强调色竖条 + 整行底色）。"""
        self._focused = bool(on)
        self.setProperty("focused", self._focused)
        self.setStyleSheet(_FOCUSED_QSS if self._focused else "")

    # ---- 交互 ----

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked_line.emit(self)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        self.context_requested.emit(self, event.globalPos())
        event.accept()


class ScriptSceneRow(QWidget):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 2)
        dot = QLabel("◆")
        dot.setStyleSheet(f"color: {theme.ACCENT_DARK}; background: transparent;")
        label = QLabel(text)
        label.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600; background: transparent;")
        lay.addStretch(1)
        lay.addWidget(dot)
        lay.addWidget(label)
        lay.addStretch(1)


class ScriptPanel(QWidget):
    """剧本模式：顶栏（标题/关卡切换/切回）+ 可滚动剧本行（支持键盘流）。

    大关卡（RPG 整关近 4000 行）按 ``_CHUNK`` 行分批渲染：切换/切分支时先出第一屏，
    其余滚到底、按 ↓ 越过末尾或点「继续载入」时补齐，避免一次建几千个控件卡住界面。
    """

    _CHUNK = 120  #: 每批渲染的行数

    back_requested = Signal()
    stage_selected = Signal(object)  # {"stage": stage_code, "branch": branch_id|None}
    chapter_selected = Signal(str)  # chapter_id
    line_clicked = Signal(object)  # item dict
    skip_requested = Signal(object)  # item dict（键盘 S：标记跳过）
    unskip_requested = Signal(object)  # item dict（右键：取消跳过）
    delete_requested = Signal(object)  # item dict（键盘 Delete / 右键：删除该行）
    restore_requested = Signal(object)  # item dict（右键：恢复已删除行）
    delete_all_requested = Signal(object)  # item dict（右键：删除本关全部未对应行）
    suggest_requested = Signal(object)  # item dict（右键：自动建议本关未对应行的对应）
    batch_requested = Signal(object)  # item dict（右键：从该行起批量对应）

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.title_label = QLabel("剧本模式")
        self.title_label.setObjectName("title")
        self.chapter_combo = QComboBox()
        self.chapter_combo.setMinimumWidth(110)
        self.stage_combo = QComboBox()
        self.stage_combo.setMinimumWidth(180)
        self.info_label = QLabel("")
        self.info_label.setObjectName("dim")
        self.unaligned_only_cb = QCheckBox("只看未对应")
        self.unaligned_only_cb.setToolTip("只显示未对齐（wiki 独有、无本地对应）的对话行，方便集中处理")
        self.show_deleted_cb = QCheckBox("显示已删除")
        self.show_deleted_cb.setToolTip("勾选后显示已删除的行（灰字删除线），可右键「恢复该行」")
        back_btn = QLabel("⟵ 切回条目模式")
        back_btn.setStyleSheet(f"color: {theme.ACCENT}; background: transparent;")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.mousePressEvent = lambda _e: self.back_requested.emit()
        header.addWidget(self.title_label)
        header.addWidget(self.chapter_combo)
        header.addWidget(self.stage_combo)
        header.addWidget(self.info_label)
        header.addStretch(1)
        header.addWidget(self.unaligned_only_cb)
        header.addWidget(self.show_deleted_cb)
        header.addWidget(back_btn)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 方向键交给面板处理（不被滚动条吃掉）
        self.scroll.setToolTip(_KEY_HINT)
        self.container = QWidget()
        self.container.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(2, 2, 2, 2)
        self.vbox.setSpacing(4)
        self.vbox.addStretch(1)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 面板自己接受键盘焦点
        self._rows: list[ScriptLineRow] = []
        self._items: list[dict] = []  # 最近一次加载的原始 items（切换「显示已删除」时重绘）
        self._visible: list[dict] = []  # 按顶栏开关过滤后、真正要渲染的 items
        self._focus_index = -1
        self._cursor = 0  # 已渲染到 _visible 的哪个位置（大关卡分批渲染）
        self._more_label: QLabel | None = None

        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.stage_combo.currentIndexChanged.connect(
            lambda *_a: self.stage_selected.emit(self.stage_combo.currentData() or {}))
        self.chapter_combo.currentIndexChanged.connect(lambda *_a: self.chapter_selected.emit(self.chapter_combo.currentData() or ""))
        self.show_deleted_cb.toggled.connect(lambda _on: self._rerender())
        self.unaligned_only_cb.toggled.connect(lambda _on: self._rerender())

    def load_stage(self, chapter_label: str, stages: list[dict], stage_code: str | None, items: list[dict],
                   chapters: list[dict] | None = None, chapter_id: str | None = None,
                   focus_key: str | None = None, branch_id: str | None = None) -> None:
        self.title_label.setText(f"剧本模式 · {chapter_label}")
        if chapters is not None:
            self.chapter_combo.blockSignals(True)
            self.chapter_combo.clear()
            for c in chapters:
                self.chapter_combo.addItem(c.get("chapter_label", c.get("chapter_id")), c.get("chapter_id"))
            idx = self.chapter_combo.findData(chapter_id) if chapter_id else 0
            self.chapter_combo.setCurrentIndex(max(idx, 0))
            self.chapter_combo.blockSignals(False)
        self.stage_combo.blockSignals(True)
        self.stage_combo.clear()
        select_index = 0
        for s in stages:
            code = s.get("stage_code")
            branches = s.get("branches") or []
            if branches:
                tail = f"（{len(branches)} 段）"
            else:
                segs = " + ".join(p.get("segment", "") for p in s.get("pages", []))
                tail = f"（{segs}）" if segs else ""
            self.stage_combo.addItem(f"{code}{tail}", {"stage": code, "branch": None})
            if code == stage_code and not branch_id:
                select_index = self.stage_combo.count() - 1
            # RPG 关卡：分支挂在关卡下面（按玩家游玩顺序），选中即只看这一段
            for br in branches:
                bid = br.get("branch_id")
                label = br.get("label") or bid or ""
                self.stage_combo.addItem(f"        └ {label}", {"stage": code, "branch": bid})
                if code == stage_code and branch_id and bid == branch_id:
                    select_index = self.stage_combo.count() - 1
        if stage_code and not branch_id:
            for i in range(self.stage_combo.count()):
                d = self.stage_combo.itemData(i) or {}
                if d.get("stage") == stage_code and not d.get("branch"):
                    select_index = i
                    break
        self.stage_combo.setCurrentIndex(max(select_index, 0))
        self.stage_combo.blockSignals(False)
        self.show_items(items, focus_key=focus_key)

    def show_items(self, items: list[dict], focus_key: str | None = None) -> None:
        """载入 items 并渲染**第一屏**（大关卡分批渲染，切换不再卡）。

        RPG 关卡一整关有近 4000 行，一次性建 4000 个行控件会让切换卡住；
        这里只渲染前 ``_CHUNK`` 行，其余在滚到底 / 按 ↓ 越过末尾 / 点「继续载入」时补齐。
        """
        self._items = list(items or [])
        self._clear_rows()
        self._visible = self._filter_items(self._items)
        self._render_counts()
        self._render_next_chunk()
        self._focus_first(focus_key)

    def _filter_items(self, items: list[dict]) -> list[dict]:
        """按顶栏两个开关过滤出「要显示的行」。"""
        show_deleted = self.show_deleted_cb.isChecked()
        unaligned_only = self.unaligned_only_cb.isChecked()
        out: list[dict] = []
        for it in items:
            if it.get("deleted") and not show_deleted:
                continue  # 已删除的行默认不显示（勾选「显示已删除」后可恢复）
            if unaligned_only and not (it.get("type") == "line" and it.get("wiki_only")
                                       and not it.get("skip") and not it.get("deleted")):
                continue  # 「只看未对应」：场景行与已对齐行都不显示
            out.append(it)
        return out

    def _clear_rows(self) -> None:
        while self.vbox.count() > 1:
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._rows = []
        self._more_label = None
        self._cursor = 0

    def _render_next_chunk(self) -> int:
        """渲染下一批行（默认 120 行）；返回本次渲染的行数。"""
        end = min(len(self._visible), self._cursor + self._CHUNK)
        for it in self._visible[self._cursor:end]:
            if it.get("type") == "scene":
                row = ScriptSceneRow(it.get("text", ""))
                self.vbox.insertWidget(self.vbox.count() - 1, row)
            else:
                row = ScriptLineRow(it.get("speaker"), it.get("title"), it.get("text", ""),
                                    bool(it.get("wiki_only")), bool(it.get("skip")),
                                    bool(it.get("deleted")), item=it)
                row.clicked_line.connect(self._on_row_clicked)
                row.context_requested.connect(self._on_row_context)
                self.vbox.insertWidget(self.vbox.count() - 1, row)
                self._rows.append(row)
        rendered = end - self._cursor
        self._cursor = end
        self._update_more_label()
        return rendered

    def remaining_items(self) -> int:
        """还有多少行没渲染（分批渲染的剩余量）。"""
        return max(0, len(self._visible) - self._cursor)

    def load_more(self) -> int:
        """继续渲染下一批（滚到底 / 按 ↓ / 点提示行都会调它）。"""
        if self.remaining_items() <= 0:
            return 0
        before = self._cursor
        self._render_next_chunk()
        return self._cursor - before

    def _update_more_label(self) -> None:
        """行尾的「继续载入」提示行（渲染完就消失）。"""
        remaining = self.remaining_items()
        if self._more_label is not None:
            self._more_label.deleteLater()
            self._more_label = None
        if remaining <= 0:
            return
        label = QLabel(f"▼ 继续载入剩余 {remaining} 行（滚到底 / 按 ↓ / 点这里）")
        label.setObjectName("dim")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setCursor(Qt.CursorShape.PointingHandCursor)
        label.setStyleSheet(f"color: {theme.ACCENT}; background: transparent; padding: 10px;")
        label.mousePressEvent = lambda _e: self._load_more_from_hint()
        self.vbox.insertWidget(self.vbox.count() - 1, label)
        self._more_label = label

    def _load_more_from_hint(self) -> None:
        self.load_more()

    def _on_scroll(self, value: int) -> None:
        bar = self.scroll.verticalScrollBar()
        if self.remaining_items() and value >= bar.maximum() - 2:
            self.load_more()

    def _render_counts(self) -> None:
        """顶栏进度（按当前过滤后的行统计，和以前一致）。"""
        lines = sum(1 for i in self._visible if i.get("type") != "scene")
        scene = sum(1 for i in self._visible if i.get("type") == "scene")
        unaligned_only = self.unaligned_only_cb.isChecked()
        unaligned = sum(1 for i in self._items if i.get("wiki_only") and not i.get("skip")
                        and not i.get("deleted"))
        manual = sum(1 for i in self._items if i.get("manual") and not i.get("deleted"))
        skipped = sum(1 for i in self._items if i.get("skip") and not i.get("deleted"))
        deleted = sum(1 for i in self._items if i.get("deleted"))
        aligned = max(0, lines - unaligned - skipped - deleted)
        done = aligned + manual  # 手动对应的行也算「已处理」
        pct = round(done * 100 / lines) if lines else 100
        manual_txt = f" · 手动 {manual}" if manual else ""
        skip_txt = f" · 跳过 {skipped}" if skipped else ""
        del_txt = f" · 删除 {deleted}" if deleted else ""
        done_txt = " · 全部对应 ✔" if lines and unaligned == 0 else ""
        self.info_label.setText(
            f"本关 {done}/{lines}（{pct}%）· 未对齐 {unaligned}"
            f"{manual_txt}{skip_txt}{del_txt}{done_txt}"
            f"{' · 只看未对应' if unaligned_only else ''}"
        )
        self.info_label.setToolTip(
            f"对话 {lines} 行 · 场景 {scene} 行 · 已对齐 {aligned} · 手动对应 {manual}"
            f" · 未对齐 {unaligned} · 已跳过 {skipped} · 已删除 {deleted}"
        )

    def _rerender(self, focus_key: str | None = None) -> None:
        """按当前「显示已删除」开关重绘（尽量保持焦点位置）。"""
        if focus_key is None:
            focus_key = (self.current_item() or {}).get("key")
        self.show_items(self._items, focus_key=focus_key)

    def unaligned_items(self) -> list[dict]:
        """所有未对齐行（带 key），用于「删除本关全部未对应行」。

        注意：按 ``_items`` 统计而不是已渲染的行——大关卡是分批渲染的。
        """
        return [i for i in self._items
                if i.get("wiki_only") and not i.get("skip") and not i.get("deleted") and i.get("key")]

    # ---------- 键盘焦点（↑↓ / Enter / S / Ctrl+↑↓） ----------

    def line_rows(self) -> list[ScriptLineRow]:
        """按显示顺序排列的对话行（不含场景行）。"""
        return list(self._rows)

    def focus_index(self) -> int:
        return self._focus_index

    def current_row(self) -> ScriptLineRow | None:
        if 0 <= self._focus_index < len(self._rows):
            return self._rows[self._focus_index]
        return None

    def current_item(self) -> dict | None:
        row = self.current_row()
        return row.item if row is not None else None

    def _row_index_of(self, item) -> int:
        for i, row in enumerate(self._rows):
            if row.item is item:
                return i
        return -1

    def _visible_index_of(self, item) -> int:
        """item 在 _visible 里的位置（未渲染的行也能找到）。"""
        for i, it in enumerate(self._visible):
            if it is item:
                return i
        return -1

    def _row_index_for_visible(self, pos: int) -> int:
        """_visible 位置 → 对话行下标（场景行不占行号）。"""
        return sum(1 for it in self._visible[:pos] if it.get("type") != "scene")

    def _focus_first(self, focus_key: str | None = None) -> None:
        """show_items 后聚焦第一行（有 focus_key 时聚焦该行，用于刷新后恢复位置）。"""
        index = 0
        if focus_key:
            for i, row in enumerate(self._rows):
                if row.item.get("key") == focus_key:
                    index = i
                    break
        self.set_focus_index(index if self._rows else -1)
        if self._rows:
            self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _render_until_row(self, index: int) -> None:
        """把第 index 条对话行渲染出来（分批渲染时按需补齐）。"""
        while index >= len(self._rows) and self.remaining_items() > 0:
            self.load_more()

    def set_focus_index(self, index: int) -> int:
        """把焦点移到第 index 条对话行（越界时夹取到两端）；返回实际下标。"""
        if index >= len(self._rows):
            self._render_until_row(index)
        if not self._rows:
            self._focus_index = -1
            return -1
        index = max(0, min(int(index), len(self._rows) - 1))
        for i, row in enumerate(self._rows):
            row.set_focused(i == index)
        self._focus_index = index
        self.scroll.ensureWidgetVisible(self._rows[index], 0, 24)
        return index

    def move_focus(self, delta: int) -> int:
        """↑/↓：在当前按序的对话行之间移动（不环绕）。"""
        if not self._rows:
            return -1
        if self._focus_index < 0:
            return self.set_focus_index(0 if delta >= 0 else len(self._rows) - 1)
        return self.set_focus_index(self._focus_index + int(delta))

    def jump_unaligned(self, delta: int) -> int:
        """Ctrl+↑/↓：跳到上一条/下一条未对齐行；找不到时保持原位。

        在 ``_visible`` 上找（分批渲染时未渲染的行也能跳过去，找到后按需补齐）。
        """
        if not self._visible:
            return -1
        step = 1 if delta > 0 else -1
        pos = self._visible_index_of(self.current_item()) if self.current_row() is not None else -1
        start = 0 if pos < 0 else pos + step
        rng = range(start, len(self._visible)) if step > 0 else range(start, -1, -1)
        for p in rng:
            it = self._visible[p]
            if it.get("type") != "scene" and it.get("wiki_only") and not it.get("skip")                     and not it.get("deleted"):
                return self.set_focus_index(self._row_index_for_visible(p))
        return self._focus_index

    def activate_current(self) -> dict | None:
        """Enter：对当前行触发 line_clicked（未对齐→建立对应；已对齐→进编辑器）。"""
        row = self.current_row()
        if row is None:
            return None
        self.line_clicked.emit(row.item)
        return row.item

    def skip_current(self) -> dict | None:
        """S：当前行是未对齐行时触发 skip_requested。"""
        row = self.current_row()
        if row is None or not row.is_unaligned:
            return None
        self.skip_requested.emit(row.item)
        return row.item

    def delete_current(self) -> dict | None:
        """Delete：当前行（wiki 行且未对齐/已跳过）触发 delete_requested。"""
        row = self.current_row()
        if row is None or not row.is_deletable:
            return None
        self.delete_requested.emit(row.item)
        return row.item

    def keyPressEvent(self, event) -> None:
        key = event.key()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        down = key == Qt.Key.Key_Down
        up = key == Qt.Key.Key_Up
        if down or up:
            if ctrl:
                self.jump_unaligned(1 if down else -1)
            else:
                self.move_focus(1 if down else -1)
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.activate_current()
            event.accept()
            return
        if key == Qt.Key.Key_S and not ctrl:
            self.skip_current()
            event.accept()
            return
        if key == Qt.Key.Key_Delete:
            self.delete_current()
            event.accept()
            return
        super().keyPressEvent(event)

    # ---------- 右键菜单与批量对应 ----------

    def row_menu(self, row: ScriptLineRow) -> QMenu | None:
        """行的右键菜单（动作类型写在 action.data() 里，由 _on_row_context 分发）。

        - 未对齐：批量对应 / 删除该行 / 删除本关全部未对应行
        - 已跳过：取消跳过 / 删除该行
        - 已删除：恢复该行
        - 已对齐：在编辑器中打开
        """
        menu = QMenu(self)

        def add(text: str, kind: str):
            action = menu.addAction(text)
            action.setData(kind)
            return action

        if row.is_deleted:
            add("恢复该行", "restore")
            return menu
        if row.is_unaligned:
            add("从该行起批量对应…", "batch")
            n_all = len(self.unaligned_items())
            if n_all > 1:
                add(f"自动建议对应（本关 {n_all} 行未对应）…", "suggest")
            menu.addSeparator()
            add("删除该行（从剧本中移除）", "delete")
            n = len(self.unaligned_items())
            if n > 1:
                add(f"删除本关全部未对应行（{n} 行）", "delete_all")
            return menu
        if row.is_aligned:
            add("在编辑器中打开", "open")
            return menu
        if row.wiki_only and row.skipped:  # 已跳过
            add("取消跳过（恢复为未对齐）", "unskip")
            add("删除该行（从剧本中移除）", "delete")
            return menu
        return None

    def contiguous_unaligned(self, item: dict) -> list[dict]:
        """从 item（含）起连续的未对齐行；场景行不影响，遇到已对齐/已跳过行或换页换文件即止。"""
        if not isinstance(item, dict):
            return []
        idx = self._visible_index_of(item)
        if idx < 0:
            return []
        page, relfile = item.get("page"), item.get("file")
        out: list[dict] = []
        for it in self._visible[idx:]:  # 扫过滤后的全量（分批渲染时未渲染的也算）
            if it.get("type") == "scene":
                continue
            if not (it.get("wiki_only") and not it.get("skip") and not it.get("deleted") and it.get("key")):
                break
            if it.get("page") != page or it.get("file") != relfile:
                break
            out.append(it)
        return out

    def next_unaligned_key(self, item: dict | None) -> str | None:
        """item 之后（不含自身）第一条未对齐行的 key；用于刷新后恢复焦点。"""
        if not isinstance(item, dict):
            return None
        start = self._row_index_of(item) + 1
        for row in self._rows[max(start, 0):]:
            if row.is_unaligned and row.item.get("key"):
                return row.item.get("key")
        return None

    def _on_row_clicked(self, row: ScriptLineRow) -> None:
        idx = self._row_index_of(row.item)
        if idx >= 0:
            self.set_focus_index(idx)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.line_clicked.emit(row.item)

    def _on_row_context(self, row: ScriptLineRow, pos) -> None:
        idx = self._row_index_of(row.item)
        if idx >= 0:
            self.set_focus_index(idx)
        menu = self.row_menu(row)
        if menu is None:
            return
        chosen = menu.exec(pos)
        if chosen is None:
            return
        kind = chosen.data()
        if kind == "batch":
            self.batch_requested.emit(row.item)
        elif kind == "delete":
            self.delete_requested.emit(row.item)
        elif kind == "delete_all":
            self.delete_all_requested.emit(row.item)
        elif kind == "suggest":
            self.suggest_requested.emit(row.item)
        elif kind == "restore":
            self.restore_requested.emit(row.item)
        elif kind == "unskip":
            self.unskip_requested.emit(row.item)
        else:
            self.line_clicked.emit(row.item)
