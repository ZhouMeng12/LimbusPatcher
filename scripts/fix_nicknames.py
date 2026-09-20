"""罗佳式昵称统一：Ishy→以实、Meur→默尔、Fau→浮、Sinc→辛。

依据（零协旧章实测）：
  Ishy → 以实（以实玛利的截断）      Greg → 格雷格（昵称本身音译）
规律：把昵称按中文名的截断/音译写出来，罗佳的语气要口语化。
用法：python scripts/fix_nicknames.py [--dry-run]
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
import translate_pack as tp  # noqa: E402

#: 英文昵称 → 中文昵称（拉丁残留直接换掉，安全）
LATIN_NICK = {
    r"\bIshy\b": "以实",
    r"(?<![A-Za-z])Meur(?![A-Za-z])": "默尔",
    r"(?<![A-Za-z])Fau(?![A-Za-z])": "浮",
    r"(?<![A-Za-z])Sinc(?![A-Za-z])": "辛",
}
#: 机翻把昵称音译/写错时的中文修正（只在昵称语境里替换，避免误伤普通词）
ZH_NICK = {
    "梅尔": "默尔",          # Meur 被译成梅尔
    "弗奥": "浮", "福啊": "浮啊", "福……": "浮……", "福？！": "浮？！",
    "说句公道话，Sinc": "说句公道话，辛",
}
#: 逐条定点（文件, 记录键）→ 新译文（EN 用昵称、译文却写了全名/错名的地方）
LINE_FIX = {
    ("S1001B", "36"): "浮。我们启动的那台机器……是某种传送装置吗？",
    ("S1001B", "38"): "那么……我们到底在哪儿？要去哪里找默尔？",
    ("S1004B", "137"): "无论如何，我得说，如果默尔只是破坏了一些财物，他还是有机会从轻发落的~",
    ("S1004B", "177"): "我们说的是浮啊。",
    ("S1004B", "275"): "为什么，浮……？！",
}


def fix_text(text: str) -> tuple[str, int]:
    n = 0
    for pattern, zh in LATIN_NICK.items():
        text, k = re.subn(pattern, zh, text)
        n += k
    for wrong, right in ZH_NICK.items():
        if wrong != right and wrong in text:
            n += text.count(wrong)
            text = text.replace(wrong, right)
    return text, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    total = 0
    for name in tp.STORY_FILES:
        path = tp.ZH_DIR / f"{name}.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        lines = data.get("lines") or {}
        hits = 0
        for rid, zh in list(lines.items()):
            fixed, n = fix_text(str(zh))
            if n:
                lines[rid] = fixed
                hits += n
        for (fname, rid), new in LINE_FIX.items():
            if fname == name and rid in lines and lines[rid] != new:
                lines[rid] = new
                hits += 1
        if hits and not args.dry_run:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        if hits:
            print(f"  {name}: {hits} 处")
            total += hits
    print(f"昵称统一 {total} 处" + ("（--dry-run）" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
