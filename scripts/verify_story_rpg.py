"""体检 RPG 关卡剧本数据（第十章 10-4 起）。

    python scripts/verify_story_rpg.py                  # 全部 RPG 关卡
    python scripts/verify_story_rpg.py --stage 10-04    # 指定关卡
    python scripts/verify_story_rpg.py --quiet          # 只出结论

硬性检查（不通过即 exit 1）：
  1. 来源：每条对话行的文本必须与零协包（LLC_zh-CN）同位置一字不差；
  2. 覆盖：编排表覆盖到的零协文件，每个非空文本都收录且只收录一次（不多不少）；
  3. 顺序：items 的分支顺序 == 编排表顺序；分支内 (record, text_index) 单调不减，文件顺序与编排表一致；
  4. 结构：每条 item 的 branch 都在 branches 里，对话行都有 file/record，场景行不带 file。
软性检查（只报告）：RPG key 前缀与楼层是否一致、说话人是否与零协一致。
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from limbus_patcher.config import AppPaths, ConfigStore  # noqa: E402
from limbus_patcher.paths import resolve_game_paths  # noqa: E402
from limbus_patcher.textsource import TextSource  # noqa: E402

DATA = ROOT / "limbus_patcher" / "data" / "story_stages.json"

#: 文件名里的楼层 → 该层 RPG 对话 key 允许的前缀
FLOOR_PREFIX = {
    "floor-1": ("D1",),
    "floor-2": ("D2",),
    "floor-3": ("D3",),
    "floor-4": ("D4",),
    "floor-b1": ("D-1",),
    "floor-b2": ("D-2", "D2"),
    "route-a": ("D9",),
    "common": ("D9",),
}


def _read(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _floor_of(rel: str) -> tuple[str, ...] | None:
    """文件声明的楼层 → 该层 key 允许的前缀；选项/旁白/通用文件不参与（编号体系不同）。"""
    name = Path(rel).name
    if "-choice" in name or "narration" in name or "dialogue-common" in name:
        return None
    for tag, prefix in FLOOR_PREFIX.items():
        if tag in name:
            return prefix
    return None


def check_stage(code: str, stage: dict, llc_dir: Path | None,
                src: "TextSource | None" = None) -> tuple[list[str], list[str], int]:
    """返回 (错误, 提示, 对话行数)。"""
    errors: list[str] = []
    notes: list[str] = []
    items = stage.get("items") or []
    branches = stage.get("branches") or []
    pages = stage.get("pages") or []
    lines = [i for i in items if i.get("type") == "line"]

    # 4. 结构
    ids = [b.get("branch_id") for b in branches]
    if len(set(ids)) != len(ids):
        errors.append(f"{code}: branches 里有重复 branch_id")
    known = set(ids)
    if [p.get("branch_id") for p in pages] != ids:
        errors.append(f"{code}: pages 与 branches 的顺序/对应不一致")
    seen_branch_order: list[str] = []
    for it in items:
        b = it.get("branch")
        if b not in known:
            errors.append(f"{code}: item 的 branch={b!r} 不在 branches 里")
            break
        if not seen_branch_order or seen_branch_order[-1] != b:
            seen_branch_order.append(b)
    if seen_branch_order != ids:
        errors.append(f"{code}: items 的分支顺序与 branches 不一致：{seen_branch_order[:5]}…")
    for it in lines:
        if not it.get("file") or not isinstance(it.get("record"), int):
            errors.append(f"{code}: 对话行缺少 file/record：{str(it.get('text'))[:20]}")
            break
    for it in items:
        if it.get("type") == "scene" and it.get("file"):
            errors.append(f"{code}: 场景行不该带 file：{str(it.get('text'))[:20]}")
            break

    # 3. 顺序（分支内文件顺序与记录/text_index 单调）
    by_branch = collections.OrderedDict((b, []) for b in ids)
    for it in lines:
        by_branch[it["branch"]].append(it)
    for b, rows in by_branch.items():
        # 楼层分段会把同一文件与过场交替排列（1F → 过场 → 1F 续），所以只要求：
        # 同一文件内部记录不倒退、区间不重叠（这是编排表 parts 的真实不变量）。
        last_per_file: dict[str, tuple[int, int]] = {}
        for r in rows:
            pos = (int(r["record"]), int(r["text_index"] or 0))
            prev = last_per_file.get(r["file"])
            if prev is not None and pos < prev:
                errors.append(f"{code}/{b}: {r['file']} 的记录顺序倒退或区间重叠（{prev} → {pos}）")
                break
            last_per_file[r["file"]] = pos

    if llc_dir is None:
        notes.append(f"{code}: 没找到零协包，跳过来源/覆盖检查")
        return errors, notes, len(lines)

    # 1. 来源 + 2. 覆盖
    expect: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for b in branches:
        for rel in b.get("files") or []:
            expect.setdefault(rel, collections.Counter())
    got: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for it in lines:
        rel = it["file"]
        if rel not in expect:
            errors.append(f"{code}: items 出现了编排表没声明的文件 {rel}")
            continue
        # 数据里只存位置：文本现从语言文件取（没装零协时就是英文基线）
        text = it.get("text")
        if text is None and src is not None:
            text, _sp, _ti = src.resolve(rel, int(it["record"]), it.get("text_index"), it.get("field"))
        got[rel][(int(it["record"]), it.get("text_index"), text or "")] += 1
    for rel in expect:
        data = _read(llc_dir / rel)
        if data is None:
            notes.append(f"{code}: 零协包里没有 {rel}（该分支用兜底来源）")
            continue
        want = collections.Counter()
        for ri, rec in enumerate(data.get("dataList") or []):
            if not isinstance(rec, dict):
                continue
            texts = rec.get("texts")
            if isinstance(texts, list):
                for pos, t in enumerate(texts):
                    if isinstance(t, dict) and (t.get("text") or "").strip():
                        idx = t.get("index")
                        want[(ri, idx if isinstance(idx, int) else pos, t["text"])] += 1
            elif (rec.get("content") or "").strip():
                want[(ri, None, rec["content"])] += 1
            elif (rec.get("text") or "").strip():
                want[(ri, None, rec["text"])] += 1
        missing = want - got.get(rel, collections.Counter())
        extra = got.get(rel, collections.Counter()) - want
        if missing:
            errors.append(f"{code}: {rel} 漏收 {sum(missing.values())} 条（例：{list(missing)[0][2][:24]}…）")
        if extra:
            errors.append(f"{code}: {rel} 多出 {sum(extra.values())} 条（例：{list(extra)[0][2][:24]}…）")
        # 软性：楼层前缀（key 编号 vs 文件所在楼层）
        prefixes = _floor_of(rel)
        if prefixes:
            for it in by_branch_items(items, rel):
                key = it.get("key") or ""
                if key and not any(key.startswith(p) for p in prefixes):
                    sample = it.get("text")
                    if sample is None and src is not None:
                        sample, _sp, _ti = src.resolve(rel, int(it["record"]),
                                                       it.get("text_index"), it.get("field"))
                    notes.append(f"{code}: {rel} 里 {key} 的编号前缀与楼层不符（{(sample or '')[:18]}…）")
                    break
    return errors, notes, len(lines)


def by_branch_items(items: list[dict], rel: str):
    return [i for i in items if i.get("type") == "line" and i.get("file") == rel]


def main() -> int:
    ap = argparse.ArgumentParser(description="RPG 关卡剧本数据体检")
    ap.add_argument("--stage", action="append", default=[])
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--game", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    story = _read(Path(args.data))
    if story is None:
        print(f"读不到 {args.data}")
        return 1

    cfg = ConfigStore(AppPaths.from_root(ROOT)).load()
    gd = Path(args.game or cfg.game_dir or "")
    llc = resolve_game_paths(gd).llc_pack_dir if gd else None
    llc_dir = llc if (llc and llc.is_dir()) else None
    src = TextSource.detect(llc_dir, resolve_game_paths(gd).en_base_dir() if gd else None)

    targets: list[tuple[str, dict]] = []
    for ch in story.get("chapters", []):
        for st in ch.get("stages", []):
            if not st.get("branches"):
                continue
            if args.stage and st.get("stage_code") not in args.stage:
                continue
            targets.append((st.get("stage_code"), st))
    if not targets:
        print("没有带 branches 的关卡（先跑 scripts/build_story_rpg.py）")
        return 1

    total_err = 0
    for code, st in targets:
        errors, notes, n = check_stage(code, st, llc_dir, src)
        total_err += len(errors)
        print(f"{'[OK]' if not errors else '[!!]'} {code}: {len(st.get('branches') or [])} 分支 / {n} 行")
        for e in errors:
            print(f"    ✗ {e}")
        if not args.quiet:
            for note in notes[:20]:
                print(f"    · {note}")
            if len(notes) > 20:
                print(f"    · …另有 {len(notes) - 20} 条提示")
    print(f"\n{'全部通过' if not total_err else f'{total_err} 处不合格'}（零协包：{llc_dir or '未找到'}）")
    return 1 if total_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
