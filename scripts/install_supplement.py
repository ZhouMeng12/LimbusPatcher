"""把译好的新章节文件装成「补译文件」，随补丁一起进游戏。

用法：
    python scripts/install_supplement.py                       # 装到仓库 data/supplement（开发用）
    python scripts/install_supplement.py --data-dir dist/data   # 装到打包版旁边（exe 同目录）
    python scripts/install_supplement.py --status               # 只看现状
    python scripts/install_supplement.py --disable              # 全部停用（下次应用会从副本包移除）

来源：data/translate/out/zh/<文件>.json（由 translate_pack.py merge 产出，结构=零协包格式）
目标：<data-dir>/supplement/StoryData/<文件>.json（零协包里没有的文件才装）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from limbus_patcher.supplement import SupplementPack, validate_json_file  # noqa: E402
import llc_update  # noqa: E402  （判断零协是否已完全覆盖，避免把官方译文顶掉）

SRC = ROOT / "data" / "translate" / "out" / "zh"
#: 这些目录里的文件装到 supplement 的哪个子目录（对应零协包内路径）
ROUTE = {"S": "StoryData", "P": "StoryData", "E": "StoryData", "ES": "StoryData"}


def dest_rel(name: str) -> str | None:
    """文件名 → 零协包内相对路径。"""
    stem = name.removesuffix(".json")
    for prefix in ("ES", "S", "E", "P"):
        if stem.startswith(prefix):
            sub = ROUTE.get(prefix)
            if sub:
                return f"{sub}/{stem}.json"
    return None


def collect_files(files_dir: Path) -> list[tuple[str, Path]]:
    """data/translate/files/** → [(零协包内相对路径, 文件)]（子目录原样保留）。"""
    out: list[tuple[str, Path]] = []
    if not files_dir.is_dir():
        return out
    for p in sorted(files_dir.rglob("*.json")):
        if ".parts" in p.parts:          # 切片中间产物不是补译文件
            continue
        rel = p.relative_to(files_dir).as_posix()
        out.append((rel, p))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data")
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--files", type=Path, default=ROOT / "data" / "translate" / "files")
    ap.add_argument("--no-files", action="store_true", help="只装故事文本，不装数据文件")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--force", action="store_true", help="零协已有同名文件也照装（默认跳过）")
    ap.add_argument("--disable", action="store_true")
    args = ap.parse_args()

    pack = SupplementPack(args.data_dir)
    if args.status:
        total, on = pack.count()
        print(f"{args.data_dir}: {pack.summary()}")
        for f in pack.files():
            print(f"  [{'√' if f.enabled else ' '}] {f.rel}  {f.records} 条  {f.note}")
        return 0
    if args.disable:
        n = pack.set_all_enabled(False)
        print(f"已停用 {n} 个补译文件（下次「应用到游戏」会从副本包移除）")
        return 0

    extra = collect_files(args.files) if not args.no_files else []
    print(f"故事文本 {args.src} · 数据文件 {len(extra)} 个")
    files = sorted(args.src.glob("*.json"))
    if not files and not extra:
        print(f"没有译文可装：{args.src}")
        return 1
    added = skipped = bad = covered = 0
    for src in files:
        rel = dest_rel(src.name)
        if not rel:
            bad += 1
            continue
        state, missing = llc_update.covers(src, rel)
        if state == "full" and not args.force:
            covered += 1
            continue                      # 零协官方已有这份文件 → 不用我们的补译
        ok, err = validate_json_file(src)
        if not ok:
            print(f"  跳过 {src.name}: {err}")
            bad += 1
            continue
        data = json.loads(src.read_text(encoding="utf-8-sig"))
        note = f"新章节补译 · {len(data.get('dataList') or [])} 条"
        done, msg = pack.add(rel, src, note=note)
        if done:
            added += 1
        else:
            print(f"  {msg}")
            skipped += 1
    for rel, src in extra:                     # 数据文件（技能/状态/RPG/章节名…）原样装
        state, missing = llc_update.covers(src, rel)
        if state == "full" and not args.force:
            covered += 1
            continue
        ok, err = validate_json_file(src)
        if not ok:
            print(f"  跳过 {rel}: {err}")
            bad += 1
            continue
        done, msg = pack.add(rel, src, note="第十章数据/RPG 文本")
        if done:
            added += 1
        else:
            skipped += 1
    total, on = pack.count()
    print(f"已安装 {added} 个（跳过 {skipped}，零协已覆盖 {covered}，无效 {bad}）→ {pack.root}")
    print(f"现状：{pack.summary()}")
    print("下一步：程序里点「应用到游戏」；或在 exe 目录执行 --data-dir dist/data 后再应用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
