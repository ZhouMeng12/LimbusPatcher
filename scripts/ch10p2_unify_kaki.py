# -*- coding: utf-8 -*-
"""Kaki → 褐派（零协：Hungry Kaki=饥饿的褐派 / Thirsty Kaki=干渴的褐派）。

我们早先把 Kaki 音译成「卡基」，与零协不一致，本脚本按零协对齐。
用法： python scripts/ch10p2_unify_kaki.py [--apply]
"""
import io
import json
import os
import sys

ROOT = r"D:\Desktop\lbc"
OUT = os.path.join(ROOT, "_kaki_diff.txt")
SCAN = [
    os.path.join(ROOT, "data", "translate", "files"),
    os.path.join(ROOT, "data", "translate", "zh"),
    os.path.join(ROOT, "data", "translate", "out", "zh"),
]
PAIRS = [
    ("饥渴的卡基", "干渴的褐派"),
    ("饥饿的卡基", "饥饿的褐派"),
    ("卡基族", "褐派"),
    ("卡基", "褐派"),
]
KEYS = {"text", "name", "title", "desc", "content", "flavor", "speaker", "zh", "label"}


def conv(v):
    if not isinstance(v, str) or "卡基" not in v:
        return v
    new = v
    for a, b in PAIRS:
        new = new.replace(a, b)
    return new


def walk(obj, path, out, apply):
    changed = False
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            v = obj[k]
            if k in KEYS and isinstance(v, str):
                nv = conv(v)
                if nv != v:
                    out.write("  %s\n    - %s\n    + %s\n" % (path + "/" + k, v, nv))
                    if apply:
                        obj[k] = nv
                    changed = True
            elif walk(v, path + "/" + str(k), out, apply):
                changed = True
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if walk(v, path + "[%d]" % i, out, apply):
                changed = True
    return changed


def main():
    apply = "--apply" in sys.argv
    out = io.open(OUT, "w", encoding="utf-8", buffering=1)
    files = []
    for base in SCAN:
        for dp, dn, fns in os.walk(base):
            for fn in fns:
                if fn.endswith(".json"):
                    files.append(os.path.join(dp, fn))
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
                io.open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2))
    out.write("\nfiles touched=%d\n" % touched)
    out.close()


if __name__ == "__main__":
    main()
