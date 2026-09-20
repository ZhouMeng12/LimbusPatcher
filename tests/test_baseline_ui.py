"""英语原文 UI：编辑器第三栏、Ctrl+E、搜索范围、列表「英文命中」标记。"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from limbus_patcher.app_state import AppContext
from limbus_patcher.baseline import clear_cache
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
    clear_cache()
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    w = MainWindow(ctx)
    w.show()
    w._index_ready()
    yield w
    w.close()
    clear_cache()


def open_first(win: MainWindow, keyword: str = "") -> None:
    win.list_panel.search_edit.setText(keyword)
    win.refresh_list()
    hits = win.list_panel.model._hits
    assert hits, f"没搜到 {keyword!r}"
    win._on_hit_activated(hits[0])


def test_baseline_pane_hidden_by_default_and_toggle(win):
    open_first(win, "群体攻击")
    assert not win.editor.baseline_visible()
    win.editor.set_baseline_visible(True)
    assert win.editor.baseline_visible() and win.editor.baseline_btn.isChecked()
    assert win.editor.baseline_edit.toPlainText() == "Mass Attack"
    assert win.editor.baseline_edit.isReadOnly()
    win.editor.set_baseline_visible(False)
    assert not win.editor.baseline_visible() and not win.editor.baseline_btn.isChecked()


def test_ctrl_e_toggles_baseline(win):
    open_first(win, "群体攻击")
    assert not win.editor.baseline_visible()
    QTest.keyClick(win.editor, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
    assert win.editor.baseline_visible()
    QTest.keyClick(win.editor, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
    assert not win.editor.baseline_visible()


def test_missing_english_shows_reason(win):
    """英文缺字段 / 缺文件时给出中文原因，而不是空白。"""
    open_first(win, "强壮")           # Enhancement：英文只有 desc，没有 name
    note = win.editor.baseline_edit.placeholderText()
    assert "英文" in note and win.editor.baseline_edit.toPlainText() == ""
    open_first(win, "某日的肖像")      # 该文件没有英文基线
    assert "没有英文基线" in win.editor.baseline_edit.placeholderText()


def test_search_scope_baseline_finds_english(win):
    win.list_panel.search_edit.setText("Mass Attack")
    win.list_panel.set_scope("baseline")
    win.refresh_list()
    hits = win.list_panel.model._hits
    assert hits and hits[0].hit.ref.id == "AreaAtk"
    assert hits[0].english_hit is True
    # 切回原文范围：英文词搜不到
    win.list_panel.set_scope("original")
    win.refresh_list()
    assert win.list_panel.model._hits == []


def test_search_scope_custom_finds_modified_text(win):
    """自定义文本以前搜不到，现在可以在「自定义」范围搜到。"""
    win.list_panel.set_scope("original")
    open_first(win, "群体攻击")
    ref = win._current_hit.ref
    res = win.ctx.upsert_entry(ref, "自定义：全体攻击")
    assert res.ok
    win.ctx.save_profile()
    win.list_panel.search_edit.setText("自定义：全体攻击")
    win.list_panel.set_scope("custom")
    win.refresh_list()
    hits = win.list_panel.model._hits
    assert hits and hits[0].hit.ref.key() == ref.key()
    assert hits[0].custom == "自定义：全体攻击"
    assert hits[0].status == "modified"
    # 「全部」范围同时搜得到中英文与自定义
    win.list_panel.set_scope("all")
    win.refresh_list()
    assert win.list_panel.model._hits


def test_session_remembers_baseline_and_scope(qapp, tmp_path):
    game = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", game)
    clear_cache()
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    win = MainWindow(ctx)
    win.show()
    win._index_ready()
    try:
        win.editor.set_baseline_visible(True)
        win.list_panel.set_scope("baseline")
        win._capture_session()
        ui = win.ctx.config.ui
        assert ui.show_baseline is True and ui.search_scope == "baseline"
    finally:
        win.close()

    ctx2 = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx2.set_game_dir(str(game))
    ctx2.indexer.build(ctx2.game_paths.llc_pack_dir, baseline_dir=ctx2.baseline_dir)
    win2 = MainWindow(ctx2)
    try:
        win2.show()
        win2._index_ready()
        assert win2.editor.baseline_visible() is True
        assert win2.list_panel.current_scope() == "baseline"
    finally:
        win2.close()
        clear_cache()


def test_baseline_status_action(win, monkeypatch):
    from limbus_patcher.ui import main_window as mw_mod

    texts: list[tuple] = []
    monkeypatch.setattr(mw_mod, "info", lambda *a, **k: texts.append(a))
    monkeypatch.setattr(mw_mod, "warn", lambda *a, **k: texts.append(a))
    win.show_baseline_status()
    assert texts and "英文基线" in str(texts[0][1])
    body = str(texts[0][2])
    assert "EN_BattleKeywords" not in body  # 只报目录与统计，不刷文件名
    assert "文本对照" in body and "可选语言目录" in body
