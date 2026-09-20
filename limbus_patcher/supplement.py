"""补译文件（零协包里没有、由本工具生成的文件，例如新章节剧情）。

为什么需要：零协更新前，新章节（如第十章）在零协包里**根本不存在对应文件**，
游戏会回退到英文。补译文件让这类「我们自己译好的文件」也能随补丁一起进游戏：

    <应用数据目录>/supplement/<零协包内的相对路径>      例：supplement/StoryData/S1000B.json
    <应用数据目录>/supplement/manifest.json              启用状态 + 说明

规则（安全第一）：
- 只接受「能解析、且有 dataList 列表」的 JSON，坏文件一律拒绝导入；
- 停用/移除后，下次「应用到游戏」会把它从副本包里删掉（副本包不需要它）；
- 零协包里的同名文件**永远优先**：补译文件不会覆盖零协已有文件（避免把官方译文顶掉）。
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SUPPLEMENT_DIR_NAME = "supplement"
MANIFEST_NAME = "manifest.json"
FORMAT_VERSION = 1


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class SupplementFile:
    rel: str                 # 相对零协包的 posix 路径，如 StoryData/S1000B.json
    path: Path               # 实际文件
    enabled: bool = True
    note: str = ""
    added_at: str = ""

    @property
    def size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    @property
    def records(self) -> int:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
            dl = data.get("dataList") if isinstance(data, dict) else None
            return len(dl) if isinstance(dl, list) else 0
        except (OSError, json.JSONDecodeError):
            return 0


def validate_json_file(path: Path) -> tuple[bool, str]:
    """补译文件必须是可解析的本地化 JSON（dict + dataList 列表）。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except OSError as exc:
        return False, f"读不到文件：{exc}"
    except json.JSONDecodeError as exc:
        return False, f"JSON 解析失败：{exc}"
    if not isinstance(data, dict):
        return False, "顶层不是对象"
    if not isinstance(data.get("dataList"), list):
        return False, "缺少 dataList 列表"
    return True, ""


class SupplementPack:
    """补译文件集合（磁盘上的 supplement/ 目录 + manifest）。"""

    def __init__(self, data_dir: Path):
        self.root = Path(data_dir) / SUPPLEMENT_DIR_NAME
        self.manifest_path = self.root / MANIFEST_NAME

    # ---- manifest ----

    def _load(self) -> dict:
        if not self.manifest_path.is_file():
            return {"format_version": FORMAT_VERSION, "files": {}}
        try:
            obj = json.loads(self.manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {"format_version": FORMAT_VERSION, "files": {}}
        if not isinstance(obj, dict) or not isinstance(obj.get("files"), dict):
            return {"format_version": FORMAT_VERSION, "files": {}}
        obj.setdefault("format_version", FORMAT_VERSION)
        return obj

    def _save(self, obj: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")

    # ---- 查询 ----

    def files(self) -> list[SupplementFile]:
        obj = self._load()
        out: list[SupplementFile] = []
        for rel, meta in sorted((obj.get("files") or {}).items()):
            meta = meta if isinstance(meta, dict) else {}
            path = self.root / rel
            if path.is_file():
                out.append(SupplementFile(rel=rel, path=path,
                                          enabled=bool(meta.get("enabled", True)),
                                          note=str(meta.get("note") or ""),
                                          added_at=str(meta.get("added_at") or "")))
        return out

    def count(self) -> tuple[int, int]:
        """(总数, 已启用数)。"""
        files = self.files()
        return len(files), sum(1 for f in files if f.enabled)

    def enabled_map(self) -> dict[str, Path]:
        return {f.rel: f.path for f in self.files() if f.enabled}

    def note_of(self, rel: str) -> str:
        meta = (self._load().get("files") or {}).get(rel) or {}
        return str(meta.get("note") or "") if isinstance(meta, dict) else ""

    # ---- 增删改 ----

    def add(self, rel: str, source: Path, note: str = "", enabled: bool = True) -> tuple[bool, str]:
        """导入一个文件；rel 是它在零协包里的相对路径（如 StoryData/S1000B.json）。"""
        rel = str(rel).replace("\\", "/").lstrip("/")
        if not rel or ".." in rel.split("/"):
            return False, f"路径不合法：{rel}"
        ok, err = validate_json_file(Path(source))
        if not ok:
            return False, f"{rel}: {err}"
        dst = self.root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dst)
        obj = self._load()
        obj["files"][rel] = {"enabled": bool(enabled), "note": note, "added_at": _now()}
        self._save(obj)
        return True, f"已导入 {rel}"

    def remove(self, rel: str) -> bool:
        rel = str(rel).replace("\\", "/")
        obj = self._load()
        existed = rel in (obj.get("files") or {})
        obj.get("files", {}).pop(rel, None)
        self._save(obj)
        path = self.root / rel
        if path.is_file():
            path.unlink()
        return existed

    def set_enabled(self, rel: str, enabled: bool) -> bool:
        obj = self._load()
        meta = (obj.get("files") or {}).get(rel)
        if not isinstance(meta, dict):
            return False
        meta["enabled"] = bool(enabled)
        self._save(obj)
        return True

    def set_all_enabled(self, enabled: bool) -> int:
        obj = self._load()
        n = 0
        for meta in (obj.get("files") or {}).values():
            if isinstance(meta, dict):
                meta["enabled"] = bool(enabled)
                n += 1
        self._save(obj)
        return n

    def summary(self) -> str:
        total, on = self.count()
        if not total:
            return "无补译文件"
        return f"补译文件 {on}/{total} 已启用"
