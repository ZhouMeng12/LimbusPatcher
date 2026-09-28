"""人格 / E.G.O 导航与列表：实体选择器、内容类型、角色徽标。"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppPaths
from limbus_patcher.entities import KIND_EGO, KIND_PERSONALITY
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
    llc = game / "LimbusCompany_Data/Lang/LLC_zh-CN"
    (llc / "Personalities.json").write_text(
        '{"dataList": ['
        '{"id": 10301, "title": "LCB", "name": "堂吉诃德", "desc": "堂吉诃德的第1人格"},'
        '{"id": 10310, "title": "拉·曼却领", "name": "堂吉诃德", "desc": "堂吉诃德的第10人格"}]}',
        encoding="utf-8")
    (llc / "Skills_Personality-03.json").write_text(
        '{"dataList": [{"id": 1031001, "levelList": [{"level": 1, "name": "穿刺", "desc": "技能一"}]}]}',
        encoding="utf-8")
    (llc / "StoryData/P10310.json").write_text(
        '{"dataList": [{"id": 0, "teller": "堂吉诃德", "content": "人格剧情正文"}]}', encoding="utf-8")
    (llc / "PersonalityVoiceDlg").mkdir(exist_ok=True)
    (llc / "PersonalityVoiceDlg/Voice_DonQuixote_Bloodfiend_10310.json").write_text(
        '{"dataList": [{"id": 0, "content": "语音一"}]}', encoding="utf-8")

    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    w = MainWindow(ctx)
    w.show()
    w._index_ready()
    yield w
    w.close()


def nav_keys(win: MainWindow) -> set[str]:
    keys = set()

    def walk(item):
        for i in range(item.childCount()):
            child = item.child(i)
            data = child.data(0, Qt.ItemDataRole.UserRole)
            if data:
                keys.add(data)
            walk(child)

    for i in range(win.nav.tree.topLevelItemCount()):
        walk(win.nav.tree.topLevelItem(i))
    return keys


def test_nav_has_codex_and_script_entries(win):
    """导航改版后的契约（见 DESIGN_SYSTEM.md §5）。

    改动点：
    * 「剧本模式」仍在导航里（剧院分区第一项）；
    * 「人格图鉴 / 敌方图鉴」**移出导航**，由顶栏按钮独占入口 —— 两处都能进属于
      等价重复入口，与「主行动唯一」原则冲突；
    * 人格技能 / 人格语音 / E.G.O 技能 / E.G.O 语音 / 人格一览 / E.G.O 一览
      重新回到导航（放进「人格」「E.G.O」两个分区）—— 与游戏原版
      「人格 / E.G.O 菜单 → 角色 → 技能·剧情·语音」的结构一致。
    """
    keys = nav_keys(win)
    assert "script" in keys
    # 图鉴不在导航里，但顶栏有独占入口
    assert "codex" not in keys and "enemy_codex" not in keys
    assert win.codex_btn_top.text() == "人格图鉴"
    assert win.enemy_btn_top.text() == "敌方图鉴"
    # 角色聚合入口重新可达
    assert {"role:identity_skill", "role:identity_voice", "entities:personality",
            "role:ego_skill", "role:ego_voice", "entities:ego"} <= keys
    # 走一遍确认真的能切过去（不是只挂了个空节点）
    win._on_nav_category("role:ego_voice")
    assert win._category == "role:ego_voice"
    win._on_nav_category("entities:ego")
    assert win._category == "entities:ego"


def test_nav_codex_entries_open_topbar_pages(win):
    """图鉴入口虽然移出导航，但 _on_nav_category 的兼容分支仍要能打开页面。"""
    win._on_nav_category("codex")
    assert win.center_stack.currentWidget() is win.codex_page
    win._on_nav_category("enemy_codex")
    assert win.center_stack.currentWidget() is win.enemy_codex_page


def test_entity_overview_shows_combo_and_counts(win):
    win._on_nav_category("entities:personality")
    assert win.list_panel.entity_combo.isVisible()
    keys = [win.list_panel.entity_combo.itemData(i) for i in range(win.list_panel.entity_combo.count())]
    assert keys == ["", "P:10301", "P:10310"]       # 第一项「全部」，其后按罪人 + 序号
    assert "第1" in win.list_panel.entity_combo.itemText(1)
    assert "全部人格" in win.list_panel.entity_combo.itemText(0)
    hits = win.list_panel.model._hits
    assert hits and all(h.role_label for h in hits)  # 行内带「技能 N · 剧情 N · 语音 N」提示
    labels = " ".join(h.role_label for h in hits)
    assert "技能 1" in labels and "剧情 1" in labels and "语音 1" in labels


def test_entity_content_filter(win):
    win._on_nav_category("entities:personality")
    win.list_panel.set_entity_context(
        win.ctx.search.list_entities(KIND_PERSONALITY), [("all", "全部"), ("identity_skill", "技能"),
                                                         ("identity_story", "剧情"), ("identity_voice", "语音")],
        "P:10310", "identity_skill")
    win.refresh_list()
    hits = win.list_panel.model._hits
    assert hits and all(h.hit.role == "identity_skill" for h in hits)
    assert hits[0].role_label == "技能"
    win.list_panel.set_entity_context(
        win.ctx.search.list_entities(KIND_PERSONALITY), [("all", "全部"), ("identity_skill", "技能"),
                                                         ("identity_story", "剧情"), ("identity_voice", "语音")],
        "P:10310", "identity_story")
    win.refresh_list()
    hits = win.list_panel.model._hits
    assert hits and all(h.hit.role == "identity_story" for h in hits)


def test_open_entity_from_overview(win):
    win._on_nav_category("entities:personality")
    win._open_entity("P:10310")
    assert win.list_panel.current_entity() == "P:10310"
    assert win.list_panel.current_content() == "all"
    hits = win.list_panel.model._hits
    assert hits and all(h.hit.entity_key == "P:10310" for h in hits)
    roles = {h.hit.role for h in hits}
    assert {"identity", "identity_skill", "identity_story", "identity_voice"} <= roles


def test_role_shortcut_lists_across_sinners(win):
    win._on_nav_category("role:identity_story")
    hits = win.list_panel.model._hits
    assert hits and all(h.hit.role == "identity_story" for h in hits)
    assert not win.list_panel.entity_combo.isVisible()  # 跨罪人聚合不带实体选择器
    assert hits[0].role_label == "剧情"


def test_sinner_node_gets_entity_combo(win):
    win._on_nav_category("sinner:03:identity")
    assert win.list_panel.entity_combo.isVisible()
    keys = [win.list_panel.entity_combo.itemData(i) for i in range(win.list_panel.entity_combo.count())]
    assert keys == ["", "P:10301", "P:10310"]
    # 该罪人下没有 EGO 实体时，下拉隐藏（不显示空选择器）
    win._on_nav_category("sinner:03:ego")
    assert win.list_panel.entity_combo.count() == 0
    assert not win.list_panel.entity_combo.isVisible()


# ---------- 选择罪人页：照游戏原版的 2 行 × 6 列竖版卡 ----------


def test_sinner_page_is_two_rows_of_six_vertical_cards(win):
    from PySide6.QtWidgets import QGridLayout, QLabel

    from limbus_patcher.entities import SINNER_NAMES
    from limbus_patcher.ui.codex_page import (
        SINNER_CARD_IMG_H,
        SINNER_CARD_W,
        CodexPage,
        _Card,
    )

    page = CodexPage(win.ctx)
    page.resize(1100, 620)
    page._show_sinners()
    cards = page.findChildren(_Card)
    assert len(cards) == len(SINNER_NAMES) == 12
    assert all(c.width() == SINNER_CARD_W and c.height() == SINNER_CARD_IMG_H + 44 for c in cards)

    grid = page.findChild(QGridLayout)
    pos = [grid.getItemPosition(grid.indexOf(c))[:2] for c in cards]
    assert {r for r, _c in pos} == {0, 1}, "应当只有 2 行"
    assert {c for _r, c in pos} == set(range(6)), "每行 6 个"
    assert pos[:6] == [(0, i) for i in range(6)] and pos[6:] == [(1, i) for i in range(6)]

    # 卡上显示罪人名（没有卡面时占位字也是名字首字），不显示等级
    texts = [lbl.text() for lbl in cards[0].findChildren(QLabel) if lbl.text()]
    assert "李箱" in texts, texts
    assert not any("Lv" in t for t in texts)
    page.close()


def test_vertical_pixmap_crops_to_aspect(tmp_path):
    from PySide6.QtGui import QColor, QImage

    from limbus_patcher.ui.codex_page import vertical_pixmap

    img = QImage(640, 360, QImage.Format.Format_ARGB32)
    for x in range(640):                      # 左半红、右半蓝：锚点决定裁到哪一边
        col = QColor("#ff0000") if x < 320 else QColor("#0000ff")
        for y in range(360):
            img.setPixelColor(x, y, col)
    path = tmp_path / "art.png"
    assert img.save(str(path))

    center = vertical_pixmap(path, 168, 224, 0.5)
    left = vertical_pixmap(path, 168, 224, 0.0)
    right = vertical_pixmap(path, 168, 224, 1.0)
    assert (center.width(), center.height()) == (168, 224)
    assert left.toImage().pixelColor(84, 112).name() == "#ff0000"
    assert right.toImage().pixelColor(84, 112).name() == "#0000ff"
    assert vertical_pixmap(None, 168, 224) is None
    assert vertical_pixmap(tmp_path / "没有这个文件.png", 168, 224) is None
