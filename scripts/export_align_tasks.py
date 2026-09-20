"""导出「AI 语义对齐任务包」：把未逐字对齐的 wiki 台词 + 本地候选记录整理成可直接粘贴给任意 AI 的提示词。

用法：python scripts/export_align_tasks.py [--out data/wiki_story/tasks]
产出：tasks/<页标题>.txt（每页一个任务）+ tasks/_index.txt
任务 JSON 答案格式（导入器可解析）：
    {"matches": [{"wiki": 0, "record": 3, "note": "..."}], "skips": [1, 5]}
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

from _match import norm  # noqa: E402
from _align import align_page  # noqa: E402

MAIN = {"prologue", "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9"}
CHAPTER_LABEL = {"prologue": "序章"}
CHAPTER_LABEL.update({f"c{i}": f"第{i}章" for i in range(1, 10)})

REQ = """需求：
1. **以零协（本地汉化）文本为基准**：下方 A 是零协本地记录（真值），B 是 wiki 台词。请把 B 的每一句对应到 A 的记录编号（record）。两者是同一剧情，零协与 wiki 存在少量措辞修订差异——只要语义与剧情位置一致即视为对应。
2. 严格按 B 的剧情顺序逐句指认，不要跳跃；一条 A 记录最多对应一条 B 句（除非文字完全相同且确为重复句，可复用并在 note 说明）。
3. **拿不准必须显式标注，不许静默硬配**：
   - 语义能对上但措辞差异大、或你只有六七成把握 → certainty 填 "low" 并写清 note（为什么拿不准）；
   - 完全无法对应 → 放进 skips（并可在 note 解释）；
   - 你觉得需要人工判断边界情况的 → 在 uncertain 里给出 wiki 编号与原因。
4. 不要把 B 当基准改写 A；输出一律指向 A 已有记录编号。

只输出 JSON，不要任何其他文字，格式如下：
{"matches": [{"wiki": 0, "record": 52, "certainty": "high", "note": "可选说明"}],
 "skips": [3],
 "uncertain": [{"wiki": 7, "reason": "与多条记录相近，无法定夺"}]}
"""
PROMPT_TEMPLATE = "你是边狱公司汉化校对助手。\n" + REQ + """

## 关卡：{chapter_label} {stage_code}（页面：{page_title}）
## A. 零协本地记录文件：{file}（未使用记录，编号即 record）

{records_block}

## B. 待对应 wiki 台词（按剧情顺序）

{wiki_block}
"""


def _records_of(llc_dir: Path, relfile: str) -> list[dict]:
    try:
        d = json.loads((llc_dir / relfile).read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    return [r for r in d.get("dataList", []) if isinstance(r, dict)]


def make_task_text(llc_dir: Path, title: str, stage: dict, page_items: list[dict], file: str) -> str | None:
    records = _records_of(llc_dir, file)
    un = [i for i in page_items if i["type"] == "line" and i.get("wiki_only") and not i.get("skip")]
    if not un or not records:
        return None
    aligned = {i.get("record") for i in page_items if i["type"] == "line" and i.get("record") is not None}
    rec_lines = []
    for idx, r in enumerate(records):
        if idx in aligned:
            continue
        who = r.get("teller") or ""
        txt = (r.get("content") or "")[:160]
        rec_lines.append(f"[{idx}] {who}: {txt}")
    wiki_lines = [f"[{i}] {u['text']}" for i, u in enumerate(un)]
    text = PROMPT_TEMPLATE
    for token, value in (
        ("{chapter_label}", str(stage.get("chapter_label", title))),
        ("{stage_code}", str(stage.get("stage_code", ""))),
        ("{page_title}", title),
        ("{file}", file),
        ("{records_block}", "\n".join(rec_lines)),
        ("{wiki_block}", "\n".join(wiki_lines)),
    ):
        text = text.replace(token, value)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llc", type=Path, default=Path(r"D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data/Lang/LLC_zh-CN"))
    ap.add_argument("--crawl", type=Path, default=ROOT / "data" / "wiki_story")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "duiying" / "tasks")
    args = ap.parse_args()

    parsed = json.load(open(args.crawl / "parsed.json", encoding="utf-8"))
    sm = json.load(open(args.crawl / "stage_map.json", encoding="utf-8"))
    ov_path = args.crawl / "align_overrides.json"
    overrides: dict = {}
    if ov_path.is_file():
        try:
            overrides = json.load(open(ov_path, encoding="utf-8"))
        except Exception:
            overrides = {}
    names = []
    args.out.mkdir(parents=True, exist_ok=True)
    index: list[str] = []
    count = 0
    for title, m in sm.get("stages", {}).items():
        st = m.get("stage")
        if not st or st.get("chapter_id") not in MAIN:
            continue
        if m.get("file") is None:
            continue
        items = align_page(parsed.get(title, {}), m["file"], args.llc, names, overrides.get(title))
        if not any(i.get("wiki_only") for i in items):
            continue
        text = make_task_text(args.llc, title, st, items, m["file"])
        if not text:
            continue
        safe = re.sub(r'[\\/:*?"<>|]', "_", title)
        (args.out / f"{safe}.txt").write_text(text, encoding="utf-8")
        index.append(f"{title}\t{st.get('chapter_label','')}\t{st.get('stage_code','')}\t{sum(1 for i in items if i.get('wiki_only'))} 句")
        count += 1
    (args.out / "_index.txt").write_text("\n".join(index), encoding="utf-8")
    print(f"生成 {count} 个任务包 → {args.out}（_index.txt 为清单）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
