"""导出剧本对照表：crawl 产物（stage_map.json + parsed.json）→ 应用数据 story_stages.json。

用法：python scripts/export_stages.py [--src data/wiki_story] [--dest limbus_patcher/data]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _sort_key(stage_code: str) -> tuple:
    m = re.match(r"(\d+(?:\.\d)?)-(\d+)", stage_code)
    if m:
        return (0, float(m.group(1)), int(m.group(2)))
    return (1, 0, 0)


def export(src: Path, dest: Path) -> dict:
    sm = json.load(open(src / "stage_map.json", encoding="utf-8"))
    parsed = json.load(open(src / "parsed.json", encoding="utf-8"))
    chapters: dict[str, dict] = {}
    for title, m in sm.get("stages", {}).items():
        st = m.get("stage")
        if not st or not m.get("file"):
            continue
        cid = st.get("chapter_id") or "other"
        ch = chapters.setdefault(cid, {"chapter_id": cid, "chapter_label": st.get("chapter_label") or cid, "stages": {}})
        code = st.get("stage_code")
        stg = ch["stages"].setdefault(code, {"stage_code": code, "pages": []})
        stg["pages"].append({"segment": st.get("segment"), "title": title, "file": m["file"]})
    out = {
        "format_version": 1,
        "generated_at": json.load(open(src / "stage_map.json", encoding="utf-8")).get("format_version"),
        "source": "limbuscompany.huijiwiki.com",
        "matched_pages": len(sm.get("stages", {})),
        "unmatched_pages": len(sm.get("unmatched_pages", [])),
        "chapters": [],
    }
    for cid, ch in sorted(chapters.items()):
        stages = [s for _, s in sorted(ch["stages"].items(), key=lambda kv: _sort_key(kv[0]))]
        out["chapters"].append({"chapter_id": cid, "chapter_label": ch["chapter_label"], "stages": stages})
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "story_stages.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=ROOT / "data" / "wiki_story")
    ap.add_argument("--dest", type=Path, default=ROOT / "limbus_patcher" / "data")
    args = ap.parse_args()
    out = export(args.src, args.dest)
    print(f"导出 {out['matched_pages']} 页 / {len(out['chapters'])} 章，未命中 {out['unmatched_pages']} 页")
    for ch in out["chapters"]:
        print(f"  {ch['chapter_label']}: {len(ch['stages'])} 关卡")
    return 0


if __name__ == "__main__":
    sys.exit(main())
