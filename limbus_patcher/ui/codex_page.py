"""人格 / E.G.O 图鉴页（照游戏原版的信息层级）。

三级导航：罪人 → 人格 / E.G.O 卡片 → 技能 / 剧情 / 语音 三页签。
- 技能：一张卡一个技能（名字 · 等级 · 硬币），展开看各等级效果与硬币效果，逐条可改。
- 剧情：本地逐行（说话人 · 场景 · 正文），可逐行改，也可一键进剧本模式。
- 语音：一格一条（上=类别如「战斗胜利」，下=台词），点击就地改。
只读参考：英语原文（若已配置英文基线）。

显示：正文 / 台词 / 技能说明 / 硬币效果都按零协原文渲染格式（颜色 / 字号 / 高亮 / 粗体…），
页头「显示格式」可一键切回纯文本；tooltip 一律用去标签的纯文本。
技能说明 / 硬币效果 / 剧情 / 语音里的方括号关键词 id（[KarmaOfIndexAlly]、[Breath]…）
按关键词表显示成游戏里的中文名（见 limbus_patcher.keywords），页头「关键词名」可切回原始 [id]；
tooltip 里附带这条文本用到的关键词明细（id + 中文名）。

关键词交互（只作用于显示，不碰原文）：
- 鼠标在关键词名上停 KEYWORD_HOVER_DELAY_MS 毫秒 → 弹出它的 desc（说明）与 flavor（风味文本，灰色）；
- 点关键词 → 打开「关键词 / 状态」编辑（name / desc / flavor，写的是 BattleKeywords / Bufs / SkillTag 里的记录）；
- 点正文空白处 → 还是原来的技能说明 / 台词 / 剧情编辑，编辑框里看到的是原始 [id]，一个字符都不改。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .. import codex, keywords, richtext
from ..entities import CONTENT_CHOICES, KIND_EGO, KIND_PERSONALITY, SINNER_NAMES
from ..patch import EntryRef, encode_fp
from ..search import SCOPE_LABELS  # noqa: F401  (保持与主界面同一套范围词)
from . import theme
from .dialogs import info, safe_exec
from .replace_dialog import open_replace_dialog

PORTRAIT_DIR_NAME = "portraits"
#: tooltip 里最多列几个关键词（多了反而看不清）
TOKEN_TIP_LIMIT = 8
#: 关键词锚点的 href 前缀（<a href="kw:Breath">呼吸法</a>）
KEYWORD_LINK_PREFIX = "kw:"
#: 鼠标在关键词上停留多久才弹说明（毫秒）——「悬放一会儿才显示」
#: 风味小字（游戏里的小字 flavor）样式：小号、灰、斜体
FLAVOR_STYLE = 'color: #8a9bb5; font-size: 11px; font-style: italic;'

KEYWORD_HOVER_DELAY_MS = 600

#: 罪人选择页：照游戏原版排成 2 行 × 6 列
SINNER_COLUMNS = 6
#: 罪人卡尺寸（竖版，卡面 3:4 —— 灰机卡面是 16:9，按此比例居中裁竖）
SINNER_CARD_W = 168
SINNER_CARD_IMG_H = 224
#: 竖版裁剪的水平锚点（0=靠左，0.5=居中，1=靠右）
SINNER_CROP_ANCHOR_X = 0.5


def portrait_path(app_data_dir: Path, kind: str, entity_id: int) -> Path | None:
    """头像文件（由 scripts/extract_portraits.py 抽取，缺失则返回 None）。"""
    sub = "identity" if kind == KIND_PERSONALITY else "ego"
    for ext in (".png", ".webp", ".jpg"):
        p = Path(app_data_dir) / PORTRAIT_DIR_NAME / sub / f"{entity_id}{ext}"
        if p.is_file():
            return p
    return None


def vertical_pixmap(path: Path | None, width: int, height: int,
                    anchor_x: float = SINNER_CROP_ANCHOR_X):
    """把横版卡面裁成竖版（按比例放大到铺满，再以 anchor_x 为水平锚点居中裁切）。"""
    if path is None:
        return None
    try:
        from PySide6.QtGui import QPixmap

        pix = QPixmap(str(path))
    except Exception:  # noqa: BLE001
        return None
    if pix.isNull():
        return None
    scaled = pix.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation)
    if scaled.width() <= width and scaled.height() <= height:
        return scaled
    left = int(round((scaled.width() - width) * min(max(anchor_x, 0.0), 1.0)))
    top = max(0, (scaled.height() - height) // 2)
    return scaled.copy(left, top, width, height)


class _Card(QFrame):
    """可点击卡片：头像（有则显示）+ 标题 + 副标题。

    ``vertical=True``：竖版卡（罪人选择页）——卡面在上、名字在卡面下方居中。
    """

    clicked = Signal()

    def __init__(self, title: str, subtitle: str, badge: str = "", portrait: Path | None = None,
                 parent=None, vertical: bool = False):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if vertical:
            self._build_vertical(title, subtitle, portrait)
            return
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)

        thumb = QLabel()
        thumb.setFixedSize(64, 64)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if portrait is not None:
            pix = None
            try:
                from PySide6.QtGui import QPixmap

                pix = QPixmap(str(portrait)).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation)
            except Exception:  # noqa: BLE001
                pix = None
            if pix is not None and not pix.isNull():
                thumb.setPixmap(pix)
        if thumb.pixmap() is None or thumb.pixmap().isNull():
            thumb.setText((title or "?")[:1])
            thumb.setStyleSheet(
                f"background: {theme.PANEL}; color: {theme.TEXT_DIM}; border-radius: 6px;"
                f" font-size: 22px; font-weight: 600;"
            )
        lay.addWidget(thumb)

        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(title)
        name.setStyleSheet(f"color: {theme.TEXT}; font-weight: 600;")
        name.setWordWrap(True)
        sub = QLabel(subtitle)
        sub.setObjectName("dim")
        sub.setWordWrap(True)
        col.addWidget(name)
        col.addWidget(sub)
        lay.addLayout(col, 1)
        if badge:
            tag = QLabel(badge)
            tag.setObjectName("dim")
            tag.setStyleSheet(f"color: {theme.ACCENT};")
            lay.addWidget(tag, 0, Qt.AlignmentFlag.AlignTop)

    def _build_vertical(self, title: str, subtitle: str, portrait: Path | None) -> None:
        """竖版卡：竖裁卡面 + 底部居中的罪人名（下面一行小字计数）。"""
        self.setFixedSize(SINNER_CARD_W, SINNER_CARD_IMG_H + 44)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 4)
        lay.setSpacing(2)

        art = QLabel()
        art.setFixedSize(SINNER_CARD_W, SINNER_CARD_IMG_H)
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = vertical_pixmap(portrait, SINNER_CARD_W, SINNER_CARD_IMG_H, SINNER_CROP_ANCHOR_X)
        if pix is not None and not pix.isNull():
            art.setPixmap(pix)
        else:  # 没有卡面就退回首字占位（不至于空一块）
            art.setText((title or "?")[:1])
            art.setStyleSheet(f"background: {theme.PANEL}; color: {theme.TEXT_DIM};"
                              f" font-size: 40px; font-weight: 600;")
        lay.addWidget(art)

        name = QLabel(title)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600; font-size: 13px;")
        lay.addWidget(name)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("dim")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
            lay.addWidget(sub)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            # 延迟触发：回调会重建页面（删除当前卡片），不能在自身事件处理里做
            QTimer.singleShot(0, self.clicked.emit)


class CodexEditDialog(QDialog):
    """单条文本编辑：零协原文 / 英语原文（只读）+ 自定义文本（可改）。"""

    def __init__(self, parent, ctx, ref: EntryRef, title: str = "", subtitle: str = ""):
        super().__init__(parent)
        self.ctx = ctx
        self.ref = ref
        self.saved = False
        self.setWindowTitle(title or "编辑文本")
        self.resize(700, 420)

        lay = QVBoxLayout(self)
        head = QLabel(title)
        head.setObjectName("title")
        head.setWordWrap(True)
        lay.addWidget(head)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("dim")
            sub.setWordWrap(True)
            lay.addWidget(sub)

        original, err = ctx.original_of(ref)
        en_text, en_note = ctx.baseline_of(ref)
        entry = ctx.profile.get(ref)

        box = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("零协原文（只读）"))
        self.original_view = QPlainTextEdit(original if original is not None else f"（读取失败：{err}）")
        self.original_view.setReadOnly(True)
        left.addWidget(self.original_view, 1)
        right = QVBoxLayout()
        right.addWidget(QLabel("自定义文本"))
        self.custom_edit = QPlainTextEdit(entry.value if entry else "")
        right.addWidget(self.custom_edit, 1)
        box.addLayout(left, 1)
        box.addLayout(right, 1)
        lay.addLayout(box, 1)

        self.en_label = QLabel(("英语：" + en_text) if en_text else f"英语：{en_note or '（无）'}")
        self.en_label.setObjectName("dim")
        self.en_label.setWordWrap(True)
        lay.addWidget(self.en_label)

        btns = QHBoxLayout()
        self.restore_btn = QPushButton("还原为原文")
        save = QPushButton("保存")
        save.setObjectName("primary")
        close = QPushButton("关闭")
        btns.addWidget(self.restore_btn)
        btns.addStretch(1)
        btns.addWidget(close)
        btns.addWidget(save)
        lay.addLayout(btns)

        save.clicked.connect(self._save)
        self.restore_btn.clicked.connect(self._restore)
        close.clicked.connect(self.reject)

    def _save(self) -> None:
        res = self.ctx.upsert_entry(self.ref, self.custom_edit.toPlainText())
        if not res.ok:
            info(self, "保存失败", res.message)
            return
        self.saved = True
        self.accept()

    def _restore(self) -> None:
        text, err = self.ctx.original_of(self.ref)
        if text is None:
            info(self, "无法读取原文", err or "")
            return
        res = self.ctx.upsert_entry(self.ref, text)
        if not res.ok:
            info(self, "还原失败", res.message)
            return
        self.saved = True
        self.accept()


class KeywordEditDialog(QDialog):
    """关键词 / 状态编辑：一次改 name（名称）/ desc（说明）/ flavor（风味文本）。

    与技能文本编辑的区别：这里改的是关键词表里的那条记录
    （BattleKeywords-*.json / Bufs-*.json / SkillTag.json），
    技能说明里的 [id] 一个字符都不会动——想改技能说明请点正文空白处。

    同一个 id 在多张表里都有记录时（例如 BattleKeywords 与 Bufs 都写了「业」），
    勾选「同时更新」会把这些记录一起改掉：游戏里的状态提示可能读的是 Bufs。
    """

    def __init__(self, parent, ctx, token: str, records: list, name: str = ""):
        super().__init__(parent)
        self.ctx = ctx
        self.token = token
        self.records = list(records or [])
        self.saved = False
        self.targets = keywords.edit_targets(self.records)   # 字段 → 含该字段的记录
        self.editors: dict = {}
        self._originals: dict[str, str] = {}

        title = name or self._display_name() or token
        self.setWindowTitle(f"关键词 · {title}")
        self.resize(780, 560)

        lay = QVBoxLayout(self)
        head = QLabel(f"{title}　[{token}]")
        head.setObjectName("title")
        head.setWordWrap(True)
        lay.addWidget(head)

        files = "、".join(dict.fromkeys(r.file for r in self.records))
        sub = QLabel(
            f"记录来源：{files}\n"
            f"这里改的是关键词表本身；技能 / 硬币文本里的 [{token}] 不会被改动，"
            f"要改技能文本请点正文空白处。保存后写入方案，需「应用到游戏」才生效。"
        )
        sub.setObjectName("dim")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        for field in keywords.EDITABLE_FIELDS:
            recs = self.targets.get(field) or []
            if not recs:
                continue
            self._originals[field] = recs[0].text_of(field)
            lab = QLabel(keywords.FIELD_LABELS.get(field, field))
            lab.setObjectName("dim")
            lay.addWidget(lab)
            if field == "name":
                editor = QLineEdit(self._current(field, recs[0]))
            else:
                editor = QPlainTextEdit(self._current(field, recs[0]))
                editor.setMinimumHeight(96)
            self.editors[field] = editor
            lay.addWidget(editor, 0 if field == "name" else 1)

        others = self._other_files()
        self.sync_cb = QCheckBox(f"同时更新同 id 的其他记录（{'、'.join(others)}）")
        self.sync_cb.setChecked(bool(others))     # 默认勾选：一处改名，各处一致
        self.sync_cb.setVisible(bool(others))
        self.sync_cb.setToolTip("同一 id 在 BattleKeywords / Bufs / SkillTag 里可能都有记录，"
                                "游戏里的状态提示读的可能是 Bufs")
        lay.addWidget(self.sync_cb)

        btns = QHBoxLayout()
        restore = QPushButton("还原为原文")
        close = QPushButton("关闭")
        save = QPushButton("保存")
        save.setObjectName("primary")
        btns.addWidget(restore)
        btns.addStretch(1)
        btns.addWidget(close)
        btns.addWidget(save)
        lay.addLayout(btns)

        save.clicked.connect(self._save)
        restore.clicked.connect(self._restore)
        close.clicked.connect(self.reject)

    # ---- 数据 ----

    def _display_name(self) -> str:
        return next((r.name for r in self.records if r.name), "")

    def _other_files(self) -> list[str]:
        """除主记录外，同一个 id 还出现在哪些文件里。"""
        out: list[str] = []
        for field in self.editors or keywords.EDITABLE_FIELDS:
            for rec in (self.targets.get(field) or [])[1:]:
                if rec.file not in out:
                    out.append(rec.file)
        return out

    def _refs_for(self, field: str, sync: bool) -> list[EntryRef]:
        """该字段要写入的记录（sync=False 时只改主记录）。"""
        recs = self.targets.get(field) or []
        if not sync:
            recs = recs[:1]
        return [EntryRef(file=r.file, id=r.id, record_index=r.record_index,
                         field_path=[{"k": field}]) for r in recs]

    def _profile_entry(self, ref: EntryRef):
        profile = getattr(self.ctx, "profile", None)
        if profile is None:
            return None
        try:
            return profile.get(ref)
        except Exception:  # noqa: BLE001  方案读不到就当没改过
            return None

    def _current(self, field: str, rec) -> str:
        """编辑框初值：方案里已改过的值优先，否则用原文。"""
        refs = self._refs_for(field, False)
        entry = self._profile_entry(refs[0]) if refs else None
        return entry.value if entry is not None else rec.text_of(field)

    # ---- 按钮 ----

    def _sync(self) -> bool:
        return bool(self.sync_cb.isChecked())

    def _save(self) -> None:
        for field, editor in self.editors.items():
            value = editor.text() if isinstance(editor, QLineEdit) else editor.toPlainText()
            original = self._originals.get(field, "")
            refs = self._refs_for(field, False)
            if value == original and refs and self._profile_entry(refs[0]) is None:
                continue                      # 没动过：不往方案里塞多余条目
            for ref in self._refs_for(field, self._sync()):
                res = self.ctx.upsert_entry(ref, value)
                if not getattr(res, "ok", True):
                    info(self, "保存失败", getattr(res, "message", "") or "写入方案失败。")
                    return
        self.saved = True
        self.accept()

    def _restore(self) -> None:
        """还原为原文：把这些记录在方案里的修改清掉。"""
        for field in self.editors:
            for ref in self._refs_for(field, self._sync()):
                self.ctx.remove_entry(ref)
        self.saved = True
        self.accept()


class CodexPage(QWidget):
    """图鉴主页面。"""

    close_requested = Signal()
    story_requested = Signal(object)  # entity_key：进剧本模式读人格剧情

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.level = 1                 # 1=罪人 2=人格/EGO 3=详情
        self.sinner = ""
        self.kind = KIND_PERSONALITY
        self.entity: codex.CodexEntity | None = None
        self.show_format = True        # 页头「显示格式」开关：默认按游戏格式渲染
        self.show_keywords = True      # 页头「关键词名」开关：默认把 [id] 显示成中文名
        self._kw_map: dict | None = None   # 关键词表（按零协包懒加载一次）
        self._kw_records: dict | None = None   # 关键词原始记录（编辑 / tooltip 用）
        self._hover_token: dict[QLabel, str] = {}   # 当前鼠标悬停的关键词（label → token）
        self._kw_docs: dict[QLabel, tuple] = {}     # label → 命中测试用的镜像文档缓存
        # 悬停一会儿才弹关键词说明：扫过时不打扰
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(KEYWORD_HOVER_DELAY_MS)
        self._hover_timer.timeout.connect(self._show_hover_tip)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)

        head = QHBoxLayout()
        back = QPushButton("← 返回")
        back.clicked.connect(self._go_back)
        self.crumb = QLabel("人格图鉴")
        self.crumb.setObjectName("title")
        self.format_btn = QPushButton("显示格式")
        self.format_btn.setCheckable(True)
        self.format_btn.setChecked(True)   # 默认勾选：有格式就渲染格式
        self.format_btn.setToolTip(
            "勾选：按游戏里的颜色 / 字号 / 高亮 / 粗体等格式渲染\n"
            "取消勾选：只显示纯文本（标签被去掉，不会看到 <color=…> 这类裸标签）\n"
            "编辑框里保存的始终是原始文本"
        )
        self.format_btn.toggled.connect(self._on_show_format)
        self.keyword_btn = QPushButton("关键词名")
        self.keyword_btn.setCheckable(True)
        self.keyword_btn.setChecked(True)  # 默认勾选：把 [Breath] 这类 id 显示成中文名
        self.keyword_btn.setToolTip(
            "勾选：技能说明 / 硬币效果 / 剧情 / 语音里的关键词 id 显示成游戏里的中文名\n"
            "（如 [Breath] →「呼吸法」，用蓝色标出），鼠标悬停可看 id 明细\n"
            "取消勾选：显示原始 [id]\n"
            "关键词 id 本身不会被改动，编辑框里保存的始终是原始文本"
        )
        self.keyword_btn.toggled.connect(self._on_show_keywords)
        self.story_btn = QPushButton("在剧本模式打开剧情")
        self.story_btn.hide()
        self.story_btn.clicked.connect(lambda: self.entity and self.story_requested.emit(self.entity.entity_key))
        head.addWidget(back)
        head.addWidget(self.crumb, 1)
        head.addWidget(self.format_btn)
        head.addWidget(self.keyword_btn)
        head.addWidget(self.story_btn)
        root.addLayout(head)

        self.body = QScrollArea()
        self.body.setWidgetResizable(True)
        root.addWidget(self.body, 1)

        self._show_sinners()

    # ---------- 导航 ----------

    def _set_body(self, widget: QWidget) -> None:
        # 重建页面：清掉挂在旧标签上的悬停状态与镜像文档（标签随后会被销毁）
        self._hover_timer.stop()
        self._hover_token.clear()
        self._kw_docs.clear()
        self.body.setWidget(widget)

    # ---------- 富文本渲染 ----------

    def _on_show_format(self, on: bool) -> None:
        """页头「显示格式」开关：就地重建详情页，套用新的渲染方式。"""
        self.show_format = bool(on)
        if self.level == 3 and self.entity is not None:
            self._show_entity(self.entity.entity_key)

    def _on_show_keywords(self, on: bool) -> None:
        """页头「关键词名」开关：切换 [id] / 中文名的显示，重建详情页。"""
        self.show_keywords = bool(on)
        if self.level == 3 and self.entity is not None:
            self._show_entity(self.entity.entity_key)

    def _keyword_map(self) -> dict:
        """关键词表（id → 中文名）：按零协包懒加载一次，失败降级为空表。"""
        if self._kw_map is None:
            try:
                self._kw_map = keywords.load_map(Path(self.ctx.env.llc_pack_dir))
            except Exception:  # noqa: BLE001  显示层不该因为关键词表挂掉
                self._kw_map = {}
        return self._kw_map

    def _keyword_records(self) -> dict:
        """关键词原始记录（id → [记录…]）：按零协包懒加载一次，失败降级为空表。"""
        if self._kw_records is None:
            try:
                self._kw_records = keywords.load_records(Path(self.ctx.env.llc_pack_dir))
            except Exception:  # noqa: BLE001  显示层不该因为关键词表挂掉
                self._kw_records = {}
        return self._kw_records

    def _tip_text(self, tip: str, plain_text: str, text: str, mapping: dict) -> str:
        """tooltip：提示语 + 纯文本 + 这条文本用到的关键词明细（id + 中文名，最多 8 条）。"""
        lines = [tip] if tip else []
        lines.append(plain_text)
        found = keywords.tokens_in(text, mapping)
        if found:
            names = "；".join(
                f"[{it['id']}] = {it['name'] or '（无中文名）'}" for it in found[:TOKEN_TIP_LIMIT])
            lines.append("关键词：" + names)
            if len(found) > TOKEN_TIP_LIMIT:
                lines.append(f"（另有 {len(found) - TOKEN_TIP_LIMIT} 个关键词未列出）")
        return "\n".join(line for line in lines if line)

    def _set_rich_text(self, label: QLabel, text: str, prefix: str = "", tip: str = "") -> None:
        """把一段零协原文渲染进 QLabel（含关键词 id → 中文名的显示层替换）。

        - 关键词：勾选「关键词名」时 [Breath] → 中文名（富文本里用 KEYWORD_COLOR 标出），
          取消勾选时原样显示 [id]；未知 token 一律原样保留（keywords 模块保证）；
        - 格式：勾选「显示格式」且有格式标签 / 有命中的关键词 → 富文本
          （keywords.render_html 内部就是「先替换再 richtext.to_html」）；
        - 其余情况 → 纯文本（richtext.plain，标签被去掉，不留裸标签）；
        - tooltip：纯文本 + 关键词明细；悬停时不会看到裸格式标签。
        """
        mapping = self._keyword_map()
        mode = "name" if self.show_keywords else "raw"
        shown = keywords.substitute(text, mapping, mode)
        plain_text = richtext.plain(shown)
        keyword_hit = plain_text != richtext.plain(text)   # 有没有真的替换掉 token
        if self.show_format and (keyword_hit or richtext.has_format(text)):
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setText(prefix + keywords.render_html(text, mapping, mode, KEYWORD_LINK_PREFIX))
        else:
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setText(prefix + plain_text)
        label.setToolTip(self._tip_text(tip, plain_text, text, mapping))
        self._wire_keyword_hover(label)

    # ---------- 关键词：悬停看说明 / 点击进关键词编辑 ----------

    def _wire_keyword_hover(self, label: QLabel) -> None:
        """给带关键词锚点的标签装上悬停 / 点击处理（没有锚点就什么都不做）。

        用自建镜像文档做命中测试，而不是 QLabel 的 linkHovered / linkActivated：
        后者在离屏 / 布局子控件场景下不可靠，而镜像文档的排版与 QLabel 完全一致
        （documentMargin=0、同样的字体与宽度，实测 heightForWidth 逐像素吻合）。
        """
        self._kw_docs.pop(label, None)
        if KEYWORD_LINK_PREFIX not in (label.text() or ""):
            return
        label.setMouseTracking(True)                      # 不按键也要收到 MouseMove
        label.installEventFilter(self)
        self._hover_token.pop(label, None)

    def _keyword_ranges(self, label: QLabel) -> list[tuple[int, int, str]]:
        """标签里关键词锚点的字符区间 [(起点, 终点, token), …]（按显示文本的下标）。"""
        doc = self._mirror_doc(label)
        ranges: list[tuple[int, int, str]] = []
        offset = 0
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    text = frag.text()
                    fmt = frag.charFormat()
                    href = fmt.anchorHref() if fmt.isAnchor() else ""
                    if href.startswith(KEYWORD_LINK_PREFIX):
                        ranges.append((offset, offset + len(text),
                                       href[len(KEYWORD_LINK_PREFIX):]))
                    offset += len(text)
                it += 1
            block = block.next()
        return ranges

    def _mirror_doc(self, label: QLabel) -> QTextDocument:
        """按标签当前文本 / 宽度 / 字体建（或复用）镜像文档，用于命中测试。"""
        html = label.text() or ""
        width = max(0, label.contentsRect().width())
        cached = self._kw_docs.get(label)
        if cached is not None and cached[0] == html and cached[1] == width:
            return cached[2]
        doc = QTextDocument()
        doc.setDefaultFont(label.font())
        doc.setDocumentMargin(0)                          # 与 QLabel 内部文档一致
        doc.setHtml(html)
        if label.wordWrap() and width > 0:
            doc.setTextWidth(width)
        self._kw_docs[label] = (html, width, doc)
        return doc

    def _token_at(self, label: QLabel, pos) -> str:
        """标签坐标 → 该处关键词 token（不在关键词上返回空串）。"""
        try:
            doc = self._mirror_doc(label)
            # QLabel 默认垂直居中：标签比文本高时把坐标补回来
            dy = max(0.0, (label.height() - doc.size().height()) / 2.0)
            index = doc.documentLayout().hitTest(
                QPointF(float(pos.x()), max(0.0, float(pos.y()) - dy)),
                Qt.HitTestAccuracy.ExactHit)
        except Exception:  # noqa: BLE001  命中测试失败不该影响点击
            return ""
        if index is None or index < 0:
            return ""
        for start, end, token in self._keyword_ranges(label):
            if start <= index < end:
                return token
        return ""

    def _clear_hover(self, label=None) -> None:
        """清掉悬停状态（鼠标移开 / 标签隐藏 / 页面重建）。"""
        if label is None:
            self._hover_token.clear()
        else:
            self._hover_token.pop(label, None)
        if not self._hover_token:
            self._hover_timer.stop()
            QToolTip.hideText()

    def _show_hover_tip(self) -> None:
        """悬停计时到点：给鼠标下那个关键词弹说明（desc + 灰色 flavor）。"""
        for label, token in list(self._hover_token.items()):
            self._popup_keyword_tip(label, token)
            break

    def _popup_keyword_tip(self, label: QLabel, token: str) -> None:
        """弹关键词说明；没有说明 / flavor 时不弹（例如只有名字的技能标签）。"""
        records = self._keyword_records().get(token) or []
        html = keywords.tooltip_html(token, records)
        if html:
            QToolTip.showText(QCursor.pos(), html, label)   # 贴着鼠标显示

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        """关键词交互：MouseMove 记悬停 + 计时，ToolTip 让位给关键词说明，左键点关键词进编辑。"""
        etype = event.type()
        if isinstance(obj, QLabel) and KEYWORD_LINK_PREFIX in (obj.text() or ""):
            if etype == QEvent.Type.MouseMove:
                token = self._token_at(obj, event.position().toPoint())
                if token:
                    obj.setCursor(Qt.CursorShape.PointingHandCursor)
                    self._hover_token[obj] = token
                    self._hover_timer.start()             # 悬停一段时间才弹
                else:
                    obj.setCursor(Qt.CursorShape.ArrowCursor)
                    self._clear_hover(obj)
            elif etype in (QEvent.Type.Leave, QEvent.Type.Hide):
                self._clear_hover(obj)
            elif etype == QEvent.Type.ToolTip:
                token = self._hover_token.get(obj, "")
                if token:
                    # 关键词自己说明自己：压掉普通 tooltip（否则 Qt 的提示会把它顶掉）
                    self._popup_keyword_tip(obj, token)
                    return True
            elif etype == QEvent.Type.MouseButtonPress:
                token = self._token_at(obj, event.position().toPoint())
                if token and event.button() == Qt.MouseButton.LeftButton:
                    event.accept()
                    self._clear_hover(obj)
                    self._open_keyword(token)             # 点关键词 = 改关键词，不是改技能文本
                    return True
        return super().eventFilter(obj, event)

    def _open_keyword(self, token: str) -> None:
        """打开关键词 / 状态的 name / desc / flavor 编辑（延迟到事件循环，避免重建页面时删控件）。"""
        records = self._keyword_records().get(token) or []
        if not records:
            info(self, "找不到关键词记录", f"[{token}] 在 BattleKeywords / Bufs / SkillTag 里都没有记录。")
            return
        QTimer.singleShot(0, lambda: self._edit_keyword(token, records))

    def _edit_keyword(self, token: str, records: list) -> None:
        """关键词编辑对话框：改 name / desc / flavor（写进方案，应用到游戏才生效）。"""
        dlg = KeywordEditDialog(self, self.ctx, token, records)
        if safe_exec(dlg) == QDialog.DialogCode.Accepted and dlg.saved:
            self.ctx.save_profile()
            info(self, "已保存", "关键词修改已写入方案，记得「应用到游戏」才会生效。")
            key = self.entity.entity_key if self.entity is not None else None
            if key:
                QTimer.singleShot(0, lambda k=key: self._show_entity(k))

    def _go_back(self) -> None:
        if self.level == 3:
            self._show_entities(self.sinner, self.kind)
        elif self.level == 2:
            self._show_sinners()
        else:
            self.close_requested.emit()

    def _grid_page(self, title: str, cards: list[QWidget], columns: int = 3) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(8)
        if title:
            lab = QLabel(title)
            lab.setObjectName("dim")
            lay.addWidget(lab)
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, card in enumerate(cards):
            grid.addWidget(card, i // columns, i % columns)
        lay.addLayout(grid)
        lay.addStretch(1)
        return page

    def refresh(self) -> None:
        """索引重建 / 方案变化后按当前层级重新渲染（不会丢用户所在的位置）。"""
        if self.level == 3 and self.entity is not None:
            self._show_entity(self.entity.entity_key)
        elif self.level == 2 and self.sinner:
            self._show_entities(self.sinner, self.kind)
        else:
            self._show_sinners()

    def _show_sinners(self) -> None:
        self.level = 1
        self.sinner = ""
        self.entity = None
        self.story_btn.hide()
        self.crumb.setText("人格图鉴 · 选择罪人")
        cards = []
        for code, name in sorted(SINNER_NAMES.items(), key=lambda kv: int(kv[0])):
            n = len(self.ctx.search.list_entities(KIND_PERSONALITY, code))
            e = len(self.ctx.search.list_entities(KIND_EGO, code))
            # 罪人本身没有独立卡图：用他的基础人格（1<罪人码>01）的卡面
            base_id = int(f"1{code}01")
            portrait = portrait_path(self.ctx.app_paths.data_dir, KIND_PERSONALITY, base_id)                 or portrait_path(self.ctx.app_paths.data_dir, "sinner", int(code))
            card = _Card(name, f"人格 {n} · E.G.O {e}", portrait=portrait, vertical=True)
            card.setToolTip(f"{name}：人格 {n} · E.G.O {e}")
            card.clicked.connect(lambda c=code: self._show_entities(c, KIND_PERSONALITY))
            cards.append(card)
        # 照游戏原版：2 行 × 6 列
        self._set_body(self._grid_page("选择罪人（12 位）", cards, columns=SINNER_COLUMNS))

    def _show_entities(self, sinner: str, kind: str) -> None:
        self.level = 2
        self.sinner = sinner
        self.kind = kind
        self.entity = None
        self.story_btn.hide()
        name = SINNER_NAMES.get(sinner, sinner)
        self.crumb.setText(f"人格图鉴 · {name}")

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(8)

        tabs = QHBoxLayout()
        for k, label in ((KIND_PERSONALITY, "人格"), (KIND_EGO, "E.G.O")):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(k == kind)
            btn.clicked.connect(lambda _c=False, kk=k: self._show_entities(sinner, kk))
            tabs.addWidget(btn)
        tabs.addStretch(1)
        lay.addLayout(tabs)

        entities = self.ctx.search.list_entities(kind, sinner)
        cards = []
        for e in entities:
            counts = []
            if e.get("skill_count"):
                counts.append(f"技能 {e['skill_count']}")
            if e.get("passive_count"):
                counts.append(f"被动 {e['passive_count']}")
            if e.get("story_count"):
                counts.append(f"剧情 {e['story_count']}")
            if e.get("voice_count"):
                counts.append(f"语音 {e['voice_count']}")
            subtitle = (self._override(e, "title") or e.get("title") or "").replace("\n", " ")
            subtitle = subtitle or (e.get("desc") or "")
            badge = " · ".join(counts[:3])
            card = _Card(self._override(e, "name") or e.get("name") or "", f"{subtitle}", badge=badge,
                         portrait=portrait_path(self.ctx.app_paths.data_dir, kind, e["entity_id"]))
            card.clicked.connect(lambda key=e["entity_key"]: self._show_entity(key))
            cards.append(card)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._grid_page("", cards, columns=2))
        lay.addWidget(scroll, 1)
        self._set_body(page)

    def _show_entity(self, entity_key: str) -> None:
        summary = self.ctx.search.entity_summary(entity_key)
        if not summary:
            info(self, "找不到实体", entity_key)
            return
        self.level = 3
        self.entity = codex.build_entity(Path(self.ctx.env.llc_pack_dir), summary)
        self._apply_overlay(self.entity)
        ent = self.entity
        self.crumb.setText(f"人格图鉴 · {ent.sinner_name} · {ent.name}（{ent.ordinal}）")

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(8)

        tools = QHBoxLayout()
        self.name_btn = QPushButton("改名称 ▾")
        self.name_btn.setToolTip("修改这个人格／E.G.O 的名称、罪人名、简介（写进方案，零协原文不动）")
        menu = QMenu(self.name_btn)
        for item in ent.self_texts:
            act = menu.addAction(item.label)
            act.triggered.connect(lambda _c=False, it=item: self._edit_self_text(it))
        self.name_btn.setMenu(menu)
        self.name_btn.setEnabled(bool(ent.self_texts))
        tools.addWidget(self.name_btn)
        rep_btn = QPushButton("一键替换")
        rep_btn.setToolTip("在这个人格／E.G.O 的全部文本里批量查找替换")
        rep_btn.clicked.connect(lambda _c=False, e=ent: self._open_entity_replace(e))
        tools.addWidget(rep_btn)
        tools.addStretch(1)
        lay.addLayout(tools)

        info_row = QLabel(self._entity_headline(ent))
        info_row.setObjectName("dim")
        info_row.setWordWrap(True)
        lay.addWidget(info_row)

        tabs = QTabWidget()
        if ent.kind == KIND_PERSONALITY:
            tabs.addTab(self._skills_tab(ent), f"技能（{len(ent.skills)}）· 被动（{len(ent.passives)}）")
            tabs.addTab(self._story_tab(ent), f"剧情（{len(ent.story_lines)} 行）")
        else:
            tabs.addTab(self._skills_tab(ent), f"技能（{len(ent.skills)}）· 被动（{len(ent.passives)}）")
        tabs.addTab(self._voice_tab(ent), f"语音（{len(ent.voices)} 条）")
        tabs.addTab(self._bubble_tab(ent), f"战中气泡（{len(ent.bubbles)}）")
        tabs.currentChanged.connect(lambda _i: self.story_btn.setVisible(
            ent.kind == KIND_PERSONALITY and tabs.currentIndex() == 1))
        lay.addWidget(tabs, 1)
        self._set_body(page)

    @staticmethod
    def _entity_headline(ent: codex.CodexEntity) -> str:
        bits = [ent.ordinal]
        if ent.title:
            bits.append(ent.title.replace("\n", " "))
        if ent.season_label:
            bits.append(ent.season_label)
        if ent.acq_label:
            bits.append(ent.acq_label)
        if ent.name_en:
            bits.append(ent.name_en)
        text = " · ".join(b for b in bits if b)
        if ent.get_conditions:
            text += "\n获取：" + "；".join(ent.get_conditions)
        return text

    # ---------- 三页签 ----------

    def _skills_tab(self, ent: codex.CodexEntity) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(6)
        if not ent.skills and not ent.passives:
            lay.addWidget(QLabel("（游戏本体没有这个人格的技能文本）"))
        for i, skill in enumerate(ent.skills, start=1):
            card = QFrame()
            card.setObjectName("panel")
            cl = QVBoxLayout(card)
            cl.setSpacing(4)
            head = QPushButton(f"{i}. {skill.label}    · {len(skill.levels)} 级 · {skill.coin_count} 硬币")
            head.setCheckable(True)
            head.setStyleSheet("text-align: left; font-weight: 600;")
            cl.addWidget(head)
            detail = QWidget()
            dl = QVBoxLayout(detail)
            dl.setSpacing(4)
            for lv in skill.levels:
                row = QLabel()
                row.setObjectName("dim")
                row.setWordWrap(True)
                row.setCursor(Qt.CursorShape.PointingHandCursor)
                # 等级说明按游戏格式渲染（前缀 Lv 序号保持纯文本）
                self._set_rich_text(row, lv.desc or "（无说明）", prefix=f"Lv{lv.level}　",
                                    tip="点击编辑该等级说明")
                row.mousePressEvent = (  # noqa: ARG005
                    lambda _e, s=skill, l=lv: self._edit(s.file, s.record_index, s.skill_id,
                                                         l.desc_fp, f"{skill.label} · Lv{l.level} 说明")
                )
                dl.addWidget(row)
                for text, fp in lv.coins:
                    coin = QLabel()
                    coin.setObjectName("dim")
                    coin.setWordWrap(True)
                    coin.setCursor(Qt.CursorShape.PointingHandCursor)
                    self._set_rich_text(coin, text or "", prefix="　◦ ",
                                        tip="点击编辑该硬币效果")
                    coin.mousePressEvent = (  # noqa: ARG005
                        lambda _e, s=skill, f=fp: self._edit(s.file, s.record_index, s.skill_id, f,
                                                             f"{skill.label} · 硬币效果")
                    )
                    dl.addWidget(coin)
                if lv.flavor:
                    flav = QLabel()
                    flav.setWordWrap(True)
                    flav.setCursor(Qt.CursorShape.PointingHandCursor)
                    flav.setStyleSheet(FLAVOR_STYLE)
                    self._set_rich_text(flav, lv.flavor, prefix="　", tip="点击编辑这句风味文本")
                    flav.mousePressEvent = (  # noqa: ARG005
                        lambda _e, s=skill, l=lv: self._edit(s.file, s.record_index, s.skill_id,
                                                             l.flavor_fp,
                                                             f"{skill.label} · Lv{l.level} 风味文本")
                    )
                    dl.addWidget(flav)
            detail.setVisible(False)
            head.toggled.connect(detail.setVisible)
            cl.addWidget(detail)
            lay.addWidget(card)

        if ent.passives:
            ptitle = QLabel(f"被动能力（{len(ent.passives)}）")
            ptitle.setObjectName("title")
            lay.addWidget(ptitle)
            for psv in ent.passives:
                pcard = QFrame()
                pcard.setObjectName("panel")
                pcl = QVBoxLayout(pcard)
                pcl.setSpacing(2)
                pname = QLabel()
                pname.setWordWrap(True)
                pname.setCursor(Qt.CursorShape.PointingHandCursor)
                self._set_rich_text(pname, psv.name or "（无名称）", prefix="◆ ", tip="点击修改被动名称")
                pname.mousePressEvent = (  # noqa: ARG005
                    lambda _e, p=psv: self._edit(p.file, p.record_index, p.record_id, p.name_fp,
                                                 f"被动 · {p.label} 名称")
                )
                pcl.addWidget(pname)
                pdesc = QLabel()
                pdesc.setWordWrap(True)
                pdesc.setCursor(Qt.CursorShape.PointingHandCursor)
                self._set_rich_text(pdesc, psv.desc or "（无说明）", prefix="　", tip="点击修改被动说明")
                pdesc.mousePressEvent = (  # noqa: ARG005
                    lambda _e, p=psv: self._edit(p.file, p.record_index, p.record_id, p.desc_fp,
                                                 f"被动 · {p.label} 说明")
                )
                pcl.addWidget(pdesc)
                if psv.flavor:
                    pflav = QLabel()
                    pflav.setWordWrap(True)
                    pflav.setCursor(Qt.CursorShape.PointingHandCursor)
                    pflav.setStyleSheet(FLAVOR_STYLE)
                    self._set_rich_text(pflav, psv.flavor, prefix="　", tip="点击编辑这句风味文本")
                    pflav.mousePressEvent = (  # noqa: ARG005
                        lambda _e, p=psv: self._edit(p.file, p.record_index, p.record_id,
                                                     p.flavor_fp, f"被动 · {p.label} 风味文本")
                    )
                    pcl.addWidget(pflav)
                lay.addWidget(pcard)
        lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _story_tab(self, ent: codex.CodexEntity) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(2)
        if not ent.story_lines:
            hint = QLabel("（游戏本体没有这个人格的剧情文本：LCB 初始人格、活动特殊人格没有独立剧情）")
            hint.setWordWrap(True)
            hint.setObjectName("dim")
            lay.addWidget(hint)
        for line in ent.story_lines:
            row = QFrame()
            row.setObjectName("panel")
            rl = QVBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            rl.setSpacing(0)
            who = QLabel((line.teller or "旁白") + (f"　〔{line.title}〕" if line.title else ""))
            who.setStyleSheet(f"color: {theme.ACCENT if line.teller else theme.TEXT_DIM}; font-size: 11px;")
            text = QLabel()
            text.setWordWrap(True)
            self._set_rich_text(text, line.text or "", tip="点击编辑该行")
            rl.addWidget(who)
            rl.addWidget(text)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setToolTip("点击编辑该行")
            row.mousePressEvent = (  # noqa: ARG005
                lambda _e, l=line: self._edit(l.file, l.record_index, l.record_id, l.fp,
                                              f"人格剧情 · 第{l.record_index + 1} 行")
            )
            lay.addWidget(row)
        lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _voice_tab(self, ent: codex.CodexEntity) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setSpacing(8)
        if not ent.voices:
            grid.addWidget(QLabel("（没有语音文本）"), 0, 0)
        for i, voice in enumerate(ent.voices):
            cell = QFrame()
            cell.setObjectName("panel")
            cell.setMinimumHeight(88)
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(8, 6, 8, 6)
            cl.setSpacing(2)
            cat = QLabel(voice.category or "语音")
            cat.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600; font-size: 11px;")
            body = QLabel()
            body.setWordWrap(True)
            self._set_rich_text(body, voice.text or "", tip="点击修改这句台词")
            cl.addWidget(cat)
            cl.addWidget(body, 1)
            cell.setCursor(Qt.CursorShape.PointingHandCursor)
            cell.setToolTip("点击修改这句台词")
            cell.mousePressEvent = (  # noqa: ARG005
                lambda _e, v=voice: self._edit(v.file, v.record_index, v.record_id, v.fp,
                                               f"{v.category or '语音'} · {v.key}")
            )
            grid.addWidget(cell, i // 3, i % 3)
        grid.setRowStretch(grid.rowCount(), 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _bubble_tab(self, ent: codex.CodexEntity) -> QWidget:
        """前 1-9 章通用战中气泡台词（点击卡片即可修改，字段 dlg）。"""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(6)
        if not ent.bubbles:
            lay.addWidget(QLabel("（没有该人格/E.G.O 的前 1-9 章气泡台词）"))
        for b in ent.bubbles:
            card = QFrame()
            card.setObjectName("panel")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(8, 4, 8, 4)
            cl.setSpacing(2)
            head = QLabel(b.key or "气泡")
            head.setStyleSheet("font-weight: 600; font-size: 11px; color: #8a9bb5;")
            cl.addWidget(head)
            if b.category:
                cat = QLabel(b.category)
                cat.setObjectName("dim")
                cat.setStyleSheet("font-size: 11px;")
                cat.setWordWrap(True)
                cl.addWidget(cat)
            body = QLabel()
            body.setWordWrap(True)
            self._set_rich_text(body, b.text or "", tip="点击修改这句气泡台词")
            cl.addWidget(body)
            # 战中气泡的台词在记录里的字段是 dlg —— 点一下就能像语音那样改
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setToolTip("点击修改这句气泡台词")
            for child in card.findChildren(QLabel):
                child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            card.mousePressEvent = (  # noqa: ARG005
                lambda _e, b=b: self._edit(b.file, b.record_index, b.record_id,
                                            [{"k": "dlg"}], b.key or "战中气泡")
            )
            lay.addWidget(card)
        lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    # ---------- 编辑 ----------

    # ---------- 本体文本（人格名称 / 罪人名 / 简介）与一键替换 ----------

    def _overlay_index(self) -> dict:
        """方案里的自定义文本索引：{(文件, id, 字段路径): 文本}（不依赖记录下标，卡片列表也能用）。"""
        out: dict = {}
        for entry in self.ctx.profile.values():
            ref = entry.ref
            out[(ref.file, json.dumps(ref.id, ensure_ascii=False), encode_fp(ref.field_path))] = entry.value
        return out

    def _override(self, entity_row: dict, field: str, index: dict | None = None) -> str | None:
        idx = self._overlay_index() if index is None else index
        key = (entity_row.get("source_file") or "",
               json.dumps(entity_row.get("entity_id"), ensure_ascii=False),
               encode_fp([{"k": field}]))
        return idx.get(key)

    def _apply_overlay(self, ent: codex.CodexEntity) -> None:
        """把方案里改过的名称/简介覆盖到实体上（索引是按零协原文建的，不覆盖就看不到改后的名字）。"""
        idx = self._overlay_index()
        for item in ent.self_texts:
            key = (ent.self_file, json.dumps(ent.self_record_id, ensure_ascii=False), encode_fp(item.fp))
            value = idx.get(key)
            if value is None:
                continue
            item.text = value
            if item.key == "title":
                ent.title = value
            elif item.key == "name":
                ent.name = value
            elif item.key == "desc":
                ent.desc = value

    def _edit_self_text(self, item: codex.CodexSelfText) -> None:
        ent = self.entity
        if ent is None or not item.fp or not ent.self_file:
            info(self, "无法编辑", "找不到该实体的本体记录。")
            return
        ref = EntryRef(file=ent.self_file, id=ent.self_record_id,
                       record_index=ent.self_record_index, field_path=item.fp)
        dlg = CodexEditDialog(self, self.ctx, ref, f"{ent.kind_label} · {item.label}",
                              subtitle=(item.text or "").replace("\n", " "))
        if safe_exec(dlg) == QDialog.DialogCode.Accepted and dlg.saved:
            self.ctx.save_profile()
            info(self, "已保存", "名称已写入方案，点「应用到游戏」后生效。")
            key = ent.entity_key
            QTimer.singleShot(0, lambda k=key: self._show_entity(k))

    def _open_entity_replace(self, ent: codex.CodexEntity) -> None:
        label = f"{ent.sinner_name} · {ent.name}（{ent.ordinal}）" if ent.kind == KIND_PERSONALITY else ent.name
        if open_replace_dialog(self, self.ctx, scope_label=f"{ent.kind_label}：{label}",
                               entity_key=ent.entity_key):
            key = ent.entity_key
            QTimer.singleShot(0, lambda k=key: self._show_entity(k))

    def _edit(self, rel: str, record_index: int, record_id, field_path, title: str) -> None:
        if not rel or not field_path:
            info(self, "无法编辑", "缺少定位信息。")
            return
        ref = EntryRef(file=rel, id=record_id, record_index=record_index, field_path=field_path)
        dlg = CodexEditDialog(self, self.ctx, ref, title)
        if safe_exec(dlg) == QDialog.DialogCode.Accepted and dlg.saved:
            self.ctx.save_profile()
            info(self, "已保存", "修改已写入方案，记得「应用到游戏」才会生效。")
            key = self.entity.entity_key if self.entity is not None else None
            if key:
                QTimer.singleShot(0, lambda k=key: self._show_entity(k))  # 延迟重建，避免删掉触发控件
