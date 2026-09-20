"""赛季/种类映射生成器：从 limbuscompany.wiki.gg 公开 API 拉取分类，
用英文基线名称（零协仓库 EN/ 目录）与零协本地化 ID 做名称 join。

输出：
- season_map.json：人格/E.G.O 的 id → {season, acq, wiki_id, name_en}
- enemy_map.json：敌方 id → {group, label, name_en}

仅生成时联网；运行时由 season.py 离线加载。
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

WIKI_API = "https://limbuscompany.wiki.gg/api.php"
LLC_EN_BASE = "https://raw.githubusercontent.com/LocalizeLimbusCompany/LocalizeLimbusCompany/main/EN/{file}"
USER_AGENT = "limbus-patcher/0.1 (season map generator)"
FORMAT_VERSION = 1

_RISK = ("ZAYIN", "TETH", "HE", "WAW", "ALEPH")


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


_CACHE_PATH: Path | None = None
_CACHE: dict[str, dict] = {}


def set_http_cache(path: Path | None) -> None:
    """开启跨运行的响应缓存（生成器重跑时避免重复请求/限流）。"""
    global _CACHE_PATH, _CACHE
    _CACHE_PATH = path
    _CACHE = {}
    if path and path.is_file():
        try:
            _CACHE = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _CACHE = {}


def _save_cache() -> None:
    if _CACHE_PATH is None:
        return
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(_CACHE, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def http_json(url: str, params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    cache_key = f"{url}?{query}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    req = urllib.request.Request(cache_key, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=40) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(f"wiki API 错误：{data['error']}")
    if _CACHE_PATH is not None:
        _CACHE[cache_key] = data
        _save_cache()
    return data


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def fetch_category_members(category: str, progress=None) -> list[tuple[str, str]]:
    """返回 [(wiki_id, 页面标题)]，自动处理分页。"""
    out: list[tuple[str, str]] = []
    cont: dict | None = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmlimit": "500",
            "cmprop": "ids|title|sortkey",
            "format": "json",
            "formatversion": "2",
        }
        if cont:
            params.update(cont)
        data = http_json(WIKI_API, params)
        for m in data.get("query", {}).get("categorymembers", []):
            sortkey = m.get("sortkey") or ""
            if re.fullmatch(r"[0-9a-fA-F]{2,}", sortkey) and len(sortkey) % 2 == 0:
                try:
                    sortkey = bytes.fromhex(sortkey).decode("utf-8")
                except ValueError:
                    pass
            wid = sortkey.split()[0] if sortkey else ""
            out.append((wid, m.get("title", "")))
        if progress:
            progress(len(out), len(out) + 500)
        if "continue" not in data:
            break
        cont = data["continue"]
    return out


def _fetch_batch(params: dict, retries: int = 5) -> dict:
    last: Exception | None = None
    import time

    for attempt in range(retries):
        time.sleep(1.0 + attempt * 0.5)  # 温和限速，避免 429
        try:
            return http_json(WIKI_API, params)
        except Exception as e:  # noqa: BLE001
            last = e
            wait = 30.0 if "429" in str(e) else 3.0 * (attempt + 1)
            time.sleep(wait)
    raise RuntimeError(f"wiki API 请求失败：{last}")


def _categories_batches(titles: list[str], size: int = 50):
    """分块：含 '::' 的标题单独成批（wiki.gg 批量查询该类标题会丢分类，需逐个请求）。"""
    out: list[list[str]] = []
    buf: list[str] = []
    for t in titles:
        if "::" in t:
            if buf:
                out.append(buf)
                buf = []
            out.append([t])
        else:
            buf.append(t)
            if len(buf) >= size:
                out.append(buf)
                buf = []
    if buf:
        out.append(buf)
    return out


def fetch_categories(titles: list[str], progress=None) -> dict[str, list[str]]:
    """批量获取页面分类（含隐藏分类：Season 等为隐藏分类，需 clshow=hidden 再取一次）。"""
    out: dict[str, list[str]] = {}
    done = 0
    for batch in _categories_batches(titles):
        merged: dict[str, list[str]] = {}
        for clshow in (None, "hidden"):
            params = {
                "action": "query",
                "prop": "categories",
                "titles": "|".join(batch),
                "cllimit": "max",
                "format": "json",
                "formatversion": "2",
            }
            if clshow:
                params["clshow"] = clshow
            data = _fetch_batch(params)
            for page in data.get("query", {}).get("pages", []):
                cats = [c.get("title", "").removeprefix("Category:") for c in page.get("categories", [])]
                merged.setdefault(page.get("title", ""), []).extend(cats)
        out.update(merged)
        done += len(batch)
        if progress:
            progress(done, len(titles))
    return out


# ---- 英文基线（零协仓库 EN/ 目录）----

def _find(en_dir: Path, name: str) -> Path | None:
    """兼容零协仓库 EN/（无前缀）与游戏目录 en/（EN_ 前缀）两种命名。"""
    for cand in (en_dir / name, en_dir / f"EN_{name}"):
        if cand.is_file():
            return cand
    return None


def build_en_maps(en_dir: Path) -> dict:
    """从 EN 基线文件构建 id→英文名 索引（兼容 EN_ 前缀命名）。"""
    personalities = _find(en_dir, "Personalities.json")
    egos_file = _find(en_dir, "Egos.json")
    if personalities is None or egos_file is None:
        raise FileNotFoundError(f"EN 基线文件缺失：{en_dir}")

    identities: dict[str, str] = {}
    sinners: dict[str, str] = {}
    for e in load_json(personalities).get("dataList", []):
        sid = str(e.get("id"))
        title = re.sub(r"\s+", " ", str(e.get("title") or "")).strip()
        name = str(e.get("name") or "").strip()
        identities[sid] = f"{title} {name}".strip()
        if sid.endswith("01") and len(sid) == 5:
            sinners[sid[1:3]] = name

    egos: dict[str, tuple[str, str]] = {}
    for e in load_json(egos_file).get("dataList", []):
        sid = str(e.get("id"))
        code = sid[1:3] if len(sid) >= 3 else ""
        egos[sid] = (str(e.get("name") or ""), sinners.get(code, ""))

    enemies: dict[str, str] = {}
    # 先处理 Enemies.json（基础图鉴 id），章节文件兜底补充（同名不同 id 时以图鉴为准）
    patterns = ("Enemies.json", "EN_Enemies.json", "Enemies*.json", "EN_Enemies*.json")
    for pat in patterns:
        for f in sorted(en_dir.glob(pat)):
            for e in load_json(f).get("dataList", []):
                if str(e.get("id")) not in enemies:
                    enemies[str(e.get("id"))] = str(e.get("name") or "")
    return {"identities": identities, "egos": egos, "enemies": enemies}


def fetch_wikitext(titles: list[str], progress=None) -> dict[str, str]:
    """批量获取页面 wikitext（prop=revisions，50 页/请求）。"""
    out: dict[str, str] = {}
    done = 0
    for batch in _categories_batches(titles):
        data = _fetch_batch(
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": "|".join(batch),
                "format": "json",
                "formatversion": "2",
            }
        )
        for page in data.get("query", {}).get("pages", []):
            revs = page.get("revisions") or []
            if revs:
                out[page.get("title", "")] = revs[0].get("slots", {}).get("main", {}).get("content", "")
        done += len(batch)
        if progress:
            progress(done, len(titles))
    return out


# ---- 分类解析 ----

def parse_identity_season(cats: list[str], wikitext: str = "") -> tuple[int | None, str]:
    """解析 (赛季号, 获取类型)。

    赛季号以页面 IDPage/EGOPage 模板的 |season=N 字段为准（0 = 基础/常驻，
    与灰机 wiki 的人格筛选口径一致）；获取类型从分类推断。
    """
    season: int | None = None
    m = re.search(r"\|season\s*=\s*(\d+)", wikitext)
    if m:
        season = int(m.group(1))
    acq = "seasonal"
    if "Walpurgis Night" in cats:
        acq = "walpurgis"
    elif any(re.fullmatch(r"Season \d+ Pass", c) for c in cats):
        acq = "pass"
    elif any(re.fullmatch(r"Season \d+ Event", c) for c in cats) or "Event Reward Identities and E.G.O" in cats:
        acq = "event"
    elif "Regular" in cats:
        acq = "seasonal"
    if season == 0 or season is None:
        acq = "base" if acq == "seasonal" else acq
    return season, acq


def parse_enemy_kind(cats: list[str]) -> tuple[str, str] | None:
    """从页面分类解析 (种类组, 种类标签)。组: abnormality / faction / unit。"""
    for cat in cats:
        m = re.fullmatch(r"(ZAYIN|TETH|HE|WAW|ALEPH) Abnormalities", cat)
        if m:
            return "abnormality", m.group(1)
    for cat in cats:
        if cat.endswith(" Enemies"):
            prefix = cat.removesuffix(" Enemies").strip()
            if prefix:
                return "faction", prefix
    if "Abnormality" in cats:
        return "abnormality", "异想体"
    if "Enemy" in cats:
        return "unit", "敌方单位"
    return None


# ---- 生成 ----

def generate(dest_dir: Path, en_dir: Path | None = None, progress=None, cache_path: Path | None = None) -> dict:
    """生成映射表并写盘，返回报告。"""
    set_http_cache(cache_path or (dest_dir / "wiki_cache.json"))
    if en_dir is None:
        en_dir = _download_en_baseline(dest_dir.parent / "cache")
    en = build_en_maps(en_dir)
    report: dict = {"unmatched": {}}

    # 人格
    id_members = fetch_category_members("Identity ID", progress)
    norm_identities = {normalize(v): k for k, v in en["identities"].items()}
    id_cats = fetch_categories([t for _, t in id_members], progress)
    id_text = fetch_wikitext([t for _, t in id_members], progress)
    identities: dict[str, dict] = {}
    unmatched_identities: list[str] = []
    for wid, title in id_members:
        key = norm_identities.get(normalize(title))
        if key is None:
            unmatched_identities.append(title)
            continue
        season, acq = parse_identity_season(id_cats.get(title, []), id_text.get(title, ""))
        identities[key] = {"season": season, "acq": acq, "wiki_id": wid, "name_en": title}
    report["unmatched"]["identities"] = unmatched_identities

    # E.G.O
    ego_members = fetch_category_members("E.G.O ID", progress)
    norm_egos = {normalize(f"{name} {sinner}".strip()): k for k, (name, sinner) in en["egos"].items()}
    ego_cats = fetch_categories([t for _, t in ego_members], progress)
    ego_text = fetch_wikitext([t for _, t in ego_members], progress)
    egos: dict[str, dict] = {}
    unmatched_egos: list[str] = []
    for wid, title in ego_members:
        key = norm_egos.get(normalize(title))
        if key is None:
            unmatched_egos.append(title)
            continue
        season, acq = parse_identity_season(ego_cats.get(title, []), ego_text.get(title, ""))
        egos[key] = {"season": season, "acq": acq, "wiki_id": wid, "name_en": title}
    report["unmatched"]["egos"] = unmatched_egos

    # 敌方
    enemy_members = fetch_category_members("Enemy", progress)
    norm_enemies: dict[str, list[str]] = {}
    for sid, name in en["enemies"].items():
        norm_enemies.setdefault(normalize(name), []).append(sid)
    enemy_cats = fetch_categories([t for _, t in enemy_members], progress)
    enemies: dict[str, dict] = {}
    unmatched_enemies: list[str] = []
    for wid, title in enemy_members:
        # wiki 敌方页面常见子页形式：Ahab/Enemy/Ahab、Aida/Enemy —— 取主段匹配
        candidates = [title]
        if "/Enemy" in title:
            candidates.insert(0, title.split("/Enemy", 1)[0])
        ids: list[str] = []
        for cand in candidates:
            ids = norm_enemies.get(normalize(cand)) or []
            if ids:
                break
        if not ids:
            unmatched_enemies.append(title)
            continue
        kind = parse_enemy_kind(enemy_cats.get(title, []))
        if kind is None:
            unmatched_enemies.append(title)
            continue
        group, label = kind
        for key in ids:  # 同名（图鉴 id 与章节实例 id）一并标注
            enemies[key] = {"group": group, "label": label, "name_en": title}
    # 子页条目（Ahab/Enemy/Ahab 等）回退到主页面映射：主页面种类更准确
    base_map = {v.get("name_en", ""): v for v in enemies.values() if "/Enemy" not in v.get("name_en", "")}
    for key, v in list(enemies.items()):
        if "/Enemy" in v.get("name_en", ""):
            better = base_map.get(v["name_en"].split("/Enemy", 1)[0])
            if better:
                enemies[key] = dict(better)
    report["unmatched"]["enemies"] = unmatched_enemies

    # EN 侧缺失（EN 有 id 但 wiki 无对应页面，多为新内容/未建页）
    report["en_side_unmatched"] = {
        "identities": [sid for sid in en["identities"] if sid not in identities],
        "egos": [sid for sid in en["egos"] if sid not in egos],
        "enemies": [sid for sid in en["enemies"] if sid not in enemies],
    }

    dest_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    stamp = datetime.now().isoformat(timespec="seconds")
    (dest_dir / "season_map.json").write_text(
        json.dumps(
            {"format_version": FORMAT_VERSION, "generated_at": stamp, "source": WIKI_API,
             "identities": identities, "egos": egos},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    (dest_dir / "enemy_map.json").write_text(
        json.dumps(
            {"format_version": FORMAT_VERSION, "generated_at": stamp, "source": WIKI_API,
             "enemies": enemies},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    report.update(
        {
            "counts": {"identities": len(identities), "egos": len(egos), "enemies": len(enemies),
                       "en_identities": len(en["identities"]), "en_egos": len(en["egos"]),
                       "en_enemies": len(en["enemies"])},
        }
    )
    return report


def _download_en_baseline(dest: Path) -> Path:
    """回退方案：从零协 GitHub 仓库下载 EN 基线文件（含全部 Enemies*）。"""
    dest.mkdir(parents=True, exist_ok=True)
    api = "https://api.github.com/repos/LocalizeLimbusCompany/LocalizeLimbusCompany/contents/EN"
    req = urllib.request.Request(api, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=40) as resp:
        listing = json.loads(resp.read().decode("utf-8"))
    names = [it["name"] for it in listing if it.get("name", "").endswith(".json")]
    wanted = [n for n in names if n in ("Personalities.json", "Egos.json") or n.startswith("Enemies")]
    for name in wanted:
        if (dest / name).is_file():
            continue
        url = LLC_EN_BASE.format(file=name)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            (dest / name).write_bytes(resp.read())
    return dest
