"""一键重跑剧本匹配：解析 → 页面匹配 → 按行对齐 → 写回包内数据。

用途：零协汉化更新或重新抓取 wiki 后，在本机执行一次即可刷新剧本数据。
    python scripts/rematch_all.py [--llc <LLC目录>] [--crawl data/wiki_story]

注意：本脚本是**开发机工具**；应用内不调用（exe 只读取已生成的数据）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

DEFAULT_LLC = r"D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data/Lang/LLC_zh-CN"


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd), flush=True)
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc != 0:
        raise SystemExit(f"命令失败（{rc}）：{' '.join(cmd)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llc", type=Path, default=Path(DEFAULT_LLC))
    ap.add_argument("--crawl", type=Path, default=ROOT / "data" / "wiki_story")
    ap.add_argument("--skip-crawl", action="store_true", help="跳过 parse-all（未重新抓取时）")
    args = ap.parse_args()
    py = str(ROOT / ".venv" / "Scripts" / "python.exe")

    if not args.skip_crawl:
        run([py, "scripts/crawl_wiki_story.py", "parse-all"])
    run([py, "scripts/crawl_wiki_story.py", "match", str(args.llc)])

    import _align

    out = _align.build_all(args.llc, args.crawl)
    (args.crawl / "story_stages.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    (ROOT / "limbus_patcher" / "data" / "story_stages.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8"
    )
    lines = sum(1 for c in out["chapters"] for s in c["stages"] for i in s["items"] if i["type"] == "line")
    unaligned = sum(1 for c in out["chapters"] for s in c["stages"] for i in s["items"] if i.get("wiki_only"))
    print(f"完成：{len(out['chapters'])} 章 · 剧本行 {lines} · 未对齐 {unaligned}")
    print("如需更新任务包：python scripts/export_align_tasks.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
