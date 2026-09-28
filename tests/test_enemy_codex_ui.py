"""敌方图鉴二级列表：分组过滤 + 分批渲染（点开分组不再卡）。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppPaths
from limbus_patcher.ui.enemy_codex_page import ENTITY_CHUNK, EnemyCodexPage
from limbus_patcher.ui.theme import apply_theme

FIXTURES = Path(__file__).resolve().parent / "fixtures"

TOTAL = 200
UNIT_IDS = list(range(91000, 91000 + TOTAL))
OTHER_IDS = [92000, 92001]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


@pytest.fixture
def page(qapp, tmp_path):
    game = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", game)
    llc = game / "LimbusCompany_Data/Lang/LLC_zh-CN"
    cache = tmp_path / "app" / "data" / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    entries = [{"id": i, "name": f"测试敌人{i}"} for i in UNIT_IDS + OTHER_IDS]
    # 91000 / 91001：同名同描述且 id 连续 → 视为同一敌人的两个形态（像 9-50 里恩 1347/1348）
    for i in (91000, 91001):
        entries = [e for e in entries if e["id"] != i]
    entries = [{"id": 91000, "name": "测试里恩", "desc": "测试父辈"},
               {"id": 91001, "name": "测试里恩", "desc": "测试父辈"}] + entries
    (llc / "Enemies.json").write_text(
        json.dumps({"dataList": entries}, ensure_ascii=False), encoding="utf-8")
    (llc / "Skills_Enemy-test.json").write_text(json.dumps({"dataList": [
        {"id": 9100001, "levelList": [{"level": 1, "name": "测试技能", "desc": "效果说明",
                                       "flavor": "这是风味小字。",
                                       "coinlist": [{"coindescs": [{"desc": "硬币效果"}]}]}]},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Passives_Enemy-test.json").write_text(json.dumps({"dataList": [
        {"id": 9100002, "name": "测试被动", "desc": "被动说明", "flavor": "被动的风味小字。"},
    ]}, ensure_ascii=False), encoding="utf-8")
    enemy_map = {"enemies": {}}
    for i in UNIT_IDS:
        enemy_map["enemies"][str(i)] = {"group": "unit", "dimensions": {"danger_level": "1"}}
    for i in OTHER_IDS:
        enemy_map["enemies"][str(i)] = {"group": "abnormality", "dimensions": {"danger_level": "2"}}
    (cache / "enemy_map.json").write_text(
        json.dumps(enemy_map, ensure_ascii=False), encoding="utf-8")

    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    ctx.maps.reload()
    p = EnemyCodexPage(ctx)
    p.resize(1000, 700)
    yield p
    p.close()


def cards_of(page: EnemyCodexPage) -> int:
    grid = getattr(page, "_entity_grid", None)
    return 0 if grid is None else grid.count()


def test_group_list_is_filtered_and_paged(page: EnemyCodexPage):
    page._show_entities("unit")
    # 分组过滤：unit 组应当只有 TOTAL 条（以前读错字段 → 每个分组都列出全部敌人）
    assert len(page._entity_specs) == TOTAL
    # 分批：先建一批，其余按需
    assert cards_of(page) == ENTITY_CHUNK
    assert page.remaining_entities() == TOTAL - ENTITY_CHUNK
    page._load_more_entities()
    assert cards_of(page) == ENTITY_CHUNK * 2
    assert page.remaining_entities() == TOTAL - ENTITY_CHUNK * 2


def test_other_group_only_has_its_own(page: EnemyCodexPage):
    page._show_entities("abnormality")
    assert len(page._entity_specs) == len(OTHER_IDS)
    assert page.remaining_entities() == 0
    assert cards_of(page) == len(OTHER_IDS)


def test_loading_to_the_end_stops(page: EnemyCodexPage):
    page._show_entities("unit")
    while page.remaining_entities() > 0:
        assert page._load_more_entities() > 0
    assert cards_of(page) == TOTAL
    assert page._load_more_entities() == 0


def test_phase_variants_only_group_consecutive_ids(tmp_path):
    """同文件 + 同名同描述 + id 连续才算同一敌人的多形态。"""
    from limbus_patcher.enemy_codex import phase_variants

    d = tmp_path / "pack"
    d.mkdir()
    (d / "Enemies-test.json").write_text(json.dumps({"dataList": [
        {"id": 1347, "name": "里恩", "desc": "父辈"},
        {"id": 1348, "name": "里恩", "desc": "父辈"},
        {"id": 134701, "name": "躯干", "desc": "部位"},          # 部位不算形态
        {"id": 90004, "name": "流氓", "desc": "敌方单位"},         # 跨难度同名但 id 不连续
        {"id": 99005, "name": "流氓", "desc": "敌方单位"},
    ]}, ensure_ascii=False), encoding="utf-8")
    assert [v["id"] for v in phase_variants(d, 1347)] == [1347, 1348]
    assert [v["id"] for v in phase_variants(d, 1348)] == [1347, 1348]
    assert [v["id"] for v in phase_variants(d, 90004)] == [90004]
    assert [v["id"] for v in phase_variants(d, 134701)] == [134701]


def test_detail_page_has_phase_switch(page: EnemyCodexPage):
    """技能/被动页面要能在多个形态之间切换。"""
    from PySide6.QtWidgets import QPushButton

    page._show_entity("N:91000")
    btns = [b for b in page.findChildren(QPushButton) if b.text().startswith("形态")]
    assert [b.text() for b in btns] == ["形态 1 · 91000", "形态 2 · 91001"]
    assert btns[0].isChecked() and not btns[1].isChecked()
    btns[1].click()
    assert page.entity.entity_id == 91001


def test_back_from_entity_returns_to_stage(page: EnemyCodexPage, monkeypatch):
    """从关卡点进敌人详情，「返回」应回到那个关卡，而不是分组实体列表。"""
    from limbus_patcher import stage_enemies as se
    from limbus_patcher.ui.codex_page import _Card

    data = {"chapters": [{"chapter_id": "T", "chapter_label": "第 T 章", "chapter_name": "",
                          "stages": [{"stage_code": "T-01", "stage_name": "测试关",
                                      "enemies": [{"id": 91000}, {"id": 92000}]}]}],
            "dungeons": [], "extra": []}
    monkeypatch.setattr(se, "load_stage_enemies", lambda: data)

    # —— 关卡路径：关卡详情 → 敌人详情 → 返回 → 回到该关卡 ——
    page._show_stage_detail("T-01")
    assert page.level == 4
    cards = page.findChildren(_Card)
    assert len(cards) == 2            # 91000（含 91001 形态，合并一张）+ 92000
    cards[0].clicked.emit()
    assert page.level == 3
    assert page._stage_return == ("stage", "T-01")
    page._go_back()
    assert page.level == 4
    assert "T-01" in page.crumb.text()
    # 返回后重进同一关卡：返回栈不得叠加重复条目（无防重复会变成两条 chapter）
    assert page._stage_stack == [("chapter", "T")]
    page._go_back()                   # 关卡 → 章节（章节页会补 push query）
    assert page.level == 4
    assert page._stage_stack == [("query", None)]
    page._go_back()                   # 章节 → 关卡查询主页
    assert page.level == 4

    # —— 迷宫 / 活动：同样回到来源 ——
    data["dungeons"] = [{"tag": "d1", "label": "测试迷宫", "enemies": [{"id": 91000}]}]
    data["extra"] = [{"tag": "x1", "label": "测试活动", "enemies": [{"id": 91000}]}]
    page._show_stage_dungeon("d1")
    page.findChildren(_Card)[0].clicked.emit()
    assert page._stage_return == ("dungeon", "d1")
    page._go_back()
    assert page.level == 4 and "测试迷宫" in page.crumb.text()
    page._show_stage_extra("x1")
    page.findChildren(_Card)[0].clicked.emit()
    assert page._stage_return == ("extra", "x1")
    page._go_back()
    assert page.level == 4 and "测试活动" in page.crumb.text()

    # —— 普通分组路径不受影响：分组列表 → 详情 → 返回 → 分组列表 ——
    page._show_groups()
    page._show_entities("unit")
    page._show_entity("N:91000")
    assert page.level == 3 and page._stage_return is None
    page._go_back()
    assert page.level == 2


def test_flavor_small_text_is_shown_and_clickable(page: EnemyCodexPage):
    """第 9 章起的风味小字（技能 levelList[].flavor / 被动 flavor）要显示且可点击编辑。"""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLabel

    page._show_entity("N:91000")
    ent = page.entity
    skill_flavors = [lv for s in ent.skills for lv in s.levels if lv.flavor]
    passive_flavors = [p for p in ent.passives if p.flavor]
    assert skill_flavors and skill_flavors[0].flavor == "这是风味小字。"
    assert passive_flavors and passive_flavors[0].flavor == "被动的风味小字。"

    tab = page._skills_tab(ent)
    labels = [l for l in tab.findChildren(QLabel) if "风味小字" in l.text()]
    assert len(labels) == 2  # 技能 + 被动各一条
    calls: list[tuple] = []
    page._edit = lambda rel, idx, rid, fp, title: calls.append((rel, idx, rid, fp, title))
    QTest.mouseClick(labels[0], Qt.MouseButton.LeftButton, pos=QPoint(3, 3))
    assert calls and calls[0][3] == skill_flavors[0].flavor_fp
    calls.clear()
    QTest.mouseClick(labels[1], Qt.MouseButton.LeftButton, pos=QPoint(3, 3))
    assert calls and calls[0][3] == passive_flavors[0].flavor_fp
