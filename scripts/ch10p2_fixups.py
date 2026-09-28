"""第10章第二部分（a1c10p2）答案统一修正：用词对齐 + 几处硬伤。

    python scripts/ch10p2_fixups.py --dry-run   # 只看会改什么
    python scripts/ch10p2_fixups.py             # 写回 ans/

用词一律「零协实际用词 > 术语表 > 本次定名」，并且**只在英文原文确实出现该词时**才替换
（避免把「喷泉」这种同形而不同义的词一并改掉：the Fount=泉 / the fountain=苏打喷泉）。
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "translate" / "ch10p2"
TASKS, ANS = WORK / "tasks", WORK / "ans"

#: (英文触发正则, 旧写法, 新写法, 说明)
RULES: list[tuple[str, str, str, str]] = [
    (r"Golden Hide", "黄金之皮", "黄金皮革", "零协用「黄金皮革」"),
    (r"\bstrangers?\b", "陌生人", "异乡人", "零协与路线A用「异乡人」"),
    (r"\bShore\b", "海滨", "海岸", "零协用「海岸」"),
    (r"\bFount\b", "喷泉", "泉", "the Fount=泉（零协）；苏打喷泉另算"),
    (r"\bFount\b", "源泉", "泉", "同上"),
    (r"Maison du Noir", "黑派公馆", "黑派品牌世家", "零协用「黑派品牌世家」"),
    (r"Key Mapping", "按键设置", "快捷键", "零协用「快捷键」"),
    (r"Sapsaree|삽살", "萨普萨犬", "萨普萨里", "统一音译"),
    (r"Wriggley|Wriggle|Wriggly", "扭扭", "里格利", "零协「扭扭」指噗扭扭，本体用里格利"),
    (r"Needlekin", "针族劳工", "针族工人", "零协用「针族工人」"),
]

#: 逐条手工修正（键 = 批次/文件#下标）
MANUAL: dict[str, str] = {
    # 说明字段里 EN 没写方括号 → 译文也不该有
    "batch_004/BattleKeywords-a1c10p2.json#20":
        "- 移除全部混乱阈值\n- 拼点威力+2\n- 受到来自忧郁的理智值伤害-50%（向下取整）\n"
        "- 回合结束：恢复10点理智值，且下回合获得5层迅捷\n"
        "- <color=#ff6000><mark color=#ff000040><b><u>拼点胜利：为该单位及援助单位在内的所有友方恢复5点理智值</color></mark></b></u>",
    # 原答案给成了名称，整条漏译
    "batch_005/Passives_Abnormality-a1c10p2.json#57":
        "首次进入交战时，获得5层[NoirBindArmor]\n\n"
        "回合开始：获得等同于（[NoirBindArmor]层数）%该单位最大体力的护盾\n\n"
        "陷入混乱时，失去全部[NoirBindArmor]\n"
        "回合开始：该单位从混乱中恢复时，获得5层[NoirBindArmor]",
    # EN 结尾有换行，译文漏了
    "batch_006/Passives_Abnormality-a1c10p2.json#110": None,  # 由下面 append_nl 处理
    # 效果 id 被译错 + 多译了半句
    "batch_006/Passives_Abnormality-a1c10p2.json#118":
        "该单位的等级因刺痛阳光之雨的影响而提升\n\n交战开始：获得[SapsareeGold]",
    # 漏了整段标签 + 漏掉一行原文
    "batch_007/Skills_Abnormality-a1c10p2.json#171": None,  # 由 prepend 处理
    # 前两行的加粗下划线包裹丢了
    "batch_007/Skills_Abnormality-a1c10p2.json#189": None,  # 由 wrap_head 处理
}

SKILL171_HEAD = ("<color=#ff6000><mark=#ff000040><b><u>无视速度值与本技能拼点</u></b></mark></color>\n")
SKILL189_OPEN = "<color=#ff6000><mark=#ff000040><b><u>"
SKILL189_CLOSE = "</u></b></mark></color>"


def fix_one(batch: str, key: str, en: str, zh: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    for pat, old, new, why in RULES:
        if old in zh and re.search(pat, en, re.I):
            n = zh.count(old)
            zh = zh.replace(old, new)
            notes.append(f"{old}→{new}×{n}（{why}）")
    full = f"{batch}/{key}"
    if full in MANUAL and MANUAL[full]:
        zh = MANUAL[full]
        notes.append("手工修正整条")
    if full == "batch_006/Passives_Abnormality-a1c10p2.json#110" and en.endswith("\n") and not zh.endswith("\n"):
        zh += "\n"
        notes.append("补回结尾换行")
    if full == "batch_007/Skills_Abnormality-a1c10p2.json#171" and "无视速度值与本技能拼点" not in zh:
        zh = SKILL171_HEAD + zh
        notes.append("补回「无视速度值与本技能拼点」整行")
    if full == "batch_007/Skills_Abnormality-a1c10p2.json#189":
        head = "[CantChangeTarget]\n目标为[TailoringTarget]"
        if zh.startswith(head) and not zh.startswith(SKILL189_OPEN):
            zh = SKILL189_OPEN + head + SKILL189_CLOSE + zh[len(head):]
            notes.append("补回前两行的加粗下划线包裹")
    return zh, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    stat: Counter = Counter()
    for tp in sorted(TASKS.glob("batch_*.json")):
        batch = json.loads(tp.read_text(encoding="utf-8"))
        apath = ANS / tp.name
        ans = json.loads(apath.read_text(encoding="utf-8-sig"))
        changed = 0
        for it in batch["items"]:
            key = it["ids"][0]
            zh = ans.get(key)
            if not isinstance(zh, str) or not zh.strip():
                continue
            new_zh, notes = fix_one(tp.stem, key, it["en"], zh)
            if new_zh != zh:
                ans[key] = new_zh
                changed += 1
                stat["改动条目"] += 1
                for n in notes:
                    stat[n.split("（")[0]] += 1
        if changed and not args.dry_run:
            apath.write_text(json.dumps(ans, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"{tp.stem}: 改动 {changed} 条")
    print(f"\n合计改动 {stat['改动条目']} 条")
    for k, v in stat.most_common():
        if k != "改动条目":
            print(f"   {v:4d}  {k}")
    if args.dry_run:
        print("[dry-run] 未写入")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
