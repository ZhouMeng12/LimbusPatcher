"""第10章第二部分（a1c10p2）答案体检：逐批核对键、方括号 id、标签、占位符、换行、残留语言。

    python scripts/ch10p2_check.py            # 全部批次
    python scripts/ch10p2_check.py --fix      # 能自动修的（补回缺失的 [id] / 标签 / 占位符）直接改
    python scripts/ch10p2_check.py -v         # 打印每条问题

规则来自 data/translate/ch10p2/翻译规则.md：
  · desc/summary/statText/effect/... 里的 [EffectId] 必须与英文一字不差；
  · <color=…>/<i>/<b>/<u>/<mark …> 等标签、{0}{1} 占位符、换行数量必须原样；
  · 名字字段里的方括号是描述文字（要翻，且方括号前不留空格）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import ch10p2_prep as P  # noqa: E402

WORK = ROOT / "data" / "translate" / "ch10p2"
TASKS, ANS = WORK / "tasks", WORK / "ans"

#: 只认真正的游戏富文本标签；但丁的 <内心台词> 也是用尖括号包的，不能当标签比
_TAG = re.compile(
    r"</?(?:i|b|u|s)>"                       # 无属性标签（但丁的 <I ...> 内心台词不能算）
    r"|</?(?:color|size|mark|style|sprite|link|material|key|input|ruby|nobr|br|font|sub|sup)"
    r"(?=[\s=/>])[^<>]*>",
    re.I,
)
_BRACKET = re.compile(r"\[[^\[\]]+\]")
_PLACE = re.compile(r"\{\d+\}")
_HANGUL = re.compile(r"[가-힯]")
#: 去掉 [id]/标签/占位符/数字/标点之后还剩不剩「自然语言」
_NATURAL = re.compile(r"[A-Za-z]{2,}")


def has_natural_language(en: str) -> bool:
    """原文去掉 [id]、标签、占位符、数字与标点之后，还剩不剩要翻的自然语言。"""
    t = _BRACKET.sub("", en)
    t = _TAG.sub("", t)
    t = _PLACE.sub("", t)
    t = re.sub(r"[0-9\s%+\-–—.,:;!?'\"/()\*&→←…·=]", "", t)
    return bool(_NATURAL.search(t))
#: 允许在译文里出现的拉丁字符（专名/缩写/游戏术语）
ALLOW_LATIN = re.compile(r"^(E\.G\.O|SP|HP|MP|B\d+F?|\d+F|LCB|N Corp\.?|W Corp\.?|T Corp\.?|K Corp\.?|"
                         r"C\.H\.|G\.B\.|S\.H\.N\.C\.|S\.Y\.N\.C\.|G\.Y\.B\.|L\.B\.|"
                         r"[A-Z]\.|[A-Za-z]+é|Mme|La |Le |L')")



_TAG_ANY = re.compile(r"</?[a-zA-Z][^<>]*>")


def autofix(en: str, zh: str) -> tuple[str, list[str]]:
    """能机械修的标签问题：镜像英文的标签写法；整段被 <i> 包住时补/去包裹。

    返回 (修好的译文, 修了什么)；修不了的返回原样 + 说明。
    """
    notes: list[str] = []
    # 0) 标签数量相同但写法/闭合顺序不同（<mark=#..> ↔ <mark color=#..>、</u></b> ↔ </b></u>）
    #    → 整段按英文的标签序列重写，里面的中文一个字不动
    en_tags, zh_tags = _TAG.findall(en), _TAG.findall(zh)
    if en_tags and len(en_tags) == len(zh_tags) and en_tags != zh_tags:
        it = iter(en_tags)
        zh = _TAG.sub(lambda m: next(it, m.group(0)), zh)
        notes.append("标签序列已对齐英文")
        en_tags, zh_tags = _TAG.findall(en), _TAG.findall(zh)
    # 1) 同一批标签，属性写法不同（<mark=#ff000040> ↔ <mark color=#ff000040>）→ 镜像英文
    for name in ("mark", "color", "size", "style"):
        pat = re.compile(r"</?%s[^<>]*>|</?%s=[^<>]*>" % (name, name), re.I)
        en_tags, zh_tags = pat.findall(en), pat.findall(zh)
        if len(en_tags) == len(zh_tags) and en_tags != zh_tags:
            for et in en_tags:
                zh = zh.replace(next(z for z in zh_tags if z.split("=")[0].split()[0].lower()
                                     == et.split("=")[0].split()[0].lower()), et, 1)
            notes.append(f"{name} 标签写法已对齐英文")
    # 1.5) 整段被单一标签包住（如 <color=#ebcaa2>…</color>），译文把标签丢了 → 补回
    m = re.fullmatch(r"(<[^<>]+>)(.*?)(</[^<>]+>)", en, re.S)
    if m and not _TAG.search(zh):
        open_tag, _inner, close_tag = m.groups()
        name = open_tag[1:].split("=")[0].split()[0].strip()
        if close_tag.lower() == f"</{name.lower()}>":
            zh = f"{open_tag}{zh}{close_tag}"
            notes.append(f"补回整段 {open_tag}")

    # 2) 整段 <i>/<b>/<u>/<s> 包裹差异
    for name in ("i", "b", "u", "s"):
        op, cl = f"<{name}>", f"</{name}>"
        en_o, en_c = en.count(op), en.count(cl)
        zh_o, zh_c = zh.count(op), zh.count(cl)
        if en_o == zh_o and en_c == zh_c:
            continue
        if en_o == 1 and en_c == 1 and zh_o == 0 and zh_c == 0:
            zh = f"{op}{zh}{cl}"
            notes.append(f"补回整段 {op}")
        elif en_o == 0 and en_c == 0 and zh_o == 1 and zh_c == 1:
            zh = zh.replace(op, "", 1).replace(cl, "", 1)
            notes.append(f"去掉多余的 {op}")
    return zh, notes


def fields_of(batch: dict) -> dict:
    return {it["ids"][0]: it for it in batch["items"]}


def check_batch(batch_path: Path, verbose: bool, fix: bool = False) -> tuple[list[str], Counter]:
    name = batch_path.stem
    ans_path = ANS / f"{name}.json"
    problems: list[str] = []
    stat: Counter = Counter()
    if not ans_path.is_file():
        return [f"{name}: 缺答案文件"], stat
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    ans = json.loads(ans_path.read_text(encoding="utf-8-sig"))
    items = fields_of(batch)

    missing = [k for k in items if k not in ans]
    extra = [k for k in ans if k not in items]
    if missing:
        problems.append(f"{name}: 缺 {len(missing)} 条（例 {missing[:2]}）")
    if extra:
        problems.append(f"{name}: 多出 {len(extra)} 条（例 {extra[:2]}）")

    fixed_keys = []
    for key, it in items.items():
        zh = ans.get(key)
        if fix and isinstance(zh, str) and zh.strip():
            new_zh, notes = autofix(it["en"], zh)
            if new_zh != zh:
                ans[key] = zh = new_zh
                fixed_keys.append(key)
        if not isinstance(zh, str) or not zh.strip():
            stat["空译文"] += 1
            problems.append(f"{name}/{key}: 译文为空")
            continue
        en = it["en"]
        field = str(it.get("field") or "")
        # 1) 说明字段里的效果 id 必须一字不差
        if field in P.DESC_FIELDS:
            # 只比「数量集合」：中文语序可以不同（[A] 与 [B] 互换位置是对的）
            en_ids, zh_ids = Counter(_BRACKET.findall(en)), Counter(_BRACKET.findall(zh))
            if en_ids != zh_ids:
                stat["方括号 id 不一致"] += 1
                problems.append(f"{name}/{key}: [id] 不一致 EN={dict(en_ids)} ZH={dict(zh_ids)}")
        # 2) 标签 / 占位符 / 换行
        if Counter(_TAG.findall(en)) != Counter(_TAG.findall(zh)):
            stat["标签不一致"] += 1
            problems.append(f"{name}/{key}: 标签不一致 EN={Counter(_TAG.findall(en))} ZH={Counter(_TAG.findall(zh))}")
        if Counter(_PLACE.findall(en)) != Counter(_PLACE.findall(zh)):
            stat["占位符不一致"] += 1
            problems.append(f"{name}/{key}: 占位符不一致 EN={_PLACE.findall(en)} ZH={_PLACE.findall(zh)}")
        if en.count("\n") != zh.count("\n"):
            stat["换行数不一致"] += 1
            problems.append(f"{name}/{key}: 换行 {en.count(chr(10))} → {zh.count(chr(10))}")
        # 3) 残留语言
        if _HANGUL.search(zh):
            stat["韩文残留"] += 1
            problems.append(f"{name}/{key}: 韩文残留 {zh[:30]}")
        if zh.strip() == en.strip() and has_natural_language(en):
            stat["未翻译（同英文）"] += 1
            problems.append(f"{name}/{key}: 与英文完全相同")
        stat["条目"] += 1
    if fixed_keys:
        ans_path.write_text(json.dumps(ans, ensure_ascii=False, indent=0), encoding="utf-8")
        stat["已自动修"] = len(fixed_keys)
    if verbose:
        for p in problems:
            print("   ", p)
    return problems, stat


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--batch", default=None, help="只查某一个批次，如 batch_016")
    ap.add_argument("--fix", action="store_true", help="能机械修的标签问题直接写回答案文件")
    args = ap.parse_args()

    tasks = sorted(TASKS.glob("batch_*.json"))
    if args.batch:
        tasks = [p for p in tasks if p.stem == args.batch]
    total: Counter = Counter()
    all_problems: list[str] = []
    for tp in tasks:
        problems, stat = check_batch(tp, args.verbose, fix=args.fix)
        total += stat
        all_problems += problems
        tag = "OK " if not problems else "!! "
        print(f"{tag}{tp.stem}: {stat['条目']} 条, 问题 {len(problems)}"
              + (f", 自动修 {stat['已自动修']}" if stat.get("已自动修") else ""))
    print(f"\n合计 {sum(1 for _ in tasks)} 批 / {total['条目']} 条")
    if all_problems:
        print("问题分类:", {k: v for k, v in total.items() if k != "条目"})
        print(f"（共 {len(all_problems)} 条问题，加 -v 看明细）")
        return 1
    print("全部通过 ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
