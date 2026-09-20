"""英文基线进索引 / 搜索：schema、text_en 列、搜索范围。"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from limbus_patcher.baseline import clear_cache
from limbus_patcher.index import SCHEMA_VERSION, Indexer
from limbus_patcher.search import SearchEngine

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def game(tmp_path) -> Path:
    dst = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", dst)
    clear_cache()
    yield dst
    clear_cache()


def dirs(game: Path) -> tuple[Path, Path]:
    llc = game / "LimbusCompany_Data/Lang/LLC_zh-CN"
    base = game / "LimbusCompany_Data/Assets/Resources_moved/Localize/en"
    return llc, base


def build(tmp_path, game: Path) -> Indexer:
    llc, base = dirs(game)
    idx = Indexer(tmp_path / "index.sqlite", tmp_path / "manifest.json", meta_overlay=tmp_path)
    idx.build(llc, baseline_dir=base)
    return idx


def test_schema_version_is_current():
    assert SCHEMA_VERSION >= 8  # 8=英文基线列；9=人格/EGO 实体列（见 tests/test_entities.py）


def test_build_stores_english_text(tmp_path, game):
    llc, base = dirs(game)
    idx = Indexer(tmp_path / "index.sqlite", tmp_path / "manifest.json", meta_overlay=tmp_path)
    res = idx.build(llc, baseline_dir=base)
    assert res.baseline_hits > 0 and res.baseline_dir == str(base)
    eng = SearchEngine(tmp_path / "index.sqlite")
    hits = eng.search("Mass Attack", scope="baseline")
    assert hits and hits[0].text_en == "Mass Attack"
    assert hits[0].ref.id == "AreaAtk"
    stats = eng.baseline_stats()
    assert stats[0] == res.baseline_hits and stats[1] == res.total_entries


def test_scope_original_baseline_all(tmp_path, game):
    build(tmp_path, game)
    eng = SearchEngine(tmp_path / "index.sqlite")
    # 英文词只在 baseline/all 命中
    assert eng.search("Mass Attack", scope="baseline")
    assert not eng.search("Mass Attack", scope="original")
    assert eng.search("Mass Attack", scope="all")
    # 中文词在 original 命中，baseline 不命中
    assert eng.search("群体攻击", scope="original")
    assert not eng.search("群体攻击", scope="baseline")


def test_english_missing_rows_are_null(tmp_path, game):
    build(tmp_path, game)
    eng = SearchEngine(tmp_path / "index.sqlite")
    # 英文的 Enhancement 没有 name 字段 → 该叶子 text_en 为 NULL，但零协原文仍在
    hits = eng.search("强壮", scope="original")
    assert hits
    row = [h for h in hits if h.ref.field_path == [{"k": "name"}]]
    assert row and row[0].text_en is None
    # 同一条记录的 desc 有英文（说明是"英文缺字段"而不是整条没对上）
    hits = eng.search("一回合内攻击技能", scope="original")
    assert hits and hits[0].text_en and hits[0].text_en.startswith("Final power")
    # 没有英文基线的零协文件（Skills_Ego_Personality-01）整份 text_en 为 NULL
    hits = eng.search("某日的肖像", scope="original")
    assert hits and all(h.text_en is None for h in hits)
    assert hits[0].ref.file == "Skills_Ego_Personality-01.json"


def test_manifest_detects_baseline_changes(tmp_path, game):
    llc, base = dirs(game)
    idx = build(tmp_path, game)
    assert idx.manifest_matches(llc, base) is True
    # 基线目录换了 → 必须重建
    assert idx.manifest_matches(llc, base.parent / "jp") is False
    # 英文文件改了 → 必须重建
    p = base / "EN_BattleKeywords.json"
    data = p.read_text(encoding="utf-8").replace("Mass Attack", "Mass Attack!!")
    p.write_text(data, encoding="utf-8")
    assert idx.manifest_matches(llc, base) is False
    # 原本没有英文对应的零协文件，现在出现了英文文件 → 也要重建
    idx2 = build(tmp_path, game)
    assert idx2.manifest_matches(llc, base) is True
    (base / "EN_Skills_Ego_Personality-01.json").write_text('{ "dataList": [] }', encoding="utf-8")
    assert idx2.manifest_matches(llc, base) is False
    # 英文目录里多出无关键协的文件不影响（不触发重建）
    idx3 = build(tmp_path, game)
    (base / "EN_NotInLlc.json").write_text('{ "dataList": [] }', encoding="utf-8")
    assert idx3.manifest_matches(llc, base) is True


def test_lookup_meta_for_custom_entries(tmp_path, game):
    build(tmp_path, game)
    eng = SearchEngine(tmp_path / "index.sqlite")
    hits = eng.search("群体攻击", scope="original")
    assert hits
    ref = hits[0].ref
    meta = eng.lookup_meta([ref])
    assert ref.key() in meta
    got = meta[ref.key()]
    assert got.category == hits[0].category and got.text == hits[0].text
    assert eng.lookup_meta([]) == {}


def test_build_without_baseline_keeps_working(tmp_path, game):
    """没给英文基线目录时（旧调用方式）照常构建，text_en 全为 NULL。"""
    llc, _base = dirs(game)
    idx = Indexer(tmp_path / "index.sqlite", tmp_path / "manifest.json", meta_overlay=tmp_path)
    res = idx.build(llc)
    assert res.baseline_hits == 0 and res.baseline_dir is None
    eng = SearchEngine(tmp_path / "index.sqlite")
    assert eng.baseline_stats()[0] == 0
    assert eng.search("群体攻击", scope="original")


def test_empty_stub_files_do_not_force_rebuild(tmp_path, game):
    """零协包里的空壳文件（`{}`，无 dataList）也要记进 manifest 的英文基线表。

    否则 manifest_matches() 每次都会认为「新出现了英文基线文件」→ 每次启动全量重建索引
    （实测 ~14 秒）。回归见 _fill_missing_baseline()。
    """
    llc, base = dirs(game)
    (llc / "Stub-a1c9p1.json").write_text("{}", encoding="utf-8")
    (base / "EN_Stub-a1c9p1.json").write_text("{}", encoding="utf-8")
    idx = build(tmp_path, game)
    assert idx.manifest_matches(llc, base) is True
    # 再建一次也该是「无需重建」
    idx2 = build(tmp_path, game)
    assert idx2.manifest_matches(llc, base) is True
