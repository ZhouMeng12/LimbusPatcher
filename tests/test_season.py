"""赛季/种类映射加载与标签测试（依赖内置 data/*.json）。"""
from __future__ import annotations

from pathlib import Path

from limbus_patcher.season import (
    MetaMaps,
    acq_display,
    kind_display,
    package_data_dir,
    season_display,
    season_key,
)


def test_package_data_bundled():
    d = package_data_dir()
    assert (d / "season_map.json").is_file()
    assert (d / "enemy_map.json").is_file()


def test_season_labels():
    assert season_key(None) is None
    assert season_key({"season": 0, "acq": "base"}) == "base"
    assert season_key({"season": 3, "acq": "seasonal"}) == "s3"
    assert season_key({"season": None, "acq": "base"}) == "base"
    assert season_display({"season": 0, "acq": "base"}) == "基础"
    assert season_display({"season": None, "acq": "base"}) == "常驻"
    assert season_display({"season": 4, "acq": "pass"}) == "第4赛季"
    assert acq_display({"season": 4, "acq": "pass"}) == "通行证"
    assert acq_display({"season": 4, "acq": "seasonal"}) is None
    assert acq_display({"season": 4, "acq": "walpurgis"}) == "瓦夜"
    assert kind_display({"group": "abnormality", "label": "WAW"}) == "WAW 异想体"
    assert kind_display({"group": "faction", "label": "N Corp."}) == "N Corp.（势力）"
    assert kind_display({"group": "unit", "label": "敌方单位"}) == "敌方单位"


def test_bundled_maps_have_known_ids():
    maps = MetaMaps()
    assert maps.identity_meta("10101") is not None
    assert maps.identity_meta("10102") is not None
    assert maps.ego_meta("20101") is not None
    assert maps.ego_meta("20106") is not None
    assert maps.enemy_meta("8001") is not None
    assert maps.enemy_meta("8001")["label"] == "WAW"


def test_overlay_priority(tmp_path):
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "season_map.json").write_text(
        '{"identities": {"99999": {"season": 7, "acq": "walpurgis"}}}', encoding="utf-8"
    )
    maps = MetaMaps(overlay_dir=overlay)
    assert maps.identity_meta("99999") == {"season": 7, "acq": "walpurgis"}
    assert maps.identity_meta("10101") is None  # overlay 完全覆盖内置表
