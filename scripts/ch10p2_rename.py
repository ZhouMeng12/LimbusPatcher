"""两件收尾：①第10章 RPG 关卡改号 10-04/10-05 → 10-4A/10-4B；②第一部分敌人名统一成零协用词。

    python scripts/ch10p2_rename.py --dry-run
    python scripts/ch10p2_rename.py

改动面：
  limbus_patcher/data/story_stages.json      stage_code
  limbus_patcher/data/story_rpg_plan.json   关卡键 + label
  limbus_patcher/data/stage_enemies.json    stage_code + 第一部分敌人中文名
  data/wiki_story/story_stages.json         stage_code（运行时副本）
  dist/data/cache/story_stages.json         stage_code（运行时副本）
  data/config.json                          ui.script_stage（上次看的关卡）
  tests/test_story_rpg.py                   用例里的关卡号
敌人名统一：零协 Enemies-a1c10p1.json 为准（零协实际用词 > wiki 来源）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GAME = Path("D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data")
LLC_ENEMIES_P1 = GAME / "Lang" / "LLC_zh-CN" / "Enemies-a1c10p1.json"

RENAME = {"10-04": "10-4A", "10-05": "10-4B"}
LABELS = {
    "10-4A": "10-4A 西西弗百货·路线A",
    "10-4B": "10-4B 西西弗百货·路线B",
}
PLAN_LABELS = {
    "10-4A": "西西弗百货·路线A（RPG 关卡）",
    "10-4B": "西西弗百货·路线B（RPG 关卡）",
}

JSON_TARGETS = [
    "limbus_patcher/data/story_stages.json",
    "limbus_patcher/data/story_rpg_plan.json",
    "limbus_patcher/data/stage_enemies.json",
    "data/wiki_story/story_stages.json",
    "dist/data/cache/story_stages.json",
    "data/config.json",
]
TEXT_TARGETS = ["tests/test_story_rpg.py"]


def rename_in_json(node, count: dict):
    if isinstance(node, dict):
        code = node.get("stage_code")
        if isinstance(code, str) and code in RENAME:
            node["stage_code"] = RENAME[code]
            count[code] = count.get(code, 0) + 1
        for k, v in list(node.items()):
            if isinstance(k, str) and k in RENAME and isinstance(v, (dict, list)):
                node[RENAME[k]] = node.pop(k)
                count[f"key:{k}"] = count.get(f"key:{k}", 0) + 1
            rename_in_json(v, count)
    elif isinstance(node, list):
        for v in node:
            rename_in_json(v, count)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    total: dict = {}

    # ---------- 1) 关卡改号 ----------
    for rel in JSON_TARGETS:
        p = ROOT / rel
        if not p.is_file():
            print(f"  （跳过，文件不存在）{rel}")
            continue
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        cnt: dict = {}
        rename_in_json(data, cnt)
        # 编排表 / 关卡名的 label
        stages = data.get("stages")
        if isinstance(stages, dict):
            for old, new in RENAME.items():
                if new in stages:
                    if stages[new].get("label"):
                        stages[new]["label"] = PLAN_LABELS[new]
                        cnt["label"] = cnt.get("label", 0) + 1
        if not cnt:
            continue
        print(f"  {rel}: {cnt}")
        total[rel] = cnt
        if not args.dry_run:
            p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    for rel in TEXT_TARGETS:
        p = ROOT / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        new = text
        for old, nw in RENAME.items():
            new = new.replace(old, nw)
        if new == text:
            continue
        n = sum(text.count(o) for o in RENAME)
        print(f"  {rel}: 文本替换 {n} 处")
        total[rel] = n
        if not args.dry_run:
            p.write_text(new, encoding="utf-8")

    # dist/data/cache 的 stage_enemies / enemy_map 后面单独同步
    # ---------- 2) 敌人名统一 ----------
    llc = json.loads(LLC_ENEMIES_P1.read_text(encoding="utf-8-sig"))["dataList"]
    llc_name = {r["id"]: (r.get("name") or "").strip() for r in llc if r.get("name")}
    se_path = ROOT / "limbus_patcher" / "data" / "stage_enemies.json"
    se = json.loads(se_path.read_text(encoding="utf-8"))
    changed = []
    for ch in se.get("chapters", []):
        if ch.get("chapter_id") != "c10":
            continue
        for bucket in (ch.get("chapter_enemies", []),):
            for e in bucket:
                want = llc_name.get(e["id"])
                if want and want != e["name"]:
                    changed.append((e["id"], e["name"], want))
                    e["name"] = want
        for st in ch.get("stages", []):
            for e in st.get("enemies", []):
                want = llc_name.get(e["id"])
                if want and want != e["name"]:
                    changed.append((e["id"], e["name"], want))
                    e["name"] = want
        for st in ch.get("stages", []):
            if st.get("stage_code") in LABELS and not st.get("stage_name"):
                st["stage_name"] = LABELS[st["stage_code"]]
    print(f"\n敌人名统一 {len(changed)} 处：")
    for i, old, new in changed:
        print(f"   {i:<8} {old[:20]:<22} → {new}")
    if not args.dry_run:
        se_path.write_text(json.dumps(se, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        for rel in ("dist/data/cache/stage_enemies.json",):
            (ROOT / rel).write_text(json.dumps(se, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("→ stage_enemies.json 已写（含 dist/data/cache 副本）")

    if args.dry_run:
        print("\n[dry-run] 未写入")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
