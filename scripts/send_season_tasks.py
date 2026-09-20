"""按顺序把赛季/获取方式任务分片交给桌面版豆包（剪贴板 + 唤起豆包 + 资源管理器选中）。

用法：
    python scripts/send_season_tasks.py            # 送出「下一片还没答案的」
    python scripts/send_season_tasks.py --status   # 只看进度
    python scripts/send_season_tasks.py --index 3  # 指定第 3 片（按文件名排序）
    python scripts/send_season_tasks.py --no-open  # 只复制到剪贴板

回包存成 data/seasons/ans/<分片同名>.json，全部贴完跑：
    python scripts/import_season_answers.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from send_to_doubao import open_doubao, reveal, to_clipboard  # noqa: E402

PASTE = ROOT / "data" / "seasons" / "paste"
ANS = ROOT / "data" / "seasons" / "ans"


def shards() -> list[Path]:
    return sorted(PASTE.glob("*.txt"))


def answered(path: Path) -> bool:
    return (ANS / (path.stem + ".json")).is_file()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=0, help="指定第几片（1 起，0=自动挑下一片）")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--no-reveal", action="store_true")
    args = ap.parse_args()

    all_shards = shards()
    if not all_shards:
        print("还没有任务包：先跑 python scripts/export_season_tasks.py")
        return 1
    done = [p for p in all_shards if answered(p)]
    print(f"进度：{len(done)}/{len(all_shards)} 片已有答案")
    for p in all_shards:
        print(f"  [{'√' if answered(p) else ' '}] {p.name}")
    if args.status:
        return 0

    todo = [p for p in all_shards if not answered(p)]
    if not todo:
        print("全部贴完了，跑：python scripts/import_season_answers.py")
        return 0
    target = all_shards[args.index - 1] if args.index else todo[0]
    text = target.read_text(encoding="utf-8")
    ok = to_clipboard(text)
    print(f"\n已复制到剪贴板：{target.name}（{len(text)} 字）" if ok else "复制剪贴板失败")
    if not args.no_reveal:
        reveal(target)
    if not args.no_open:
        open_doubao()
    print("把它粘给豆包（Ctrl+V）；回包 JSON 存成："
          f"\n  {(ANS / (target.stem + '.json'))}")
    print("下一片：python scripts\\send_season_tasks.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
