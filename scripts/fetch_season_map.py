"""生成赛季/种类映射表（离线数据的刷新脚本）。

用法：
    python scripts/fetch_season_map.py [--en-dir <零协仓库EN目录>] [--dest <输出目录>]

默认 dest = limbus_patcher/data（随软件发布）；
--en-dir 指定本地零协仓库的 EN 目录可避免重复下载（不指定则从 GitHub 下载）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from limbus_patcher.wiki_data import generate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="生成赛季/敌方种类映射表")
    ap.add_argument("--en-dir", type=Path, default=None, help="零协仓库 EN 目录（本地）")
    ap.add_argument("--dest", type=Path, default=ROOT / "limbus_patcher" / "data", help="输出目录")
    args = ap.parse_args()

    print("从 wiki.gg 拉取分类并生成映射表…")
    report = generate(
        args.dest,
        en_dir=args.en_dir,
        progress=lambda done, total: print(f"\r  {done}/{total}", end=""),
        cache_path=ROOT / "wiki_cache.json",
    )
    print()
    counts = report["counts"]
    print(f"人格：{counts['identities']}/{counts['en_identities']} 已标注赛季")
    print(f"E.G.O：{counts['egos']}/{counts['en_egos']} 已标注赛季")
    print(f"敌方：{counts['enemies']}/{counts['en_enemies']} 已标注种类")
    for key in ("identities", "egos", "enemies"):
        um = report["unmatched"][key]
        if um:
            print(f"未匹配 {key}（{len(um)}）：")
            for t in um[:20]:
                print(f"   - {t}")
    print(f"已写入：{args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
