"""机翻稿质量体检：挑出需要人工修的句子（术语、标签、残留英文、疑似截断）。

用法：
    python scripts/qa_review.py                 # 汇总
    python scripts/qa_review.py S1004B          # 只看某个文件（打印 EN/ZH 对照）
    python scripts/qa_review.py --all-lines S1012B   # 打印该文件全部行（逐行过一遍用）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import translate_pack as tp  # noqa: E402

TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s*=\s*[^>]*)?>")
LATIN_WORD = re.compile(r"[A-Za-z]{3,}")
KEEP_LATIN = {"E.G.O", "N", "T", "K", "L", "W", "U", "J", "G", "C", "M", "S", "A", "B",
              "Le", "Rouge", "ma", "puce", "Flore", "Royal", "vin", "coq", "au", "Nelly",
              "Sisyphe", "Corp"}
PLACEHOLDER_LEAK = re.compile(r"[《〖【『]?\s*\d{1,2}\s*[》〗】』]|@@\d+@@")


def qa_lines(name: str) -> list[tuple[int, str, str, list[str]]]:
    en = [r for r in tp.records(name) if isinstance(r, dict) and r.get("content")]
    p = tp.ZH_DIR / f"{name}.json"
    if not p.is_file():
        return []
    zh = json.loads(p.read_text(encoding="utf-8")).get("lines") or {}
    out = []
    for r in en:
        rid = str(r.get("id"))
        e = str(r.get("content") or "")
        z = str(zh.get(rid) or "")
        issues = []
        if not z.strip():
            issues.append("空译")
        else:
            if PLACEHOLDER_LEAK.search(z):
                issues.append("占位符泄漏")
            if "*" in z and z.count("*") % 2 == 1:
                issues.append("动作标记未收敛")
            if "*" in z and re.search(r"\*[A-Za-z]+\*", z):
                issues.append("英文动作标记")
            for word in LATIN_WORD.findall(TAG_RE.sub("", z)):
                if word not in KEEP_LATIN and not word.isupper() and len(word) > 3:
                    issues.append(f"残留英文 {word}")
                    break
            if TAG_RE.findall(e) and len(TAG_RE.findall(z)) != len(TAG_RE.findall(e)):
                issues.append("标签数不一致")
            # 中文比英文紧凑：按「英文词数 × 1.6 字」估期望长度
            expect = max(len(TAG_RE.sub("", e).split()) * 1.6, 4)
            ratio = len(TAG_RE.sub("", z)) / expect
            if ratio < 0.5:
                issues.append(f"疑似过短({ratio:.2f})")
        if issues:
            out.append((r.get("id"), e, z, issues))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--all-lines", action="store_true")
    args = ap.parse_args()
    names = args.names or tp.STORY_FILES
    total = 0
    for name in names:
        rows = qa_lines(name)
        total += len(rows)
        print(f"== {name}: {len(rows)} 行待看")
        if args.names or args.all_lines:
            for rid, e, z, issues in rows:
                print(f"  #{rid} [{', '.join(issues)}]")
                print(f"     EN: {e[:150]}")
                print(f"     ZH: {z[:150]}")
    print(f"\n合计待看 {total} 行 / 1105")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
