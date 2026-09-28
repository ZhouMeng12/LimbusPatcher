# -*- coding: utf-8 -*-
"""按零协译法统一 Le Rouge / Le Noir 相关译名（第十章）。

规则优先级：
0. PROTECT：法文专名整体保护，不做任何替换
1. EXACT ：整字段精确替换（零协术语表对齐）
2. SUBSTR：子串替换（术语名、商品名，含被引用的 desc）
3. REGEX ：通用内联替换（长句正文），并清理替换后残留的多余空格
用法：
    python scripts/ch10p2_unify_terms.py           # dry-run -> _term_diff.txt
    python scripts/ch10p2_unify_terms.py --apply   # 落盘
"""
import io
import json
import os
import re
import sys

ROOT = r"D:\Desktop\lbc"
DIFF = os.path.join(ROOT, "_term_diff.txt")

# 0) 法文专名：整体保护
PROTECT = [
    "Maison du Noir",
    "Le Trou Rouge",
    "Le Président",
    "Café de Flore",
    "Le Kaki",
    "L'Inamovible",
]
SENT = "@@P%d@@"

# 1) 整字段精确替换
EXACT = {
    "Le Noir销售助理 Gustave": "黑派店员 居斯塔夫",
    "Le Rouge销售助理 Mimosa": "红派店员 含羞草",
    "Le Noir销售助理[Sunshone]": "黑派店员[阳光]",
    "Le Rouge销售助理[Sunshone]": "红派店员[阳光]",
    "Le Noir Footwear Hall": "黑派制鞋馆",
    "Le Rouge人偶": "红派人台",
    "Le Rouge": "红派",
    "Le Noir": "黑派",
}

# 2) 子串替换（零协术语；含 desc 中被引用的术语名）
SUBSTR = [
    ("Boutique du Rouge", "红派精品店"),
    ("Le Noir：华达呢大衣", "黑派 华达呢大衣"),
    ("Le Noir：精梳毛呢", "黑派 精纺面料"),
    ("Le Noir：华达呢布料", "黑派 华达呢面料"),
    ("Le Noir：布料", "黑派面料"),
    ("Le Rouge：夹克", "红派 夹克"),
    ("Le Noir 鞋履厅", "黑派制鞋馆"),
]

# 3) 通用内联替换
RE_LE = re.compile(r"Le (Noir|Rouge)")
RE_BARE = re.compile(r"(?<![A-Za-z\[])(Noir|Rouge)(?![A-Za-z\])])")
ZH = "\u4e00-\u9fff\u3000-\u303f\uff00-\uffef"
RE_SP_BEFORE = re.compile(r"([%s]) (红派|黑派)" % ZH)
RE_SP_AFTER = re.compile(r"(红派|黑派) ([%s])" % ZH)

TEXT_KEYS = {"text", "name", "title", "desc", "content", "speaker", "teller",
             "castName", "place", "location", "label", "zh"}

SCAN_DIRS = [
    os.path.join(ROOT, "data", "translate", "files"),
    os.path.join(ROOT, "data", "translate", "zh"),
    os.path.join(ROOT, "data", "translate", "out", "zh"),
]


def convert(v):
    if not isinstance(v, str):
        return v
    if v in EXACT:
        return EXACT[v]
    # 保护法文专名
    new = v
    store = []
    for i, p in enumerate(PROTECT):
        if p in new:
            store.append((i, p))
            new = new.replace(p, SENT % i)
    for a, b in SUBSTR:
        # \x00 标记该空格为“零协风格空格”，后续清理时跳过
        new = new.replace(a, b.replace(" ", "\x00"))
    new = RE_LE.sub(lambda m: "黑派" if m.group(1) == "Noir" else "红派", new)
    new = RE_BARE.sub(lambda m: "黑派" if m.group(1) == "Noir" else "红派", new)
    # 清理替换后残留的多余空格：中文 + 空格 + 红派/黑派（+ 空格 + 中文）
    new = RE_SP_BEFORE.sub(r"\1\2", new)
    new = RE_SP_AFTER.sub(r"\1\2", new)
    new = new.replace("\x00", " ")
    for i, p in store:
        new = new.replace(SENT % i, p)
    return new


def walk(obj, path, out, apply):
    changed = False
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            v = obj[k]
            if k in TEXT_KEYS and isinstance(v, str):
                nv = convert(v)
                if nv != v:
                    out.write("  %s\n    - %s\n    + %s\n" % (path + "/" + k, v, nv))
                    if apply:
                        obj[k] = nv
                    changed = True
            else:
                if walk(v, path + "/" + str(k), out, apply):
                    changed = True
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if walk(v, path + "[%d]" % i, out, apply):
                changed = True
    return changed


def main():
    apply = "--apply" in sys.argv
    out = io.open(DIFF, "w", encoding="utf-8", buffering=1)
    files = []
    for base in SCAN_DIRS:
        for dirpath, dirnames, filenames in os.walk(base):
            for fn in filenames:
                if fn.endswith(".json"):
                    files.append(os.path.join(dirpath, fn))
    touched = 0
    for p in sorted(files):
        try:
            d = json.load(io.open(p, encoding="utf-8"))
        except Exception:
            continue
        out.write("== %s\n" % os.path.relpath(p, ROOT))
        if walk(d, "", out, apply):
            touched += 1
            if apply:
                io.open(p, "w", encoding="utf-8").write(
                    json.dumps(d, ensure_ascii=False, indent=2))
    out.write("\nfiles touched=%d\n" % touched)
    out.close()


if __name__ == "__main__":
    main()
