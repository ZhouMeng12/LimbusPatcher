"""敌方图鉴页（UI 完全仿照人格图鉴 CodexPage）。

三级导航：一级分组（异想体 / 敌方单位 / 阵营）→ 二级实体卡片（可按
chapter_type / enemy_type / danger_level 筛选）→ 三级详情（技能 / 被动页签）。

- 技能：一张卡一个技能（名字 · 等级 · 硬币），展开看各等级效果与硬币效果，逐条可改。
- 被动：一格一条（名称 + 说明），点击就地改。
- 部位：并入本体详情，单独一节标注展示（不可单独编辑成实体）。
- 阵营（faction 359 条）：仅英文名录只读，不显示改名入口、不可编辑。
- 关键词悬停 / 点击编辑沿用 CodexPage 机制（只作用于显示，不碰原文）。
只读参考：英语原文（若已配置英文基线）。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QTextDocument
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .. import enemy_codex, keywords, richtext, stage_enemies
from ..enemy_codex import (
    phase_variants,
    CHAPTER_TYPE_LABELS,
    DANGER_LEVEL_LABELS,
    ENEMY_TYPE_LABELS,
    GROUP_LABELS,
    CodexEnemy,
    build_enemy,
)
from ..entities import ROLE_ENEMY, ROLE_ENEMY_PASSIVE, ROLE_ENEMY_SKILL
from ..patch import EntryRef, encode_fp
from . import theme
from .codex_page import (
    KEYWORD_HOVER_DELAY_MS,
    KEYWORD_LINK_PREFIX,
    TOKEN_TIP_LIMIT,
    _Card,
    CodexEditDialog,
    KeywordEditDialog,
)
from .dialogs import info, safe_exec
from .replace_dialog import open_replace_dialog

#: 一级分组显示顺序（照游戏习惯：异想体在前）
GROUP_ORDER = ("abnormality", "unit", "faction")
#: 二级列表每行卡片数
ENEMY_COLUMNS = 3
#: 风味小字（游戏里的小字 flavor）样式：小号、灰、斜体
FLAVOR_STYLE = 'color: #8a9bb5; font-size: 11px; font-style: italic;'
#: 二级列表每批构建的卡片数（阵营 359 条 / 敌方单位 177 条，一次建完会卡）
ENTITY_CHUNK = 45


class EnemyCodexPage(QWidget):
    """敌方图鉴主页面。"""

    close_requested = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.level = 1                 # 1=分组 2=实体列表 3=详情
        self.group = GROUP_ORDER[0]
        self.entity: CodexEnemy | None = None
        self.show_format = True        # 页头「显示格式」开关：默认按游戏格式渲染
        self.show_keywords = True      # 页头「关键词名」开关：默认把 [id] 显示成中文名
        self._kw_map: dict | None = None
        self._kw_records: dict | None = None
        self._hover_token: dict[QLabel, str] = {}
        self._kw_docs: dict[QLabel, tuple] = {}
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(KEYWORD_HOVER_DELAY_MS)
        self._hover_timer.timeout.connect(self._show_hover_tip)
        self._stage_stack: list[tuple[str, object]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)

        head = QHBoxLayout()
        back = QPushButton("← 返回")
        back.clicked.connect(self._go_back)
        self.crumb = QLabel("敌方图鉴")
        self.crumb.setObjectName("title")
        self.format_btn = QPushButton("显示格式")
        self.format_btn.setCheckable(True)
        self.format_btn.setChecked(True)
        self.format_btn.setToolTip(
            "勾选：按游戏里的颜色 / 字号 / 高亮 / 粗体等格式渲染\n"
            "取消勾选：只显示纯文本（标签被去掉，不会看到 <color=…> 这类裸标签）\n"
            "编辑框里保存的始终是原始文本"
        )
        self.format_btn.toggled.connect(self._on_show_format)
        self.keyword_btn = QPushButton("关键词名")
        self.keyword_btn.setCheckable(True)
        self.keyword_btn.setChecked(True)
        self.keyword_btn.setToolTip(
            "勾选：技能说明 / 硬币效果 / 被动里的关键词 id 显示成游戏里的中文名\n"
            "（如 [Breath] →「呼吸法」，用蓝色标出），鼠标悬停可看 id 明细\n"
            "取消勾选：显示原始 [id]\n"
            "关键词 id 本身不会被改动，编辑框里保存的始终是原始文本"
        )
        self.keyword_btn.toggled.connect(self._on_show_keywords)
        head.addWidget(back)
        head.addWidget(self.crumb, 1)
        head.addWidget(self.format_btn)
        head.addWidget(self.keyword_btn)
        root.addLayout(head)

        self.body = QScrollArea()
        self._entity_specs: list[dict] = []
        self._entity_cursor = 0
        self.body.setWidgetResizable(True)
        root.addWidget(self.body, 1)

        self._show_groups()

    # ---------- 导航 ----------

    def _set_body(self, widget: QWidget) -> None:
        self._hover_timer.stop()
        self._hover_token.clear()
        self._kw_docs.clear()
        self.body.setWidget(widget)

    def _go_back(self) -> None:
        if self.level == 4:
            if self._stage_stack:
                view, ident = self._stage_stack.pop()
                if view == "chapter":
                    self._show_stage_chapter(ident)
                elif view == "extra":
                    self._show_stage_extra(ident)
                else:
                    self._show_stage_query()
            else:
                self._show_groups()
        elif self.level == 3:
            self._show_entities(self.group)
        elif self.level == 2:
            self._show_groups()
        else:
            self.close_requested.emit()

    def refresh(self) -> None:
        """索引重建 / 方案变化后按当前层级重新渲染（不会丢用户所在的位置）。"""
        if self.level == 3 and self.entity is not None:
            self._show_entity(self.entity.entity_key)
        elif self.level == 2:
            self._show_entities(self.group)
        else:
            self._show_groups()

    # ---------- 富文本渲染 / 关键词交互（与 CodexPage 一致） ----------

    def _on_show_format(self, on: bool) -> None:
        self.show_format = bool(on)
        if self.level == 3 and self.entity is not None:
            self._show_entity(self.entity.entity_key)

    def _on_show_keywords(self, on: bool) -> None:
        self.show_keywords = bool(on)
        if self.level == 3 and self.entity is not None:
            self._show_entity(self.entity.entity_key)

    def _keyword_map(self) -> dict:
        if self._kw_map is None:
            try:
                self._kw_map = keywords.load_map(
                    Path(self.ctx.env.llc_pack_dir),
                    extra_dirs=[self.ctx.supplement.root])
            except Exception:  # noqa: BLE001  显示层不该因为关键词表挂掉
                self._kw_map = {}
        return self._kw_map

    def _keyword_records(self) -> dict:
        if self._kw_records is None:
            try:
                self._kw_records = keywords.load_records(
                    Path(self.ctx.env.llc_pack_dir),
                    extra_dirs=[self.ctx.supplement.root])
            except Exception:  # noqa: BLE001  显示层不该因为关键词表挂掉
                self._kw_records = {}
        return self._kw_records

    def _tip_text(self, tip: str, plain_text: str, text: str, mapping: dict) -> str:
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
        mapping = self._keyword_map()
        mode = "name" if self.show_keywords else "raw"
        shown = keywords.substitute(text, mapping, mode)
        plain_text = richtext.plain(shown)
        keyword_hit = plain_text != richtext.plain(text)
        if self.show_format and (keyword_hit or richtext.has_format(text)):
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setText(prefix + keywords.render_html(text, mapping, mode, KEYWORD_LINK_PREFIX))
        else:
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setText(prefix + plain_text)
        label.setToolTip(self._tip_text(tip, plain_text, text, mapping))
        self._wire_keyword_hover(label)

    def _wire_keyword_hover(self, label: QLabel) -> None:
        self._kw_docs.pop(label, None)
        if KEYWORD_LINK_PREFIX not in (label.text() or ""):
            return
        label.setMouseTracking(True)
        label.installEventFilter(self)
        self._hover_token.pop(label, None)

    def _keyword_ranges(self, label: QLabel) -> list[tuple[int, int, str]]:
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
        html = label.text() or ""
        width = max(0, label.contentsRect().width())
        cached = self._kw_docs.get(label)
        if cached is not None and cached[0] == html and cached[1] == width:
            return cached[2]
        doc = QTextDocument()
        doc.setDefaultFont(label.font())
        doc.setDocumentMargin(0)
        doc.setHtml(html)
        if label.wordWrap() and width > 0:
            doc.setTextWidth(width)
        self._kw_docs[label] = (html, width, doc)
        return doc

    def _token_at(self, label: QLabel, pos) -> str:
        try:
            doc = self._mirror_doc(label)
            dy = max(0.0, (label.height() - doc.size().height()) / 2.0)
            index = doc.documentLayout().hitTest(
                QPointF(float(pos.x()), max(0.0, float(pos.y()) - dy)),
                Qt.HitTestAccuracy.ExactHit)
        except Exception:  # noqa: BLE001
            return ""
        if index is None or index < 0:
            return ""
        for start, end, token in self._keyword_ranges(label):
            if start <= index < end:
                return token
        return ""

    def _clear_hover(self, label=None) -> None:
        if label is None:
            self._hover_token.clear()
        else:
            self._hover_token.pop(label, None)
        if not self._hover_token:
            self._hover_timer.stop()
            QToolTip.hideText()

    def _show_hover_tip(self) -> None:
        for label, token in list(self._hover_token.items()):
            self._popup_keyword_tip(label, token)
            break

    def _popup_keyword_tip(self, label: QLabel, token: str) -> None:
        records = self._keyword_records().get(token) or []
        html = keywords.tooltip_html(token, records)
        if html:
            QToolTip.showText(QCursor.pos(), html, label)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        etype = event.type()
        if isinstance(obj, QLabel) and KEYWORD_LINK_PREFIX in (obj.text() or ""):
            if etype == QEvent.Type.MouseMove:
                token = self._token_at(obj, event.position().toPoint())
                if token:
                    obj.setCursor(Qt.CursorShape.PointingHandCursor)
                    self._hover_token[obj] = token
                    self._hover_timer.start()
                else:
                    obj.setCursor(Qt.CursorShape.ArrowCursor)
                    self._clear_hover(obj)
            elif etype in (QEvent.Type.Leave, QEvent.Type.Hide):
                self._clear_hover(obj)
            elif etype == QEvent.Type.ToolTip:
                token = self._hover_token.get(obj, "")
                if token:
                    self._popup_keyword_tip(obj, token)
                    return True
            elif etype == QEvent.Type.MouseButtonPress:
                token = self._token_at(obj, event.position().toPoint())
                if token and event.button() == Qt.MouseButton.LeftButton:
                    event.accept()
                    self._clear_hover(obj)
                    self._open_keyword(token)
                    return True
        return super().eventFilter(obj, event)

    def _open_keyword(self, token: str) -> None:
        records = self._keyword_records().get(token) or []
        if not records:
            info(self, "找不到关键词记录", f"[{token}] 在 BattleKeywords / Bufs / SkillTag 里都没有记录。")
            return
        QTimer.singleShot(0, lambda: self._edit_keyword(token, records))

    def _edit_keyword(self, token: str, records: list) -> None:
        dlg = KeywordEditDialog(self, self.ctx, token, records)
        if safe_exec(dlg) == QDialog.DialogCode.Accepted and dlg.saved:
            self.ctx.save_profile()
            info(self, "已保存", "关键词修改已写入方案，记得「应用到游戏」才会生效。")
            key = self.entity.entity_key if self.entity is not None else None
            if key:
                QTimer.singleShot(0, lambda k=key: self._show_entity(k))

    # ---------- 一级：分组 ----------

    def _show_groups(self) -> None:
        self.level = 1
        self.entity = None
        self.crumb.setText("敌方图鉴 · 选择分组")

        counts = self._group_counts()
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(8)
        lab = QLabel("选择分组（敌方图鉴）")
        lab.setObjectName("dim")
        lay.addWidget(lab)

        cards = []
        for group in GROUP_ORDER:
            n = counts.get(group, 0)
            label = GROUP_LABELS.get(group, group)
            sub = f"{n} 条" + ("（英文名录只读）" if group == "faction" else "（可编辑）")
            card = _Card(label, sub, badge="", portrait=None)
            card.setToolTip(f"{label}：{n} 条" +
                            ("，仅英文名录只读，不可编辑" if group == "faction" else "，名称 / 简介 / 技能 / 被动可编辑"))
            card.clicked.connect(lambda _c=False, g=group: self._show_entities(g))
            cards.append(card)
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, card in enumerate(cards):
            grid.addWidget(card, i // 3, i % 3)
        lay.addLayout(grid)

        # 按关卡查询入口
        stage_btn = QPushButton("按关卡查询敌人 ▸")
        stage_btn.setToolTip(
            "按关卡（1-1 … 9-51）查看出现的敌人。\n"
            "主线关卡为章节级数据（LLC_zh-CN/Enemies-*.json），非主线活动已聚合本地活动文件。"
        )
        stage_btn.clicked.connect(self._show_stage_query)
        lay.addWidget(stage_btn)

        lay.addStretch(1)
        self._set_body(page)

    # ---------- 按关卡查询（level 4） ----------

    def _show_stage_query(self) -> None:
        """关卡查询一级：章节 / 活动列表。"""
        self.level = 4
        self.entity = None
        self._stage_stack.clear()
        self.crumb.setText("敌方图鉴 · 按关卡查询")

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(8)
        lab = QLabel("选择章节（主线 序章~第9章；点章节查看关卡名与敌人）")
        lab.setObjectName("dim")
        lab.setWordWrap(True)
        lay.addWidget(lab)

        cards = []
        for ch in stage_enemies.chapters():
            n_stages = len(ch.get("stages", []))
            n_ens = len(ch.get("chapter_enemies", []))
            title = ch.get("chapter_label", ch.get("chapter_id", ""))
            cname = ch.get("chapter_name")
            if cname:
                title = f"{title} · {cname}"
            sub = f"{n_stages} 关"
            if n_ens:
                sub += f" · 章节敌人 {n_ens}"
            else:
                sub += " · 章节敌人待补充"
            card = _Card(title, sub, badge="")
            card.setToolTip(f"{title}：{n_stages} 个关卡"
                            + (f"，章节级敌人 {n_ens} 条" if n_ens else "，本地无章节级敌人数据"))
            card.clicked.connect(lambda _c=False, cid=ch.get("chapter_id"): self._show_stage_chapter(cid))
            cards.append(card)
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, card in enumerate(cards):
            grid.addWidget(card, i // 3, i % 3)
        lay.addLayout(grid)

        extra = stage_enemies.extra_items()
        if extra:
            elab = QLabel("活动 / 特殊（镜牢 · 瓦夜 · 间章等）")
            elab.setObjectName("dim")
            lay.addWidget(elab)
            extra_cards = []
            for it in extra:
                sub = f"{len(it.get('enemies', []))} 条"
                card = _Card(it.get("label", it.get("tag", "")), sub, badge="")
                card.setToolTip(f"{it.get('label')}：{sub}，点击查看敌人")
                card.clicked.connect(lambda _c=False, t=it.get("tag"): self._show_stage_extra(t))
                extra_cards.append(card)
            egrid = QGridLayout()
            egrid.setSpacing(8)
            for i, card in enumerate(extra_cards):
                egrid.addWidget(card, i // 4, i % 4)
            lay.addLayout(egrid)

        lay.addStretch(1)
        self._set_body(page)

    def _show_stage_chapter(self, chapter_id: str) -> None:
        """关卡查询二级：某章节的关卡按钮网格。"""
        self.level = 4
        ch = next((c for c in stage_enemies.chapters() if c.get("chapter_id") == chapter_id), None)
        if ch is None:
            info(self, "找不到章节", chapter_id)
            return
        self._stage_stack.append(("query", None))
        cname = ch.get("chapter_name")
        title = ch.get("chapter_label", chapter_id)
        if cname:
            title = f"{title} · {cname}"
        self.crumb.setText(f"敌方图鉴 · 按关卡查询 · {title}")

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(8)
        lab = QLabel(f"{title}：{len(ch.get('stages', []))} 个关卡，点击查看该关敌人")
        lab.setObjectName("dim")
        lay.addWidget(lab)

        if ch.get("chapter_ref"):
            edit_btn = QPushButton("编辑章节名")
            edit_btn.setToolTip("修改章节名（写入自定义副本 LLC_zh-CN_custom，重启保持）")
            edit_btn.clicked.connect(lambda _c=False, c=ch: self._edit_chapter_name(c))
            lay.addWidget(edit_btn, 0, Qt.AlignmentFlag.AlignLeft)

        grid = QGridLayout()
        grid.setSpacing(6)
        stages = ch.get("stages", [])
        for i, st in enumerate(stages):
            sc = st.get("stage_code", "?")
            sname = st.get("stage_name")
            text = f"{sc} {sname}" if sname else sc
            btn = QPushButton(text)
            if st.get("no_battle"):
                btn.setToolTip(f"关卡 {sc}：纯剧情关·无战斗")
            else:
                btn.setToolTip(f"关卡 {sc}："
                               + ("本地章节级敌人集合（未精确到本关）" if st.get("wiki_required") else "本地数据"))
            btn.clicked.connect(lambda _c=False, s=sc: self._show_stage_detail(s))
            grid.addWidget(btn, i // 8, i % 8)
        grid.setRowStretch(grid.rowCount(), 1)
        lay.addLayout(grid)
        lay.addStretch(1)
        self._set_body(page)

    def _show_stage_extra(self, tag: str) -> None:
        """活动条目敌人列表。"""
        self.level = 4
        it = next((e for e in stage_enemies.extra_items() if e.get("tag") == tag), None)
        if it is None:
            info(self, "找不到条目", tag)
            return
        self._stage_stack.append(("query", None))
        self.crumb.setText(f"敌方图鉴 · 按关卡查询 · {it.get('label')}")
        self._render_stage_enemies(it.get("label", tag), it.get("enemies", []),
                                   "本地章节级数据（LLC_zh-CN Enemies 文件）")

    def _show_stage_detail(self, stage_code: str) -> None:
        """关卡查询三级：某关敌人列表。"""
        self.level = 4
        st = stage_enemies.find_stage(stage_code)
        if st is None:
            info(self, "找不到关卡", stage_code)
            return
        self._stage_stack.append(("chapter", st.get("chapter_id")))
        cname = st.get("chapter_name")
        title = st.get("chapter_label", "")
        if cname:
            title = f"{title} · {cname}"
        self.crumb.setText(f"敌方图鉴 · 按关卡查询 · {title} · {stage_code}")

        sc = st.get("stage_code", stage_code)
        sname = st.get("stage_name")
        head = f"关卡 {sc}"
        if sname:
            head = f"{head} · {sname}"

        if st.get("no_battle"):
            self._render_stage_enemies(head, [], "", no_battle=True, stage=st)
            return

        enemies = st.get("enemies") or []
        if enemies:
            note = "关卡级数据"
        elif st.get("chapter_source") == "local_chapter":
            enemies = st.get("chapter_enemies") or []
            note = "本地仅有章节级数据（该章节敌人集合），未精确到本关"
        else:
            enemies = []
            note = "本地无该章节敌人数据"
        self._render_stage_enemies(head, enemies, note, stage=st)

    def _render_stage_enemies(self, title: str, enemies: list, note: str,
                              no_battle: bool = False, stage: dict | None = None) -> None:
        """关卡 / 活动敌人卡片网格（点击进入敌人详情）。"""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(8)
        t = QLabel(title)
        t.setObjectName("title")
        lay.addWidget(t)

        if stage and stage.get("stage_ref"):
            edit_btn = QPushButton("编辑关卡名")
            edit_btn.setToolTip("修改关卡名（写入自定义副本 LLC_zh-CN_custom，重启保持）")
            edit_btn.clicked.connect(lambda _c=False, s=stage: self._edit_stage_name(s))
            lay.addWidget(edit_btn, 0, Qt.AlignmentFlag.AlignLeft)

        if no_battle:
            nb = QLabel("纯剧情关·无战斗")
            nb.setObjectName("title")
            nb.setStyleSheet("color: #d08a2e;")
            lay.addWidget(nb)
            desc = QLabel("该关卡只有剧情演出，没有敌人列表。")
            desc.setObjectName("dim")
            lay.addWidget(desc)
            lay.addStretch(1)
            self._set_body(page)
            return

        if note:
            nlab = QLabel(note)
            nlab.setObjectName("dim")
            nlab.setWordWrap(True)
            lay.addWidget(nlab)
        if not enemies:
            empty = QLabel("（暂无敌人数据）")
            empty.setObjectName("dim")
            lay.addWidget(empty)
            lay.addStretch(1)
            self._set_body(page)
            return
        cards = []
        seen_ids: set = set()
        for e in enemies:
            eid = e.get("id")
            # 多阶段敌人（如 9-50 里恩 1347/1348）：把同一敌人的各形态都列出来，
            # 否则关卡里只会看到其中一阶段的技能 / 被动。
            variants = ([{"id": None, "label": ""}] if eid is None else
                        phase_variants(Path(self.ctx.env.llc_pack_dir), eid,
                                       extra_dirs=[self.ctx.supplement.root]))
            multi = len(variants) > 1
            for vi, v in enumerate(variants):
                vid = v["id"]
                if vid is not None:
                    if vid in seen_ids:
                        continue
                    seen_ids.add(vid)
                name = e.get("name") or f"敌方 {vid}"
                meta = self._meta_of(vid) if vid is not None else None
                dims = dict(meta.get("dimensions") or {}) if meta else {}
                subtitle = ""
                if dims.get("danger_level"):
                    subtitle = str(dims.get("danger_level"))
                if dims.get("chapter_type"):
                    subtitle = (subtitle + " · " if subtitle else "") + \
                               CHAPTER_TYPE_LABELS.get(dims.get("chapter_type"), dims.get("chapter_type"))
                if multi and vid is not None:
                    subtitle = (subtitle + " · " if subtitle else "") + f"{v.get('label') or ''} {vid}".strip()
                card = _Card(name, subtitle, badge="")
                if vid is None:
                    card.setToolTip(f"{name}（暂无本地详情数据）")
                else:
                    tip = f"{name}（敌方 {vid}）点击查看详情"
                    if multi:
                        tip += f"\n这是该敌人的第 {vi + 1}/{len(variants)} 个形态，技能与被动不同。"
                    card.setToolTip(tip)
                    card.clicked.connect(lambda _c=False, k=f"N:{vid}": self._show_entity(k))
                cards.append(card)
        host = QWidget()
        host.setLayout(self._grid(cards, columns=ENEMY_COLUMNS))
        lay.addWidget(host)
        lay.addStretch(1)
        self._set_body(page)

    def _group_counts(self) -> dict[str, int]:
        """各分组实体数（读 enemy_map.json 元数据，与索引是否重建无关）。"""
        counts = {g: 0 for g in GROUP_ORDER}
        maps = self.ctx.maps if hasattr(self.ctx, "maps") else None
        enemy_map = (maps.enemy_map if maps else None) or {}
        for meta in enemy_map.get("enemies", {}).values():
            group = meta.get("group") if isinstance(meta, dict) else None
            if group in counts:
                counts[group] += 1
        if sum(counts.values()) == 0:
            # 兜底：直接用 list_entities 统计（索引已建好时）
            for e in self.ctx.search.list_entities("enemy"):
                meta = self._meta_of(e.get("entity_id"))
                if meta:
                    g = meta.get("group")
                    if g in counts:
                        counts[g] += 1
        return counts

    def _meta_of(self, entity_id: object) -> dict | None:
        maps = getattr(self.ctx, "maps", None)
        return maps.enemy_meta(entity_id) if maps is not None else None

    # ---------- 二级：实体列表 ----------

    def _show_entities(self, group: str) -> None:
        self.level = 2
        self.group = group
        self.entity = None
        group_label = GROUP_LABELS.get(group, group)
        self.crumb.setText(f"敌方图鉴 · {group_label}")

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(8)

        # 二级筛选：chapter_type / enemy_type / danger_level
        filters = QHBoxLayout()
        filters.addWidget(QLabel("关卡类型"))
        self.chapter_combo = QComboBox()
        self.chapter_combo.addItem("全部", "")
        for k, v in CHAPTER_TYPE_LABELS.items():
            self.chapter_combo.addItem(v, k)
        filters.addWidget(self.chapter_combo)
        filters.addWidget(QLabel("敌人类型"))
        self.enemy_combo = QComboBox()
        self.enemy_combo.addItem("全部", "")
        for k, v in ENEMY_TYPE_LABELS.items():
            self.enemy_combo.addItem(v, k)
        filters.addWidget(self.enemy_combo)
        filters.addWidget(QLabel("危险等级"))
        self.danger_combo = QComboBox()
        self.danger_combo.addItem("全部", "")
        for k, v in DANGER_LEVEL_LABELS.items():
            self.danger_combo.addItem(v, k)
        filters.addWidget(self.danger_combo)
        filters.addStretch(1)
        lay.addLayout(filters)

        for combo in (self.chapter_combo, self.enemy_combo, self.danger_combo):
            combo.currentIndexChanged.connect(lambda _i: self._rebuild_entity_list())

        self.list_host = QVBoxLayout()
        lay.addLayout(self.list_host, 1)
        self._rebuild_entity_list()
        self._set_body(page)

    def _dimension_of(self, entity_id: object) -> dict:
        meta = self._meta_of(entity_id)
        dims = (meta or {}).get("dimensions")
        return dict(dims) if isinstance(dims, dict) else {}

    def _rebuild_entity_list(self) -> None:
        """按当前分组 + 三个筛选维度重建二级卡片网格；**分批构建卡片**。

        阵营 359 条、敌方单位 177 条，一次性构造几百张卡片会让「点开分组」卡住
        （实测每组 ~0.6 秒，真实窗口更久）。这里只先建 ``_ENTITY_CHUNK`` 张，
        其余滚到底 / 点按钮继续。
        """
        while self.list_host.count():
            item = self.list_host.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        chapter = self.chapter_combo.currentData() or ""
        etype = self.enemy_combo.currentData() or ""
        danger = self.danger_combo.currentData() or ""

        specs: list[dict] = []
        for e in self.ctx.search.list_entities("enemy"):
            meta = self._meta_of(e.get("entity_id")) or {}
            # ⚠ group 在元数据**顶层**（dimensions 里只有 chapter_type / enemy_type / danger_level）；
            # 以前读 dims["group"] 拿到的一直是 None，于是每个分组都把 638 个敌人全列出来。
            if (meta.get("group") or self.group) != self.group:
                continue
            dims = dict(meta.get("dimensions") or {})
            if chapter and dims.get("chapter_type") != chapter:
                continue
            if etype and dims.get("enemy_type") != etype:
                continue
            if danger and dims.get("danger_level") != danger:
                continue
            name = self._override(e, "name") or e.get("name") or ""
            subtitle = ""
            if dims.get("danger_level"):
                subtitle = str(dims.get("danger_level"))
            if dims.get("chapter_type"):
                subtitle = (subtitle + " · " if subtitle else "") +                            CHAPTER_TYPE_LABELS.get(dims.get("chapter_type"), dims.get("chapter_type"))
            counts = []
            if e.get("skill_count"):
                counts.append(f"技能 {e['skill_count']}")
            if e.get("passive_count"):
                counts.append(f"被动 {e['passive_count']}")
            specs.append({
                "name": name or f"敌方 {e.get('entity_id')}",
                "subtitle": subtitle,
                "badge": " · ".join(counts),
                "key": e["entity_key"],
            })

        self._entity_specs = specs
        self._entity_cursor = 0

        host = QWidget()
        outer = QVBoxLayout(host)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        if not specs:
            empty = QLabel("（该筛选条件下没有敌方条目）")
            empty.setObjectName("dim")
            outer.addWidget(empty)
            outer.addStretch(1)
        else:
            grid_host = QWidget()
            grid = QGridLayout(grid_host)
            grid.setSpacing(8)
            outer.addWidget(grid_host)
            self._entity_grid = grid
            more = QPushButton("")
            more.setCursor(Qt.CursorShape.PointingHandCursor)
            more.clicked.connect(lambda _c=False: self._load_more_entities())
            outer.addWidget(more, 0, Qt.AlignmentFlag.AlignHCenter)
            self._entity_more = more
            outer.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(host)
        self._entity_scroll = scroll
        if specs:
            scroll.verticalScrollBar().valueChanged.connect(self._maybe_load_more_entities)
            self._render_entity_chunk()
        self.list_host.addWidget(scroll)

    _ENTITY_CHUNK = ENTITY_CHUNK

    def _render_entity_chunk(self) -> int:
        """构造下一批卡片并挂进网格；返回本批数量。"""
        specs = self._entity_specs
        end = min(len(specs), self._entity_cursor + self._ENTITY_CHUNK)
        rendered = 0
        for i in range(self._entity_cursor, end):
            spec = specs[i]
            card = _Card(spec["name"], spec["subtitle"], badge=spec["badge"])
            card.clicked.connect(lambda _c=False, k=spec["key"]: self._show_entity(k))
            self._entity_grid.addWidget(card, i // ENEMY_COLUMNS, i % ENEMY_COLUMNS)
            rendered += 1
        self._entity_cursor = end
        remaining = len(specs) - end
        more = getattr(self, "_entity_more", None)
        if more is not None:
            more.setVisible(remaining > 0)
            more.setText(f"▼ 继续载入剩余 {remaining} 项（滚到底或点这里）")
        return rendered

    def remaining_entities(self) -> int:
        return max(0, len(getattr(self, "_entity_specs", [])) - getattr(self, "_entity_cursor", 0))

    def _load_more_entities(self) -> int:
        if self.remaining_entities() <= 0:
            return 0
        return self._render_entity_chunk()

    def _maybe_load_more_entities(self, value: int) -> None:
        """内层滚动到底部时自动补一批。"""
        if self.remaining_entities() <= 0:
            return
        bar = self._entity_scroll.verticalScrollBar()
        if value >= bar.maximum() - 2:
            self._load_more_entities()

    def _grid(self, cards: list[QWidget], columns: int) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, card in enumerate(cards):
            grid.addWidget(card, i // columns, i % columns)
        grid.setRowStretch(grid.rowCount(), 1)
        return grid

    # ---------- 三级：详情 ----------

    def _show_entity(self, entity_key: str) -> None:
        summary = self.ctx.search.entity_summary(entity_key)
        if not summary:
            info(self, "找不到实体", entity_key)
            return
        self.level = 3
        self.entity = build_enemy(Path(self.ctx.env.llc_pack_dir), summary, self.ctx.maps,
                                  extra_dirs=[self.ctx.supplement.root])
        self._apply_overlay(self.entity)
        ent = self.entity
        self.crumb.setText(f"敌方图鉴 · {ent.group_label or ent.group} · {ent.name or ent.name_en}")

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(8)

        tools = QHBoxLayout()
        self.name_btn = QPushButton("改名称 ▾")
        self.name_btn.setToolTip("修改这个敌人的名称、简介（写进方案，零协原文不动；阵营条目只读）")
        menu = QMenu(self.name_btn)
        for item in ent.self_texts:
            act = menu.addAction(item.label)
            act.triggered.connect(lambda _c=False, it=item: self._edit_self_text(it))
        self.name_btn.setMenu(menu)
        self.name_btn.setEnabled(bool(ent.self_texts) and not ent.is_faction)
        tools.addWidget(self.name_btn)
        if not ent.is_faction:
            rep_btn = QPushButton("一键替换")
            rep_btn.setToolTip("在这个敌人的全部文本里批量查找替换")
            rep_btn.clicked.connect(lambda _c=False, e=ent: self._open_entity_replace(e))
            tools.addWidget(rep_btn)
        tools.addStretch(1)
        lay.addLayout(tools)

        # 多阶段敌人（如 9-50 里恩 1347/1348）：在技能/被动页签上方切换形态
        variants = phase_variants(Path(self.ctx.env.llc_pack_dir), ent.entity_id,
                                  extra_dirs=[self.ctx.supplement.root])
        if len(variants) > 1:
            vrow = QHBoxLayout()
            vlab = QLabel(f"形态（{len(variants)}）：")
            vlab.setObjectName("dim")
            vrow.addWidget(vlab)
            for v in variants:
                btn = QPushButton(f"{v['label']} · {v['id']}")
                btn.setCheckable(True)
                btn.setChecked(int(v["id"]) == int(ent.entity_id))
                btn.setToolTip(f"这个敌人的另一个阶段（id {v['id']}），技能与被动不同")
                btn.clicked.connect(lambda _c=False, vid=int(v["id"]): self._show_entity(f"N:{vid}"))
                vrow.addWidget(btn)
            vrow.addStretch(1)
            lay.addLayout(vrow)

        info_row = QLabel(self._entity_headline(ent))
        info_row.setObjectName("dim")
        info_row.setWordWrap(True)
        lay.addWidget(info_row)

        # 部位：并入本体详情，单独一节标注展示
        if ent.parts:
            parts_box = QFrame()
            parts_box.setObjectName("panel")
            pl = QVBoxLayout(parts_box)
            pl.setSpacing(2)
            ptitle = QLabel(f"部位（{len(ent.parts)}）")
            ptitle.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600;")
            pl.addWidget(ptitle)
            for part in ent.parts:
                pn = QLabel()
                pn.setWordWrap(True)
                pn.setCursor(Qt.CursorShape.PointingHandCursor)
                self._set_rich_text(pn, part.name or f"部位 {part.seq}", prefix="◆ ",
                                    tip="点击修改部位名称")
                pn.mousePressEvent = (  # noqa: ARG005
                    lambda _e, p=part: self._edit(p.file, p.record_index, p.record_id, p.name_fp,
                                                  f"部位 · {p.label} 名称")
                )
                pl.addWidget(pn)
                pd = QLabel()
                pd.setWordWrap(True)
                pd.setCursor(Qt.CursorShape.PointingHandCursor)
                self._set_rich_text(pd, part.desc or "（无说明）", prefix="　",
                                    tip="点击修改部位说明")
                pd.mousePressEvent = (  # noqa: ARG005
                    lambda _e, p=part: self._edit(p.file, p.record_index, p.record_id, p.desc_fp,
                                                  f"部位 · {p.label} 说明")
                )
                pl.addWidget(pd)
            lay.addWidget(parts_box)

        tabs = QTabWidget()
        tabs.addTab(self._skills_tab(ent), f"技能（{len(ent.skills)}）· 被动（{len(ent.passives)}）")
        tabs.addTab(self._bubble_tab(ent), f"战中气泡（{len(ent.bubbles)}）")
        lay.addWidget(tabs, 1)
        self._set_body(page)

    @staticmethod
    def _entity_headline(ent: CodexEnemy) -> str:
        bits = []
        if ent.group_label:
            bits.append(ent.group_label)
        for key in ("chapter_type", "enemy_type", "danger_level"):
            label = ent.dimension_label(key)
            if label:
                bits.append(label)
        if ent.name_en:
            bits.append(ent.name_en)
        text = " · ".join(b for b in bits if b)
        if ent.desc:
            text += "\n" + richtext.plain(ent.desc)
        if ent.is_faction:
            text += "\n（阵营条目仅英文名录，只读）" if not ent.desc else ""
        return text

    def _skills_tab(self, ent: CodexEnemy) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(6)
        if not ent.skills and not ent.passives:
            lay.addWidget(QLabel("（游戏本体没有这个敌人的技能文本）"))
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

    def _bubble_tab(self, ent: CodexEnemy) -> QWidget:
        """前 1-9 章战中气泡台词（点击卡片即可修改，字段 dlg）。"""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(6)
        if not ent.bubbles:
            lay.addWidget(QLabel("（游戏本体没有该敌人的前 1-9 章气泡台词）"))
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

    def _overlay_index(self) -> dict:
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

    def _apply_overlay(self, ent: CodexEnemy) -> None:
        idx = self._overlay_index()
        for item in ent.self_texts:
            key = (ent.self_file, json.dumps(ent.self_record_id, ensure_ascii=False), encode_fp(item.fp))
            value = idx.get(key)
            if value is None:
                continue
            item.text = value
            if item.key == "name":
                ent.name = value
            elif item.key == "desc":
                ent.desc = value

    def _edit_self_text(self, item) -> None:
        ent = self.entity
        if ent is None or not item.fp or not ent.self_file or ent.is_faction:
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

    def _open_entity_replace(self, ent: CodexEnemy) -> None:
        label = f"{ent.group_label} · {ent.name or ent.name_en}"
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
                QTimer.singleShot(0, lambda k=key: self._show_entity(k))

    # ---------- 章节名 / 关卡名编辑 ----------

    def _edit_chapter_name(self, ch: dict) -> None:
        ref_d = ch.get("chapter_ref")
        if not ref_d:
            info(self, "无法编辑", "该章节在游戏包中无独立章节名记录，暂不可编辑。")
            return
        ref = EntryRef(file=ref_d["file"], id=ref_d["id"],
                       record_index=ref_d["record_index"], field_path=ref_d["field_path"])
        dlg = CodexEditDialog(self, self.ctx, ref,
                              f"编辑章节名 · {ch.get('chapter_label')}",
                              subtitle=ch.get("chapter_name") or "")
        if safe_exec(dlg) == QDialog.DialogCode.Accepted and dlg.saved:
            self.ctx.save_profile()
            entry = self.ctx.profile.get(ref)
            new_name = (entry.value if entry else "").strip() or ch.get("chapter_name") or ""
            stage_enemies.set_chapter_name(ch.get("chapter_id"), new_name)
            info(self, "已保存", "章节名已更新（重启保持；游戏内生效需「应用到游戏」）。")
            self._show_stage_chapter(ch.get("chapter_id"))

    def _edit_stage_name(self, st: dict) -> None:
        ref_d = st.get("stage_ref")
        if not ref_d:
            info(self, "无法编辑", "该关卡没有可编辑的源文件定位。")
            return
        ref = EntryRef(file=ref_d["file"], id=ref_d["id"],
                       record_index=ref_d["record_index"], field_path=ref_d["field_path"])
        dlg = CodexEditDialog(self, self.ctx, ref,
                              f"编辑关卡名 · {st.get('stage_code')}",
                              subtitle=st.get("stage_name") or "")
        if safe_exec(dlg) == QDialog.DialogCode.Accepted and dlg.saved:
            self.ctx.save_profile()
            entry = self.ctx.profile.get(ref)
            new_name = (entry.value if entry else "").strip() or st.get("stage_name") or ""
            stage_enemies.set_stage_name(st.get("stage_code"), new_name)
            info(self, "已保存", "关卡名已更新（重启保持；游戏内生效需「应用到游戏」）。")
            self._show_stage_detail(st.get("stage_code"))
