"""从 Limbus Company Fandom wiki 批量抓取人格 / E.G.O 立绘（离线缓存到 data/portraits）。

- 实体清单与英文名来自索引库 + season_map（name_en）。
- 每个实体取 <英文名>_Full.png（立绘），退化用 _Idle_Sprite.png。
- 只写 data/portraits/identity|ego/<id>.png，不动游戏文件。

用法：
    python scripts/fetch_portraits_fandom.py [--out data/portraits] [--kinds identity,ego] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

API = "https://limbuscompany.fandom.com/api.php"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LimbusPatcher/1.0"
BATCH = 40


def api(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def entity_rows(db_path: Path, kinds: list[str]) -> list[dict]:
    con = sqlite3.connect(str(db_path))
    rows = con.execute(
        "SELECT entity_key, kind, entity_id, name, name_with_title FROM entities WHERE kind IN (%s)"
        % ",".join("?" * len(kinds)), kinds).fetchall()
    con.close()
    return [{"key": r[0], "kind": r[1], "id": r[2], "name": r[3], "title": r[4]} for r in rows]


def english_names() -> dict[int, str]:
    """从 season_map.json 读英文名（identities / egos 两段）。"""
    path = ROOT / "limbus_patcher" / "data" / "season_map.json"
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[int, str] = {}
    for section in ("identities", "egos"):
        for key, meta in (obj.get(section) or {}).items():
            if isinstance(meta, dict) and meta.get("name_en"):
                try:
                    out[int(key)] = str(meta["name_en"])
                except (TypeError, ValueError):
                    continue
    return out


def file_urls(file_titles: list[str]) -> dict[str, str]:
    """File:xxx → 原图 URL。"""
    out: dict[str, str] = {}
    for i in range(0, len(file_titles), BATCH):
        chunk = file_titles[i:i + BATCH]
        d = api({"action": "query", "format": "json", "titles": "|".join(chunk),
                 "prop": "imageinfo", "iiprop": "url"})
        for page in (d.get("query", {}) or {}).get("pages", {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("url"):
                out[str(page.get("title", ""))] = info["url"]
    return out


def images_of(titles: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        d = api({"action": "query", "format": "json", "titles": "|".join(chunk),
                 "prop": "images", "imlimit": "200"})
        for page in (d.get("query", {}) or {}).get("pages", {}).values():
            out[str(page.get("title", ""))] = [im.get("title", "") for im in page.get("images", []) or []]
    return out


def download(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = resp.read()
        if len(data) < 1024:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True
    except Exception:  # noqa: BLE001
        return False


def pick_file(images: list[str], en: str) -> str | None:
    """优先 <英文名>_Full.png，其次 <英文名>_Idle_Sprite.png。"""
    want_full = f"File:{en}_Full.png".lower()
    want_idle = f"File:{en}_Idle_Sprite.png".lower()
    fallback = None
    for title in images:
        low = title.lower()
        if low == want_full:
            return title
        if low == want_idle and fallback is None:
            fallback = title
    if fallback:
        return fallback
    for title in images:  # 名字对不上时，退一步找含 Full 的
        if title.lower().endswith("_full.png"):
            return title
    return None


def page_images(titles: list[str]) -> dict[str, str]:
    """页面标题 → 原图 URL（pageimages/original）。"""
    out: dict[str, str] = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        try:
            d = api({"action": "query", "format": "json", "titles": "|".join(chunk),
                     "prop": "pageimages", "piprop": "original", "redirects": "1"})
        except Exception:  # noqa: BLE001
            continue
        pages = (d.get("query", {}) or {}).get("pages", {}) or {}
        redirects = {r.get("from"): r.get("to") for r in (d.get("query", {}) or {}).get("redirects", []) or []}
        for page in pages.values():
            title = str(page.get("title", ""))
            src = (page.get("original") or {}).get("source")
            if src:
                out[title] = src
        for src_title, dst_title in redirects.items():
            if dst_title in out and src_title not in out:
                out[src_title] = out[dst_title]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "portraits")
    ap.add_argument("--db", type=Path, default=ROOT / "data" / "cache" / "index.sqlite")
    ap.add_argument("--kinds", default="identity,ego")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if not args.db.is_file():
        print(f"找不到索引库：{args.db}（先在应用里建索引）")
        return 2

    kinds = ["personality" if k.startswith("ident") else "ego" for k in args.kinds.split(",")]
    rows = entity_rows(args.db, kinds)
    en = english_names()
    if args.limit:
        rows = rows[:args.limit]
    print(f"实体 {len(rows)} 个，英文名 {len(en)} 条")

    todo = []
    for row in rows:
        sub = "identity" if row["kind"] == "personality" else "ego"
        dest = args.out / sub / f"{row['id']}.png"
        if dest.is_file() and not args.force:
            continue
        name_en = en.get(row["id"])
        if not name_en:
            continue
        todo.append((row, name_en, dest))
    print(f"待抓取 {len(todo)} 个")

    pages = [t[1] for t in todo]
    found = page_images(pages)
    print(f"页面命中 {len(found)} 个")
    saved = 0
    kinds_saved: list[str] = []
    t0 = time.time()
    for row, name_en, dest in todo:
        url = found.get(name_en)
        if not url:
            continue
        if download(url, dest):
            saved += 1
            kinds_saved.append(row["kind"])
    ids = kinds_saved
    print(f"完成：下载 {saved} 张（人格 {ids.count('personality')} / EGO {ids.count('ego')}）"
          f"，用时 {time.time() - t0:.1f}s → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
