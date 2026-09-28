"""诊断 test_deploy_incremental 失败：对比两次 sync 之间源/副本的 (size, mtime_ns)。

用法：.venv/Scripts/python.exe scripts/diag_deploy_incremental.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DSH_NO_MODAL", "1")

from limbus_patcher.deploy import Deployer, _same_size_mtime  # noqa: E402
from limbus_patcher.fsutil import collect_rel_files  # noqa: E402
from limbus_patcher.paths import resolve_game_paths  # noqa: E402
from tests.test_deploy_incremental import CLONE, mk_profile  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="diag-dep-"))
game = tmp / "game"
shutil.copytree(ROOT / "tests" / "fixtures" / "game", game)
paths = resolve_game_paths(game)
dep = Deployer(tmp / "cache")
clone = paths.patch_pack_dir(CLONE)
profile = mk_profile()

print("LLC pack:", paths.llc_pack_dir)
print("clone   :", clone)
print("drive   :", str(clone)[:3])
import ctypes  # noqa: E402

buf = ctypes.create_unicode_buffer(261)
if ctypes.windll.kernel32.GetVolumeNameForVolumeMountPointW(str(clone)[:3], buf, 261):
    fs = ctypes.create_unicode_buffer(261)
    if ctypes.windll.kernel32.GetVolumeInformationW(buf.value, None, 0, None, None, None, fs, 261):
        print("fs type :", fs.value)

r1 = dep.sync_clone(paths, CLONE, profile)
print("\nfirst :", r1)

print("\n-- src vs clone (size, mtime_ns) after first sync --")
for rel, src in sorted(collect_rel_files(paths.llc_pack_dir).items()):
    dst = clone / rel
    s, d = src.stat(), dst.stat()
    flag = "OK " if (s.st_size == d.st_size and s.st_mtime_ns == d.st_mtime_ns) else "DIFF"
    print(f"{flag} {rel:40s} src=({s.st_size},{s.st_mtime_ns}) dst=({d.st_size},{d.st_mtime_ns})")

r2 = dep.sync_clone(paths, CLONE, profile)
print("\nsecond:", r2)
if r2.files_copied or r2.files_written:
    print("\n-- after 2nd sync, re-diff --")
    for rel, src in sorted(collect_rel_files(paths.llc_pack_dir).items()):
        dst = clone / rel
        s, d = src.stat(), dst.stat()
        flag = "OK " if (s.st_size == d.st_size and s.st_mtime_ns == d.st_mtime_ns) else "DIFF"
        print(f"{flag} {rel:40s} src=({s.st_size},{s.st_mtime_ns}) dst=({d.st_size},{d.st_mtime_ns})")

shutil.rmtree(tmp, ignore_errors=True)
