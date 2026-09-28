"""主窗口：顶部状态栏 + 三栏工作台 + 首次引导。"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..app_state import AppContext
from .. import categories as _categories
from ..categories import chapter_hint, classify
from ..entities import (CONTENT_CHOICES, KIND_EGO, KIND_ENEMY, KIND_PERSONALITY, ROLE_EGO, ROLE_IDENTITY,
                        ROLE_LABELS, parse_entity_key)
from ..index import normalize
from ..patch import EntryRef, ref_label
from ..search import SearchHit
from ..season import acq_display, kind_display, season_display, season_key
from ..story import story_of
from ..textsource import speaker_of
from . import theme
from .brand import LogoMark, MoreButton, SaveDot
from .dialogs import BackupDialog, HistoryDialog, confirm, error, info, safe_exec, warn
from .codex_page import CodexPage
from .enemy_codex_page import EnemyCodexPage
from .editor_panel import EditorPanel
from .list_panel import (
    STATUS_MISSING,
    STATUS_MODIFIED,
    STATUS_PENDING,
    STATUS_UNMODIFIED,
    HitView,
    ListPanel,
)
from .nav import NavPanel
from .onboarding import OnboardingPage
from .replace_dialog import open_replace_dialog
from .supplement_dialog import open_supplement_dialog
from .script_panel import ScriptPanel
from .status_pill import StatusPill, StatusRow
from .theme_switch import ThemeSwitcher
from .workers import Runner


#: 获取方式分组顺序（base 在前，未标注永远垫底）
ACQ_GROUP_ORDER = [
    ("base", "常驻（基础）"),
    ("seasonal", "赛季限定"),
    ("pass", "通行证"),
    ("event", "活动赠送"),
    ("walpurgis", "瓦尔普吉斯之夜"),
    ("unknown", "未标注"),
]
#: 分组标题里「未标注」永远排最后
_GROUP_LAST = "未标注"


def _season_group_rank(label: str) -> tuple:
    if label == "基础":
        return (0, 0)
    if label == "常驻":
        return (1, 0)
    if label.startswith("第") and label.endswith("赛季"):
        num = label[1:-2]
        return (2, int(num)) if num.isdigit() else (2, 999)
    return (9, 0)


def _vsep() -> QFrame:
    """竖分隔线。

    v3 起顶栏不再用它（原型的顶栏用间距而不是分隔线分组），
    但图鉴 / 剧本模式等整页仍可用；样式见 ``QFrame#vsep``。
    """
    f = QFrame()
    f.setObjectName("vsep")
    f.setFixedSize(1, 18)
    return f


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, startup_backup: bool = True):
        super().__init__()
        self.ctx = ctx
        self.runner = Runner()
        self._workers: list = []
        self._category = "all"
        self._current_hit: SearchHit | None = None
        self._story_ctx: tuple[str, str] | None = None
        self._session_restored = False  # 会话记忆只在索引就绪后恢复一次
        self._switching_theme = False   # 正在因换主题而重建窗口
        self._crumb = ""                # 顶栏面包屑文案
        self.setWindowTitle("边狱巴士汉化文本修改器")
        self.resize(1400, 900)

        # ---------- 顶部栏 ----------
        topbar = self._build_topbar()

        # ---------- 页面切换 ----------
        self.stack = QStackedWidget()
        self.onboarding = OnboardingPage()
        self.workspace = self._build_workspace()
        self.stack.addWidget(self.onboarding)
        self.stack.addWidget(self.workspace)

        root = QWidget()
        # 根容器显式铺窗口底色：卡片之间的 8px 缝隙要透出 BG（比面板更暗一层）。
        # 不依赖 QMainWindow 自身背景 —— 离屏 grab 时顶层窗口背景不会被绘制。
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(topbar)
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        # ---------- 菜单 ----------
        # 关掉原生菜单栏：Windows 上原生菜单栏不吃 QSS，会和自绘顶栏割裂成两种观感。
        mbar = self.menuBar()
        mbar.setNativeMenuBar(False)
        menu = mbar.addMenu("工具")
        act_rescan = QAction("重新检测环境", self)
        act_reindex = QAction("重建文本索引", self)
        act_backups = QAction("备份管理…", self)
        act_datadir = QAction("打开数据目录", self)
        act_replace_all = QAction("一键替换（全部文本）…", self)
        menu.addAction(act_replace_all)
        menu.addSeparator()
        menu.addAction(act_rescan)
        menu.addAction(act_reindex)
        menu.addAction(act_backups)
        menu.addAction(act_datadir)
        menu.addSeparator()
        act_replace_all.triggered.connect(lambda: self.batch_replace(whole=True))
        menu.addAction(QAction("退出", self, triggered=self.close))
        help_menu = self.menuBar().addMenu("帮助")
        help_menu.addAction(QAction("使用说明", self, triggered=self._usage))
        help_menu.addAction(QAction("关于", self, triggered=self._about))

        # ---------- 快捷键 ----------
        from PySide6.QtGui import QKeySequence, QShortcut

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.editor._on_save)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        QShortcut(QKeySequence("Esc"), self, activated=self._clear_search)
        QShortcut(QKeySequence("Ctrl+Shift+D"), self, activated=lambda: self.editor.diff_btn.toggle())
        QShortcut(QKeySequence("Ctrl+Shift+A"), self, activated=lambda: self.act_advanced.toggle())

        # ---------- 连接 ----------
        self.onboarding.scan_requested.connect(self.scan_steam)
        self.onboarding.manual_requested.connect(self.choose_dir)
        self.onboarding.retry_requested.connect(self.retry_env)
        self.nav.category_selected.connect(self._on_nav_category)
        self.list_panel.search_requested.connect(self._on_search_requested)
        self.list_panel.filters_changed.connect(self._on_filters_changed)
        self.list_panel.scope_combo.currentIndexChanged.connect(lambda _i: self.refresh_list())
        self.list_panel.entity_combo.currentIndexChanged.connect(lambda _i: self.refresh_list())
        self.list_panel.content_combo.currentIndexChanged.connect(lambda _i: self.refresh_list())
        self.list_panel.entity_requested.connect(self._open_entity)
        self.list_panel.hit_activated.connect(self._on_hit_activated)
        self.list_panel.favorite_requested.connect(self._on_favorite)
        self.list_panel.batch_restore_requested.connect(self._on_batch_restore)
        self.list_panel.batch_favorite_requested.connect(self._on_batch_favorite)
        self.list_panel.source_requested.connect(self._on_show_source)
        self.editor.save_requested.connect(self._on_save)
        self.editor.restore_requested.connect(self._on_restore)
        self.editor.favorite_toggled.connect(self._on_favorite)
        self.editor.history_requested.connect(self._on_history)
        self.editor.story_requested.connect(self._on_story_open)
        self.script_panel.back_requested.connect(self._exit_script_mode)
        self.script_panel.stage_selected.connect(self._script_stage_changed)
        self.script_panel.line_clicked.connect(self._on_script_line)
        self.script_panel.skip_requested.connect(self._on_script_skip)
        self.script_panel.unskip_requested.connect(self._on_script_unskip)
        self.script_panel.delete_requested.connect(self._on_script_delete)
        self.script_panel.restore_requested.connect(self._on_script_restore)
        self.script_panel.delete_all_requested.connect(self._on_script_delete_all)
        self.script_panel.suggest_requested.connect(self._on_script_suggest)
        self.script_panel.batch_requested.connect(self._on_script_batch)
        self.script_panel.chapter_selected.connect(self._on_script_chapter)
        # 顶栏三颗整页入口的向后兼容别名（旧测试/脚本按 *_btn_top 取；
        # 它们现在是真按钮，所以 .text() / .click() 都能用）
        self.script_btn_top = self.page_script
        self.codex_btn_top = self.page_codex
        self.enemy_btn_top = self.page_enemy
        self.theme_switch.theme_selected.connect(self.set_theme)
        self.apply_btn.clicked.connect(self.apply_patch)
        self.act_clear.triggered.connect(self.clear_all)
        self.act_disable.triggered.connect(self.disable_patch)
        self.act_backup.triggered.connect(self.make_backup)
        self.act_replace.triggered.connect(self.batch_replace)
        self.act_supplement.triggered.connect(self.manage_supplement)
        self.act_suggest.triggered.connect(self.suggest_all_story)
        self.act_baseline.triggered.connect(self.show_baseline_status)
        self.act_export.triggered.connect(self.export_profile_pack)
        self.act_import.triggered.connect(self.import_profile_pack)
        self.act_dir.triggered.connect(self.choose_dir)
        self.act_advanced.toggled.connect(self._on_advanced)
        act_rescan.triggered.connect(self.retry_env)
        act_reindex.triggered.connect(lambda: self._ensure_index_async(force=True))
        act_backups.triggered.connect(self.open_backups)
        act_datadir.triggered.connect(lambda: self._open_dir(self.ctx.app_paths.data_dir))

        # ---------- 启动 ----------
        if startup_backup:
            # 切换主题会重建窗口，重建时不再重复做启动备份
            self.ctx.backup.backup("startup")
        self.refresh_topbar()
        self._restore_window_state()  # 窗口/分栏先恢复（不依赖索引）
        self._show_page()
        if self.ctx.env.healthy():
            self._ensure_index_async()

    # ---------- 构建 ----------

    def _build_topbar(self) -> QFrame:
        """顶栏：左「品牌 + 面包屑 + 整页入口」，右「状态 + 操作」。

        结构：

            [logo 邊] 边狱巴士汉化文本修改器 ●   人格 › 技能 │ [人格图鉴][敌方图鉴][剧本模式]   ……   [37 条待确认] [风格 · 巴士] [应用到游戏] [•••]

        「人格图鉴 / 敌方图鉴 / 剧本模式」是**整页入口**，直接摆在顶栏可见
        （它们是「去哪」，跟面包屑同一组语义）；选中态表示当前就在那一页，
        再点一次回工作台。最右那颗「••• 更多操作」只放工具类动作
        （备份 / 导入导出 / 高级模式…），不放整页入口。
        「当前方案 / N 条修改」不占顶栏横向空间，挂在品牌名下方做副标题。
        """
        bar = QFrame()
        bar.setObjectName("topbar")
        self.topbar = bar
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 7, 12, 7)
        lay.setSpacing(12)

        # ---- 品牌区：金色 logo + 应用名 + 保存点 / 副标题给方案信息 ----
        self.brand_logo = LogoMark("邊", 28)
        self.brand_name = QLabel("边狱巴士汉化文本修改器")
        self.brand_name.setObjectName("brandName")
        self.save_dot = SaveDot()
        self.profile_chip = QLabel("")
        self.profile_chip.setObjectName("faint")

        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(5)
        name_row.addWidget(self.brand_name)
        name_row.addWidget(self.save_dot)
        name_row.addStretch(1)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)
        text_col.addLayout(name_row)
        text_col.addWidget(self.profile_chip)

        brand = QFrame()
        brand.setObjectName("brand")
        brand_lay = QHBoxLayout(brand)
        brand_lay.setContentsMargins(0, 0, 0, 0)
        brand_lay.setSpacing(9)
        brand_lay.addWidget(self.brand_logo)
        brand_lay.addLayout(text_col)

        self.crumb = QLabel("")
        self.crumb.setObjectName("crumb")

        # ---- 右侧操作区 ----
        self.status_pill = StatusPill()

        self.apply_btn = QPushButton("应用到游戏")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.setFixedHeight(28)

        self.theme_switch = ThemeSwitcher(theme.current_mode())

        self.more_btn = MoreButton()
        self.more_menu = QMenu(self)

        # —— 整页入口：三颗 tab 直接摆在顶栏（可见，不塞进「•••」）——
        self.page_codex = self._page_tab("人格图鉴", "codex")
        self.page_enemy = self._page_tab("敌方图鉴", "enemy")
        self.page_script = self._page_tab("剧本模式", "script")

        self.act_llc = QAction("装零协汉化", self)
        self.act_llc.setToolTip("用零协工具箱一键安装中文汉化；装好后点「重新检测」即可切回中文底本")
        self.act_llc.triggered.connect(lambda _c=False: open_llc_toolbox(self, "安装零协汉化", True))
        self.act_llc.setVisible(False)
        self.more_menu.addAction(self.act_llc)
        self.more_menu.addSeparator()

        # —— 原来的「操作 ▼」菜单项 ——
        self.act_clear = QAction("清空全部修改", self)
        self.act_disable = QAction("停用修改", self)
        self.act_backup = QAction("立即备份", self)
        self.act_suggest = QAction("自动建议剧本对应…", self)
        self.act_supplement = QAction("补译文件…", self)
        self.act_supplement.setToolTip("管理零协包里没有、由本工具生成的文件（如新章节剧情）")
        self.act_replace = QAction("一键替换…", self)
        self.act_replace.setToolTip("在当前列表筛选结果里批量查找替换（列表为空时按全库处理）")
        self.act_baseline = QAction("英文基线状态…", self)
        self.act_export = QAction("导出方案包…", self)
        self.act_import = QAction("导入方案包…", self)
        self.act_dir = QAction("设置游戏目录…", self)
        self.act_advanced = QAction("高级模式", self, checkable=True, checked=self.ctx.config.advanced_mode)
        self.more_menu.addAction(self.act_clear)
        self.more_menu.addAction(self.act_disable)
        self.more_menu.addSeparator()
        self.more_menu.addAction(self.act_supplement)
        self.more_menu.addAction(self.act_replace)
        self.more_menu.addAction(self.act_backup)
        self.more_menu.addAction(self.act_suggest)
        self.more_menu.addAction(self.act_baseline)
        self.more_menu.addSeparator()
        self.more_menu.addAction(self.act_export)
        self.more_menu.addAction(self.act_import)
        self.more_menu.addAction(self.act_dir)
        self.more_menu.addSeparator()
        self.more_menu.addAction(self.act_advanced)
        self.more_btn.setMenu(self.more_menu)

        lay.addWidget(brand)
        lay.addWidget(self.crumb)
        # 整页入口跟在面包屑后面：它们和「我在哪」属于同一组「位置 / 去哪」语义，
        # 放左边也就把右侧留给「状态 + 操作」，保住「应用到游戏」唯一 primary 的地位。
        lay.addWidget(_vsep())
        lay.addWidget(self.page_codex)
        lay.addWidget(self.page_enemy)
        lay.addWidget(self.page_script)
        lay.addStretch(1)
        lay.addWidget(self.status_pill)
        lay.addWidget(self.theme_switch)
        lay.addWidget(self.apply_btn)
        lay.addWidget(self.more_btn)
        return bar

    def _page_tab(self, text: str, key: str) -> QPushButton:
        """顶栏的整页入口按钮：可选中，选中 = 当前正在那一页；再点一次回工作台。"""
        btn = QPushButton(text)
        btn.setObjectName("pageTab")
        btn.setCheckable(True)
        btn.setFixedHeight(28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda checked=False, k=key: self._on_page_tab(k, checked))
        return btn

    def _on_page_tab(self, key: str, checked: bool) -> None:
        """点顶栏整页入口。

        选中 → 进那一页；**取消选中（再点一次）→ 回工作台**（tab 的常规语义）。
        进剧本模式要先回工作台：剧本面板是替换工作台里的列表面板，不在 center_stack 上。
        """
        if not checked:
            self._exit_script_mode()
            self.center_stack.setCurrentIndex(0)
        elif key == "codex":
            self.open_codex()
        elif key == "enemy":
            self.open_enemy_codex()
        else:
            self.center_stack.setCurrentIndex(0)
            self.open_script_mode()
        # 以「实际状态」为准回写选中态：open_* 可能因为环境不满足而提前返回。
        self._sync_page_tabs()

    def _sync_page_tabs(self) -> None:
        """把三颗整页入口的选中态、以及顶栏面包屑，对齐到真实所在页。

        这是「我在哪」的唯一回写点：切图鉴页、进出剧本模式、点顶栏 tab、
        点导航（含图鉴页里的「返回」）、切主题重建窗口，最后都收敛到这里。
        """
        if not hasattr(self, "page_codex") or not hasattr(self, "center_stack"):
            return
        try:
            cur = self.center_stack.currentWidget()
        except RuntimeError:      # 控件已销毁（切主题重建窗口的瞬间）
            return
        on_codex = cur is self.codex_page
        on_enemy = cur is self.enemy_codex_page
        script = bool(getattr(self, "_script_active", False))
        self.page_codex.setChecked(on_codex)
        self.page_enemy.setChecked(on_enemy)
        self.page_script.setChecked(script)
        # 面包屑跟着走：进整页显示页名，回工作台回到当前分类
        if on_codex:
            self._set_crumb("codex")
        elif on_enemy:
            self._set_crumb("enemy_codex")
        elif script:
            self._set_crumb("script")
        else:
            self._set_crumb(getattr(self, "_category", "") or "")

    def _build_workspace(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        # 照原型 .body{padding:8px}：四周留 8px，让卡片「浮」在更暗的窗口底色上。
        # 卡片之间的缝由 QSplitter 的 8px 透明 handle 提供（见 theme.py 的 QSS）。
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.nav = NavPanel()
        self.list_panel = ListPanel()
        self.editor = EditorPanel()
        self.nav.setMinimumWidth(170)
        self.nav.setMaximumWidth(260)
        self.list_panel.setMinimumWidth(360)
        self.editor.setMinimumWidth(420)
        # 中间+右侧放进内容栈：0 = 列表+编辑器，1 = 人格图鉴
        inner = QSplitter(Qt.Orientation.Horizontal)
        inner.addWidget(self.list_panel)
        inner.addWidget(self.editor)
        inner.setStretchFactor(0, 3)
        inner.setStretchFactor(1, 4)
        inner.setSizes([480, 690])
        self._inner_splitter = inner

        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(inner)
        self.codex_page = CodexPage(self.ctx)
        self.codex_page.close_requested.connect(lambda: self.center_stack.setCurrentIndex(0))
        self.codex_page.story_requested.connect(self.open_identity_story)
        self.center_stack.addWidget(self.codex_page)
        self.enemy_codex_page = EnemyCodexPage(self.ctx)
        self.enemy_codex_page.close_requested.connect(lambda: self.center_stack.setCurrentIndex(0))
        self.center_stack.addWidget(self.enemy_codex_page)
        # 页面切换（含图鉴页自己的「返回」）后回写顶栏整页入口的选中态
        self.center_stack.currentChanged.connect(lambda _i: self._sync_page_tabs())

        splitter.addWidget(self.nav)
        splitter.addWidget(self.center_stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([230, 1170])
        layout.addWidget(splitter)
        self._splitter = splitter
        self.script_panel = ScriptPanel()
        self._script_active = False
        self._script_cid: str | None = None
        self._script_code: str | None = None
        self._script_branch: str | None = None  # RPG 关卡下的分支（10-04 的「1F 探索」等）
        return w

    # ---------- 页面与状态 ----------

    def _show_page(self) -> None:
        if self.ctx.env.healthy():
            self.stack.setCurrentWidget(self.workspace)
        else:
            self.stack.setCurrentWidget(self.onboarding)

    def refresh_topbar(self) -> None:
        self.profile_chip.setText(f"{self.ctx.profile.name} · {self.ctx.profile.count()} 条修改")
        self.save_dot.set_state(not self.ctx.profile_dirty)
        rows: list[StatusRow] = []

        # ---- 保存 ----
        if self.ctx.profile_dirty:
            rows.append(StatusRow("save", "保存", "有未保存修改", "warn", "改动还在内存里，按 Ctrl+S 落盘"))
        else:
            rows.append(StatusRow("save", "保存", "已保存", "ok"))

        # ---- 环境 ----
        env = self.ctx.env
        if env.game_dir_ok and env.llc_ok:
            rows.append(StatusRow("env", "环境", "环境正常", "ok"))
        elif env.healthy():
            # 没装零协但游戏英文基线在：用英文原文当文本来源，功能照常（除了写回游戏）
            rows.append(StatusRow("env", "环境", "英文原文模式（未装零协）", "warn",
                                  "可用英文原文当底本编辑，但无法写回游戏"))
        elif env.game_dir:
            detail = "；".join(i.message for i in env.issues) or "请检查游戏目录"
            rows.append(StatusRow("env", "环境", env.brief(), "err", detail))
        else:
            rows.append(StatusRow("env", "环境", "未选目录", "err",
                                  "用「更多操作 → 设置游戏目录…」选择游戏目录"))
        self.act_llc.setVisible(self.ctx.env.text_source == "en")

        # ---- 应用 ----
        sup_total, sup_on = self.ctx.supplement.count()
        if not self.ctx.env.llc_ok or (self.ctx.profile.count() == 0 and not sup_on):
            rows.append(StatusRow("apply", "应用", "无修改", "none"))
            self.apply_btn.setEnabled(False)
        else:
            view = self.ctx.apply_view()
            if view is None:
                rows.append(StatusRow("apply", "应用", "环境异常", "err"))
            elif view.applied:
                rows.append(StatusRow("apply", "应用", "已应用", "ok"))
            elif view.enabled:
                rows.append(StatusRow("apply", "应用", "待重新应用", "warn", "改动之后还没重新写回游戏"))
            else:
                rows.append(StatusRow("apply", "应用", "未启用", "warn", "点「应用到游戏」让改动生效"))
            self.apply_btn.setEnabled(True)

        # ---- 补译 ----
        total, on = self.ctx.supplement.count()
        if not total:
            rows.append(StatusRow("supplement", "补译", "无补译", "none"))
        elif on:
            rows.append(StatusRow("supplement", "补译", f"补译 {on}/{total}", "info",
                                  "零协包里没有、由本工具补上的文件"))
        else:
            rows.append(StatusRow("supplement", "补译", f"补译已停用（{total}）", "warn"))

        # ---- 待确认（兼容性）----
        if self.ctx.profile.count() == 0:
            rows.append(StatusRow("pending", "待确认", "无待确认", "none"))
        else:
            compat = self.ctx.compat_status()
            n = sum(1 for s, _ in compat.values() if s in ("changed", "missing"))
            if n:
                rows.append(StatusRow("pending", "待确认", f"{n} 条待确认", "warn",
                                      "底本发生了变化，建议逐条复核"))
            else:
                rows.append(StatusRow("pending", "待确认", "兼容正常", "ok"))

        self.status_pill.set_rows(rows)
        self.theme_switch.set_current(theme.current_mode())

    # ---------- 主题 ----------

    def set_theme(self, theme_id: str) -> MainWindow | None:
        """切换界面主题。

        控件在构造时读取颜色 token，所以换主题必须重建界面。这里选择
        **重建整个主窗口**（而不是就地刷新控件）——因为除了颜色，主题还会改变
        形状/描边，并且菜单、快捷键、图鉴页都持有具体控件引用；重建窗口是唯一
        能保证不留悬空引用与陈旧样式的做法。

        返回新窗口（主题未变化时返回 ``None``），便于测试与调用方接管。
        """
        tid = theme.resolve_theme(theme_id)
        if tid == theme.current_mode():
            self.theme_switch.set_current(tid)
            return None
        self.ctx.config.ui.theme = tid
        # 先把当前界面状态落盘（几何/分栏/搜索/条目/剧本位置），新窗口据此还原
        self._capture_session()
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app, tid)
        return self._reopen_for_theme()

    def _reopen_for_theme(self) -> MainWindow:
        new = MainWindow(self.ctx, startup_backup=False)
        # 先显示新窗口再关旧窗口，避免「最后一个窗口关闭 → 应用退出」
        new.show()
        self._switching_theme = True  # closeEvent 会跳过重复的状态落盘
        self.close()
        return new

    # ---------- 环境 / 索引 ----------

    def retry_env(self) -> None:
        self.ctx.refresh_env()
        self.refresh_topbar()
        self._show_page()
        if self.ctx.env.healthy():
            self._ensure_index_async()
        else:
            for issue in self.ctx.env.issues:
                warn(self, "环境检查", issue.message, issue.next_action)

    def choose_dir(self) -> None:
        start = self.ctx.config.game_dir or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "选择《边狱巴士》游戏目录（含 LimbusCompany.exe）", start)
        if not d:
            return
        self._set_dir(d)

    def scan_steam(self) -> None:
        from ..paths import find_steam_game_dirs

        dirs = find_steam_game_dirs()
        if not dirs:
            warn(
                self,
                "自动扫描",
                "未在 Steam 库中找到《边狱巴士》。",
                "请点击「手动选择游戏目录」，或先在 Steam 中安装游戏。",
            )
            return
        if len(dirs) == 1:
            if confirm(
                self,
                "自动扫描",
                f"已找到《边狱巴士》游戏目录：\n{dirs[0]}\n\n使用该目录吗？",
                ok_label="使用",
                danger=False,
            ):
                self._set_dir(str(dirs[0]))
            return
        name, ok = QInputDialog.getItem(self, "选择游戏目录", "找到多个游戏目录：", [str(d) for d in dirs], 0, False)
        if ok and name:
            self._set_dir(name)

    def _set_dir(self, d: str) -> None:
        self.ctx.set_game_dir(d)
        self.refresh_topbar()
        self._show_page()
        if self.ctx.env.healthy():
            self._ensure_index_async()
        else:
            for issue in self.ctx.env.issues:
                warn(self, "环境检查", issue.message, issue.next_action)

    def _ensure_index_async(self, force: bool = False) -> None:
        env = self.ctx.env
        src = self.ctx.text_source
        if not src.ok or src.root is None:
            return
        llc = Path(src.root)
        base = self.ctx.baseline_dir if src.mode == "llc" else None
        strip = src.prefix
        if not force and self.ctx.indexer.manifest_matches(llc, base, strip_prefix=strip):
            self._index_ready()
            return

        def task(progress):
            self.ctx.indexer.build(llc, progress, baseline_dir=base, strip_prefix=strip)

        label = "正在建立文本索引…" + ("（英文原文）" if src.mode == "en" else "")
        self._run_with_progress(task, label, self._index_ready)

    def _index_ready(self, _res=None) -> None:
        """索引进度任务完成回调（后台线程结果忽略）。"""
        self.nav.set_counts(self.ctx.search.count_by_category(), self.ctx.search.count_by_sinner(),
                           self.ctx.search.count_by_role(),
                           {"personality": self.ctx.search.count_entities(KIND_PERSONALITY),
                            "ego": self.ctx.search.count_entities(KIND_EGO)})
        self._populate_filters()
        self.refresh_topbar()
        if not self._session_restored:
            self._session_restored = True
            self._restore_session()  # 分类/筛选/搜索/上次条目/剧本位置
        else:
            self.refresh_list()
        if self.center_stack.currentWidget() is self.codex_page:
            # 启动时索引可能还在重建（图鉴先渲染成空），重建完成后补一次
            self.codex_page.refresh()
        if self.center_stack.currentWidget() is self.enemy_codex_page:
            self.enemy_codex_page.refresh()
        self.statusBar().showMessage(self._index_status_text(), 8000)

    def _index_status_text(self) -> str:
        """状态栏：索引文件数 + 英文基线对照情况。"""
        env = self.ctx.env
        if env.text_source == "en":
            text = f"索引就绪：英文原文 {env.base_file_count} 个文件"
        else:
            text = f"索引就绪：{env.llc_file_count} 个文件"
        if not env.base_ok:
            return text + " · 未找到英文基线（编辑器不显示英文）"
        stats = self.ctx.search.baseline_stats()
        if stats[1]:
            text += f" · 英文对照 {stats[0]}/{stats[1]}"
        return text

    # ---------- 会话记忆（窗口/分栏/分类/筛选/上次条目/剧本位置） ----------

    @staticmethod
    def _b64(data) -> str:
        """QByteArray → base64 字符串（写进 config.json）。"""
        try:
            return bytes(data.toBase64()).decode("ascii")
        except (AttributeError, UnicodeDecodeError):
            return ""

    @staticmethod
    def _unb64(text: str):
        from PySide6.QtCore import QByteArray

        try:
            return QByteArray.fromBase64(text.encode("ascii"))
        except (AttributeError, UnicodeEncodeError, ValueError):
            return None

    def _restore_window_state(self) -> None:
        """启动时恢复窗口大小/位置与两处分栏（不依赖索引）。"""
        ui = self.ctx.config.ui
        geo = self._unb64(ui.geometry)
        if geo is not None and not geo.isEmpty():
            self.restoreGeometry(geo)
        for widget, value in ((self._splitter, ui.splitter),
                              (self.editor.compare_splitter, ui.compare_splitter)):
            state = self._unb64(value)
            if state is not None and not state.isEmpty():
                widget.restoreState(state)

    @staticmethod
    def _set_combo(combo, value: str) -> None:
        idx = combo.findData(value) if value else 0
        combo.blockSignals(True)
        combo.setCurrentIndex(max(idx, 0))
        combo.blockSignals(False)

    def _restore_session(self) -> None:
        """索引就绪后恢复上次的分类/筛选/搜索/条目/剧本位置。"""
        ui = self.ctx.config.ui
        if ui.search:
            self.list_panel.search_edit.blockSignals(True)
            self.list_panel.search_edit.setText(ui.search)
            self.list_panel.search_edit.blockSignals(False)
        self._set_combo(self.list_panel.chapter_combo, ui.chapter)
        self.list_panel.set_levels(self.ctx.search.list_levels(ui.chapter) if ui.chapter else [])
        self._set_combo(self.list_panel.level_combo, ui.level)
        self._set_combo(self.list_panel.season_combo, ui.season)
        self._set_combo(self.list_panel.kind_combo, ui.kind)
        self.list_panel.set_scope(ui.search_scope)
        self.editor.set_baseline_visible(ui.show_baseline)
        category = ui.category if ui.category in _categories.CATEGORIES or ui.category in _categories.PSEUDO_CATEGORIES \
            or ui.category in ("script", "codex", "enemy_codex") else "all"
        self._on_nav_category(category)
        if ui.hit_key:
            self._open_ref_key(ui.hit_key)
        self.script_panel.show_deleted_cb.setChecked(ui.script_show_deleted)
        self.script_panel.unaligned_only_cb.setChecked(ui.script_unaligned_only)
        if ui.script_active and ui.script_chapter and ui.script_stage:
            self.enter_script_mode(ui.script_chapter, ui.script_stage, ui.script_branch or None)

    def _open_ref_key(self, key: str) -> bool:
        """按 EntryRef.key() 重新打开上次的条目（找不到就静默跳过）。"""
        from ..categories import classify
        from ..patch import EntryRef
        from ..search import SearchHit

        try:
            ref = EntryRef.from_key(key)
        except (ValueError, TypeError, IndexError):
            return False
        original, _err = self.ctx.original_of(ref)
        if original is None:
            return False
        hit = SearchHit(file=ref.file, category=classify(ref.file), chapter=chapter_hint(ref.file),
                        ref=ref, text=original)
        self._on_hit_activated(HitView(hit=hit))
        return True

    def _capture_session(self) -> None:
        """关闭窗口时把当前界面状态写进 config.json。"""
        ui = self.ctx.config.ui
        ui.geometry = self._b64(self.saveGeometry())
        ui.splitter = self._b64(self._splitter.saveState())
        ui.compare_splitter = self._b64(self.editor.compare_splitter.saveState())
        ui.category = self._category
        ui.search = self.list_panel.search_edit.text()
        ui.chapter = self.list_panel.current_chapter()
        ui.level = self.list_panel.current_level()
        ui.season = self.list_panel.current_season()
        ui.kind = self.list_panel.current_kind()
        ui.hit_key = self._current_hit.ref.key() if self._current_hit is not None else ""
        ui.script_active = bool(self._script_active)
        ui.script_chapter = self._script_cid or ""
        ui.script_stage = self._script_code or ""
        ui.script_branch = self._script_branch or ""
        ui.script_show_deleted = bool(self.script_panel.show_deleted_cb.isChecked())
        ui.script_unaligned_only = bool(self.script_panel.unaligned_only_cb.isChecked())
        ui.show_baseline = bool(self.editor.baseline_visible())
        ui.search_scope = self.list_panel.current_scope()
        try:
            self.ctx.config_store.save(self.ctx.config)
        except OSError:
            pass  # 记忆保存失败不影响退出

    def closeEvent(self, event) -> None:
        if not self._switching_theme:
            # 换主题重建时状态已在 set_theme 里落过盘，无需重复写
            self._capture_session()
        super().closeEvent(event)

    def _populate_filters(self) -> None:
        eng = self.ctx.search
        self.list_panel.set_chapters(eng.list_chapters())
        self.list_panel.set_levels(eng.list_levels(self.list_panel.current_chapter() or "c1"))
        self.list_panel.set_seasons(eng.list_seasons())
        self.list_panel.set_kinds(eng.list_kinds())

    def _on_filters_changed(self) -> None:
        # 分类下拉由用户改动时才覆盖导航状态（其余筛选保持罪人树等导航选择）
        if self.sender() is self.list_panel.category_combo:
            self._category = self.list_panel.current_category() if self.list_panel.current_category() in _categories.CATEGORIES else self._category
        chapter = self.list_panel.current_chapter()
        self.list_panel.set_levels(self.ctx.search.list_levels(chapter) if chapter else [])
        self.refresh_list()

    # ---------- 列表 / 搜索 ----------

    def _set_crumb(self, key: str) -> None:
        """顶栏面包屑：「分区 › 条目」，让用户随时知道自己在哪。

        照原型 ``.crumb`` 的两级配色：分区名用正文色加粗，条目用暗色，
        分隔符用最暗色。QLabel 走富文本，纯文本原文另存 :attr:`_crumb`
        （会话记忆与测试用）。
        """
        if key == "codex":
            self._set_crumb_parts("图鉴", "人格图鉴")
            return
        if key == "enemy_codex":
            self._set_crumb_parts("图鉴", "敌方图鉴")
            return
        found = _categories.nav_zone_of(key)
        if found:
            self._set_crumb_parts(found[0], found[1])
        else:
            self.crumb.clear()
            self._crumb = ""

    def _set_crumb_parts(self, section: str, item: str) -> None:
        self._crumb = f"{section} › {item}"
        self.crumb.setText(
            f'<span style="color:{theme.TEXT};font-weight:600">{section}</span>'
            f'<span style="color:{theme.TEXT_FAINT}"> › </span>'
            f'<span style="color:{theme.TEXT_DIM}">{item}</span>'
        )

    def _on_nav_category(self, key: str) -> None:
        if key == "script":
            self.nav.set_current(key)
            self._set_crumb(key)
            self.open_script_mode()
            return
        if key == "codex":
            self.nav.set_current(key)
            self._set_crumb(key)
            self.open_codex()
            return
        if key == "enemy_codex":
            self.nav.set_current(key)
            self._set_crumb(key)
            self.open_enemy_codex()
            return
        if key in _categories.CATEGORIES:
            idx = self.list_panel.category_combo.findData(key)
            self.list_panel.category_combo.blockSignals(True)
            self.list_panel.category_combo.setCurrentIndex(max(idx, 0))
            self.list_panel.category_combo.blockSignals(False)
        self._category = key
        self.nav.set_current(key)
        # 点导航 = 回工作台：图鉴页 / 剧本模式都退出，避免「面包屑变了、中间还停在图鉴页」
        if self._script_active:
            self._exit_script_mode()
        if self.center_stack.currentIndex() != 0:
            self.center_stack.setCurrentIndex(0)
        self._set_crumb(key)
        self.refresh_list()

    def _on_search_requested(self, text: str) -> None:
        self.refresh_list()

    def _category_targets(self) -> tuple[list[str] | None, str | None]:
        """根据当前导航/筛选解析 (分类列表, 罪人码)。

        role:* 与 entities:* 由 _entity_context() 另行解析（见 refresh_list）。
        """
        cat = self._category
        if cat.startswith("role:"):
            return None, None
        if cat.startswith("entities:"):
            return None, None
        if cat.startswith("sinner:"):
            parts = cat.split(":")
            cats = ["identity", "ego"]
            code = parts[1] if len(parts) > 1 and parts[1] != "all" else None
            if len(parts) > 2 and parts[2] in ("identity", "ego"):
                cats = [parts[2]]
            return cats, code
        if cat in _categories.CATEGORIES:
            return [cat], None
        return None, None

    def _entity_context(self) -> tuple[str | None, list[str] | None, str | None]:
        """解析当前导航的实体上下文，返回 (kind, roles, entity_key)。

        - role:identity_skill 等 → 该角色的全部条目（跨罪人）
        - entities:personality / entities:ego → 实体一览（本体条目 + 计数提示）
        - sinner:<code>:identity / ego 或 entities 一览里选中某实体 → 该实体的内容
        """
        cat = self._category
        content = self.list_panel.current_content()
        if cat.startswith("role:"):
            role = cat.split(":", 1)[1]
            return None, [role], None
        if cat.startswith("entities:"):
            kind = KIND_PERSONALITY if cat.endswith("personality") else KIND_EGO
            key = self.list_panel.current_entity()
            if key is None:  # 「全部」= 实体一览（每行一个人格/EGO 的本体）
                return kind, [ROLE_IDENTITY if kind == KIND_PERSONALITY else ROLE_EGO], None
            return kind, (None if content == "all" else [content]), key
        if cat.startswith("sinner:") and cat.count(":") >= 2:
            kind = KIND_PERSONALITY if cat.endswith("identity") else KIND_EGO
            key = self.list_panel.current_entity()
            base = ROLE_IDENTITY if kind == KIND_PERSONALITY else ROLE_EGO
            if key is None:  # 该罪人的全部人格/EGO（本体行）
                return kind, [base], None
            return kind, (None if content == "all" else [content]), key
        return None, None, None

    def _open_entity(self, entity_key: str) -> None:
        """从实体一览跳到某个实体的全部内容（技能/剧情/语音）。"""
        kind = KIND_PERSONALITY if entity_key.startswith("P:") else KIND_EGO
        cat = "entities:personality" if kind == KIND_PERSONALITY else "entities:ego"
        if self._category != cat:
            self._on_nav_category(cat)
        self.list_panel.set_entity_context(
            self.ctx.search.list_entities(kind, None),
            CONTENT_CHOICES.get(kind) or [("all", "全部")],
            entity_key, "all",
            "全部人格" if kind == KIND_PERSONALITY else "全部 E.G.O",
        )
        self.refresh_list()

    def _entity_counts_table(self, kind: str) -> dict[str, dict]:
        """{entity_key: {skill_count, story_count, voice_count}}（实体一览页的行内提示）。"""
        skill_role = "identity_skill" if kind == KIND_PERSONALITY else "ego_skill"
        story_role = "identity_story" if kind == KIND_PERSONALITY else None
        voice_role = "identity_voice" if kind == KIND_PERSONALITY else "ego_voice"
        roles = [r for r in (skill_role, story_role, voice_role) if r]
        rows = self.ctx.search.count_by_entity_role(roles)
        table: dict[str, dict] = {}
        for (key, role), n in rows.items():
            slot = table.setdefault(key, {"skill_count": 0, "story_count": 0, "voice_count": 0})
            if role == skill_role:
                slot["skill_count"] = n
            elif role == story_role:
                slot["story_count"] = n
            elif role == voice_role:
                slot["voice_count"] = n
        return table

    def _refresh_entity_context(self, kind: str | None, sinner: str | None = None) -> None:
        """填充实体选择器 + 内容类型下拉（非实体上下文则隐藏）。"""
        if not kind:
            self.list_panel.set_entity_context(None, None)
            return
        entities = self.ctx.search.list_entities(kind, sinner)
        choices = CONTENT_CHOICES.get(kind) or [("all", "全部")]
        current = self.list_panel.current_entity()
        if current and not any(e.get("entity_key") == current for e in entities):
            current = None
        content = self.list_panel.current_content()
        all_label = "全部人格" if kind == KIND_PERSONALITY else "全部 E.G.O"
        self.list_panel.set_entity_context(entities, choices, current, content, all_label)

    def _scope_hits(self, text: str, scope: str, categories, chapter: str, level: str,
                    season: str, kind: str, sinner: str, source: str | None = None,
                    entity_key: str | None = None, roles: list[str] | None = None,
                    overview: bool = False) -> list[SearchHit]:
        """按搜索范围取结果：原文/英文走索引，自定义走方案（Python 侧合并）。"""
        hits: list[SearchHit] = []
        if not text:
            # 无关键词时：自定义范围没有"全部列出"的意义，回退成原文范围
            scope = "original" if scope == "custom" else scope
        if scope in ("original", "baseline", "all") or not text:
            hits = self.ctx.search.search(
                text or None,
                categories=categories,
                chapter=chapter or None,
                level=level or None,
                season=season or None,
            source=source,
                kind_label=kind or None,
                sinner_code=sinner or None,
                limit=500,
                scope="all" if (not text or scope == "all") else scope,
                entity_key=entity_key,
                roles=roles,
                order="relevance" if text else "natural",
                field_path=[{"k": "name"}] if overview else None,
            )
        if text and scope in ("custom", "all"):
            hits = hits + self._custom_hits(text, categories, chapter, level, season, kind, sinner)
        return hits

    def _custom_hits(self, text: str, categories, chapter: str, level: str, season: str,
                     kind: str, sinner: str) -> list[SearchHit]:
        """在方案（自定义文本）里搜索；元数据从索引批量取回，复用同一套筛选。"""
        want = normalize(text)
        if not want:
            return []
        entries = [e for e in self.ctx.profile.values() if want in normalize(e.value or "")]
        if not entries:
            return []
        meta = self.ctx.search.lookup_meta([e.ref for e in entries])
        out: list[SearchHit] = []
        for entry in entries:
            hit = meta.get(entry.ref.key())
            if hit is None:
                # 索引里没有（例如零协更新后条目失效）：仍按文件路径给出基本信息
                rel = entry.ref.file
                hit = SearchHit(file=rel, category=classify(rel), chapter=chapter_hint(rel),
                                ref=entry.ref, text=entry.value)
            if categories and hit.category not in categories:
                continue
            if chapter and hit.chapter_id != chapter:
                continue
            if level and hit.level_key != level:
                continue
            if season and hit.season != season:
                continue
            if kind and hit.kind_label != kind:
                continue
            if sinner and hit.sinner_code != sinner:
                continue
            out.append(hit)
        return out

    @staticmethod
    def _english_hit(hit: SearchHit, text: str) -> bool:
        """该命中是否来自英文基线（用于列表标记）。"""
        if not text or not hit.text_en:
            return False
        return normalize(text) in normalize(hit.text_en)

    def refresh_list(self) -> None:
        if not self.ctx.env.text_ok:
            self.list_panel.set_hits([])
            return
        text = self.list_panel.search_edit.text()
        status_filter = self.list_panel.current_status()
        chapter = self.list_panel.current_chapter()
        level = self.list_panel.current_level()
        season = self.list_panel.current_season()
        kind = self.list_panel.current_kind()
        cat = self._category
        categories, sinner = self._category_targets()
        ent_kind, ent_roles, ent_key = self._entity_context()
        if cat.startswith(("role:", "entities:", "sinner:")):
            self._refresh_entity_context(ent_kind, sinner)
            ent_roles, ent_key = self._entity_context()[1:]

        if cat == "supplement":
            raw = self._scope_hits(text, self.list_panel.current_scope(), categories, chapter, level,
                                   season, kind, sinner, entity_key=None, roles=None,
                                   overview=False, source="supplement")
        elif cat == "favorites":
            raw: list[SearchHit] = self._profile_hits(favorites_only=True)
        elif cat == "recent":
            raw = self._profile_hits(recent=True)
        elif cat == "pending":
            raw = self._profile_hits(compat_filter={"changed", "missing"})
        else:
            overview_mode = cat.startswith("entities:") and self.list_panel.current_entity() is None
            raw = self._scope_hits(text, self.list_panel.current_scope(), categories,
                                   chapter, level, season, kind, sinner,
                                   entity_key=ent_key, roles=ent_roles, overview=overview_mode,
                                   source=None)

        entity_info: dict[str, dict] = {}
        overview = cat.startswith("entities:") and self.list_panel.current_entity() is None
        if cat.startswith("entities:"):
            kind_for_counts = KIND_PERSONALITY if cat.endswith("personality") else KIND_EGO
            entity_info = self._entity_counts_table(kind_for_counts)  # 注意：别覆盖筛选用的 kind
        if overview:
            # 每个实体只保留一行（name 叶子已在 SQL 层过滤；E.G.O 变体记录会合并到基础实体）
            seen_entities: set[str] = set()
            unique: list[SearchHit] = []
            for h in raw:
                if not h.entity_key or h.entity_key in seen_entities:
                    continue
                seen_entities.add(h.entity_key)
                unique.append(h)
            raw = unique
        compat = self.ctx.compat_status()
        views: list[HitView] = []
        for h in raw:
            # 伪分类（收藏/最近/待确认）在 Python 侧应用维度筛选
            if cat in ("favorites", "recent", "pending"):
                if chapter and h.chapter_id != chapter:
                    continue
                if level and h.level_key != level:
                    continue
                if season and h.season != season:
                    continue
                if kind and h.kind_label != kind:
                    continue
                if categories and h.category not in categories:
                    continue
                if sinner and h.sinner_code != sinner:
                    continue
                if text:
                    # 无 KeyID 的记录用「记录 #N」参与匹配，避免退化成字符串 "none"
                    key_text = h.display_key if hasattr(h, "display_key") else ref_label(h.ref)
                    if normalize(text) not in normalize(h.text) and normalize(text) not in normalize(key_text):
                        continue
            entry = self.ctx.profile.get(h.ref)
            english = self._english_hit(h, text)
            role_label = ROLE_LABELS.get(h.role or "", "")
            if cat.startswith("entities:") and h.role in ("identity", "ego"):
                # 实体一览：本体行附加「技能 N · 剧情 N · 语音 N」
                info = entity_info.get(h.entity_key) if entity_info else None
                if info:
                    bits = []
                    if info.get("skill_count"):
                        bits.append(f"技能 {info['skill_count']}")
                    if info.get("story_count"):
                        bits.append(f"剧情 {info['story_count']}")
                    if info.get("voice_count"):
                        bits.append(f"语音 {info['voice_count']}")
                    if bits:
                        role_label = " · ".join(bits)
            if entry is not None:
                cs = compat.get(h.ref.key(), ("ok", ""))[0]
                status = STATUS_MISSING if cs == "missing" else STATUS_PENDING if cs == "changed" else STATUS_MODIFIED
                v = HitView(hit=h, status=status, favorite=entry.favorite, custom=entry.value,
                            english_hit=english, role_label=role_label)
            else:
                v = HitView(hit=h, status=STATUS_UNMODIFIED, english_hit=english, role_label=role_label)
            if status_filter == "favorite":
                if not v.favorite:
                    continue
            elif status_filter and v.status != status_filter:
                continue
            views.append(v)

        views = views if overview else self._dedupe_views(views)
        note = ""
        if overview:
            group = self.list_panel.current_group()
            if group:
                views, note = self._group_entity_views(views, group)
        self.list_panel.model.set_highlight(text)
        self.list_panel.set_filter_visibility(self._category)
        self.list_panel.group_combo.setVisible(overview)
        self.list_panel.set_hits(views, truncated=len(raw) >= 500, note=note)

    def _entity_group_label(self, view: HitView, group: str) -> str:
        """实体一览的一行 → 所属分组标题。"""
        parsed = parse_entity_key(view.hit.entity_key or "")
        if not parsed:
            return _GROUP_LAST
        kind, entity_id = parsed
        meta = self.ctx.maps.identity_meta(entity_id) if kind == KIND_PERSONALITY \
            else self.ctx.maps.ego_meta(entity_id)
        if group == "season":
            label = season_display(meta)
            if label:
                return label
            # 没有赛季但有获取方式（瓦夜/活动/通行证）→ 用它当分组，别一律塞进「未标注」
            acq = (meta or {}).get("acq")
            if acq and acq != "unknown":
                return dict(ACQ_GROUP_ORDER).get(acq, _GROUP_LAST)
            return _GROUP_LAST
        acq = (meta or {}).get("acq")
        if acq in (None, "", "unknown"):
            # 赛季标了但获取方式没标 → 按赛季推断，避免整片「未标注」
            season = (meta or {}).get("season")
            return "赛季限定" if season not in (None, 0) else _GROUP_LAST
        return dict(ACQ_GROUP_ORDER).get(acq, _GROUP_LAST)

    def _group_entity_views(self, views: list[HitView], group: str) -> tuple[list[HitView], str]:
        """把人格/EGO 一览插进分组标题行，并返回「标注进度」说明。"""
        buckets: dict[str, list[HitView]] = {}
        for view in views:
            buckets.setdefault(self._entity_group_label(view, group), []).append(view)
        if group == "season":
            order = sorted((k for k in buckets if k != _GROUP_LAST), key=_season_group_rank)
        else:
            ranks = {label: i for i, (_key, label) in enumerate(ACQ_GROUP_ORDER)}
            order = sorted((k for k in buckets if k != _GROUP_LAST),
                           key=lambda k: (ranks.get(k, 50), k))
        if _GROUP_LAST in buckets:
            order.append(_GROUP_LAST)

        out: list[HitView] = []
        for label in order:
            rows = buckets[label]
            out.append(HitView(hit=rows[0].hit, header=f"{label}（{len(rows)}）"))
            out.extend(rows)

        total = len(views)
        labeled = total - len(buckets.get(_GROUP_LAST, []))
        pct = round(labeled * 100 / total) if total else 100
        kind_label = "人格" if self._category == "entities:personality" else "E.G.O"
        note = f"{kind_label}标注进度 {labeled}/{total}（{pct}%）" + \
            (f"，未标注 {total - labeled} 个排在最后" if labeled < total else "")
        return out, note

    @staticmethod
    def _dedupe_views(views: list[HitView]) -> list[HitView]:
        """按文本去重显示：同一文本合并为一行并累计「重复 N 处」。

        保留优先级：已修改 > 待确认 > 已失效 > 收藏 > 普通（保证能编辑到有意义的那条）。
        """
        order = {STATUS_MODIFIED: 4, STATUS_PENDING: 3, STATUS_MISSING: 2}
        best: dict[str, HitView] = {}
        for v in views:
            key = v.hit.text
            cur = best.get(key)
            if cur is None:
                best[key] = v
                continue
            cur.dup_count += 1
            v.dup_count = cur.dup_count
            cur_pri = order.get(cur.status, 0) + (1 if cur.favorite else 0)
            new_pri = order.get(v.status, 0) + (1 if v.favorite else 0)
            if new_pri > cur_pri:
                best[key] = v
        return list(best.values())

    def _profile_hits(self, favorites_only: bool = False, recent: bool = False,
                      compat_filter: set[str] | None = None) -> list[SearchHit]:
        entries = self.ctx.profile.values()  # 快照：部署线程可能同时在改条目
        if compat_filter:
            compat = self.ctx.compat_status()
            entries = [e for e in entries if compat.get(e.ref.key(), ("ok", ""))[0] in compat_filter]
        if favorites_only:
            entries = [e for e in entries if e.favorite]
        if recent:
            entries.sort(key=lambda e: e.modified_at, reverse=True)
            entries = entries[:200]
        hits: list[SearchHit] = []
        for e in entries:
            record, _ = self.ctx.load_record(e.ref)
            from ..categories import character_hint, sinner_of

            cat = classify(e.ref.file)
            story = story_of(e.ref.file)
            meta = None
            if cat == "identity":
                meta = self.ctx.maps.identity_meta(e.ref.id)
            elif cat == "ego":
                meta = self.ctx.maps.ego_meta(e.ref.id)
            elif cat == "enemy":
                meta = self.ctx.maps.enemy_meta(e.ref.id)
            sinner = sinner_of(cat, e.ref.id)
            sinner_code, sinner_name = (sinner if sinner else (None, None))
            character = character_hint(e.ref.file, record) if record else None
            if character is None and sinner_name:
                character = sinner_name
            hits.append(
                SearchHit(
                    file=e.ref.file,
                    category=cat,
                    chapter=chapter_hint(e.ref.file),
                    ref=e.ref,
                    text=e.value,
                    character=character,
                    chapter_id=story.chapter_id if story else None,
                    chapter_label=story.chapter_label if story else None,
                    level_key=story.level_key if story else None,
                    level_label=story.level_label if story else None,
                    season=season_key(meta),
                    season_label=season_display(meta),
                    acq_label=acq_display(meta),
                    kind_group=meta.get("group") if meta else None,
                    kind_label=kind_display(meta),
                    sinner_code=sinner_code,
                    sinner_name=sinner_name,
                )
            )
        return hits

    def _on_hit_activated(self, view: HitView) -> None:
        hit = view.hit
        original, err = self.ctx.original_of(hit.ref)
        if original is None:
            error(self, "无法读取原文", err or "未知错误", "检查零协汉化是否完整，或重新检测环境。")
            return
        record, _ = self.ctx.load_record(hit.ref)
        entry = self.ctx.profile.get(hit.ref)
        en_text, en_note = self.ctx.baseline_of(hit.ref)  # 英文只读参考（失败给中文原因）
        self._current_hit = hit
        self.editor.load_hit(
            ref=hit.ref,
            original_text=original,
            custom=entry.value if entry else None,
            record=record,
            chapter=hit.chapter,
            category=hit.category,
            character=hit.character,
            favorite=entry.favorite if entry else False,
            advanced=self.ctx.config.advanced_mode,
            baseline_text=en_text,
            baseline_note=en_note,
        )
        key = hit.ref.key()
        compat = self.ctx.compat_status().get(key)
        if compat and compat[0] == "changed":
            self.editor.set_status(f"※ 原文已变化：{compat[1]}。请核对后再保存。", ok=False)
        elif compat and compat[0] == "missing":
            self.editor.set_status(f"※ {compat[1]}。重新保存可尝试修复。", ok=False)

        # 剧本模式可用性（条目所在文件能对应到 wiki 关卡页时显示按钮）
        self._story_ctx = None
        stages = self.ctx.storybook.file_stages(hit.file)
        if stages:
            cid, code, _ = stages[0]
            self._story_ctx = (cid, code)
            self.editor.set_story_available(True)
        else:
            self.editor.set_story_available(False)

    def _on_story_open(self) -> None:
        """打开剧本模式：中间列表切换为该关卡剧本。"""
        if not self._story_ctx or not self.ctx.env.text_ok:
            return
        self._enter_script_mode(self._story_ctx[0], self._story_ctx[1])

    # ---------- 剧本模式（中间列表切换） ----------

    def _chapter_label(self, cid: str) -> str:
        for c in self.ctx.storybook.chapter_list():
            if c.get("chapter_id") == cid:
                return c.get("chapter_label") or cid
        return cid

    def _enter_script_mode(self, cid: str, code: str, branch: str | None = None) -> None:
        book = self.ctx.storybook
        stage = book.stage(cid, code)
        if stage is None:
            warn(self, "剧本模式", "该关卡暂无剧本对照数据（本地汉化包可能滞后）。")
            return
        if not self._script_active:
            self._inner_splitter.replaceWidget(self._inner_splitter.indexOf(self.list_panel), self.script_panel)
            self._script_active = True
        self._script_cid = cid
        self._script_code = code
        self._script_branch = branch or None
        items = book.stage_items(cid, code, self._script_branch)
        self.script_panel.load_stage(
            self._chapter_label(cid), book.stages_of(cid), code, items,
            chapters=book.chapter_list(), chapter_id=cid, branch_id=self._script_branch,
        )
        self._sync_page_tabs()

    def _on_script_chapter(self, cid: str) -> None:
        """剧本模式内切换章节：跳到该章第一个关卡。"""
        if not cid or not self._script_active:
            return
        stages = self.ctx.storybook.stages_of(cid)
        if not stages:
            return
        code = stages[0].get("stage_code")
        self._script_cid = cid
        self._story_ctx = (cid, code)
        self._enter_script_mode(cid, code)

    def open_codex(self) -> None:
        """顶栏「人格图鉴」：切到图鉴页。"""
        if not self.ctx.env.text_ok:
            warn(self, "人格图鉴", "尚未找到可用的文本。", "先设置游戏目录并建立索引；或安装零协汉化。")
            self._sync_page_tabs()
            return
        self.center_stack.setCurrentWidget(self.codex_page)
        if self.codex_page.level == 1 and self.codex_page.entity is None \
                and not self.ctx.search.count_entities(KIND_PERSONALITY):
            # 索引还没建好时构造出来的图鉴页是空的：进页面时补渲染一次
            self.codex_page.refresh()
        self._sync_page_tabs()

    def open_enemy_codex(self) -> None:
        """顶栏/导航「敌方图鉴」：切到敌方图鉴页。"""
        if not self.ctx.env.text_ok:
            warn(self, "敌方图鉴", "尚未找到可用的文本。", "先设置游戏目录并建立索引；或安装零协汉化。")
            self._sync_page_tabs()
            return
        self.center_stack.setCurrentWidget(self.enemy_codex_page)
        if self.enemy_codex_page.level == 1 and self.enemy_codex_page.entity is None \
                and not self.ctx.search.count_entities(KIND_ENEMY):
            # 索引还没建好时构造出来的图鉴页是空的：进页面时补渲染一次
            self.enemy_codex_page.refresh()
        self._sync_page_tabs()

    def open_identity_story(self, entity_key: str) -> None:
        """在剧本面板里逐行阅读某人格的剧情（本地文本，无 wiki 对照）。"""
        from ..entities import parse_entity_key

        parsed = parse_entity_key(entity_key)
        if not parsed:
            return
        _kind, entity_id = parsed
        rel = f"StoryData/P{entity_id}.json"
        path = Path(self.ctx.env.llc_pack_dir) / rel
        if not path.is_file():
            info(self, "没有剧情", f"零协包里没有 {rel}。")
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            error(self, "无法读取剧情", str(exc))
            return
        records = data.get("dataList") if isinstance(data, dict) else None
        if not isinstance(records, list) or not records:
            info(self, "没有剧情", "该文件没有剧情内容。")
            return
        summary = self.ctx.search.entity_summary(entity_key) or {}
        items = []
        for i, rec in enumerate(records):
            if not isinstance(rec, dict):
                continue
            items.append({
                "type": "line", "speaker": speaker_of(rec) or "",
                "title": rec.get("title") or "", "text": rec.get("content") or "",
                "file": rel, "page": rel, "record": i, "wiki_only": False,
                "place": rec.get("place") or "",
            })
        self.center_stack.setCurrentIndex(0)
        if not self._script_active:
            self._inner_splitter.replaceWidget(self._inner_splitter.indexOf(self.list_panel), self.script_panel)
            self._script_active = True
        self._script_cid = None
        self._script_code = None
        self._story_ctx = None
        sinner = summary.get("sinner_name") or ""
        name = summary.get("name") or ""
        label = name if name and name in sinner else f"{sinner}{name}"
        self.script_panel.load_stage(f"{label} · 人格剧情（本地，未与 wiki 对照）", [], None, items)

    def enter_script_mode(self, cid: str | None = None, code: str | None = None,
                          branch: str | None = None) -> None:
        """进入指定章节/关卡（可带分支）的剧本模式（会话恢复与顶部入口共用）。"""
        if cid and code:
            self._story_ctx = (cid, code)
            self._enter_script_mode(cid, code, branch)
            return
        self.open_script_mode()

    def open_script_mode(self) -> None:
        """顶栏入口：进入剧本模式（默认当前章节，否则第一章第一个关卡）。"""
        if not self.ctx.env.text_ok:
            warn(self, "剧本模式", "尚未找到可用的文本，无法打开剧本。", "先设置游戏目录并建立索引；或安装零协汉化。")
            self._sync_page_tabs()
            return
        chapters = self.ctx.storybook.chapter_list()
        if not chapters:
            warn(self, "剧本模式", "暂无剧本对照数据。")
            self._sync_page_tabs()
            return
        cid = self._script_cid or (self._story_ctx[0] if self._story_ctx else chapters[0].get("chapter_id"))
        stages = self.ctx.storybook.stages_of(cid or "")
        if not stages:
            cid = chapters[0].get("chapter_id")
            stages = self.ctx.storybook.stages_of(cid)
        code = self._story_ctx[1] if self._story_ctx and self._story_ctx[0] == cid else (stages[0].get("stage_code") if stages else None)
        if cid and code:
            self._enter_script_mode(cid, code)
        self._sync_page_tabs()

    def _reload_script_panel(self, cid: str, code: str, focus_key: str | None = None) -> None:
        items = self.ctx.storybook.stage_items(cid, code, self._script_branch)
        self.script_panel.load_stage(
            self._chapter_label(cid), self.ctx.storybook.stages_of(cid), code, items,
            chapters=self.ctx.storybook.chapter_list(), chapter_id=cid, focus_key=focus_key,
            branch_id=self._script_branch,
        )

    def _exit_script_mode(self) -> None:
        if self._script_active:
            self._inner_splitter.replaceWidget(self._inner_splitter.indexOf(self.script_panel), self.list_panel)
            self._script_active = False
            self._script_cid = None
            self._script_code = None
            self._script_branch = None
            self.refresh_list()
        self._sync_page_tabs()

    def _script_stage_changed(self, data) -> None:
        """顶栏切换关卡或关卡下的分支（RPG 关卡）。"""
        if isinstance(data, dict):
            code, branch = data.get("stage"), data.get("branch")
        else:  # 兼容旧调用：只给关卡号
            code, branch = data, None
        if not (self._script_active and self._script_cid and code):
            return
        stage = self.ctx.storybook.stage(self._script_cid, code)
        if not stage:
            return
        self._script_code = code
        self._script_branch = branch or None
        self.script_panel.show_items(
            self.ctx.storybook.stage_items(self._script_cid, code, self._script_branch))
        self._story_ctx = (self._script_cid, code)

    def _on_script_line(self, item: dict) -> None:
        from ..story_rpg import entry_ref_for_item

        relfile = item.get("file")
        record = item.get("record")
        if not relfile or record is None or item.get("wiki_only"):
            self._manual_match(item)
            return
        # 由 文件+记录下标 找到条目 id 并载入右侧编辑器（零协包无文件时回退 supplement）
        data, err = self.ctx.load_pack_json(relfile)
        if data is None:
            error(self, "无法读取记录", err or "未知错误")
            return
        dl = data.get("dataList") if isinstance(data, dict) else None
        if not isinstance(dl, list) or not (0 <= record < len(dl)) or not isinstance(dl[record], dict):
            error(self, "无法读取记录", "记录定位失败。")
            return
        ref = entry_ref_for_item(item, dl[record])
        original, err = self.ctx.original_of(ref)
        if original is None:
            error(self, "无法读取原文", err or "未知错误")
            return
        from ..categories import classify
        from ..search import SearchHit

        hit = SearchHit(file=relfile, category=classify(relfile), chapter=chapter_hint(relfile), ref=ref, text=original)
        self._on_hit_activated(HitView(hit=hit))

    def _script_loc(self) -> tuple[str | None, str | None]:
        """当前剧本模式正在显示的 (chapter_id, stage_code)。"""
        if self._script_cid and self._script_code:
            return self._script_cid, self._script_code
        return self._story_ctx or (self._script_cid, None)

    def _used_records(self, page: str) -> set[int]:
        """该页已被其它行占用的零协记录下标。"""
        return {
            i.get("record")
            for c in self.ctx.storybook.chapter_list()
            for s in c.get("stages", [])
            for i in s.get("items", [])
            if i.get("type") == "line" and i.get("page") == page and i.get("record") is not None
        }

    def _manual_match(self, item: dict) -> None:
        """手动为未对齐行建立与零协记录的对应（或标记跳过）。"""
        from .mapping_dialog import ManualMatchDialog

        page = item.get("page")
        key = item.get("key")
        relfile = item.get("file")
        if not page or not key or not relfile:
            info(self, "无法建立对应", "该行缺少定位信息（请重建剧本数据）。")
            return
        used = self._used_records(page)
        cands = self.ctx.story_edit.candidates(relfile, used)
        if not cands:
            warn(self, "无法建立对应", f"本地文件 {relfile} 没有可用记录。")
            return
        dlg = ManualMatchDialog(self, item.get("text", ""), relfile, cands)
        if safe_exec(dlg) != dlg.DialogCode.Accepted or dlg.result_value is None:
            return
        kind, rec = dlg.result_value
        cid, code = self._script_loc()
        nxt = self.script_panel.next_unaligned_key(item)  # 刷新后把焦点落到下一条未对齐行
        if kind == "record":
            n = self.ctx.apply_story_mapping(page, key, record=int(rec))
            info(self, "已建立对应", f"已把该句对应到零协记录 [{rec}]（本次应用 {n} 条手动对应）。", "现在可以直接编辑该行了。")
        elif kind == "skip":
            self.ctx.apply_story_mapping(page, key, skip=True)
        else:
            self.ctx.apply_story_mapping(page, key, record=None)
        if cid and code:
            self._reload_script_panel(cid, code, focus_key=nxt)

    def _on_script_skip(self, item: dict) -> None:
        """剧本面板按 S：把当前未对齐行标记为跳过，然后刷新面板。"""
        page, key = item.get("page"), item.get("key")
        if not page or not key:
            info(self, "无法标记跳过", "该行缺少定位信息（请重建剧本数据）。")
            return
        nxt = self.script_panel.next_unaligned_key(item)
        self.ctx.apply_story_mapping(page, key, skip=True)
        cid, code = self._script_loc()
        if cid and code:
            self._reload_script_panel(cid, code, focus_key=nxt)

    # ---------- 自动建议对应 ----------

    def _used_records_all(self) -> dict[str, set[int]]:
        """全剧本每个页面已被占用的记录下标（自动建议用）。"""
        used: dict[str, set[int]] = {}
        for chapter in self.ctx.storybook.chapter_list():
            for stage in chapter.get("stages", []):
                for item in stage.get("items", []):
                    if item.get("type") != "line" or not isinstance(item.get("record"), int):
                        continue
                    page = item.get("page")
                    if page:
                        used.setdefault(page, set()).add(item["record"])
        return used

    def _suggest_for(self, items: list[dict], scope_label: str) -> int:
        """对给定未对齐行做相似度建议 → 弹窗确认 → 批量写入并刷新。返回应用条数。"""
        from .suggest_dialog import SuggestDialog

        se = self.ctx.story_edit
        rows = [i for i in items if i.get("key") and i.get("file") and i.get("page")]
        if not rows:
            info(self, "自动建议对应", "当前范围没有可自动处理的未对应行。")
            return 0
        suggestions = se.suggest_matches(rows, self._used_records_all())
        if not suggestions:
            info(self, "自动建议对应",
                 f"{scope_label} 的 {len(rows)} 行里没有找到足够相似的零协记录。",
                 "可以逐条手动建立对应，或直接删除/跳过这些行。")
            return 0
        dlg = SuggestDialog(self, suggestions, scope_label)
        if safe_exec(dlg) != dlg.DialogCode.Accepted or not dlg.result_value:
            return 0
        chosen = dlg.result_value
        n = se.apply_suggestions(chosen)
        se.rebuild()
        self.ctx.storybook.reload()
        cid, code = self._script_loc()
        if cid and code:
            self._reload_script_panel(cid, code)
        self.refresh_topbar()
        info(self, "已建立对应", f"已按建议建立 {n} 条对应（相似度 ≥ 85%）。",
             "这些行现在可以直接编辑；剩余未对应行可在「只看未对应」里继续处理。")
        return n

    def _on_script_suggest(self, item: dict) -> None:
        """右键「自动建议对应（本关）」：对当前关卡所有未对应行做建议。"""
        self._suggest_for(self.script_panel.unaligned_items(), "本关")

    def suggest_all_story(self) -> None:
        """操作菜单：对全部主线关卡一次性做自动建议。"""
        rows: list[dict] = []
        for chapter in self.ctx.storybook.chapter_list():
            for stage in chapter.get("stages", []):
                for item in stage.get("items", []):
                    if item.get("type") == "line" and item.get("wiki_only") and item.get("key") \
                            and not item.get("skip") and not item.get("deleted"):
                        rows.append(item)
        if not rows:
            info(self, "自动建议对应", "全部主线已经没有未对应行了。")
            return
        self._suggest_for(rows, "全部主线")

    def _on_script_delete(self, item: dict) -> None:
        """Delete / 右键「删除该行」：把该行从剧本中移除（本地覆盖，可恢复）。"""
        page, key = item.get("page"), item.get("key")
        if not page or not key:
            info(self, "无法删除", "该行缺少定位信息（请重建剧本数据）。")
            return
        nxt = self.script_panel.next_unaligned_key(item)
        self.ctx.apply_story_mapping(page, key, deleted=True)
        cid, code = self._script_loc()
        if cid and code:
            self._reload_script_panel(cid, code, focus_key=nxt)
        self.refresh_topbar()

    def _on_script_restore(self, item: dict) -> None:
        """右键「恢复该行」：清除删除/跳过/对应覆盖，行回到剧本里。"""
        page, key = item.get("page"), item.get("key")
        if not page or not key:
            info(self, "无法恢复", "该行缺少定位信息（请重建剧本数据）。")
            return
        self.ctx.apply_story_mapping(page, key, record=None)
        cid, code = self._script_loc()
        if cid and code:
            self._reload_script_panel(cid, code, focus_key=key)
        self.refresh_topbar()

    def _on_script_unskip(self, item: dict) -> None:
        """右键「取消跳过」：清除覆盖，行回到未对齐状态。"""
        self._on_script_restore(item)

    def _on_script_delete_all(self, item: dict) -> None:
        """右键「删除本关全部未对应行」：当前关卡所有未对齐行一次性删除。"""
        rows = self.script_panel.unaligned_items()
        if not rows:
            info(self, "无法删除", "当前关卡没有未对应行。")
            return
        if not confirm(self, "删除本关全部未对应行",
                       f"将把当前关卡的 {len(rows)} 行未对应台词从剧本中移除（本地覆盖，"
                       "可勾选「显示已删除」后逐行恢复）。零协汉化不受影响。",
                       ok_label="删除"):
            return
        n = self.ctx.story_edit.mark_deleted_many(
            [(i.get("page"), i.get("key")) for i in rows]
        )
        self.ctx.story_edit.rebuild()
        self.ctx.storybook.reload()
        cid, code = self._script_loc()
        if cid and code:
            self._reload_script_panel(cid, code)
        self.refresh_topbar()
        info(self, "已删除", f"已从剧本中移除 {n} 行未对应台词。",
             "需要找回时勾选顶栏「显示已删除」，右键「恢复该行」。")

    def _on_script_batch(self, item: dict) -> None:
        """右键「从该行起批量对应…」：一次分配多条，最后统一重建 + 刷新。"""
        from .batch_dialog import BatchMatchDialog, plan_batch

        page, key, relfile = item.get("page"), item.get("key"), item.get("file")
        if not page or not key or not relfile:
            info(self, "无法建立对应", "该行缺少定位信息（请重建剧本数据）。")
            return
        rows = self.script_panel.contiguous_unaligned(item)
        if not rows:
            info(self, "无法建立对应", "该行不是未对齐行（可能已对齐或已标记跳过）。")
            return
        used = self._used_records(page)
        cands = self.ctx.story_edit.candidates(relfile, used)
        if not cands:
            warn(self, "无法建立对应", f"本地文件 {relfile} 没有可用记录。")
            return
        dlg = BatchMatchDialog(self, rows, cands)
        if safe_exec(dlg) != dlg.DialogCode.Accepted or dlg.result_value is None:
            return
        start_record, count = dlg.result_value
        plan = plan_batch(rows, start_record, count, used, cands)
        if not plan:
            warn(self, "无法建立对应", "没有可用的记录可供分配。", "换一个起始记录，或先用「建立对应」逐条处理。")
            return
        last_item = rows[min(len(plan), len(rows)) - 1]
        nxt = self.script_panel.next_unaligned_key(last_item)
        se = self.ctx.story_edit
        for line_key, rec in plan:
            se.set_record(page, line_key, rec)
        applied = se.rebuild()  # 批量：只重建一次（不逐条走 apply_story_mapping）
        self.ctx.storybook.reload()
        cid, code = self._script_loc()
        if cid and code:
            self._reload_script_panel(cid, code, focus_key=nxt)
        if applied:
            info(self, "已建立对应", f"已建立 {len(plan)} 条对应。", "可继续右键批量对应，或逐条进入编辑器修改。")
        else:
            warn(self, "已建立对应", f"已写入 {len(plan)} 条对应，但剧本数据未能重建。", "检查剧本数据是否完整后重试。")

    # ---------- 编辑 ----------

    def _on_save(self, ref, value: str) -> None:
        res = self.ctx.upsert_entry(ref, value)
        if not res.ok:
            error(self, "保存失败", res.message, "检查零协汉化后重试。")
            return
        self.ctx.save_profile()
        now = datetime.now().strftime("%H:%M:%S")
        note = "（空文本）" if value == "" else ""
        self.editor.set_status(f"{res.message}{note} · {now}")
        self.refresh_topbar()
        self._refresh_editor_state()

    def _on_restore(self, ref) -> None:
        if not confirm(self, "还原为原文", "将该条目还原为零协原文并删除自定义文本？", ok_label="还原", danger=False):
            return
        original, err = self.ctx.original_of(ref)
        if original is None:
            error(self, "还原失败", err or "未知错误")
            return
        self.ctx.upsert_entry(ref, original)
        self.ctx.save_profile()
        self.editor.custom_edit.setPlainText(original)
        self.editor.set_status("已还原为原文")
        self.refresh_topbar()
        self._refresh_editor_state()

    def _on_favorite(self, ref, checked: bool) -> None:
        entry = self.ctx.profile.get(ref)
        if entry is None:
            # 未修改条目的收藏：保存一个与原文相同的占位不可取，仅提示
            info(self, "收藏", "请先保存修改后收藏（收藏仅适用于已修改条目）。")
            self.editor.fav_btn.setChecked(False)
            return
        entry.favorite = checked
        self.ctx.save_profile()
        self.editor.fav_btn.setText("★ 已收藏" if checked else "☆ 收藏")

    def _on_batch_restore(self, refs: list) -> None:
        """多选批量还原为原文（删除方案中的这些条目）。"""
        refs = [r for r in (refs or []) if self.ctx.profile.get(r) is not None]
        if not refs:
            info(self, "批量还原", "选中的条目里没有已修改的条目。")
            return
        if not confirm(self, "批量还原为原文",
                       f"将把选中的 {len(refs)} 条修改还原为原文（可从备份或历史找回）。",
                       ok_label="还原"):
            return
        for ref in refs:
            self.ctx.remove_entry(ref)
        self.ctx.save_profile()
        if self._current_hit is not None and any(self._current_hit.ref.key() == r.key() for r in refs):
            self._on_hit_activated(HitView(hit=self._current_hit))
        self.refresh_topbar()
        self.refresh_list()
        info(self, "已批量还原", f"已还原 {len(refs)} 条修改。", "记录可在「修改历史」里查看。")

    def _on_batch_favorite(self, refs: list, favorite: bool) -> None:
        """多选批量收藏/取消收藏（仅对已修改条目生效）。"""
        entries = [self.ctx.profile.get(r) for r in (refs or [])]
        entries = [e for e in entries if e is not None]
        if not entries:
            info(self, "批量收藏", "选中的条目里没有已修改的条目（收藏仅适用于已修改条目）。")
            return
        for entry in entries:
            entry.favorite = bool(favorite)
        self.ctx.save_profile()
        if self._current_hit is not None:
            entry = self.ctx.profile.get(self._current_hit.ref)
            now_fav = bool(entry and entry.favorite)
            self.editor.fav_btn.setChecked(now_fav)
            self.editor.fav_btn.setText("★ 已收藏" if now_fav else "☆ 收藏")
        self.refresh_list()
        verb = "加入收藏" if favorite else "取消收藏"
        info(self, "已批量收藏" if favorite else "已批量取消收藏",
             f"{verb} {len(entries)} 条。", "在左侧「我的收藏」里可以只看这些条目。")

    def _on_history(self, ref) -> None:
        entries = self.ctx.history.get(ref.key())
        if not entries:
            info(self, "修改历史", "该条目暂无历史记录。", "修改并保存后会自动记录。")
            return

        def restore(value: str) -> None:
            self.editor.custom_edit.setPlainText(value)

        dlg = HistoryDialog(self, ref.key(), entries, "", restore)
        safe_exec(dlg)

    def _refresh_editor_state(self) -> None:
        if self._current_hit is None:
            return
        entry = self.ctx.profile.get(self._current_hit.ref)
        self.editor.fav_btn.setChecked(bool(entry and entry.favorite))
        self.editor.fav_btn.setText("★ 已收藏" if entry and entry.favorite else "☆ 收藏")

    # ---------- 应用 / 清空 / 停用 ----------

    def manage_supplement(self) -> None:
        """补译文件管理（零协包里没有的文件）。"""
        before = self.ctx.supplement.enabled_map()
        open_supplement_dialog(self, self.ctx)
        after = self.ctx.supplement.enabled_map()
        if before != after:
            self.refresh_topbar()
            self.refresh_list()
        self.refresh_topbar()

    def batch_replace(self, whole: bool = False) -> None:
        """一键替换：默认只在当前列表筛选结果里替换，``whole=True`` 时按全库。"""
        views = [v for v in self.list_panel.model.hits() if not v.is_header]
        hits = None if (whole or not views) else [v.hit for v in views]
        label = "全库文本" if hits is None else f"当前列表（{len(hits)} 条）"
        if hits is not None:
            label += "　（同一文本重复出现的位置只显示一条，要全覆盖请用「一键替换（全部文本）」）"
        if open_replace_dialog(self, self.ctx, scope_label=label, hits=hits):
            self.refresh_topbar()
            self.refresh_list()
            self._refresh_editor_state()

    def apply_patch(self) -> None:
        if not self.ctx.env.llc_ok:
            # 副本包是从零协包镜像出来的；没有零协就只能浏览/翻译，不能写回游戏
            open_llc_toolbox(self, "无法应用到游戏", self.ctx.env.text_source == "en")
            return
        if self.ctx.profile.count() == 0:
            info(self, "应用补丁", "当前方案没有修改。", "先在右侧编辑并保存一条文本。")
            return
        if self.ctx.profile_dirty:
            self.ctx.save_profile()

        def task(progress):
            return self.ctx.apply(progress)

        def done(report) -> None:
            self.refresh_topbar()
            if report.ok:
                info(self, "应用成功", f"补丁已应用到游戏（{report.files_written} 个文件已更新）。",
                     "进入游戏后在左下角语言选择中确认已选中副本语言包（默认 LLC_zh-CN_custom）。")
            else:
                error(self, "应用失败", "部分文件写入失败：" + "；".join(report.errors[:3]),
                      "点击「重试」再次应用；原零协文件不受影响。")

        self._run_with_progress(task, "正在应用到游戏…", done)

    def clear_all(self) -> None:
        if self.ctx.profile.count() == 0:
            info(self, "清空", "当前没有修改。")
            return
        if not confirm(self, "清空全部修改", f"将删除全部 {self.ctx.profile.count()} 条修改，并把副本包恢复为与零协一致。此操作可通过备份恢复。", ok_label="清空"):
            return

        def task(progress):
            return self.ctx.clear_all(progress)

        def done(report) -> None:
            self.refresh_topbar()
            self.refresh_list()
            if report.ok:
                info(self, "已清空", "全部修改已清除，副本包已与零协一致。")
            else:
                error(self, "清空失败", "；".join(report.errors[:3]), "重试或从备份恢复。")

        self._run_with_progress(task, "正在清空…", done)

    def disable_patch(self) -> None:
        if not confirm(self, "停用修改", "游戏将恢复使用零协原版语言包（副本包数据保留，可随时重新应用）。", ok_label="停用"):
            return
        self.ctx.disable()
        self.refresh_topbar()
        info(self, "已停用", "已切换回零协原版语言包。", "点击「应用到游戏」可再次启用。")

    # ---------- 备份 ----------

    # ---------- 方案导入导出 ----------

    def export_profile_pack(self) -> None:
        """操作菜单：把当前方案（+ 剧本对应）导出成便携 zip。"""
        from ..portable import PortableError, export_pack

        default = str(Path.home() / f"边狱修改器方案_{datetime.now():%Y%m%d}.zip")
        path, _f = QFileDialog.getSaveFileName(self, "导出方案包", default, "方案包 (*.zip)")
        if not path:
            return
        with_backups = confirm(self, "导出方案包",
                               "是否一并打包最近的备份文件（最多 5 个）？\n"
                               "不打包更小，打包便于在新机器上直接恢复。",
                               ok_label="包含备份", danger=False)
        try:
            res = export_pack(Path(path), self.ctx.profile, self.ctx.story_edit.overrides(),
                              self.ctx.app_paths.backups_dir, with_backups=with_backups)
        except PortableError as exc:
            error(self, "导出失败", str(exc), "换个位置再试；方案数据未受影响。")
            return
        info(self, "导出完成",
             f"已导出到：{res.path}\n修改 {res.entries} 条 · 剧本对应 {res.story_rules} 条"
             + (f" · 备份 {res.backups} 个" if res.backups else ""),
             "在新机器上把 exe 与 data/ 放好后，用「导入方案包」即可恢复。")

    def import_profile_pack(self) -> None:
        """操作菜单：导入便携 zip（合并剧本对应，覆盖同名方案前留 .bak）。"""
        from ..portable import PortableError, import_pack, peek_pack

        path, _f = QFileDialog.getOpenFileName(self, "导入方案包", str(Path.home()), "方案包 (*.zip)")
        if not path:
            return
        try:
            manifest = peek_pack(Path(path))
        except PortableError as exc:
            error(self, "无法导入", str(exc), "请选择本工具导出的 *.zip 方案包。")
            return
        detail = (f"方案：{manifest.get('profile_name')}\n"
                  f"修改条目：{manifest.get('entries')} 条\n"
                  f"剧本对应：{manifest.get('story_rules')} 条\n"
                  f"导出时间：{manifest.get('exported_at')}")
        if not confirm(self, "导入方案包", detail + "\n\n将写入 data/（同名方案先备份为 .bak）。",
                       ok_label="导入"):
            return
        try:
            res = import_pack(Path(path), self.ctx.app_paths.profiles_dir,
                              self.ctx.app_paths.cache_dir, self.ctx.app_paths.backups_dir,
                              target=self.ctx.profile_path)
        except PortableError as exc:
            error(self, "导入失败", str(exc), "原有方案与游戏文件都未被修改。")
            return
        # 重新载入方案与剧本数据
        self.ctx.load_profile()
        self.ctx.story_edit.rebuild()
        self.ctx.storybook.reload()
        self.refresh_topbar()
        self.refresh_list()
        if self._script_active:
            cid, code = self._script_loc()
            if cid and code:
                self._reload_script_panel(cid, code)
        note = ("；".join(res.notes) + "。") if res.notes else ""
        info(self, "导入完成",
             f"方案「{res.profile_name}」：{res.entries} 条修改 · 剧本对应 {res.story_rules} 条。"
             + (f"\n备份 {res.backups} 个已放入 data/backups。" if res.backups else ""),
             note + "如需让游戏生效，请点「应用到游戏」。")


    def show_baseline_status(self) -> None:
        """操作菜单：显示英文基线的目录、覆盖情况与切换方式（只读参考）。"""
        from ..baseline import baseline_langs

        env = self.ctx.env
        if not env.game_dir_ok:
            info(self, "英文基线", "尚未选择游戏目录。", "先设置游戏目录并建立索引。")
            return
        paths = self.ctx.game_paths
        base = self.ctx.baseline_dir
        if base is None:
            warn(self, "英文基线",
                 f"未找到英文基线目录：{paths.baseline_dir(self.ctx.config.baseline_lang)}",
                 "该目录由游戏本体提供（Assets/Resources_moved/Localize/en）。找不到时编辑器不显示英文，其余功能不受影响。")
            return
        hits, total = self.ctx.search.baseline_stats()
        langs = "、".join(baseline_langs(paths.base_localize_dir)) or "（无）"
        pct = f"{hits * 100 // total}%" if total else "—"
        info(self, "英文基线",
             f"目录：{base}\n文件：{env.base_file_count} 个\n"
             f"文本对照：{hits}/{total}（{pct}）\n可选语言目录：{langs}",
             "编辑器里勾选「英语原文」或按 Ctrl+E 并排显示；搜索范围可切到「英文」。")

    def make_backup(self) -> None:
        path = self.ctx.backup.backup("manual")
        if path:
            info(self, "备份完成", f"已创建备份：{path.name}")
        else:
            error(self, "备份失败", "无法创建备份文件。", "检查磁盘空间与 data/backups 目录权限。")

    def open_backups(self) -> None:
        def restore(path: Path) -> None:
            try:
                names = self.ctx.backup.restore(path)
            except Exception as e:  # noqa: BLE001
                error(self, "恢复失败", str(e), "重新选择其他备份。")
                return
            self.ctx.load_profile()
            self.ctx.config = self.ctx.config_store.load()
            self.ctx.refresh_env()
            self.refresh_topbar()
            self.refresh_list()
            info(self, "恢复完成", "已恢复：" + "、".join(names), "检查顶部状态，必要时重新「应用到游戏」。")

        dlg = BackupDialog(self, self.ctx.backup.list(), restore, self.ctx.app_paths.data_dir)
        safe_exec(dlg)

    # ---------- 其他 ----------

    def _on_advanced(self, checked: bool) -> None:
        self.ctx.config.advanced_mode = checked
        self.ctx.config_store.save(self.ctx.config)
        if self._current_hit is not None:
            self._on_hit_activated(HitView(hit=self._current_hit))

    def _about(self) -> None:
        info(
            self,
            "关于",
            f"边狱巴士汉化文本修改器 v{__version__}\n\n"
            "· 文本只读自你本机的语言文件（零协汉化；没装则用游戏英文原文）\n"
            "· 仅写入独立的副本语言包，不修改零协原始汉化与游戏英文基线\n"
            "· 修改保存在应用 data/ 目录，可随文件夹迁移\n"
            "· 汉化更新后自动检查兼容性，不会删除你的修改\n"
            "· 人格/E.G.O 卡面来源：灰机 wiki（huijiwiki.com）\n"
            "· 发布包内不含任何译文与游戏素材\n\n"
            "本工具与 Project Moon、零协会汉化组均无隶属关系；仅供个人汉化对照使用。\n"
            "第三方组件许可见发布包内 THIRD_PARTY_LICENSES.md。",
        )

    def _usage(self) -> None:
        info(
            self,
            "使用说明",
            "1. 首次运行：选择游戏目录（自动扫描 Steam 库 或 手动选择）\n"
            "2. 等待文本索引建立（仅首次，之后秒开）\n"
            "3. 左侧导航：罪人 → 人格/E.G.O；或按剧情章节/活动浏览\n"
            "4. 顶部搜索：支持中文原文、自定义文本、KeyID（如 2010611）\n"
            "5. 单击条目 → 右侧对照零协原文 → 输入自定义文本 → Ctrl+S 保存\n"
            "6. 点「应用到游戏」→ 进入游戏，在左下角语言选择中确认副本语言包\n"
            "7. 零协更新后：顶部出现「N 条待确认」，逐条核对后重新应用\n\n"
            "剧本模式（中间栏）：↑/↓ 移动焦点 · Enter 打开条目或建立对应 · S 标记跳过 · "
            "Ctrl+↑/↓ 跳到上一条/下一条未对齐 · 右键「从该行起批量对应…」一次分配多条\n\n"
            "快捷键：Ctrl+S 保存 · Ctrl+F 搜索 · Esc 清空搜索 · "
            "Ctrl+Shift+D 差异 · Ctrl+Shift+A 高级模式",
        )

    def _on_show_source(self, ref) -> None:
        from ..patch import EntryRef

        if isinstance(ref, EntryRef):
            fp = " / ".join(seg.get("k", f"[{seg.get('i')}]") for seg in ref.field_path)
            from ..patch import ref_label

            info(self, "来源文件", f"文件：{ref.file}\nKeyID：{ref_label(ref)}\n字段路径：{fp}")
        else:
            info(self, "来源文件", f"文件：{ref}")

    def _focus_search(self) -> None:
        self.list_panel.search_edit.setFocus()
        self.list_panel.search_edit.selectAll()

    def _clear_search(self) -> None:
        self.list_panel.search_edit.clear()
        self.list_panel.search_edit.clearFocus()

    @staticmethod
    def _open_dir(path: Path) -> None:
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except OSError:
            pass

    def _run_with_progress(self, task, label: str, on_done) -> None:
        """后台任务 + 模态进度条；任务结束后弹窗**必须自己消失**。

        以前只调 ``dlg.reset()``：worker 线程里晚到的 progress 信号（``setValue`` 会把
        隐藏中的对话框重新 show 出来）会让进度条卡在 100% 不走。这里加了 finished 闸门
        + ``close()``，并把 late 信号直接丢掉。
        """
        dlg = QProgressDialog(label, None, 0, 0, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(150)
        dlg.setCancelButton(None)
        dlg.setAutoClose(True)      # 到 max 自动关（双保险）
        dlg.setAutoReset(True)
        state = {"finished": False}

        def finish() -> None:
            if state["finished"]:
                return
            state["finished"] = True
            dlg.close()
            dlg.deleteLater()

        def on_progress(done: int, total: int) -> None:
            if state["finished"]:  # 任务已经结束：迟到的进度一律忽略
                return
            if dlg.maximum() == 0 and total > 0:
                dlg.setRange(0, total)
            if total > 0:
                dlg.setValue(done)
                dlg.setLabelText(f"{label}（{done}/{total}）")
            else:
                dlg.setLabelText(f"{label}（已处理 {done}）")

        def done(res) -> None:
            finish()
            on_done(res)

        def on_error(msg: str) -> None:
            finish()
            error(self, "操作失败", msg, "检查后重试；数据与备份未受影响。")

        worker = self.runner.run(task, on_done=done, on_error=on_error, on_progress=on_progress)
        self._workers.append(worker)
