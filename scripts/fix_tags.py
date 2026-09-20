"""标签补齐：机翻偶尔会吞掉 <color=…>／<i> 标签，按英文原文把标签补回去。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import translate_pack as tp  # noqa: E402

TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s*=\s*[^>]*)?>")


def fix_line(en: str, zh: str) -> str:
    en_tags = TAG_RE.findall(en)
    if not en_tags or TAG_RE.findall(zh):
        return zh
    # 英文整行被一对标签包住 → 把同样的标签套到译文上
    if len(en_tags) == 2 and en.startswith(en_tags[0]) and en.endswith(en_tags[1]):
        return f"{en_tags[0]}{zh}{en_tags[1]}"
    open_tags = [t for t in en_tags if not t.startswith("</")]
    close_tags = [t for t in en_tags if t.startswith("</")]
    if len(open_tags) == 1 and len(close_tags) == 1:
        return f"{open_tags[0]}{zh}{close_tags[0]}"
    return zh


def main() -> int:
    n = 0
    for path in sorted(tp.ZH_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        lines = data.get("lines") or {}
        en = {str(r.get("id")): str(r.get("content") or "")
              for r in tp.records(path.stem) if isinstance(r, dict)}
        hits = 0
        for rid, zh in list(lines.items()):
            src = en.get(rid, "")
            if not src:
                continue
            fixed = fix_line(src, str(zh))
            if fixed != zh:
                lines[rid] = fixed
                hits += 1
        if hits:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {path.stem}: 补标签 {hits} 行")
            n += hits
    print(f"共补 {n} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
