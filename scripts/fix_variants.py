"""机翻残留的错译名 → 定译名 的批量校正（跑在 data/translate/zh/*.json 上，然后重新 merge）。

这些错译来自「整批失败 → 逐行兜底」那批行（那批没走占位符保护），
所以统一在这里按对照表改掉，不动其它文字。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import translate_pack as tp  # noqa: E402

#: 错译 → 定译（长的先替换）
FIXES: dict[str, str] = {
    "大西西弗商场": "西西弗百货", "西西弗商场": "西西弗百货", "西西弗斯百货": "西西弗百货",
    "西西弗惩罚": "西西弗刑罚", "西西弗斯的惩罚": "西西弗刑罚",
    "梅尔索": "默尔索", "莫尔索": "默尔索", "默尔索先生": "默尔索先生",
    "内莉": "耐莉", "奈莉": "耐莉",
    "福斯特": "浮士德", "浮士德女士": "浮士德女士",
    "凉州": "良秀", "良州": "良秀", "凉秀": "良秀",
    "丹特": "但丁", "但丁先生": "但丁先生",
    "艾兹拉": "埃兹拉", "以斯拉": "埃兹拉",
    "伊什梅尔": "以实玛利", "以实马利": "以实玛利",
    "珍娜": "让娜", "贞娜": "让娜",
    "维吉利乌斯": "维吉里乌斯", "维吉尔": "维吉里乌斯",
    "奥蒂斯": "奥提斯", "欧提斯": "奥提斯",
    "格里戈尔": "格里高尔", "格雷戈尔": "格里高尔",
    "辛克莱尔": "辛克莱", "希斯克利夫先生": "希斯克利夫先生",
    "罗迪亚": "罗佳", "罗迪娅": "罗佳", "罗佳娅": "罗佳",
    "罐头体验": "罐头体验", "罐装体验": "罐头体验", "罐头经验": "罐头体验",
    "自杀自动售货机": "自杀贩卖机", "自杀售货机": "自杀贩卖机",
    "变革者": "改造师", "改造者": "改造师",
    "金皮": "金皮", "金色毛皮": "金皮", "金色皮革": "金皮",
    "陌生人": "异乡人", "外地人": "异乡人",

    "西西弗斯": "西西弗",
    "西绪福斯": "西西弗",
}
FIXES.update({
    "时间尺度绞刑架": "时间刻度绞刑架", "时间尺度": "时间刻度",
    "大商店": "西西弗百货", "大百货公司": "西西弗百货", "诺尔家": "Le Noir", "诺尔家族": "Le Noir", "大商场": "西西弗百货", "大型商场": "西西弗百货",
    "百货公司": "西西弗百货", "大百货商店": "西西弗百货",
    "金丝": "金线团", "金色绞线": "金线团", "金色线团": "金线团",
    "金茧": "金茧", "金色茧": "金茧",
    "金色树脂": "金树脂", "金色的脓液": "金脓",
    "阿恩杜": "艾恩杜", "樱桃": "艾恩杜", "英杜": "艾恩杜",
    "油灰": "普蒂", "赤裸": "赤裸者", "调色板": "帕莱特", "帕莱特": "帕莱特",
    "团队负责人": "组长", "队长": "组长",
})

#: 词边界敏感的（避免误伤）
REGEX_FIXES: list[tuple[str, str]] = [
    (r"(?<!辩护)律师", "辩护律师"),
    (r"\bSisyphe\b", "西西弗"),
    (r"\bOutis\b", "奥提斯"),
    (r"\bMeursault\b", "默尔索"),
    (r"\bJeanne\b", "让娜"),
    (r"\bDante\b", "但丁"),
    (r"\bAlterationist\b", "改造师"),
]

def fix_text(text: str) -> tuple[str, int]:
    n = 0
    text, k = re.subn(r"(?<![\w@])@(?![\w@])", "", text)   # 占位符残留的孤立 @
    n += k
    for wrong, right in FIXES.items():
        if wrong != right and wrong in text:
            n += text.count(wrong)
            text = text.replace(wrong, right)
    for pattern, right in REGEX_FIXES:
        text, k = re.subn(pattern, right, text)
        n += k
    return text, n

def main() -> int:
    total = 0
    changed_files = 0
    targets = sorted(tp.ZH_DIR.glob("*.json"))
    files_dir = ROOT / "data" / "translate" / "files"
    targets += sorted(files_dir.rglob("*.json")) if files_dir.is_dir() else []      # RPG/数据文件
    for path in targets:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        hits = 0
        if isinstance(data, dict) and isinstance(data.get("lines"), dict):      # 故事译文
            lines = data["lines"]
            for rid, zh in list(lines.items()):
                fixed, n = fix_text(str(zh))
                if n:
                    lines[rid] = fixed
                    hits += n
        else:                                                                   # 数据文件：整份 json 走一遍
            def rec(node):
                nonlocal hits
                if isinstance(node, dict):
                    for k, v in list(node.items()):
                        if isinstance(v, str):
                            fixed, n = fix_text(v)
                            if n:
                                node[k] = fixed
                                hits += n
                        else:
                            rec(v)
                elif isinstance(node, list):
                    for i, v in enumerate(node):
                        if isinstance(v, str):
                            fixed, n = fix_text(v)
                            if n:
                                node[i] = fixed
                                hits += n
                        else:
                            rec(v)
            rec(data)
        if hits:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            changed_files += 1
            print(f"  {path.stem}: 校正 {hits} 处")
            total += hits
    print(f"共校正 {total} 处（{changed_files} 个文件）")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
