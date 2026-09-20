"""导出 RPG 关卡的中英对照（第十章 10-4 起）。

    python scripts/export_story_rpg.py --stage 10-04
    python scripts/export_story_rpg.py --stage 10-04 --out data/translate/out

产物（按分支分段，分支顺序 = 玩家游玩顺序）：
  <out>/第十章-10-4剧情-中英对照.md
  <out>/第十章-10-4剧情-中英对照.csv

中文一律取零协包原文；英文取游戏英文基线（EN_ 前缀同位置），仅作对照列。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from limbus_patcher.config import AppPaths, ConfigStore  # noqa: E402
from limbus_patcher.paths import resolve_game_paths  # noqa: E402
from limbus_patcher.textsource import TextSource  # noqa: E402

DATA = ROOT / "limbus_patcher" / "data" / "story_stages.json"
OUT = ROOT / "data" / "translate" / "out"


def _read(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def en_map(en_dir: Path, rel: str) -> dict:
    """英文基线同位置的文本：{(record, text_index): (text, speaker)}。"""
    p = Path(rel)
    data = _read(Path(en_dir) / p.parent / f"EN_{p.name}")
    out: dict = {}
    if data is None:
        return out
    for ri, rec in enumerate(data.get("dataList") or []):
        if not isinstance(rec, dict):
            continue
        texts = rec.get("texts")
        if isinstance(texts, list):
            for pos, t in enumerate(texts):
                if isinstance(t, dict) and (t.get("text") or "").strip():
                    idx = t.get("index")
                    out[(ri, idx if isinstance(idx, int) else pos)] = (t["text"], t.get("speaker"))
        elif (rec.get("content") or "").strip():
            out[(ri, None)] = (rec["content"], rec.get("teller"))
        elif (rec.get("text") or "").strip():
            out[(ri, None)] = (rec["text"], None)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="导出 RPG 关卡中英对照")
    ap.add_argument("--stage", default="10-04")
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--game", default=None)
    args = ap.parse_args()

    story = _read(Path(args.data))
    if story is None:
        print(f"读不到 {args.data}")
        return 1
    stage = None
    for ch in story.get("chapters", []):
        for st in ch.get("stages", []):
            if st.get("stage_code") == args.stage:
                stage = st
    if stage is None or not stage.get("branches"):
        print(f"{args.stage} 没有分支数据（先跑 scripts/build_story_rpg.py --stage {args.stage}）")
        return 1

    cfg = ConfigStore(AppPaths.from_root(ROOT)).load()
    gd = Path(args.game or cfg.game_dir or "")
    paths = resolve_game_paths(gd) if gd else None
    en_dir = paths.en_base_dir() if paths else None
    llc_dir = paths.llc_pack_dir if paths else None

    items = stage.get("items") or []
    branches = stage.get("branches") or []
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"第十章-{args.stage}剧情-中英对照.md"
    csv_path = out / f"第十章-{args.stage}剧情-中英对照.csv"

    src = TextSource.detect(llc_dir, en_dir)
    if not src.ok:
        print("找不到可用的文本来源（零协包 / 英文基线都没有）")
        return 1
    print(f"文本来源：{src.label}")

    en_cache: dict[str, dict] = {}
    rows: list[list[str]] = []
    md: list[str] = [f"# 第十章 {args.stage} 剧情（中英对照）", ""]
    md.append(f"- 分支 {len(branches)} 段，按**玩家游玩顺序**排列；中文为零协包原文，英文为游戏基线。")
    md.append("- 顺序依据见各段「依据」；标 low 的段落位置待进游戏确认。")
    md.append("")

    for br in branches:
        bid = br["branch_id"]
        md.append(f"## {br['label']}")
        md.append("")
        meta = f"- 类型：{br.get('kind_label') or br.get('kind')} · 置信：{br.get('confidence') or '-'}"
        if br.get("evidence"):
            meta += f" · 依据：{br['evidence']}"
        md.append(meta)
        md.append("")
        for it in items:
            if it.get("branch") != bid:
                continue
            if it.get("type") == "scene":
                text = it.get("text") or ""
                if it.get("source") == "plan" and text == br["label"]:
                    continue  # 分支标题已经写成 ## 了
                if it.get("source") == "plan":
                    md.append(f"### {text}")
                    md.append("")
                else:
                    md.append(f"*{text}*")
                continue
            rel = it["file"]
            if rel not in en_cache:
                en_cache[rel] = en_map(en_dir, rel) if en_dir else {}
            en_text, _en_speaker = en_cache[rel].get((it["record"], it.get("text_index")), ("", None))
            zh_text, speaker, _title = src.resolve(rel, int(it["record"]), it.get("text_index"), it.get("field"))
            who = speaker or "旁白"
            md.append(f"**{who}**：{zh_text or ''}")
            rows.append([bid, br["label"], speaker or "", zh_text or "", en_text,
                         rel, str(it.get("record")), str(it.get("text_index") if it.get("text_index") is not None else ""),
                         it.get("key") or ""])
        md.append("")

    md_path.write_text("\n".join(md) + "\n", encoding="utf-8", newline="")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["分支", "分支标题", "说话人", "中文（零协）", "英文", "文件", "记录", "text_index", "key"])
        w.writerows(rows)

    print(f"{args.stage}：{len(rows)} 行对话")
    print(f"  中英对照 → {md_path}")
    print(f"  表格版   → {csv_path}")
    if en_dir is None:
        print("  （没找到英文基线，英文列留空）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
