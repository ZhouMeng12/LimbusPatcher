"""第十章数据/RPG 文件终检与修补：
1) 残留英文（机翻没译的）→ 走同一套流水线补译；
2) 半角标点 / 省略号规范化；
3) 译名统一（Kaki、Needlekin、Crimson God、Le Rouge 员工…）与已知误译修正；
4) 空字段检查（有空的直接报出来）。

用法：python scripts/final_pass.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import mt_translate as mt  # noqa: E402
import mt_files as mf  # noqa: E402

LATIN_ONLY = re.compile(r"^[A-Za-z0-9 ,.'\"!?…\-–—():;*]+$")
LATIN = re.compile(r"[A-Za-z]{3,}")
SKIP_FIELDS = {"id", "model", "key", "code"}

#: 译名统一 / 已知误译（长的先替换）
FIXES: dict[str, str] = {
    "暴怒之神": "深红之神", "暴怒神": "深红之神", "红色神明": "深红之神", "红神": "深红之神",
    "卡其": "卡基", "经针精灵": "针怪", "纬针精灵": "针怪", "扭曲针灵": "针怪", "纬针灵": "针怪",
    "针之王": "针怪之王", "针工之王": "针怪之王",
    "流氓团伙": "Le Rouge 的人", "胭脂": "Rouge", "红色店员": "Le Rouge 店员",
    "奇数回合": "偶数回合",
    "东……方向！": "盛……宴！", "东……方向": "盛……宴",
    "撤销……": "解开……", "撤销": "解开",
    "经理": "经理",          # 零协译法就是「经理」，保持不变（占位，防止误改）
    "使……与……哭泣对齐！": "与……的哭声……对齐！",
}

#: 只对人名/说话人字段生效的统一表（避免误改正文里的普通词）
NAME_FIELDS = {"speaker", "displayName", "name", "teller"}
NAME_FIXES: dict[str, str] = {
    "含羞草": "米莫萨", "米莫莎": "米莫萨", "咪莫萨": "米莫萨", "米莫萨": "米莫萨",
    "法兰绒": "弗兰内尔", "毡": "费尔特", "毡布": "费尔特", "毡子": "费尔特", "毛毡": "费尔特",
    "衣架式骨折固定器": "挂骨者", "骨架挂钩": "挂骨者", "骨挂": "挂骨者", "骨架悬挂者": "挂骨者",
    "快乐的衣橱": "快乐衣柜", "不可动摇的": "不可动摇者", "副厨师长": "副主厨", "副厨": "副主厨",
    "Le Noir波特": "Le Noir 搬运工", "Le Rouge波特": "Le Rouge 搬运工", "Le Noir门卫": "Le Noir 门卫",
    "勒卡基": "Le Kaki", "那位暴怒神": "深红之神", "垂死的Noir": "垂死的 Noir",
    "排队Noir": "排队的 Noir", "一个流氓的尸体": "一具 Le Rouge 成员的尸体",
    "流氓的尸体": "Le Rouge 成员的尸体",
}

#: 逐条定点修正：(文件, key, 字段) → 新译文
TARGETED: dict[tuple[str, str, str], str] = {
    ("BattleSpeechBubbleDlg-a1c10p1.json", "10SV-095", "dlg"): "一闪……一闪……亮晶晶……",
    ("BattleSpeechBubbleDlg-a1c10p1.json", "10SV-097", "dlg"): "别……笑……！哈……！",
    ("BattleSpeechBubbleDlg-a1c10p1.json", "10SV-098", "dlg"): "啊……！嗯……！",
    ("Enemies-a1c10p1.json", "12008", "name"): "同步 & 异想解析",
}


def normalize(text: str) -> str:
    out = text
    out = re.sub(r"…\s*([!?])", lambda m: "……" + ("！" if m.group(1) == "!" else "？"), out)
    out = out.replace("!!", "！！").replace("??", "？？").replace("!", "！").replace("?", "？")
    out = re.sub(r"(?<=[\u4e00-\u9fff])\.", "。", out)
    out = re.sub(r"…{3,}", "……", out)
    for wrong, right in FIXES.items():
        if wrong != right and wrong in out:
            out = out.replace(wrong, right)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    terms = mt.term_map()
    retranslated = fixed_names = empty = 0
    files = sorted(mf.OUT.rglob("*.json")) if mf.OUT.is_dir() else []
    for path in files:
        rel = path.relative_to(mf.OUT).as_posix()
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        changed = 0

        def rec(node, key_hint=""):
            nonlocal changed, retranslated, fixed_names, empty
            if isinstance(node, dict):
                key = str(node.get("key") or node.get("id") or key_hint)
                for k, v in list(node.items()):
                    if isinstance(v, str):
                        if k in SKIP_FIELDS or not v.strip():
                            if k not in SKIP_FIELDS and isinstance(v, str) and not v.strip():
                                empty += 1
                            continue
                        new = normalize(v)
                        if k in NAME_FIELDS:
                            for wrong, right in NAME_FIXES.items():
                                if wrong != right and wrong in new:
                                    new = new.replace(wrong, right)
                                    fixed_names += 1 if False else 0
                        if LATIN_ONLY.match(v.strip()) and LATIN.search(v):
                            got = mt.translate_and_restore(v, terms) if hasattr(mt, "translate_and_restore") else None
                            if got is None:
                                masked, mapping = mt.protect(v, terms)
                                got = mt.normalize_zh(mt.restore(mt.gt(masked) or v, mapping))
                            if got.strip() and not mt._placeholder_left(got) and got.strip() != v.strip():
                                new = got
                                retranslated += 1
                        tgt = TARGETED.get((rel, key, k))
                        if tgt:
                            new = tgt
                            fixed_names += 1
                        if new != v:
                            node[k] = new
                            changed += 1
                    elif isinstance(v, (dict, list)):
                        rec(v, key)
            elif isinstance(node, list):
                for item in node:
                    rec(item, key_hint)

        rec(data)
        if changed and not args.dry_run:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        if changed:
            print(f"  {rel}: {changed} 处")
    print(f"规范化/改名 {fixed_names} 处 · 补译残留英文 {retranslated} 处 · 空字段 {empty} 处"
          + ("（--dry-run）" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
