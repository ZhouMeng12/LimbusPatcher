"""赛季/获取方式：豆包任务包导出 → 答案汇总导入，以及人格一览分组。

脚本本体在 scripts/ 下（不是包），这里用 importlib 直接加载来做端到端测试。
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppPaths
from limbus_patcher.entities import KIND_EGO, KIND_PERSONALITY

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_script_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def pack(tmp_path) -> Path:
    """带 int id 的零协包（含活动追加表）。"""
    game = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", game)
    llc = game / "LimbusCompany_Data/Lang/LLC_zh-CN"
    (llc / "Personalities.json").write_text(json.dumps({"dataList": [
        {"id": 10101, "title": "LCB\n罪人", "name": "李箱", "desc": "李箱的第1人格"},
        {"id": 10310, "title": "拉·曼却领\n总督", "name": "堂吉诃德", "desc": "堂吉诃德的第10人格"},
        {"id": 9999, "title": "占位", "name": "维吉尔", "desc": ""},
    ]}, ensure_ascii=False), encoding="utf-8")
    # 活动追加表：用一个「不在实体排除表里」的特殊 id（400025 之类愚人节人格已被剔除）
    (llc / "Personalities-x1p1c1.json").write_text(json.dumps({"dataList": [
        {"id": 400099, "title": "活动人格\n测试", "name": "李箱", "desc": "李箱的???人格"},
    ]}, ensure_ascii=False), encoding="utf-8")
    (llc / "Egos.json").write_text(json.dumps({"dataList": [
        {"id": 20101, "name": "乌瞰刀", "desc": "李箱的基础E.G.O装备"},
    ]}, ensure_ascii=False), encoding="utf-8")
    return llc


# ---------- 导出 ----------


def test_export_collect_and_shards(tmp_path, pack):
    mod = _load_script("export_season_tasks")
    from limbus_patcher.season import MetaMaps

    persons, egos = mod.collect(pack, MetaMaps(data_dir=ROOT / "limbus_patcher" / "data"))
    ids = [p["id"] for p in persons]
    assert 10101 in ids and 10310 in ids and 400099 in ids
    assert 9999 not in ids, "9999 是占位条目，不算人格"
    assert [e["id"] for e in egos] == [20101]
    special = [p for p in persons if p["id"] == 400099][0]
    assert special["sinner"] == "李箱", "活动特殊 id 的罪人要从 desc 反查"

    text = mod.shard_text("人格", persons[:2], 1, 2)
    assert "只输出 JSON" in text and "现标注" in text
    assert text.count("｜") >= 4

    out = tmp_path / "seasons"
    argv = sys.argv
    sys.argv = ["export_season_tasks", "--llc", str(pack), "--out", str(out), "--per", "2"]
    try:
        assert mod.main() == 0
    finally:
        sys.argv = argv
    shards = sorted((out / "paste").glob("*.txt"))
    assert [p.name for p in shards] == ["01_人格.txt", "02_人格.txt", "03_EGO.txt"]
    assert (out / "提示词.md").is_file() and (out / "答案模板.json").is_file()
    assert "1/2 片" in shards[0].read_text(encoding="utf-8")


# ---------- 导入 ----------


def test_import_normalize_validates(tmp_path, pack):
    mod = _load_script("import_season_answers")
    persons, egos = mod.known_ids(pack)
    assert 10101 in persons and 20101 in egos

    problems: list[str] = []
    got = mod.normalize({"entities": [
        {"id": "10101", "season": "3", "acq": "Seasonal", "name_en": "LCB Yi Sang"},
        {"id": "20101", "season": 0, "acq": "base"},
        {"id": "777777", "season": 1, "acq": "base"},
        {"id": "abc", "season": 1, "acq": "base"},
        {"id": "10310", "season": 99, "acq": "wat"},
    ]}, persons, egos, problems)
    assert got["10101"]["season"] == 3 and got["10101"]["acq"] == "seasonal"
    assert got["20101"]["bucket"] == "egos"
    assert got["10310"]["season"] is None and got["10310"]["acq"] == "unknown"
    assert len(problems) == 4, problems  # 未知 id / 非法 id / season 越界 / acq 非法
    assert mod.rows_of([1, 2]) == [1, 2] and mod.rows_of({"files": [{"a": 1}]}) == [{"a": 1}]


def test_import_merges_only_missing_by_default(tmp_path, pack):
    mod = _load_script("import_season_answers")
    out = tmp_path / "season_map.json"
    out.write_text(json.dumps({
        "format_version": 1, "source": "wiki.gg",
        "identities": {"10101": {"season": 0, "acq": "base", "name_en": "LCB Sinner Yi Sang"}},
        "egos": {},
    }, ensure_ascii=False), encoding="utf-8")
    ans = tmp_path / "ans"
    ans.mkdir()
    (ans / "01.json").write_text(json.dumps({"entities": [
        {"id": "10101", "season": 4, "acq": "seasonal", "reason": "与现有不符"},
        {"id": "10310", "season": 3, "acq": "seasonal", "name_en": "The One Who Grips", "reason": "第3赛季"},
        {"id": "20101", "season": 0, "acq": "base"},
    ]}, ensure_ascii=False), encoding="utf-8")

    def run(*extra: str) -> int:
        argv = sys.argv
        sys.argv = ["import_season_answers", "--llc", str(pack), "--out", str(out),
                    "--ans", str(ans), *extra]
        try:
            return mod.main()
        finally:
            sys.argv = argv

    assert run("--dry-run") == 0
    before = json.loads(out.read_text(encoding="utf-8"))
    assert before["identities"]["10101"]["season"] == 0, "dry-run 不该动文件"

    assert run() == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["identities"]["10101"]["season"] == 0, "默认不覆盖现有标注"
    assert data["identities"]["10310"]["season"] == 3
    assert data["identities"]["10310"]["source"] == "doubao/huiji"
    assert data["egos"]["20101"]["acq"] == "base"
    assert "豆包/灰机" in data["source"]

    assert run("--apply-changes") == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["identities"]["10101"]["season"] == 4, "--apply-changes 才接受改动"
    report = ROOT / "data" / "seasons" / "变更报告.md"
    assert report.is_file() and "10101" in report.read_text(encoding="utf-8")


# ---------- 界面：人格一览按赛季 / 获取方式分组 ----------


@pytest.fixture
def win(tmp_path, pack):
    from PySide6.QtWidgets import QApplication

    from limbus_patcher.ui import theme
    from limbus_patcher.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(pack.parents[2]))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    window = MainWindow(ctx)
    window._index_ready()
    yield window
    window.close()


def test_entity_overview_grouping_by_season(win, tmp_path):
    import json as _json

    from limbus_patcher.ui.list_panel import HitView

    ctx = win.ctx
    # 造一份赛季映射：10101 基础 / 10310 第3赛季 / 400099 未标注
    (ctx.app_paths.cache_dir / "season_map.json").write_text(_json.dumps({
        "identities": {
            "10101": {"season": 0, "acq": "base"},
            "10310": {"season": 3, "acq": "seasonal"},
        },
        "egos": {"20101": {"season": 0, "acq": "base"}},
    }, ensure_ascii=False), encoding="utf-8")
    ctx.maps.reload()

    win._on_nav_category("entities:personality")
    assert win.list_panel.group_combo.isVisibleTo(win.list_panel), "实体一览里应显示分组下拉"
    rows = [v for v in win.list_panel.model.hits()]
    assert rows and not any(v.is_header for v in rows), "默认不分组"

    win.list_panel.group_combo.setCurrentIndex(win.list_panel.group_combo.findData("season"))
    win.refresh_list()
    rows = win.list_panel.model.hits()
    headers = [v.header for v in rows if v.is_header]
    assert "基础（1）" in headers and "第3赛季（1）" in headers and "未标注（1）" in headers
    assert headers[-1].startswith("未标注"), "未标注永远排最后"
    assert "标注进度 2/3" in win.list_panel.count_label.text()

    # 分组标题行不可激活：当前行是标题时不发 hit_activated
    seen: list = []
    win.list_panel.hit_activated.connect(seen.append)
    header_row = next(i for i, v in enumerate(rows) if v.is_header)
    win.list_panel.view.setCurrentIndex(win.list_panel.model.index(header_row, 0))
    assert not seen, "标题行不应触发条目激活"
    assert all(not v.is_header for v in win.list_panel.selected_hits())
    assert isinstance(rows[0], HitView)

    win.list_panel.group_combo.setCurrentIndex(win.list_panel.group_combo.findData("acq"))
    win.refresh_list()
    headers = [v.header for v in win.list_panel.model.hits() if v.is_header]
    assert "赛季限定（1）" in headers and "未标注（1）" in headers

    # 离开实体一览后不再分组
    win._on_nav_category("main_story")
    assert not win.list_panel.group_combo.isVisibleTo(win.list_panel)
    assert not any(v.is_header for v in win.list_panel.model.hits())
