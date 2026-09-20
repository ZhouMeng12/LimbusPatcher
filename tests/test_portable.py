"""便携方案包（导出/导入）测试。"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from limbus_patcher.patch import EntryRef, Profile
from limbus_patcher.portable import (
    MANIFEST_NAME,
    OVERRIDES_NAME,
    PROFILE_NAME,
    PortableError,
    export_pack,
    import_pack,
    peek_pack,
)


def _ref(file="BattleKeywords.json", rid="Enhancement"):
    return EntryRef(file=file, id=rid, record_index=0, field_path=[{"k": "desc"}])


def _profile() -> Profile:
    p = Profile(name="我的方案")
    p.upsert(_ref(), "自定义描述", "原始描述")
    return p


def _overrides() -> dict:
    return {"0-01战前": {"key1": {"record": 3}, "key2": {"deleted": True}}}


def test_export_creates_expected_members(tmp_path):
    dest = tmp_path / "pack"          # 无后缀 → 自动补 .zip
    res = export_pack(dest, _profile(), _overrides())
    assert res.path.suffix == ".zip" and res.path.is_file()
    assert res.entries == 1 and res.story_rules == 2 and res.backups == 0
    with zipfile.ZipFile(res.path) as zf:
        names = set(zf.namelist())
        assert {MANIFEST_NAME, PROFILE_NAME, OVERRIDES_NAME} <= names
        assert "backups/" not in " ".join(names)
        manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
    assert manifest["kind"] == "limbus_patcher_portable"
    assert manifest["profile_name"] == "我的方案" and manifest["entries"] == 1


def test_export_with_backups_keeps_latest_five(tmp_path):
    backups = tmp_path / "backups"
    backups.mkdir()
    for i in range(7):
        (backups / f"backup_2026010{i}_1_startup.zip").write_bytes(b"zip")
    res = export_pack(tmp_path / "p.zip", _profile(), {}, backups, with_backups=True)
    assert res.backups == 5
    with zipfile.ZipFile(res.path) as zf:
        assert len([n for n in zf.namelist() if n.startswith("backups/")]) == 5


def test_roundtrip_import(tmp_path):
    pack = export_pack(tmp_path / "p.zip", _profile(), _overrides()).path
    profiles = tmp_path / "app" / "profiles"
    cache = tmp_path / "app" / "cache"
    res = import_pack(pack, profiles, cache)
    assert res.profile_name == "我的方案" and res.entries == 1 and res.story_rules == 2
    assert res.profile_path.is_file()
    loaded = Profile(); loaded.load(res.profile_path)
    assert loaded.name == "我的方案"
    assert loaded.get(_ref()).value == "自定义描述"
    rules = json.loads((cache / OVERRIDES_NAME).read_text(encoding="utf-8"))
    assert rules == _overrides()


def test_import_merges_story_overrides_and_keeps_existing(tmp_path):
    profiles = tmp_path / "profiles"; cache = tmp_path / "cache"
    cache.mkdir(parents=True)
    (cache / OVERRIDES_NAME).write_text(json.dumps({"旧页": {"旧key": {"skip": True}}}), encoding="utf-8")
    pack = export_pack(tmp_path / "p.zip", _profile(), _overrides()).path
    res = import_pack(pack, profiles, cache)
    rules = json.loads((cache / OVERRIDES_NAME).read_text(encoding="utf-8"))
    assert rules["旧页"]["旧key"] == {"skip": True}          # 原有规则保留
    assert rules["0-01战前"]["key1"]["record"] == 3        # 导入规则写入
    assert any("合并" in n for n in res.notes)


def test_import_target_overwrites_and_backs_up(tmp_path):
    profiles = tmp_path / "profiles"; profiles.mkdir(parents=True)
    target = profiles / "default.json"
    target.write_text(json.dumps({"format_version": 1, "name": "旧方案", "revision": 0, "entries": []}),
                      encoding="utf-8")
    pack = export_pack(tmp_path / "p.zip", _profile(), {}).path
    res = import_pack(pack, profiles, tmp_path / "cache", target=target)
    assert res.profile_path == target
    assert json.loads(target.read_text(encoding="utf-8"))["name"] == "我的方案"
    assert (profiles / "default.json.bak").is_file()  # 覆盖前留底
    assert any("bak" in n for n in res.notes)


def test_import_rejects_bad_packs(tmp_path):
    # 不是 zip
    bad = tmp_path / "bad.zip"; bad.write_text("not a zip", encoding="utf-8")
    with pytest.raises(PortableError):
        peek_pack(bad)
    # zip 但缺 manifest
    z = tmp_path / "nomani.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("hello.txt", "hi")
    with pytest.raises(PortableError):
        peek_pack(z)
    # kind 不匹配
    z2 = tmp_path / "other.zip"
    with zipfile.ZipFile(z2, "w") as zf:
        zf.writestr(MANIFEST_NAME, json.dumps({"kind": "something_else", "format_version": 1}))
    with pytest.raises(PortableError):
        peek_pack(z2)
    # 版本过新
    z3 = tmp_path / "newer.zip"
    with zipfile.ZipFile(z3, "w") as zf:
        zf.writestr(MANIFEST_NAME, json.dumps({"kind": "limbus_patcher_portable", "format_version": 99}))
    with pytest.raises(PortableError):
        peek_pack(z3)
    # 缺 profile.json
    z4 = tmp_path / "noprof.zip"
    with zipfile.ZipFile(z4, "w") as zf:
        zf.writestr(MANIFEST_NAME, json.dumps({"kind": "limbus_patcher_portable", "format_version": 1}))
    with pytest.raises(PortableError):
        import_pack(z4, tmp_path / "p", tmp_path / "c")


def test_import_rejects_invalid_profile(tmp_path):
    z = tmp_path / "bad_profile.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr(MANIFEST_NAME, json.dumps({"kind": "limbus_patcher_portable", "format_version": 1}))
        zf.writestr(PROFILE_NAME, json.dumps({"format_version": 1, "name": "x", "entries": "不是数组"}))
    with pytest.raises(PortableError) as exc:
        import_pack(z, tmp_path / "p", tmp_path / "c")
    assert "不合法" in str(exc.value)
