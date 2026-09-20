"""良秀式缩写（C.H. / G.B. / S.H.N.C. …）还原成中文缩写 + 相关句子修正。

零协旧例（第 1~9 章实测）：
  B.A.R.F. → 余·指·尽·折     L.N.L. → 九·九·律      Da GAME of DEATH → 死·亡·游·戏！
即「逐词对应、字间加分隔符」。本表按同一思路处理第十章：
  C.H.    = Cut Head                 → 折.脖.（用户指定）
  G.B.    = Golden Buildingskin      → 金.皮.
  S.H.N.C.= Slice Her Neck Clean     → 折.她.脖.
  S.Y.N.C.= Slice Your Neck Clean    → 折.你.脖.
  G.Y.B.  = Get You Back             → 报.复.你.
  L.B.    = Limbs Broken（推断）      → 断.你.肢.   ← 待复核
用法：python scripts/fix_abbrev.py [--dry-run]
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

#: 英文缩写 → 中文缩写（长的先替换）
ABBREV = {
    "S.H.N.C.": "折.她.脖.",
    "S.Y.N.C.": "折.你.脖.",
    "G.Y.B.": "报.复.你.",
    "C.H.": "折.脖.",
    "G.B.": "金.皮.",
    "L.B.": "断.你.肢.",
}
#: 机翻把缩写拆开/译错时的整句修正（按 文件#记录id → 新译文）
LINE_FIX = {
    ("S1014B", "5"): "<良秀，等等！别折.她.脖.！>",
    ("S1013B", "10"): "……什么？需要金.皮.什么的吗？",
    ("S1013B", "12"): "啧……G.B. 指的是金.皮.，不是金枝。",
    ("S1004B", "15"): "你干嘛用那种眼神看我，折.脖.？想打架吗？",
    ("S1004B", "19"): "呼……折.脖.的时代开始倒数了。",
    ("S1004B", "332"): "……这笔账我会报.复.你.的……",
    ("S1005B", "35"): "……还有话说？那就尽管啰嗦。正好让我想想，是折.你.脖.，还是断.你.肢.",
}
#: 缩写被机翻成中文后的清理
CLEANUP = {
    "金建筑皮": "金皮", "黄金建筑皮": "金皮", "金色建筑皮": "金皮",
    "G.B. 是指金建筑皮": "G.B. 指的是金.皮.", "G.B.是指金建筑皮": "G.B. 指的是金.皮.",
}


def fix_text(text: str) -> tuple[str, int]:
    n = 0
    for wrong, right in CLEANUP.items():
        if wrong in text:
            n += text.count(wrong)
            text = text.replace(wrong, right)
    for en, zh in ABBREV.items():
        if en in text:
            n += text.count(en)
            text = text.replace(en, zh)
        bare = en.rstrip(".")
        if re.search(rf"(?<![A-Za-z.]){re.escape(bare)}(?![A-Za-z.])", text) and bare not in ABBREV:
            text, k = re.subn(rf"(?<![A-Za-z.]){re.escape(bare)}(?![A-Za-z.])", zh, text)
            n += k
    return text, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    total = 0

    # 1) 剧情译文
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
            if fname == name and rid in lines:
                if lines[rid] != new:
                    lines[rid] = new
                    hits += 1
        if hits and not args.dry_run:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        if hits:
            print(f"  {name}: {hits} 处")
            total += hits

    # 2) 数据文件（RPG 对白、战斗气泡等）
    files_dir = ROOT / "data" / "translate" / "files"
    if files_dir.is_dir():
        for path in sorted(files_dir.rglob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            hits = 0

            def rec(node):
                nonlocal hits
                if isinstance(node, dict):
                    for k, v in list(node.items()):
                        if isinstance(v, str):
                            fixed, n = fix_text(v)
                            if n:
                                node[k] = fixed
                                hits += n
                        else:
                            rec(v)
                elif isinstance(node, list):
                    for i, v in enumerate(node):
                        if isinstance(v, str):
                            fixed, n = fix_text(v)
                            if n:
                                node[i] = fixed
                                hits += n
                        else:
                            rec(v)

            rec(data)
            if hits and not args.dry_run:
                path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            if hits:
                print(f"  {path.relative_to(files_dir)}: {hits} 处")
                total += hits
    print(f"缩写还原共 {total} 处" + ("（--dry-run，未写盘）" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
