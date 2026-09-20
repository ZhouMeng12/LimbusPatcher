"""wiki 剧情页 ↔ 本地零协 StoryData 文本匹配（文件级打分）。

wiki 文本含说话人名前缀，本地 content 不含（teller 单独存），
故按「去掉已知说话人前缀后的锚点串」与各文件 content 前缀做包含投票，
得分最高且 ≥ 阈值的文件即该段落页对应的本地文件。

用法：python scripts/crawl_wiki_story.py match <LLC目录>
输出：data/wiki_story/stage_map.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SPEAKERS = [
    "但丁", "浮士德", "李箱", "以实玛利", "罗佳", "格里高尔", "奥提斯", "希斯克利夫",
    "鸿璐", "良秀", "默尔索", "辛克莱", "狼", "狮", "豹", "卡戎", "维吉里乌斯",
    "红眼之人", "???", "？？？", "我",
]

_PUNCT_RE = re.compile(r'[“”"\'《》<>『』「」…·!！?？。，、：；\-—~～()（）_＊*#＃&＆|｜／/\\]')


def norm(s: str) -> str:
    from limbus_patcher.storybook import norm_text

    return norm_text(s)


def strip_speaker(text: str) -> str:
    for sp in sorted(SPEAKERS, key=len, reverse=True):
        if text.startswith(sp):
            return text[len(sp):]
    return text


def signatures(text: str) -> list[str]:
    n = norm(strip_speaker(text))
    if len(n) < 4:
        return []
    return [n[:24], n[:12], n[:8]]


def load_file_prefixes(llc_dir: Path) -> dict[str, set[str]]:
    """文件内容前缀索引；每条记录建立 content 与 teller+content 两个键。"""
    files: dict[str, set[str]] = {}
    sd = llc_dir / "StoryData"
    if not sd.is_dir():
        raise FileNotFoundError(f"缺少 StoryData：{sd}")
    for p in sorted(sd.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        pre: set[str] = set()
        for r in d.get("dataList", []):
            c = r.get("content")
            if not isinstance(c, str):
                continue
            n = norm(c)
            if len(n) >= 4:
                pre.add(n[:24])
            t = r.get("teller")
            if isinstance(t, str) and t.strip():
                nt = norm(t + c)
                if len(nt) >= 4:
                    pre.add(nt[:24])
        files[f"StoryData/{p.name}"] = pre
    return files


def match_page_file(page: dict, files: dict[str, set[str]]) -> tuple[str | None, int, int]:
    lines = [l["text"] for l in page["lines"] if not l.get("scene") and len(norm(l["text"])) >= 4]
    total = len(lines)
    if total == 0:
        return None, 0, 0
    best_file, best_score = None, 0
    for fname, pre in files.items():
        sc = 0
        for t in lines:
            for s in signatures(t):
                if any(p.startswith(s) or s in p for p in pre):
                    sc += 1
                    break
        if sc > best_score:
            best_file, best_score = fname, sc
    return (best_file if best_score >= max(3, total * 0.2) else None), best_score, total


def run_match(out_dir: Path, llc_dir: Path | None = None) -> int:
    llc_dir = llc_dir or Path(sys.argv[2] if len(sys.argv) > 2 else "")
    if not llc_dir.is_dir():
        print("用法: crawl_wiki_story.py match <LLC目录>")
        return 2
    parsed = json.load(open(out_dir / "parsed.json", encoding="utf-8"))
    files = load_file_prefixes(llc_dir)
    print(f"本地 StoryData 文件：{len(files)}")
    stages: dict[str, dict] = {}
    unmatched: list[str] = []
    for title, page in parsed.items():
        fname, score, total = match_page_file(page, files)
        if fname is None:
            unmatched.append(title)
            continue
        stages[title] = {
            "stage": page.get("stage"),
            "file": fname,
            "score": score,
            "total": total,
        }
    (out_dir / "stage_map.json").write_text(
        json.dumps(
            {"format_version": 1, "total_pages": len(parsed), "matched_pages": len(stages),
             "stages": stages, "unmatched_pages": unmatched},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"匹配：{len(stages)}/{len(parsed)} 页命中")
    for u in unmatched[:25]:
        print("  未命中:", u)
    return 0
