"""数据文件机翻：技能/被动/状态/道具/UI 这类「非剧情」json 的整文件翻译。

与剧情用的 mt_translate.py 同一套机制（术语与标签挖成占位符 → Bing 翻译 → 填回 + 中文标点规范化），
区别是输入输出按**整份 json 结构**走：只翻字符串叶子，其它字段原样保留。

用法：
    python scripts/mt_files.py Skills_Abnormality-a1c10p1.json Bufs-a1c10p1.json …
    python scripts/mt_files.py --list                # 列出第十章待翻的数据文件
产物：data/translate/files/<文件>.json（可直接被 install_supplement.py 装成补译文件）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import mt_translate as mt  # noqa: E402
import translate_pack as tp  # noqa: E402

GAME = Path("D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data")
EN_DIR = GAME / "Assets/Resources_moved/Localize/en"
ZH_DIR = GAME / "Lang/LLC_zh-CN"
OUT = ROOT / "data" / "translate" / "files"

#: RPG 玩法（第十章新增）：RPGSystem/ 下 44 个文件
RPG_FILES = [
    "RPGSystem/rpg-loc-dialogue-common-a1c10p1.json",
    "RPGSystem/rpg-loc-dialogue-route-a.json",
    "RPGSystem/rpg-loc-dialogue-theater.json",
    "RPGSystem/rpg-loc-narration-floor-3.json",
    "RPGSystem/rpg-loc-dialogue-floor-1.json",
    "RPGSystem/rpg-loc-dialogue-floor-2.json",
    "RPGSystem/rpg-loc-dialogue-floor-3.json",
    "RPGSystem/rpg-loc-dialogue-floor-4.json",
    "RPGSystem/rpg-loc-dialogue-floor-b1.json",
    "RPGSystem/rpg-loc-dialogue-floor-b2.json",
    "RPGSystem/rpg-loc-dialogue-choice-common-a1c10p1.json",
    "RPGSystem/rpg-loc-dialogue-choice-floor-1.json",
    "RPGSystem/rpg-loc-dialogue-choice-floor-2.json",
    "RPGSystem/rpg-loc-dialogue-choice-floor-3.json",
    "RPGSystem/rpg-loc-dialogue-choice-floor-b1.json",
    "RPGSystem/rpg-loc-dialogue-choice-floor-b2.json",
    "RPGSystem/rpg-loc-npc-common-a1c10p1.json",
    "RPGSystem/rpg-loc-npc-floor-1.json",
    "RPGSystem/rpg-loc-npc-floor-2.json",
    "RPGSystem/rpg-loc-npc-floor-3.json",
    "RPGSystem/rpg-loc-npc-floor-4.json",
    "RPGSystem/rpg-loc-npc-floor-b1.json",
    "RPGSystem/rpg-loc-npc-floor-b2.json",
    "RPGSystem/rpg-loc-npc-floor-1-a-enemy.json",
    "RPGSystem/rpg-loc-npc-floor-2-a-enemy.json",
    "RPGSystem/rpg-loc-npc-floor-3-a-enemy.json",
    "RPGSystem/rpg-loc-npc-floor-4-a-enemy.json",
    "RPGSystem/rpg-loc-npc-floor-b1-a-enemy.json",
    "RPGSystem/rpg-loc-npc-floor-b2-a-enemy.json",
    "RPGSystem/rpg-loc-npc-route-a-warden.json",
    "RPGSystem/rpg-loc-quest-floor-1.json",
    "RPGSystem/rpg-loc-quest-floor-2.json",
    "RPGSystem/rpg-loc-quest-floor-3.json",
    "RPGSystem/rpg-loc-quest-floor-4.json",
    "RPGSystem/rpg-loc-quest-floor-b1.json",
    "RPGSystem/rpg-loc-quest-floor-b2.json",
    "RPGSystem/rpg-loc-location-floor-1.json",
    "RPGSystem/rpg-loc-location-floor-2.json",
    "RPGSystem/rpg-loc-location-floor-3.json",
    "RPGSystem/rpg-loc-location-floor-4.json",
    "RPGSystem/rpg-loc-location-floor-b1.json",
    "RPGSystem/rpg-loc-location-floor-b2.json",
    "RPGSystem/rpg-loc-item-common-a1c10p1.json",
    "RPGSystem/rpg-loc-ui-common-a1c10p1.json",
]

#: 第十章（含 RPG 玩法）需要翻的数据文件
CH10_FILES = [
    "Skills_Abnormality-a1c10p1.json",
    "Skills_Enemy-a1c10p1.json",
    "Passives_Abnormality-a1c10p1.json",
    "Passives_Enemy-a1c10p1.json",
    "BattleKeywords-a1c10p1.json",
    "Bufs-a1c10p1.json",
    "Items-a1c10p1.json",
    "Enemies-a1c10p1.json",
    "BattleSpeechBubbleDlg-a1c10p1.json",
    "BattleResultHint-a1c10p1.json",
    "MainUIText-a1c10p1.json",
    "PanicInfo-a1c10p1.json",
    "Announcer-a1c10p1.json",
    "StageNode-a1c10p1.json",
    "UnitKeyword-a1c10p1.json",
    "UserTicket-L-a1c10p1.json",
    "UserTicket-R-a1c10p1.json",
    "UserTicket-EGOBg-a1c10p1.json",
    "BattlePass-a1c10.json",
    "IAPProduct-a1c10.json",
    "RPGSuicideBoxUI.json",
]


def en_path(rel: str) -> Path:
    """支持子目录：'RPGSystem/rpg-loc-xxx.json' → EN_RPGSystem/... 不对，实际是 RPGSystem/EN_xxx.json。"""
    p = Path(rel)
    cand = EN_DIR / p.parent / f"EN_{p.name}"
    if cand.is_file():
        return cand
    cand2 = EN_DIR / p.parent / p.name
    return cand2 if cand2.is_file() else EN_DIR / rel


def walk_strings(node, out: list, prefix: list | None = None) -> list[tuple[list, str]]:
    """收集 (路径, 文本)；路径用键/下标列表表示（嵌套 dict 必须带上父键前缀）。"""
    prefix = prefix or []
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("id", "model", "key", "code"):
                continue
            if isinstance(v, (dict, list)):
                walk_strings(v, out, prefix + [k])
            elif isinstance(v, str) and v.strip():
                out.append((prefix + [k], v))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, (dict, list)):
                walk_strings(v, out, prefix + [i])
            elif isinstance(v, str) and v.strip():
                out.append((prefix + [i], v))
    return out


def set_path(root, path: list, value: str) -> None:
    cur = root
    for key in path[:-1]:
        cur = cur[key]
    cur[path[-1]] = value


def translate_leafs(items: list[tuple[list, str]], terms: dict[str, str]) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    out: list[str] = []
    for start in range(0, len(items), mt.CHUNK):
        chunk = items[start:start + mt.CHUNK]
        masked, maps = [], []
        for _path, text in chunk:
            m, mapping = mt.protect(text, terms)
            masked.append(m)
            maps.append(mapping)
        raw = mt.gt("\n".join(masked))
        parts = [p.strip() for p in raw.split("\n") if p.strip()] if raw else []
        if len(parts) == len(chunk):
            restored = [mt.normalize_zh(mt.restore(p, m)) for p, m in zip(parts, maps)]
            if not any(mt._placeholder_left(t) for t in restored):
                out.extend(restored)
                time.sleep(mt.THROTTLE)
                continue
            problems.append(f"第 {start + 1}~{start + len(chunk)} 个字段：占位符未填回，逐条重试")
        else:
            problems.append(f"第 {start + 1}~{start + len(chunk)} 个字段：整批失败（{len(parts)} 行），逐条重试")
        for masked_line, mapping, (_p, raw_line) in zip(masked, maps, chunk):
            text = ""
            for _ in range(3):
                single = mt.gt(masked_line) or ""
                text = mt.normalize_zh(mt.restore(single, mapping))
                if text.strip() and not mt._placeholder_left(text) and text.strip() != raw_line.strip():
                    break
                time.sleep(mt.THROTTLE)
            out.append(text)
            time.sleep(mt.THROTTLE)
    return out, problems


def run_file(name: str, terms: dict[str, str], dry: bool = False) -> dict:
    src = en_path(name)
    if not src.is_file():
        print(f"  {name}: 英文基线里没有这个文件")
        return {"name": name, "ok": False, "reason": "missing"}
    data = json.loads(src.read_text(encoding="utf-8-sig"))
    items: list[tuple[list, str]] = []
    walk_strings(data.get("dataList") if isinstance(data, dict) else data, items)
    if dry:
        print(f"  {name}: {len(items)} 个字段")
        return {"name": name, "ok": True, "fields": len(items)}
    t0 = time.time()
    outs, problems = translate_leafs(items, terms)
    out_data = json.loads(json.dumps(data, ensure_ascii=False))     # 深拷贝
    target = out_data.get("dataList") if isinstance(out_data, dict) else out_data
    for (path, _text), zh in zip(items, outs):
        set_path(target, path, zh)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(out_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    empty = sum(1 for z in outs if not z.strip())
    leaks = sum(1 for z in outs if mt._placeholder_left(z))
    print(f"  {name}: {len(items)} 字段 · {time.time() - t0:.0f}s · 空译 {empty} · 占位符残留 {leaks} · 问题 {len(problems)}")
    for p in problems[:2]:
        print("     ·", p)
    return {"name": name, "ok": empty == 0 and leaks == 0, "fields": len(items), "empty": empty, "leaks": leaks}


PARTS = OUT / ".parts"


def slice_file(name: str, terms: dict[str, str], start: int, end: int) -> dict:
    """只翻 items[start:end]，把结果写成 part 文件。"""
    src = en_path(name)
    if not src.is_file():
        print(f"  {name}: 英文基线里没有")
        return {"name": name, "ok": False}
    data = json.loads(src.read_text(encoding="utf-8-sig"))
    items: list[tuple[list, str]] = []
    walk_strings(data.get("dataList") if isinstance(data, dict) else data, items)
    chunk = items[start:end]
    t0 = time.time()
    outs, problems = translate_leafs(chunk, terms)
    PARTS.mkdir(parents=True, exist_ok=True)
    part = PARTS / f"{name.replace('/', '__')}.{start}-{end}.json"
    part.write_text(json.dumps({"name": name, "start": start, "end": end,
                                "pairs": [[path, zh] for (path, _t), zh in zip(chunk, outs)]},
                               ensure_ascii=False), encoding="utf-8")
    empty = sum(1 for z in outs if not z.strip())
    leaks = sum(1 for z in outs if mt._placeholder_left(z))
    print(f"  {name}[{start}:{end}]: {len(chunk)} 字段 · {time.time() - t0:.0f}s · "
          f"空译 {empty} · 占位符残留 {leaks} · 问题 {len(problems)} → {part.name}")
    return {"name": name, "ok": empty == 0 and leaks == 0, "part": str(part)}


def join_parts(name: str) -> bool:
    """把该文件的所有 part 合并成最终文件（结构取自英文基线）。

    切片可能是在旧版 walk_strings（嵌套路径缺父键）下生成的，那些路径回填会失败；
    这里按「切片范围 + 字段顺序」做一次重映射兜底，绝不再静默丢字段。
    """
    src = en_path(name)
    if not src.is_file():
        print(f"  {name}: 英文基线里没有")
        return False
    data = json.loads(src.read_text(encoding="utf-8-sig"))
    target = data.get("dataList") if isinstance(data, dict) else data
    items: list[tuple[list, str]] = []
    walk_strings(target, items)          # 修正后的正确路径（顺序与切片时一致）
    parts = sorted(PARTS.glob(f"{name.replace('/', '__')}.*.json"))
    if not parts:
        print(f"  {name}: 没有 part 文件")
        return False
    applied = failed = 0
    for part in parts:
        obj = json.loads(part.read_text(encoding="utf-8"))
        pairs = obj.get("pairs") or []
        start = int(obj.get("start") or 0)
        for idx, (path, zh) in enumerate(pairs):
            ok = True
            try:
                set_path(target, path, zh)
            except (KeyError, IndexError, TypeError):
                ok = False
            if not ok:                    # 旧切片路径：按顺序重映射
                pos = start + idx
                if 0 <= pos < len(items):
                    try:
                        set_path(target, items[pos][0], zh)
                        ok = True
                    except (KeyError, IndexError, TypeError):
                        ok = False
            applied += 1 if ok else 0
            failed += 0 if ok else 1
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {name}: 合并 {applied} 个字段（{len(parts)} 个 part）" + (f"，失败 {failed}" if failed else ""))
    return failed == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--slice", default="", help="只翻第 A:B 个字段（写到 .parts，之后用 --join 合并）")
    ap.add_argument("--join", action="store_true", help="把 .parts 合并成最终文件")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--engine", choices=("bing", "google"), default="bing")
    args = ap.parse_args()
    mt.ENGINE = args.engine
    names = args.names or CH10_FILES
    terms = mt.term_map()
    if args.list:
        for n in names:
            run_file(n, terms, dry=True)
        return 0
    if args.join:
        ok = all(join_parts(n) for n in names)
        return 0 if ok else 1
    if args.slice:
        try:
            a, b = (int(x) for x in args.slice.split(":"))
        except ValueError:
            print("--slice 形如 0:220")
            return 2
        results = [slice_file(n, terms, a, b if b > 0 else 10 ** 6) for n in names]
        bad = [r for r in results if not r.get("ok")]
        print(f"切片完成 {len(results) - len(bad)}/{len(results)}" + (f"，失败 {[b['name'] for b in bad]}" if bad else ""))
        print("全部切片跑完后：python scripts/mt_files.py <同样的文件> --join")
        return 0
    print(f"待翻 {len(names)} 个数据文件 · 强制术语 {len(terms)} 条")
    results = [run_file(n, terms, dry=args.dry_run) for n in names]
    bad = [r for r in results if not r.get("ok")]
    print(f"完成 {len(results) - len(bad)}/{len(results)}" + (f"，失败：{[b['name'] for b in bad]}" if bad else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
