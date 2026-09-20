from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from limbus_patcher.backup import BackupManager
from limbus_patcher.config import AppPaths
from limbus_patcher.patch import Profile


def make_paths(tmp_path: Path) -> AppPaths:
    ap = AppPaths.from_root(tmp_path / "app")
    ap.ensure_dirs()
    return ap


def seed(ap: AppPaths):
    ap.config_path.write_text(json.dumps({"format_version": 1, "game_dir": "D:/x"}), encoding="utf-8")
    Profile().save(ap.profiles_dir / "default.json")
    (ap.history_dir / "h.jsonl").write_text("{}", encoding="utf-8")


def test_backup_and_list_and_rotate(tmp_path):
    ap = make_paths(tmp_path)
    seed(ap)
    bm = BackupManager(ap, keep=3)
    z1 = bm.backup("apply")
    assert z1 and z1.is_file()
    assert len(bm.list()) == 1 and bm.list()[0].reason == "apply"
    for _ in range(4):
        bm.backup("apply")
    assert len(bm.list()) == 3  # 轮转保留最近 3 份


def test_restore(tmp_path):
    ap = make_paths(tmp_path)
    seed(ap)
    bm = BackupManager(ap)
    z = bm.backup("startup")
    assert z
    # 破坏 profile 与 config
    (ap.profiles_dir / "default.json").write_text("garbage", encoding="utf-8")
    ap.config_path.write_text("garbage", encoding="utf-8")
    names = bm.restore(z)
    assert "profiles" in names and "config.json" in names
    assert json.loads(ap.config_path.read_text(encoding="utf-8"))["game_dir"] == "D:/x"
    p = Profile()
    p.load(ap.profiles_dir / "default.json")
    assert p.count() == 0


def test_restore_rejects_traversal(tmp_path):
    ap = make_paths(tmp_path)
    bm = BackupManager(ap)
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../evil.txt", "x")
    with pytest.raises(ValueError):
        bm.restore(evil)


def test_backup_contains_expected_parts(tmp_path):
    ap = make_paths(tmp_path)
    seed(ap)
    bm = BackupManager(ap)
    z = bm.backup("test")
    with zipfile.ZipFile(z) as zf:
        names = set(zf.namelist())
    assert "config.json" in names
    assert any(n.startswith("profiles/") for n in names)
    assert "backup_meta.json" in names
