"""汇总豆包的「赛季 / 获取方式」答案 → limbus_patcher/data/season_map.json。

输入：data/seasons/ans/*.json（与 paste/ 下分片同名，结构见 scripts/export_season_tasks.py）
输出：limbus_patcher/data/season_map.json（分类/图鉴按赛季与获取方式分组读取）
      data/seasons/变更报告.md（补全 / 改动 / 未识别清单）

默认**只补缺失**（现有 season/acq 为空的条目），`--apply-changes` 才接受与现有不同的答案
（现有数据来自 wiki.gg，改动一律写进报告便于复核）。

用法：
    python scripts/import_season_answers.py [--ans data/seasons/ans] [--llc <零协包>] [--dry-run] [--apply-changes]
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
OUT_PATH = ROOT / "limbus_patcher" / "data" / "season_map.json"
ACQ_VALUES = {"base", "seasonal", "pass", "event", "walpurgis", "unknown"}


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  ! {path.name} 不可读：{exc}")
        return None


def known_ids(llc: Path) -> tuple[set[int], set[int]]:
    """(人格 id, E.G.O id)——以零协包为准，答案里多出来的 id 一律忽略。"""
    persons: set[int] = set()
    egos: set[int] = set()
    for path in sorted(llc.glob("Personalities*.json")):
        for rec in (load(path) or {}).get("dataList") or []:
            if isinstance(rec, dict) and isinstance(rec.get("id"), int) and rec["id"] >= 10000:
                persons.add(rec["id"])
    for path in sorted(llc.glob("Egos*.json")):
        for rec in (load(path) or {}).get("dataList") or []:
            rid = rec.get("id") if isinstance(rec, dict) else None
            if isinstance(rid, int) and rid >= 10000:
                egos.add(rid // 10 if 200000 <= rid <= 299999 else rid)
    return persons, egos


def rows_of(obj) -> list[dict]:
    """兼容 {"entities":[...]} / {"files":[...]} / 直接数组 三种回包。"""
    if isinstance(obj, dict):
        for key in ("entities", "files", "rows", "data", "items"):
            rows = obj.get(key)
            if isinstance(rows, list):
                return rows
        return []
    return obj if isinstance(obj, list) else []


def normalize(obj, persons: set[int], egos: set[int], problems: list[str]) -> dict[str, dict]:
    """回包 → {id: {"season": int|None, "acq": str, "name_en": str, "reason": str}}。"""
    out: dict[str, dict] = {}
    for i, row in enumerate(rows_of(obj)):
        if not isinstance(row, dict):
            problems.append(f"第 {i + 1} 条不是对象")
            continue
        raw_id = str(row.get("id") or "").strip()
        if not raw_id.isdigit():
            problems.append(f"第 {i + 1} 条 id 非法：{raw_id!r}")
            continue
        rid = int(raw_id)
        if rid in egos:
            key, kind = ("egos", rid)
        elif rid in persons:
            key, kind = ("identities", rid)
        else:
            problems.append(f"id {rid} 不在零协包里，已忽略")
            continue
        season = row.get("season")
        if isinstance(season, str) and season.strip().isdigit():
            season = int(season.strip())
        if season is not None and not isinstance(season, int):
            problems.append(f"{rid}: season 非法（{season!r}），按未标注处理")
            season = None
        if isinstance(season, int) and not 0 <= season <= 9:
            problems.append(f"{rid}: season 超出 0~9（{season}），按未标注处理")
            season = None
        acq = str(row.get("acq") or "").strip().lower()
        if acq not in ACQ_VALUES:
            if acq:
                problems.append(f"{rid}: acq 非法（{acq!r}），按 unknown 处理")
            acq = "unknown"
        out[str(rid)] = {
            "bucket": key,
            "season": season,
            "acq": acq,
            "name_en": str(row.get("name_en") or "").strip(),
            "reason": str(row.get("reason") or "").strip()[:60],
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ans", type=Path, default=ROOT / "data" / "seasons" / "ans")
    ap.add_argument("--llc", default=DEFAULT_LLC)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply-changes", action="store_true",
                    help="接受与现有标注不同的答案（默认只补缺失）")
    ap.add_argument("--deploy", type=Path, default=None,
                    help="同时铺到便携目录：<DIR>/data/cache/season_map.json（DIR 通常是 exe 所在目录）")
    args = ap.parse_args()

    llc = Path(args.llc)
    if not (llc / "Personalities.json").is_file():
        print(f"零协包不可用：{llc}")
        return 1
    ans_files = sorted(p for p in Path(args.ans).glob("*.json") if p.name != "答案模板.json")
    if not ans_files:
        print(f"还没有答案：把豆包回出来的 JSON 存到 {args.ans}/<分片同名>.json")
        return 1

    persons, egos = known_ids(llc)
    answers: dict[str, dict] = {}
    problems: list[str] = []
    for path in ans_files:
        obj = load(path)
        if obj is None:
            continue
        got = normalize(obj, persons, egos, problems)
        answers.update(got)
        print(f"  {path.name}: {len(got)} 条")

    current = load(args.out) or {}
    current.setdefault("identities", {})
    current.setdefault("egos", {})
    filled, changed, kept = [], [], 0
    for rid, ans in sorted(answers.items(), key=lambda kv: int(kv[0])):
        bucket = current[ans["bucket"]]
        old = bucket.get(rid) or {}
        old_season, old_acq = old.get("season"), old.get("acq")
        missing = old_season is None or old_acq in (None, "", "unknown")
        same = (old_season == ans["season"] and old_acq == ans["acq"])
        if same:
            kept += 1
            continue
        if not missing and not args.apply_changes:
            kept += 1
            continue
        entry = dict(old)
        entry["season"] = ans["season"]
        entry["acq"] = ans["acq"]
        if ans["name_en"]:
            entry["name_en"] = ans["name_en"]
        entry["source"] = "doubao/huiji"
        if ans["reason"]:
            entry["note"] = ans["reason"]
        bucket[rid] = entry
        (filled if missing else changed).append(
            f"{rid} {entry.get('name_en') or ''}".strip()
            + f"：{old_season}/{old_acq or '未标注'} → {ans['season']}/{ans['acq']}"
            + (f"（{ans['reason']}）" if ans["reason"] else ""))

    total = len(persons) + len(egos)
    labeled = sum(1 for b in ("identities", "egos") for v in current[b].values()
                  if v.get("season") is not None or v.get("acq") not in (None, "", "unknown"))
    print(f"\n答案条目 {len(answers)} 条：补全 {len(filled)} · 改动 {len(changed)} · 一致/跳过 {kept}")
    print(f"标注进度：{labeled}/{total}（{round(labeled * 100 / total)}%）")
    if problems:
        print(f"回包问题 {len(problems)} 处（前 8 条）：")
        for p in problems[:8]:
            print("  ·", p)
    if args.dry_run:
        print("（--dry-run：没有写文件）")
        return 0

    current["generated_at"] = datetime.now().isoformat(timespec="seconds")
    current["source"] = (str(current.get("source") or "https://limbuscompany.wiki.gg/api.php")
                         + " + 豆包/灰机核对补全")
    args.out.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = ROOT / "data" / "seasons" / "变更报告.md"
    report.write_text(
        f"# 赛季 / 获取方式 变更报告（{datetime.now():%Y-%m-%d %H:%M}）\n\n"
        f"- 答案文件：{len(ans_files)} 个\n- 标注进度：{labeled}/{total}（{round(labeled * 100 / total)}%）\n"
        f"- 补全 {len(filled)} 条\n- 改动 {len(changed)} 条（需要 `--apply-changes`）\n\n"
        + "## 补全\n" + "\n".join(f"- {x}" for x in filled or ["（无）"])
        + "\n\n## 改动\n" + "\n".join(f"- {x}" for x in changed or ["（无）"])
        + "\n\n## 回包问题\n" + "\n".join(f"- {x}" for x in problems or ["（无）"]) + "\n",
        encoding="utf-8")
    print(f"已写入 {args.out}\n报告：{report}")
    if args.deploy:
        target = Path(args.deploy) / "data" / "cache" / "season_map.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(args.out.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"已铺到便携目录：{target}（程序里「重建文本索引」后生效）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
