"""会话记忆（窗口/分栏/分类/筛选/上次条目/剧本位置）测试。"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppConfig, AppPaths, ConfigStore, UiState
from limbus_patcher.ui.main_window import MainWindow
from limbus_patcher.ui.theme import apply_theme

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


def test_ui_state_roundtrip_and_defaults():
    state = UiState(category="identity", search="但丁", chapter="c1", level="1-01",
                    script_active=True, script_chapter="c1", script_stage="1-01",
                    script_show_deleted=True, script_unaligned_only=True,
                    geometry="QUJD", splitter="REVG")
    again = UiState.from_dict(state.to_dict())
    assert again == state
    # 缺省/脏数据不炸，并且分类回落到 all
    empty = UiState.from_dict(None)
    assert empty.category == "all" and empty.search == "" and empty.script_active is False
    dirty = UiState.from_dict({"category": "", "search": 5, "script_active": "yes", "unknown": 1})
    assert dirty.category == "all" and dirty.search == "" and dirty.script_active is True


def test_config_store_persists_ui_state(tmp_path):
    paths = AppPaths.from_root(tmp_path)
    paths.ensure_dirs()
    store = ConfigStore(paths)
    cfg = AppConfig(game_dir="D:/game")
    cfg.ui.category = "enemy"
    cfg.ui.search = "镜牢"
    store.save(cfg)
    loaded = store.load()
    assert loaded.ui.category == "enemy" and loaded.ui.search == "镜牢"
    assert loaded.game_dir == "D:/game"
    # 老版本 config.json（没有 ui 段）也能读
    paths.config_path.write_text('{"format_version": 1, "game_dir": "X"}', encoding="utf-8")
    assert store.load().ui.category == "all"


def _make_window(qapp, tmp_path) -> MainWindow:
    game = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", game)
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    win = MainWindow(ctx)
    win.show()
    win._index_ready()
    return win


def test_window_captures_and_restores_session(qapp, tmp_path):
    win = _make_window(qapp, tmp_path)
    try:
        # 制造一份「上次的样子」
        win._on_nav_category("dungeon_story")
        win.list_panel.search_edit.setText("但丁")
        hits = win.list_panel.model._hits
        assert hits, "夹具里应当能搜到内容"
        win._on_hit_activated(hits[0])
        opened = win._current_hit.ref.key()
        win._splitter.setSizes([300, 400, 700])
        win._capture_session()
    finally:
        win.close()

    ui = win.ctx.config.ui
    assert ui.category == "dungeon_story" and ui.search == "但丁"
    assert ui.hit_key == opened and ui.splitter and ui.geometry

    # 新窗口：应当恢复分类/搜索/上次条目
    ctx2 = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx2.set_game_dir(str(tmp_path / "game"))
    ctx2.indexer.build(ctx2.game_paths.llc_pack_dir, baseline_dir=ctx2.baseline_dir)
    win2 = MainWindow(ctx2)
    try:
        win2.show()
        win2._index_ready()
        assert win2.list_panel.search_edit.text() == "但丁"
        assert win2._category == "dungeon_story"
        assert win2._current_hit is not None and win2._current_hit.ref.key() == opened
        assert win2.editor.original_edit.toPlainText().strip()
    finally:
        win2.close()


def test_script_position_is_remembered(qapp, tmp_path):
    win = _make_window(qapp, tmp_path)
    try:
        book = win.ctx.storybook
        target = None
        for ch in book.chapter_list():
            for st in book.stages_of(ch["chapter_id"]):
                if st.get("items"):
                    target = (ch["chapter_id"], st["stage_code"])
                    break
            if target:
                break
        if not target:
            pytest.skip("无剧本数据")
        cid, code = target
        win._enter_script_mode(cid, code)
        win.script_panel.unaligned_only_cb.setChecked(True)
        win.script_panel.show_deleted_cb.setChecked(True)
        win._capture_session()
        ui = win.ctx.config.ui
        assert ui.script_active and ui.script_chapter == cid and ui.script_stage == code
        assert ui.script_unaligned_only and ui.script_show_deleted
    finally:
        win.close()

    ctx2 = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx2.set_game_dir(str(tmp_path / "game"))
    ctx2.indexer.build(ctx2.game_paths.llc_pack_dir, baseline_dir=ctx2.baseline_dir)
    win2 = MainWindow(ctx2)
    try:
        win2.show()
        win2._index_ready()
        assert win2._script_active and (win2._script_cid, win2._script_code) == (cid, code)
        assert win2.script_panel.unaligned_only_cb.isChecked()
        assert win2.script_panel.show_deleted_cb.isChecked()
    finally:
        win2.close()
