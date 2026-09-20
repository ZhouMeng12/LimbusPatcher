"""按编排表重建 RPG 关卡的剧本数据（第十章 10-4 起）。

    python scripts/build_story_rpg.py --stage 10-04            # 只重建 10-04
    python scripts/build_story_rpg.py --all-rpg                # 编排表里所有关卡
    python scripts/build_story_rpg.py --stage 10-04 --dry-run   # 只看会生成什么

文本来源：零协包（``Lang/LLC_zh-CN``）优先 → ``data/supplement`` → 英文基线（仅兜底）。
生成结果写回 ``limbus_patcher/data/story_stages.json`` 的对应 stage：
``branches``（玩家游玩顺序的分支）/ ``pages``（每分支一页，含多文件）/ ``items``（逐行）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from limbus_patcher.config import AppPaths, ConfigStore  # noqa: E402
from limbus_patcher.paths import resolve_game_paths  # noqa: E402
from limbus_patcher.story_rpg import build_stage, dump_json_crlf, load_plan  # noqa: E402

DATA = ROOT / "limbus_patcher" / "data" / "story_stages.json"


def resolve_dirs(game_dir: str | None) -> tuple[Path, Path | None, Path | None]:
    """返回 (零协包目录, supplement 目录, 英文基线目录)。"""
    cfg = ConfigStore(AppPaths.from_root(ROOT)).load()
    gd = Path(game_dir or cfg.game_dir or "")
    paths = resolve_game_paths(gd)
    llc = paths.llc_pack_dir
    if not llc.is_dir():
        raise SystemExit(f"零协包不存在：{llc}\n（用 --game 指定游戏目录，或先在程序里设置游戏目录）")
    en = paths.en_base_dir()
    return llc, ROOT / "data" / "supplement", (en if en.is_dir() else None)


def find_stage(data: dict, code: str) -> dict | None:
    for ch in data.get("chapters", []):
        for st in ch.get("stages", []):
            if st.get("stage_code") == code:
                return st
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="按编排表重建 RPG 关卡剧本数据")
    ap.add_argument("--stage", action="append", default=[], help="关卡号，如 10-04（可重复）")
    ap.add_argument("--all-rpg", action="store_true", help="重建编排表里的全部关卡")
    ap.add_argument("--game", default=None, help="游戏目录（默认读 data/config.json）")
    ap.add_argument("--data", default=str(DATA), help="story_stages.json 路径")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = ap.parse_args()

    plan = load_plan()
    targets = list(args.stage)
    if args.all_rpg:
        targets += [c for c in (plan.get("stages") or {}) if c not in targets]
    if not targets:
        targets = [c for c in (plan.get("stages") or {})]
    if not targets:
        print("编排表里没有可用关卡（limbus_patcher/data/story_rpg_plan.json）")
        return 1

    llc, supplement, en = resolve_dirs(args.game)
    data_path = Path(args.data)
    try:
        story = json.loads(data_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读不到剧本数据 {data_path}：{exc}")
        return 1

    total_lines = 0
    for code in targets:
        st_plan = (plan.get("stages") or {}).get(code)
        if not st_plan:
            print(f"[跳过] {code}：编排表里没有这个关卡")
            continue
        stage = find_stage(story, code)
        if stage is None:
            print(f"[跳过] {code}：story_stages.json 里没有这个关卡")
            continue
        built = build_stage(st_plan, llc, supplement_dir=supplement, en_dir=en)
        items = built["items"]
        lines = sum(1 for i in items if i.get("type") == "line")
        total_lines += lines
        stage["mode"] = st_plan.get("mode") or "rpg"
        stage["branch_source"] = "limbus_patcher/data/story_rpg_plan.json"
        stage["branches"] = built["branches"]
        stage["pages"] = built["pages"]
        stage["items"] = items
        print(f"\n=== {code} {st_plan.get('label') or ''} → {len(built['branches'])} 分支 / "
              f"{lines} 行 / {len(items) - lines} 场景行")
        per = {}
        for it in items:
            if it.get("type") == "line":
                per[it.get("branch")] = per.get(it.get("branch"), 0) + 1
        for br in built["branches"]:
            conf = br.get("confidence") or "-"
            print(f"    {br['branch_id']:>4s} {br['label'][:34]:36s} {per.get(br['branch_id'], 0):5d} 行  "
                  f"[{br['kind_label']}] 置信 {conf}")
        for w in built["warnings"]:
            print(f"    ⚠ {w}")

    if args.dry_run:
        print(f"\n[dry-run] 未写入。合计 {total_lines} 行。")
        return 0
    dump_json_crlf(data_path, story)
    print(f"\n已写入 {data_path}（{total_lines} 行）")
    # 运行时还有两份副本会盖过包数据：开发态读 data/wiki_story/，打包版读 <exe>/data/cache/
    # （Storybook 的加载顺序是 overlay → 开发爬取目录 → 包数据），存在就一起刷新。
    for extra in (ROOT / "data" / "wiki_story" / "story_stages.json",
                  ROOT / "dist" / "data" / "cache" / "story_stages.json"):
        if extra.is_file() and extra.resolve() != data_path.resolve():
            dump_json_crlf(extra, story)
            print(f"已同步运行时副本 {extra}")
    print("提醒：程序里需重启并点「应用到游戏」，剧本模式才会看到新数据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
