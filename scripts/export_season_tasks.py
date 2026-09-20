"""导出「人格/EGO 赛季与获取方式」核对补全任务包（给豆包查灰机 wiki 用）。

背景：分类/图鉴按赛季与获取方式分组，靠的是 limbus_patcher/data/season_map.json。
现有数据来自 wiki.gg（2026-08 生成），还有少量人格/EGO 没有标注；本脚本把全部人格/EGO
连同「现有标注」打包成分片文本，交给豆包对照灰机 wiki 核对并补全。

用法：
    python scripts/export_season_tasks.py [--llc <零协包>] [--out data/seasons] [--per 25]

产物：
    data/seasons/paste/01_人格.txt …    # 每一片自带提示词，整文件粘给豆包
    data/seasons/提示词.md              # 用法与字段说明
    data/seasons/答案模板.json          # 回包结构示例
答案存成 data/seasons/ans/<同名>.json，再跑 scripts/import_season_answers.py 汇总。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from limbus_patcher.entities import is_excluded_entity  # noqa: E402
from limbus_patcher.season import ACQ_LABELS, MetaMaps  # noqa: E402

DEFAULT_LLC = r"D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data/Lang/LLC_zh-CN"

INSTRUCTIONS = [
    "【任务】对照《边狱巴士》(Limbus Company) 灰机 wiki（limbuscompany.huijiwiki.com），"
    "核对下列人格 / E.G.O 的「所属赛季」与「获取方式」，只输出 JSON，不要解释。",
    "【输出格式】",
    '{"entities":[{"id":"10310","season":3,"acq":"seasonal","name_en":"The One Who Shall Grip","reason":"20字内"}]}',
    "字段说明：",
    "· id：照抄下面给出的 id（人格 5 位、E.G.O 5 位，一个都不能少）；",
    "· season：0 = 基础 / 常驻（不属于任何赛季限定）；1~7 = 第几赛季实装；拿不准写 0；",
    "· acq 取值：base=基础/常驻 · seasonal=赛季限定 · pass=通行证奖励 · event=活动赠送 · walpurgis=瓦尔普吉斯之夜；",
    "· name_en：英文名，可留空；reason：一句话依据（20 字内），不确定就写「不确定」。",
    "【注意】下面每个条目的「现标注」只作参考：与 wiki 不符时以 wiki 为准，并在 reason 里说明。",
]


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def collect(llc: Path, maps: MetaMaps) -> tuple[list[dict], list[dict]]:
    """返回 (人格条目, EGO 条目)；每条含 id / 名字 / 罪人 / 现标注。"""
    from limbus_patcher.entities import SINNER_NAMES, split_entity_id

    def meta_of(entry_id: int, kind: str) -> dict:
        return (maps.identity_meta(entry_id) if kind == "personality" else maps.ego_meta(entry_id)) or {}

    def current_label(meta: dict) -> str:
        if not meta:
            return "未标注"
        season = meta.get("season")
        acq = meta.get("acq") or "unknown"
        if season == 0:
            season_text = "基础"
        elif isinstance(season, int):
            season_text = f"第{season}赛季"
        else:
            season_text = "未标赛季"
        return f"{season_text}/{ACQ_LABELS.get(acq, acq)}"

    rows: dict[str, list[dict]] = {"personality": [], "ego": []}
    extra = sorted(p.name for p in llc.glob("Personalities-*.json")) +         sorted(p.name for p in llc.glob("Egos-*.json"))
    files = [("Personalities.json", "personality")] +         [(name, "personality") for name in extra if name.startswith("Personalities")] +         [("Egos.json", "ego")] + [(name, "ego") for name in extra if name.startswith("Egos")]
    seen: set[int] = set()
    for fname, kind in files:
        data = load(llc / fname)
        records = (data or {}).get("dataList") or []
        for rec in records:
            if not isinstance(rec, dict):
                continue
            rid = rec.get("id")
            if not isinstance(rid, int) or rid < 10000:
                continue
            if kind == "ego" and 200000 <= rid <= 299999:
                rid = rid // 10  # E.G.O 变体归到基础实体
            if rid in seen:  # 活动追加表里的重复条目
                continue
            if is_excluded_entity(kind, rid):  # 愚人节人格等：不进图鉴，也不用管赛季
                continue
            seen.add(rid)
            meta = meta_of(rid, kind)
            code, seq = split_entity_id(rid)
            desc = str(rec.get("desc") or "").replace("\n", " ")[:48]
            if code not in SINNER_NAMES:  # 活动特殊 id（4000xx）：从 desc「<罪人>的…」反查
                code = next((c for c, n in SINNER_NAMES.items() if desc.startswith(n + "的")), code)
            # 人格用 title（人格名），E.G.O 用 name（E.G.O 名）
            name = str(rec.get("title") or rec.get("name") or "").replace("\n", " ")
            rows[kind].append({
                "id": rid,
                "kind": kind,
                "name": name,
                "sinner": SINNER_NAMES.get(code, ""),
                "seq": seq,
                "current": current_label(meta),
                "reason": desc,
            })
    for kind in rows:
        rows[kind].sort(key=lambda r: (int(str(r["id"])[1:3] or 0), r["id"]))
    return rows["personality"], rows["ego"]


def shard_text(group_label: str, items: list[dict], part: int, total_parts: int) -> str:
    head = list(INSTRUCTIONS)
    head.insert(1, f"（本片：{group_label} 第 {part}/{total_parts} 片，共 {len(items)} 条）")
    lines = ["\n".join(head), "", "【数据】"]
    for it in items:
        lines.append(f'{it["id"]}｜{it["name"]}｜{it["sinner"]}｜现标注：{it["current"]}｜{it["reason"]}')
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llc", default=DEFAULT_LLC)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "seasons")
    ap.add_argument("--per", type=int, default=25)
    args = ap.parse_args()

    llc = Path(args.llc)
    if not (llc / "Personalities.json").is_file():
        print(f"零协包不可用：{llc}")
        return 1
    out: Path = args.out
    paste = out / "paste"
    paste.mkdir(parents=True, exist_ok=True)
    (out / "ans").mkdir(parents=True, exist_ok=True)

    maps = MetaMaps()
    persons, egos = collect(llc, maps)
    written: list[Path] = []
    idx = 0
    for kind, label, items in (("人格", "人格", persons), ("EGO", "E.G.O", egos)):
        parts = [items[i:i + args.per] for i in range(0, len(items), args.per)] or [[]]
        for n, chunk in enumerate(parts, start=1):
            idx += 1
            path = paste / f"{idx:02d}_{kind}.txt"
            path.write_text(shard_text(label, chunk, n, len(parts)), encoding="utf-8")
            written.append(path)

    missed = [it["id"] for it in persons + egos if it["current"] == "未标注"]
    (out / "答案模板.json").write_text(json.dumps({
        "entities": [
            {"id": "10310", "season": 3, "acq": "seasonal", "name_en": "", "reason": "第3赛季实装"}
        ]
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (out / "提示词.md").write_text(f"""# 给豆包的任务：人格 / E.G.O 赛季与获取方式核对

共 {len(persons)} 个人格 + {len(egos)} 个 E.G.O，现标注缺失 {len(missed)} 个（{", ".join(map(str, missed)) or "无"}）。
生成时间：{datetime.now():%Y-%m-%d %H:%M}

## 用法（老规矩）

1. 打开 `data/seasons/paste/` 下的某个 txt，**整文件**粘给豆包（一次一片，避免串味）；
2. 把豆包回出来的 JSON 存成 `data/seasons/ans/<同名>.json`（例如 `01_人格.txt` → `ans/01_人格.json`）；
3. 全部贴完跑 `python scripts/import_season_answers.py`（默认只补缺失，`--apply-changes` 才接受改动）；
4. 程序里「工具 → 重建文本索引」后，人格一览的「按赛季 / 按获取方式分组」就是新数据。

> 一片吃不下就说「只判断前 8 个」，分几次给，结果合并写进同一个 ans 文件即可。

## 字段

| 字段 | 说明 |
| --- | --- |
| id | 人格 5 位 / E.G.O 5 位，照抄 |
| season | 0=基础/常驻；1~7=第几赛季实装 |
| acq | base 基础 · seasonal 赛季限定 · pass 通行证 · event 活动赠送 · walpurgis 瓦尔普吉斯之夜 |
| name_en | 英文名，可空 |
| reason | 一句话依据，不确定写「不确定」 |
""", encoding="utf-8")

    print(f"已生成 {len(written)} 个分片（人格 {len(persons)} / EGO {len(egos)}）→ {paste}")
    print(f"未标注：{missed or '无'}")
    for path in written:
        print(" ", path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
