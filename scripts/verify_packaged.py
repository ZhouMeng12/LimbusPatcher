"""打包版冷启动验证：索引 schema / 是否重复重建 / 有无崩溃日志。"""
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = next(ROOT.glob("dist/*.exe"))
DATA = ROOT / "dist" / "data"
INDEX = DATA / "cache" / "index.sqlite"
MANIFEST = DATA / "cache" / "manifest.json"
CRASH = DATA / "crash.log"


def run_once(tag: str, wait: int) -> dict:
    crash_before = CRASH.stat().st_mtime if CRASH.exists() else 0
    manifest_before = MANIFEST.stat().st_mtime if MANIFEST.exists() else 0
    proc = subprocess.Popen([str(EXE)], cwd=str(ROOT / "dist"))
    time.sleep(wait)
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                   capture_output=True, text=True)
    time.sleep(2)
    info = {
        "tag": tag,
        "manifest_changed": (MANIFEST.stat().st_mtime if MANIFEST.exists() else 0) != manifest_before,
        "manifest_at": MANIFEST.stat().st_mtime if MANIFEST.exists() else 0,
        "crash_new": (CRASH.stat().st_mtime if CRASH.exists() else 0) > crash_before,
        "alive": proc.poll() is None,
    }
    return info


def db_state() -> str:
    if not INDEX.is_file():
        return "（索引还不存在，程序首次启动会自动建立）"
    con = sqlite3.connect(f"file:{INDEX}?mode=ro", uri=True)
    try:
        ver = con.execute("PRAGMA user_version").fetchone()[0]
        ents = con.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        cols = [r[1] for r in con.execute("PRAGMA table_info(entities)")]
        roles = dict(con.execute("SELECT role, COUNT(*) FROM entries GROUP BY role"))
        cols_entries = [r[1] for r in con.execute("PRAGMA table_info(entries)")]
        return (f"schema={ver} 实体={ents} 被动列={'passive_count' in cols} "
                f"被动条目={roles.get('identity_passive')}/{roles.get('ego_passive')} "
                f"total={sum(roles.values())}")
    finally:
        con.close()


print("索引:", db_state())
first = run_once("第一次（应重建到 schema 12）", 55)
print("第一次:", first)
print("索引:", db_state())
second = run_once("第二次（不应重建）", 30)
print("第二次:", second)
print("索引:", db_state())
print("manifest 未被第二次改写:", first["manifest_at"] == second["manifest_at"])
print("无新崩溃日志:", not first["crash_new"] and not second["crash_new"])
if CRASH.exists():
    print("crash.log 尾部:", CRASH.read_text(encoding="utf-8", errors="replace")[-300:])
sys.exit(0)
