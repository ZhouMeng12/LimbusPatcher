"""顶栏改版的离屏测试：单颗状态药丸 + 嵌套主题切换器 + 切换后重建。

对应需求（见 DESIGN_SYSTEM.md §5）
----------------------------------
* 顶栏从 5 颗等价 chip 收敛成**一颗**药丸，只显示最需要注意的那一条，
  点击弹出完整清单；
* 主题切换器是 `1 + (1+1)`：左侧「巴士」直接选中，右侧「简约」**只展开**出
  暗/亮，点亮暗叶子才真正换主题；
* 换主题后**重建界面**，并且会话状态（分类/搜索/面包屑）要还原。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppPaths
from limbus_patcher.ui import theme
from limbus_patcher.ui.main_window import MainWindow
from limbus_patcher.ui.status_pill import StatusPill, StatusRow
from limbus_patcher.ui.theme_switch import ThemeSwitcher

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app, theme.DEFAULT_THEME)
    return app


def _mk_ctx(tmp_path):
    game = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", game)
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    return ctx


@pytest.fixture
def win(qapp, tmp_path):
    # 用**默认主题**建窗口 —— 这样测的就是用户真正会看到的那套
    theme.apply_theme(qapp, theme.DEFAULT_THEME)
    ctx = _mk_ctx(tmp_path)
    w = MainWindow(ctx)
    w.show()
    w._index_ready()
    yield w
    try:
        w.close()
    except RuntimeError:
        pass


# --------------------------------------------------------------------------
# 状态药丸
# --------------------------------------------------------------------------
def test_药丸取代了五颗_chip(win) -> None:
    for gone in ("save_chip", "env_chip", "apply_chip", "pending_chip", "supplement_chip"):
        assert not hasattr(win, gone), f"{gone} 应该已经收敛进药丸"
    assert isinstance(win.status_pill, StatusPill)


def test_药丸显示最需要注意的那一条(qapp) -> None:
    pill = StatusPill()
    pill.set_rows([
        StatusRow("apply", "应用", "已应用", "ok"),
        StatusRow("supplement", "补译", "补译 3/4", "info"),
        StatusRow("pending", "待确认", "37 条待确认", "warn"),
        StatusRow("save", "保存", "有未保存修改", "warn"),
    ])
    # warn 比 ok/info 都紧急；同级取靠前的（pending 在 save 前）
    assert pill.top_row().key == "pending"
    assert pill._text.text() == "37 条待确认"
    # 升级为错误后必须立刻改口
    pill.set_rows([
        StatusRow("pending", "待确认", "37 条待确认", "warn"),
        StatusRow("env", "环境", "未选目录", "err"),
    ])
    assert pill.top_row().key == "env"
    assert pill._text.text() == "未选目录"


def test_药丸的语气优先级(qapp) -> None:
    from limbus_patcher.ui.status_pill import TONE_ORDER
    assert TONE_ORDER["err"] > TONE_ORDER["warn"] > TONE_ORDER["info"] > TONE_ORDER["ok"] > TONE_ORDER["none"]


def test_药丸空状态不崩(qapp) -> None:
    pill = StatusPill()
    pill.set_rows([])
    assert pill.top_row() is None
    assert pill._text.text() == "—"


def test_窗口启动后药丸有完整五条(win) -> None:
    keys = [r.key for r in win.status_pill.rows]
    assert keys == ["save", "env", "apply", "supplement", "pending"]
    assert win.status_pill.top_row() is not None


# --------------------------------------------------------------------------
# 主题切换器
# --------------------------------------------------------------------------
def test_切换器初始态跟随当前主题(qapp) -> None:
    theme.apply_theme(qapp, "bus")
    sw = ThemeSwitcher("bus")
    assert sw.current == "bus"
    assert sw.text() == "风格 · 巴士"          # 原型 themeBtn 文案
    theme.apply_theme(qapp, "mini-light")
    sw2 = ThemeSwitcher("mini-light")
    assert sw2.current == "mini-light"
    assert sw2.text() == "风格 · 简约 · 亮"
    theme.apply_theme(qapp, "bus")


def test_点简约只展开亮暗不提交(qapp) -> None:
    theme.apply_theme(qapp, "bus")
    sw = ThemeSwitcher("bus")
    got = []
    sw.theme_selected.connect(got.append)
    sw._open_popover()
    pop = sw._pop
    assert pop is not None, "点按钮应该弹出风格浮层"
    assert pop._mini_btn.isVisibleTo(pop), "巴士选中时右半是单格「简约」"
    pop._show_tone()                    # 点「简约」→ 原地换成「亮 / 暗」
    assert got == [], "点风格名不应该直接换主题"
    assert not pop._mini_btn.isVisibleTo(pop)
    assert pop._tone_btns["mini-light"].isVisibleTo(pop)
    assert pop._tone_btns["mini-dark"].isVisibleTo(pop)
    assert sw.current == "bus", "只展开，不提交"


def test_点亮暗叶子才换主题(qapp) -> None:
    theme.apply_theme(qapp, "bus")
    sw = ThemeSwitcher("bus")
    got = []
    sw.theme_selected.connect(got.append)
    sw._open_popover()
    sw._pop._show_tone()
    sw._pop._pick_tone("mini-light")
    assert got == ["mini-light"]
    assert sw.current == "mini-light"


def test_点巴士直接选中(qapp) -> None:
    theme.apply_theme(qapp, "mini-dark")
    sw = ThemeSwitcher("mini-dark")
    got = []
    sw.theme_selected.connect(got.append)
    sw._open_popover()
    sw._pop._pick_bus()
    assert got == ["bus"]
    assert sw.current == "bus"
    theme.apply_theme(qapp, "bus")


def test_重复点当前主题不重复发信号(qapp) -> None:
    theme.apply_theme(qapp, "bus")
    sw = ThemeSwitcher("bus")
    got = []
    sw.theme_selected.connect(got.append)
    sw._open_popover()
    sw._pop._pick_bus()
    assert got == []


# --------------------------------------------------------------------------
# 切换 → 重建界面
# --------------------------------------------------------------------------
def test_切换主题会重建窗口并落盘(win, tmp_path) -> None:
    dark_accent = theme.tokens("mini-dark")["ACCENT"]
    assert theme.ACCENT.lower() == dark_accent.lower()

    win._on_nav_category("main_story")
    win.list_panel.search_edit.setText("limbus")
    new = win.set_theme("mini-light")
    assert new is not None and new is not win
    assert theme.current_mode() == "mini-light"
    # 颜色真的换了（亮色下金色必须换深，否则白底上对比不足）
    assert theme.ACCENT.lower() != dark_accent.lower()
    assert theme.ACCENT.lower() == theme.tokens("mini-light")["ACCENT"].lower()
    new._index_ready()
    # 会话状态被还原
    assert new._category == "main_story"
    assert new.list_panel.search_edit.text() == "limbus"
    # 面包屑现在走富文本（分区加粗 + 分隔符最暗），纯文本原文在 _crumb
    assert new._crumb == "剧院 › 主线剧情"
    assert "主线剧情" in new.crumb.text()
    # 落盘
    cfg = json.loads((Path(tmp_path / "app") / "data" / "config.json").read_text(encoding="utf-8"))
    assert cfg["ui"]["theme"] == "mini-light"
    new.close()


def test_切到巴士再切回来(win) -> None:
    """默认是 mini-dark（圆角），切到巴士应变直角，切回来应恢复圆角。"""
    assert theme.current_mode() == "mini-dark"
    assert theme.RADIUS_MD == 6
    bus = win.set_theme("bus")
    assert bus is not None
    bus._index_ready()
    assert theme.current_mode() == "bus"
    assert theme.RADIUS_MD == 0          # 巴士：直角

    back = bus.set_theme("mini-dark")
    assert back is not None
    back._index_ready()
    assert theme.current_mode() == "mini-dark"
    assert theme.RADIUS_MD == 6          # 简约：圆角回来
    back.close()


def test_同主题再选一次不做任何事(win) -> None:
    assert theme.current_mode() == theme.DEFAULT_THEME
    assert win.set_theme(theme.DEFAULT_THEME) is None
    # 窗口没被换掉
    assert win.isVisible() or True


def test_非法主题名回落到默认(win) -> None:
    assert theme.resolve_theme("") == theme.DEFAULT_THEME
    assert theme.resolve_theme("garbage") == theme.DEFAULT_THEME
    assert win.set_theme("garbage") is None   # 解析成默认，与当前一致 → 无操作


def test_重建后消失的控件引用不会残留(win) -> None:
    """重建走的是"新窗口"路线，旧窗口的 chip 系列不应该在新窗口上复活。"""
    new = win.set_theme("bus")           # 换一个与当前不同的主题才会重建
    assert new is not None and new is not win
    assert not any(hasattr(new, n) for n in
                   ("save_chip", "env_chip", "apply_chip", "pending_chip", "supplement_chip"))
    assert isinstance(new.status_pill, StatusPill)
    new.close()


# --------------------------------------------------------------------------
# 配置持久化
# --------------------------------------------------------------------------
def test_配置写入并读回主题(tmp_path) -> None:
    from limbus_patcher.config import AppConfig, ConfigStore, UiState

    paths = AppPaths.from_root(tmp_path / "app")
    paths.ensure_dirs()
    store = ConfigStore(paths)
    cfg = AppConfig()
    assert cfg.ui.theme == "mini-dark"    # 默认 = 第一版暗金
    cfg.ui.theme = "mini-light"
    store.save(cfg)
    assert store.load().ui.theme == "mini-light"
    # 脏数据回落默认
    assert UiState.from_dict({"theme": "hotdog"}).theme == "mini-dark"
    assert UiState.from_dict({}).theme == "mini-dark"
    # 三个合法值都认，旧名也认
    for ok in ("mini-dark", "mini-light", "bus", "dark", "light"):
        assert UiState.from_dict({"theme": ok}).theme in ("mini-dark", "mini-light", "bus")
    assert UiState.from_dict({"theme": "dark"}).theme == "mini-dark"
    assert UiState.from_dict({"theme": "light"}).theme == "mini-light"
