from __future__ import annotations

import json
from pathlib import Path

from limbus_patcher.index import Indexer, normalize
from limbus_patcher.patch import EntryRef, ref_label
from limbus_patcher.search import SearchEngine


def test_normalize():
    assert normalize(" 技能 描述\n") == "技能描述"
    assert normalize("Hello World") == "helloworld"


def test_build_index(llc_dir, tmp_path):
    idx = Indexer(tmp_path / "index.sqlite", tmp_path / "manifest.json")
    result = idx.build(llc_dir)
    # 8 个合法文件（BrokenFile.json 只告警）
    assert result.total_files == 8
    assert len(result.warnings) == 1 and "BrokenFile.json" in result.warnings[0]
    # 叶子数：BattleKeywords 6 + Skills_Ego 8 + MainUIText 2 + 1D101A 4 + S101A 4
    #        + Personalities 8 + Egos 2 + Enemies 4 = 38
    assert result.total_entries == 38
    assert result.category_counts.get("combat") == 1
    assert result.category_counts.get("ego") == 2
    assert result.category_counts.get("ui") == 1
    assert result.category_counts.get("main_story") == 1   # S101A
    assert result.category_counts.get("dungeon_story") == 1   # 1D101A（第1章迷宫剧情，AI 判定表）
    assert result.category_counts.get("identity") == 1
    assert result.category_counts.get("enemy") == 1


def test_manifest_matches(llc_dir, tmp_path):
    import shutil

    pack = tmp_path / "pack"
    shutil.copytree(llc_dir, pack)
    idx = Indexer(tmp_path / "index.sqlite", tmp_path / "manifest.json")
    idx.build(pack)
    assert idx.manifest_matches(pack)
    # 修改一个文件的内容（大小可能不变，mtime 变化）
    p = pack / "BattleKeywords.json"
    data = p.read_text(encoding="utf-8")
    p.write_text(data + "\n", encoding="utf-8")
    assert not idx.manifest_matches(pack)
    # 新增文件
    (pack / "NewFile.json").write_text('{"dataList":[]}', encoding="utf-8")
    assert not idx.manifest_matches(pack)


def test_rules_stamp_only_depends_on_content(monkeypatch, tmp_path):
    """回归：单文件 exe 每次启动都会把内置 data/*.json 解包到新的临时目录（mtime 每次都变），
    指纹只能看内容——否则每次启动都判定「规则变了」，于是每次启动都全量重建索引。"""
    import os
    from limbus_patcher import index as indexmod

    rules = tmp_path / "category_rules.json"
    kinds = tmp_path / "misc_story_kinds.json"
    rules.write_text('{"format_version":1}', encoding="utf-8")
    kinds.write_text('{"format_version":1}', encoding="utf-8")
    monkeypatch.setattr(indexmod, "rules_path", lambda: rules)
    monkeypatch.setattr(indexmod, "kinds_path", lambda: kinds)

    before = indexmod.rules_stamp()
    os.utime(rules, (1, 1))
    os.utime(kinds, (2, 2))
    assert indexmod.rules_stamp() == before          # 只动 mtime：指纹不变

    kinds.write_text('{"format_version":2}', encoding="utf-8")
    assert indexmod.rules_stamp() != before          # 内容变了：必须重建


def test_search(llc_dir, tmp_path):
    idx = Indexer(tmp_path / "index.sqlite", tmp_path / "manifest.json")
    idx.build(llc_dir)
    eng = SearchEngine(tmp_path / "index.sqlite")

    hits = eng.search("群体攻击")
    assert hits and any(h.file == "BattleKeywords.json" and h.text == "群体攻击" for h in hits)

    # KeyID 搜索
    hits = eng.search("2010611")
    assert hits and all(h.ref.id == 2010611 for h in hits)

    # 模糊归一化：中间有空格
    hits = eng.search("最终威力 增加")
    assert hits and any(h.ref.id == "Enhancement" for h in hits)

    # 分类筛选
    hits = eng.search("清除", category="ui")
    assert hits and all(h.category == "ui" for h in hits)
    hits = eng.search("清除", category="skill")
    assert hits == []

    # BOM 文件可读
    hits = eng.search("格里高尔")
    assert hits and any(h.file == "StoryData/1D101A.json" for h in hits)


def test_categories_present(llc_dir, tmp_path):
    idx = Indexer(tmp_path / "index.sqlite", tmp_path / "manifest.json")
    idx.build(llc_dir)
    eng = SearchEngine(tmp_path / "index.sqlite")
    counts = eng.count_by_category()
    assert counts["combat"] == 1 and counts["ego"] == 2 and counts["ui"] == 1 and counts["main_story"] == 1
    assert counts["dungeon_story"] == 1 and counts["identity"] == 1 and counts["enemy"] == 1


def test_index_includes_record_without_id(tmp_path):
    """缺少 id 的记录（真实包里的人格剧情）也要入索引：id 记为 None，靠 record_index 定位。"""
    pack = tmp_path / "pack"
    (pack / "StoryData").mkdir(parents=True)
    (pack / "StoryData" / "P10210.json").write_text(
        json.dumps(
            {
                "dataList": [
                    {"id": 7, "content": "有 id 的记录正文"},
                    {
                        "model": "이상",
                        "teller": "李箱",
                        "content": "无 id 的记录正文",
                        "levelList": [{"level": 1, "desc": "无 id 的嵌套描述"}],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    idx = Indexer(tmp_path / "index.sqlite", tmp_path / "manifest.json")
    result = idx.build(pack)
    assert result.total_entries == 4  # 1（有 id 记录）+ 3（teller / content / 嵌套 desc）
    assert result.warnings == []  # 不再因为缺少 id 告警跳过

    eng = SearchEngine(tmp_path / "index.sqlite")
    hits = eng.search("无 id 的记录正文")
    assert len(hits) == 1
    hit = hits[0]
    assert hit.file == "StoryData/P10210.json" and hit.category == "identity_story"
    assert hit.ref.id is None and hit.ref.record_index == 1
    assert EntryRef.from_key(hit.ref_key) == hit.ref
    assert ref_label(hit.ref) == "记录 #1" and "None" not in hit.ref.key()

    # 嵌套叶子（levelList）也可搜到
    hits = eng.search("无 id 的嵌套描述")
    assert len(hits) == 1 and hits[0].ref.field_path[0]["k"] == "levelList"

    # 无 id 记录的 id_norm 是空串：KeyID 搜索不会退化成匹配字符串 "none"
    assert eng.search("none") == []
    # 有 id 的记录照旧按 id 命中
    assert [h.ref.id for h in eng.search("7")] == [7]


def test_manifest_matches_requires_current_schema(llc_dir, tmp_path):
    """索引库缺失或 schema 版本落后时必须返回 False（SCHEMA_VERSION 升级后自动重建）。"""
    import shutil
    import sqlite3

    from limbus_patcher.index import SCHEMA_VERSION

    pack = tmp_path / "pack"
    shutil.copytree(llc_dir, pack)
    db = tmp_path / "index.sqlite"
    idx = Indexer(db, tmp_path / "manifest.json")
    idx.build(pack)
    assert idx.manifest_matches(pack)

    def set_version(v: int) -> None:
        con = sqlite3.connect(db)
        try:
            con.execute(f"PRAGMA user_version={v}")
        finally:
            con.close()

    set_version(SCHEMA_VERSION - 1)  # 模拟旧版本建出来的库
    assert not idx.manifest_matches(pack)
    set_version(SCHEMA_VERSION)
    assert idx.manifest_matches(pack)
    db.unlink()  # 库文件被删
    assert not idx.manifest_matches(pack)
