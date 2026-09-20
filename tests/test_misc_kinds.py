"""AI 判定表（misc_story_kinds）→ 分类/章节 接线测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from limbus_patcher import misc_kinds
from limbus_patcher.categories import CATEGORIES, chapter_hint, classify


def test_answers_file_exists_and_parses():
    entries = misc_kinds._table()
    # 真实答案是 201 条（147 迷宫 + 54 间章活动）
    assert len(entries) >= 200
    stats = misc_kinds.stats()
    assert stats.get("迷宫剧情", 0) >= 100 and stats.get("间章活动", 0) >= 30


def test_known_files_map_to_expected_category():
    # 迷宫剧情 → 第 N 章
    assert misc_kinds.kind_of("StoryData/1D101A.json") == "迷宫剧情"
    assert misc_kinds.chapter_of("StoryData/5D201B.json") == "第5章"
    assert classify("StoryData/5D201B.json") == "dungeon_story"
    assert chapter_hint("StoryData/5D201B.json") == "第5章"
    # 间章活动 → ES / PC
    assert classify("StoryData/ES011A.json") == "event"
    assert chapter_hint("StoryData/PC01A.json") == "8.5-EX"
    assert misc_kinds.category_of("StoryData/PC01A.json") == "event"


def test_unknown_files_fall_back_to_rules():
    assert misc_kinds.entry_of("StoryData/S525B.json") is None
    assert classify("StoryData/S525B.json") == "main_story"
    assert classify("StoryData/P10310.json") == "identity_story"
    assert classify("StoryData/NOT_EXIST.json") == "main_story"  # 仍按路径规则


def test_new_category_registered():
    """新分类要写进随包规则文件（别的测试可能临时替换 CATEGORIES，所以直接读文件断言）。"""
    from limbus_patcher.season import package_data_dir

    obj = json.loads((package_data_dir() / "category_rules.json").read_text(encoding="utf-8"))
    assert obj["categories"]["dungeon_story"] == "迷宫剧情"
    assert obj["categories"]["misc_story"] == "其他剧情"
    members = [c for g in obj["groups"].values() for c in g["members"]]
    assert "dungeon_story" in members and len(members) == len(set(members))
    # 代码内置默认值与文件保持一致
    assert CATEGORIES["dungeon_story"] == "迷宫剧情"


def test_order_and_chapter_number_lookup():
    item = misc_kinds.entry_of("StoryData/2D102B.json")
    assert item and item["order"] == 1 and item["chapter_number"] == "02"
    assert misc_kinds.order_of("StoryData/2D102B.json") == 1
    assert misc_kinds.chapter_number_of("StoryData/2D102B.json") == "02"
    assert misc_kinds.kind_of("StoryData/不存在.json") is None
