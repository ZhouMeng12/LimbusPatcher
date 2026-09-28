"""第10章第二部分（a1c10p2）收尾：把答案 + 预填灌回完整结构，落到交付目录。

    python scripts/ch10p2_apply.py --dry-run
    python scripts/ch10p2_apply.py

来源：
  · 英文基线（结构模板，含 dataList 外壳）
  · data/translate/ch10p2/prefill/<文件>.json（翻译记忆命中，path→中文）
  · data/translate/ch10p2/ans/batch_*.json（AI 分片答案，id=「文件#叶子下标」→中文）
叶子顺序用的是 ch10p2_prep.walk()，与切任务包时**完全同一套**，所以下标一一对应。

落点（install_supplement.py 的两个来源）：
  · RPG / 根数据文件 → data/translate/files/<相对路径>
  · StoryData/*.json  → data/translate/out/zh/<文件名>
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import ch10p2_prep as P  # noqa: E402

WORK = ROOT / "data" / "translate" / "ch10p2"
ANS, PREFILL = WORK / "ans", WORK / "prefill"
FILES_OUT = ROOT / "data" / "translate" / "files"
ZH_OUT = ROOT / "data" / "translate" / "out" / "zh"


def set_by_path(node, path: list, value: str) -> bool:
    """按 walk() 给的路径写入字符串（路径元素是键名或列表下标）。"""
    cur = node
    for seg in path[:-1]:
        cur = cur[seg] if not isinstance(seg, int) else cur[seg]
    last = path[-1]
    if isinstance(cur, dict) and isinstance(cur.get(last), str):
        cur[last] = value
        return True
    if isinstance(cur, list) and isinstance(last, int) and 0 <= last < len(cur) \
            and isinstance(cur[last], str):
        cur[last] = value
        return True
    return False


def load_answers() -> dict[str, str]:
    """答案 + 原文去重时的**所有落点**。

    切任务包时按英文原文去重（同一句只翻一次），item.ids 里带着全部落点；
    所以这里要把答案展开到每个 id，否则重复出现的叶子会漏。
    """
    out: dict[str, str] = {}
    for p in sorted(ANS.glob("batch_*.json")):
        d = json.loads(p.read_text(encoding="utf-8-sig"))
        tp = WORK / "tasks" / p.name
        if tp.is_file():
            for it in json.loads(tp.read_text(encoding="utf-8"))["items"]:
                zh = d.get(it["ids"][0])
                if zh:
                    for i in it["ids"]:
                        out[i] = zh
        out.update(d)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    answers = load_answers()
    print(f"答案合计 {len(answers)} 条")
    stat: Counter = Counter()
    written = []
    for rel in P.new_files():
        ep = P.en_path(rel)
        if not ep.is_file():
            stat["英文基线缺文件"] += 1
            continue
        data = P.load(ep)
        leaves: list = []
        P.walk(P.body(data), leaves)
        # 预填（翻译记忆）
        pre: dict = {}
        pf = PREFILL / f"{rel.replace('/', '__')}.json"
        if pf.is_file():
            for path, zh in json.loads(pf.read_text(encoding="utf-8"))["pairs"]:
                pre[tuple(path)] = zh
        miss = 0
        for idx, (path, en, _ctx) in enumerate(leaves):
            zh = answers.get(f"{rel}#{idx}") or pre.get(tuple(path))
            if not zh:
                miss += 1
                stat["未覆盖叶子"] += 1
                continue
            if not set_by_path(P.body(data), path, zh):
                stat["路径写不回"] += 1
                miss += 1
        stat["文件"] += 1
        stat["叶子"] += len(leaves)
        if miss:
            print(f"  ! {rel}: {len(leaves)} 叶子，缺 {miss}")
        if not args.dry_run:
            text = json.dumps(data, ensure_ascii=False, indent=1)
            text = text.replace("\r\n", "\n").replace("\n", "\r\n") + "\r\n"
            target = (ZH_OUT / Path(rel).name) if rel.startswith("StoryData/") else (FILES_OUT / rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="")
            written.append(target)

    print(f"\n处理 {stat['文件']} 个文件 / {stat['叶子']} 个叶子")
    if stat["未覆盖叶子"] or stat["路径写不回"] or stat["英文基线缺文件"]:
        print("问题:", {k: v for k, v in stat.items() if k in ("未覆盖叶子", "路径写不回", "英文基线缺文件")})
    if args.dry_run:
        print("[dry-run] 未写入")
        return 0
    print(f"已写出 {len(written)} 个文件：")
    for t in written[:8]:
        print("   ", t.relative_to(ROOT))
    if len(written) > 8:
        print(f"    …共 {len(written)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
