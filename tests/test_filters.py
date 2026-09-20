"""章节/赛季/种类筛选（索引与检索层）测试。"""
from __future__ import annotations

from limbus_patcher.index import Indexer
from limbus_patcher.search import SearchEngine


def build(llc_dir, tmp_path):
    idx = Indexer(tmp_path / "index.sqlite", tmp_path / "manifest.json", meta_overlay=tmp_path)
    idx.build(llc_dir)
    return SearchEngine(tmp_path / "index.sqlite")


def test_chapter_filter(llc_dir, tmp_path):
    eng = build(llc_dir, tmp_path)
    chapters = eng.list_chapters()
    assert ("c1", "第1章") in chapters
    hits = eng.search(chapter="c1")
    assert hits and all(h.file.startswith("StoryData/") for h in hits)
    levels = eng.list_levels("c1")
    assert ("1D10", "对话 1D10") in levels
    assert eng.search(chapter="c1", level="1D10")
    assert eng.search(chapter="c1", level="不存在的关卡") == []


def test_season_filter(llc_dir, tmp_path):
    eng = build(llc_dir, tmp_path)
    seasons = eng.list_seasons()
    assert ("base", "基础") in seasons  # 10101/10102/20101
    assert ("s4", "第4赛季") in seasons  # 20106 往昔 = S4 通行证
    base = eng.search(season="base")
    assert base and all(h.file in ("Personalities.json", "Egos.json") for h in base)
    assert all(h.ref.id != 20106 for h in base)
    s4 = eng.search(season="s4")
    assert s4 and all(h.ref.id == 20106 for h in s4)


def test_kind_filter(llc_dir, tmp_path):
    eng = build(llc_dir, tmp_path)
    kinds = eng.list_kinds()
    assert any(label == "WAW 异想体" for label, _ in kinds)
    hits = eng.search(kind_label="WAW 异想体")
    assert hits and all(h.ref.id == "8001" and h.file == "Enemies.json" for h in hits)


def test_combined_filters(llc_dir, tmp_path):
    eng = build(llc_dir, tmp_path)
    hits = eng.search(text="李箱", category="identity", season="base")
    assert hits and all(h.category == "identity" for h in hits)


def test_season_labels_on_hits(llc_dir, tmp_path):
    eng = build(llc_dir, tmp_path)
    hits = eng.search(text="往昔")
    assert hits and hits[0].season_label == "第4赛季" and hits[0].acq_label == "通行证"
    wa = eng.search(text="黑檀女王的苹果", kind_label="WAW 异想体")
    assert wa and wa[0].kind_label == "WAW 异想体"


def test_sinner_filter(llc_dir, tmp_path):
    eng = build(llc_dir, tmp_path)
    # 罪人树：李箱(01) 的人格
    ids = eng.search(categories=["identity"], sinner_code="01")
    assert ids and all(str(h.ref.id) in ("10101", "10102") and h.file == "Personalities.json" for h in ids)
    # 李箱 的 E.G.O（fixture 含 Egos.json 与 Skills_Ego_Personality-01.json）
    egos = eng.search(categories=["ego"], sinner_code="01")
    assert egos and all(
        str(h.ref.id) in ("20101", "20106", "2010611") and h.file in ("Egos.json", "Skills_Ego_Personality-01.json")
        for h in egos
    )
    # 罪人浏览根：人格+EGO 全量
    all_hits = eng.search(categories=["identity", "ego"], sinner_code="01")
    assert len(all_hits) == len(ids) + len(egos)
    # 按罪人的文件数
    counts = eng.count_by_sinner()
    assert counts.get("01") == 3  # Personalities.json + Egos.json + Skills_Ego_Personality-01.json
