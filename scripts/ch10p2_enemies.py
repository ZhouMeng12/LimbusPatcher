"""把第10章第二部分（a1c10p2）的敌人写进软件的数据表。

  · limbus_patcher/data/enemy_map.json   —— id → 英文名 / 维度（敌人图鉴的骨架）
  · limbus_patcher/data/stage_enemies.json —— 第10章新增关卡 10-05 的敌人 + 并入章节级清单

英文名取自英文基线，中文名取自我们的译文（data/translate/files/Enemies-a1c10p2.json）。
有「部位」子项的（Body/Left Arm/Right Arm）按精英算，其余按普通。

    python scripts/ch10p2_enemies.py            # 写入
    python scripts/ch10p2_enemies.py --dry-run  # 只打印
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

EN_DIR = Path("D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data/Assets/Resources_moved/Localize/en")
ENEMY_MAP = ROOT / "limbus_patcher" / "data" / "enemy_map.json"
STAGE_ENEMIES = ROOT / "limbus_patcher" / "data" / "stage_enemies.json"
ZH = ROOT / "data" / "translate" / "files" / "Enemies-a1c10p2.json"

CHAPTER_ID = "c10"
STAGE_CODE = "10-4B"
STAGE_NAME = "西西弗百货·路线B"

#: 手定精英（没有部位子项但确实是首领的）
FORCE_ELITE = {1488}          # 统制者


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    zh = json.loads(ZH.read_text(encoding="utf-8"))["dataList"]
    en = json.loads((EN_DIR / "EN_Enemies-a1c10p2.json").read_text(encoding="utf-8-sig"))["dataList"]
    en_by_id = {r["id"]: r for r in en}

    parents = set()
    for r in en:
        for other in en:
            pass
    # 部位：id 是某个 id 的 100 倍 + 余数（1503 → 150301/150302/150303）
    for r in en:
        rid = str(r["id"])
        if len(rid) == 6 and rid[:4] in {str(x["id"]) for x in en}:
            parents.add(rid[:4])

    rows = []
    for r in zh:
        rid = str(r["id"])
        name_zh = (r.get("name") or "").strip()
        name_en = (en_by_id.get(r["id"], {}).get("name") or "").strip()
        if not name_zh:
            continue
        elite = (rid in parents) or (r["id"] in FORCE_ELITE)
        rows.append({
            "id": r["id"],
            "name": name_zh,
            "name_en": name_en,
            "enemy_type": "elite" if elite else "normal",
        })

    print(f"第二部分敌人 {len(rows)} 个（精英 {sum(1 for x in rows if x['enemy_type'] == 'elite')}）")
    for x in rows:
        print(f"   {x['id']:<8} {x['name']:<22} {x['name_en'][:32]:<32} {x['enemy_type']}")
    if args.dry_run:
        return 0

    # ---- enemy_map.json ----
    em = json.loads(ENEMY_MAP.read_text(encoding="utf-8"))
    enemies = em.setdefault("enemies", {})
    added = 0
    for x in rows:
        key = str(x["id"])
        if key in enemies:
            continue
        enemies[key] = {
            "group": "unit",
            "label": "敌方单位",
            "name_en": x["name_en"],
            "dimensions": {"chapter_type": "main", "enemy_type": x["enemy_type"]},
        }
        added += 1
    ENEMY_MAP.write_text(json.dumps(em, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"→ enemy_map.json 新增 {added} 条（共 {len(enemies)}）")

    # ---- stage_enemies.json ----
    se = json.loads(STAGE_ENEMIES.read_text(encoding="utf-8"))
    ch = next((c for c in se.get("chapters", []) if c.get("chapter_id") == CHAPTER_ID), None)
    if ch is None:
        raise SystemExit(f"stage_enemies.json 里没有 {CHAPTER_ID}")

    payload = [{"id": x["id"], "name": x["name"]} for x in rows]
    stages = ch.setdefault("stages", [])
    stage = next((s for s in stages if s.get("stage_code") == STAGE_CODE), None)
    if stage is None:
        stages.append({
            "stage_code": STAGE_CODE,
            "enemies": payload,
            "source": "local_chapter",
            "wiki_required": False,
            "stage_name": STAGE_NAME,
        })
        print(f"→ stage_enemies.json 新增关卡 {STAGE_CODE}（{len(payload)} 个敌人）")
    else:
        stage["enemies"] = payload
        stage["stage_name"] = STAGE_NAME
        print(f"→ stage_enemies.json 更新关卡 {STAGE_CODE}（{len(payload)} 个敌人）")

    known = {e["id"] for e in ch.get("chapter_enemies", [])}
    ch.setdefault("chapter_enemies", []).extend([e for e in payload if e["id"] not in known])
    print(f"→ 第10章章节级敌人 {len(ch['chapter_enemies'])} 个")
    STAGE_ENEMIES.write_text(json.dumps(se, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
