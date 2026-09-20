"""剧本按行对齐：wiki 页对白 → 逐条对应本地记录 → 产出 story_stages.json v2。

每条 item：scene(场景行) 或 line{speaker, text(本地 content), file, record}。
说话人：优先本地 teller；其次 wiki 文本前缀名；再其次 None(旁白)。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _match import norm  # noqa: E402

CORE_SPEAKERS = [
    "但丁", "浮士德", "李箱", "以实玛利", "罗佳", "格里高尔", "奥提斯", "希斯克利夫",
    "鸿璐", "良秀", "默尔索", "辛克莱", "狼", "狮", "豹", "卡戎", "维吉里乌斯", "???", "？？？", "我",
]

# 仅主线（序章 + 第1~9章）；间章/活动暂缓
MAIN_CHAPTERS = {"prologue", "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9"}


def collect_names(llc_dir: Path) -> list[str]:
    names = set(CORE_SPEAKERS)
    for p in sorted((llc_dir / "StoryData").glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        for r in d.get("dataList", []):
            t = r.get("teller")
            if isinstance(t, str) and t.strip():
                names.add(t.strip())
    return sorted(names, key=len, reverse=True)


def leading_speaker(text: str, names: list[str]) -> str | None:
    for n in names:
        if text.startswith(n):
            return n
    return None


def load_records(llc_dir: Path, relfile: str) -> list[dict]:
    try:
        d = json.loads((llc_dir / relfile).read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    return [r for r in d.get("dataList", []) if isinstance(r, dict)]


NOISE_MARKERS = {"???", "？？？", "我"}


def align_page(page: dict, relfile: str, llc_dir: Path, names: list[str],
               overrides: dict | None = None, page_title: str | None = None) -> list[dict]:
    """把一页对白按序对齐到本地文件记录，产出 items。

    speaker 判定：本地 teller 优先 → wiki 语音图切分人名；
    title 取该行前一个 [标记]（如 LCE研究组 / 2号罪人），???/我 不作标题；
    无名字的行视为旁白。overrides: {未对齐句序号: 本地记录号}（AI 语义对齐复核结果）。
    """
    records = load_records(llc_dir, relfile)
    local_norms = [norm((r.get("content") or "")) for r in records]
    items: list[dict] = []
    j = 0
    un_idx = 0
    ov_by_text: dict = {}
    ov_by_index: dict = {}
    if overrides:
        if "by_text" in overrides or "by_index" in overrides:
            ov_by_text = overrides.get("by_text") or {}
            ov_by_index = overrides.get("by_index") or {}
        else:
            ov_by_index = overrides
    last_place: str | None = None
    last_item_type = None
    last_scene_text: str | None = None
    pending_marker: str | None = None

    def add_place_if_new(r: dict) -> None:
        nonlocal last_place, last_item_type, last_scene_text
        pl = r.get("place")
        if not (isinstance(pl, str) and pl.strip()) or pl.strip() == last_place:
            return
        last_place = pl.strip()
        if last_item_type == "scene" and last_scene_text and (last_scene_text in pl or pl in last_scene_text):
            return  # 与 wiki ### 标题重复的场景行
        items.append({"type": "scene", "text": f"📍 {pl.strip()}", "file": relfile, "record": None, "page": page_title})
        last_item_type = "scene"
        last_scene_text = pl.strip()

    def add_scene(text: str) -> None:
        nonlocal last_item_type, last_scene_text
        if last_item_type == "scene":
            return
        items.append({"type": "scene", "text": text, "file": relfile, "record": None, "page": page_title})
        last_item_type = "scene"
        last_scene_text = text

    def clean_prefix(text: str, speaker: str | None) -> str:
        for tok in ([speaker] if speaker else []) + ["???", "？？？", "…", "……"]:
            if tok and text.startswith(tok):
                text = text[len(tok):]
        return text.strip()

    def tidy_speaker(sp: str | None) -> str | None:
        if sp in ("???", "？？？"):
            return "？？？"
        return sp

    for entry in page.get("lines", []):
        if entry.get("scene"):
            add_scene(entry["text"])
            pending_marker = None
            continue
        m = entry.get("marker")
        if m:
            pending_marker = m
        text = entry.get("text", "")
        entry_name = tidy_speaker(entry.get("name"))
        w = norm(text)
        if len(w) < 4:
            continue
        found: int | None = None
        for jj in range(j, len(records)):
            ln = local_norms[jj]
            if len(ln) < 4:
                continue
            if w.endswith(ln) or ln in w or w in ln or w.endswith(ln[:14]) or ln[:14] in w:
                found = jj
                break
        if found is None:
            ov = ov_by_text.get(norm(text)) or ov_by_index.get(str(un_idx))
            un_idx += 1
            ov_rec = ov if isinstance(ov, int) else (ov or {}).get("record")
            if ov_rec is not None and isinstance(ov_rec, int) and 0 <= ov_rec < len(records):
                ov = ov_rec
                # AI 复核结果：按指认记录对齐（不逐字匹配）
                r = records[ov]
                add_place_if_new(r)
                teller = r.get("teller")
                sp = teller if isinstance(teller, str) and teller.strip() else entry_name
                speaker = tidy_speaker(sp)
                title = pending_marker if speaker and pending_marker and pending_marker not in NOISE_MARKERS and pending_marker != speaker else None
                content = r.get("content")
                items.append({
                    "type": "line", "speaker": speaker, "title": title,
                    "text": content if isinstance(content, str) else "",
                    "file": relfile, "record": ov, "page": page_title,
                })
                last_item_type = "line"
                j = ov + 1
                continue
            sp = entry_name or tidy_speaker(leading_speaker(text, names))
            cleaned = text
            title = pending_marker if sp and pending_marker and pending_marker not in NOISE_MARKERS and pending_marker != sp else None
            items.append({
                "type": "line", "speaker": sp, "title": title,
                "text": cleaned, "file": relfile, "record": None, "wiki_only": True,
                "page": page_title, "key": norm(cleaned),
            })
            continue
        r = records[found]
        add_place_if_new(r)
        teller = r.get("teller")
        sp = teller if isinstance(teller, str) and teller.strip() else entry_name
        speaker = tidy_speaker(sp)
        title = pending_marker if speaker and pending_marker and pending_marker not in NOISE_MARKERS and pending_marker != speaker else None
        content = r.get("content")
        items.append({
            "type": "line", "speaker": speaker, "title": title,
            "text": content if isinstance(content, str) else "",
            "file": relfile, "record": found, "page": page_title,
        })
        last_item_type = "line"
        j = found + 1
    return items


def build_all(llc_dir: Path, src: Path) -> dict:
    parsed = json.load(open(src / "parsed.json", encoding="utf-8"))
    sm = json.load(open(src / "stage_map.json", encoding="utf-8"))
    names = collect_names(llc_dir)
    ovp = src / "align_overrides.json"
    ovtp = src / "align_overrides_text.json"
    overrides: dict = {}
    try:
        if ovp.is_file():
            overrides["by_index"] = json.load(open(ovp, encoding="utf-8"))
        if ovtp.is_file():
            overrides["by_text"] = json.load(open(ovtp, encoding="utf-8"))
    except Exception:
        overrides = {}
    chapters: dict[str, dict] = {}

    def sort_key(code: str):
        m = re.match(r"(\d+(?:\.\d)?)-(\d+)", code or "")
        return (0, float(m.group(1)), int(m.group(2))) if m else (1, 0, 0)

    for title, m in sm.get("stages", {}).items():
        st = m.get("stage")
        if not st or not m.get("file"):
            continue
        cid = st.get("chapter_id") or "other"
        if cid not in MAIN_CHAPTERS:
            continue  # 仅主线；间章/活动暂缓
        ch = chapters.setdefault(cid, {"chapter_id": cid, "chapter_label": st.get("chapter_label") or cid, "stages": {}})
        code = st.get("stage_code")
        stg = ch["stages"].setdefault(code, {"stage_code": code, "pages": [], "items": []})
        stg["pages"].append({"segment": st.get("segment"), "title": title, "file": m["file"]})
        ov_page = {
            "by_text": (overrides.get("by_text") or {}).get(title) or {},
            "by_index": (overrides.get("by_index") or {}).get(title) or {},
        }
        stg["items"].extend(align_page(parsed.get(title, {}), m["file"], llc_dir, names, ov_page, title))

    out = {
        "format_version": 2,
        "source": "limbuscompany.huijiwiki.com + 本地零协包按行对齐",
        "matched_pages": len(sm.get("stages", {})),
        "unmatched_pages": len(sm.get("unmatched_pages", [])),
        "chapters": [],
    }
    for cid, ch in sorted(chapters.items()):
        stages = []
        for code in sorted(ch["stages"], key=sort_key):
            stg = ch["stages"][code]
            stages.append({"stage_code": stg["stage_code"], "pages": stg["pages"], "items": stg["items"]})
        out["chapters"].append({"chapter_id": cid, "chapter_label": ch["chapter_label"], "stages": stages})
    return out


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/wiki_story")
    llc = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("")
    if not llc.is_dir():
        print("用法: _align.py <crawl目录> <LLC目录>")
        return 2
    out = build_all(llc, src)
    dest = src / "story_stages.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    # 统计
    lines = scene = unaligned = 0
    speakers = set()
    for ch in out["chapters"]:
        for st in ch["stages"]:
            for it in st["items"]:
                if it["type"] == "scene":
                    scene += 1
                else:
                    lines += 1
                    if it.get("wiki_only"):
                        unaligned += 1
                    if it.get("speaker"):
                        speakers.add(it["speaker"])
    print(f"产出 {dest}：行 {lines} / 场景 {scene} / 未对齐 {unaligned} / 说话人 {len(speakers)} 种")
    return 0


if __name__ == "__main__":
    sys.exit(main())
