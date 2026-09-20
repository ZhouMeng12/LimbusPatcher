"""补译文件（零协包里没有的新章节文件）在部署里的行为。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppPaths
from limbus_patcher.patch import EntryRef
from limbus_patcher.supplement import SupplementPack

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def env(tmp_path) -> tuple[AppContext, Path]:
    game = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", game)
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    return ctx, game


def _chapter_file(text: str = "第十章第一行") -> dict:
    return {"dataList": [{"id": 0, "content": text},
                         {"id": 1, "model": "단테", "content": "第二行"}]}


def _write_json(path: Path, obj) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


# ---------- 管理器 ----------


def test_supplement_add_validate_enable_remove(tmp_path):
    pack = SupplementPack(tmp_path / "data")
    src = _write_json(tmp_path / "S1000B.json", _chapter_file())
    ok, msg = pack.add("StoryData/S1000B.json", src, note="第十章剧情")
    assert ok and "已导入" in msg
    files = pack.files()
    assert len(files) == 1 and files[0].rel == "StoryData/S1000B.json"
    assert files[0].enabled and files[0].records == 2 and files[0].note == "第十章剧情"
    assert pack.count() == (1, 1) and "1/1" in pack.summary()

    assert pack.set_enabled("StoryData/S1000B.json", False)
    assert pack.count() == (1, 0) and pack.enabled_map() == {}
    assert pack.set_all_enabled(True) == 1 and pack.count() == (1, 1)

    assert pack.remove("StoryData/S1000B.json")
    assert pack.files() == [] and not (pack.root / "StoryData/S1000B.json").exists()


def test_supplement_rejects_broken_files(tmp_path):
    pack = SupplementPack(tmp_path / "data")
    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    ok, msg = pack.add("StoryData/X.json", bad)
    assert not ok and "JSON 解析失败" in msg
    ok, msg = pack.add("StoryData/X.json", _write_json(tmp_path / "list.json", [1, 2, 3]))
    assert not ok and ("缺少 dataList" in msg or "顶层不是对象" in msg)
    ok, msg = pack.add("../escape.json", _write_json(tmp_path / "ok.json", _chapter_file()))
    assert not ok and "路径不合法" in msg
    assert pack.files() == []


# ---------- 部署 ----------


def test_deploy_keeps_supplement_and_removes_when_disabled(env, tmp_path):
    ctx, game = env
    src = _write_json(tmp_path / "S1000B.json", _chapter_file())
    ok, msg = ctx.supplement.add("StoryData/S1000B.json", src, note="第十章")
    assert ok, msg

    report = ctx.apply()
    clone = ctx.game_paths.patch_pack_dir(ctx.config.patch_pack_name)
    assert report.ok, report.errors
    deployed = clone / "StoryData/S1000B.json"
    assert deployed.is_file(), "启用中的补译文件必须进副本包"
    data = json.loads(deployed.read_text(encoding="utf-8-sig"))
    assert data["dataList"][0]["content"] == "第十章第一行"

    # 停用 → 再应用 → 副本包里的补译文件被清掉（零协本来就没有它）
    ctx.supplement.set_all_enabled(False)
    ctx.apply()
    assert not deployed.is_file(), "停用后应从副本包移除"
    # 零协原文件仍在
    assert (clone / "MainUIText.json").is_file()


def test_deploy_ignores_supplement_for_existing_file(env, tmp_path):
    """零协包里已有的文件：补译文件不得覆盖同 id 记录（官方译文优先）。"""
    ctx, _game = env
    src = _write_json(tmp_path / "MainUIText.json", {"dataList": [{"id": "clear_cache",
                                                                   "content": "被覆盖了"}]})
    ctx.supplement.add("MainUIText.json", src)
    report = ctx.apply()
    clone = ctx.game_paths.patch_pack_dir(ctx.config.patch_pack_name)
    text = json.loads((clone / "MainUIText.json").read_text(encoding="utf-8-sig"))
    contents = [r.get("content") for r in text["dataList"]]
    assert "被覆盖了" not in contents, "补译文件不能顶掉零协既有记录"


def test_deploy_reports_invalid_supplement(env, tmp_path):
    ctx, _game = env
    src = _write_json(tmp_path / "S1001B.json", _chapter_file())
    ctx.supplement.add("StoryData/S1001B.json", src)
    # 导入后再把磁盘上的文件改坏（模拟外部破坏）→ 部署必须报错且不写入
    (ctx.supplement.root / "StoryData/S1001B.json").write_text("{oops", encoding="utf-8")
    report = ctx.apply()
    clone = ctx.game_paths.patch_pack_dir(ctx.config.patch_pack_name)
    assert not (clone / "StoryData/S1001B.json").exists()
    assert any("补译文件无效" in e for e in report.errors)


def test_supplement_file_is_editable_via_profile(env, tmp_path):
    """补译文件也能像零协文件一样被编辑：原文从 supplement/ 读，补丁写进副本包。"""
    ctx, _game = env
    ctx.supplement.add("StoryData/S1000B.json", _write_json(tmp_path / "S1000B.json", _chapter_file()))
    ref = EntryRef(file="StoryData/S1000B.json", id=0, record_index=0, field_path=[{"k": "content"}])
    original, err = ctx.original_of(ref)
    assert err is None and original == "第十章第一行"
    assert ctx.upsert_entry(ref, "改过的第一行").ok
    ctx.save_profile()
    ctx.apply()
    clone = ctx.game_paths.patch_pack_dir(ctx.config.patch_pack_name)
    data = json.loads((clone / "StoryData/S1000B.json").read_text(encoding="utf-8-sig"))
    assert data["dataList"][0]["content"] == "改过的第一行"


def test_supplement_merges_missing_records_into_existing_file(env, tmp_path):
    """零协已有同名文件时：只追加「零协缺的记录」，已有记录仍以零协为准。

    第十章章节名（StageChapterText 缺第十章那两行）就是靠这条路径生效的。
    """
    ctx, _game = env
    src = _write_json(tmp_path / "MainUIText.json", {"dataList": [
        {"id": "clear_cache", "content": "篡改官方译文"},
        {"id": "chapter_n_110", "company": "N公司", "chaptertitle": "凝视之下"},
    ]})
    ok, msg = ctx.supplement.add("MainUIText.json", src, note="章节名")
    assert ok, msg
    report = ctx.apply()
    clone = ctx.game_paths.patch_pack_dir(ctx.config.patch_pack_name)
    rows = json.loads((clone / "MainUIText.json").read_text(encoding="utf-8-sig"))["dataList"]
    by_id = {str(r.get("id")): r for r in rows}
    assert "chapter_n_110" in by_id, "零协缺的记录要追加进去"
    assert by_id["chapter_n_110"]["chaptertitle"] == "凝视之下"
    assert by_id["clear_cache"]["content"] != "篡改官方译文", "零协已有的记录不能被覆盖"
    assert report.ok and not report.errors


# ---------- 补译文件进索引（软件里能搜能改） ----------


def test_supplement_files_are_indexed_and_searchable(env, tmp_path):
    ctx, _game = env
    story = _write_json(tmp_path / "S1000B.json",
                        {"dataList": [{"id": 0, "content": "衷心欢迎莅临西西弗百货。"},
                                      {"id": 1, "model": "단테", "content": "这里是哪里？"}]})
    rpg = _write_json(tmp_path / "rpg-loc-dialogue-floor-1.json",
                      {"dataList": [{"key": "D1", "texts": [{"index": 0, "text": "迷宫的一层。"}]}]})
    assert ctx.supplement.add("StoryData/S1000B.json", story)[0]
    assert ctx.supplement.add("RPGSystem/rpg-loc-dialogue-floor-1.json", rpg)[0]
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)

    hits = ctx.search.search(text="西西弗百货", limit=10, source="supplement")
    assert hits and hits[0].source == "supplement" and hits[0].file == "StoryData/S1000B.json"
    rpg_hits = ctx.search.search(text="迷宫的一层", limit=10, source="supplement")
    assert rpg_hits and rpg_hits[0].file == "RPGSystem/rpg-loc-dialogue-floor-1.json"
    # 分类规则把 RPGSystem 细分了：rpg-loc-dialogue-* → rpg_dialogue（见 data/category_rules.json）
    assert rpg_hits[0].category.startswith("rpg"), "RPG 文本应归到「RPG 剧情」分类"

    all_sup = ctx.search.search(text="", limit=1000, source="supplement")
    assert len(all_sup) >= 3
    assert all(h.source == "supplement" for h in all_sup)
    # 不带过滤时两类都在索引里；带 source 过滤时各自干净
    both = ctx.search.search(text="", limit=2000)
    assert any(h.source == "llc" for h in both) and any(h.source == "supplement" for h in both)
    assert all(h.source == "supplement" for h in both if h.file.startswith(("RPGSystem/", "StoryData/S1000B")))


def test_supplement_text_is_editable_in_app(env, tmp_path):
    """补译条目也能像零协条目一样改：原文从 supplement/ 读，补丁写进副本包。"""
    ctx, _game = env
    story = _write_json(tmp_path / "S1001B.json", {"dataList": [{"id": 0, "content": "原始译文"}]})
    ctx.supplement.add("StoryData/S1001B.json", story)
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    hit = ctx.search.search(text="原始译文", limit=5, source="supplement")[0]
    assert ctx.original_of(hit.ref)[0] == "原始译文"
    assert ctx.upsert_entry(hit.ref, "改过的补译").ok
    ctx.save_profile()
    ctx.apply()
    clone = ctx.game_paths.patch_pack_dir(ctx.config.patch_pack_name)
    rows = json.loads((clone / "StoryData/S1001B.json").read_text(encoding="utf-8-sig"))["dataList"]
    assert rows[0]["content"] == "改过的补译"
