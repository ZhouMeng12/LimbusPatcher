"""列表多选批量操作（批量还原 / 批量收藏）测试。"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QAbstractItemView, QApplication

from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppPaths
from limbus_patcher.ui import main_window as mw_mod
from limbus_patcher.ui.main_window import MainWindow
from limbus_patcher.ui.theme import apply_theme

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


def _window(qapp, tmp_path) -> MainWindow:
    game = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", game)
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    win = MainWindow(ctx)
    win.show()
    win._index_ready()
    return win


def _modify_two(win) -> list:
    """把列表前两条改成自定义文本，返回它们的 ref。"""
    win._on_nav_category("all")
    hits = list(win.list_panel.model._hits)
    assert len(hits) >= 2
    refs = []
    for view in hits[:2]:
        res = win.ctx.upsert_entry(view.hit.ref, "批量测试文本")
        assert res.ok, res.message
        refs.append(view.hit.ref)
    win.refresh_list()
    return refs


def test_selection_mode_is_multi(qapp, tmp_path):
    win = _window(qapp, tmp_path)
    try:
        view = win.list_panel.view
        assert view.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
        win._on_nav_category("all")
        model = win.list_panel.model
        assert model.rowCount() >= 2
        sm = view.selectionModel()
        sm.select(model.index(0, 0), QItemSelectionModel.SelectionFlag.Select)
        sm.select(model.index(1, 0), QItemSelectionModel.SelectionFlag.Select)
        sel = win.list_panel.selected_hits()
        assert len(sel) == 2
        # 单条选择只返回一条
        sm.clearSelection()
        sm.select(model.index(3, 0), QItemSelectionModel.SelectionFlag.Select)
        assert len(win.list_panel.selected_hits()) == 1
    finally:
        win.close()


def test_batch_restore_removes_entries(qapp, tmp_path, monkeypatch):
    win = _window(qapp, tmp_path)
    messages: list[tuple] = []
    monkeypatch.setattr(mw_mod, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(mw_mod, "info", lambda *a, **k: messages.append(a))
    try:
        refs = _modify_two(win)
        assert win.ctx.profile.count() == 2
        win._on_batch_restore(refs)
        assert win.ctx.profile.count() == 0
        assert any("已批量还原" in " ".join(str(x) for x in a) for a in messages)
        # 取消确认时不删
        refs2 = _modify_two(win)
        monkeypatch.setattr(mw_mod, "confirm", lambda *a, **k: False)
        win._on_batch_restore(refs2)
        assert win.ctx.profile.count() == 2
        # 没有已修改条目时给出提示且不报错
        win._on_batch_restore([])
    finally:
        win.close()


def test_batch_favorite_toggles_entries(qapp, tmp_path, monkeypatch):
    win = _window(qapp, tmp_path)
    messages: list[tuple] = []
    monkeypatch.setattr(mw_mod, "info", lambda *a, **k: messages.append(a))
    try:
        refs = _modify_two(win)
        win._on_batch_favorite(refs, True)
        assert all(win.ctx.profile.get(r).favorite for r in refs)
        assert any("已批量收藏" in " ".join(str(x) for x in a) for a in messages)
        win._on_batch_favorite(refs, False)
        assert not any(win.ctx.profile.get(r).favorite for r in refs)
        # 未修改条目：只提示，不报错
        win._on_nav_category("all")
        untouched = [v.hit.ref for v in win.list_panel.model._hits if win.ctx.profile.get(v.hit.ref) is None]
        win._on_batch_favorite(untouched[:2], True)
        assert any("批量收藏" in " ".join(str(x) for x in a) for a in messages)
    finally:
        win.close()
