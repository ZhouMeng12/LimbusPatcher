"""人格图鉴（数据层 + 界面）测试。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QTabWidget

from limbus_patcher import codex
from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppPaths
from limbus_patcher.entities import KIND_EGO, KIND_PERSONALITY
from limbus_patcher.ui.codex_page import CodexEditDialog, CodexPage
from limbus_patcher.ui.theme import apply_theme

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


@pytest.fixture
def env(tmp_path) -> tuple[AppContext, Path]:
    game = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", game)
    llc = game / "LimbusCompany_Data/Lang/LLC_zh-CN"
    (llc / "Personalities.json").write_text(json.dumps({"dataList": [
        {"id": 10310, "title": "拉·曼却领\n总督", "name": "堂吉诃德", "desc": "堂吉诃德的第10人格"},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Egos.json").write_text(json.dumps({"dataList": [
        {"id": 20301, "name": "桑丘之血", "desc": "堂吉诃德的专用E.G.O装备"},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Skills_Personality-03.json").write_text(json.dumps({"dataList": [
        {"id": 1031001, "levelList": [
            {"level": 1, "name": "忍耐已经结束", "desc": "",
             "coinlist": [{"coindescs": [{"desc": "硬币一效果"}]}]},
            {"level": 2, "name": "忍耐已经结束", "desc": "等级二说明",
             "coinlist": [{"coindescs": [{"desc": "硬币一效果"}]}, {"coindescs": [{"desc": "硬币二效果"}]}]},
        ]},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Skills.json").write_text(json.dumps({"dataList": [
        {"id": 1010101, "levelList": [{"level": 1, "name": "基础技能", "desc": "基础人格技能说明"}]},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Passives.json").write_text(json.dumps({"dataList": [
        {"id": 1031001, "name": "血之记忆", "desc": "被动说明一"},
        {"id": 1031002, "name": "第二被动", "desc": "被动说明二"},
        {"id": 9999901, "name": "敌人被动", "desc": "不该挂到人格上"},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Passive_Ego.json").write_text(json.dumps({"dataList": [
        {"id": 2030101, "name": "E.G.O 被动", "desc": "EGO 被动说明"},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "StoryData/P10310.json").write_text(json.dumps({"dataList": [
        {"id": 0, "teller": "堂吉诃德", "title": "拉·曼却领", "content": "人格剧情第一行"},
        {"id": 1, "teller": "", "content": "旁白第二行"},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "PersonalityVoiceDlg").mkdir(exist_ok=True)
    (llc / "PersonalityVoiceDlg/Voice_DonQuixote_Bloodfiend_10310.json").write_text(json.dumps({"dataList": [
        {"id": "get_10310_1", "desc": "获得人格", "dlg": "获得台词"},
        {"id": "battle_win_10310_1", "desc": "战斗胜利", "dlg": "胜利台词"},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "EGOVoiceDig").mkdir(exist_ok=True)
    (llc / "EGOVoiceDig/Voice_EGO_DonQuixote_3.json").write_text(json.dumps({"dataList": [
        {"id": "battle_awaken_20301_1", "desc": "E.G.O觉醒", "dlg": "觉醒台词"},
        {"id": "battle_awaken_20302_1", "desc": "E.G.O觉醒", "dlg": "别的 EGO"},
    ]}, ensure_ascii=False), encoding="utf-8")
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    return ctx, llc


def test_build_entity_personality(env):
    ctx, llc = env
    ent = codex.build_entity(llc, ctx.search.entity_summary("P:10310"))
    assert ent.name == "堂吉诃德" and ent.ordinal == "第10人格"
    assert ent.title.replace("\n", "") == "拉·曼却领总督"      # title 原样保留换行，界面自行处理
    # 技能：名字取 levelList 的 name，等级与硬币都在，且带可编辑字段路径
    assert len(ent.skills) == 1
    skill = ent.skills[0]
    assert skill.label == "忍耐已经结束" and len(skill.levels) == 2
    assert skill.levels[1].desc == "等级二说明" and skill.levels[1].desc_fp
    assert [c[0] for c in skill.levels[1].coins] == ["硬币一效果", "硬币二效果"]
    assert skill.levels[1].coins[0][1]                        # 硬币也有字段路径
    # 剧情 / 语音
    assert [l.text for l in ent.story_lines] == ["人格剧情第一行", "旁白第二行"]
    assert [(v.category, v.text) for v in ent.voices] == [("获得人格", "获得台词"), ("战斗胜利", "胜利台词")]
    assert ent.voice_groups()[0][0] == "获得人格"             # 常用类别排前面
    assert ent.ordinal and ent.kind == KIND_PERSONALITY


def test_build_entity_ego_filters_voice_by_id(env):
    ctx, llc = env
    ent = codex.build_entity(llc, ctx.search.entity_summary("E:20301"))
    assert ent.kind == KIND_EGO and ent.ordinal == "专用"
    # EGO 语音按记录 id 里的 EGO id 精确归属（20302 那条不算）
    assert [v.text for v in ent.voices] == ["觉醒台词"]


def test_codex_dialog_edits_and_restores(qapp, env):
    from limbus_patcher.patch import EntryRef

    ctx, llc = env
    ref = EntryRef(file="StoryData/P10310.json", id=0, record_index=0, field_path=[{"k": "content"}])
    dlg = CodexEditDialog(None, ctx, ref, "剧情第一行")
    assert "人格剧情第一行" in dlg.original_view.toPlainText()
    dlg.custom_edit.setPlainText("改过的第一行")
    dlg._save()
    assert ctx.profile.get(ref) is not None and dlg.saved
    assert ctx.profile.get(ref).value == "改过的第一行"
    dlg2 = CodexEditDialog(None, ctx, ref, "剧情第一行")
    dlg2._restore()
    assert ctx.profile.get(ref) is None                       # 还原为原文 = 从方案移除


def test_card_click_defers_rebuild(qapp, env):
    """回归：点卡片时页面会重建，回调必须延迟触发（否则 C++ 对象已删除崩溃）。"""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    ctx, _llc = env
    page = CodexPage(ctx)
    page.show()
    cards = [w for w in page.findChildren(type(page.findChildren(object)[0])) ]  # 占位，下面用真实类型
    from limbus_patcher.ui.codex_page import _Card

    cards = page.findChildren(_Card)
    assert cards, "罪人页应当有卡片"
    before = page.level
    QTest.mouseClick(cards[0], Qt.MouseButton.LeftButton)
    qapp.processEvents()          # 处理延迟回调
    assert page.level == 2 and page.sinner == "01"
    page.close()


def test_codex_page_navigation(qapp, env):
    ctx, _llc = env
    page = CodexPage(ctx)
    assert page.level == 1 and "选择罪人" in page.crumb.text()
    page._show_entities("03", KIND_PERSONALITY)
    assert page.level == 2 and "堂吉诃德" in page.crumb.text()
    page._show_entity("P:10310")
    assert page.level == 3
    tabs = page.findChildren(QTabWidget)[0]
    assert [tabs.tabText(i) for i in range(tabs.count())] == [
        "技能（1）· 被动（2）", "剧情（2 行）", "语音（2 条）", "战中气泡（0）"]
    # EGO 只做技能 + 语音 + 战中气泡
    page._show_entity("E:20301")
    tabs = page.findChildren(QTabWidget)[0]
    assert [tabs.tabText(i) for i in range(tabs.count())] == [
        "技能（0）· 被动（1）", "语音（1 条）", "战中气泡（0）"]
    # 返回层级
    page._go_back()
    assert page.level == 2
    page._go_back()
    assert page.level == 1


def test_story_and_voice_refs_are_locatable(env):
    """回归：图鉴里点剧情 / 语音必须能定位到记录（缺记录 id 会报「记录定位失败」）。"""
    from limbus_patcher.patch import EntryRef

    ctx, llc = env
    ent = codex.build_entity(llc, ctx.search.entity_summary("P:10310"))

    line = ent.story_lines[0]
    assert line.record_id is not None, "剧情行必须带记录 id"
    ref = EntryRef(file=line.file, id=line.record_id, record_index=line.record_index, field_path=line.fp)
    text, err = ctx.original_of(ref)
    assert err is None and text == line.text

    voice = ent.voices[0]
    assert voice.record_id, "语音必须带记录 id"
    ref2 = EntryRef(file=voice.file, id=voice.record_id, record_index=voice.record_index, field_path=voice.fp)
    text2, err2 = ctx.original_of(ref2)
    assert err2 is None and text2 == voice.text

    # 缺 id 才会失败（证明之前是真 bug）
    bad = EntryRef(file=line.file, id=None, record_index=line.record_index, field_path=line.fp)
    _text, err3 = ctx.original_of(bad)
    assert err3 and "记录定位失败" in err3


def test_battle_bubble_lines_are_clickable(qapp, env):
    """战中气泡台词以前是只读的，点了没反应；现在点卡片要能进编辑（字段 dlg）。"""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QFrame

    from limbus_patcher.bubble_map import BubbleLine

    ctx, _llc = env
    page = CodexPage(ctx)
    page._show_entity("P:10310")
    ent = page.entity
    ent.bubbles = [BubbleLine(file="BattleSpeechBubbleDlg.json", record_index=7,
                              record_id="battle_10808_1", key="battle_10808_1",
                              category="말풍선 특수 대사", text="“我的错”吗……不对，那都是我的功劳。")]
    calls: list[tuple] = []
    page._edit = lambda rel, idx, rid, fp, title: calls.append((rel, idx, rid, fp, title))

    tab = page._bubble_tab(ent)
    card = tab.findChildren(QFrame)[0]
    assert card.cursor().shape() == Qt.CursorShape.PointingHandCursor
    QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    assert calls == [("BattleSpeechBubbleDlg.json", 7, "battle_10808_1", [{"k": "dlg"}],
                      "battle_10808_1")]


def test_flavor_is_parsed_for_skills_and_passives():
    """第 9 章起技能/被动带 flavor（小字），数据层要抓下来并记住字段路径。"""
    from limbus_patcher.codex import _passive_of_record, _skill_of_record

    skill = _skill_of_record({"id": 1031001, "levelList": [
        {"level": 1, "name": "忍耐已经结束", "desc": "等级一说明", "flavor": "风味小字一"},
        {"level": 2, "name": "忍耐已经结束", "desc": "等级二说明", "flavor": "风味小字二"},
    ]}, 0, "Skills_Personality-03.json", divisor=100)
    assert [lv.flavor for lv in skill.levels] == ["风味小字一", "风味小字二"]
    assert skill.levels[0].flavor_fp == [{"k": "levelList"}, {"i": 0, "h": {"level": 1}}, {"k": "flavor"}]

    psv = _passive_of_record({"id": 1031001, "name": "血之记忆", "desc": "被动说明",
                              "flavor": "被动的风味小字"}, 0, "Passives.json", 10310)
    assert psv is not None and psv.flavor == "被动的风味小字"
    assert psv.flavor_fp == [{"k": "flavor"}]
