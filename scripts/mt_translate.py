"""机翻第一遍（Google 翻译 gtx 接口）＋**术语强制**：把专有名词/标签挖成占位符，翻完按定译表填回。

为什么这么做（对应「省 token + 专有名词不能错」）：
- 专有名词零容错 → 一律挖成占位符，机翻不可能译错；空格/大小写也统一由定译表说了算；
- 游戏标签（`<color=…>`/`<i>`/`<ruby=…>`）同样挖掉，避免被翻译或吃掉；
- 一整段用换行拼起来一次请求（25 行一批），回来按行拆；行数对不上就退回逐行；
- 回来再做中文标点规范化（`...`→`……`、半角→全角、`N 公司`→`N公司`；`--`→`——`）。

产物：`data/translate/zh/<文件>.json`（与人工译文同结构，`translate_pack.py merge` 直接吃）
用法：
    python scripts/mt_translate.py --missing            # 只翻还没有译文的
    python scripts/mt_translate.py S1003B S1004B        # 指定文件
    python scripts/mt_translate.py --missing --dry-run  # 只看待翻量
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import translate_pack as tp  # noqa: E402
import mt_engines  # noqa: E402

API = "https://translate.googleapis.com/translate_a/single"
CHUNK = 8            # 每批 8 行：批太大 Bing 会整批失败退化成逐行（慢）
ENGINE = "bing"
THROTTLE = 1.0      # 多子代理并行时共用同一出口 IP，节流放大一点防限流      # 每次请求之间的间隔（秒），别把接口打限流
TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s*=\s*[^>]*)?>")  # 只认真标签；<*sigh* …> 这种「但丁心声」不算
BRACKET_RE = re.compile(r"\[[^\]\n]{0,60}\]")   # [Bleed]/[CombatStart] 是游戏内部效果 id，必须原样保留
PH_L, PH_R = "@@", "@@"                  # @@n@@：实测 GT 原样保留（〖〗 / <<>> 会被改成《》）
_CJK = r"\u4e00-\u9fff\u3000-\u303f\uff00-\uffef"


def term_map() -> dict[str, str]:
    """英文术语 → 中文（术语表 + 审定新词）。"""
    out = {}
    for en, info in tp.glossary().items():
        zh = info.get("zh") if isinstance(info, dict) else str(info)
        if en and zh:
            out[en] = zh
    return out


def protect(text: str, terms: dict[str, str]) -> tuple[str, dict[str, str]]:
    """标签与术语 → 占位符。ASCII 术语按词边界匹配，避免 Bus 命中 Business。"""
    mapping: dict[str, str] = {}

    def _mask(value: str) -> str:
        key = f"{PH_L}{len(mapping)}{PH_R}"
        mapping[key] = value
        return key

    text = text.replace("\n", _mask("\n"))       # 换行也让 Bing 原样带着走
    for tag in TAG_RE.findall(text):
        text = text.replace(tag, _mask(tag))
    for seg in BRACKET_RE.findall(text):         # 方括号效果 id 整段挖走，绝不翻译
        text = text.replace(seg, _mask(seg))
    for en in sorted(terms, key=len, reverse=True):
        zh = terms[en]
        if en not in text:
            continue
        if en.isascii():
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(en)}(?![A-Za-z0-9])")
            if pattern.search(text):
                text = pattern.sub(lambda _m: _mask(zh), text)
        else:
            text = text.replace(en, _mask(zh))
    return text, mapping


def restore(text: str, mapping: dict[str, str]) -> str:
    for key, value in mapping.items():
        text = text.replace(key, value)
    for key, value in mapping.items():          # GT 偶尔换括号形态，兜底
        num = re.search(r"\d+", key)
        if not num:
            continue
        for variant in (f"〖{num.group()}〗", f"【{num.group()}】", f"《{num.group()}》",
                        f"『{num.group()}』", f"[{num.group()}]", f"({num.group()})",
                        f"｛{num.group()}｝", f"__{num.group()}__", f"%%{num.group()}%%"):
            text = text.replace(variant, value)
    return text


def gt(text: str) -> str | None:
    """交给 mt_engines（Bing 为主，Google 兜底）。"""
    return mt_engines.translate(text, ENGINE)


#: 机翻留下的动作标记 → 零协写法（零协把 *sigh* 这类写成中文拟声词）
ACTION_MAP = {
    "*叹气*": "唉，", "*叹息*": "唉，", "*轻叹*": "唉，", "*耸耸肩*": "（耸耸肩）",
    "*笑*": "哈哈，", "*轻笑*": "呵呵，", "*咯咯笑*": "嘻嘻，", "*大笑*": "哈哈哈！",
    "*咳嗽*": "咳，", "*干咳*": "咳，", "*喘息*": "呼……", "*喘气*": "呼……",
    "*抽气*": "呼，", "*嘟囔*": "嘀咕着，", "*低声*": "低声，", "*摇头*": "（摇头）",
    "*点头*": "（点头）", "*微笑*": "（微笑）", "*沉默*": "……", "*嗤笑*": "嗤，",
}
#: 英文动作标记（机翻有时原样留下）
ACTION_EN = {
    "*sigh*": "唉，", "*chuckle*": "呼呼，", "*laugh*": "哈哈，", "*cough*": "咳，",
    "*hack*": "咳，", "*wheeze*": "呼……", "*puff*": "呼，", "*giggle*": "嘻嘻，",
    "*snort*": "哼，", "*groan*": "呃……", "*gasp*": "呼……", "*mutter*": "低声，",
}


def normalize_zh(text: str) -> str:
    """中文标点与空格规范化（只动标点/空格/动作标记，不碰标签与内容）。"""
    for raw, fixed in {**ACTION_MAP, **ACTION_EN}.items():
        text = text.replace(raw, fixed)
    text = re.sub(r"\.{2,}", "……", text)
    text = re.sub(r"…+\.+", "……", text)
    text = re.sub(r"…{3,}", "……", text)
    text = text.replace("....", "……")
    text = re.sub(r"-{2,}", "——", text)
    text = re.sub(rf"(?<=[{_CJK}])\s+(?=[{_CJK}])", "", text)          # 中文之间的空格
    text = re.sub(rf"(?<=[{_CJK}])\s+(?=[A-Za-z0-9])", "", text)       # 中文后接英文/数字
    text = re.sub(rf"(?<=[A-Za-z0-9])\s+(?=[{_CJK}])", "", text)       # 英文/数字后接中文
    punct = {",": "，", "!": "！", "?": "？", ";": "；", ":": "："}
    text = re.sub(rf"(?<=[{_CJK}])([,!?;:])", lambda m: punct[m.group()], text)
    text = re.sub(r"(?<=[一-鿿])\.", "。", text)
    text = re.sub(r"([，。！？；：])+", r"", text)
    return text.strip()


PLACEHOLDER_LEFT = re.compile(r"@@\s*\d+\s*@@|[〖【『《]\s*\d{1,2}\s*[〗】』》]|%%.{0,3}%%")


def _placeholder_left(text: str) -> bool:
    return bool(PLACEHOLDER_LEFT.search(text))


def translate_lines(lines: list[str], terms: dict[str, str]) -> tuple[list[str], list[str]]:
    out: list[str] = []
    problems: list[str] = []
    for start in range(0, len(lines), CHUNK):
        chunk = lines[start:start + CHUNK]
        masked, maps = [], []
        for line in chunk:
            m, mapping = protect(line, terms)
            masked.append(m)
            maps.append(mapping)
        raw = gt("\n".join(masked))
        parts = [p.strip() for p in raw.split("\n") if p.strip()] if raw else []
        if len(parts) == len(chunk):
            restored = [normalize_zh(restore(p, m)) for p, m in zip(parts, maps)]
            if not any(_placeholder_left(t) for t in restored):
                out.extend(restored)
                continue
            problems.append(f"第 {start + 1}~{start + len(chunk)} 行：有占位符没填回，逐行重试")
        problems.append(f"第 {start + 1}~{start + len(chunk)} 行整批失败（{len(parts)} 行），逐行重试")
        for masked_line, mapping, raw_line in zip(masked, maps, chunk):
            text = ""
            for attempt in range(3):           # 占位符没填回/整行没翻 → 重试
                single = gt(masked_line) or ""
                text = normalize_zh(restore(single, mapping))
                if text.strip() and not _placeholder_left(text) and text.strip() != raw_line.strip():
                    break
                time.sleep(THROTTLE)
            out.append(text)
            time.sleep(THROTTLE)
    return out, problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--missing", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--engine", choices=("bing", "google"), default="bing")
    args = ap.parse_args()

    global ENGINE
    ENGINE = args.engine
    terms = term_map()
    names = args.names or tp.STORY_FILES
    if args.missing:
        names = [n for n in names if not (tp.ZH_DIR / f"{n}.json").is_file()]
    todo = 0
    for name in names:
        rows = [r for r in tp.records(name) if isinstance(r, dict) and r.get("content")]
        todo += len(rows[:args.limit] if args.limit else rows)
    print(f"待翻 {len(names)} 个文件 · {todo} 行 · 强制术语 {len(terms)} 条")
    if args.dry_run:
        for n in names:
            rows = [r for r in tp.records(n) if isinstance(r, dict) and r.get("content")]
            print(f"  {n}: {len(rows)} 行")
        return 0

    tp.ZH_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        rows = [r for r in tp.records(name) if isinstance(r, dict) and r.get("content")]
        if args.limit:
            rows = rows[:args.limit]
        src = [str(r.get("content") or "") for r in rows]
        t0 = time.time()
        out, problems = translate_lines(src, terms)
        empties = sum(1 for z in out if not z.strip())
        if out and empties > max(2, len(out) * 0.1):
            print(f"{name}: 空译过多（{empties}/{len(out)}），跳过不写，稍后重试")
            continue
        (tp.ZH_DIR / f"{name}.json").write_text(json.dumps({
            "lines": {tp.line_key(r, i): zh for i, (r, zh) in enumerate(zip(rows, out))},
            "meta": {},
            "mt": {"engine": "google-gtx", "at": time.strftime("%Y-%m-%d %H:%M")},
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        empty = sum(1 for z in out if not z.strip())
        print(f"{name}: {len(out)} 行 · {time.time() - t0:.0f}s · 空译 {empty} · 问题 {len(problems)}")
        for p in problems[:2]:
            print("   ·", p)
    print("下一步：python scripts/translate_pack.py merge <文件>；再跑 check 做术语校验")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
