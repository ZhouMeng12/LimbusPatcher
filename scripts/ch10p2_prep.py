"""第10章第二部分（a1c10p2）补译准备：清点 → 建翻译记忆 → 预填 → 切任务包。

零协包这次完全没有 c10p2 / 新 RPG 路线 B 的文件，所以全部得自己翻。
为了又快又一致：
  1) 先用「英文原文 → 已有中文」的全局记忆（零协包 + 我们已译文件）把能复用的先填上；
  2) 剩下的按文件切成任务包 data/translate/ch10p2/tasks/*.json，交给 AI 分批翻；
  3) ch10p2_apply.py 再把答案合回完整结构，落到 data/translate/files/。

用法：
    python scripts/ch10p2_prep.py --stats      # 只看规模与记忆覆盖率
    python scripts/ch10p2_prep.py              # 生成任务包
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

GAME = Path("D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data")
EN_DIR = GAME / "Assets/Resources_moved/Localize/en"
LLC_DIR = GAME / "Lang" / "LLC_zh-CN"
OUR_DIR = ROOT / "data" / "translate" / "files"
OUT_DIR = ROOT / "data" / "translate" / "files"
WORK = ROOT / "data" / "translate" / "ch10p2"
TASKS = WORK / "tasks"
PREFILL = WORK / "prefill"

#: 第10章第二部分新增的剧情文件（零协全缺）
STORY_FILES = [f"StoryData/S{n}B.json" for n in range(1017, 1030)]
STORY_FILES += ["StoryData/S9992B.json", "StoryData/P10917.json"]

#: 第10章第二部分新增的根数据文件
ROOT_FILES = [
    "AbnormalityGuides-a1c10p2.json",
    "Assist-a1c10p2.json",
    "BattleKeywords-a1c10p2.json",
    "BattleResultHint-a1c10p2.json",
    "BattleSpeechBubbleDlg-a1c10p2.json",
    "Bufs-a1c10p2.json",
    "Enemies-a1c10p2.json",
    "PanicInfo-a1c10p2.json",
    "Passives_Abnormality-a1c10p2.json",
    "Passives_Assist-a1c10p2.json",
    "Skills_Abnormality-a1c10p2.json",
    "Skills_Assist-a1c10p2.json",
]

#: 这些键不是给人看的（内部 id / 资源名），不翻
SKIP_KEYS = {
    "id", "model", "key", "code", "codeName", "index", "level", "sprite", "icon",
    "prefab", "sound", "bgm", "path", "font", "color", "image", "illust", "portrait",
    "category", "group", "type", "kind", "order", "value", "count", "turn", "num",
}
#: 这些字段是说明文字里的效果 id / 标签宿主，值本身要翻，但 [xxx] 里的 id 不能动
DESC_FIELDS = {"desc", "summary", "statText", "effect", "lowMoraleDescription",
               "panicDescription", "description"}

_NAME_RE = re.compile(r"^[A-Za-z0-9_\-\.\/]+$")
_HANGUL = re.compile(r"[\uac00-\ud7af]")


def en_path(rel: str) -> Path:
    p = Path(rel)
    cand = EN_DIR / p.parent / f"EN_{p.name}"
    return cand if cand.is_file() else EN_DIR / rel


def llc_path(rel: str) -> Path:
    return LLC_DIR / rel


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def walk(node, out: list, prefix: list | None = None, parent_key: str = "", ctx=None) -> None:
    """收集 (路径, 文本, 上下文)：跳过内部 id 键；路径用键/下标列表表示。

    上下文取同一层的 speaker / teller / name / title，给翻译时判断语气用。
    """
    prefix = prefix or []
    if isinstance(node, dict):
        here = {k: node.get(k) for k in ("speaker", "teller", "name", "title")
                if isinstance(node.get(k), str) and node.get(k).strip()}
        merged = {**(ctx or {}), **here}
        for k, v in node.items():
            if k in SKIP_KEYS:
                continue
            if isinstance(v, (dict, list)):
                walk(v, out, prefix + [k], k, merged)
            elif isinstance(v, str) and v.strip():
                out.append((prefix + [k], v, merged))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, (dict, list)):
                walk(v, out, prefix + [i], parent_key, ctx)
            elif isinstance(v, str) and v.strip():
                out.append((prefix + [i], v, ctx or {}))


def body(data):
    return data.get("dataList") if isinstance(data, dict) else data


# ---------------- 翻译记忆 ----------------

def build_memory() -> dict[str, str]:
    """遍历「英文与中文成对存在」的所有文件，按相同路径抽 en→zh。"""
    mem: dict[str, Counter] = defaultdict(Counter)

    def feed(rel: str, zh_root: Path):
        ep = en_path(rel)
        if not ep.is_file() or not zh_root.is_file():
            return
        try:
            ed, zd = body(load(ep)), body(load(zh_root))
        except Exception:
            return
        ei, zi = [], []
        walk(ed, ei)
        walk(zd, zi)
        if len(ei) != len(zi):
            return
        for (p1, e, _c1), (_p2, z, _c2) in zip(ei, zi):
            if not e.strip() or not z.strip():
                continue
            if _HANGUL.search(z):          # 零协里残留的韩文不算数
                continue
            if z.strip() == e.strip():     # 没翻的（仍是英文）不算数
                continue
            mem[e][z] += 1

    for rel in _all_game_rels():
        feed(rel, llc_path(rel))
    # 我们自己的译文（含 RPG 路线 A，路线 B 大量复用）
    for p in sorted(OUR_DIR.rglob("*.json")):
        if ".parts" in p.parts:
            continue
        rel = p.relative_to(OUR_DIR).as_posix()
        feed(rel, p)
    return {e: c.most_common(1)[0][0] for e, c in mem.items()}


def _all_game_rels() -> list[str]:
    rels = []
    for p in sorted(EN_DIR.glob("*.json")):
        if p.name.startswith("EN_"):
            rels.append(p.name[3:])
    for sub in ("StoryData", "RPGSystem"):
        d = EN_DIR / sub
        if d.is_dir():
            for p in sorted(d.glob("EN_*.json")):
                rels.append(f"{sub}/{p.name[3:]}")
    return rels


def new_files() -> list[str]:
    out = list(STORY_FILES) + list(ROOT_FILES)
    llc_rpg = set()
    d = LLC_DIR / "RPGSystem"
    if d.is_dir():
        llc_rpg = {p.name for p in d.glob("*.json")}
    for p in sorted((EN_DIR / "RPGSystem").glob("EN_*.json")):
        if p.name[3:] not in llc_rpg:
            out.append(f"RPGSystem/{p.name[3:]}")
    return out


# ---------------- 主流程 ----------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--per", type=int, default=260, help="每个任务包最多多少条")
    ap.add_argument("--chars", type=int, default=16000, help="每个任务包约多少英文字符")
    args = ap.parse_args()

    files = new_files()
    print(f"待处理文件 {len(files)} 个（剧情 {len(STORY_FILES)} · 数据 {len(ROOT_FILES)} · RPG {len(files) - len(STORY_FILES) - len(ROOT_FILES)}）")

    mem = build_memory()
    print(f"翻译记忆 {len(mem)} 条")

    todo: list[dict] = []
    prefill: dict[str, list] = defaultdict(list)
    stat_rows = []
    for rel in files:
        ep = en_path(rel)
        if not ep.is_file():
            print(f"  ! 英文基线缺 {rel}")
            continue
        data = load(ep)
        items: list = []
        walk(body(data), items)
        hit = 0
        for idx, (path, en, ctx) in enumerate(items):
            zh = mem.get(en)
            # 记忆里的译文本身不能再是英文/韩文
            if zh and not _HANGUL.search(zh):
                prefill[rel].append([path, zh])
                hit += 1
            else:
                slot = {"id": f"{rel}#{idx}", "file": rel, "field": str(path[-1]),
                        "en": en, "path": path}
                if ctx:
                    slot["ctx"] = ctx
                todo.append(slot)
        stat_rows.append((rel, len(items), hit))

    total = sum(r[1] for r in stat_rows)
    hits = sum(r[2] for r in stat_rows)
    chars = sum(len(t["en"]) for t in todo)
    print(f"文本叶子 {total} · 记忆复用 {hits}（{hits / max(total, 1) * 100:.1f}%）· 待翻 {len(todo)} 条 / {chars} 字符")

    # 按原文去重：同一句英文在多个文件里重复出现，只翻一次
    uniq: dict[str, dict] = {}
    for t in todo:
        e = t["en"]
        if e in uniq:
            uniq[e]["ids"].append(t["id"])
        else:
            uniq[e] = {"en": e, "ids": [t["id"]],
                       "file": t["file"], "field": t["field"],
                       "ctx": t.get("ctx", {})}
    print(f"去重后唯一原文 {len(uniq)} 条 / {sum(len(v['en']) for v in uniq.values())} 字符")

    if args.stats:
        for rel, n, h in stat_rows:
            if n - h:
                print(f"   {rel:52s} {h:5d}/{n:5d}")
        return 0

    PREFILL.mkdir(parents=True, exist_ok=True)
    for rel, pairs in prefill.items():
        safe = rel.replace("/", "__")
        (PREFILL / f"{safe}.json").write_text(
            json.dumps({"file": rel, "pairs": pairs}, ensure_ascii=False), encoding="utf-8")

    TASKS.mkdir(parents=True, exist_ok=True)
    for f in TASKS.glob("*.json"):
        f.unlink()
    # 按文件分组切包，尽量不打散上下文（同一句只出现一次，ids 里带全部落点）
    by_file: dict[str, list] = defaultdict(list)
    for v in uniq.values():
        by_file[v["file"]].append(v)
    # 按「文件顺序 + 累积字符数」打包：同一文件的句子尽量挨在一起，包大小可控
    ordered = [v for rel in files for v in (by_file.get(rel) or [])]
    batch, cur, cur_chars = [], [], 0
    for v in ordered:
        cur.append(v)
        cur_chars += len(v["en"])
        if cur_chars >= args.chars or len(cur) >= args.per:
            batch.append(cur)
            cur, cur_chars = [], 0
    if cur:
        batch.append(cur)
    n = 0
    for b in batch:
        n += 1
        name = f"batch_{n:03d}.json"
        (TASKS / name).write_text(json.dumps(
            {"batch": name, "files": sorted({x["file"] for x in b}), "count": len(b),
             "chars": sum(len(x["en"]) for x in b), "items": b},
            ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"任务包 {len(batch)} 个（每包约 {args.chars} 字符）→ {TASKS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
