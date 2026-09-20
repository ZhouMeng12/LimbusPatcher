"""增量同步专用测试：验证「没变化的文件不重写」以及各种边界。

覆盖：
1. 首次同步全量写入 → 第二次同步（源与目标都没变）几乎不写；
2. 改一条补丁值 → 只重写该文件，其余文件连 mtime 都不动；
3. 零协源文件被改动（内容 / 仅 mtime）、删除、新增时的行为；
4. 补丁 JSON 不走 (size, mtime) 快路径，副本被换回原文也必须重写；
5. 增量同步的副本包结果与全量同步逐文件内容哈希完全一致。
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from limbus_patcher.deploy import Deployer
from limbus_patcher.fsutil import collect_rel_files, sha256_file
from limbus_patcher.patch import EntryRef, Profile
from limbus_patcher.paths import resolve_game_paths

CLONE = "LLC_zh-CN_custom"
FULL = "LLC_zh-CN_full"
# 补丁涉及的三个文件（其中一个在子目录里，用于覆盖嵌套路径）
PATCHED = ("BattleKeywords.json", "MainUIText.json", "StoryData/1D101A.json")
# 纯复制文件，用来验证 (size, mtime_ns) 增量判定
PLAIN = "Personalities.json"

BOM = b"\xef\xbb\xbf"


def mk_profile() -> Profile:
    """构造一个小方案：3 个文件需要打补丁，其余原样复制。"""
    p = Profile(name="增量测试方案")
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
        EntryRef("StoryData/1D101A.json", 0, 0, [{"k": "content"}]),
        "格里高尔点上了烟，吐出了更长的烟气。",
        "格里高尔点上了烟，比平时更长久地吐出了烟气。",
    )
    return p


def tree_hashes(root: Path) -> dict[str, str]:
    """整棵树的 {相对路径: 内容 sha256}。"""
    return {rel: sha256_file(p) for rel, p in collect_rel_files(root).items()}


def stamps(root: Path) -> dict[str, tuple[int, int]]:
    """整棵树的 {相对路径: (size, mtime_ns)}，用于判断文件是否被重写。"""
    return {rel: (p.stat().st_size, p.stat().st_mtime_ns) for rel, p in collect_rel_files(root).items()}


def deps_and_paths(tmp_game, tmp_path):
    paths = resolve_game_paths(tmp_game)
    return paths, Deployer(tmp_path / "cache"), paths.patch_pack_dir(CLONE)


def test_first_sync_writes_all_then_second_sync_skips(tmp_game, tmp_path):
    """首次同步全量写入；第二次同步源与目标都没变 → 一个文件都不重写。"""
    paths, dep, clone = deps_and_paths(tmp_game, tmp_path)
    profile = mk_profile()
    total = len(collect_rel_files(paths.llc_pack_dir))

    first = dep.sync_clone(paths, CLONE, profile)
    assert first.ok, first.errors
    assert first.files_written == len(PATCHED)
    assert first.files_copied == total - len(PATCHED)
    assert first.files_skipped == 0
    assert first.files_removed == 0

    after_first = stamps(clone)
    second = dep.sync_clone(paths, CLONE, profile)
    assert second.ok, second.errors
    assert (second.files_written, second.files_copied, second.files_removed) == (0, 0, 0)
    assert second.files_skipped == total
    # 连 mtime 都没变 → 确实一个文件都没落盘
    assert stamps(clone) == after_first

    # 进度回调语义不变：仍然按 (已处理, 总数) 从 1 报到 total
    seen: list[tuple[int, int]] = []
    dep.sync_clone(paths, CLONE, profile, progress=lambda i, t: seen.append((i, t)))
    assert seen[0] == (1, total) and seen[-1] == (total, total)


def test_patch_value_change_rewrites_only_that_file(tmp_game, tmp_path):
    """改一条补丁值 → 只重写该文件，其它文件不动。"""
    paths, dep, clone = deps_and_paths(tmp_game, tmp_path)
    profile = mk_profile()
    total = len(collect_rel_files(paths.llc_pack_dir))
    dep.sync_clone(paths, CLONE, profile)
    before = stamps(clone)
    bk = clone / "BattleKeywords.json"
    bk_before = bk.read_bytes()

    # 只改动 BattleKeywords.json 里那一条目的译文（upsert 参数为 值, 原文）
    profile.upsert(
        EntryRef("BattleKeywords.json", "Enhancement", 1, [{"k": "desc"}]),
        "【增量】一回合内攻击技能的最终威力大幅增加。",
        "一回合内攻击技能的最终威力大幅增加。",
    )
    report = dep.sync_clone(paths, CLONE, profile)
    assert report.ok, report.errors
    assert report.files_written == 1
    assert report.files_copied == 0
    assert report.files_skipped == total - 1

    after = stamps(clone)
    changed = {rel for rel in after if after[rel] != before[rel]}
    assert changed == {"BattleKeywords.json"}

    raw = bk.read_bytes()
    assert raw != bk_before
    assert raw.startswith(BOM)  # 仍然是 UTF-8 BOM
    data = json.loads(raw.decode("utf-8-sig"))
    by_id = {str(e["id"]): e for e in data["dataList"]}
    assert by_id["Enhancement"]["desc"] == "【增量】一回合内攻击技能的最终威力大幅增加。"
    assert by_id["AreaAtk"]["name"] == "群体攻击"  # 同文件其它条目未被破坏
    # 原子写不留临时文件
    assert not list(clone.rglob("*.tmp*"))


def test_patched_json_regenerated_even_if_stamp_matches(tmp_game, tmp_path):
    """补丁 JSON 不依赖 (size, mtime)：副本时间戳与源一致但内容过期时也必须重写。"""
    paths, dep, clone = deps_and_paths(tmp_game, tmp_path)
    profile = mk_profile()
    dep.sync_clone(paths, CLONE, profile)

    src = paths.llc_pack_dir / "BattleKeywords.json"
    dst = clone / "BattleKeywords.json"
    shutil.copy2(src, dst)  # 把副本换成未打补丁的原文（size 与 mtime 都与源相同）
    st = src.stat()
    os.utime(dst, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert (dst.stat().st_size, dst.stat().st_mtime_ns) == (st.st_size, st.st_mtime_ns)

    report = dep.sync_clone(paths, CLONE, profile)
    assert report.errors == []
    assert report.files_written == 1  # 内容比对发现不一致 → 重写
    assert report.files_copied == 0

    data = json.loads(dst.read_bytes().decode("utf-8-sig"))
    by_id = {str(e["id"]): e for e in data["dataList"]}
    assert by_id["Enhancement"]["desc"] == "一回合内攻击技能的最终威力大幅增加。"


def test_source_change_size_and_mtime_is_recopied(tmp_game, tmp_path):
    """零协源文件内容变化 → 重新复制；仅 mtime 变化也视为变化。"""
    paths, dep, clone = deps_and_paths(tmp_game, tmp_path)
    profile = mk_profile()
    total = len(collect_rel_files(paths.llc_pack_dir))
    dep.sync_clone(paths, CLONE, profile)
    src = paths.llc_pack_dir / PLAIN
    dst = clone / PLAIN

    # (a) 内容变化（size 随之变化）
    obj = json.loads(src.read_text(encoding="utf-8-sig"))
    obj["dataList"].append({"id": "NEW_FROM_LLC", "name": "零协新增条目"})
    src.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    report = dep.sync_clone(paths, CLONE, profile)
    assert report.errors == []
    assert report.files_copied == 1
    assert report.files_written == 0
    assert report.files_skipped == total - 1
    assert json.loads(dst.read_text(encoding="utf-8-sig"))["dataList"][-1]["id"] == "NEW_FROM_LLC"

    # (b) 内容与 size 都不变，只把 mtime 推后 1 小时 → 也要重新复制
    st = src.stat()
    os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns + 3_600_000_000_000))
    report = dep.sync_clone(paths, CLONE, profile)
    assert report.files_copied == 1
    assert report.files_skipped == total - 1
    assert (dst.stat().st_size, dst.stat().st_mtime_ns) == (
        src.stat().st_size,
        src.stat().st_mtime_ns,
    )

    # (c) 再同步一次：又回到全部跳过
    report = dep.sync_clone(paths, CLONE, profile)
    assert (report.files_copied, report.files_written) == (0, 0)
    assert report.files_skipped == total


def test_source_added_and_deleted(tmp_game, tmp_path):
    """零协包新增文件要复制过来；已删除的文件副本要清理。"""
    paths, dep, clone = deps_and_paths(tmp_game, tmp_path)
    profile = mk_profile()
    total = len(collect_rel_files(paths.llc_pack_dir))
    dep.sync_clone(paths, CLONE, profile)

    (paths.llc_pack_dir / "Enemies.json").unlink()  # 零协删文件
    new_dir = paths.llc_pack_dir / "NewFolder"  # 零协新增文件（含新目录）
    new_dir.mkdir()
    (new_dir / "Extra.json").write_text('{"dataList": []}\n', encoding="utf-8")

    report = dep.sync_clone(paths, CLONE, profile)
    assert report.errors == []
    assert report.files_copied == 1  # 只复制新增的 Extra.json
    assert report.files_written == 0
    assert report.files_skipped == total - 1
    assert report.files_removed == 1  # Enemies.json
    assert not (clone / "Enemies.json").exists()
    assert (clone / "NewFolder" / "Extra.json").is_file()

    # 清空目录也被回收（原包里的 StoryData 仍在，空目录只有 NewFolder 之外的情况）
    assert not [p for p in clone.rglob("*") if p.is_dir() and not any(p.iterdir())]


def test_corrupted_plain_copy_is_repaired(tmp_game, tmp_path):
    """纯复制文件被写坏（size 相同但 mtime 不同）→ 重新复制修复。"""
    paths, dep, clone = deps_and_paths(tmp_game, tmp_path)
    profile = mk_profile()
    dep.sync_clone(paths, CLONE, profile)
    src = paths.llc_pack_dir / PLAIN
    dst = clone / PLAIN
    dst.write_bytes(b"!" * src.stat().st_size)  # 同 size，内容不同，mtime 变新

    report = dep.sync_clone(paths, CLONE, profile)
    assert report.files_copied == 1
    assert report.files_written == 0
    assert sha256_file(dst) == sha256_file(src)


def test_known_boundary_same_size_and_mtime_not_rewritten(tmp_game, tmp_path):
    """已知边界（有意取舍，不是 bug）：

    纯复制文件若在副本侧被替换成「size 与源相同、且 mtime 被伪造回源值」的内容，
    (size, mtime_ns) 快路径无法分辨，本次不会重写。要识别它只能逐文件比对内容哈希，
    代价是每次同步都读满整个包（~50 MB），收益远小于成本，因此接受该边界；
    需要打补丁的 JSON 不受此影响（见 test_patched_json_regenerated_even_if_stamp_matches）。
    """
    paths, dep, clone = deps_and_paths(tmp_game, tmp_path)
    profile = mk_profile()
    total = len(collect_rel_files(paths.llc_pack_dir))
    dep.sync_clone(paths, CLONE, profile)

    src = paths.llc_pack_dir / PLAIN
    dst = clone / PLAIN
    tampered = b"Z" * src.stat().st_size
    dst.write_bytes(tampered)
    st = src.stat()
    os.utime(dst, ns=(st.st_atime_ns, st.st_mtime_ns))

    report = dep.sync_clone(paths, CLONE, profile)
    assert (report.files_copied, report.files_written) == (0, 0)
    assert report.files_skipped == total
    assert dst.read_bytes() == tampered  # 未被修复 —— 这就是接受的边界


def test_entry_removed_reverts_file_to_raw_source(tmp_game, tmp_path):
    """补丁条目被移除 → 该文件必须回退成零协原文（不能因「看起来没变」而留着旧补丁）。"""
    paths, dep, clone = deps_and_paths(tmp_game, tmp_path)
    profile = mk_profile()
    total = len(collect_rel_files(paths.llc_pack_dir))
    dep.sync_clone(paths, CLONE, profile)
    src = paths.llc_pack_dir / "MainUIText.json"
    dst = clone / "MainUIText.json"
    assert sha256_file(dst) != sha256_file(src)  # 已打补丁

    ref = EntryRef("MainUIText.json", "clear_cache", 0, [{"k": "content"}])
    assert profile.remove(ref) is True
    report = dep.sync_clone(paths, CLONE, profile)
    assert report.errors == []
    assert (report.files_written, report.files_copied) == (0, 1)
    assert report.files_skipped == total - 1
    assert sha256_file(dst) == sha256_file(src)  # 已回退成原文

    # 再加回条目 → 重新打补丁（走内容比对，不依赖 mtime）
    profile.upsert(ref, "清除全部缓存", "清除缓存")
    report = dep.sync_clone(paths, CLONE, profile)
    assert report.files_written == 1
    assert sha256_file(dst) != sha256_file(src)
    assert json.loads(dst.read_bytes().decode("utf-8-sig"))["dataList"][0]["content"] == "清除全部缓存"


def test_incremental_clone_equals_full_sync(tmp_game, tmp_path):
    """增量同步多轮之后的副本包，与从零全量同步的结果逐文件哈希完全一致。"""
    paths, dep, _ = deps_and_paths(tmp_game, tmp_path)
    profile = mk_profile()

    # A：增量路径 —— 先同步，再制造「零协更新 + 补丁改动 + 增删文件」，然后再同步
    dep.sync_clone(paths, CLONE, profile)
    llc = paths.llc_pack_dir
    bk = json.loads(llc.joinpath("BattleKeywords.json").read_text(encoding="utf-8-sig"))
    for e in bk["dataList"]:
        if e["id"] == "Agility":
            e["desc"] = "零协把这条原文改掉了"
    (llc / "BattleKeywords.json").write_text(json.dumps(bk, ensure_ascii=False, indent=2), encoding="utf-8")
    (llc / "Personalities.json").unlink()
    (llc / "新增文件.json").write_text('{"dataList": []}\n', encoding="utf-8")
    profile.upsert(
        EntryRef("MainUIText.json", "clear_cache", 0, [{"k": "content"}]),
        "清空缓存",
        "清除全部缓存",
    )
    incr = dep.sync_clone(paths, CLONE, profile)
    assert incr.errors == []
    cloned = dep.sync_clone(paths, CLONE, profile)  # 再同步一次走全跳过分支
    assert (cloned.files_written, cloned.files_copied, cloned.files_removed) == (0, 0, 0)

    # B：全量路径 —— 在同样的源状态下从空目录同步一次
    dep.sync_clone(paths, FULL, profile)

    assert tree_hashes(paths.patch_pack_dir(CLONE)) == tree_hashes(paths.patch_pack_dir(FULL))
