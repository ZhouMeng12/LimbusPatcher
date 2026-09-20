"""导入 AI 语义对齐答案并重建剧本数据。

答案文件格式（豆包等返回的 JSON，按页面命名 <页标题>.json 放在同一目录）：
    {"matches": [{"wiki": 0, "record": 12, "note": "同义改写"}], "skips": [2]}
也可整体一个 answers.json：{"<页标题>": {"matches": [...], "skips": [...]}}

用法：
    python scripts/import_alignment.py <答案目录> [--llc <LLC目录>] [--crawl data/wiki_story]

流程：校验每个 record 是否是该页本地文件真实记录 → 写入 align_overrides.json
→ 用 _align.build_all 重建 story_stages.json（dev 与包数据）→ 输出统计。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import _align  # noqa: E402

MAIN = {"prologue", "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("answers_dir", type=Path)
    ap.add_argument("--llc", type=Path, default=Path(r"D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data/Lang/LLC_zh-CN"))
    ap.add_argument("--crawl", type=Path, default=ROOT / "data" / "wiki_story")
    args = ap.parse_args()

    answers: dict[str, dict] = {}
    if (args.answers_dir / "answers.json").is_file():
        obj = json.load(open(args.answers_dir / "answers.json", encoding="utf-8"))
        answers = obj
    else:
        for p in sorted(args.answers_dir.glob("*.json")):
            answers[p.stem] = json.load(open(p, encoding="utf-8"))
    if not answers:
        print("未找到答案文件（*.json 或 answers.json）")
        return 2

    parsed = json.load(open(args.crawl / "parsed.json", encoding="utf-8"))
    sm = json.load(open(args.crawl / "stage_map.json", encoding="utf-8"))
    ov_path = args.crawl / "align_overrides.json"
    overrides: dict = json.load(open(ov_path, encoding="utf-8")) if ov_path.is_file() else {}

    accepted = skipped_lines = invalid = 0
    low_list: list[dict] = []
    review: list[dict] = []
    for title, ans in answers.items():
        info = sm.get("stages", {}).get(title)
        if not info or not info.get("file"):
            print(f"[跳过] 无此页映射：{title}")
            continue
        records = _align.load_records(args.llc, info["file"])
        # 该页候选序号 0..n-1 与任务包 wiki 行一致（重新走一遍 align 的未对齐序号）
        page_items = _align.align_page(parsed.get(title, {}), info["file"], args.llc, [], {})
        unaligned = [it for it in page_items if it["type"] == "line" and it.get("wiki_only")]
        page_ov = overrides.setdefault(title, {})
        for m in ans.get("matches", []):
            w, r = m.get("wiki"), m.get("record")
            certainty = str(m.get("certainty", "high") or "high")
            note = str(m.get("note", "") or "")
            if not isinstance(w, int) or not isinstance(r, int):
                invalid += 1
                continue
            if w < 0 or w >= len(unaligned):
                invalid += 1
                print(f"[无效行号] {title} wiki={w}")
                continue
            if r < 0 or r >= len(records):
                invalid += 1
                print(f"[无效记录] {title} wiki={w} record={r}（该文件仅 {len(records)} 条）")
                continue
            page_ov[str(w)] = {"record": r, "certainty": certainty, "note": note}
            review.append({
                "page": title, "file": info["file"], "wiki": w,
                "wiki_text": unaligned[w]["text"], "record": r,
                "local_text": (records[r].get("content") or ""), "certainty": certainty, "note": note,
            })
            if certainty == "low":
                low_list.append(review[-1])
            accepted += 1
        skipped_lines += len(ans.get("skips", []))
    json.dump(overrides, open(ov_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    # 同时写「按文本索引」版本：重解析/换汉化版本后行号变动也能命中
    import re as _re
    from _match import norm as _norm

    by_text: dict = {}
    for x in review:
        by_text.setdefault(x["page"], {})[_norm(x["wiki_text"])] = {
            "record": x["record"], "certainty": x["certainty"], "note": x["note"],
        }
    (args.crawl / "align_overrides_text.json").write_text(
        json.dumps(by_text, ensure_ascii=False, indent=2), encoding="utf-8")

    out = _align.build_all(args.llc, args.crawl)
    (args.crawl / "story_stages.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    pkg = ROOT / "limbus_patcher" / "data" / "story_stages.json"
    pkg.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    # 审阅报告：给用户/助手复核 low 与文字相似度过低的匹配
    if review:
        from difflib import SequenceMatcher

        import re as _re

        def sim(a, b):
            na = _re.sub(r"\W", "", a or "")
            nb = _re.sub(r"\W", "", b or "")
            return SequenceMatcher(None, na, nb).ratio()

        rep = [f"# AI 对齐审阅报告（{_re.sub(r'[:]','',str(args.answers_dir))}）\n",
               f"共接受 {accepted} 条匹配，其中 certainty=low {len(low_list)} 条。", ""]
        sus = [x for x in review if x["certainty"] == "low" or sim(x["wiki_text"], x["local_text"]) < 0.25]
        rep.append(f"## 建议人工复核 {len(sus)} 条（low 或 字面差异极大）\n")
        for x in sus:
            rep.append(f"- {x['page']} [wiki {x['wiki']}]（{x['certainty']}）")
            rep.append(f"  wiki: {x['wiki_text'][:60]}")
            rep.append(f"  零协: {x['local_text'][:60]}")
            if x.get("note"):
                rep.append(f"  note: {x['note']}")
        rep_path = args.crawl / "align_review.md"
        rep_path.write_text("\n".join(rep), encoding="utf-8")
        print(f"审阅报告：{rep_path}（人工复核 {len(sus)} 条）")

    print(f"接受匹配 {accepted}（含 low {len(low_list)}），跳过声明 {skipped_lines}，无效 {invalid}")
    print(f"已重建 story_stages.json（主线剩余未对齐 "
          f"{sum(1 for c in out['chapters'] for s in c['stages'] for i in s['items'] if i.get('wiki_only'))} 句）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
