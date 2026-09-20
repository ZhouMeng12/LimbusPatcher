"""把「大量文本修改」打包成任务分片交给别的 AI（豆包/ChatGPT/本地小模型），再收回答案。

为什么要它：让模型在会话里逐条读改几千行文本极其费 token。这里把活拆成
「粘贴 → 回 JSON」，交给外部 AI（或 `mt_engines` 里的本地小模型）批量做，本仓库只负责
导出/收回/校验，不消耗会话 token。

用法：
    # 1) 导出：默认按「文件 × 每片 60 条」切分，写进 data/text_tasks/paste/
    python scripts/text_tasks.py export --rel RPGSystem/rpg-loc-quest-floor-3.json
    python scripts/text_tasks.py export --all --per 60          # 全部第十章文件
    python scripts/text_tasks.py export --all --only-bad        # 只导出体检有问题的
    python scripts/text_tasks.py status                          # 看进度

    # 2) 把 paste/*.txt 整篇粘给外部 AI，要求它只回 JSON，存成 data/text_tasks/ans/<同名>.json
    #    结构：{"<文件>|<字段路径>": "新中文", ...}（字段路径写法见分片头部示例）

    # 3) 收回：默认 dry-run，先看会改哪些
    python scripts/text_tasks.py import --dry-run
    python scripts/text_tasks.py import

设计约束（照仓库既有规矩）：
- 说明类字段里的方括号 `[CombatStart]`/`[Bleed]` 是游戏内部效果 id，外部 AI 一律不许改；
- 术语表 `data/translate/glossary.json` + `审定新词.json` 会随提示词一起发出去；
- 收回时做校验：JSON 合法、行数不变、方括号序列与英文基线一致、无韩文、无 `@@n@@` 残留。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import mt_files as mf  # noqa: E402
import mt_translate as mt  # noqa: E402
import repair_ch10 as rc  # noqa: E402
import translate_pack as tp  # noqa: E402

WORK = ROOT / "data" / "text_tasks"
PASTE, ANS = WORK / "paste", WORK / "ans"
HANGUL = re.compile(r"[\uac00-\ud7af]")
#: 说明类字段：方括号是效果 id，外部 AI 不许动
NO_TOUCH = rc.ID_FIELDS


def _path_str(path: tuple) -> str:
    return "/".join(str(p) for p in path)


def candidate_fields(rel: str) -> list[tuple[tuple, str, str]]:
    """[(字段路径, 英文, 现译)]，只挑「有英文、有译文」的文本字段。"""
    zh_path, en_path = rc._resolve(rel)
    if zh_path is None or en_path is None or not Path(en_path).is_file():
        return []
    zh = rc.en_strings(json.loads(Path(zh_path).read_text(encoding="utf-8-sig")), {})
    en = rc.en_strings(json.loads(Path(en_path).read_text(encoding="utf-8-sig")), {})
    out = []
    for path, text in zh.items():
        src = en.get(path)
        if isinstance(src, str) and src.strip() and text.strip():
            out.append((path, src, text))
    return out


def only_bad(rows: list[tuple[tuple, str, str]]) -> list[tuple[tuple, str, str]]:
    """只留体检可疑的：含韩文、含 @@ 残留、整段英文没翻、说明字段方括号被翻。"""
    bad = []
    for path, src, text in rows:
        field = path[-1] if path else ""
        bracketed = ([b for b in rc.BRACKET.findall(src)] !=
                     [b for b in rc.BRACKET.findall(text)])
        if (HANGUL.search(text) or "@@" in text or
                (field in NO_TOUCH and bracketed) or
                (not re.search(r"[\u4e00-\u9fff]", re.sub(r"<[^>]*>|\[[^\]]*\]", "", text))
                 and len(text) > 8)):
            bad.append((path, src, text))
    return bad


def glossary_block(limit: int = 400) -> str:
    terms = mt.term_map()
    items = list(terms.items())[:limit]
    return "、".join(f"{en}={zh}" for en, zh in items)


def export_one(rel: str, rows: list[tuple[tuple, str, str]], per: int) -> list[Path]:
    made = []
    for start in range(0, len(rows), per):
        chunk = rows[start:start + per]
        idx = start // per + 1
        name = f"{Path(rel).stem}__{idx:02d}.txt".replace("/", "_")
        lines = [
            f"# 任务：润色/补译《边狱巴士》第十章汉化文本（{rel} 第 {idx} 片，共 {len(chunk)} 条）",
            "",
            "## 硬性规则（违反即作废）",
            "1. 只改中文译文，**不改**结构、不改键名、不增删条目。",
            "2. 方括号 `[...]` 在**说明类字段**（desc/summary/statText/effect/lowMoraleDescription/panicDescription）里是"
            "游戏内部效果 id，必须与给出的英文一字不差（如 `[CombatStart]`、`[Bleed]`、`[Laceration]`）；"
            "在 name/title/displayName 里才按中文译（如 `BongBong [Orange]` → `噗扭扭[橙子味]`，方括号前不留空格）。",
            "3. 标签 `<color=#xxxxxx>`、`<i>`、`{0}` `{1}` 占位符原样保留，数量和顺序不能变；换行 `\\n` 数量不变。",
            "4. 专有名词照下面的术语表；术语表没有的人名/品牌保留原文（Le Noir、Le Rouge、L'Inamovible…）。",
            "5. 零协风格：简体中文、中文标点（，。！？：；「」用“”）、省略号用「……」、不夹韩文。",
            "6. 零协既有用词：Uptie=同步、Threadspinning=异想解析、Identity=人格、Clash=拼点、SP=理智值、"
            "HP=体力、Sin=罪孽（暴怒/色欲/怠惰/暴食/忧郁/傲慢/嫉妒）、Stagger=混乱、Max Stack=最大值。",
            "",
            "## 术语表（节选）",
            glossary_block(),
            "",
            "## 只回 JSON，格式：{\"<文件>|<字段路径>\": \"新中文\", ...}",
            f"文件写 `{rel}`，字段路径就是下面每条的「路径」。**不要**输出英文原文，不要解释。",
            "",
            "---- 待处理 ----",
            "",
        ]
        for path, src, text in chunk:
            tag = "【不可动方括号】" if (path[-1] if path else "") in NO_TOUCH else ""
            lines.append(f"### 路径：{_path_str(path)} {tag}")
            lines.append(f"EN: {src}")
            lines.append(f"ZH: {text}")
            lines.append("")
        PASTE.mkdir(parents=True, exist_ok=True)
        target = PASTE / name
        target.write_text("\n".join(lines), encoding="utf-8")
        made.append(target)
    return made


def apply_answers(dry: bool) -> dict:
    """收回答案：data/text_tasks/ans/*.json → 覆盖译文。"""
    stat = {"files": 0, "changed": 0, "rejected": 0}
    if not ANS.is_dir():
        print(f"没有答案目录：{ANS}")
        return stat
    by_file: dict[str, dict[str, str]] = {}
    for p in sorted(ANS.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            print(f"  {p.name}: 不是 JSON 对象，跳过")
            continue
        for key, value in data.items():
            if not isinstance(value, str) or "|" not in key:
                stat["rejected"] += 1
                continue
            rel, path = key.split("|", 1)
            by_file.setdefault(rel.strip(), {})[path.strip()] = value
    for rel, mapping in by_file.items():
        zh_path, en_path = rc._resolve(rel)
        if zh_path is None or en_path is None:
            print(f"  跳过未知文件：{rel}")
            continue
        zh_data = json.loads(Path(zh_path).read_text(encoding="utf-8-sig"))
        en_map = rc.en_strings(json.loads(Path(en_path).read_text(encoding="utf-8-sig")), {})
        zh_map = {_path_str(p): (holder, key) for holder, key, p in _holders(zh_data)}
        changed = 0
        for path_str, new_text in mapping.items():
            spot = zh_map.get(path_str)
            if spot is None:
                stat["rejected"] += 1
                continue
            holder, key = spot
            field = key if isinstance(key, str) else ""
            src = en_map.get(tuple(_split_path(path_str)))
            if isinstance(src, str) and field in NO_TOUCH:
                want = [b for b in rc.BRACKET.findall(src) if not HANGUL.search(b)]
                have = [b for b in rc.BRACKET.findall(new_text) if not HANGUL.search(b)]
                if want != have:                      # 方括号被改坏 → 拒绝
                    stat["rejected"] += 1
                    continue
            if HANGUL.search(new_text) or "@@" in new_text:
                stat["rejected"] += 1
                continue
            if holder.get(key) != new_text:
                holder[key] = new_text
                changed += 1
        if changed and not dry:
            Path(zh_path).write_text(json.dumps(zh_data, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
        if changed:
            stat["files"] += 1
            stat["changed"] += changed
            print(f"  {rel}: {changed} 处" + ("（dry-run）" if dry else ""))
    print(f"合计：{stat['files']} 文件 / {stat['changed']} 处改动 · 拒绝 {stat['rejected']}")
    return stat


def _holders(node, path: tuple = ()):
    """产出 (容器, 键, 路径) —— 可写回的定位。"""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str):
                yield node, k, path + (k,)
            else:
                yield from _holders(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                yield node, i, path + (i,)
            else:
                yield from _holders(v, path + (i,))


def _split_path(path_str: str) -> list:
    out: list = []
    for part in path_str.split("/"):
        out.append(int(part) if part.isdigit() else part)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--rel", nargs="*", default=None)
    e.add_argument("--all", action="store_true")
    e.add_argument("--per", type=int, default=60)
    e.add_argument("--only-bad", action="store_true")
    i = sub.add_parser("import")
    i.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    args = ap.parse_args()

    if args.cmd == "status":
        pasted = sorted(PASTE.glob("*.txt")) if PASTE.is_dir() else []
        answered = {p.stem for p in ANS.glob("*.json")} if ANS.is_dir() else set()
        done = [p for p in pasted if p.stem in answered]
        print(f"分片 {len(pasted)} 个，已回 {len(done)} 个，未回 {len(pasted) - len(done)} 个")
        for p in pasted:
            if p.stem not in answered:
                print(f"  待回：{p.name}")
        return 0
    if args.cmd == "import":
        return 0 if apply_answers(args.dry_run)["changed"] or True else 1

    rels = args.rel or (mf.CH10_FILES + mf.RPG_FILES + [f"{n}.json" for n in tp.STORY_FILES])
    total = 0
    for rel in rels:
        rows = candidate_fields(rel)
        if args.only_bad:
            rows = only_bad(rows)
        if not rows:
            continue
        made = export_one(rel, rows, args.per)
        total += len(rows)
        print(f"  {rel}: {len(rows)} 条 → {len(made)} 片")
    print(f"合计导出 {total} 条，分片在 {PASTE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
