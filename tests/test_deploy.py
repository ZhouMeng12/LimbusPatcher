from __future__ import annotations

import json
from pathlib import Path

import pytest

from limbus_patcher.deploy import Deployer, original_text
from limbus_patcher.fsutil import load_json, sha256_file
from limbus_patcher.patch import EntryRef, Profile
from limbus_patcher.paths import resolve_game_paths

CLONE = "LLC_zh-CN_custom"


def mk_profile():
    p = Profile(name="测试方案")
    p.upsert(
        EntryRef("BattleKeywords.json", "Enhancement", 1, [{"k": "desc"}]),
        "一回合内攻击技能的最终威力大幅增加。",
        "一回合内攻击技能的最终威力增加等同于本效果层数的数值。",
    )
    p.upsert(
        EntryRef("MainUIText.json", "clear_cache", 0, [{"k": "content"}]),
        "清除全部缓存",
        "清除缓存",
    )
    p.upsert(
        EntryRef("Skills_Ego_Personality-01.json", 2010611, 0, [{"k": "levelList"}, {"i": 1, "h": {"level": 3}}, {"k": "desc"}]),
        "等级3新描述",
        "",
    )
    p.upsert(
        EntryRef("StoryData/1D101A.json", 0, 0, [{"k": "content"}]),
        "格里高尔点上了烟，吐出了更长的烟气。",
        "格里高尔点上了烟，比平时更长久地吐出了烟气。",
    )
    return p


def llc_hashes(game_dir: Path) -> dict[str, str]:
    llc = game_dir / "LimbusCompany_Data" / "Lang" / "LLC_zh-CN"
    return {p.name: sha256_file(p) for p in llc.rglob("*.json") if p.is_file()}


def test_original_text(llc_dir):
    ref = EntryRef("BattleKeywords.json", "Enhancement", 1, [{"k": "desc"}])
    text, err = original_text(llc_dir, ref)
    assert err is None and "最终威力" in text
    bad = EntryRef("BattleKeywords.json", "NoSuch", 0, [{"k": "desc"}])
    assert original_text(llc_dir, bad)[0] is None


def test_enable_apply_view_disable(tmp_game, tmp_path):
    paths = resolve_game_paths(tmp_game)
    before = llc_hashes(tmp_game)
    profile = mk_profile()
    dep = Deployer(tmp_path / "cache")

    report = dep.enable(paths, CLONE, profile)
    assert report.ok, report.errors
    assert report.files_written == 4
    assert report.files_copied == 7  # BrokenFile + Personalities + Egos + Enemies + StoryData/S101A + 2 字体
    assert report.previous_lang == "LLC_zh-CN"

    # 原包一字未动
    assert llc_hashes(tmp_game) == before

    # config.json 切换 + 未知键保留
    cfg, err = load_json(paths.config_path)
    assert err is None and cfg["lang"] == CLONE and cfg.get("futureKey") == "keep-me"

    # 副本包内容正确（BOM + 合并结果 + 其余条目完整）
    clone_bk = paths.patch_pack_dir(CLONE) / "BattleKeywords.json"
    raw = clone_bk.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    data = json.loads(raw.decode("utf-8-sig"))
    by_id = {str(e["id"]): e for e in data["dataList"]}
    assert by_id["Enhancement"]["desc"] == "一回合内攻击技能的最终威力大幅增加。"
    assert by_id["AreaAtk"]["name"] == "群体攻击"
    assert by_id["Agility"]["desc"].startswith("一回合内速度值")

    # 嵌套路径写入
    skills = json.loads((paths.patch_pack_dir(CLONE) / "Skills_Ego_Personality-01.json").read_text(encoding="utf-8-sig"))
    assert skills["dataList"][0]["levelList"][1]["desc"] == "等级3新描述"

    # 应用状态
    view = dep.view(paths, CLONE, profile)
    assert view.applied and view.enabled and view.revision_matches

    # 方案再变更 → 应用状态失效
    profile.upsert(EntryRef("MainUIText.json", "custom_translation_note", 1, [{"k": "content"}]), "新", "自定义翻译测试按钮")
    view = dep.view(paths, CLONE, profile)
    assert view.enabled and not view.applied

    # 停用：lang 恢复
    dep.disable(paths, CLONE, "LLC_zh-CN")
    cfg, _ = load_json(paths.config_path)
    assert cfg["lang"] == "LLC_zh-CN"

    # 无临时文件残留
    assert not list(paths.patch_pack_dir(CLONE).rglob("*.tmp*"))


def test_sync_bad_entry_falls_back(tmp_game, tmp_path):
    paths = resolve_game_paths(tmp_game)
    profile = Profile(name="坏条目")
    profile.upsert(EntryRef("BattleKeywords.json", "Enhancement", 1, [{"k": "no_such_field"}]), "新", "原文")
    dep = Deployer(tmp_path / "cache")
    report = dep.sync_clone(paths, CLONE, profile)
    assert report.errors and report.files_written == 0
    # 文件按原样复制，仍是合法 JSON
    clone_bk = paths.patch_pack_dir(CLONE) / "BattleKeywords.json"
    data, err = load_json(clone_bk)
    assert err is None and data is not None


def test_compat_check(tmp_game, tmp_path):
    paths = resolve_game_paths(tmp_game)
    profile = mk_profile()
    dep = Deployer(tmp_path / "cache")
    result = dep.check_entries(paths, profile)
    assert all(status == "ok" for status, _ in result.values())

    # 原文变化 → changed
    llc = paths.llc_pack_dir
    bk, _ = load_json(llc / "BattleKeywords.json")
    for e in bk["dataList"]:
        if e["id"] == "Enhancement":
            e["desc"] = "原文被汉化更新改掉了"
    (llc / "BattleKeywords.json").write_text(json.dumps(bk, ensure_ascii=False), encoding="utf-8")
    result = dep.check_entries(paths, profile)
    assert any(status == "changed" and "Enhancement" in key for key, (status, _) in result.items())

    # 文件消失 → missing
    (llc / "StoryData" / "1D101A.json").unlink()
    result = dep.check_entries(paths, profile)
    assert any(status == "missing" and "1D101A" in key for key, (status, _) in result.items())


def test_remove_stale_files(tmp_game, tmp_path):
    paths = resolve_game_paths(tmp_game)
    profile = Profile()
    dep = Deployer(tmp_path / "cache")
    dep.sync_clone(paths, CLONE, profile)
    clone = paths.patch_pack_dir(CLONE)
    (clone / "ZombieFile.json").write_text("{}", encoding="utf-8")
    report = dep.sync_clone(paths, CLONE, profile)
    assert report.files_removed == 1
    assert not (clone / "ZombieFile.json").exists()
