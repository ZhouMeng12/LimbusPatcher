"""补翻第十章里**空着**的字段（英文基线有内容、译文却是空串）。

为什么会空：早期 merge/切片时按结构建了记录，但有些字段没被翻到（RPG 任务面板、
Bufs 的部分 buff、Passives_Enemy 的几条），部署到游戏里就是一片空白。
本脚本只填空字段，不碰已有译文；术语/方括号/标签照旧占位符保护。

用法：
    python scripts/fill_missing_ch10.py                # 全部第十章文件
    python scripts/fill_missing_ch10.py --files A.json
    python scripts/fill_missing_ch10.py --dry-run
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
import mt_files as mf  # noqa: E402
import mt_translate as mt  # noqa: E402
import repair_ch10 as rc  # noqa: E402

HANGUL = re.compile(r"[\uac00-\ud7af]")


def translate(text: str) -> str:
    """整段翻译（韩文源走 ko→zh），术语与方括号占位符保护。"""
    terms = mt.term_map()
    src = "ko" if HANGUL.search(text) else "en"
    masked, mapping = mt.protect(text, terms)
    got = rc._mt_segment(masked, src)
    if not got:
        return ""
    out = mt.normalize_zh(mt.restore(got, mapping))
    if not out.strip() or mt._placeholder_left(out):
        return ""
    return out


def fill_node(node, en_node, out: list, path: tuple = ()) -> None:
    """按 (键, 路径) 对照英文基线，把译文里的空串补上。"""
    if isinstance(node, dict) and isinstance(en_node, dict):
        for k, v in list(node.items()):
            if k not in en_node:
                continue
            if isinstance(v, str):
                src = en_node[k]
                if isinstance(src, str) and src.strip() and not v.strip():
                    out.append((node, k, src, path + (k,)))
            else:
                fill_node(v, en_node[k], out, path + (k,))
    elif isinstance(node, list) and isinstance(en_node, list):
        for i, v in enumerate(node):
            if i >= len(en_node):
                break
            if isinstance(v, str):
                src = en_node[i]
                if isinstance(src, str) and src.strip() and not v.strip():
                    out.append((node, i, src, path + (i,)))
            else:
                fill_node(v, en_node[i], out, path + (i,))


def run_file(rel: str, dry: bool = False) -> dict:
    path, en = rc._resolve(rel)
    if path is None or en is None or not Path(en).is_file():
        return {"rel": rel, "ok": False, "reason": "缺文件"}
    zh_data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    en_data = json.loads(Path(en).read_text(encoding="utf-8-sig"))
    todo: list = []
    fill_node(zh_data, en_data, todo)
    filled, failed = 0, 0
    for container, key, src, _path in todo:
        got = translate(src)
        if got:
            container[key] = got
            filled += 1
        else:
            failed += 1
    if filled and not dry:
        path.write_text(json.dumps(zh_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if "/" in rel or Path(rel).name != rel:
            pass
    return {"rel": rel, "ok": True, "empty": len(todo), "filled": filled, "failed": failed}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    names = args.files or (mf.CH10_FILES + mf.RPG_FILES)
    tot = {"empty": 0, "filled": 0, "failed": 0}
    for rel in names:
        res = run_file(rel, dry=args.dry_run)
        if not res.get("ok"):
            print(f"  {rel}: {res.get('reason')}")
            continue
        for k in tot:
            tot[k] += res.get(k, 0)
        if res["empty"]:
            print(f"  {rel}: 空 {res['empty']} → 补齐 {res['filled']}（失败 {res['failed']}）")
    print(f"合计：空字段 {tot['empty']} · 已补 {tot['filled']} · 失败 {tot['failed']}"
          + ("（--dry-run，未写盘）" if args.dry_run else ""))
    return 0 if tot["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
