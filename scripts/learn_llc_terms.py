"""学零协的术语：把零协包的英文↔中文按记录 id 对齐，抽出「名词级」术语，
再和我们自己的术语表/审定新词对照，列出冲突并（可选）按零协口径统一。

为什么：零协是译名的唯一权威。我们为了翻第十章自己定过一批词（审定新词.json），
零协更新后他们有了官方译法，必须**以他们为准**，并且把仍在用的补译文件改过来。

用法：
    python scripts/learn_llc_terms.py                 # 学习 + 冲突报告（只读）
    python scripts/learn_llc_terms.py --chapter 10     # 只看第十章相关文件学到的词
    python scripts/learn_llc_terms.py --apply          # 按零协口径更新 审定新词.json / glossary.json
    python scripts/learn_llc_terms.py --apply --files   # 再把仍在用的补译文件里的旧译名换成零协译名

产物：
    data/translate/零协术语.json        学到的术语（英文 → 中文 + 出处）
    data/translate/术语冲突.md          我们的译名 vs 零协译名的差异清单
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import build_glossary as bg  # noqa: E402
import mt_files as mf  # noqa: E402
import translate_pack as tp  # noqa: E402

WORK = ROOT / "data" / "translate"
LEARNED = WORK / "零协术语.json"
CONFLICTS = WORK / "术语冲突.md"
DECIDED = WORK / "审定新词.json"
CH10_RE = re.compile(r"a1c10|c10", re.I)


def learn(chapter: int | None = None) -> dict[str, dict]:
    """按 id 配对学名词；chapter 给定时只用该章的文件（如第十章 a1c10*）。"""
    terms: dict[str, dict] = {}
    tables: dict[str, str] = dict(bg.NAME_TABLES)
    if chapter is not None:
        keep = {}
        for table, kind in tables.items():
            en = tp.EN_STORY.parent / f"EN_{table}.json"
            if not en.is_file():
                keep[table] = kind            # 基础表（没有章节号）保留
                continue
            hits = list(en.parent.glob(f"EN_{table.replace('.json','')}*a1c{chapter}*.json"))
            if hits:
                for h in hits:
                    keep[h.name[3:-5]] = kind
            else:
                keep[table] = kind
        tables = keep
    for table, kind in tables.items():
        pairs = bg.by_id(tp.ZH_STORY.parent / f"{table}.json",
                         tp.EN_STORY.parent / f"EN_{table}.json")
        for rid, fields in pairs.items():
            for fp, en_text in fields.items():
                if fp.startswith("#zh:"):
                    continue
                leaf = fp.split(".")[-1].split("[")[0]
                if leaf not in bg.NAME_FIELDS:
                    continue
                zh_text = (fields.get(f"#zh:{fp}") or "").strip()
                en_text = (en_text or "").strip()
                if not en_text or not zh_text or en_text == zh_text:
                    continue
                if len(en_text) > 80 or len(zh_text) > 40:
                    continue
                terms[en_text] = {"zh": zh_text, "kind": kind, "file": table, "id": rid}
    return terms


def _flat(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def conflicts(learned: dict[str, dict]) -> list[tuple[str, str, str, str]]:
    """(英文, 我们的译名, 零协译名, 来源) —— 只列不一致的（纯空白差异不算）。"""
    ours: dict[str, str] = {}
    for src, name in ((DECIDED, "审定新词"),
                      (WORK / "glossary.json", "术语表")):
        if not src.is_file():
            continue
        data = json.loads(src.read_text(encoding="utf-8"))
        for en, info in (data.get("terms") or {}).items():
            zh = info.get("zh") if isinstance(info, dict) else str(info)
            if zh:
                ours.setdefault(en, zh)
    out = []
    for en, info in learned.items():
        mine = ours.get(en)
        if mine and _flat(mine) != _flat(info["zh"]):
            out.append((en, mine, info["zh"], info["file"]))
    return out


def apply_terms(learned: dict[str, dict], rows: list[tuple[str, str, str, str]]) -> int:
    """把零协译名写进审定新词.json（零协优先）。"""
    obj = json.loads(DECIDED.read_text(encoding="utf-8")) if DECIDED.is_file() else {}
    terms = obj.setdefault("terms", {})
    n = 0
    for en, _mine, theirs, _file in rows:
        if terms.get(en) != theirs:
            terms[en] = theirs
            n += 1
    obj["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
    obj["note"] = "零协官方译名优先（learn_llc_terms.py --apply 写入）"
    DECIDED.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return n


def apply_to_files(rows: list[tuple[str, str, str, str]]) -> int:
    """把仍在用的补译文件/译文里的旧译名换成零协译名。"""
    pairs = [(mine, theirs) for _en, mine, theirs, _f in rows if mine and theirs and mine != theirs]
    if not pairs:
        return 0
    changed = 0
    roots = [ROOT / "data" / "translate" / "files", ROOT / "data" / "translate" / "zh"]
    for root in roots:
        for p in sorted(root.rglob("*.json")):
            text = p.read_text(encoding="utf-8-sig")
            new = text
            for mine, theirs in pairs:
                if mine in new and mine != theirs:
                    new = new.replace(mine, theirs)
            if new != text:
                p.write_text(new, encoding="utf-8")
                changed += 1
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", type=int, default=None)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--files", action="store_true", help="同时把译文里的旧译名换成零协译名")
    args = ap.parse_args()

    learned = learn(args.chapter)
    target = LEARNED if args.chapter is None else LEARNED.with_name(f"零协术语-第{args.chapter}章.json")
    target.write_text(json.dumps({"note": "从零协包按记录 id 学到的名词级术语",
                                   "count": len(learned), "terms": learned},
                                  ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"学到术语 {len(learned)} 条 → {target}")

    rows = conflicts(learned)
    print(f"与我们译名冲突 {len(rows)} 条")
    for en, mine, theirs, file in rows[:25]:
        print(f"  {en}\n    我们：{mine}   零协：{theirs}   （{file}）")
    if rows:
        lines = ["# 术语冲突：我们 vs 零协（零协优先）", "",
                 f"共 {len(rows)} 条。零协是唯一权威，`--apply` 会写进 "
                 "`data/translate/审定新词.json` 并（加 `--files`）改掉译文里的旧译名。", ""]
        for en, mine, theirs, file in rows:
            lines.append(f"- `{en}`（{file}）：我们「{mine}」→ 零协「{theirs}」")
        CONFLICTS.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"清单 → {CONFLICTS}")
    if args.apply:
        n = apply_terms(learned, rows)
        print(f"审定新词已更新 {n} 条")
        if args.files:
            print(f"译文文件已替换旧译名：{apply_to_files(rows)} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
