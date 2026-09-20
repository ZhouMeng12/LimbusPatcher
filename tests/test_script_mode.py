"""剧本模式（中间列表切换）UI 冒烟。"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppPaths
from limbus_patcher.ui.main_window import MainWindow
from limbus_patcher.ui.theme import apply_theme

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


@pytest.fixture
def win(qapp, tmp_path):
    game = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", game)
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    w = MainWindow(ctx)
    w.show()
    w._index_ready()
    yield w
    w.close()


def test_script_mode_enter_exit(win):
    book = win.ctx.storybook
    chapters = book.chapter_list()
    # 用真实 v2 数据（开发库内含 story_stages.json）选择一个有剧本数据的关卡
    target = None
    for ch in chapters:
        st = book.stages_of(ch["chapter_id"])
        for s in st:
            if s.get("items"):
                target = (ch["chapter_id"], s["stage_code"], s)
                break
        if target:
            break
    if not target:
        pytest.skip("无剧本数据")
    cid, code, stage = target
    win._enter_script_mode(cid, code)
    assert win._script_active
    # 顶栏与行容器存在
    assert "剧本模式" in win.script_panel.title_label.text()
    assert win.script_panel.vbox.count() > 1
    win._exit_script_mode()
    assert not win._script_active


def test_ruby_parser():
    from limbus_patcher.ui.script_panel import parse_ruby

    segs = parse_ruby("前<ruby=りょう>Ryō</ruby>后")
    assert segs == [("plain", "", "前"), ("ruby", "りょう", "Ryō"), ("plain", "", "后")]
    assert parse_ruby("纯文本") == [("plain", "", "纯文本")]


def test_topbar_entry_and_chapter_switch(win):
    """顶部栏「剧本模式」入口 + 章节切换。"""
    assert win.script_btn_top.text() == "剧本模式"
    win.open_script_mode()
    assert win._script_active
    assert win.script_panel.chapter_combo.count() >= 2
    # 切到另一个章节（取第 2 个条目），应加载该章第一个关卡
    win.script_panel.chapter_combo.setCurrentIndex(1)
    cid = win.script_panel.chapter_combo.currentData()
    assert cid == win._script_cid
    assert win.script_panel.vbox.count() > 1
    win._exit_script_mode()
    assert not win._script_active
