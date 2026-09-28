# -*- coding: utf-8 -*-
"""按灰机 wiki「放映室」分段重排 10-4A / 10-4B 的分支。

wiki: https://limbuscompany.huijiwiki.com/wiki/章节X_凝视之下
路线A（9 段）: 1F → 2F① → 3F① → 4F → 3F② → B1F → B2F → 3F③ → 2F②
路线B（17 段）: 1F① → 2F① → 3F① → 2F② → 3F② → 4F① → 5F① → B1F①
                → B2F① → B3F① → B2F② → B1F② → 1F② → 2F③ → 4F② → B3F② → 5F②

用法：
    python scripts/ch10p2_resegment.py          # 打印新分支结构到 _reseg.txt
    python scripts/ch10p2_resegment.py --apply  # 写回 story_rpg_plan.json（先备份）
"""
import io
import json
import os
import shutil
import sys

ROOT = r"D:\Desktop\lbc"
PLAN = os.path.join(ROOT, "limbus_patcher", "data", "story_rpg_plan.json")
OUT = os.path.join(ROOT, "_reseg.txt")

R = "RPGSystem/"
S = "StoryData/"


def p(file, rec=None, label=None):
    d = {"file": file}
    if rec:
        d["records"] = rec
    if label:
        d["label"] = label
    return d


# ---------------------------------------------------------------- 路线 A
A = [
    {
        "id": "b01",
        "label": "01 1F·西西弗百货（含序章）",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线A 第 1 段 = 1F。序章（S1000B 入店广播、S1001B 坠落）与 1F 探索合为一段；floor-1 全篇单次到访，Q1000–Q1064。",
        "parts": [
            p(S + "S1000B.json", label="过场·进店广播"),
            p(S + "S1001B.json", label="过场·坠落与苏醒"),
            p(R + "rpg-loc-dialogue-floor-1.json", [0, 5], "探索·尸雨"),
            p(S + "S1002B.json", label="过场·克罗默之姐·美容厅"),
            p(R + "rpg-loc-dialogue-floor-1.json", [6, None], "探索·百货店（人台→服饰馆→红派→扶梯）"),
            p(R + "rpg-loc-dialogue-choice-floor-1.json"),
        ],
        "quests": ["Q1000", "Q1011", "Q1012", "Q1013", "Q1014", "Q1021", "Q1022",
                   "Q1023", "Q1031", "Q1032", "Q1041", "Q1042", "Q1051", "Q1052",
                   "Q1061", "Q1062", "Q1064", "Q1018", "Q1001"],
    },
    {
        "id": "b02",
        "label": "02 2F·第一部分",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线A 第 2 段 = 2F 第一部分。floor-2 全篇单次到访（Q2001–Q2004，奢华大厅→击退红派→圣所）；wiki 的 2F 第二部分在终盘，见 b09。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-2.json", None, "探索·2F（施工→奢侈品馆→帐幕）"),
            p(R + "rpg-loc-dialogue-choice-floor-2.json"),
        ],
        "quests": ["Q2001", "Q2002", "Q2003", "Q2011", "Q2004"],
    },
    {
        "id": "b03",
        "label": "03 3F·第一部分",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线A 第 3 段 = 3F 第一部分。floor-3 记录 0–144（Q3001–Q3024：咔嚓声→改衣室→不可动摇者→广播室→买剪刀散会→绕道黑派→击杀安妮特）；145 起为「你回来了」的折返，已拆到 b05。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-3.json", [0, 6], "探索·上楼（辛克莱与奥提斯）"),
            p(S + "S1008B.json", label="过场·让娜之声（走廊 3F）"),
            p(R + "rpg-loc-dialogue-floor-3.json", [7, 11], "探索·循声而行"),
            p(S + "S1009B.json", label="过场·改衣室·安妮特（改造店 3F）"),
            p(S + "S1010B.json", label="过场·默尔索妈妈（3F 红派精品店）"),
            p(R + "rpg-loc-dialogue-floor-3.json", [12, 144], "探索·品牌世家（两件套→精品店→广播室）"),
            p(R + "rpg-loc-dialogue-choice-floor-3.json"),
            p(R + "rpg-loc-narration-floor-3.json"),
        ],
        "quests": ["Q3001", "Q3002", "Q3003", "Q3004", "Q3005", "Q3006", "Q3007",
                   "Q3008", "Q3009", "Q3010", "Q3011", "Q3012", "Q3013",
                   "Q3016T", "Q3016H1", "Q3016H2"],
    },
    {
        "id": "b04",
        "label": "04 4F",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线A 第 4 段 = 4F。floor-4 全篇单次到访（Q4001–Q4013 家具馆/弧形落地灯，Q4009 前往地下楼层）。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-4.json", None, "探索·4F（制鞋馆→家具馆）"),
            p(R + "rpg-loc-dialogue-choice-floor-4.json"),
        ],
        "quests": ["Q4001", "Q4002", "Q4003", "Q4004", "Q4005", "Q4006", "Q4007",
                   "Q4008", "Q4013", "Q4009"],
    },
    {
        "id": "b05",
        "label": "05 3F·第二部分（取钉子）",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "medium",
        "evidence": "wiki 路线A 第 5 段 = 3F 第二部分（在 4F 之后）。floor-3 记录 145–150：D41410「啊……你回来了。我们一直在等你。」+ D41420 安妮特交付金色面料，对应归档在 3F 任务文件里的 Q4014–Q4017。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-3.json", [145, 150], "折返·取钉子与金色面料"),
        ],
        "quests": ["Q4014", "Q4015", "Q4016", "Q4017"],
    },
    {
        "id": "b06",
        "label": "06 B1F",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线A 第 6 段 = B1F。S1011B（扶梯厅）→ floor-b1 0–7 → S1012B（肉味苏打）→ floor-b1 8–末（美食广场）；Q-1000–Q-1011。",
        "parts": [
            p(S + "S1011B.json", label="过场·自动扶梯·原地打转"),
            p(R + "rpg-loc-dialogue-floor-b1.json", [0, 7], "探索·扶梯厅"),
            p(S + "S1012B.json", label="过场·肉味苏打"),
            p(R + "rpg-loc-dialogue-floor-b1.json", [8, None], "探索·美食广场（副主厨→屠夫→黄金之茧）"),
            p(R + "rpg-loc-dialogue-choice-floor-b1.json"),
        ],
        "quests": ["Q-1000", "Q-1001", "Q-1002", "Q-1003", "Q-1004", "Q-1005",
                   "Q-1006", "Q-1008", "Q-1009", "Q-1010", "Q-1011"],
    },
    {
        "id": "b07",
        "label": "07 B2F",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线A 第 7 段 = B2F。floor-b2 0–37 抵达与线团之巢 → S1013B 楼层管理员 → 38–48 染色室 → S1014B 帕莱特 → 49–末 取线；Q-2000–Q-2017（末为「前往 3F」）。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-b2.json", [0, 37], "探索·抵达与线团之巢"),
            p(S + "S1013B.json", label="过场·楼层管理员"),
            p(R + "rpg-loc-dialogue-floor-b2.json", [38, 48], "探索·染色室"),
            p(S + "S1014B.json", label="过场·染坊·帕莱特"),
            p(R + "rpg-loc-dialogue-floor-b2.json", [49, None], "探索·取线（无色染料→抽丝→黄金线团）"),
            p(R + "rpg-loc-dialogue-choice-floor-b2.json"),
        ],
        "quests": ["Q-2000", "Q-2001", "Q-2002", "Q-2003", "Q-2004", "Q-2005",
                   "Q-2006", "Q-2007", "Q-2008", "Q-2009", "Q-2010", "Q-2011",
                   "Q-2012", "Q-2013", "Q-2014", "Q-2015", "Q-2016A", "Q-2017"],
    },
    {
        "id": "b08",
        "label": "08 3F·第三部分（织布与收尾）",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线A 第 8 段 = 3F 第三部分（B2F 之后）。floor-3 记录 151–末（金线团→剪刀声消失→不可动摇者终幕）+ S1015B（改造店 3F 金线织布）+ route-a「我们又回到了这里」+ S1016B（place=红色精品店，三楼）。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-3.json", [151, None], "折返·金线团与终幕"),
            p(S + "S1015B.json", label="过场·金线织布（改造店 3F）"),
            p(R + "rpg-loc-dialogue-route-a.json", label="探索·返回 3F 收尾"),
            p(S + "S1016B.json", label="过场·不可移动者（红派精品店 3F）"),
        ],
        "quests": [],
    },
    {
        "id": "b09",
        "label": "09 2F·第二部分·终盘",
        "kind": "story",
        "kind_label": "过场",
        "confidence": "medium",
        "evidence": "wiki 路线A 第 9 段 = 2F 第二部分。place 标记：S1061B=豪华大厅 2 楼；S1062B=西西弗塔楼巨人的房间；S1060B（被告·杀害妈妈）与 S9991B（尾声）无 place，按剧情顺序附于末段。floor-2 对话内无 2F 折返内容，故本段由过场构成。",
        "parts": [
            p(S + "S1060B.json", label="过场·被告·杀害妈妈"),
            p(S + "S1061B.json", label="过场·摇篮曲（豪华大厅 2F）"),
            p(S + "S1062B.json", label="过场·让娜·被钉死（塔楼巨人之室）"),
            p(S + "S9991B.json", label="过场·尾声·永存的西西弗"),
        ],
        "quests": [],
    },
    {
        "id": "b10",
        "label": "10 通用互动台词（跨楼层复用）",
        "kind": "common",
        "kind_label": "通用",
        "confidence": "high",
        "evidence": "D900xx 各楼层复用的互动台词（尸体/任务提示/通用应答），不属特定楼层，置底单列。",
        "parts": [
            p(R + "rpg-loc-dialogue-common-a1c10p1.json", label="通用互动台词"),
            p(R + "rpg-loc-dialogue-choice-common-a1c10p1.json"),
        ],
        "quests": [],
    },
    {
        "id": "b11",
        "label": "11 放映厅（未解锁）",
        "kind": "common",
        "kind_label": "通用",
        "confidence": "high",
        "evidence": "rpg-loc-dialogue-theater.json 为放映厅台词，游戏内未解锁，单列置底。",
        "parts": [
            p(R + "rpg-loc-dialogue-theater.json", label="未解锁·放映厅"),
        ],
        "quests": [],
    },
]

# ---------------------------------------------------------------- 路线 B
B = [
    {
        "id": "b01",
        "label": "01 1F·第一部分（含序章）",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线B 第 1 段 = 1F 第一部分。序章 S1017B（place=泉，1F）与 S1018B（1F 美妆馆）并入本段；floor-1-b 记录 0–116 为首次到访（Q1000–Q1064）。",
        "parts": [
            p(S + "S1017B.json", label="过场·再次坠落（泉，1F）"),
            p(R + "rpg-loc-dialogue-floor-1-b.json", [0, 116], "探索·1F（美妆馆→快销服饰馆→人偶→扶梯）"),
            p(R + "rpg-loc-dialogue-choice-floor-1-b.json"),
            p(S + "S1018B.json", label="过场·1F 美妆馆"),
        ],
        "quests": ["Q1000", "Q1001", "Q1011", "Q1013", "Q1021", "Q1022", "Q1023",
                   "Q1031", "Q1064", "Q1012S"],
    },
    {
        "id": "b02",
        "label": "02 2F·第一部分",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线B 第 2 段 = 2F 第一部分。floor-2-b 记录 0–27：初入 2F、施工、奢侈品馆（Q2001–Q2005）。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-2-b.json", [0, 27], "探索·2F（施工→奢侈品馆）"),
        ],
        "quests": ["Q2001", "Q2003", "Q2004", "Q2005"],
    },
    {
        "id": "b03",
        "label": "03 3F·第一部分",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线B 第 3 段 = 3F 第一部分。floor-3-b 记录 0–104（抵达→裁衣声→精品店→不可动摇者→走廊）+ S1019B（3F 走廊）、S1020B（3F 改衣室）。105 起「欢迎回来」属 b05。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-3-b.json", [0, 104], "探索·3F（裁衣声→精品店→不可动摇者）"),
            p(R + "rpg-loc-dialogue-choice-floor-3-b.json"),
            p(R + "rpg-loc-narration-floor-3-b.json"),
            p(S + "S1019B.json", label="过场·3F 走廊"),
            p(S + "S1020B.json", label="过场·3F 改衣室"),
        ],
        "quests": ["Q3001", "Q3002", "Q3004", "Q3005", "Q3006", "Q3020", "Q3021",
                   "Q3022", "Q3023", "Q3024"],
    },
    {
        "id": "b04",
        "label": "04 2F·第二部分（送眼珠·摇篮）",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线B 第 4 段 = 2F 第二部分（在 3F① 之后，对应 3F 任务 Q3025「回到 2F」）。floor-2-b 记录 28–59：D2026「咦？又回这层？喂，带了好多眼珠来？」→ 摇篮/孩童事件。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-2-b.json", [28, 59], "折返·摇篮与孩童（普伊）"),
        ],
        "quests": ["Q3025", "Q2008", "Q2008A", "Q2008B", "Q2009", "Q2010"],
    },
    {
        "id": "b05",
        "label": "05 3F·第二部分",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线B 第 5 段 = 3F 第二部分。floor-3-b 记录 105–末：D3206 安妮特「欢迎回来，肩缝松垮的异乡人们」→ 带孩子见不可动摇者（Q3026–Q3028）。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-3-b.json", [105, None], "折返·再见不可动摇者"),
        ],
        "quests": ["Q3003", "Q3026", "Q3027", "Q3028", "Q3016T", "Q3016H1", "Q3016H2"],
    },
    {
        "id": "b06",
        "label": "06 4F·第一部分",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "medium",
        "evidence": "wiki 路线B 第 6 段 = 4F 第一部分。floor-4-b 记录 0–163：制鞋馆→家具馆→多萝西娅→箱包馆设计师（Q4001–Q4026）+ 4F 过场 S1022B–S1025B（place 均为 4F）。164 起为 4F 第二部分（b14）。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-4-b.json", [0, 163], "探索·4F（制鞋馆→家具馆→箱包馆）"),
            p(R + "rpg-loc-dialogue-choice-floor-4-b.json"),
            p(S + "S1022B.json", label="过场·走廊 4F"),
            p(S + "S1023B.json", label="过场·鞋履馆 4F"),
            p(S + "S1024B.json", label="过场·走失儿童中心 4F"),
            p(S + "S1025B.json", label="过场·红派箱包馆 4F"),
        ],
        "quests": ["Q4001", "Q4002", "Q4002A", "Q4003", "Q4003A", "Q4003B", "Q4004",
                   "Q4005", "Q4006", "Q4007", "Q4008", "Q4008A", "Q4013", "Q4021",
                   "Q4022", "Q4023", "Q4023A", "Q4023B", "Q4023C", "Q4023D",
                   "Q4023E", "Q4024", "Q4024A", "Q4024B", "Q4024C", "Q4025",
                   "Q4025A", "Q4025B", "Q4025C", "Q4026"],
    },
    {
        "id": "b07",
        "label": "07 5F·第一部分",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "medium",
        "evidence": "wiki 路线B 第 7 段 = 5F 第一部分。floor-5-b 记录 0–96：抵达 5F→普伊化茧→黑派品牌经理→黑之丝（Q5001–Q5002）+ S1026B（place=餐厅 5F）。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-5-b.json", [0, 96], "探索·5F（初入与帐幕）"),
            p(S + "S1026B.json", label="过场·餐厅 5F"),
        ],
        "quests": ["Q5001", "Q5002", "Q5011"],
    },
    {
        "id": "b08",
        "label": "08 B1F·第一部分",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线B 第 8 段 = B1F 第一部分。floor-b1-b 全篇：猎物思维→副主厨→海岸→幼虫→扶梯厅（Q-1000–Q-1011）。注：wiki 另有 B1F 第二部分（取皮革回访 Q-3011），本文件内未找到独立的二次到访对话，疑似复用通用台词，待实机确认。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-b1-b.json", None, "探索·B1F（美食广场→海岸→扶梯厅）"),
            p(R + "rpg-loc-dialogue-choice-floor-b1-b.json"),
        ],
        "quests": ["Q-1000", "Q-1001", "Q-1002", "Q-1003", "Q-1004", "Q-1005",
                   "Q-1008", "Q-1009", "Q-1010", "Q-1011"],
    },
    {
        "id": "b09",
        "label": "09 B2F·第一部分",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线B 第 9 段 = B2F 第一部分。floor-b2-b 记录 0–116：抵达→裸体者→染坊→线团巢→楼层管理员→交线团（Q-2000–Q-2010A）+ S1027B（place=B2F 线团之巢）。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-b2-b.json", [0, 116], "探索·B2F（线团之巢→染坊）"),
            p(R + "rpg-loc-dialogue-choice-floor-b2-b.json"),
            p(S + "S1027B.json", label="过场·B2F 线团之巢"),
        ],
        "quests": ["Q-2000", "Q-2000A", "Q-2001", "Q-2002", "Q-2003", "Q-2004",
                   "Q-2004A", "Q-2005", "Q-2006", "Q-2007", "Q-2008", "Q-2009",
                   "Q-2010", "Q-2010A"],
    },
    {
        "id": "b10",
        "label": "10 B3F·第一部分",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线B 第 10 段 = B3F 第一部分。floor-b3-b 记录 0–17：乘扶梯抵达鞣皮室、统制者交代皮革所在（Q-3000）+ S1028B（place=鞣皮室 B3F）。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-b3-b.json", [0, 17], "探索·B3F 鞣皮室（领取任务）"),
            p(S + "S1028B.json", label="过场·鞣皮室 B3F"),
        ],
        "quests": ["Q-3000", "Q-3010", "Q-3010A", "Q-3010B", "Q-3010S", "Q-3011S"],
    },
    {
        "id": "b11",
        "label": "11 B2F·第二部分（取皮革）",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线B 第 11 段 = B2F 第二部分。floor-b2-b 记录 117–末：D-2244 调色板「又完好无损地回来了。是临走前来道别的吗？」→ 取黄金皮革（Q-3011 去取皮革 - B1F 之后的跑腿）。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-b2-b.json", [117, None], "折返·取黄金皮革"),
        ],
        "quests": ["Q-3011"],
    },
    {
        "id": "b12",
        "label": "12 1F·第二部分（取皮革）",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "low",
        "evidence": "wiki 路线B 第 13 段 = 1F 第二部分（取皮革 Q-3012）。floor-1-b 记录 117–末为候选区间，但本文件无显式「回到 1F」标记，切点为推断（依 D1981 含羞草被打、文末普伊 D1805 现身的战斗残段）。需进游戏确认。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-1-b.json", [117, None], "折返·取皮革与收尾战斗"),
        ],
        "quests": ["Q-3012"],
    },
    {
        "id": "b13",
        "label": "13 2F·第三部分（取皮革）",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "medium",
        "evidence": "wiki 路线B 第 14 段 = 2F 第三部分（取皮革 Q-3013）。floor-2-b 记录 60–末：摇篮事件后的战斗残骸与柱子线索（D2902 起）。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-2-b.json", [60, None], "折返·取皮革与柱子线索"),
        ],
        "quests": ["Q-3013"],
    },
    {
        "id": "b14",
        "label": "14 4F·第二部分（取皮革）",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "medium",
        "evidence": "wiki 路线B 第 15 段 = 4F 第二部分（取皮革 Q-3015）。floor-4-b 记录 164–末：D42093 鸿璐「还记得这地方吗？我们早年间建的……」→ 家具/设计师最终对抗。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-4-b.json", [164, None], "折返·取皮革与设计师终局"),
        ],
        "quests": ["Q-3015"],
    },
    {
        "id": "b15",
        "label": "15 B3F·第二部分（统制者）",
        "kind": "rpg",
        "kind_label": "RPG 楼层",
        "confidence": "high",
        "evidence": "wiki 路线B 第 16 段 = B3F 第二部分。floor-b3-b 记录 18–末：D-3214 统制者「上层顾客带回了所有必需的黄金皮革」→ 鞣皮→裁剪→缝制→领取黄金寿衣→击杀统制者（Q-3006–Q-3002）；warden-boss 三文件属统制者战，归本段。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-b3-b.json", [18, None], "折返·黄金寿衣与统制者"),
            p(R + "rpg-loc-npc-route-b-warden.json"),
            p(R + "rpg-loc-npc-common-warden-boss-a1c10p2.json"),
            p(R + "rpg-loc-narration-common-warden-boss-a1c10p2.json"),
        ],
        "quests": ["Q-3006", "Q-3003", "Q-3003A", "Q-3003B", "Q-3003C", "Q-3004",
                   "Q-3007", "Q-3001", "Q-3005", "Q-3002", "Q-3011T", "Q-3011H1",
                   "Q-3011H2", "Q-3011H3", "Q-3011R"],
    },
    {
        "id": "b16",
        "label": "16 5F·第二部分·终盘",
        "kind": "story",
        "kind_label": "过场",
        "confidence": "medium",
        "evidence": "wiki 路线B 第 17 段 = 5F 第二部分。floor-5-b 记录 97–末（DDS501 普伊独自一人、D5027「西西弗百货中的众生，听我一言」）+ S1029B（place=餐厅 5F）+ S9992B（无 place，按内容归终盘，把握 low）+ route-b 三文件。",
        "parts": [
            p(R + "rpg-loc-dialogue-floor-5-b.json", [97, None], "终盘·5F"),
            p(R + "rpg-loc-dialogue-route-b.json"),
            p(R + "rpg-loc-player-route-b.json"),
            p(R + "rpg-loc-npc-route-b.json"),
            p(S + "S1029B.json", label="过场·餐厅 5F·普伊成王"),
            p(S + "S9992B.json", label="过场·西西弗百货必须被消费"),
        ],
        "quests": ["Q5004", "Q5008", "Q5006", "Q5007", "Q5003", "Q5005", "Q5009",
                   "Q5010", "Q5012"],
    },
    {
        "id": "b17",
        "label": "17 通用互动台词（跨楼层复用）",
        "kind": "common",
        "kind_label": "通用",
        "confidence": "high",
        "evidence": "路线 B 的通用对话/名称/道具/UI，跨楼层复用，置底单列。",
        "parts": [
            p(R + "rpg-loc-dialogue-common-a1c10p2.json"),
            p(R + "rpg-loc-npc-common-a1c10p2.json"),
            p(R + "rpg-loc-item-common-a1c10p2.json"),
            p(R + "rpg-loc-ui-common-a1c10p2.json"),
        ],
        "quests": [],
    },
    {
        "id": "b18",
        "label": "18 杜布瓦人格剧情",
        "kind": "story",
        "kind_label": "过场",
        "confidence": "medium",
        "evidence": "P10917 说话人杜布瓦，属人格/EGO 解锁剧情，不属主线；杜布瓦在 1F（Q1064）现身，置底最稳妥。",
        "parts": [
            p(S + "P10917.json"),
        ],
        "quests": [],
    },
]


def main():
    apply = "--apply" in sys.argv
    out = io.open(OUT, "w", encoding="utf-8", buffering=1)
    pl = json.load(io.open(PLAN, encoding="utf-8"))
    for code, branches in (("10-4A", A), ("10-4B", B)):
        st = pl["stages"][code]
        out.write("=== %s  %s\n" % (code, st.get("label")))
        for b in branches:
            out.write("  [%s] %s  conf=%s\n" % (b["id"], b["label"], b["confidence"]))
            for pt in b["parts"]:
                rec = pt.get("records")
                out.write("      - %s %s %s\n" % (pt["file"], rec or "", pt.get("label", "")))
        if apply:
            st["branches"] = branches
    if apply:
        bak = PLAN + ".bak_reseg"
        shutil.copy2(PLAN, bak)
        io.open(PLAN, "w", encoding="utf-8").write(json.dumps(pl, ensure_ascii=False, indent=2))
        out.write("\napplied. backup=%s\n" % os.path.relpath(bak, ROOT))
    out.close()


if __name__ == "__main__":
    main()
