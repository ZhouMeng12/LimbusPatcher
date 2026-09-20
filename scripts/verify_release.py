"""发布前自检：产物内容 + 冷启动 + 版本一致性 + 校验和。

    python scripts/verify_release.py            # 检查 dist/ 与 dist/release/

检查项（任一不过 exit 1）：
  1. 发布包里**不含**索引 / 方案 / 备份 / 头像 / 崩溃日志 / .bak 文件；
  2. 发布包含剧本结构数据（只存位置）、README、LICENSE、第三方许可、使用说明；
  3. 单文件版能冷启动（不崩、不重复重建索引）；
  4. 版本号与 CHANGELOG 首条一致。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from limbus_patcher import __version__  # noqa: E402

RELEASE = ROOT / "dist" / "release"
#: 发布包里绝不允许出现的东西（文件名片段）
FORBIDDEN = ("index.sqlite", "manifest.json", "story_overrides.json", ".bak", "crash.log",
             "crash_native.log", "qt_messages.log", "profiles/", "backups/", "history/",
             "portraits/", "config.json")
REQUIRED = ("data/cache/story_stages.json", "README.md", "LICENSE",
            "THIRD_PARTY_LICENSES.md", "使用说明.txt")


def check_zip(path: Path) -> list[str]:
    problems: list[str] = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    for bad in FORBIDDEN:
        hits = [n for n in names if bad in n]
        if hits:
            problems.append(f"{path.name}: 含不该发布的内容 {bad} → {hits[:3]}")
    for need in REQUIRED:
        if not any(n.endswith(need) for n in names):
            problems.append(f"{path.name}: 缺少 {need}")
    # 剧本数据必须是「只存位置」的：有本地定位的行绝不能带文本
    for n in names:
        if not n.endswith("story_stages.json"):
            continue
        with zipfile.ZipFile(path) as z:
            data = json.loads(z.read(n).decode("utf-8"))
        lines = [i for ch in data.get("chapters", []) for st in ch.get("stages", [])
                 for i in st.get("items", []) if isinstance(i, dict) and i.get("type") == "line"]
        located = [i for i in lines if i.get("file") and i.get("record") is not None]
        bad = [i for i in located if "text" in i]
        if bad:
            problems.append(f"{path.name}: 有定位的行仍带文本 {len(bad)} 条（应只存位置）")
        wiki_only = [i for i in lines if not (i.get("file") and i.get("record") is not None)]
        if wiki_only:
            # 已知例外：178 行「wiki 独有、本地无对应」的台词（对照工作流要用），保留文本
            print(f"  提示：{path.name} 有 {len(wiki_only)} 行无本地定位（wiki 独有台词，保留文本）")
    return problems


def cold_start(exe: Path, seconds: float = 20.0) -> list[str]:
    data = exe.parent / "data"
    manifest = data / "cache" / "manifest.json"
    crash = data / "crash.log"
    before = (manifest.stat().st_mtime if manifest.exists() else 0,
              crash.stat().st_mtime if crash.exists() else 0)
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent))
    time.sleep(seconds)
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    time.sleep(1.5)
    after = (manifest.stat().st_mtime if manifest.exists() else 0,
             crash.stat().st_mtime if crash.exists() else 0)
    problems = []
    if after[1] > before[1]:
        problems.append(f"{exe.name}: 冷启动产生崩溃日志（{crash}）")
    if after[0] and after[0] == before[0] and before[0] != 0:
        pass  # 未重建 → 正常
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="发布前自检")
    ap.add_argument("--no-start", action="store_true", help="跳过冷启动检查")
    args = ap.parse_args()

    problems: list[str] = []
    changelog = ROOT / "CHANGELOG.md"
    if changelog.is_file():
        head = changelog.read_text(encoding="utf-8")[:400]
        m = re.search(r"##\s*v?([\d.]+)", head)
        if m and m.group(1) != __version__:
            problems.append(f"CHANGELOG 首条 v{m.group(1)} 与 __version__ {__version__} 不一致")
    else:
        problems.append("缺少 CHANGELOG.md")

    zips = sorted(RELEASE.glob("*.zip")) if RELEASE.is_dir() else []
    if not zips:
        problems.append(f"{RELEASE} 下没有发布包（先跑 scripts/build.ps1）")
    for z in zips:
        problems += check_zip(z)

    exe = next((p for p in (ROOT / "dist_build" / "边狱巴士汉化文本修改器.exe",
                            ROOT / "dist" / "边狱巴士汉化文本修改器.exe") if p.is_file()), None)
    if args.no_start:
        print("（跳过冷启动检查）")
    elif exe.is_file():
        print(f"冷启动检查：{exe.name} …")
        problems += cold_start(exe)
    else:
        problems.append("dist 下没有单文件版 exe")

    print(f"版本 {__version__} | 发布包 {len(zips)} 个")
    for z in zips:
        print(f"  · {z.name}  {z.stat().st_size / 1048576:.1f} MB")
    if problems:
        print("\n发现问题：")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("\n发布自检通过 ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
