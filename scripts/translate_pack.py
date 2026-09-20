"""第十章翻译工作台：导出待译行 / 合并译文 / 生成中英对照与中文剧本。

用法：
    python scripts/translate_pack.py dump   S1000B            # 打印待译行（给人/AI 看）
    python scripts/translate_pack.py merge  S1000B            # 读 data/translate/zh/S1000B.json 合并
    python scripts/translate_pack.py status                   # 进度 + 术语校验
    python scripts/translate_pack.py check                    # 只跑术语/格式校验

译文文件 data/translate/zh/<文件>.json 结构：
{
  "lines": {"<记录 id>": "中文台词"},
  "meta":  {"<记录 id>": {"teller": "中文", "title": "中文", "place": "中文"}}   # 需要时才有
}
只翻 `content`；`model` / `id` 原样保留。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GAME = Path("D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data")
EN_STORY = GAME / "Assets/Resources_moved/Localize/en/StoryData"
ZH_STORY = GAME / "Lang/LLC_zh-CN/StoryData"
WORK = ROOT / "data" / "translate"
ZH_DIR = WORK / "zh"
OUT = WORK / "out"
GLOSSARY = WORK / "glossary.json"

#: 第十章剧情文件名（S + 两位章号 10 + 两位节号；注意别把第 1 章的 S101B 也算进来）
CH10_RE = re.compile(r"^EN_S10\d\d[A-Z]?\d*\.json$")


def _story_files() -> list[str]:
    """第十章剧情文件（按名字排序，就是剧情顺序）。"""
    return [p.name[3:-5] for p in sorted(EN_STORY.glob("EN_*.json")) if CH10_RE.match(p.name)]


#: 零协也缺、但属于第十章的其它剧情文件（第十章 EX 段与新增人格剧情）
EXTRA_STORY = ["S9991B", "P10416", "P10816"]
STORY_FILES = _story_files() + [n for n in EXTRA_STORY
                                if (EN_STORY / f"EN_{n}.json").is_file()
                                and n not in _story_files()]
#: 审定新词（我/人工定的专有名词译法），并入术语校验
DECIDED = WORK / "审定新词.json"
_TAG_RE = re.compile(r"<[^>]+>|\[[^\]]+\]|\{[^}]*\}")
#: 这些类别是游戏机制词（关键词/状态/buff），只在 [Tag] 形态下强制
KEYWORD_KINDS = {"关键词/状态", "buff", "技能标签", "技能", "被动", "能力"}


def line_key(record: dict, index: int) -> str:
    """译文键：有 id 用 id，没有 id 用 #序号（同一个文件里多条无 id 记录不能挤在一个键上）。"""
    rid = record.get("id")
    return str(rid) if rid is not None else f"#{index}"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def en_file(name: str) -> Path:
    return EN_STORY / f"EN_{name}.json"


def records(name: str) -> list:
    return load(en_file(name)).get("dataList") or []


def glossary() -> dict:
    """术语表 + 审定新词（后者优先，覆盖前者）。"""
    terms = {}
    if GLOSSARY.is_file():
        terms.update(load(GLOSSARY).get("terms") or {})
    if DECIDED.is_file():
        for en, zh in (load(DECIDED).get("terms") or {}).items():
            terms[en] = {"zh": zh, "kind": "审定新词", "file": DECIDED.name, "id": "-", "field": "-"}
    return terms


def speakers() -> dict:
    if not GLOSSARY.is_file():
        return {}
    return load(GLOSSARY).get("speakers") or {}


# ---------- dump ----------


def cmd_dump(args) -> int:
    name = args.name
    if not en_file(name).is_file():
        print(f"没有 {en_file(name)}")
        return 1
    terms, spk = glossary(), speakers()
    print(f"### {name}（{len(records(name))} 条记录）")
    hits = []
    for r in records(name):
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        model = r.get("model") or ""
        teller_en = r.get("teller") or ""
        title_en = r.get("title") or ""
        content = str(r.get("content") or "")
        extra = ""
        if teller_en or title_en:
            s = spk.get(model, {})
            extra = f"  [说话人 {teller_en!r} → 零协叫法 {s.get('teller_zh', '?')!r}]"
            if title_en and title_en != teller_en:
                extra += f" [title {title_en!r}]"
        print(f"{rid}\t{model}\t{content}{extra}")
        for term in terms:
            if term in content and len(term) > 3:
                hits.append(term)
    if hits:
        uniq = sorted(set(hits))
        print(f"\n# 本文件命中的术语（{len(uniq)} 条，必须按此译）：")
        for t in uniq:
            print(f"#   {t} → {terms[t]['zh']}")
    return 0


# ---------- merge ----------


def cmd_merge(args) -> int:
    name = args.name
    src = ZH_DIR / f"{name}.json"
    if not src.is_file():
        print(f"没有译文文件 {src}")
        return 1
    payload = load(src)
    lines = payload.get("lines") or {}
    meta = payload.get("meta") or {}
    en = records(name)
    out_records = []
    missing = []
    for idx, r in enumerate(en):
        if not isinstance(r, dict):
            continue
        rid = line_key(r, idx)
        rec = dict(r)
        if rid in lines:
            rec["content"] = lines[rid]
        elif r.get("content"):
            missing.append(rid)
        m = meta.get(rid) or {}
        for field in ("teller", "title", "place"):
            if field in m:
                rec[field] = m[field]
            elif field in rec and rec.get(field):
                rec[field] = zh_meta_of(rec, field)
        out_records.append(rec)
    ZH_DIR.mkdir(parents=True, exist_ok=True)
    (OUT / "zh").mkdir(parents=True, exist_ok=True)
    (OUT / "zh" / f"{name}.json").write_text(
        json.dumps({"dataList": out_records}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{name}: 合并 {len(lines)} 行" + (f"，缺 {len(missing)} 行 {missing[:5]}" if missing else " ✅"))
    build_reports()
    return 0


def zh_meta_of(rec: dict, field: str) -> str:
    """说话人/标题按零协既有叫法替换（表里没有就原样留着，等人工补进 meta）。"""
    spk = speakers()
    value = str(rec.get(field) or "")
    if value in ("???", "?"):
        return "？？？"
    model = rec.get("model") or ""
    s = spk.get(model)
    if s and field == "teller" and s.get("teller_zh"):
        return s["teller_zh"]
    return value



#: 立绘 model（韩文/英文）→ 中文说话人：报告里显示「谁在说话」用
MODEL_ZH: dict[str, str] = {
    "이상": "李箱", "파우스트": "浮士德", "돈키호테": "堂吉诃德", "료슈": "良秀", "뫼르소": "默尔索",
    "홍루": "鸿璐", "히스클리프": "希斯克利夫", "이스마엘": "以实玛利", "로쟈": "罗佳",
    "싱클레어": "辛克莱", "오티스": "奥提斯", "그레고르": "格里高尔", "단테": "但丁",
    "베르길리우스": "维吉里乌斯", "베르길리우스2": "维吉里乌斯", "잔느": "让娜",
    "크로머언니": "克罗默的姐姐", "맨얼굴크로머언니": "克罗默的姐姐", "넬리": "耐莉", "넬리2": "耐莉",
    "에즈라": "埃兹拉", "에즈라먼지": "埃兹拉", "아세아": "亚细亚", "판사": "审判长", "검사": "检察官",
    "3층가위": "安妮特", "N사해결사": "N公司解决师", "뫼르소엄마": "妈妈", "카론": "卡戎",
    "B2층염색실주인": "B2层染坊主", "B2층플로어매니저": "B2层楼层管理员", "가환": "枷环",
}


def speaker_zh(model: str, teller: str = "") -> str:
    """报告用说话人：优先用译文里的 teller，其次查说话人对照表 / 内置表，最后退回 model。"""
    if teller and teller not in ("???", "？", "？？？"):
        return teller
    if teller in ("？？？",):
        return "？？？"
    tag = (model or "").strip()
    if not tag:
        return ""
    table = speakers()
    if tag in table and table[tag].get("teller_zh"):
        return table[tag]["teller_zh"]
    for key in sorted(MODEL_ZH, key=len, reverse=True):     # 变体名（료슈2、에즈라먼지…）按前缀命中
        if tag.startswith(key):
            return MODEL_ZH[key]
    return tag


def build_reports() -> None:
    """按剧情顺序汇总：中英对照 md + 纯中文剧本 md。"""
    zh_dir = OUT / "zh"
    done = [n for n in STORY_FILES if (zh_dir / f"{n}.json").is_file()]
    bilingual = ["# 第十章 · 中英对照", "",
                 f"已完成 {len(done)}/{len(STORY_FILES)} 个文件。中文译名以零协既有译法为准。", ""]
    chinese = ["# 第十章 · 中文剧本", ""]
    for name in done:
        rows = load(zh_dir / f"{name}.json").get("dataList") or []
        en_rows = records(name)
        bilingual += [f"## {name}", ""]
        chinese += [f"## {name}", ""]
        for i, r in enumerate(rows):
            if not isinstance(r, dict):
                continue
            content = str(r.get("content") or "").strip()
            if not content:
                continue
            model = str(r.get("model") or "")
            who = speaker_zh(model, str(r.get("teller") or "")) or str(r.get("title") or "")
            if not who:
                who = "旁白"
            if who == "？？？" and model:
                who = "？？？"
            en_content = ""
            if i < len(en_rows) and isinstance(en_rows[i], dict):
                en_content = str(en_rows[i].get("content") or "").strip()
            chinese.append(f"**{who}**：{content}" if who != "旁白" else content)
            chinese.append("")
            if en_content:
                bilingual.append(f"**{who}**：{content}")
                bilingual.append(f"> {en_content}")
                bilingual.append("")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "第十章-中文剧本.md").write_text("\n".join(chinese) + "\n", encoding="utf-8")
    (OUT / "第十章-中英对照.md").write_text("\n".join(bilingual) + "\n", encoding="utf-8")


# ---------- check ----------


def check_terms() -> tuple[int, list[str]]:
    """术语一致性：英文行里出现的术语，中文行必须用表里的译法。"""
    terms = glossary()
    zh_dir = OUT / "zh"
    problems: list[str] = []
    checked = 0
    for name in STORY_FILES:
        p = zh_dir / f"{name}.json"
        if not p.is_file():
            continue
        rows = load(p).get("dataList") or []
        en_rows = records(name)
        for r, er in zip(rows, en_rows):
            if not isinstance(r, dict) or not isinstance(er, dict):
                continue
            en_text = str(er.get("content") or "")
            zh_text = str(r.get("content") or "")
            if not en_text or not zh_text:
                continue
            checked += 1
            for term, info in terms.items():
                if len(term) < 4:
                    continue
                if term.isascii():
                    if not re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", en_text):
                        continue
                elif term not in en_text:
                    continue
                kind = info.get("kind") or ""
                # 关键词/状态/buff 这类通用词只在游戏标签形态（[Term]）下才强制；
                # 普通叙述里的 "silence" 不等于状态「沉默」。
                # 机制名（技能/被动/状态/关键词）只在游戏标签形态 [Term] 下强制：
                # 叙述句里的 "Silence prevailed" 跟技能名「闭嘴」没有关系。
                is_mechanic = kind in KEYWORD_KINDS or                     (info.get("file") or "").startswith(("BattleKeywords", "Bufs", "SkillTag", "Skills",
                                                         "Passives", "Abilities"))
                if is_mechanic and f"[{term}]" not in en_text:
                    continue
                # 更长且已满足的术语优先（Meat Soda 命中了就别再拿 Soda 报错）
                if any(len(o) > len(term) and o in en_text and terms[o]["zh"] in zh_text
                       for o in terms):
                    continue
                want = info["zh"]
                # 术语的英文原词出现了，但中文里没有对应译法 → 记问题（可能是意译/代词，人工看）
                if want not in zh_text and term.lower() not in zh_text.lower():
                    problems.append(f"{name} 第 {r.get('id')} 行：{term} → 应为「{want}」，"
                                    f"实际：{zh_text[:40]}")
    return checked, problems


def cmd_check(_args) -> int:
    checked, problems = check_terms()
    print(f"术语校验：检查 {checked} 行，疑似不一致 {len(problems)} 处")
    for p in problems[:25]:
        print("  ·", p)
    if len(problems) > 25:
        print(f"  …… 其余 {len(problems) - 25} 处见输出文件")
    return 1 if problems else 0


def cmd_status(_args) -> int:
    zh_dir = ZH_DIR  # 输入译文目录（合并产物在 out/zh，那是零协结构文件）
    total_lines = 0
    done_lines = 0
    print("文件            行数  已译")
    for name in STORY_FILES:
        rows = [r for r in records(name) if isinstance(r, dict) and r.get("content")]
        total_lines += len(rows)
        n = 0
        p = zh_dir / f"{name}.json"
        if p.is_file():
            n = len(load(p).get("lines") or {})
        done_lines += n
        flag = "✅" if n >= len(rows) else ("…" if n else "")
        print(f"{name:<14} {len(rows):>5} {n:>5} {flag}")
    print(f"合计 {done_lines}/{total_lines} 行（{done_lines * 100 // max(total_lines, 1)}%）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("name")
    d.set_defaults(func=cmd_dump)
    m = sub.add_parser("merge")
    m.add_argument("name")
    m.set_defaults(func=cmd_merge)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("check").set_defaults(func=cmd_check)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
