"""把第10章第二部分（路线B）的分段方案写进编排表 + story_stages 骨架。

    python scripts/ch10p2_plan.py            # 写入
    python scripts/ch10p2_plan.py --dry-run  # 只检查文件是否都存在

编排表是唯一事实源；写完跑 scripts/build_story_rpg.py --stage 10-05 重建剧本数据。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

PLAN = ROOT / "limbus_patcher" / "data" / "story_rpg_plan.json"
STAGES = ROOT / "limbus_patcher" / "data" / "story_stages.json"
EN = Path("D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data/Assets/Resources_moved/Localize/en")

STAGE_CODE = "10-4B"

#: （分支号, label, kind, kind_label, confidence, evidence, 文件列表）
BRANCHES = [
    ("b01", "01 序章·再次坠落", "story", "过场", "high",
     "S1017B 开头即「按下按钮后视野才清晰起来 → 坠入水中」，是路线 B 的开场，对应 Q1000",
     ["StoryData/S1017B.json"]),
    ("b02", "02 1F·美妆馆", "rpg", "RPG 楼层", "high",
     "S1018B 的 place 标记为 1F 美妆馆；任务 Q1000–Q1064（Q1064 转 2F、杜布瓦现身）",
     ["RPGSystem/rpg-loc-dialogue-floor-1-b.json",
      "RPGSystem/rpg-loc-dialogue-choice-floor-1-b.json",
      "StoryData/S1018B.json"]),
    ("b03", "03 2F·奢侈品馆与摇篮", "rpg", "RPG 楼层", "high",
     "S1021B 的 place 标记为 2F 奢侈品馆；任务 Q2001–Q2010（摇篮救出普伊后转 4F）",
     ["RPGSystem/rpg-loc-dialogue-floor-2-b.json",
      "StoryData/S1021B.json"]),
    ("b04", "04 3F·品牌世家", "rpg", "RPG 楼层", "medium",
     "S1019B（3F 走廊）、S1020B（3F 改衣室）place 均为 3F；任务 Q3001–Q3028。段内有「黑派支线 → 回 2F → 再回 3F」的回环，需进游戏确认穿插",
     ["RPGSystem/rpg-loc-dialogue-floor-3-b.json",
      "RPGSystem/rpg-loc-dialogue-choice-floor-3-b.json",
      "RPGSystem/rpg-loc-narration-floor-3-b.json",
      "StoryData/S1019B.json",
      "StoryData/S1020B.json"]),
    ("b05", "05 4F·家具馆与制鞋", "rpg", "RPG 楼层", "high",
     "S1022B/S1023B/S1024B/S1025B 的 place 均为 4F；任务 Q4001–Q4026（普伊的鞋 + 卡门的墙语）",
     ["RPGSystem/rpg-loc-dialogue-floor-4-b.json",
      "RPGSystem/rpg-loc-dialogue-choice-floor-4-b.json",
      "StoryData/S1022B.json",
      "StoryData/S1023B.json",
      "StoryData/S1024B.json",
      "StoryData/S1025B.json"]),
    ("b06", "06 5F·初入与帐幕", "rpg", "RPG 楼层", "high",
     "Q4026 转 5F；Q5001–Q5002 说威望不足、要先去地下楼层取黄金寿衣。S1026B 的 place 为餐厅 5F",
     ["RPGSystem/rpg-loc-dialogue-floor-5-b.json",
      "StoryData/S1026B.json"]),
    ("b07", "07 B1F·美食广场", "rpg", "RPG 楼层", "high",
     "Q5002 转地下楼层；任务 Q-1000–Q-1011（幼虫 → 屠夫 → 扶梯厅转 B2F）。B1F 无专属过场",
     ["RPGSystem/rpg-loc-dialogue-floor-b1-b.json",
      "RPGSystem/rpg-loc-dialogue-choice-floor-b1-b.json"]),
    ("b08", "08 B2F·纺丝场", "rpg", "RPG 楼层", "high",
     "S1027B 的 place 为 B2F 线团之巢；任务 Q-2000–Q-2010A（去 B3F 扶梯）",
     ["RPGSystem/rpg-loc-dialogue-floor-b2-b.json",
      "RPGSystem/rpg-loc-dialogue-choice-floor-b2-b.json",
      "StoryData/S1027B.json"]),
    ("b09", "09 B3F·鞣皮室与统制者", "rpg", "RPG 楼层", "medium",
     "S1028B 的 place 为鞣皮室 B3F；任务 Q-3000–Q-3005（击杀统制者后回 5F）。warden-boss 两文件暂归本段，若实为 5F 终盘请移到 b10",
     ["RPGSystem/rpg-loc-dialogue-floor-b3-b.json",
      "RPGSystem/rpg-loc-npc-route-b-warden.json",
      "RPGSystem/rpg-loc-npc-common-warden-boss-a1c10p2.json",
      "RPGSystem/rpg-loc-narration-common-warden-boss-a1c10p2.json",
      "StoryData/S1028B.json"]),
    ("b10", "10 5F·终盘·自助餐", "story", "过场", "high",
     "Q-3002 回 5F → Q5005/Q5010；S1029B（place 餐厅 5F）普伊成王/神。S9992B「西西弗百货必须被消费」无 place 标记，按内容推断归入终盘，把握 low",
     ["RPGSystem/rpg-loc-dialogue-route-b.json",
      "RPGSystem/rpg-loc-player-route-b.json",
      "RPGSystem/rpg-loc-npc-route-b.json",
      "StoryData/S1029B.json",
      "StoryData/S9992B.json"]),
    ("b11", "11 通用互动台词（跨楼层复用）", "common", "通用互动", "high",
     "路线 B 的通用对话/名称/道具/UI，跨楼层复用；与第一部分 b10 同样单独成段置底",
     ["RPGSystem/rpg-loc-dialogue-common-a1c10p2.json",
      "RPGSystem/rpg-loc-npc-common-a1c10p2.json",
      "RPGSystem/rpg-loc-item-common-a1c10p2.json",
      "RPGSystem/rpg-loc-ui-common-a1c10p2.json"]),
    ("b12", "12 杜布瓦人格剧情", "story", "人格剧情", "medium",
     "P10917 说话人杜布瓦，属人格/EGO 解锁剧情不属主线；杜布瓦在 1F（Q1064）现身，但置底最稳妥",
     ["StoryData/P10917.json"]),
]

QUEST_FILES = [
    "RPGSystem/rpg-loc-quest-floor-1-b.json",
    "RPGSystem/rpg-loc-quest-floor-2-b.json",
    "RPGSystem/rpg-loc-quest-floor-3-b.json",
    "RPGSystem/rpg-loc-quest-floor-4-b.json",
    "RPGSystem/rpg-loc-quest-floor-5-b.json",
    "RPGSystem/rpg-loc-quest-floor-b1-b.json",
    "RPGSystem/rpg-loc-quest-floor-b2-b.json",
    "RPGSystem/rpg-loc-quest-floor-b3-b.json",
]


def exists(rel: str) -> bool:
    p = EN / rel
    return (p.parent / f"EN_{p.name}").is_file() or p.is_file()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    missing = [f for _b in BRANCHES for f in _b[6] if not exists(f)]
    missing += [f for f in QUEST_FILES if not exists(f)]
    if missing:
        print("英文基线里找不到这些文件，已从清单剔除：")
        for m in missing:
            print("   -", m)
    drop = set(missing)

    stage = {
        "mode": "rpg",
        "label": "西西弗百货·路线B（RPG 关卡）",
        "source": "我方补译（零协无 c10p2；RPG 分支按玩家游玩顺序）",
        "story_dir": "StoryData",
        "rpg_dir": "RPGSystem",
        "quest_files": [f for f in QUEST_FILES if f not in drop],
        "branches": [
            {"id": bid, "label": label, "kind": kind, "kind_label": klabel,
             "confidence": conf, "evidence": ev,
             "parts": [{"file": f} for f in files if f not in drop]}
            for bid, label, kind, klabel, conf, ev, files in BRANCHES
        ],
    }

    print(f"关卡 {STAGE_CODE}：{len(stage['branches'])} 段")
    for b in stage["branches"]:
        print(f"   {b['id']} {b['label']:26s} {b['confidence']:6s} {len(b['parts'])} 个文件")
    if args.dry_run:
        return 0

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan.setdefault("stages", {})[STAGE_CODE] = stage
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"→ 编排表已写入 {PLAN}")

    data = json.loads(STAGES.read_text(encoding="utf-8"))
    for ch in data.get("chapters", []):
        if ch.get("chapter_id") != "c10":
            continue
        if any(s.get("stage_code") == STAGE_CODE for s in ch.get("stages", [])):
            print(f"story_stages.json 里已有 {STAGE_CODE}")
            break
        ch.setdefault("stages", []).append({
            "stage_code": STAGE_CODE,
            "pages": [],
            "items": [],
            "mode": "rpg",
            "branch_source": "plan",
            "branches": [],
        })
        STAGES.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"→ story_stages.json 已加 {STAGE_CODE} 骨架")
        break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
