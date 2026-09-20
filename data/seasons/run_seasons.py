# -*- coding: utf-8 -*-
"""赛季/获取方式核对：13 个分片 → ans/<同名>.json
从灰机 wiki 页面渲染文本提取「获取方式」，映射为 (season, acq)，以 wiki 为准。
"""
import glob
import io
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, r"D:\Desktop\lbc\data\portraits")
from huiji_api import api

ROOT = r"D:\Desktop\lbc\data\seasons"
PASTE = os.path.join(ROOT, "paste")
ANS = os.path.join(ROOT, "ans")
PORTRAITS_ANS = r"D:\Desktop\lbc\data\portraits\ans"
SEASON_MAP = r"D:\Desktop\lbc\limbus_patcher\data\season_map.json"

# 40501 等特殊页覆盖
PAGE_OVERRIDE = {"40501": "外观投影/背井离乡的那一夜"}

LINE_RE = re.compile(r"^(\d{5})\uFF5C(.*?)\uFF5C(.*?)\uFF5C现标注：([^\uFF5C]*)/([^\uFF5C]*)\uFF5C(.*)$")


def load_id2page():
    d = {}
    for f in glob.glob(os.path.join(PORTRAITS_ANS, "*.json")):
        for it in json.load(io.open(f, encoding="utf-8"))["items"]:
            if it["page"]:
                d[str(it["id"])] = urllib.parse.unquote(it["page"].rsplit("/", 1)[-1])
    d.update(PAGE_OVERRIDE)
    return d


def parse_paste(path: str) -> list[dict]:
    out = []
    for line in io.open(path, encoding="utf-8").read().splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        eid, name, sinner, cur_s, cur_a, desc = m.groups()
        out.append({"id": eid, "name": name.strip(), "sinner": sinner.strip(),
                    "cur_s": cur_s.strip(), "cur_a": cur_a.strip(), "desc": desc.strip()})
    return out


def acq_text(page: str):
    d = api({"action": "parse", "page": page, "prop": "text", "section": "0", "format": "json"})
    if "parse" not in d:
        return None, "页面不存在"
    s = d["parse"]["text"]["*"]
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", s, re.S)
    for i, r in enumerate(rows):
        t = re.sub(r"<[^>]+>", " ", r)
        t = re.sub(r"\s+", " ", t).strip()
        if t == "获取方式" and i + 1 < len(rows):
            n = re.sub(r"<[^>]+>", " ", rows[i + 1])
            n = re.sub(r"\s+", " ", n).strip()
            return n[:60], None
    return None, "无获取方式行"


def map_acq(t: str):
    t = t or ""
    if "瓦尔普吉斯之夜" in t or "瓦夜" in t:
        return None, "walpurgis"
    if "通行证" in t:
        m = re.search(r"第(\d+)赛季", t)
        return (int(m.group(1)) if m else 0), "pass"
    if "常驻" in t or "主线获取" in t or "初始" in t or "基础" in t or "提取" in t and "赛季" not in t:
        return 0, "base"
    m = re.search(r"第(\d+)赛季提取", t)
    if m:
        return int(m.group(1)), "seasonal"
    m = re.search(r"第(\d+)赛季活动", t)
    if m:
        return int(m.group(1)), "event"
    if "活动" in t:
        return 0, "event"
    return None, "unknown"


def main():
    os.makedirs(ANS, exist_ok=True)
    id2page = load_id2page()
    cur_map = json.load(io.open(SEASON_MAP, encoding="utf-8"))
    cur_all = {**cur_map.get("identities", {}), **cur_map.get("egos", {})}

    files = sorted(f for f in os.listdir(PASTE) if f.endswith(".txt"))
    total = 0
    problems = []
    unseen_texts = {}
    stats = {}
    for pf in files:
        ents = parse_paste(os.path.join(PASTE, pf))
        total += len(ents)
        out = []
        for e in ents:
            eid = e["id"]
            page = id2page.get(eid)
            if not page:
                out.append({"id": eid, "name": e["name"], "season": None, "acq": "unknown",
                            "name_en": "", "reason": "不确定：无页面映射"})
                problems.append(f"{pf} id={eid} 无页面映射")
                continue
            txt, err = acq_text(page)
            if txt is None:
                out.append({"id": eid, "name": e["name"], "season": None, "acq": "unknown",
                            "name_en": "", "reason": "不确定"})
                problems.append(f"{pf} id={eid} {err} page={page}")
                continue
            season, acq = map_acq(txt)
            if acq == "unknown":
                unseen_texts.setdefault(txt, []).append(eid)
            reason = txt[:20]
            name_en = (cur_all.get(eid) or {}).get("name_en", "")
            out.append({"id": eid, "name": e["name"], "season": season, "acq": acq,
                        "name_en": name_en, "reason": reason})
            stats.setdefault(acq, 0)
            stats[acq] += 1
            time.sleep(0.08)
        ans_path = os.path.join(ANS, pf.replace(".txt", ".json"))
        io.open(ans_path, "w", encoding="utf-8").write(
            json.dumps({"entities": out}, ensure_ascii=False, indent=2))
        print(f"✓ {pf} → {len(ents)}", flush=True)
    print("TOTAL:", total)
    print("ACQ:", json.dumps(stats, ensure_ascii=False))
    if unseen_texts:
        print("未识别文本:")
        for t, ids in unseen_texts.items():
            print("  ", t, ids[:8])
    if problems:
        print("PROBLEMS:", len(problems))
        for p in problems:
            print("  ⚠", p)
    else:
        print("PROBLEMS: 0")
    print("DONE")


if __name__ == "__main__":
    main()
