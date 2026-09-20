"""生成「人格卡图」抓取任务（给豆包 / 或人工在灰机 wiki 上找）。

每个任务包含：实体 id、中文名、协会与职位、第 N 人格、英文名、赛季，
要求返回灰机 wiki 上该人格的**卡面/立绘图片直链**（以及页面链接作为兜底）。

用法：
    python scripts/export_portrait_tasks.py [--db dist/data/cache/index.sqlite] [--out data/portraits/tasks]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BATCH = 20


def english_and_season() -> dict[int, dict]:
    path = ROOT / "limbus_patcher" / "data" / "season_map.json"
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[int, dict] = {}
    for section in ("identities", "egos"):
        for key, meta in (obj.get(section) or {}).items():
            if isinstance(meta, dict):
                try:
                    out[int(key)] = meta
                except (TypeError, ValueError):
                    continue
    return out


INSTRUCTION = [
    "【任务】在灰机 wiki（limbuscompany.huijiwiki.com）上找到下列《边狱巴士》人格/EGO 的**卡面或立绘图片**，",
    "输出图片直链。只输出 JSON，不要解释。",
    "【输出格式】",
    '{"items":[{"id":10310,"name":"堂吉诃德","page":"https://limbuscompany.huijiwiki.com/wiki/...",'
    '"image":"https://.../xxx.png","kind":"卡面","note":""}],"uncertain":[]}',
    "字段：id 用给定编号；image 给**可直接打开的图片直链**（png/jpg）；page 给图片所在页面；",
    "kind 取「卡面 / 立绘 / 头像 / 找不到」；找不到就 kind=找不到 并写 note。不要输出 confidence 之类的额外字段。",
    "注意：只给灰机 wiki 上的图（不要 fandom、不要论坛图）；图片名通常含人格名与 Full/Card/立绘 等字样。",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=ROOT / "data" / "cache" / "index.sqlite")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "portraits" / "tasks")
    ap.add_argument("--kinds", default="personality")
    args = ap.parse_args()
    if not args.db.is_file():
        print(f"找不到索引库：{args.db}")
        return 2
    kinds = []
    for k in args.kinds.split(","):
        k = k.strip().lower()
        if k in ("personality", "identity", "ident", "人格"):
            kinds.append("personality")
        elif k in ("ego", "e.g.o", "egos", "EGO"):
            kinds.append("ego")
    con = sqlite3.connect(str(args.db))
    rows = con.execute(
        "SELECT entity_id, kind, name, title, seq, sinner_name FROM entities WHERE kind IN (%s)"
        " ORDER BY sinner_code, seq" % ",".join("?" * len(kinds)), kinds).fetchall()
    con.close()
    meta = english_and_season()
    args.out.mkdir(parents=True, exist_ok=True)

    items = []
    for eid, kind, name, title, seq, sinner in rows:
        m = meta.get(eid) or {}
        items.append({
            "id": eid, "kind": "人格" if kind == "personality" else "EGO",
            "name": name, "title": (title or "").replace(chr(10), " "),
            "sinner": sinner, "seq": seq,
            "name_en": m.get("name_en") or "", "season": m.get("season_label") or m.get("acq") or "",
        })
    parts = [items[i:i + BATCH] for i in range(0, len(items), BATCH)] or [[]]
    index = []
    for i, part in enumerate(parts, start=1):
        lines = list(INSTRUCTION)
        lines.append(f"【本批】第 {i}/{len(parts)} 批，共 {len(part)} 个")
        lines.append("")
        for it in part:
            lines.append(f"- id={it['id']}｜{it['name']}｜{it['title']}｜{it['kind']}｜"
                         f"{it['sinner']} 第{it['seq']}｜英文名：{it['name_en']}｜{it['season']}")
        lines.append("")
        lines.append("请输出 JSON（每个 id 都要有结论；找不到就写 kind=找不到）。")
        name = f"portrait_{i:02d}.txt"
        (args.out / name).write_text("\n".join(lines), encoding="utf-8")
        index.append((name, len(part)))
    (args.out / "答案模板.json").write_text(json.dumps(
        {"items": [{"id": 10310, "name": "堂吉诃德", "page": "", "image": "", "kind": "卡面",
                    "note": ""}], "uncertain": []}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"生成 {len(index)} 个任务包 → {args.out}")
    for name, n in index[:3]:
        print(f"  {name}: {n} 个")
    print("  用 scripts/send_to_doubao.py --file <任务文件> 可直接交接给桌面版豆包")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
