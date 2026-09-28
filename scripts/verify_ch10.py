"""第十章译稿体检：方括号 id、韩文残留、字体危险字符、占位符残留、未翻英文。

用法：
    python scripts/verify_ch10.py                 # 全部第十章文件
    python scripts/verify_ch10.py --files A.json B.json
    python scripts/verify_ch10.py --story         # 只查剧情
    python scripts/verify_ch10.py --quiet         # 只输出有问题的文件
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

BRACKET = re.compile(r"\[[^\]\n]{0,60}\]")
HANGUL = re.compile(r"[\uac00-\ud7af]")
CJK = re.compile(r"[\u4e00-\u9fff]")
PLACEHOLDER = re.compile(r"@@\s*\d+\s*@@|%%.{0,3}%%|〖\s*\d+\s*〗")
#: 游戏字体缺字形（零协从不使用）→ 会显示成口口
RISKY = set("〈〉「」［］｛｝體蟲國學來們為說這裡麼")
TAG_OR_NUM = re.compile(r"<[^>]*>|\{[^}]*\}|\[[^\]]*\]|[\d\s%.,:;!?/()\-–—'’\"“”·+*=<>_&@#$~^|\\]+")
#: 这些字段是程序内部键，不该翻译，也不算「漏译」
SKIP_FIELDS = {"id", "key", "model", "code"}
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")          # ReturnToMainUiScene 这种


def strip_noise(text: str) -> str:
    return TAG_OR_NUM.sub("", text)


def _skip_path(path: tuple) -> bool:
    if not path:
        return False
    last = path[-1]
    return isinstance(last, str) and last in SKIP_FIELDS


def check(rel: str) -> dict:
    path, en = rc._resolve(rel)
    if path is None or en is None or not Path(en).is_file():
        return {"rel": rel, "ok": False, "reason": "缺文件"}
    zh_map = rc.en_strings(json.loads(Path(path).read_text(encoding="utf-8-sig")), {})
    en_map = rc.en_strings(json.loads(Path(en).read_text(encoding="utf-8-sig")), {})
    bad_bracket, hangul, risky, ph, untranslated = [], [], [], [], []
    for p, text in zh_map.items():
        src = en_map.get(p)
        if not isinstance(src, str):
            continue
        # 英文基线自己带韩文的占位符（[미사용]）不算问题：译文写 [未使用] 是对的
        want = [b for b in BRACKET.findall(src) if not HANGUL.search(b)]
        have = [b for b in BRACKET.findall(text) if not HANGUL.search(b) and "未使用" not in b]
        if want != have:
            bad_bracket.append((p, want, have))
        if HANGUL.search(text) and not _skip_path(p):
            # ``model`` 是韩文角色键（原始数据，不是译文），不算韩文残留
            hangul.append((p, text[:60]))
        hit = RISKY.intersection(text)
        if hit:
            risky.append((p, "".join(sorted(hit)), text[:60]))
        if PLACEHOLDER.search(text):
            ph.append((p, text[:60]))
        body = strip_noise(text)
        if (body and not CJK.search(body) and len(body) >= 8 and not src.isupper()
                and not _skip_path(p) and not IDENT.match(text.strip())):
            untranslated.append((p, text[:70]))
    return {"rel": rel, "ok": True, "n": len(zh_map), "brackets": bad_bracket, "hangul": hangul,
            "risky": risky, "placeholders": ph, "untranslated": untranslated}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*", default=None)
    ap.add_argument("--story", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    if args.files:
        names = args.files
    elif args.story:
        names = list(mt.tp.STORY_FILES)
    else:
        names = mf.CH10_FILES + mf.RPG_FILES + list(mt.tp.STORY_FILES)
    total = {"brackets": 0, "hangul": 0, "risky": 0, "placeholders": 0, "untranslated": 0}
    for rel in names:
        res = check(rel)
        if not res.get("ok"):
            print(f"✗ {rel}: {res.get('reason')}")
            continue
        counts = {k: len(res[k]) for k in total}
        for k in total:
            total[k] += counts[k]
        if args.quiet and not any(counts.values()):
            continue
        flags = " · ".join(f"{k} {v}" for k, v in counts.items() if v) or "干净"
        print(f"{'✓' if not any(counts.values()) else '!'} {rel}（{res['n']} 条）: {flags}")
        for key, items in (("brackets", res["brackets"]), ("hangul", res["hangul"]),
                           ("risky", res["risky"]), ("placeholders", res["placeholders"]),
                           ("untranslated", res["untranslated"])):
            for item in items[:5]:
                print(f"     [{key}] {item}")
    print("合计：" + " · ".join(f"{k} {v}" for k, v in total.items()))
    return 1 if any(total.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
