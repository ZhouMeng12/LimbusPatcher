"""分类数据校验与缺失清单（用户手工维护分类时的辅助工具）。

用法：
    python scripts/check_maps.py [--game-dir <游戏目录>] [--llc-dir <零协包目录>] [--en-dir <EN基线目录>]

检查项：
1. limbus_patcher/data/category_rules.json  格式、分类 id 引用、正则可编译；
2. limbus_patcher/data/season_map.json      格式、人格/E.G.O id 缺失清单；
3. limbus_patcher/data/enemy_map.json       格式、敌方 id 缺失清单。

给出 --game-dir 或 --llc-dir/--en-dir 时，会读取实际文件列出「尚未标注」的 id。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from limbus_patcher.fsutil import load_json  # noqa: E402

DATA = ROOT / "limbus_patcher" / "data"
PROBLEMS: list[str] = []


def fail(msg: str) -> None:
    PROBLEMS.append(msg)


def check_category_rules() -> None:
    p = DATA / "category_rules.json"
    obj, err = load_json(p)
    if obj is None:
        fail(f"category_rules.json 不可读：{err}")
        return
    if not isinstance(obj, dict) or obj.get("format_version") != 1:
        fail("category_rules.json 缺少 format_version=1")
        return
    cats = obj.get("categories") or {}
    groups = obj.get("groups") or {}
    rules = obj.get("rules") or []
    members: set[str] = set()
    for gid, g in groups.items():
        if not isinstance(g, dict) or not isinstance(g.get("members"), list):
            fail(f"groups.{gid} 结构错误")
            continue
        members.update(str(m) for m in g["members"])
    if set(cats) - members:
        fail(f"分类未归入任何分组：{sorted(set(cats) - members)}")
    if members - set(cats):
        fail(f"分组引用了不存在的分类：{sorted(members - set(cats))}")
    for i, r in enumerate(rules):
        if not (isinstance(r, list) and len(r) == 2 and isinstance(r[0], str) and isinstance(r[1], str)):
            fail(f"rules[{i}] 应为 [正则, 分类id]")
            continue
        try:
            re.compile(r[0], re.I)
        except re.error as e:
            fail(f"rules[{i}] 正则错误：{e}")
        if r[1] not in cats:
            fail(f"rules[{i}] 分类 id 不存在：{r[1]}")
    print(f"category_rules.json：{len(cats)} 分类 / {len(groups)} 分组 / {len(rules)} 条规则")


def _check_map(name: str, sections: tuple[str, ...]) -> dict | None:
    p = DATA / name
    obj, err = load_json(p)
    if obj is None:
        fail(f"{name} 不可读：{err}")
        return None
    if not isinstance(obj, dict):
        fail(f"{name} 根节点必须是对象")
        return None
    for sec in sections:
        if not isinstance(obj.get(sec), dict):
            fail(f"{name}.{sec} 必须是对象")
    return obj


def collect_ids(en_dir: Path | None, llc_dir: Path | None, game_dir: Path | None) -> dict[str, set[str]]:
    """从实际数据收集 id：identities / egos / enemies。"""
    out: dict[str, set[str]] = {"identities": set(), "egos": set(), "enemies": set()}
    bases: list[Path] = []
    if en_dir:
        bases.append(Path(en_dir))
    if llc_dir:
        bases.append(Path(llc_dir))
    if game_dir:
        bases.append(Path(game_dir) / "LimbusCompany_Data" / "Assets" / "Resources_moved" / "Localize" / "en")
    files = {"identities": "Personalities.json", "egos": "Egos.json", "enemies": "Enemies"}
    for base in bases:
        for key, fname in files.items():
            for cand in (base / fname, base / f"EN_{fname}"):
                if cand.is_file():
                    obj, err = load_json(cand)
                    if isinstance(obj, dict):
                        out[key].update(str(e.get("id")) for e in obj.get("dataList", []) if isinstance(e, dict))
    # 敌方章节文件（EN_Enemies-*.json / Enemies-*.json）
    for base in bases:
        for pat in ("EN_Enemies*.json", "Enemies*.json"):
            for f in base.glob(pat):
                obj, err = load_json(f)
                if isinstance(obj, dict):
                    out["enemies"].update(str(e.get("id")) for e in obj.get("dataList", []) if isinstance(e, dict))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir", type=Path, default=None)
    ap.add_argument("--llc-dir", type=Path, default=None)
    ap.add_argument("--en-dir", type=Path, default=None)
    args = ap.parse_args()

    print("== 1. 分类规则 ==")
    check_category_rules()

    print("== 2. 赛季映射 ==")
    season = _check_map("season_map.json", ("identities", "egos"))
    if season:
        print(f"season_map.json：人格 {len(season['identities'])} 条 / E.G.O {len(season['egos'])} 条 / 生成时间 {season.get('generated_at')}")

    print("== 3. 敌方种类映射 ==")
    enemy = _check_map("enemy_map.json", ("enemies",))
    if enemy:
        dist = Counter((v.get("group"), v.get("label")) for v in enemy["enemies"].values())
        print(f"enemy_map.json：{len(enemy['enemies'])} 条 / 生成时间 {enemy.get('generated_at')}")
        print("  分布：", dict(dist.most_common(10)))

    if args.game_dir or args.llc_dir or args.en_dir:
        print("== 4. 缺失清单 ==")
        ids = collect_ids(args.en_dir, args.llc_dir, args.game_dir)
        if season:
            for key, sec in (("identities", "identities"), ("egos", "egos")):
                missing = sorted(ids[key] - set(season[sec]))
                label = "人格" if key == "identities" else "E.G.O"
                if missing:
                    print(f"{label} 未标注（{len(missing)}）：{', '.join(missing[:40])}{'…' if len(missing) > 40 else ''}")
                else:
                    print(f"{label}：全部已标注")
        if enemy:
            missing = sorted(ids["enemies"] - set(enemy["enemies"]))
            if missing:
                print(f"敌方未标注（{len(missing)}）：{', '.join(missing[:40])}{'…' if len(missing) > 40 else ''}")
            else:
                print("敌方：全部已标注")

    if PROBLEMS:
        print(f"\n共 {len(PROBLEMS)} 个问题：")
        for p in PROBLEMS:
            print("  ✘", p)
        return 1
    print("\n全部检查通过 ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
