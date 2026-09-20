"""导出「来历不明剧情文件」的确认任务包（给 AI 判定类型/章节/顺序用）。

背景：零协包里有 201 个剧情文件按文件名无法确定归属——
  · ND####（1D/2D/3D/4D/5D/7D/8D 共 147 个）：疑似「第 N 章迷宫/地牢剧情」
  · ES*（35 个）：疑似活动/间章剧情
  · PC*（19 个）：待定
它们现在被笼统归到「主线剧情」分类里。本脚本把文件名、场景标题、地点、首尾与抽样台词，
连同游戏自带的章节表（StageChapterText）、放映厅条目（StoryTheater*）、已知主线规律一起打包，
交给人工/AI 判定「类型 + 章节 + 顺序」；答案由 scripts/import_misc_kinds.py 汇总成
limbus_patcher/data/misc_story_kinds.json，供分类与导航使用。

用法：
    python scripts/export_misc_tasks.py [--llc <零协包>] [--out data/misc_story/tasks]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_LLC = r"D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data/Lang/LLC_zh-CN"

KINDS = ["迷宫剧情", "集中战斗", "间章活动", "人格剧情", "主线", "其他"]
CONFIDENCE = ["high", "medium", "low"]

INSTRUCTIONS = [
    "你是《边狱巴士》(Limbus Company) 剧情资料整理助手。下面每个条目是本地汉化包里的一个剧情文本文件，",
    "请判断它属于哪种剧情、对应哪一章、以及在同组内的先后顺序。",
    "依据：文件名规律、场景标题(title)、地点(place)、说话人(teller)、以及给出的首尾与抽样台词；",
    "同时可参考随附的章节表（StageChapterText）与放映厅条目（StoryTheater*）。",
    "要求：不确定就写 low 并在 reason 里说明，不要编造。",
    "输出必须是严格 JSON（不要额外的解释文字），结构如下：",
    "{",
    '  "files": [',
    '    {"file": "1D101A", "kind": "迷宫剧情", "chapter": "第1章", "chapter_number": "01",',
    '     "order": 1, "reason": "场景为L公司支部，与第1章一致"}',
    "  ],",
    '  "uncertain": [{"file": "PC09A", "question": "属于哪一章？", "guess": "第9章"}]',
    "}",
    "字段说明：kind 取值 " + " / ".join(KINDS) + "；chapter 用中文（如 第3章 / 间章 5.5 / 活动）；",
    "chapter_number 用游戏编号（00/01/02/03/3.5/4.5/…）；order 是同组内建议顺序（从 1 开始）；",
    "给出的每个 file 都必须出现在 files 里；不要输出 confidence 之类的额外字段。",
]


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def group_of(stem: str) -> str | None:
    """返回分组名（1D/2D/…/ES/PC）；不属于待确认集合返回 None。"""
    if re.match(r"^PC\d", stem):
        return "PC"
    if re.match(r"^ES\d", stem):
        return "ES"
    m = re.match(r"^(\d+)D", stem)
    return f"{m.group(1)}D" if m else None


# 兜底：游戏里以韩文 model 出场但剧情文本中很少带中文 teller 的角色
EXTRA_NAMES = {
    "단테": "但丁",
    "베르길리우스": "维吉里乌斯",
    "카론": "卡戎",
}


def learn_model_names(llc: Path, limit_files: int = 800) -> dict[str, str]:
    """「韩文 model → 中文名」映射：先取 IntroduceCharacter.json（12 罪人权威表），
    再从剧情文件里统计 model/teller 成对出现的情况补 NPC，最后叠兜底表。"""
    names: dict[str, str] = dict(EXTRA_NAMES)
    intro = load(llc / "IntroduceCharacter.json")
    if isinstance(intro, dict):
        for r in intro.get("dataList", []):
            if isinstance(r, dict) and isinstance(r.get("id"), str) and isinstance(r.get("name"), str):
                names[r["id"].strip()] = r["name"].strip()
    pairs: dict[str, dict[str, int]] = {}
    root = llc / "StoryData"
    for i, f in enumerate(sorted(root.glob("*.json"))):
        if i >= limit_files:
            break
        data = load(f)
        if not isinstance(data, dict):
            continue
        for r in data.get("dataList", []):
            if not isinstance(r, dict):
                continue
            model, teller = r.get("model"), r.get("teller")
            if isinstance(model, str) and isinstance(teller, str) and model.strip() and teller.strip():
                pairs.setdefault(model.strip(), {})
                pairs[model.strip()][teller.strip()] = pairs[model.strip()].get(teller.strip(), 0) + 1
    for m, c in pairs.items():
        if m not in names and c:
            names[m] = max(c.items(), key=lambda kv: kv[1])[0]
    return names


def _speaker_of(record: dict, names: dict[str, str] | None) -> str:
    """说话人：优先中文 teller，其次把韩文 model 翻成中文（学到的映射），最后原样。"""
    teller = record.get("teller")
    if isinstance(teller, str) and teller.strip():
        return teller.strip()
    model = record.get("model")
    if isinstance(model, str) and model.strip():
        model = model.strip()
        return (names or {}).get(model, model)
    return ""


def sample_lines(dl: list, head: int = 6, tail: int = 4, mid: int = 10, width: int = 70,
                 names: dict[str, str] | None = None):
    """首/尾/均匀抽样三段台词（保留说话人与场景标题）。"""
    def pack(rows):
        out = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            text = str(r.get("content") or "").replace("\n", " ")
            out.append({
                "id": r.get("id"),
                "teller": _speaker_of(r, names),
                "title": str(r.get("title") or "")[:30],
                "text": text[:width],
            })
        return out

    head_rows = pack(dl[:head])
    tail_rows = pack(dl[-tail:]) if len(dl) > head else []
    if len(dl) > head + tail:
        step = max(1, (len(dl) - head - tail) // mid)
        mid_rows = pack(dl[head:len(dl) - tail:step][:mid])
    else:
        mid_rows = []
    return head_rows, mid_rows, tail_rows


def game_context(llc: Path) -> dict:
    """游戏自带的章节表与放映厅条目（帮助判定章节与顺序）。"""
    ctx: dict = {}
    d = load(llc / "StageChapterText.json")
    if isinstance(d, dict):
        ctx["章节表(StageChapterText)"] = [
            {k: r.get(k) for k in ("chapter", "chapterNumber", "chaptertitle", "company", "area", "timeline")}
            for r in d.get("dataList", []) if isinstance(r, dict)
        ]
    theater = []
    for name in ("StoryTheaterMain.json", "StoryTheaterOther.json"):
        t = load(llc / name)
        if isinstance(t, dict):
            for r in t.get("dataList", []):
                if isinstance(r, dict) and str(r.get("id", "")).startswith(("CHAPTER_", "STORY_")):
                    theater.append({"id": r.get("id"), "title": r.get("title"), "from": name})
    if theater:
        ctx["放映厅条目(StoryTheater*)"] = theater
    ctx["已知主线规律"] = ("StoryData/S<章>##<A|B>.json 为主线（如 S525B.json = 5-25 战前）；"
                        "Personalities.json 的 id 即人格剧情文件名 StoryData/P<人格id>.json")
    return ctx


# ---------------- 纯文本分片版（直接粘给 AI） ----------------

def paste_text(group: str, files: list[dict], context: dict, part: int = 1, parts: int = 1) -> str:
    """把任务包压成适合直接粘贴的纯文本。"""
    out: list[str] = []
    out.append("【任务】判断下列《边狱巴士》剧情文本文件的类型、章节与顺序，只输出 JSON，不要解释。")
    out.append("【输出格式】")
    out.append('{"files":[{"file":"1D101A","kind":"迷宫剧情","chapter":"第1章","chapter_number":"01",'
               '"order":1,"reason":"20字内"}],"uncertain":[{"file":"...","question":"..."}]}')
    out.append("kind 取值：" + " / ".join(KINDS) + "；不要输出 confidence 之类的额外字段。")
    chapters = context.get("章节表(StageChapterText)") or []
    if chapters:
        brief = "；".join(f"{c.get('chapterNumber')}={c.get('chaptertitle')}" for c in chapters[:20])
        out.append("【章节表】" + brief)
    theater = context.get("放映厅条目(StoryTheater*)") or []
    if theater:
        brief = "；".join(f"{t.get('id')}={t.get('title')}" for t in theater[:14])
        out.append("【放映厅条目】" + brief)
    out.append("【已知规律】" + str(context.get("已知主线规律", "")))
    if parts > 1:
        out.append(f"【本组】{group}（第 {part}/{parts} 片，共 {len(files)} 个文件）")
    else:
        out.append(f"【本组】{group}（共 {len(files)} 个文件）")
    out.append("")
    for f in files:
        out.append(f"── {f['file']}（{f['records']} 条）")
        if f["titles"]:
            out.append("   场景：" + "、".join(f["titles"][:8]))
        if f["places"]:
            out.append("   地点：" + "、".join(f["places"][:5]))
        for row in f["head"][:5]:
            who = f"[{row['teller']}]" if row["teller"] else ""
            out.append(f"   {who}{row['text'][:60]}")
        if f["tail"]:
            out.append("   …")
            for row in f["tail"][:2]:
                who = f"[{row['teller']}]" if row["teller"] else ""
                out.append(f"   {who}{row['text'][:60]}")
        out.append("")
    out.append("请输出 JSON（包含上面每个 file 的判断）。")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llc", type=Path, default=Path(DEFAULT_LLC))
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "misc_story" / "tasks")
    args = ap.parse_args()
    llc: Path = args.llc
    if not llc.is_dir():
        print(f"零协包不存在：{llc}")
        return 2

    groups: dict[str, list[str]] = defaultdict(list)
    for p in sorted((llc / "StoryData").glob("*.json")):
        g = group_of(p.stem)
        if g:
            groups[g].append(p.stem)
    if not groups:
        print("没有找到待确认文件")
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    context = game_context(llc)
    names = learn_model_names(llc)  # 韩文 model → 中文说话人
    print(f"学到说话人映射 {len(names)} 条")
    order = sorted(groups, key=lambda g: (g[0].isdigit() is False, g))
    index_rows = []
    for i, g in enumerate(order, start=1):
        files = []
        for stem in sorted(groups[g]):
            data = load(llc / "StoryData" / f"{stem}.json")
            dl = data.get("dataList", []) if isinstance(data, dict) else []
            titles, places = [], []
            for r in dl:
                if not isinstance(r, dict):
                    continue
                t = str(r.get("title") or "").strip()
                if t and t not in titles:
                    titles.append(t[:30])
                pl = str(r.get("place") or "").strip()
                if pl and pl not in places:
                    places.append(pl[:30])
            head, mid, tail = sample_lines(dl, names=names)
            files.append({
                "file": stem,
                "records": len(dl),
                "titles": titles[:12],
                "places": places[:8],
                "head": head,
                "sample": mid,
                "tail": tail,
            })
        payload = {
            "format_version": 1,
            "group": g,
            "instructions": INSTRUCTIONS,
            "context": context,
            "files": files,
        }
        name = f"{i:02d}_{g}.json"
        (args.out / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        index_rows.append((name, g, len(files), sum(f["records"] for f in files)))

    lines = [
        "# 待确认剧情文件 · 任务包说明",
        "",
        f"来源零协包：{llc}",
        f"待确认文件：**{sum(len(v) for v in groups.values())}** 个，分 {len(order)} 组。",
        "",
        "## 怎么用",
        "",
        "1. 把 tasks/ 下的任务包**逐个**发给 AI（豆包等），一次一个文件，避免串味；",
        "2. 要求它严格按包内 instructions 的 JSON 结构作答（不要额外解释）；",
        "3. 把答案保存成 data/misc_story/ans/<同名>.json（例如 01_1D.json 的答案存 01_1D.json）；",
        "4. 跑 python scripts/import_misc_kinds.py 汇总校验，生成 limbus_patcher/data/misc_story_kinds.json；",
        "5. 该映射会被分类/导航读取（缺省时这些文件暂归「其他剧情」）。",
        "",
        "## 任务包清单",
        "",
        "| 文件 | 分组 | 文件数 | 记录数 |",
        "| --- | --- | --- | --- |",
    ]
    for name, g, n, recs in index_rows:
        lines.append(f"| {name} | {g} | {n} | {recs} |")
    (args.out / "使用说明.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 纯文本分片（每片 ≤ 10 个文件，方便直接粘贴给 AI）
    paste_dir = args.out.parent / "paste"
    paste_dir.mkdir(parents=True, exist_ok=True)
    paste_rows = []
    for name, g, _n, _recs in index_rows:
        payload = json.loads((args.out / name).read_text(encoding="utf-8"))
        files = payload["files"]
        chunk = 10
        parts = max(1, (len(files) + chunk - 1) // chunk)
        for k in range(parts):
            part_files = files[k * chunk:(k + 1) * chunk]
            pname = f"{name[:-5]}" + (f"_part{k + 1}.txt" if parts > 1 else ".txt")
            (paste_dir / pname).write_text(
                paste_text(g, part_files, payload["context"], k + 1, parts), encoding="utf-8")
            paste_rows.append((pname, len(part_files)))
    print(f"已生成 {len(order)} 个任务包 → {args.out}")
    print(f"已生成 {len(paste_rows)} 个粘贴版文本 → {paste_dir}")
    for name, g, n, recs in index_rows:
        print(f"  {name}: {n} 个文件 / {recs} 条记录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
