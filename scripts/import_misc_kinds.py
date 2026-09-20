"""汇总「待确认剧情文件」的 AI 答案 → limbus_patcher/data/misc_story_kinds.json。

输入：data/misc_story/ans/*.json（与 tasks/ 下任务包同名，结构见 scripts/export_misc_tasks.py）
输出：limbus_patcher/data/misc_story_kinds.json（分类/导航读取；缺省时这些文件归「其他剧情」）

用法：
    python scripts/import_misc_kinds.py [--ans data/misc_story/ans] [--llc <零协包>] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_LLC = r"D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data/Lang/LLC_zh-CN"
OUT_PATH = ROOT / "limbus_patcher" / "data" / "misc_story_kinds.json"
KINDS = ["迷宫剧情", "集中战斗", "间章活动", "人格剧情", "主线", "其他"]
CONFIDENCE = ["high", "medium", "low"]


def normalize_answer(obj) -> tuple[list[dict], list[str]]:
    """兼容两种常见回包：{"files": [...]} 或直接是 [...]。返回 (条目, 问题列表)。"""
    problems: list[str] = []
    rows = []
    if isinstance(obj, dict):
        rows = obj.get("files") or []
        if not isinstance(rows, list):
            problems.append("files 必须是数组")
            rows = []
    elif isinstance(obj, list):
        rows = obj
    else:
        problems.append("答案必须是对象或数组")
    out = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            problems.append(f"第 {i + 1} 条不是对象")
            continue
        name = str(r.get("file") or "").strip()
        if not name:
            problems.append(f"第 {i + 1} 条缺少 file")
            continue
        kind = str(r.get("kind") or "").strip()
        if kind not in KINDS:
            problems.append(f"{name}: kind 非法（{kind!r}），已按「其他」处理")
            kind = "其他"
        # confidence 现在是可选的：豆包不再输出，缺省视为正常（不因此降级）
        conf = str(r.get("confidence") or "").strip().lower()
        if conf not in CONFIDENCE:
            conf = "high"
        out.append({
            "file": name,
            "kind": kind,
            "chapter": str(r.get("chapter") or "").strip(),
            "chapter_number": str(r.get("chapter_number") or "").strip(),
            "order": r.get("order") if isinstance(r.get("order"), int) else None,
            "confidence": conf,
            "reason": str(r.get("reason") or "").strip()[:80],
        })
    return out, problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ans", type=Path, default=ROOT / "data" / "misc_story" / "ans")
    ap.add_argument("--llc", type=Path, default=Path(DEFAULT_LLC))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ans_dir: Path = args.ans
    if not ans_dir.is_dir():
        print(f"答案目录不存在：{ans_dir}")
        print("先把 AI 的答案按任务包同名存成 data/misc_story/ans/<同名>.json")
        return 2

    known_files = {p.stem for p in (args.llc / "StoryData").glob("*.json")} if args.llc.is_dir() else set()
    kinds: dict[str, dict] = {}
    problems: list[str] = []
    files_read = 0

    for path in sorted(ans_dir.glob("*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path.name}: 读取失败（{exc}）")
            continue
        rows, probs = normalize_answer(obj)
        problems += [f"{path.name}: {p}" for p in probs]
        files_read += 1
        for row in rows:
            if known_files and row["file"] not in known_files:
                problems.append(f"{path.name}: 未知文件 {row['file']}（零协包里没有）")
                continue
            old = kinds.get(row["file"])
            if old is not None and old["confidence"] == "high" and row["confidence"] != "high":
                continue  # 保留更确定的结论
            kinds[row["file"]] = row

    if not kinds:
        print("没有解析到任何有效条目")
        for p in problems[:20]:
            print("  ⚠", p)
        return 1

    payload = {
        "format_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(ans_dir),
        "count": len(kinds),
        "kinds": kinds,
    }
    if args.dry_run:
        print(f"[dry-run] 将写入 {len(kinds)} 条 → {OUT_PATH}")
    else:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {len(kinds)} 条 → {OUT_PATH}")

    stat: dict[str, int] = {}
    for row in kinds.values():
        stat[row["kind"]] = stat.get(row["kind"], 0) + 1
    print("类型分布：" + "、".join(f"{k} {v}" for k, v in sorted(stat.items(), key=lambda x: -x[1])))
    low = [r["file"] for r in kinds.values() if r["confidence"] != "high"]
    if low:
        print(f"低置信度 {len(low)} 个：{low[:12]}{'…' if len(low) > 12 else ''}")
    if problems:
        print(f"警告 {len(problems)} 条：")
        for p in problems[:15]:
            print("  ⚠", p)
    print(f"（读取答案文件 {files_read} 个）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
