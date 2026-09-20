"""待确认剧情文件的类型映射（由 data/misc_story/ans/ 的 AI 答案汇总而来）。

- 数据文件：limbus_patcher/data/misc_story_kinds.json（scripts/import_misc_kinds.py 生成）
- 作用：把这些文件的**分类**与**章节**接入 categories / index；缺省（没有答案时）按内置规则归「其他剧情」。
"""
from __future__ import annotations

from pathlib import Path

from .entities import clear_kind_map_cache, load_kind_map

# AI 判定的类型 → 工具分类 id
KIND_CATEGORY: dict[str, str] = {
    "迷宫剧情": "dungeon_story",
    "间章活动": "event",
    "主线": "main_story",
    "人格剧情": "identity_story",
    "集中战斗": "misc_story",
    "其他": "misc_story",
}

_cache: dict[str, dict] | None = None


def _table() -> dict[str, dict]:
    global _cache
    if _cache is None:
        _cache = load_kind_map()
    return _cache


def clear_cache() -> None:
    global _cache
    _cache = None
    clear_kind_map_cache()


def _stem(rel: str) -> str:
    name = (rel or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return name[:-5] if name.lower().endswith(".json") else name


def entry_of(rel: str) -> dict | None:
    """该文件在答案表里的条目（没有则 None）。"""
    return _table().get(_stem(rel))


def kind_of(rel: str) -> str | None:
    item = entry_of(rel)
    return (item or {}).get("kind") or None


def category_of(rel: str) -> str | None:
    kind = kind_of(rel)
    return KIND_CATEGORY.get(kind) if kind else None


def chapter_of(rel: str) -> str | None:
    """章节显示名（如「第5章」「间章 8.5」「8.5-EX」）。"""
    item = entry_of(rel) or {}
    return (item.get("chapter") or None) if item else None


def chapter_number_of(rel: str) -> str | None:
    item = entry_of(rel) or {}
    return (item.get("chapter_number") or None) if item else None


def order_of(rel: str) -> int | None:
    item = entry_of(rel) or {}
    order = item.get("order")
    return order if isinstance(order, int) else None


def stats() -> dict[str, int]:
    """kind → 文件数（状态栏/文档用）。"""
    out: dict[str, int] = {}
    for item in _table().values():
        kind = item.get("kind") or "未判定"
        out[kind] = out.get(kind, 0) + 1
    return out
