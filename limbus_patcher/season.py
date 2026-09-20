"""内置赛季/敌方种类映射的离线加载（data/*.json；支持用户刷新后的覆盖目录）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ACQ_LABELS: dict[str, str] = {
    "base": "基础",
    "seasonal": "赛季",
    "event": "活动",
    "pass": "通行证",
    "walpurgis": "瓦夜",
    "unknown": "未标注",
}

_RISK_LEVELS = ("ZAYIN", "TETH", "HE", "WAW", "ALEPH")


def package_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "limbus_patcher" / "data"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "data"


class MetaMaps:
    """赛季/种类映射：包内 data 目录加载，overlay_dir（用户刷新目录）优先。"""

    def __init__(self, overlay_dir: Path | None = None, data_dir: Path | None = None):
        self.data_dir = data_dir or package_data_dir()
        self.overlay_dir = overlay_dir
        self.season_map: dict = {}
        self.enemy_map: dict = {}
        self.reload()

    def reload(self) -> None:
        self.season_map = self._load("season_map.json")
        self.enemy_map = self._load("enemy_map.json")

    def _load(self, name: str) -> dict:
        dirs = [d for d in (self.overlay_dir, self.data_dir) if d]
        for d in dirs:
            p = Path(d) / name
            if p.is_file():
                try:
                    obj = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(obj, dict):
                        return obj
                except (OSError, json.JSONDecodeError):
                    continue
        return {}

    # ---- 查询 ----

    def identity_meta(self, entry_id: object) -> dict | None:
        return self.season_map.get("identities", {}).get(str(entry_id))

    def ego_meta(self, entry_id: object) -> dict | None:
        return self.season_map.get("egos", {}).get(str(entry_id))

    def enemy_meta(self, entry_id: object) -> dict | None:
        return self.enemy_map.get("enemies", {}).get(str(entry_id))

    def generated_at(self) -> str | None:
        return self.season_map.get("generated_at")


def season_key(meta: dict | None) -> str | None:
    """过滤用赛季键：base / s1..sN；无标注返回 None。

    season=0 且获取方式不是 base（如 40501 活动限定）算「没有赛季」，
    按获取方式归类（见 main_window 的分组兜底），不进「基础」筛选。
    """
    if not meta:
        return None
    season = meta.get("season")
    acq = meta.get("acq")
    if season is None:
        return "base" if acq == "base" else None
    if season == 0:
        return "base" if acq in (None, "", "base") else None
    return f"s{season}"


def season_display(meta: dict | None) -> str | None:
    """列表徽标用展示名：基础 / 常驻 / 第N赛季。"""
    if not meta:
        return None
    season = meta.get("season")
    acq = meta.get("acq")
    if acq == "base":
        return "基础" if season == 0 else "常驻"
    if season in (None, 0):
        return None  # 没有赛季归属（瓦夜/活动/通行证）→ 交给获取方式徽标
    return f"第{season}赛季"


def acq_display(meta: dict | None) -> str | None:
    """获取类型徽标（基础/赛季不显示，其余如 瓦夜/通行证/活动 显示）。"""
    if not meta:
        return None
    acq = meta.get("acq")
    if acq in (None, "base", "seasonal"):
        return None
    return ACQ_LABELS.get(acq, acq)


def kind_display(meta: dict | None) -> str | None:
    """敌方种类徽标：WAW 异想体 / N Corp.（势力）。"""
    if not meta:
        return None
    group = meta.get("group")
    label = meta.get("label") or ""
    if group == "abnormality":
        suffix = " 异想体" if label in _RISK_LEVELS else ""
        return f"{label}{suffix}"
    if group == "faction":
        return f"{label}（势力）"
    return label or None
