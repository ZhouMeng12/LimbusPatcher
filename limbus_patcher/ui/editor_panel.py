"""右侧编辑区：定位信息 / 原文只读 / 自定义编辑 / 操作与状态。

撤销/重做由面板自己的 QUndoStack 管理（Qt 自带的撤销栈已关闭）：
- 连续输入按合并窗口合并成一条命令；
- 载入新条目清空撤销栈（载入本身不可撤销）；
- 「还原为原文」/ 主窗口直接 setPlainText 都会登记成一条可撤销命令；
- 保存不改撤销栈：撤销只改编辑框内容，再次保存才会写回方案文件。
"""
from __future__ import annotations

import difflib
import html as html_mod
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import theme
from ..categories import category_label
from ..patch import record_title, ref_label

UNDO_LIMIT = 200  # 撤销栈上限（步）
UNDO_MERGE_WINDOW_MS = 800  # 连续输入合并窗口（毫秒）：窗口内的输入算作一条撤销命令
_MERGE_ID = 1  # 可合并命令的 id；QUndoStack 只在 id 相同且非 -1 时尝试 mergeWith
_LABEL_TYPING = "输入"
_LABEL_RESTORE = "还原为原文"


def _diff_html(original: str, custom: str) -> str:
    """按行 diff，生成轻量高亮 HTML（新增=青绿底，删除=砖红底）。"""
    lines_old = original.splitlines()
    lines_new = custom.splitlines()
    rows: list[str] = []

    def esc(text: str) -> str:
        out = html_mod.escape(text)
        return out if out.strip() else "&nbsp;"  # 空行也要占一行高度

    def marked(text: str, kind: str) -> str:
        if kind == "insert":
            style = "background-color:#2f4a3f;color:#cfe8dc"
        else:  # delete
            style = "background-color:#4a302c;color:#e8c6bf;text-decoration:line-through"
        return f'<span style="{style}">{esc(text)}</span>'

    # get_opcodes() 每项是 5 元组 (tag, i1, i2, j1, j2)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=lines_old, b=lines_new, autojunk=False).get_opcodes():
        if tag == "equal":
            rows.extend(esc(line) for line in lines_old[i1:i2])
        elif tag == "delete":
            rows.extend(marked(line, "delete") for line in lines_old[i1:i2])
        elif tag == "insert":
            rows.extend(marked(line, "insert") for line in lines_new[j1:j2])
        else:  # replace：先删后增，便于左右对照
            rows.extend(marked(line, "delete") for line in lines_old[i1:i2])
            rows.extend(marked(line, "insert") for line in lines_new[j1:j2])
    return "<br/>".join(rows) or "（无差异）"


class _CustomTextEdit(QPlainTextEdit):
    """自定义文本框：把「外部整段赋值」上报给面板，登记成一条可撤销命令。

    主窗口（还原为原文 / 历史回滚 / 恢复会话）会直接调用 setPlainText，
    这层包装让这些赋值也进入撤销栈，而不是绕过它。
    """

    programmatic_replace = Signal(str)  # 外部整段替换请求
    undo_pressed = Signal()  # 编辑框内按下 Ctrl+Z
    redo_pressed = Signal()  # 编辑框内按下 Ctrl+Y / Ctrl+Shift+Z

    def keyPressEvent(self, event) -> None:  # noqa: N802 —— 保持 Qt 命名
        """编辑框自己转发撤销/重做按键（Qt 自带撤销栈已关闭）。

        真实按键走 QShortcut 时不会到达这里；直接派发（测试/嵌入场景）时由这里兜底，
        两条路径互斥，不会重复撤销。
        """
        seq = QKeySequence(event.keyCombination())
        if seq == QKeySequence("Ctrl+Z"):
            self.undo_pressed.emit()
            event.accept()
            return
        if seq == QKeySequence("Ctrl+Y") or seq == QKeySequence("Ctrl+Shift+Z"):
            self.redo_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def setPlainText(self, text: str) -> None:  # noqa: N802 —— 保持 Qt 命名
        if self.toPlainText() == text:
            return  # 文本没变：不产生命令，也不重置光标
        self.programmatic_replace.emit(text)
        if self.toPlainText() != text:
            # 面板没有处理（例如未连接/被抑制）时兜底，保持原生行为
            QPlainTextEdit.setPlainText(self, text)

    def set_text_internal(self, text: str) -> None:
        """面板内部写入（载入 / 撤销 / 重做），绕过上报逻辑。"""
        QPlainTextEdit.setPlainText(self, text)

    def clear(self) -> None:  # noqa: N802 —— 保持 Qt 命名
        """清空也走整段替换，保证命令标签可控（默认「清空文本」）。"""
        self.setPlainText("")


class _TextCommand(QUndoCommand):
    """一次文本变更；连续的同类输入可合并成一条撤销命令。"""

    def __init__(self, panel: "EditorPanel", old_text: str, new_text: str, label: str, *,
                 mergeable: bool, generation: int) -> None:
        super().__init__(label)
        self._panel = panel
        self._old_text = old_text
        self._new_text = new_text
        self._label = label
        self._mergeable = mergeable
        self._generation = generation
        self._stamp = time.monotonic()

    def id(self) -> int:  # noqa: A003 —— Qt 接口
        return _MERGE_ID if self._mergeable else -1  # -1 = 永不合并

    def mergeWith(self, other: QUndoCommand) -> bool:  # noqa: N802 —— Qt 接口
        """other 是后压入的命令；只有同一代、同标签、文本首尾相接且够快才合并。"""
        if not isinstance(other, _TextCommand) or other._label != self._label:
            return False
        if other._generation != self._generation or self._new_text != other._old_text:
            return False
        if (other._stamp - self._stamp) * 1000.0 > self._panel.undo_merge_window_ms:
            return False
        self._new_text = other._new_text
        self._stamp = other._stamp
        return True

    def undo(self) -> None:
        self._panel._apply_text(self._old_text)

    def redo(self) -> None:
        self._panel._apply_text(self._new_text)


class EditorPanel(QFrame):
    save_requested = Signal(object, str)  # (ref, value)
    restore_requested = Signal(object)  # ref
    favorite_toggled = Signal(object, bool)  # (ref, favorite)
    history_requested = Signal(object)  # ref
    story_requested = Signal()
    undo_available = Signal(bool)  # 撤销可用性变化（供主窗口更新菜单/按钮）
    redo_available = Signal(bool)  # 重做可用性变化

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.title_label = QLabel("未选择条目")
        self.title_label.setObjectName("title")
        self.title_label.setWordWrap(True)
        self.meta_label = QLabel("在左侧选择分类、搜索并点击条目开始编辑")
        self.meta_label.setObjectName("dim")
        self.meta_label.setWordWrap(True)
        self.advanced_label = QLabel("")
        self.advanced_label.setObjectName("dim")
        self.advanced_label.setWordWrap(True)
        self.advanced_label.hide()

        # ---- 主列：自定义文本（原型 .emain） ----
        custom_caption_row = QHBoxLayout()
        custom_caption = QLabel("自定义文本")
        custom_caption.setObjectName("dim")
        self.char_label = QLabel("0 字")
        self.char_label.setObjectName("dim")
        custom_caption_row.addWidget(custom_caption)
        custom_caption_row.addStretch(1)
        custom_caption_row.addWidget(self.char_label)

        self.custom_edit = _CustomTextEdit()
        self.custom_edit.setPlaceholderText("在此输入自定义文本…")
        # 关掉 Qt 自带撤销栈，避免与面板的 QUndoStack 两套栈打架
        self.custom_edit.setUndoRedoEnabled(False)

        emain = QWidget()
        emain_layout = QVBoxLayout(emain)
        emain_layout.setContentsMargins(0, 0, 0, 0)
        emain_layout.setSpacing(6)
        emain_layout.addLayout(custom_caption_row)
        emain_layout.addWidget(self.custom_edit, 1)

        # ---- 右侧常驻「参考」栏（原型 .drawer）：零协原文 / 英语原文 两个页签 ----
        self.ref_tab_zh = QPushButton("零协原文")
        self.ref_tab_zh.setObjectName("refTab")
        self.ref_tab_zh.setCheckable(True)
        self.ref_tab_zh.setChecked(True)
        self.ref_tab_zh.setFixedHeight(28)
        self.ref_tab_zh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ref_tab_en = QPushButton("英语原文")
        self.ref_tab_en.setObjectName("refTab")
        self.ref_tab_en.setCheckable(True)
        self.ref_tab_en.setFixedHeight(28)
        self.ref_tab_en.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ref_tab_zh.clicked.connect(lambda _c=False: self.set_baseline_visible(False))
        self.ref_tab_en.clicked.connect(lambda _c=False: self.set_baseline_visible(True))

        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(0, 0, 0, 0)
        tab_row.setSpacing(2)
        tab_row.addWidget(self.ref_tab_zh)
        tab_row.addWidget(self.ref_tab_en)
        tab_row.addStretch(1)

        # 字段定位：相对路径 / 序号 / 字段名（原型右侧参考栏顶部的三行元信息）
        self.ref_meta = QLabel("")
        self.ref_meta.setObjectName("faint")
        self.ref_meta.setWordWrap(True)

        orig_caption = QLabel("零协原文（只读）")
        orig_caption.setObjectName("dim")
        self.original_edit = QPlainTextEdit()
        self.original_edit.setObjectName("original")
        self.original_edit.setReadOnly(True)
        self.original_edit.setPlaceholderText("（原文为空）")
        zh_page = QWidget()
        zh_lay = QVBoxLayout(zh_page)
        zh_lay.setContentsMargins(0, 0, 0, 0)
        zh_lay.setSpacing(6)
        zh_lay.addWidget(orig_caption)
        zh_lay.addWidget(self.original_edit, 1)

        self.baseline_caption = QLabel("英语原文（只读）")
        self.baseline_caption.setObjectName("dim")
        self.baseline_edit = QPlainTextEdit()
        self.baseline_edit.setObjectName("baseline")
        self.baseline_edit.setReadOnly(True)
        self.baseline_edit.setPlaceholderText("（未取到英文原文）")
        en_page = QWidget()
        en_lay = QVBoxLayout(en_page)
        en_lay.setContentsMargins(0, 0, 0, 0)
        en_lay.setSpacing(6)
        en_lay.addWidget(self.baseline_caption)
        en_lay.addWidget(self.baseline_edit, 1)

        self.ref_stack = QStackedWidget()
        self.ref_stack.addWidget(zh_page)
        self.ref_stack.addWidget(en_page)
        self.baseline_pane = en_page  # 兼容旧名：英语原文那一页

        self.drawer = QFrame()
        self.drawer.setObjectName("drawer")
        self.drawer.setFixedWidth(310)
        drawer_lay = QVBoxLayout(self.drawer)
        drawer_lay.setContentsMargins(11, 9, 11, 11)
        drawer_lay.setSpacing(6)
        drawer_lay.addLayout(tab_row)
        drawer_lay.addWidget(self.ref_meta)
        drawer_lay.addWidget(self.ref_stack, 1)

        # 主列 + 参考栏并排（原型 .ebody）
        self.compare_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.compare_splitter.addWidget(emain)
        self.compare_splitter.addWidget(self.drawer)
        self.compare_splitter.setStretchFactor(0, 1)
        self.compare_splitter.setStretchFactor(1, 0)
        self.compare_splitter.setSizes([560, 310])

        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.hide()

        btn_row = QHBoxLayout()
        # 不加弯箭头字形：U+21B6 / U+21B7（撤销/重做箭头）在 YaHei / Segoe UI /
        # SimHei 里**都没有字形**，会画成豆腐块（见 scripts/scan_glyphs.py）。
        self.undo_btn = QPushButton("撤销")
        self.undo_btn.setEnabled(False)
        self.redo_btn = QPushButton("重做")
        self.redo_btn.setEnabled(False)
        self.save_btn = QPushButton("保存")
        self.save_btn.setObjectName("primary")
        self.restore_btn = QPushButton("还原为原文")
        self.history_btn = QPushButton("历史")
        self.story_btn = QPushButton("剧本模式")
        self.story_btn.hide()
        self.fav_btn = QPushButton("☆ 收藏")
        self.fav_btn.setCheckable(True)
        self.diff_btn = QPushButton("显示差异")
        self.diff_btn.setCheckable(True)
        self.baseline_btn = QPushButton("参考 Ctrl+E")
        self.baseline_btn.setCheckable(True)
        self.baseline_btn.setToolTip(
            "右侧常驻参考栏：在「零协原文 / 英语原文」之间切换（Ctrl+E）。"
            "工具不会写入英文文件。")
        self.save_btn.setToolTip("保存到方案文件（Ctrl+S）。保存不清空撤销记录："
                                 "撤销只改编辑框内容，要再按一次 Ctrl+S 才会写回方案。")
        self.restore_btn.setToolTip(f"{_LABEL_RESTORE}：把自定义文本恢复为零协原文（Ctrl+Z 可撤销）。")
        btn_row.addWidget(self.undo_btn)
        btn_row.addWidget(self.redo_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.restore_btn)
        btn_row.addWidget(self.history_btn)
        btn_row.addWidget(self.story_btn)
        btn_row.addWidget(self.fav_btn)
        btn_row.addWidget(self.diff_btn)
        btn_row.addWidget(self.baseline_btn)
        btn_row.addStretch(1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.compare_splitter, 1)
        layout.addWidget(self.diff_view, 1)
        layout.addLayout(btn_row)
        layout.addWidget(self.status_label)

        self._ref = None
        self._original_text = ""
        self._favorite = False

        # ---- 撤销栈状态 ----
        self._last_text = ""  # 编辑框当前文本（用于生成撤销命令）
        self._applying = False  # 正在由撤销栈/载入写入时，不再生成新命令
        self._merge_generation = 0  # 递增即打断「连续输入」合并
        self.undo_merge_window_ms = UNDO_MERGE_WINDOW_MS  # 测试/调参可改
        self._undo_stack = QUndoStack(self)
        self._undo_stack.setUndoLimit(UNDO_LIMIT)
        self._undo_stack.canUndoChanged.connect(self.undo_available)
        self._undo_stack.canRedoChanged.connect(self.redo_available)

        self.custom_edit.textChanged.connect(self._on_text_changed)
        self.custom_edit.programmatic_replace.connect(self._on_programmatic_replace)
        self.custom_edit.undo_pressed.connect(self.undo)
        self.custom_edit.redo_pressed.connect(self.redo)
        self.undo_btn.clicked.connect(self.undo)
        self.redo_btn.clicked.connect(self.redo)
        self.undo_available.connect(self._on_undo_available)
        self.redo_available.connect(self._on_redo_available)
        self.save_btn.clicked.connect(self._on_save)
        self.restore_btn.clicked.connect(lambda: self.restore_requested.emit(self._ref) if self._ref else None)
        self.history_btn.clicked.connect(lambda: self.history_requested.emit(self._ref) if self._ref else None)
        self.story_btn.clicked.connect(self.story_requested)
        self.fav_btn.clicked.connect(lambda checked: self.favorite_toggled.emit(self._ref, checked) if self._ref else None)
        self.diff_btn.toggled.connect(self._on_diff_toggle)
        self.baseline_btn.toggled.connect(self.set_baseline_visible)

        # 面板自带的撤销/重做快捷键（编辑框有焦点时生效）
        self._shortcuts: list[QShortcut] = []
        for keys, slot in (
            ("Ctrl+Z", self.undo),
            ("Ctrl+Y", self.redo),
            ("Ctrl+Shift+Z", self.redo),  # 兼容常见「重做」习惯
            ("Ctrl+E", self.toggle_baseline),  # 英语原文栏
        ):
            sc = QShortcut(QKeySequence(keys), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
            self._shortcuts.append(sc)

        self.setEnabled(False)

    def set_story_available(self, available: bool) -> None:
        self.story_btn.setVisible(available)

    # ---- 载入 ----

    def load_hit(self, ref, original_text: str, custom: str | None, record: dict | None, chapter: str | None,
                 category: str, character: str | None, favorite: bool, advanced: bool,
                 baseline_text: str | None = None, baseline_note: str | None = None) -> None:
        self._ref = ref
        self._original_text = original_text
        self._favorite = favorite
        self.title_label.setText(record_title(record, ref) if record else ref_label(ref))
        parts = [category_label(category)]
        if chapter:
            parts.append(chapter)
        if character:
            parts.append(character)
        self.meta_label.setText(" · ".join(parts))
        if advanced:
            fp = " / ".join(seg.get("k", f"[{seg.get('i')}]") for seg in ref.field_path)
            self.advanced_label.setText(f"来源：{ref.file}\nKeyID：{ref_label(ref)}   字段：{fp}")
        # 字段定位统一放在右侧常驻参考栏（ref_meta），标题区不再重复一份
        self.advanced_label.hide()
        self.original_edit.setPlainText(original_text)
        self._set_ref_meta(ref)
        self._load_baseline(baseline_text, baseline_note)
        # 载入新条目：写入文本并清空撤销栈（不同条目的编辑不能互相撤销，载入本身不可撤销）
        self._reset_history(custom if custom is not None else "")
        self.fav_btn.setChecked(favorite)
        self.fav_btn.setText("★ 已收藏" if favorite else "☆ 收藏")
        self.status_label.setText("")
        self.setEnabled(True)
        self.custom_edit.setFocus()

    def _on_undo_available(self, available: bool) -> None:
        self.undo_btn.setEnabled(bool(available))
        label = self.undo_label()
        self.undo_btn.setToolTip(f"撤销「{label}」（Ctrl+Z）—— 只改编辑框，保存后才写回方案")
        self.undo_btn.setText(f"撤销 {label}" if available else "撤销")

    def _on_redo_available(self, available: bool) -> None:
        self.redo_btn.setEnabled(bool(available))
        label = self.redo_label()
        self.redo_btn.setToolTip(f"重做「{label}」（Ctrl+Y）")
        self.redo_btn.setText(f"重做 {label}" if available else "重做")

    # ---- 右侧参考栏：零协原文 / 英语原文 两个页签 ----

    def set_baseline_visible(self, on: bool) -> None:
        """切到英语原文页（True）或零协原文页（False）。

        按钮与 Ctrl+E 共用；状态由主窗口存进会话记忆。参考栏本身常驻，
        所以这里切的是**页签**而不是整栏的显隐。
        """
        on = bool(on)
        self.ref_stack.setCurrentIndex(1 if on else 0)
        self.ref_tab_en.setChecked(on)
        self.ref_tab_zh.setChecked(not on)
        if self.baseline_btn.isChecked() != on:
            self.baseline_btn.blockSignals(True)
            self.baseline_btn.setChecked(on)
            self.baseline_btn.blockSignals(False)

    def baseline_visible(self) -> bool:
        """当前是否停在「英语原文」页签。"""
        return self.ref_stack.currentIndex() == 1

    def toggle_baseline(self) -> None:
        self.set_baseline_visible(not self.baseline_visible())
        self.baseline_btn.toggled.emit(self.baseline_visible())

    def _set_ref_meta(self, ref) -> None:
        """参考栏顶部的字段定位：KeyID / idx / field（原型右侧参考栏的元信息）。"""
        if ref is None:
            self.ref_meta.setText("")
            return
        bits = []
        if getattr(ref, "file", ""):
            bits.append(f"file: {ref.file}")
        if getattr(ref, "id", None) is not None:
            bits.append(f"KeyID: {ref.id}")
        idx = getattr(ref, "record_index", None)
        if idx is not None:
            bits.append(f"idx: {idx}")
        path = getattr(ref, "field_path", None) or []
        fp = " / ".join(seg.get("k", f"[{seg.get('i')}]") for seg in path)
        if fp:
            bits.append(f"field: {fp}")
        self.ref_meta.setText(" · ".join(bits))

    def _load_baseline(self, text: str | None, note: str | None) -> None:
        """写入英文栏：有文本就显示，没有就用 placeholder 说明原因（如「英文无此字段」）。"""
        self.baseline_edit.setPlainText(text or "")
        reason = note or (None if text else "（未取到英文原文）")
        self.baseline_edit.setPlaceholderText(reason or "（未取到英文原文）")
        self.baseline_caption.setText("英语原文（只读）" + (f" · {reason}" if reason and not text else ""))

    def keyPressEvent(self, event) -> None:
        """兜底：直接派发到面板的 Ctrl+E 也生效（真实按键由 QShortcut 处理）。"""
        if event.key() == Qt.Key.Key_E and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.toggle_baseline()
            event.accept()
            return
        super().keyPressEvent(event)

    def set_status(self, text: str, ok: bool = True) -> None:
        self.status_label.setStyleSheet(f"color: {theme.SUCCESS if ok else theme.ERROR};")
        self.status_label.setText(text)

    def set_saved_info(self, text: str) -> None:
        self.status_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self.status_label.setText(text)

    def custom_text(self) -> str:
        return self.custom_edit.toPlainText()

    # ---- 撤销 / 重做（公开 API） ----

    def undo(self) -> None:
        """撤销一步（栈空时安全空操作）。只改编辑框内容，不写方案文件。"""
        self._undo_stack.undo()

    def redo(self) -> None:
        """重做一步（栈空时安全空操作）。只改编辑框内容，不写方案文件。"""
        self._undo_stack.redo()

    def can_undo(self) -> bool:
        return self._undo_stack.canUndo()

    def can_redo(self) -> bool:
        return self._undo_stack.canRedo()

    def undo_label(self) -> str:
        """下一条可撤销操作的中文名（栈空时返回「撤销」）。"""
        return self._undo_stack.undoText() or "撤销"

    def redo_label(self) -> str:
        """下一条可重做操作的中文名（栈空时返回「重做」）。"""
        return self._undo_stack.redoText() or "重做"

    def undo_count(self) -> int:
        """撤销栈中的命令数（已撤销、未撤销都计入）。"""
        return self._undo_stack.count()

    def clear_undo_history(self) -> None:
        """清空撤销栈（载入新条目时会自动调用），当前文本保持不变。"""
        self._undo_stack.clear()
        self._merge_generation += 1

    def set_custom_text(self, text: str, label: str = "应用文本") -> None:
        """外部整段替换编辑框文本，并登记成一条可撤销命令（不写方案文件）。"""
        if text == self._last_text:
            return
        self._push_command(self._last_text, text, label, mergeable=False)

    def restore_to_original(self) -> None:
        """把自定义文本还原为零协原文：一条可撤销命令（不写方案文件）。"""
        if self._ref is None:
            return
        self.set_custom_text(self._original_text, _LABEL_RESTORE)

    # ---- 内部 ----

    def _on_text_changed(self) -> None:
        self._update_char_count()
        if self._applying:
            return  # 撤销栈/载入正在写文本，别再生成命令
        new_text = self.custom_edit.toPlainText()
        if new_text == self._last_text:
            return
        old_text, self._last_text = self._last_text, new_text
        # 窗口内的连续输入由 _TextCommand.mergeWith 合并成一条
        self._push_command(old_text, new_text, _LABEL_TYPING, mergeable=True)

    def _on_programmatic_replace(self, text: str) -> None:
        """主窗口直接 setPlainText（还原为原文 / 历史回滚等）→ 一条可撤销命令。"""
        if self._applying or text == self._last_text:
            return
        self._push_command(self._last_text, text, self._label_for_text(text), mergeable=False)

    def _label_for_text(self, text: str) -> str:
        # 整段替换后与原文一致 → 认定是「还原为原文」（原文为空时同样成立）
        if text == self._original_text:
            return _LABEL_RESTORE
        if text == "":
            return "清空文本"
        return "应用文本"

    def _push_command(self, old_text: str, new_text: str, label: str, *, mergeable: bool) -> None:
        """压入一条文本命令；push 会立即调用 redo()（文本已经是 new_text 时不会重写）。"""
        self._undo_stack.push(_TextCommand(
            self, old_text, new_text, label,
            mergeable=mergeable, generation=self._merge_generation,
        ))

    def _reset_history(self, text: str) -> None:
        """写入文本并清空撤销栈（载入条目用）。"""
        self._undo_stack.clear()
        self._merge_generation += 1
        self._apply_text(text)
        # 载入后明确广播一次可用性，主窗口不必先自己查一遍
        self.undo_available.emit(self.can_undo())
        self.redo_available.emit(self.can_redo())

    def _apply_text(self, text: str) -> None:
        """写入编辑框且不产生新命令（载入 / 撤销 / 重做共用）。"""
        self._applying = True
        self._last_text = text
        try:
            if self.custom_edit.toPlainText() != text:
                self.custom_edit.set_text_internal(text)
                self._move_cursor_to_end()
        finally:
            self._applying = False
        self._update_char_count()

    def _move_cursor_to_end(self) -> None:
        cursor = self.custom_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.custom_edit.setTextCursor(cursor)

    def _break_merge(self) -> None:
        """打断「连续输入」合并：之后的输入另起一条撤销命令。"""
        self._merge_generation += 1

    def _update_char_count(self) -> None:
        self.char_label.setText(f"{len(self.custom_edit.toPlainText())} 字")

    def _on_save(self) -> None:
        if self._ref is None:
            return
        # 保存只写方案文件、不动撤销栈：撤销仍可回到保存前的文本（再保存才写回）
        self._break_merge()
        self.save_requested.emit(self._ref, self.custom_edit.toPlainText())

    def _on_diff_toggle(self, checked: bool) -> None:
        if checked:
            self.diff_view.setHtml(_diff_html(self._original_text, self.custom_edit.toPlainText()))
            self.diff_view.show()
            self.compare_splitter.hide()
        else:
            self.diff_view.hide()
            self.compare_splitter.show()
