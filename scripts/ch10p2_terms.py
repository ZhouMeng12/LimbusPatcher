"""生成第10章第二部分的术语表（给翻译用的对照文件）。

来源优先级：零协包实际用词 > 术语表/审定新词 > 本次人工定名。
产出：
  data/translate/ch10p2/术语表.md          —— 规则 + 本次定名（给人看）
  data/translate/ch10p2/术语对照.json      —— 「英文 → 中文」机器可读（给 AI 批次翻译用）
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import ch10p2_prep as P  # noqa: E402

WORK = ROOT / "data" / "translate" / "ch10p2"
GLOSSARY = ROOT / "data" / "translate" / "glossary.json"
DECIDED = ROOT / "data" / "translate" / "审定新词.json"

#: 本次（第二部分）人工定名：零协没翻过的，按韩文原意 / 与第一部分保持一致来定
MANUAL = {
    # —— 角色 ——
    "Pwie": "普伊",
    "Pwie?": "普伊？",
    "Pwuh...": "噗……",
    "Pwuh-Pwuhie...": "噗——噗伊……",
    "Overseer": "统制者",
    "The Overseer": "统制者",
    "Nurturer": "养育者",
    "Scraper": "刮削者",
    "Fisherman": "渔夫",
    "Tanner": "鞣皮师",
    "Tannery": "鞣皮室",
    "Renée": "勒妮",
    "The Nascent Crimson God": "新生的赤红之神",
    "Blackthread of the Elden Sea": "古海的黑之丝",
    "The Designer's Chef D'oeuvre": "设计师的杰作（Chef d'oeuvre）",
    "Handbags Hall": "箱包馆",
    "Le Noir Handbags Hall Designer": "黑派箱包馆设计师",
    "Le Rouge Handbags Hall Designer": "红派箱包馆设计师",
    "Le Noir's Brand Manager": "黑派品牌经理",
    "Le Noir Staff Manager": "黑派员工经理",
    "Le Noir Officer": "黑派干部",
    "Le Noir Guard": "黑派警卫",
    "Le Noir Porter": "黑派搬运工",
    "Le Rouge Porter": "红派搬运工",
    "Le Noir Sales Associate": "黑派店员",
    "Dying Noir": "濒死的黑派",
    "Maison du Noir": "黑派公馆（Maison du Noir）",
    "Boutique du Rouge": "红派精品店",
    "Le Kaki": "褐派（Le Kaki）",
    "Kaki": "褐派",
    "Needlekin": "针族",
    "Queueing Needlekin": "排队中的针族",
    "Fussy Needlekin": "吵闹的针族",
    "Loudmouthed Needlekin": "喧闹的针族",
    "Greedy Needlekin": "贪婪的针族",
    "Needlekin Laborer": "针族劳工",
    "Needlekin Laborer 2": "针族劳工2",
    "Buffet": "自助餐（Buffet）",
    "One Who Emerged from the Earth": "生于泥土者",
    "Tanned Prisoner": "被鞣制的罪人",
    "Putty": "油灰",
    "Flannel": "法兰绒",
    "Cocoon": "茧",
    "Two-piece": "两件套",
    "Four-legs": "四脚人",
    "One-leg": "单脚人",
    "Naked": "裸体者",
    "Skinhide Couch": "人皮沙发",
    "Mellow Leather Bed": "柔软皮床",
    "Taxidermied Leather Curtain": "剥制皮窗帘",
    "Red-cushioned Stool": "红垫圆凳",
    "Happy Closet": "快乐衣橱",
    "Bonehanger": "骨衣架",
    "Arc Floor Lamp": "驼背落地灯",
    "Lamp Twin": "双子台灯",
    "Leather Glove": "皮手套",
    "Crawling Leather": "爬行的皮革",
    "Felt": "毛毡",
    "Mimosa": "含羞草",
    "King of Needleworks": "裁缝之王",
    # —— 法语专名（意译 + 保留原文） ——
    "La Nausée": "恶心（La Nausée）",
    "Le Trou Rouge": "红之洞（Le Trou Rouge）",
    "Le Vomissement": "呕吐（Le Vomissement）",
    "Le Visqueux-Abject": "黏滞-卑劣（Le Visqueux-Abject）",
    "La Fin de l'Enfance": "童年终结（La Fin de l'Enfance）",
    # —— 技能 / 关键词 ——
    "Crimson Nail": "赤红之钉",
    "Baptism of Crimson Nails": "赤红之钉的洗礼",
    "Baptism [Crimson]": "洗礼[赤红]",
    "Go Away": "走开",
    "Perk Up": "打起精神",
    "Don't Get Hurty": "别受伤",
    "Grab My Hand": "抓住我的手",
    "I'll End It for You...": "我来替你结束……",
    "Leather-sewing Nail": "皮革缝制钉",
    "Pulsating Nature": "搏动的本性",
    "The Adventure": "旅程",
    "A Helping Hand": "援助之手",
    "Body Out of Control": "失控的身体",
    "Fate Lost": "脱离命运",
    "Tangling": "缠结",
    "Bursting Blackstitch": "崩开的黑线脚",
    "Clumped Black Threads": "结块的黑丝",
    "Pool of Black Water": "黑水之洼",
    "Instinct of the Predator of Eld": "远古捕食者的本能",
    "Bereaved of Child": "丧子之痛",
    "Laurel Wreath of Atonement": "赎罪的月桂冠",
    "Faint Aroma": "余香",
    "Petals": "花瓣",
    "Dyed Thread": "染色丝",
    "Gloss Medium": "光泽媒介",
    "Tar Dye": "焦油染料",
    "Inertia of Drifting": "漂流的惯性",
    "Cut Fabric": "裁剪过的面料",
    "Blossom Scissors": "花剪",
    "Alteration Target": "改造对象",
    "Mark of Shearing": "裁剪的印记",
    "Sheared Apart": "被裁开",
    "Trembling Hands": "颤抖的手",
    "Shower of Stinging Sunshine": "刺痛的阳光之雨",
    "Blessing of the Obsidian God": "黑曜之神的加护",
    "Apocalyptic Vengeance": "默示之罚",
    "Negation of Conservation": "保存的抵消",
    "Sanctum of Conservation": "保存的神域",
    "Formation Collapse": "阵型崩溃",
    "Promised Nail": "约定之钉",
    "Uncontrollable Rampage": "失控暴走",
    "Golden Revelation": "黄金启示",
    "Pink Mary Janes": "粉色玛丽珍鞋",
    "Golden Shroud": "黄金寿衣",
    "Unforgotten Pain": "无法忘却的痛楚",
    "Rule: Raw Hide Damage Prohibited": "规则：禁止损伤生皮",
    "Rule: Tanning Rush Prohibited": "规则：禁止催促进鞣",
    "Rule: Offensive Behavior Prohibited": "规则：禁止攻击性行为",
    "Rule: Defensive Behavior Prohibited": "规则：禁止防御性行为",
    "Tannery Rule Violation": "违反鞣皮室规则",
    "Uncreased Hide": "无褶之皮",
    "Rule Collapse": "规则的崩溃",
    "Jammed Machine": "机器卡死",
    "Disabled Overseeing": "统制失效",
    "Into the First Shell...": "回到第一层壳中……",
    "Sapphire": "蓝宝石",
    "Onyx": "缟玛瑙",
    "Diamond": "钻石",
    "Ripped Flesh of the Crimson God": "赤红之神被撕下的肉块",
    "Le Noir": "黑派",
    "Le Rouge": "红派",
}

#: 零协第一部分的固定译名（不许改）
LLC_FIXED = {
    "Grand Magasin Sisyphe": "西西弗百货",
    "L'Inamovible": "不可动摇者",
    "The Crimson God [Inchoate Life]": "赤红之神[未诞]",
    "The Preterm Crimson God": "未成的赤红之神",
    "Annette the Alterationist": "改衣师安妮特",
    "Sous Chef": "副主厨",
    "Brand Director": "品牌总监",
    "Floor Manager": "楼层经理",
    "3F Floor Manager": "3F楼层经理",
    "B2F Floor Manager": "B2F楼层经理",
    "Thirsty Kaki": "干渴的褐派",
    "Hungry Kaki": "饥饿的褐派",
    "Treatment Customer": "接受服务的顾客",
    "Eye-shopping Customer": "浏览商品的顾客",
    "Impatient Customer": "不耐烦的顾客",
    "Destitute Customer": "穷困的顾客",
    "Desperate Customer": "绝望的顾客",
    "Adamant Customer": "固执的顾客",
    "Hostile Customer": "怀有敌意的顾客",
}

BASE_TERMS = {
    "Uptie": "同步", "Threadspinning": "异想解析", "Identity": "人格", "Clash": "拼点",
    "SP": "理智值", "HP": "体力", "Stagger": "混乱", "Sinner": "罪人",
    "Extraction": "提取", "Egoshard": "自我碎片", "Max Stack": "最大值",
    "Sinner #1": "1号罪人", "Panic": "恐慌", "Tremor": "震颤", "Rupture": "破裂",
    "Sinking": "沉沦", "Poise": "架势", "Slash": "斩击", "Pierce": "穿刺",
    "Blunt": "打击", "Guard": "防御", "Evade": "闪避", "Counter": "反击",
}


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    mem = P.build_memory()
    files = P.new_files()

    # 新文件里出现过的「专名型」字符串（短、首字母大写、或字段本身就是名字）
    cand: Counter = Counter()
    for rel in files:
        try:
            data = P.load(P.en_path(rel))
        except Exception:
            continue
        def w(n):
            if isinstance(n, dict):
                for k, v in n.items():
                    if isinstance(v, str) and k in ("speaker", "teller", "name", "displayName", "title", "panicName"):
                        cand[v.strip()] += 1
                    else:
                        w(v)
            elif isinstance(n, list):
                for v in n:
                    w(v)
        w(P.body(data))

    table: dict[str, str] = {}
    for t in cand:
        zh = MANUAL.get(t) or LLC_FIXED.get(t) or mem.get(t)
        if zh and not re.search(r"[\uac00-\ud7af]", zh):
            table[t] = zh
    for k, v in LLC_FIXED.items():
        table[k] = v
    for k, v in MANUAL.items():
        table[k] = v

    (WORK / "术语对照.json").write_text(
        json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")

    md = ["# 第10章第二部分（a1c10p2）术语表", "",
          "权威顺序：零协包实际用词 > 术语表/审定新词 > 本次定名 > 常识。",
          "本表之外的词，按韩文原意 + 零协既有风格处理。", "",
          "## 一、本次定名（零协没翻过的）", ""]
    for k, v in MANUAL.items():
        md.append(f"- {k} → {v}")
    md += ["", "## 二、零协第一部分已定的译名（必须照抄，不许另起炉灶）", ""]
    for k, v in LLC_FIXED.items():
        md.append(f"- {k} → {v}")
    md += ["", "## 三、自动对照（新文件里出现的专名 → 零协/记忆里的中文）", ""]
    auto = {k: v for k, v in table.items() if k not in MANUAL and k not in LLC_FIXED}
    for k, v in sorted(auto.items(), key=lambda x: -len(x[0]))[:400]:
        md.append(f"- {k} → {v}")
    (WORK / "术语表.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"术语表 {len(table)} 条（人工 {len(MANUAL)} · 零协固定 {len(LLC_FIXED)} · 自动 {len(auto)}）")
    print(f"→ {WORK / '术语表.md'}")
    print(f"→ {WORK / '术语对照.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
