"""按关卡查询敌人：读取 data/stage_enemies.json。

本地数据说明（format_version 1）：
- chapters：主线章节（c1-c9 + prologue），含关卡列表（stage_code，来自
  story_stages.json）与章节级敌人集合（聚合自 LLC_zh-CN/Enemies-<章节>.json，
  仅收录 enemy_map.json 598 个已知敌方条目）。
- extra：非主线活动条目（镜牢 / 瓦夜 / 间章等），无关卡列表。
- 关卡级敌人本地无结构化数据（战斗配置在二进制 bundle），stages[].enemies
  默认空且 wiki_required=True；点开关卡时 UI 回退展示所属章节敌人集合，
  并标注数据来源（local_stage_approx / local_chapter / none）。
"""
from __future__ import annotations

import json

from .season import package_data_dir

STAGE_ENEMIES_PATH_NAME = "stage_enemies.json"

_CACHE: dict | None = None


def load_stage_enemies() -> dict:
    """加载关卡敌人映射（缓存；文件缺失时返回空结构，不抛异常）。"""
    global _CACHE
    if _CACHE is None:
        try:
            path = package_data_dir() / STAGE_ENEMIES_PATH_NAME
            _CACHE = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001  显示层不应因数据缺失崩溃
            _CACHE = {"chapters": [], "extra": []}
    return _CACHE


def chapters() -> list:
    """主线章节列表：[{chapter_id, chapter_label, chapter_enemies, stages, ...}]"""
    return load_stage_enemies().get("chapters", [])


def extra_items() -> list:
    """非主线活动条目：[{tag, label, enemies, source}]"""
    return load_stage_enemies().get("extra", [])


def find_stage(stage_code: str) -> dict | None:
    """按 stage_code（如 '9-50'）找关卡，附加所属章节信息后返回。"""
    for ch in chapters():
        for st in ch.get("stages", []):
            if st.get("stage_code") == stage_code:
                out = dict(st)
                out["chapter_id"] = ch.get("chapter_id")
                out["chapter_label"] = ch.get("chapter_label")
                out["chapter_name"] = ch.get("chapter_name")
                out["chapter_enemies"] = ch.get("chapter_enemies", [])
                out["chapter_source"] = ch.get("chapter_source", "none")
                return out
    return None


def set_stage_name(stage_code: str, name: str) -> bool:
    """写入/更新某关卡的 stage_name（写回 data/stage_enemies.json 并刷新缓存）。"""
    data = load_stage_enemies()
    for ch in data.get("chapters", []):
        for st in ch.get("stages", []):
            if st.get("stage_code") == stage_code:
                st["stage_name"] = name
                _save(data)
                return True
    return False


def set_chapter_name(chapter_id: str, name: str) -> bool:
    """写入/更新某章节的 chapter_name（写回 data/stage_enemies.json 并刷新缓存）。"""
    data = load_stage_enemies()
    for ch in data.get("chapters", []):
        if ch.get("chapter_id") == chapter_id:
            ch["chapter_name"] = name
            _save(data)
            return True
    return False


def _save(data: dict) -> None:
    global _CACHE
    path = package_data_dir() / STAGE_ENEMIES_PATH_NAME
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    _CACHE = data
