"""战中气泡（BattleSpeechBubbleDlg）→ 图鉴实体映射（运行时只读）。

覆盖前 1-9 章（含通用 / 间章）的气泡文件，供敌人图鉴 / 人格图鉴展示：
  · 章节类（a1c9p1/p2/p3、exme、twth、_Cultivation、_mowe）：按 desc 中的敌人名 / 族称
    （9SV-BATn 组）或 id 前缀 / 韩文人名映射到敌人 / 人格实体 id；
  · 通用类（BattleSpeechBubbleDlg.json）：按 id 内嵌单位数字关联人格 / E.G.O 实体 id
    （battle_<数字>_*），名字型（battle_speechbubble_<名字>）走韩文人名表。

数据只读自游戏包（LLC_zh-CN），dlg 已是中文；第十章（a1c10p1）已单独接入 story_stages，
不在此模块范围内；translate / supplement 目前无前 1-9 章气泡补译，故不参与合并。
无对应实体记录的条目（NPC / 杂项）直接丢弃，属预期行为。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

#: 前 1-9 章（含通用 / 间章）气泡文件清单（第十章 a1c10p1 不在此列）
BUBBLE_FILES: tuple[str, ...] = (
    "BattleSpeechBubbleDlg-a1c9p1.json",
    "BattleSpeechBubbleDlg-a1c9p2.json",
    "BattleSpeechBubbleDlg-a1c9p3.json",
    "BattleSpeechBubbleDlg-exme.json",
    "BattleSpeechBubbleDlg-twth.json",
    "BattleSpeechBubbleDlg.json",
    "BattleSpeechBubbleDlg_Cultivation.json",
    "BattleSpeechBubbleDlg_mowe.json",
)

#: 9SV-BAT{n} 组 → 第9章敌人 / 人格实体 id（无实体组留空，属预期丢弃）
BAT_MAP: dict[int, list[int]] = {
    1: [],            # 韦斯帕（无实体）
    2: [],            # 摩西（无实体）
    3: [1327],        # 中指父辈-马蒂亚斯
    4: [1318, 1338],  # 小指子辈-莲
    5: [],            # 霍恩海姆（无实体）
    6: [],            # 以斯拉（无实体）
    7: [1306],        # 拇指子辈-卢西奥
    8: [1314],        # 拇指父辈-瓦伦希娜
    9: [1339],        # 蜚蠊皇帝
    10: [8999],       # 维吉里乌斯
    11: [],           # 阿莉莎（无实体）
    12: [1287, 11001],  # 未来辛克莱 -> 敌人辛克莱 + 人格LCB辛克莱
    13: [1328],       # 中指子辈-绮罗
    14: [1322, 1323, 1324],  # 小指父辈-盐见夜
    15: [1331],       # 环指父辈-卡利斯托
    16: [1319],       # 环指子辈-阿尔比娜
    17: [1347, 1348],  # 食指父辈-里恩
    18: [1325, 1337],  # 食指子辈-空
    99: [10401],      # 良秀（人格 LCB）
}

#: 韩文人名 / 特征词 → 实体 id（通用文件 desc / id 匹配）
KO_NAME_MAP: dict[str, list[int]] = {
    "크로머": [91028],    # 克洛默
    "카세티": [8350],     # 卡塞蒂
    "사샤": [91018],     # 萨莎
    "뫼르소": [10508],    # 默尔索
    "김삿갓": [],        # 金笠（无实体）
    "산군": [1448, 1449],  # 山君
}


@dataclass(frozen=True)
class BubbleLine:
    """一条战中气泡（与 CodexVoice 字段对齐，便于挂载到图鉴卡片）。"""
    file: str
    record_index: int
    record_id: object = None
    key: str = ""             # 记录 id，如 9SV-BAT4-03 / battle_10808_1
    category: str = ""        # desc（触发条件，可能是中文或韩语残留）
    text: str = ""            # dlg（台词）


def parse_targets(fname: str, rid: str, desc: str) -> list[int]:
    """单条气泡 → 目标实体 id 列表（规则已实测验证，见 build_bubble_map.py 产物）。"""
    # 1) 9SV-BAT{n}（第9章族称组）
    m = re.match(r"^9SV-BAT(\d+)-", rid)
    if m:
        return BAT_MAP.get(int(m.group(1)), [])
    # 2) exme 952SV（间章：山君 / 剑界默尔索）
    if re.match(r"^952SV-", rid):
        if re.search(r"101|102|103|104|105", rid):
            return [10508, 91057, 91058]
        return [1448, 1449]
    # 3) twth 活动首领 / 援助绮罗
    if rid.startswith("9SV-EVENT1-BOSS"):
        return [1422, 1423]
    if rid.startswith("9SV-051"):
        return [1328]
    # 4) mowe 6SV（间章）
    if re.match(r"^6SV-", rid):
        if "사샤" in desc:
            return [91018]
        return [8350]
    # 5) 8SV（第八章）
    if rid.startswith("8SV-"):
        if "뇌횡" in desc:
            return [1145]
        if "가모" in desc:
            return [1146]
        return []
    # 6) 7SV-BV（第七章间章）
    if rid.startswith("7SV-BV"):
        if "리카르도" in desc:
            return [1127]
        if "桑丘" in desc or "산초" in desc:
            return [8380]
        return []
    # 7) 通用 battle_* / Cultivation：数字 id 直接关联人格 / E.G.O 实体
    if rid.startswith("battle_"):
        m = re.search(r"_(\d{4,6})[_$]", rid)
        if not m:
            m = re.search(r"_(\d{4,6})$", rid)
        if m:
            return [int(m.group(1))]
        # 无数字：名字型（battle_speechbubble_<韩文人名>）
        for ko, ids in KO_NAME_MAP.items():
            if ko in desc or ko in rid:
                return ids
        return []
    return []


def _records(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    dl = data.get("dataList") if isinstance(data, dict) else None
    return dl if isinstance(dl, list) else []


def _scan(llc_dir: str) -> dict[int, list[BubbleLine]]:
    idx: dict[int, list[BubbleLine]] = {}
    root = Path(llc_dir)
    for fname in BUBBLE_FILES:
        path = root / fname
        if not path.is_file():
            continue
        for i, rec in enumerate(_records(path)):
            if not isinstance(rec, dict):
                continue
            rid = str(rec.get("id") or "")
            desc = str(rec.get("desc") or "")
            dlg = str(rec.get("dlg") or "")
            if not dlg:
                continue
            targets = parse_targets(fname, rid, desc)
            if not targets:
                continue
            line = BubbleLine(file=fname, record_index=i, record_id=rec.get("id"),
                              key=rid, category=desc, text=dlg)
            for t in targets:
                idx.setdefault(int(t), []).append(line)
    return idx


@lru_cache(maxsize=8)
def build_index(llc_dir: str) -> dict[int, tuple[BubbleLine, ...]]:
    """扫描游戏包前 1-9 章气泡，返回 {实体 id: (BubbleLine, ...)}（缓存）。"""
    raw = _scan(llc_dir)
    return {k: tuple(v) for k, v in raw.items()}


def lines_for(llc_dir: str, entity_id: int) -> tuple[BubbleLine, ...]:
    """按实体 id 取气泡（无则空元组）。"""
    return build_index(llc_dir).get(int(entity_id), ())
