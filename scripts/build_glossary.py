"""构建新章节翻译用的「术语表 + 说话人对照 + 新词候选」。

思路（全部机械对齐，不靠人肉回忆）：
1. **术语表**：英文基线 `Localize/en/EN_<name>.json` 与零协包 `<name>.json` 结构互镜像，
   按 `id` + 字段路径配对，就能拿到「官方英文名 ↔ 零协中文名」——专有名词以零协既有译法为准。
   覆盖：状态/关键词（BattleKeywords/Bufs/SkillTag）、人格/EGO/敌方/被动名、技能名等。
2. **说话人对照**：剧情记录的 `model`（韩文立绘 id）两边一致，用第 1~9 章的零协译文反查
   「model → 中文说话人」，新章节（第十章）里同一个 model 直接照抄叫法。
3. **新词候选**：从新章节英文里抽大写词组/引号词，去掉术语表已覆盖的，
   再把该词在第 1~9 章出现过的「英文行 + 零协中文行」找出来当证据，供人工/AI 定译名。

用法：
    python scripts/build_glossary.py [--chapter 10] [--out data/translate]
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

DEFAULT_ZH = r"D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data/Lang/LLC_zh-CN"
DEFAULT_EN = (r"D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data"
              r"/Assets/Resources_moved/Localize/en")

#: 参与术语抽取的表（文件同名，EN 侧加 EN_ 前缀）
NAME_TABLES = {
    "BattleKeywords": "关键词/状态",
    "Bufs": "buff",
    "SkillTag": "技能标签",
    "Personalities": "人格",
    "Egos": "E.G.O",
    "Enemies": "敌方",
    "Passives": "被动",
    "Skills": "技能",
    "Abilities": "能力",
    "Items": "道具",
    "StageChapterText": "章节名",
    "StoryTheater": "放映厅",
}
#: 名字字段（按优先级）
NAME_FIELDS = ("name", "title", "nameWithTitle", "simpleDesc", "behaviorDesc")
#: 抽新词时忽略的大写词（句首词/常见词）
STOP = {
    "The", "A", "An", "I", "It", "He", "She", "They", "We", "You", "But", "And", "Or", "If", "So",
    "No", "Yes", "Not", "Do", "Did", "Does", "Is", "Are", "Was", "Were", "What", "Why", "How",
    "When", "Where", "Who", "That", "This", "There", "Then", "Than", "Now", "Oh", "Ah", "Well",
    "Just", "Like", "Look", "Come", "Let", "Get", "Got", "Have", "Has", "Had", "Will", "Would",
    "Can", "Could", "Should", "May", "Might", "Must", "One", "Two", "Three", "All", "Some",
    "My", "Your", "His", "Her", "Our", "Their", "Me", "Him", "Them", "Us", "Here", "Very",
    "Even", "Still", "Only", "Also", "Too", "Much", "Many", "More", "Most", "Good", "Great",
    "Sorry", "Please", "Thank", "Thanks", "Hello", "Hey", "Wait", "Stop", "Right", "Okay", "OK",
    "Anyway", "Because", "Before", "After", "Again", "Never", "Always", "Ever", "Nothing",
}


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def records(path: Path) -> list:
    data = load(path)
    dl = data.get("dataList") if isinstance(data, dict) else None
    return dl if isinstance(dl, list) else []


def walk(obj, prefix=""):
    """产出 (字段路径, 文本)。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("id", "model"):
                continue
            yield from walk(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{prefix}[{i}]")
    elif isinstance(obj, str) and obj.strip():
        yield prefix, obj


def by_id(path_zh: Path, path_en: Path) -> dict[str, dict[str, str]]:
    """同名文件按记录 id 配对 → {id: {字段: 中文}}（EN 侧同字段取值）。"""
    zh = {str(r.get("id")): r for r in records(path_zh) if isinstance(r, dict) and r.get("id") is not None}
    en = {str(r.get("id")): r for r in records(path_en) if isinstance(r, dict) and r.get("id") is not None}
    out: dict[str, dict[str, str]] = {}
    for rid, er in en.items():
        zr = zh.get(rid)
        if zr is None:
            continue
        fields = {fp: zt for fp, zt in walk(zr)}
        for fp, et in walk(er):
            if fp in fields:
                out.setdefault(rid, {})[fp] = et
                out[rid][f"#zh:{fp}"] = fields[fp]
    return out


def build_terms(zh_dir: Path, en_dir: Path) -> tuple[dict, Counter]:
    """术语表：{英文: {zh, kind, file, id, field}}。"""
    terms: dict[str, dict] = {}
    stats = Counter()
    for table, kind in NAME_TABLES.items():
        pairs = by_id(zh_dir / f"{table}.json", en_dir / f"EN_{table}.json")
        if not pairs:
            continue
        got = 0
        for rid, fields in pairs.items():
            for fp, en_text in fields.items():
                if fp.startswith("#zh:"):
                    continue
                leaf = fp.split(".")[-1].split("[")[0]
                if leaf not in NAME_FIELDS:
                    continue
                zh_text = fields.get(f"#zh:{fp}", "")
                en_text = en_text.strip()
                zh_text = zh_text.strip()
                if not en_text or not zh_text or en_text == zh_text:
                    continue
                if len(en_text) > 80 or len(zh_text) > 40:
                    continue  # 长句说明不是「名词」
                key = en_text
                if key in terms and terms[key]["zh"] != zh_text:
                    stats["冲突"] += 1
                    continue
                terms[key] = {"zh": zh_text, "kind": kind, "file": table, "id": rid, "field": fp}
                got += 1
        if got:
            print(f"  {table:<16} {kind:<8} {got} 条")
            stats[kind] += got
    return terms, stats


def build_speakers(zh_dir: Path, en_dir: Path) -> dict[str, dict]:
    """model → 中文说话人（从零协已译剧情里统计），同时留 EN 侧写法。"""
    zh_map: dict[str, Counter] = defaultdict(Counter)
    en_map: dict[str, Counter] = defaultdict(Counter)
    for name in ("S", "E", "P", "D"):
        for p in (zh_dir / "StoryData").glob(f"*{name}*.json"):
            for r in records(p):
                if isinstance(r, dict) and r.get("model"):
                    if r.get("teller"):
                        zh_map[str(r["model"])][str(r["teller"])] += 1
    for p in (en_dir / "StoryData").glob("*.json"):
        for r in records(p):
            if isinstance(r, dict) and r.get("model") and r.get("teller"):
                en_map[str(r["model"])][str(r["teller"])] += 1
    out = {}
    for model, counter in zh_map.items():
        teller, n = counter.most_common(1)[0]
        out[model] = {"teller_zh": teller, "n": n,
                      "teller_en": (en_map.get(model) or Counter()).most_common(1)[0][0]
                      if en_map.get(model) else ""}
    return out


def story_pairs(zh_dir: Path, en_dir: Path, limit_per_file: int = 4000) -> list[dict]:
    """第 1~9 章对齐行对（英文 ↔ 零协中文），给 AI 当风格与术语范例。"""
    pairs: list[dict] = []
    en_story = en_dir / "StoryData"
    for en_path in sorted(en_story.glob("EN_*.json")):
        zh_path = zh_dir / "StoryData" / en_path.name[3:]
        if not zh_path.is_file():
            continue
        zh_recs = {r.get("id"): r for r in records(zh_path) if isinstance(r, dict)}
        n = 0
        for er in records(en_path):
            if not isinstance(er, dict):
                continue
            zr = zh_recs.get(er.get("id"))
            if not zr:
                continue
            en_text = str(er.get("content") or "").strip()
            zh_text = str(zr.get("content") or "").strip()
            if not en_text or not zh_text:
                continue
            pairs.append({
                "file": en_path.name[3:-5],
                "id": er.get("id"),
                "model": er.get("model") or zr.get("model") or "",
                "teller_en": er.get("teller") or "",
                "teller_zh": zr.get("teller") or "",
                "en": en_text,
                "zh": zh_text,
            })
            n += 1
            if n >= limit_per_file:
                break
    return pairs


CAP_RE = re.compile(r"\b(?:[A-Z][A-Za-z'’\-]+)(?:\s+(?:of|the|and|de|von)?\s*[A-Z][A-Za-z'’\-]+){0,3}\b")
QUOTE_RE = re.compile(r"[「『\"“]([^」』\"”]{2,24})[」』\"”]")


def chapter_files(en_dir: Path, chapter: int) -> list[Path]:
    pat = re.compile(rf"^EN_S{chapter}\d{{2,3}}[A-Z]?\d*\.json$")
    return sorted(p for p in (en_dir / "StoryData").glob("*.json") if pat.match(p.name))


def new_term_candidates(en_dir: Path, en_chapter_files: list[Path], terms: dict,
                        pairs: list[dict], limit: int = 400) -> list[dict]:
    """新章节里出现、但术语表没覆盖的专有名词候选 + 旧章节里的英中对照证据。"""
    counter: Counter = Counter()
    for p in en_chapter_files:
        for r in records(p):
            if not isinstance(r, dict):
                continue
            text = str(r.get("content") or "")
            for m in CAP_RE.finditer(text):
                phrase = m.group(0).strip()
                words = phrase.split()
                if words[0] in STOP or len(phrase) < 4:
                    continue
                if phrase.lower() in {w.lower() for w in STOP}:
                    continue
                counter[phrase] += 1
            for m in QUOTE_RE.finditer(text):
                q = m.group(1).strip()
                if 2 <= len(q) <= 18 and not q.endswith((".", "!", "?")):
                    counter[q] += 1
    known = {t.lower() for t in terms}
    out = []
    for phrase, n in counter.most_common():
        if phrase.lower() in known:
            continue
        if any(phrase.lower() in k or k in phrase.lower() for k in known if len(k) >= 6):
            continue
        ev = [p for p in pairs if phrase in p["en"]][:3]
        out.append({"term": phrase, "count": n,
                    "evidence": [{"en": e["en"][:160], "zh": e["zh"][:80], "file": e["file"]}
                                 for e in ev]})
        if len(out) >= limit:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zh", default=DEFAULT_ZH)
    ap.add_argument("--en", default=DEFAULT_EN)
    ap.add_argument("--chapter", type=int, default=10)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "translate")
    args = ap.parse_args()

    zh_dir, en_dir, out = Path(args.zh), Path(args.en), args.out
    if not (zh_dir / "BattleKeywords.json").is_file() or not en_dir.is_dir():
        print("零协包或英文基线不可用，检查路径")
        return 1
    out.mkdir(parents=True, exist_ok=True)

    print("1) 术语表（英文基线 ↔ 零协，按 id 配对）")
    terms, stats = build_terms(zh_dir, en_dir)
    print(f"   合计 {len(terms)} 条术语（冲突 {stats['冲突']} 处已跳过）")

    print("2) 说话人对照（model → 中文名，来自零协已译剧情）")
    speakers = build_speakers(zh_dir, en_dir)
    print(f"   共 {len(speakers)} 个立绘 id 有中文叫法")

    print("3) 已译剧情英中行对（风格 / 术语范例）")
    pairs = story_pairs(zh_dir, en_dir)
    print(f"   共 {len(pairs)} 对（第 1~9 章）")

    files = chapter_files(en_dir, args.chapter)
    print(f"4) 第 {args.chapter} 章英文文件 {len(files)} 个，抽新词候选")
    cands = new_term_candidates(en_dir, files, terms, pairs)
    print(f"   候选 {len(cands)} 个（含旧章节证据的 {sum(1 for c in cands if c['evidence'])} 个）")

    (out / "glossary.json").write_text(json.dumps({
        "format_version": 1,
        "chapter": args.chapter,
        "terms": terms,
        "speakers": speakers,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = ["# 术语表（英文 → 零协中文）", "",
             f"来源：英文基线 `Localize/en/EN_*.json` 与零协包按 id 机械配对；共 {len(terms)} 条。", "",
             "| 英文 | 零协中文 | 类别 | 来源表 |", "| --- | --- | --- | --- |"]
    for en_text, info in sorted(terms.items(), key=lambda kv: (kv[1]["kind"], kv[0])):
        lines.append(f"| {en_text} | {info['zh']} | {info['kind']} | {info['file']}#{info['id']} |")
    (out / "术语表.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    spk = ["# 说话人对照（立绘 id → 零协中文叫法）", "",
           "新章节里同一个 `model` 直接用这张表的中文名，别自己另起叫法。", "",
           "| model | 中文 | 英文基线写法 | 出现次数 |", "| --- | --- | --- | --- |"]
    for model, info in sorted(speakers.items(), key=lambda kv: -kv[1]["n"]):
        spk.append(f"| {model} | {info['teller_zh']} | {info['teller_en']} | {info['n']} |")
    (out / "说话人对照.md").write_text("\n".join(spk) + "\n", encoding="utf-8")

    (out / "新词候选.json").write_text(json.dumps({
        "format_version": 1, "chapter": args.chapter, "candidates": cands,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "范例行对.jsonl").write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pairs[:3000]), encoding="utf-8")

    print(f"\n产物 → {out}")
    for name in ("glossary.json", "术语表.md", "说话人对照.md", "新词候选.json", "范例行对.jsonl"):
        p = out / name
        print(f"  {name:<16} {p.stat().st_size / 1024:.0f} KB")
    print("\n新词候选前 15（带旧章节证据）：")
    for c in [c for c in cands if c["evidence"]][:15]:
        ev = c["evidence"][0]
        print(f"  {c['term']}（{c['count']} 次）：{ev['en'][:60]} → {ev['zh'][:30]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
