"""人格 / E.G.O 实体识别与索引测试。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from limbus_patcher.entities import (
    ROLE_ENEMY,
    CONTENT_CHOICES,
    KIND_EGO,
    KIND_PERSONALITY,
    ROLE_EGO,
    ROLE_EGO_PASSIVE,
    ROLE_EGO_SKILL,
    ROLE_IDENTITY,
    ROLE_IDENTITY_PASSIVE,
    ROLE_IDENTITY_SKILL,
    ROLE_IDENTITY_STORY,
    ROLE_IDENTITY_VOICE,
    ROLE_OTHER,
    entity_id_of,
    entity_key,
    file_entity,
    parse_entity_key,
    split_entity_id,
)
from limbus_patcher.index import SCHEMA_VERSION, Indexer
from limbus_patcher.search import SearchEngine

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ---------- 纯函数：文件 → 实体/角色 ----------


def test_schema_version_is_current():
    assert SCHEMA_VERSION >= 9  # 10 起把分类规则/AI 判定表指纹纳入重建判定


@pytest.mark.parametrize("rel,kind,role", [
    ("Personalities.json", KIND_PERSONALITY, ROLE_IDENTITY),
    ("Personalities-x1p1c1.json", KIND_PERSONALITY, ROLE_IDENTITY),
    ("Egos.json", KIND_EGO, ROLE_EGO),
    ("Egos-a1c9p3.json", KIND_EGO, ROLE_EGO),
    ("Skills_Personality-03.json", KIND_PERSONALITY, ROLE_IDENTITY_SKILL),
    ("Skills_Ego_Personality-01.json", KIND_EGO, ROLE_EGO_SKILL),
    ("Skills_Ego.json", KIND_EGO, ROLE_EGO_SKILL),
    ("StoryData/P10310.json", KIND_PERSONALITY, ROLE_IDENTITY_STORY),
    ("PersonalityVoiceDlg/Voice_DonQuixote_Bloodfiend_10310.json", KIND_PERSONALITY, ROLE_IDENTITY_VOICE),
    ("EGOVoiceDig/Voice_EGO_YiSang_1.json", KIND_EGO, "ego_voice"),
])
def test_file_entity_rules(rel, kind, role):
    info = file_entity(rel)
    assert info is not None and info.kind == kind and info.role == role


@pytest.mark.parametrize("rel", [
    "StoryData/S525B.json", "StoryData/1D101A.json", "StoryData/PC01A.json",
    "BattleKeywords.json", "UI_MainUIText.json",
    # 注意：Enemies.json 现在**是**实体来源（敌方图鉴的敌人来自这里），见 test_enemy_files_are_entities
])
def test_non_entity_files(rel):
    info = file_entity(rel)
    assert info is not None and info.role == ROLE_OTHER and info.kind is None


def test_variants_and_ids():
    assert file_entity("StoryData/P10710A.json").variant == "A"
    assert file_entity("PersonalityVoiceDlg/Voice_DonQuixote_Bloodfiend_10310.json").variant == "Bloodfiend"
    assert file_entity("PersonalityVoiceDlg/Voice_Yisang_LCB_10101.json").variant == "LCB"
    assert file_entity("PersonalityVoiceDlg/Voice_DonQuixote_Bloodfiend_10310.json").entity_id == 10310
    assert file_entity("EGOVoiceDig/Voice_EGO_YiSang_1.json").entity_id is None


def test_split_and_key_helpers():
    assert split_entity_id(10310) == ("03", 10)
    assert split_entity_id(20106) == ("01", 6)  # 20106 = 2 + 01(李箱) + 06
    assert split_entity_id(400099) == ("00", 99)  # 特殊 id：罪人码取不到，由 desc 兜底
    assert entity_key(KIND_PERSONALITY, 10310) == "P:10310"
    assert entity_key(KIND_EGO, 20106) == "E:20106"
    assert parse_entity_key("P:10310") == (KIND_PERSONALITY, 10310)
    assert parse_entity_key("E:20106") == (KIND_EGO, 20106)
    assert parse_entity_key("X:1") is None and parse_entity_key("") is None


def test_entity_id_of_uses_record_id():
    # 本体：rid 就是实体 id
    assert entity_id_of("Personalities.json", {"id": 10310}) == ("P:10310", ROLE_IDENTITY)
    assert entity_id_of("Egos-a1c9p3.json", {"id": 20106}) == ("E:20106", ROLE_EGO)
    # 技能：rid = 实体 id × 100 + 技能号
    assert entity_id_of("Skills_Personality-01.json", {"id": 1010501}) == ("P:10105", ROLE_IDENTITY_SKILL)
    assert entity_id_of("Skills_Ego_Personality-01.json", {"id": 2010611}) == ("E:20106", ROLE_EGO_SKILL)
    # 剧情/语音：文件名即可
    assert entity_id_of("StoryData/P10310.json", None) == ("P:10310", ROLE_IDENTITY_STORY)
    assert entity_id_of("EGOVoiceDig/Voice_EGO_YiSang_1.json", None) == (None, "ego_voice")


def test_entity_id_of_bad_ids_degrades():
    # 缺 id / 非数字 id / 位数不对 → 不给实体，但角色仍保留（便于导航里兜底显示）
    assert entity_id_of("Skills_Personality-01.json", {}) == (None, ROLE_IDENTITY_SKILL)
    assert entity_id_of("Skills_Personality-01.json", {"id": "1010501"}) == (None, ROLE_IDENTITY_SKILL)
    assert entity_id_of("Personalities.json", {"id": 999}) == (None, ROLE_IDENTITY)
    assert entity_id_of("StoryData/S525B.json", None) == (None, ROLE_OTHER)


def test_content_choices_cover_roles():
    assert [k for k, _ in CONTENT_CHOICES[KIND_PERSONALITY]] == ["all", ROLE_IDENTITY, ROLE_IDENTITY_SKILL,
                                                                 ROLE_IDENTITY_PASSIVE, ROLE_IDENTITY_STORY,
                                                                 ROLE_IDENTITY_VOICE]
    assert [k for k, _ in CONTENT_CHOICES[KIND_EGO]] == ["all", ROLE_EGO, ROLE_EGO_SKILL, ROLE_EGO_PASSIVE,
                                                         "ego_voice"]


# ---------- 索引：实体表 + role 列 ----------


@pytest.fixture
def game(tmp_path) -> Path:
    dst = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", dst)
    llc = dst / "LimbusCompany_Data/Lang/LLC_zh-CN"
    # 夹具补齐实体相关文件（真实包结构的缩影）
    (llc / "Personalities.json").write_text(json.dumps({"dataList": [
        {"id": 10301, "title": "LCB\n罪人", "name": "堂吉诃德", "nameWithTitle": "堂吉诃德", "desc": "堂吉诃德的第1人格"},
        {"id": 10310, "title": "拉·曼却领\n总督", "name": "堂吉诃德", "desc": "堂吉诃德的第10人格"},
        # 用不在实体排除表（entity_exclude.json）里的特殊 id：愚人节那批已经被剔除
        {"id": 400099, "title": "活动人格 测试", "name": "堂吉诃德", "desc": "堂吉诃德的???人格"},
        {"id": 9999, "title": "猩红视线", "name": "维吉里乌斯", "desc": ""},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Egos.json").write_text(json.dumps({"dataList": [
        {"id": 20301, "name": "乌瞰刀", "desc": "堂吉诃德的基础E.G.O装备"},
        {"id": 20310, "name": "桑丘", "desc": "堂吉诃德的专用E.G.O装备"},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Skills_Personality-03.json").write_text(json.dumps({"dataList": [
        {"id": 1031001, "levelList": [{"level": 1, "name": "穿刺", "desc": "技能一"}]},
        {"id": 1031002, "levelList": [{"level": 1, "name": "突进", "desc": "技能二"}]},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Skills_Ego_Personality-03.json").write_text(json.dumps({"dataList": [
        {"id": 2031011, "levelList": [{"level": 1, "name": "桑丘", "desc": "EGO 技能"}]},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "StoryData/P10310.json").write_text(json.dumps({"dataList": [
        {"id": 0, "teller": "堂吉诃德", "title": "拉·曼却领", "content": "人格剧情正文一"},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "PersonalityVoiceDlg").mkdir(exist_ok=True)
    (llc / "PersonalityVoiceDlg/Voice_DonQuixote_Bloodfiend_10310.json").write_text(json.dumps({"dataList": [
        {"id": 0, "content": "语音一"},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "EGOVoiceDig").mkdir(exist_ok=True)
    (llc / "EGOVoiceDig/Voice_EGO_DonQuixote_3.json").write_text(json.dumps({"dataList": [
        {"id": 0, "content": "EGO 语音一"},
    ]}, ensure_ascii=False), encoding="utf-8")
    return dst


def build(tmp_path, game: Path) -> Indexer:
    llc = game / "LimbusCompany_Data/Lang/LLC_zh-CN"
    idx = Indexer(tmp_path / "index.sqlite", tmp_path / "manifest.json", meta_overlay=tmp_path)
    idx.build(llc)
    return idx


def test_index_collects_entities(tmp_path, game):
    idx = build(tmp_path, game)
    eng = SearchEngine(tmp_path / "index.sqlite")
    keys = {e["entity_key"] for e in eng.list_entities(KIND_PERSONALITY)}
    assert keys == {"P:10301", "P:10310", "P:400099"}  # 9999 占位条目不算人格
    assert eng.count_entities(KIND_EGO) == 2
    # 特殊 id 的罪人由 desc 兜底推导
    special = eng.entity_summary("P:400099")
    assert special["sinner_code"] == "03" and special["variant"] == "special"
    # 序号：10310 → 10；400099 → 99
    assert eng.entity_summary("P:10310")["seq"] == 10


def test_index_roles_and_counts(tmp_path, game):
    build(tmp_path, game)
    eng = SearchEngine(tmp_path / "index.sqlite")
    roles = eng.count_by_role()
    assert roles.get(ROLE_IDENTITY_STORY, 0) >= 1
    assert roles.get(ROLE_IDENTITY_SKILL, 0) >= 2
    assert roles.get(ROLE_EGO_SKILL, 0) >= 1
    assert roles.get(ROLE_IDENTITY_VOICE, 0) >= 1
    info = eng.entity_summary("P:10310")
    # role_counts 是「文本叶子数」：1 条剧情记录 3 个叶子（teller/title/content），2 条技能各 2 个叶子
    assert info["role_counts"].get(ROLE_IDENTITY_STORY) == 3
    assert info["role_counts"].get(ROLE_IDENTITY_SKILL) == 4
    # 实体表里的计数是「记录数」
    assert info["story_count"] == 1 and info["skill_count"] == 2
    # 技能/剧情/语音都能按实体 + 角色取到
    assert eng.search("", entity_key="P:10310", roles=[ROLE_IDENTITY_SKILL])
    assert eng.search("", entity_key="P:10310", roles=[ROLE_IDENTITY_STORY])[0].role == ROLE_IDENTITY_STORY
    assert eng.search("", entity_key="P:10310", roles=[ROLE_IDENTITY_VOICE])[0].text == "语音一"
    # 别的实体取不到
    assert eng.search("", entity_key="P:10301", roles=[ROLE_IDENTITY_STORY]) == []


def test_index_category_split(tmp_path, game):
    """人格剧情不再算主线；待确认的迷宫/活动文件归「其他剧情」。"""
    from limbus_patcher.categories import classify

    assert classify("StoryData/P10310.json") == "identity_story"
    assert classify("StoryData/S525B.json") == "main_story"
    # AI 判定表已回填：PC/ES → 间章活动，1D → 第1章迷宫剧情
    assert classify("StoryData/PC01A.json") == "event"
    assert classify("StoryData/ES011A.json") == "event"
    assert classify("StoryData/1D101A.json") == "dungeon_story"
    build(tmp_path, game)
    eng = SearchEngine(tmp_path / "index.sqlite")
    story = eng.search("人格剧情正文一", scope="original")
    assert story and story[0].role == ROLE_IDENTITY_STORY


def test_enemy_files_are_entities():
    """Enemies.json 是敌方图鉴的实体来源（此前被当成「非实体文件」）。"""
    info = file_entity("Enemies.json")
    assert info is not None and info.kind == "enemy" and info.role == ROLE_ENEMY
