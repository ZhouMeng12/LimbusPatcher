"""英语（游戏基线语言）原文对照：只读解析 Locale 基线文件。

游戏把各语言基线放在 `<游戏>/LimbusCompany_Data/Assets/Resources_moved/Localize/<lang>/`，
文件名规则为 `<子目录>/EN_<原文件名>`（英文前缀 EN_）。零协包 `Lang/LLC_zh-CN/StoryData/S001B.json`
对应 `Localize/en/StoryData/EN_S001B.json`。

**本模块只读**：任何情况下都不会写入 `Assets/Resources_moved/Localize/**`（也从不写零协包），
英文文本只用于界面显示与搜索索引。取值失败一律返回 (None, 中文原因)，不抛异常、不猜记录。
"""
from __future__ import annotations

import json
from pathlib import Path

from .patch import EntryRef, get_value

BASELINE_LANG_DEFAULT = "en"
EN_PREFIX = "EN_"

# 取不到英文时的中文原因（界面直接显示）
REASON_NO_DIR = "未找到英文基线目录"
REASON_NO_FILE = "该文件没有英文基线"
REASON_NO_RECORD = "英文里没有这条记录"
REASON_NO_FIELD = "英文无此字段"
REASON_EMPTY = "英文此处为空"

_CACHE_LIMIT = 12
_file_cache: dict[str, dict | None] = {}
_cache_order: list[str] = []


def clear_cache() -> None:
    """清空英文文件缓存（重建索引 / 换游戏目录后调用）。"""
    _file_cache.clear()
    _cache_order.clear()


def baseline_langs(base_localize_dir: Path) -> list[str]:
    """可用基线语言目录（en/jp/kr…），按名称排序。"""
    d = Path(base_localize_dir)
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir() and any(p.rglob("*.json")))


def baseline_relpaths(rel: str) -> list[str]:
    """零协相对路径 → 英文候选相对路径（按优先级）。"""
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel:
        return []
    d, _, name = rel.rpartition("/")
    stem, dot, ext = name.rpartition(".")
    if not dot:  # 没有扩展名：原样试一次
        return [rel]
    cands = []
    if stem.startswith(EN_PREFIX):
        cands.append(name)  # 已经是 EN_ 前缀（个别包直接以 EN_ 命名）
    else:
        cands.append(f"{EN_PREFIX}{stem}.{ext}")
        cands.append(name)  # 兜底：同名文件
    return [f"{d}/{c}" if d else c for c in cands]


def baseline_path(baseline_dir: Path | None, rel: str) -> Path | None:
    """英文基线文件路径；不存在返回 None。"""
    if baseline_dir is None:
        return None
    base = Path(baseline_dir)
    for cand in baseline_relpaths(rel):
        p = base / cand
        if p.is_file():
            return p
    return None


def _load(path: Path) -> dict | None:
    """带小 LRU 的 JSON 读取（英文文件有的带 BOM 有的不带，统一 utf-8-sig）。"""
    key = str(path)
    if key in _file_cache:
        return _file_cache[key]
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        obj = None
    _file_cache[key] = obj
    _cache_order.append(key)
    while len(_cache_order) > _CACHE_LIMIT:
        _file_cache.pop(_cache_order.pop(0), None)
    return obj


def find_record(dl: list, ref: EntryRef) -> dict | None:
    """在英文 dataList 中找对应记录：**优先且只信任 KeyID**。

    规则（宁缺勿错——显示别的台词比不显示更糟）：

    1. 英文文件里只要有任意记录带 KeyID，就只按 KeyID 匹配；匹配不到返回 None
       （实测真实包这种「有 id 却对不上」的情形为 0 条）。
    2. 英文文件整份都没有 KeyID（game 里确有这类文件）时，才按同下标对应；
       实测这类 1,124 条叶子与零协记录一一对应，无冲突。
    """
    if not dl:
        return None
    has_ids = any(isinstance(r, dict) and "id" in r for r in dl)
    if has_ids:
        if ref.id is None:
            return None
        for r in dl:
            if isinstance(r, dict) and r.get("id") == ref.id:
                return r
        return None
    if 0 <= ref.record_index < len(dl):
        cand = dl[ref.record_index]
        return cand if isinstance(cand, dict) else None
    return None


def _value(record: dict, ref: EntryRef) -> tuple[str | None, str | None]:
    """容错取字段：英文记录可能缺这个字段、或嵌套列表长度不同。"""
    try:
        value = get_value(record, ref.field_path)
    except (KeyError, IndexError, TypeError):
        return None, REASON_NO_FIELD
    if not isinstance(value, str):
        return None, REASON_NO_FIELD
    if not value.strip():
        return None, REASON_EMPTY
    return value, None


def baseline_text(baseline_dir: Path | None, ref: EntryRef) -> tuple[str | None, str | None]:
    """取英文原文。返回 (文本, 原因)；成功时原因为 None。"""
    if baseline_dir is None or not Path(baseline_dir).is_dir():
        return None, REASON_NO_DIR
    path = baseline_path(baseline_dir, ref.file)
    if path is None:
        return None, REASON_NO_FILE
    data = _load(path)
    dl = data.get("dataList") if isinstance(data, dict) else None
    if not isinstance(dl, list):
        return None, REASON_NO_FILE
    record = find_record(dl, ref)
    if record is None:
        return None, REASON_NO_RECORD
    return _value(record, ref)


def iter_baseline_texts(baseline_dir: Path | None, rel: str, dl: list):
    """按零协记录顺序产出 (record_index, ref 取值函数)，供索引构建复用同一套规则。

    yield 的是 ``(record_index, record_dict)``；调用方自行用 ref.field_path 取值，
    以便和零协侧的 walk_leaves 一一对应。
    """
    path = baseline_path(baseline_dir, rel) if baseline_dir else None
    if path is None:
        return
    data = _load(path)
    en_dl = data.get("dataList") if isinstance(data, dict) else None
    if not isinstance(en_dl, list):
        return
    for i, rec in enumerate(dl):
        if not isinstance(rec, dict):
            continue
        ref = EntryRef(file=rel, id=rec.get("id"), record_index=i, field_path=[])
        yield i, find_record(en_dl, ref)
