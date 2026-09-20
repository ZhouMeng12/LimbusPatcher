"""灰机 wiki 剧情爬虫（经 r.jina.ai 代理读取）。

流程：枚举全部剧情脚本页（intitle:战前/战中/战后）→ 逐页抓取并缓存 markdown
→ 解析为有序对白 → 与本地零协 StoryData 文本匹配，产出「wiki关卡页 ↔ 本地文件+记录区间」对照表。

用法：
    crawl_wiki_story.py list-transcripts            # 枚举剧情页标题 → data/wiki_story/transcripts.json
    crawl_wiki_story.py fetch-all                   # 抓取全部页面（可中断续跑，已缓存跳过）
    crawl_wiki_story.py parse-all                   # 解析全部缓存页 → data/wiki_story/parsed.json
    crawl_wiki_story.py match <LLC目录>             # 文本匹配 → data/wiki_story/stage_map.json
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "wiki_story"
JINA = "https://r.jina.ai/"
WIKI = "https://limbuscompany.huijiwiki.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) limbus-patcher-crawler/0.1"

SEGMENT_QUERIES = ["intitle:%E6%88%98%E5%89%8D", "intitle:%E6%88%98%E4%B8%AD", "intitle:%E6%88%98%E5%90%8E"]
KNOWN_SPEAKERS = [
    "但丁", "浮士德", "李箱", "以实玛利", "罗佳", "格里高尔", "奥提斯", "希斯克利夫", "鸿璐", "良秀", "默尔索", "辛克莱",
    "狼", "狮", "豹", "？？？", "???", "我", "罪人",
]


def _http(url: str, retries: int = 3) -> bytes:
    last: Exception | None = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=90).read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2.0)
    raise RuntimeError(f"请求失败：{last}")


def api_search(intitle_query: str) -> list[str]:
    """通过 r.jina.ai 代理 MediaWiki search API，分页取标题。"""
    titles: list[str] = []
    offset = None
    while True:
        params = f"action=query&list=search&srsearch={intitle_query}&srnamespace=0&srlimit=500&format=json"
        if offset:
            params += f"&sroffset={offset}"
        raw = _http(JINA + WIKI + "/api.php?" + params).decode("utf-8", errors="replace")
        i = raw.find("{")
        if i < 0:
            break
        try:
            d = json.loads(raw[i:])
        except json.JSONDecodeError:
            break
        hits = d.get("query", {}).get("search", [])
        for h in hits:
            t = h.get("title", "")
            if t not in titles:
                titles.append(t)
        cont = d.get("continue", {})
        if "sroffset" not in cont:
            break
        offset = cont["sroffset"]
        time.sleep(0.5)
    return titles


def page_markdown(title: str) -> str:
    quoted = urllib.parse.quote(title)
    return _http(JINA + f"{WIKI}/wiki/{quoted}").decode("utf-8", errors="replace")


def _body_lines(md: str) -> list[str]:
    lines = []
    started = False
    for raw in md.splitlines():
        s = raw.strip()
        if s.startswith("Markdown Content:"):
            started = True
            continue
        if not started:
            continue
        lines.append(s)
    return lines


def _clean_text(s: str) -> str:
    """去掉内联图片/链接标记、语音按钮残留、空白。"""
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)   # 图片（含“点击播放剧情语音”按钮）
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)  # 普通链接保留文字
    s = re.sub(r"<[^>]*>", "", s)                 # 残留 html 标签
    s = re.sub(r"\s+", " ", s).strip()
    return s


_VOICE_IMG = re.compile(r"!\[[^\]]*点击播放剧情语音[^\]]*\]\([^)]*\)")
_ALL_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")

_NOISE_SUB = (
    "来自边狱公司中文维基", "分类:", "站点侧边栏", "个人工具", "导航菜单",
)


def _is_noise_line(s: str, text: str) -> bool:
    if "来自边狱公司中文维基" in s or "blob:" in s:
        return True
    # wiki 页面维护信息 / 致谢 / 音频文件名
    if re.search(r"于\s*\d+\s*(个)?(月|天|年|小时|分钟)前修改了此页面", text):
        return True
    if "修改了此页面" in text or "本页面翻译来自" in text or "汉化组" in text and "感谢" in text:
        return True
    if re.fullmatch(r"audio\s*\d+", text.strip(), re.I):
        return True
    if ".png" in text or text.strip().endswith(")"):  # 清洗后仍残留的图片片段（如 ".png)"）
        if ".png" in text:
            return True
    if text.strip().startswith("世界观/"):
        return True
    if re.fullmatch(r"[A-Za-z]{2,}[-\s][A-Za-z0-9\-]+", text.strip()):
        return True
    if re.fullmatch(r".{0,12}(战前|战后|战中)", text.strip()) and re.search(r"[-A-Za-z0-9]", text):
        return True
    t = text
    if t.startswith(("上一章", "下一章", "前往", "折叠", "||", "分类", "章节")) or "||" in t[:14]:
        return True
    if t.count("|") >= 2:
        return True
    for n in _NOISE_SUB:
        if n in t:
            return True
    if re.fullmatch(r"章节[IVX0-9]+.*", t):
        return True
    return False


def _strip_images(s: str) -> str:
    return _clean_text(_ALL_IMG.sub("", s))


def parse_transcript(title: str, md: str) -> dict:
    """解析脚本页 → {title, lines:[{scene?, marker, name?, text}]}。

    说话人规则：一行中「点击播放剧情语音」图片之前是人名、之后是台词；
    无前置人名 = 旁白；无该图片 = 转场/叙述。scene=True 为 ### 场景标题。
    """
    entries: list[dict] = []
    marker: str | None = None
    for s in _body_lines(md):
        if not s or s.startswith("http"):
            continue
        if s.startswith("###"):
            marker = None
            entries.append({"scene": True, "marker": None, "text": _strip_images(s[3:])})
            continue
        m = re.fullmatch(r"\[([^\[\]]+)\]", s)
        if m:
            marker = m.group(1).strip()
            continue
        if s.startswith(("Title:", "URL Source:", "Published Time:")):
            continue
        text = _clean_text(s)
        if not text:
            continue
        if _is_noise_line(s, text):
            continue
        vm = _VOICE_IMG.search(s)
        name: str | None = None
        if vm:
            name_raw = s[: vm.start()]
            speech = s[vm.end():]
            name = _strip_images(name_raw).strip() or None
        else:
            speech = s
        speech = _clean_text(speech)
        speech = re.sub(r"\*\*|__|(?<!\w)\*(?=\S)|(?<=\S)\*(?!\w)|_(?=\S)|(?<=\S)_(?!\w)", "", speech).strip()
        if not speech:
            continue
        # 纯地名短行 → 场景行
        if _looks_like_place(speech):
            entries.append({"scene": True, "marker": None, "text": speech})
            continue
        # 纯称号/团体短行（如 LCE研究组 / 11号罪人）→ 作为后续台词的 title
        if _looks_like_title(speech):
            marker = speech.strip("[]（）() ")
            continue
        entries.append({"scene": False, "marker": marker, "name": name, "text": _strip_audio(speech)})
    # 不合并多段：wiki 每段 ≈ 本地一条记录
    return {"title": title, "lines": entries}


_PLACE_TAIL = re.compile(
    r".*(区|巢|层|栋|楼|街|路|室|厅|站|场|桥|森林|树林|内部|甲板|船舱|小船|走廊|地下室|对练场|门前|广场|大厅|会议室|房间|屋顶|仓库|站台)$"
)
_TITLE_HINT = ("研究组", "协会", "公司", "事务所", "部门", "支部", "号罪人", "家族", "集团", "帮", "科", "分部")


def _looks_like_place(text: str) -> bool:
    t = text.strip()
    return 2 <= len(t) <= 14 and not re.search(r"[。？！，、…]", t) and bool(_PLACE_TAIL.match(t))


def _looks_like_title(text: str) -> bool:
    t = text.strip("[]（）() ")
    if not (2 <= len(t) <= 12) or re.search(r"[。？！，、…]", t):
        return False
    return any(h in t for h in _TITLE_HINT)


def _strip_audio(text: str) -> str:
    return re.sub(r"audio\d+", "", text, flags=re.I).strip()


def classify_stage(title: str) -> dict | None:
    """从页面标题解析章节信息。返回 {chapter_id, chapter_label, stage_code, segment} 或 None。"""
    m = re.match(r"^(\d+(?:\.\d)?)-(\d+)(战前|战中|战后)", title)
    if not m:
        return None  # 特殊活动页（如 仲春夜之梦3战前）后续单独处理
    ch, stage, seg = m.group(1), m.group(2), m.group(3)
    if ch == "0":
        cid, clabel = "prologue", "序章"
    elif "." in ch:
        n = float(ch)
        cid = {3.5: "i35", 4.5: "i45", 5.5: "i55", 6.5: "i65", 7.5: "i75", 8.5: "i85"}.get(n, f"i{int(n * 10)}")
        clabel = f"间章 {ch}"
    else:
        cid, clabel = f"c{ch}", f"第{ch}章"
    return {"chapter_id": cid, "chapter_label": clabel, "stage_code": f"{ch}-{stage}", "segment": seg}


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    OUT.mkdir(parents=True, exist_ok=True)
    if cmd == "list-transcripts":
        titles: list[str] = []
        for q in SEGMENT_QUERIES:
            for t in api_search(q):
                if t not in titles:
                    titles.append(t)
        json.dump(titles, open(OUT / "transcripts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"剧情页总数：{len(titles)}")
        for t in titles[:40]:
            print(" ", t)
    elif cmd == "fetch-all":
        from concurrent.futures import ThreadPoolExecutor

        titles = json.load(open(OUT / "transcripts.json", encoding="utf-8"))
        pending = [t for t in titles if not (OUT / "pages" / f"{t}.md").is_file()]
        done = len(titles) - len(pending)
        print(f"待抓取 {len(pending)} 页（已缓存 {done}）")
        failures: list[str] = []

        def one(t: str) -> None:
            dest = OUT / "pages" / f"{t}.md"
            if dest.is_file():
                return
            try:
                md = page_markdown(t)
                dest.write_text(md, encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                failures.append(f"{t}: {e}")

        with ThreadPoolExecutor(max_workers=3) as pool:
            for i, _ in enumerate(pool.map(one, pending), 1):
                if i % 15 == 0 or i == len(pending):
                    fetched = len(titles) - len([t for t in pending if not (OUT / "pages" / f"{t}.md").is_file()])
                    print(f"进度 {done + i}/{len(titles)}（已缓存 {fetched}）", flush=True)
        if failures:
            print(f"失败 {len(failures)} 页，可重跑续抓：")
            for f in failures[:20]:
                print(" ", f)
        print("抓取完成")
    elif cmd == "parse-all":
        titles = json.load(open(OUT / "transcripts.json", encoding="utf-8"))
        out = {}
        for t in titles:
            p = OUT / "pages" / f"{t}.md"
            if not p.is_file():
                continue
            try:
                data = parse_transcript(t, p.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                print(f"[ERR] {t}: {e}")
                continue
            data["stage"] = classify_stage(t)
            out[t] = data
        json.dump(out, open(OUT / "parsed.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"解析完成：{len(out)} 页")
    elif cmd == "match":
        from _match import run_match

        return run_match(OUT)
    elif cmd == "watch":
        import time as _time

        titles = json.load(open(OUT / "transcripts.json", encoding="utf-8"))
        total = len(titles)
        t0 = _time.time()
        last = 0
        while True:
            done = sum(1 for t in titles if (OUT / "pages" / f"{t}.md").is_file())
            rate = (done - last) / 5.0
            last = done
            eta = (total - done) / rate if rate > 0.1 else float("inf")
            pct = done * 100 // total
            bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
            print(f"[{bar}] {done}/{total} ({pct}%)  速率 {rate:.1f} 页/秒  ETA {eta/60:.0f} 分钟", flush=True)
            if done >= total:
                print("抓取完成 ✔")
                break
            _time.sleep(5)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
