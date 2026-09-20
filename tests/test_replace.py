"""一键替换（批量查找替换）+ 被动技能 + 本体名称编辑的测试。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from limbus_patcher import codex
from limbus_patcher import replace as repl
from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppPaths
from limbus_patcher.entities import (
    ROLE_IDENTITY_PASSIVE,
    entity_id_of,
    file_entity,
)
from limbus_patcher.patch import EntryRef
from limbus_patcher.ui.replace_dialog import ReplaceDialog

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def env(tmp_path) -> tuple[AppContext, Path]:
    game = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", game)
    llc = game / "LimbusCompany_Data/Lang/LLC_zh-CN"
    (llc / "Personalities.json").write_text(json.dumps({"dataList": [
        {"id": 10101, "title": "LCB\n罪人", "name": "李箱", "nameWithTitle": "李箱", "desc": "李箱的第1人格"},
        {"id": 10310, "title": "拉·曼却领\n总督", "name": "堂吉诃德", "desc": "堂吉诃德的第10人格"},
    ]}, ensure_ascii=False), encoding="utf-8")
    # 基础人格技能（LCB）在无后缀的 Skills.json 里
    (llc / "Skills.json").write_text(json.dumps({"dataList": [
        {"id": 1010101, "levelList": [{"level": 1, "name": "基础技能", "desc": "基础人格技能说明"}]},
        {"id": 9990001, "levelList": [{"level": 1, "name": "敌人技能", "desc": "不该挂到人格上"}]},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Passives.json").write_text(json.dumps({"dataList": [
        {"id": 1010101, "name": "信息传递", "desc": "被动说明一"},
        {"id": 1031001, "name": "血之记忆", "desc": "被动说明【被动】"},
        {"id": 1031002, "name": "第二被动", "desc": "又一个被动"},
        {"id": 9990001, "name": "敌人被动", "desc": "不该挂到人格上"},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Passive_Ego.json").write_text(json.dumps({"dataList": [
        {"id": 2010101, "name": "E.G.O 被动", "desc": "【被动】的说明"},
    ]}, ensure_ascii=False), encoding="utf-8")
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    return ctx, llc


# ---------- 被动 / 基础人格技能 ----------


def test_skills_json_feeds_base_identity(env):
    """LCB 初始人格的技能在 Skills.json（原实现只认 Skills_Personality-*.json，会显示「没有技能」）。"""
    ctx, llc = env
    ent = codex.build_entity(llc, ctx.search.entity_summary("P:10101"))
    assert [s.name for s in ent.skills] == ["基础技能"]
    assert [p.name for p in ent.passives] == ["信息传递"]


def test_passives_attach_to_identity_and_ego(env):
    ctx, llc = env
    ent = codex.build_entity(llc, ctx.search.entity_summary("P:10310"))
    assert [p.name for p in ent.passives] == ["血之记忆", "第二被动"]
    assert ent.passives[0].file == "Passives.json" and ent.passives[0].desc_fp == [{"k": "desc"}]
    summary = ctx.search.entity_summary("P:10310")
    assert summary["passive_count"] == 2
    ego = codex.build_entity(llc, ctx.search.entity_summary("E:20101"))
    assert [p.name for p in ego.passives] == ["E.G.O 被动"]


def test_passive_ids_outside_range_are_not_attached(env):
    """敌人/异想体被动表里的 6 位 id 不该被当成「人格 id × 100」。"""
    assert file_entity("Passives.json").role == ROLE_IDENTITY_PASSIVE
    assert entity_id_of("Passives.json", {"id": 9990001}) == (None, ROLE_IDENTITY_PASSIVE)
    assert entity_id_of("Passives-BossRaid.json", {"id": 500101}) == (None, ROLE_IDENTITY_PASSIVE)
    assert entity_id_of("Passive_Ego.json", {"id": 2010101})[0] == "E:20101"
    ctx, llc = env
    ent = codex.build_entity(llc, ctx.search.entity_summary("P:10310"))
    assert all("敌人" not in p.name for p in ent.passives)


# ---------- 本体名称（人格名称 / 罪人名 / 简介） ----------


def test_self_texts_are_locatable_and_editable(env):
    ctx, llc = env
    ent = codex.build_entity(llc, ctx.search.entity_summary("P:10310"))
    keys = [t.key for t in ent.self_texts]
    assert keys[0] == "title" and ent.self_text("title").label == "人格名称"
    title = ent.self_text("title")
    ref = EntryRef(file=ent.self_file, id=ent.self_record_id,
                   record_index=ent.self_record_index, field_path=title.fp)
    text, err = ctx.original_of(ref)
    assert err is None and text == "拉·曼却领\n总督"
    assert ctx.upsert_entry(ref, "新名字").ok
    # E.G.O 也一样能改名（Egos 记录的 name 字段）
    ego = codex.build_entity(llc, ctx.search.entity_summary("E:20101"))
    assert ego.self_text("name").label == "E.G.O 名称"
    ref2 = EntryRef(file=ego.self_file, id=ego.self_record_id,
                    record_index=ego.self_record_index, field_path=ego.self_text("name").fp)
    assert ctx.upsert_entry(ref2, "改名后的 E.G.O").ok


def test_entity_name_override_shows_in_codex(qapp, env):
    """方案里改过人格名称后，详情页与卡片列表都要显示新名字（索引是按零协原文建的）。"""
    from limbus_patcher.ui.codex_page import _Card

    ctx, llc = env
    ctx2, _ = env
    ent = codex.build_entity(llc, ctx2.search.entity_summary("P:10101"))
    title = ent.self_text("title")
    ref = EntryRef(file=ent.self_file, id=ent.self_record_id,
                   record_index=ent.self_record_index, field_path=title.fp)
    assert ctx2.upsert_entry(ref, "全知之眼\n罪人").ok
    ctx2.save_profile()

    from limbus_patcher.ui.codex_page import CodexPage

    page = CodexPage(ctx2)
    page._show_entity("P:10101")
    # 详情页页头用的是实体上的 title（覆盖后应当是改过的名字）
    assert "全知之眼" in page._entity_headline(page.entity)
    # 卡片列表（二级页）也要显示新名字
    row = [e for e in ctx2.search.list_entities("personality", "01") if e["entity_key"] == "P:10101"][0]
    assert page._override(row, "title") == "全知之眼\n罪人"
    page._show_entities("01", "personality")
    card_texts = [lbl.text() for card in page.findChildren(_Card) for lbl in card.findChildren(QLabel)]
    assert any("全知之眼" in t for t in card_texts)
    page.close()


# ---------- 替换规则（纯逻辑） ----------


def test_replace_text_variants():
    assert repl.replace_text("李箱的台词", repl.ReplaceRule(find="李箱", repl="箱子")) == ("箱子的台词", 1)
    assert repl.replace_text("A b", repl.ReplaceRule(find="a", repl="c")) == ("A b", 0)
    assert repl.replace_text("A b", repl.ReplaceRule(find="a", repl="c", case_sensitive=False)) == ("c b", 1)
    # 正则 + 反向引用
    got, n = repl.replace_text("abc123", repl.ReplaceRule(find=r"(\d+)", repl=r"[\1]", regex=True))
    assert (got, n) == ("abc[123]", 1)
    # 普通模式下 \1 是字面量，不会当反向引用
    assert repl.replace_text("abc", repl.ReplaceRule(find="b", repl=r"\1"))[0] == r"a\1c"
    # 整段匹配
    assert repl.replace_text("李箱李箱", repl.ReplaceRule(find="李箱", repl="X", whole=True)) == ("李箱李箱", 0)
    assert repl.replace_text("李箱", repl.ReplaceRule(find="李箱", repl="X", whole=True)) == ("X", 1)


def test_rule_validation_and_seed():
    assert repl.ReplaceRule(find="").validate()
    assert "正则表达式有误" in repl.ReplaceRule(find="(", regex=True).validate()
    assert repl.literal_seed(repl.ReplaceRule(find=r"\d{3}李箱", regex=True)) == "李箱"
    assert repl.literal_seed(repl.ReplaceRule(find=r"\d{3}", regex=True)) is None
    assert repl.literal_seed(repl.ReplaceRule(find="李箱")) == "李箱"


def test_plan_prefers_custom_then_original():
    rule = repl.ReplaceRule(find="李箱", repl="箱子", source=repl.SOURCE_BOTH)
    ref = EntryRef(file="MainUIText.json", id="x", record_index=0, field_path=[{"k": "content"}])
    # 没改过 → 按原文算
    item = repl.plan_item(rule, ref, "李箱在此", "loc", None)
    assert item.after == "箱子在此" and item.custom_before is None and not item.from_custom
    # 改过 → 在自定义文本上改，不会丢掉原有改动
    item2 = repl.plan_item(rule, ref, "李箱在此", "loc", "李箱已经改过了")
    assert item2.after == "箱子已经改过了" and item2.from_custom
    assert item2.custom_before == "李箱已经改过了"
    # 只替换原文：即使有自定义文本也按原文算（会覆盖）
    item3 = repl.plan_item(repl.ReplaceRule(find="李箱", repl="箱子", source=repl.SOURCE_ORIGINAL),
                           ref, "李箱在此", "loc", "自定义")
    assert item3.after == "箱子在此" and item3.custom_before == "自定义"
    # 只替换自定义：没改过的条目不参与
    assert repl.plan_item(repl.ReplaceRule(find="李箱", repl="箱子", source=repl.SOURCE_CUSTOM),
                          ref, "李箱在此", "loc", None) is None


# ---------- 一键替换：端到端（方案 + 撤销） ----------


def test_collect_plan_apply_undo(env):
    ctx, _llc = env
    rule = repl.ReplaceRule(find="缓存", repl="高速缓存")
    cands = repl.collect_candidates(ctx, rule)
    assert cands, "全库候选里应当能找到「缓存」"
    items = repl.plan_candidates(ctx, cands, rule)
    assert items and items[0].after == "清除高速缓存"
    ok, errors = repl.apply_items(ctx, items)
    ctx.save_profile()
    assert ok == len(items) and not errors
    ref = items[0].ref
    assert ctx.profile.get(ref).value == "清除高速缓存"
    # 撤销：之前没改过的条目直接删掉
    assert repl.undo_items(ctx, items) == len(items)
    ctx.save_profile()
    assert ctx.profile.get(ref) is None


def test_regex_without_seed_scans_whole_index(env):
    """正则里没有可预筛的字面量时必须全库扫描（不能只看前 N 条候选，否则漏替换）。"""
    ctx, _llc = env
    rule = repl.ReplaceRule(find=r"[自白]定义", repl="X", regex=True)
    assert repl.literal_seed(rule) is None
    items = repl.plan_scope(ctx, rule)
    assert [i.after for i in items] == ["X翻译测试按钮"]
    # 候选上限不会被「前 N 条条目」吃掉：范围限定到某个人格时就只出这个实体的命中
    scoped = repl.plan_scope(ctx, repl.ReplaceRule(find="被动", repl="特性"), entity_key="P:10310")
    assert len(scoped) == 3 and all(i.ref.file == "Passives.json" for i in scoped)


def test_plan_scope_current_list_and_custom_only(env):
    ctx, _llc = env
    hits = ctx.search.search(text="缓存", limit=20)
    rule = repl.ReplaceRule(find="缓存", repl="高速缓存")
    items = repl.plan_scope(ctx, rule, hits=hits)
    assert len(items) == 1 and items[0].after == "清除高速缓存"
    # 只替换自定义文本：全库范围内只扫方案（没改过就什么都不做）
    assert repl.plan_scope(ctx, repl.ReplaceRule(find="缓存", repl="X", source=repl.SOURCE_CUSTOM)) == []
    ref = items[0].ref
    assert ctx.upsert_entry(ref, "自改的缓存").ok
    custom_items = repl.plan_scope(ctx, repl.ReplaceRule(find="缓存", repl="X", source=repl.SOURCE_CUSTOM))
    assert len(custom_items) == 1 and custom_items[0].after == "自改的X"


def test_entity_scope_limits_candidates(env):
    ctx, _llc = env
    rule = repl.ReplaceRule(find="被动", repl="特性")
    both = repl.plan_candidates(ctx, repl.collect_candidates(ctx, rule), rule)
    only_10310 = repl.plan_candidates(ctx, repl.collect_candidates(ctx, rule, entity_key="P:10310"), rule)
    assert len(both) > len(only_10310) >= 1
    assert all(i.ref.file == "Passives.json" for i in only_10310)


def test_replace_dialog_headless_flow(qapp, env):
    ctx, _llc = env
    hits = ctx.search.search(text="缓存", limit=50)
    dlg = ReplaceDialog(None, ctx, scope_label="当前列表", hits=hits)
    dlg.find_edit.setText("缓存")
    dlg.repl_edit.setText("高速缓存")
    dlg._preview()
    assert dlg.table.rowCount() == 1 and dlg.apply_btn.isEnabled()
    dlg._apply()
    assert dlg.saved and ctx.profile.count() == 1
    dlg._undo()
    assert ctx.profile.count() == 0
    dlg.close()


def test_replace_dialog_reports_bad_regex(qapp, env):
    ctx, _llc = env
    dlg = ReplaceDialog(None, ctx)
    dlg.find_edit.setText("(")
    dlg.regex_box.setChecked(True)
    dlg._preview()          # 免模态模式下只写日志，不阻塞
    assert dlg.table.rowCount() == 0 and not dlg.apply_btn.isEnabled()
    dlg.close()


# ---------- 回归：索引版本落后时界面不能崩 ----------


def test_codex_page_survives_stale_index(qapp, env):
    """SCHEMA_VERSION 升级后（旧库缺 passive_count 列）图鉴页仍要能构造出来。

    真实事故：打包版启动时构造图鉴页 → `no such column: passive_count` → 整个应用起不来。
    """
    import sqlite3

    from limbus_patcher.index import SCHEMA_VERSION
    from limbus_patcher.ui.codex_page import CodexPage

    ctx, llc = env
    con = sqlite3.connect(str(ctx.search.db_path))
    con.execute("ALTER TABLE entities DROP COLUMN passive_count")  # 模拟旧版本建出来的库
    con.execute(f"PRAGMA user_version={SCHEMA_VERSION - 1}")
    con.commit()
    con.close()

    page = CodexPage(ctx)              # 不抛异常
    assert page.level == 1
    assert ctx.search.list_entities("personality") == []   # 带新列的查询 → 空表而不是异常
    assert ctx.search.count_entities("personality") == 2    # 老查询照常（表还在，只是缺列）
    assert ctx.profile.count() == 0
    # 版本落后 → 必须判定为「需要重建」（否则用户会一直看到空图鉴）
    assert ctx.indexer.manifest_matches(Path(ctx.game_paths.llc_pack_dir), ctx.baseline_dir) is False
    page.refresh()
    assert page.level == 1
    page.close()


def test_schema_upgrade_rebuilds_entities_table(qapp, env):
    """版本升级后 entities 表必须重建（老表缺新列 → 图鉴静默变空）。"""
    import sqlite3

    from limbus_patcher.index import SCHEMA_VERSION

    ctx, _llc = env
    assert ctx.search.list_entities("personality")
    con = sqlite3.connect(str(ctx.search.db_path))
    con.execute("ALTER TABLE entities DROP COLUMN passive_count")
    con.execute(f"PRAGMA user_version={SCHEMA_VERSION - 1}")
    con.commit()
    con.close()
    assert ctx.search.list_entities("personality") == []

    assert ctx.ensure_index() is True                     # 版本落后 → 自动重建
    rows = ctx.search.list_entities("personality")
    assert rows and all("passive_count" in r for r in rows)
    assert [r["passive_count"] for r in rows if r["entity_key"] == "P:10310"] == [2]
