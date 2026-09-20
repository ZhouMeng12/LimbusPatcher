"""实体排除表（data/entity_exclude.json）：愚人节人格不进图鉴，但文本照旧可搜可改。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from limbus_patcher import entities as ent
from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppPaths
from limbus_patcher.entities import (
    KIND_EGO,
    KIND_PERSONALITY,
    ROLE_IDENTITY,
    ROLE_IDENTITY_SKILL,
    entity_id_of,
)
from limbus_patcher.index import rules_stamp

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def env(tmp_path) -> tuple[AppContext, Path]:
    game = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", game)
    llc = game / "LimbusCompany_Data/Lang/LLC_zh-CN"
    (llc / "Personalities.json").write_text(json.dumps({"dataList": [
        {"id": 10101, "title": "LCB\n罪人", "name": "李箱", "desc": "李箱的第1人格"},
    ]}, ensure_ascii=False), encoding="utf-8")
    # 愚人节整活人格（排除表里）+ 一个正常活动人格
    (llc / "Personalities-x1p1c1.json").write_text(json.dumps({"dataList": [
        {"id": 400025, "title": "小鸡班\n班长", "name": "李箱", "desc": "李箱的???人格"},
        {"id": 400099, "title": "活动人格\n测试", "name": "李箱", "desc": "李箱的???人格"},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Skills_personality-x1p1c1.json").write_text(json.dumps({"dataList": [
        {"id": 40002501, "levelList": [{"level": 1, "name": "我来正理", "desc": "愚人节技能说明"}]},
        {"id": 40009901, "levelList": [{"level": 1, "name": "活动技能", "desc": "活动技能说明"}]},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Egos.json").write_text(json.dumps({"dataList": [
        {"id": 20101, "name": "乌瞰刀", "desc": "李箱的基础E.G.O装备"},
    ]}, ensure_ascii=False), encoding="utf-8")
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    return ctx, llc


def test_exclude_table_defaults():
    table = ent.load_exclude_map()
    assert 400025 in table["identities"] and 400036 in table["identities"]
    assert 40501 in table["identities"], "映画投影人格（默尔索 背井离乡的那一夜）也要剔除"
    assert ent.is_excluded_entity(KIND_PERSONALITY, 400025)
    assert not ent.is_excluded_entity(KIND_PERSONALITY, 400099)
    assert not ent.is_excluded_entity(KIND_EGO, 400025)  # E.G.O 侧没排除
    # 缺文件时不炸（返回空表）
    empty = ent.load_exclude_map(Path("不存在的目录/entity_exclude.json"))
    assert empty == {"identities": set(), "egos": set()}


def test_excluded_entity_gets_no_key():
    assert entity_id_of("Personalities.json", {"id": 400025}) == (None, ROLE_IDENTITY)
    assert entity_id_of("Skills_personality-x1p1c1.json", {"id": 40002501}) == (None, ROLE_IDENTITY_SKILL)
    assert entity_id_of("Personalities.json", {"id": 400099}) == ("P:400099", ROLE_IDENTITY)


def test_excluded_entity_absent_from_codex_but_text_searchable(env):
    ctx, _llc = env
    keys = [e["entity_key"] for e in ctx.search.list_entities(KIND_PERSONALITY)]
    assert "P:10101" in keys and "P:400099" in keys
    assert "P:400025" not in keys, "愚人节人格不该出现在人格一览"
    assert ctx.search.count_entities(KIND_PERSONALITY) == 2

    # 文本还在索引里：搜得到、也能定位编辑
    hits = ctx.search.search(text="愚人节技能说明", limit=10)
    assert len(hits) == 1 and hits[0].entity_key is None and hits[0].role == ROLE_IDENTITY_SKILL
    text, err = ctx.original_of(hits[0].ref)
    assert err is None and text == "愚人节技能说明"

    # 同一个文件里的正常活动人格不受影响
    ok = ctx.search.search(text="活动技能说明", limit=10)
    assert ok and ok[0].entity_key == "P:400099"


def test_exclude_file_change_triggers_rebuild(tmp_path):
    """排除表内容进 rules_stamp：改列表 → 索引自动重建（不用升 schema）。"""
    from limbus_patcher import index as index_mod

    path = index_mod.exclude_path()
    original = path.read_text(encoding="utf-8")
    try:
        path.write_text(original, encoding="utf-8", newline="")  # 统一换行后再取基准
        stamp = rules_stamp()
        path.write_text(original.replace("400036", "400037"), encoding="utf-8", newline="")
        assert rules_stamp() != stamp
    finally:
        path.write_text(original, encoding="utf-8", newline="")
        ent.clear_exclude_cache()
    assert rules_stamp() == stamp


def test_rebuild_drops_entities_no_longer_collected(env):
    """重建索引时必须清空 entities：否则排除掉的人格会变成「幽灵人格」留在图鉴里。"""
    ctx, llc = env
    assert "P:400099" in [e["entity_key"] for e in ctx.search.list_entities(KIND_PERSONALITY)]
    # 模拟「先收录、后排除」：把 400099 加进排除表（直接调函数注入，避免动真数据文件）
    saved = ent.load_exclude_map
    try:
        ent.load_exclude_map = lambda path=None: {"identities": {400099}, "egos": set()}
        ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    finally:
        ent.load_exclude_map = saved
    keys = {e["entity_key"] for e in ctx.search.list_entities(KIND_PERSONALITY)}
    assert "P:400099" not in keys, f"重建后不该留下幽灵实体：{keys}"
    assert keys == {"P:10101", "P:400025"}, keys  # 这次只排除 400099，400025 反而被收录
    assert "P:400099" not in {h.entity_key for h in ctx.search.search(text="活动人格", limit=5)}
