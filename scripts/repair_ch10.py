"""第十章译文修复：
1) **方括号关键词还原**：`[Bleed]`/`[CombatStart]` 这类是游戏内部 id，绝不能翻——
   按英文基线把方括号里的内容原样还原（结构与英文基线一一对应）；
2) **字体安全**：`〈〉`/`「」`/`［］` 换成零协在用的写法，繁体字转简体
   （游戏字体缺这些字形会显示成口口）；
3) **残留韩文**：英文基线里本来就是韩文的字段，走 ko→zh 补译。

用法：
    python scripts/repair_ch10.py                      # 全部第十章文件
    python scripts/repair_ch10.py --files A.json B.json
    python scripts/repair_ch10.py --dry-run            # 只看会改多少
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import mt_engines  # noqa: E402
import mt_files as mf  # noqa: E402
import mt_translate as mt  # noqa: E402

BRACKET = re.compile(r"\[[^\]\n]{0,60}\]")
HANGUL = re.compile(r"[\uac00-\ud7af]")
SKIP_FIELDS = {"id", "model", "key", "code"}
#: 说明类字段里的 [X] 是游戏内部效果 id（翻了就显示 UNKNOWN）→ 一律按英文基线还原
ID_FIELDS = {"desc", "summary", "statText", "effect", "lowMoraleDescription", "panicDescription"}
#: 名字类字段里的方括号是描述（零协译作「噗扭扭[橙子味]」）→ 保留译文，只收拾空格
NAME_FIELDS = {"name", "title", "displayName", "panicName", "keywordName", "flavor"}
#: 像 id 的方括号内容（驼峰/下划线/大写缩写）→ 无论哪个字段都原样还原
ID_LIKE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,39}$")


def _looks_like_id(content: str) -> bool:
    if not ID_LIKE.match(content):
        return False
    return "_" in content or any(c.isupper() for c in content[1:]) or content.isupper()

#: 字体安全替换（换成零协在用的标点 / 简体写法）
CHAR_FIX = {
    "〈": "《", "〉": "》", "「": "“", "」": "”",
    "［": "[", "］": "]", "｛": "{", "｝": "}",
    "體": "体", "蟲": "虫", "國": "国", "學": "学", "來": "来", "們": "们",
    "為": "为", "說": "说", "這": "这", "裡": "里", "麼": "么",
    "…!": "……！", "…?": "……？",
}

_en_map: dict = {}
_stat: dict = {}


def en_strings(node, out: dict, path: tuple = ()) -> dict:
    """英文基线的「路径 → 文本」表（与译文结构一一对应）。"""
    if isinstance(node, dict):
        for k, v in node.items():
            en_strings(v, out, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            en_strings(v, out, path + (i,))
    elif isinstance(node, str):
        out[path] = node
    return out


def _mt_segment(text: str, src: str) -> str | None:
    return mt_engines.translate(text, "bing", src=src)


def translate_text(text: str) -> str:
    """整段补译（韩文走 ko→zh），术语与标签照旧占位符保护。"""
    terms = mt.term_map()
    src = "ko" if HANGUL.search(text) else "en"
    masked, mapping = mt.protect(text, terms)
    pieces, buf = [], []
    for line in masked.split("\n"):
        buf.append(line)
        if sum(len(x) for x in buf) > 700:
            pieces.append(_mt_segment("\n".join(buf), src) or "\n".join(buf))
            buf = []
    if buf:
        pieces.append(_mt_segment("\n".join(buf), src) or "\n".join(buf))
    got = "\n".join(pieces)
    if not got.strip() or got == masked:
        return text
    return mt.normalize_zh(mt.restore(got, mapping))


def _restore_brackets(new: str, en_text: str, keep_all: bool, field: str) -> str:
    """把方括号内容按英文基线还原。

    说明类字段（desc 等）里的 `[X]` 是游戏内部效果 id，翻了游戏里就显示 UNKNOWN →
    按**行**对齐后逐个还原（零协也是这么做的：`[Laceration]`、`[AttackUp]` 原样保留）。
    名字/正文里的方括号只有"像 id"的才还原。
    """
    def _fix(zl: str, el: str) -> str:
        want = [b for b in BRACKET.findall(el) if not HANGUL.search(b)]
        if not want:
            return zl
        have = BRACKET.findall(zl)
        for a, b in zip(want, have):
            if a == b:
                continue
            if not (keep_all or field not in NAME_FIELDS or _looks_like_id(a[1:-1])):
                continue
            zl = zl.replace(b, a, 1)
            _stat["brackets"] += 1
        for extra in want[len(have):]:
            if (not keep_all and field in NAME_FIELDS) or not _looks_like_id(extra[1:-1]):
                continue
            if extra not in zl:
                zl = (zl.rstrip() + " " + extra).strip()
                _stat["brackets"] += 1
        return zl

    zh_lines = new.split("\n")
    en_lines = en_text.split("\n")
    if len(zh_lines) == len(en_lines):
        return "\n".join(_fix(zl, el) for zl, el in zip(zh_lines, en_lines))
    return _fix(new, en_text)


def _handle(container, key, path_: tuple, text: str) -> None:
    new = text
    en_text = _en_map.get(path_)
    field = key if isinstance(key, str) else ""
    if isinstance(en_text, str) and BRACKET.search(en_text):
        new = _restore_brackets(new, en_text, field in ID_FIELDS, field)
    for bad, good in CHAR_FIX.items():
        if bad in new:
            _stat["chars"] += new.count(bad)
            new = new.replace(bad, good)
    if field in NAME_FIELDS:
        new = re.sub(r"\s+\[", "[", new)          # 零协写法：噗扭扭[橙子味]
    if HANGUL.search(new) and not HANGUL.search(en_text or ""):
        new = re.sub(r"[\uac00-\ud7af]+", "", new).strip()     # 混进来的韩文残渣
        _stat["chars"] += 1
    elif HANGUL.search(new):
        got = translate_text(new)
        if got.strip() and not HANGUL.search(got) and not mt._placeholder_left(got):
            new = got
            _stat["retrans"] += 1
    if new != text:
        container[key] = new


def walk(node, path_: tuple = ()) -> None:
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if k in SKIP_FIELDS:
                continue
            if isinstance(v, (dict, list)):
                walk(v, path_ + (k,))
            elif isinstance(v, str):
                _handle(node, k, path_ + (k,), v)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, (dict, list)):
                walk(v, path_ + (i,))
            elif isinstance(v, str):
                _handle(node, i, path_ + (i,), v)


def _resolve(rel: str):
    """数据文件（data/translate/files/…）或剧情文件（data/translate/zh/<名>.json）都能处理。

    c10p2 起的剧情译稿直接落在 ``data/translate/out/zh/``（合并产物目录），
    这里也要认，否则体检会把这些文件误报成「缺文件」而整批跳过。
    """
    p = mf.OUT / rel
    if p.is_file():
        return p, mf.en_path(rel)
    name = rel[:-5] if rel.endswith(".json") else rel
    for cand in (mt.tp.ZH_DIR / f"{name}.json", mf.OUT.parent / "out" / "zh" / f"{name}.json"):
        if cand.is_file():
            return cand, mt.tp.en_file(name)
    return None, None


def run_file(rel: str, dry: bool = False) -> dict:
    global _en_map, _stat
    path, en = _resolve(rel)
    if path is None or en is None or not Path(en).is_file():
        return {"rel": rel, "ok": False, "reason": "没有这个文件（或缺英文基线）"}
    _en_map = en_strings(json.loads(Path(en).read_text(encoding="utf-8-sig")), {})
    _stat = {"brackets": 0, "chars": 0, "retrans": 0}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    walk(data)
    if any(_stat.values()) and not dry:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"rel": rel, "ok": True, **_stat}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    names = args.files or (mf.CH10_FILES + mf.RPG_FILES + list(mt.tp.STORY_FILES))
    total = {"brackets": 0, "chars": 0, "retrans": 0}
    for rel in names:
        res = run_file(rel, dry=args.dry_run)
        if not res.get("ok"):
            print(f"  {rel}: {res.get('reason')}")
            continue
        for k in total:
            total[k] += res.get(k, 0)
        if any(res.get(k, 0) for k in total):
            print(f"  {rel}: 方括号 {res['brackets']} · 字符 {res['chars']} · 补译 {res['retrans']}")
    print(f"合计：方括号还原 {total['brackets']} · 字体替换 {total['chars']} · 补译 {total['retrans']}"
          + ("（--dry-run，未写盘）" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
