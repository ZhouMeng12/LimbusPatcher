"""把剧本数据里的**文本**去掉，只留位置（相对路径 + 记录下标 + 字段路径）。

    python scripts/strip_story_text.py [--data <story_stages.json>] [--dry-run]

为什么要这样：文本不该由本工具随包分发（零协译文 / wiki 文本都是第三方内容），
而且没装零协的玩家用的是英文基线——同一份结构换个来源就该能读。
应用运行时按位置从当前语言文件取文本（见 limbus_patcher/textsource.py）。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "limbus_patcher" / "data" / "story_stages.json"
#: 去掉的字段（位置字段一律保留；scene / 分支标题这类我们自己的文字也保留）
DROP = ("text", "speaker", "title")


def main() -> int:
    ap = argparse.ArgumentParser(description="去掉剧本数据里的游戏文本，只留位置")
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = Path(args.data)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    stat = Counter()
    for ch in data.get("chapters", []):
        for st in ch.get("stages", []):
            items = st.get("items")
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                if it.get("type") == "scene":
                    stat["scene 行（我们自己的标题，保留文字）"] += 1
                    continue
                if not it.get("file") or it.get("record") is None:
                    stat["没有位置（保留文字）"] += 1
                    continue
                for key in DROP:
                    if key in it:
                        it.pop(key, None)
                        stat[f"去掉 {key}"] += 1
                stat["保留位置的行"] += 1
    for k, v in stat.items():
        print(f"  {k}: {v}")
    if args.dry_run:
        print("[dry-run] 未写入")
        return 0
    # 结构文件不需要好看，紧凑写 + 保留中文
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8", newline="")
    print(f"已写入 {path}（{path.stat().st_size / 1024 / 1024:.2f} MB）")
    text = path.read_text(encoding="utf-8")
    for extra in (ROOT / "data" / "wiki_story" / "story_stages.json",
                  ROOT / "dist" / "data" / "cache" / "story_stages.json"):
        if extra.is_file() and extra.resolve() != path.resolve():
            extra.write_text(text, encoding="utf-8", newline="")
            print(f"已同步运行时副本 {extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
