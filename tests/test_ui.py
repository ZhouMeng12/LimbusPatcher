"""UI 逻辑的离屏断言：顶部操作菜单、筛选动态显隐、快捷键、空结果引导。"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PySide6.QtGui import QShortcut
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


def test_topbar_ops_menu(win):
    assert win.ops_btn.text() == "操作 ▾"
    texts = [a.text() for a in win.ops_menu.actions() if a.text()]
    assert "清空全部修改" in texts and "立即备份" in texts and "高级模式" in texts
    # 主按钮存在
    assert win.apply_btn.text() == "应用到游戏"


def test_filter_visibility_by_context(win):
    lp = win.list_panel
    win._on_nav_category("sinner:04:identity")
    assert lp.season_combo.isVisible() and not lp.chapter_combo.isVisible() and not lp.kind_combo.isVisible()
    win._on_nav_category("enemy")
    assert lp.kind_combo.isVisible() and not lp.season_combo.isVisible()
    win._on_nav_category("main_story")
    assert lp.chapter_combo.isVisible() and lp.level_combo.isVisible() and not lp.season_combo.isVisible()


def test_shortcuts_registered(win):
    keys = {s.key().toString() for s in win.findChildren(QShortcut)}
    assert {"Ctrl+S", "Ctrl+F", "Esc", "Ctrl+Shift+A", "Ctrl+Shift+D"} <= keys


def test_empty_search_guide(win):
    win.list_panel.search_edit.setText("zzzz不存在")
    win._on_search_requested("zzzz不存在")
    assert "未找到匹配文本" in win.list_panel.count_label.text()


def test_single_click_opens_editor(win):
    win._on_nav_category("all")
    hits = win.list_panel.model._hits
    assert hits
    first = hits[0]
    win._on_hit_activated(first)
    assert win.editor.isEnabled()
    assert win.editor.compare_splitter.isVisible()


def test_keyword_highlight_no_crash(qapp, win):
    win.list_panel.model.set_highlight("群体攻击")
    win._on_nav_category("all")
    assert len(win.list_panel.model._hits) >= 0


def test_delegate_paint_smoke(qapp, win):
    """委托绘制冒烟（含关键词高亮，防 QTextLayout.setFormats 崩溃回归）。"""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QStyleOptionViewItem

    win._on_nav_category("all")
    hits = win.list_panel.model._hits
    if not hits:
        return
    win.list_panel.model.set_highlight("的")
    img = QImage(600, 44, QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    delegate = win.list_panel.view.itemDelegate()
    for row in range(min(5, len(hits))):
        idx = win.list_panel.model.index(row, 0)
        opt = QStyleOptionViewItem()
        opt.rect = win.list_panel.view.visualRect(idx)
        delegate.paint(painter, opt, idx)
    painter.end()
    assert not img.isNull()


# ---------- 差异视图（回归：get_opcodes 5 元组被当成 2 元组解包）----------


def test_diff_html_tags_and_empty():
    from limbus_patcher.ui.editor_panel import _diff_html

    assert _diff_html("", "") == "（无差异）"
    # 完全相同：无高亮
    same = _diff_html("甲\n乙", "甲\n乙")
    assert "span" not in same and same.split("<br/>") == ["甲", "乙"]
    # 修改：旧行带删除线、新行带新增底色
    html = _diff_html("甲\n乙\n丙", "甲\n乙改了\n丙")
    assert "line-through" in html and "#2f4a3f" in html
    assert "乙" in html and "乙改了" in html and "丙" in html
    # 纯新增 / 纯删除（多行、空行、特殊字符）
    add = _diff_html("甲", "甲\n<b>新增</b>\n")
    assert "&lt;b&gt;" in add  # HTML 转义
    deal = _diff_html("甲\n乙\n丙", "甲\n丙")
    assert deal.count("line-through") == 1
    multi = _diff_html("一\n二\n三\n四", "五\n六")
    assert multi.count("line-through") == 4 and multi.count("#2f4a3f") == 2


def test_diff_toggle_checkbox_does_not_crash(win):
    """Ctrl+Shift+D 差异视图开关（真实面板 + 真实条目）。"""
    win._on_nav_category("all")
    hits = win.list_panel.model._hits
    assert hits
    win._on_hit_activated(hits[0])
    ed = win.editor
    assert ed._ref is not None
    original = ed.original_edit.toPlainText()
    ed.custom_edit.setPlainText(original + "（改）")
    ed.diff_btn.setChecked(True)  # 触发 _on_diff_toggle → _diff_html
    assert ed.diff_view.isVisible() and not ed.compare_splitter.isVisible()
    assert "（改）" in ed.diff_view.toPlainText()
    ed.diff_btn.setChecked(False)
    assert not ed.diff_view.isVisible() and ed.compare_splitter.isVisible()


def test_progress_dialog_closes_after_task(win):
    """索引进度弹窗用完必须自己消失（以前会卡在 100% 不走）。"""
    from PySide6.QtWidgets import QApplication, QProgressDialog

    ran = []
    win._run_with_progress(lambda progress: (progress(5, 5), ran.append(True))[1],
                           "测试任务…", lambda _res: ran.append("done"))
    for _ in range(50):
        QApplication.processEvents()
        if "done" in ran:
            break
    assert "done" in ran
    for _ in range(20):
        QApplication.processEvents()
    dialogs = [d for d in win.findChildren(QProgressDialog)]
    assert all(not d.isVisible() for d in dialogs), "任务结束后仍有可见的进度弹窗"


def test_progress_dialog_ignores_late_progress(win):
    """worker 结束后迟到的 setValue 不能把弹窗再弹出来。"""
    from PySide6.QtWidgets import QApplication, QProgressDialog

    box = {}

    def task(progress):
        box["progress"] = progress
        return "ok"

    win._run_with_progress(task, "测试任务…", lambda _res: None)
    for _ in range(50):
        QApplication.processEvents()
    box["progress"](9, 9)          # 迟到的进度回调
    for _ in range(10):
        QApplication.processEvents()
    assert all(not d.isVisible() for d in win.findChildren(QProgressDialog))
