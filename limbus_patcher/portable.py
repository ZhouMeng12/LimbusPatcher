"""便携包导入导出：把方案 + 剧本手动对应 + 备份打成一个 zip，方便换机器/重装迁移。

包结构（portable_v1）：
  manifest.json        版本、导出时间、条目数、方案名（回读校验用）
  profile.json         方案（Profile.to_obj 的结构）
  story_overrides.json 剧本手动对应/跳过/删除（可缺省）
  backups/*.zip        备份（可选，默认不含）

导入一律**不改动**零协包：只写 data/profiles 与 data/cache，并在覆盖前备份现有方案。
"""
from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .fsutil import atomic_write_text
from .patch import Profile, ProfileError

PACK_FORMAT = 1
MANIFEST_NAME = "manifest.json"
PROFILE_NAME = "profile.json"
OVERRIDES_NAME = "story_overrides.json"
BACKUP_DIR = "backups"


class PortableError(Exception):
    """导入导出失败（消息面向用户，中文）。"""


@dataclass
class ExportResult:
    path: Path
    entries: int = 0
    story_rules: int = 0
    backups: int = 0


@dataclass
class ImportResult:
    profile_name: str = ""
    entries: int = 0
    story_rules: int = 0
    backups: int = 0
    profile_path: Path | None = None
    notes: list[str] = field(default_factory=list)


def _count_rules(obj: dict) -> int:
    return sum(len(page) for page in obj.values() if isinstance(page, dict))


def export_pack(dest: Path, profile: Profile, overrides: dict | None = None,
                backups_dir: Path | None = None, with_backups: bool = False) -> ExportResult:
    """导出便携包；返回统计。任何异常都抛 PortableError（中文消息）。"""
    dest = Path(dest)
    if dest.suffix.lower() != ".zip":
        dest = dest.with_suffix(".zip")
    overrides = overrides or {}
    backup_files: list[Path] = []
    if with_backups and backups_dir is not None and Path(backups_dir).is_dir():
        backup_files = sorted(Path(backups_dir).glob("backup_*.zip"), reverse=True)[:5]

    manifest = {
        "format_version": PACK_FORMAT,
        "kind": "limbus_patcher_portable",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "profile_name": profile.name,
        "entries": profile.count(),
        "story_rules": _count_rules(overrides),
        "with_backups": bool(backup_files),
    }
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr(PROFILE_NAME, json.dumps(profile.to_obj(), ensure_ascii=False, indent=2))
            if overrides:
                zf.writestr(OVERRIDES_NAME, json.dumps(overrides, ensure_ascii=False, indent=2))
            for src in backup_files:
                zf.write(src, arcname=f"{BACKUP_DIR}/{src.name}")
    except OSError as exc:
        raise PortableError(f"无法写入 {dest}：{exc}") from exc
    return ExportResult(path=dest, entries=profile.count(),
                        story_rules=_count_rules(overrides), backups=len(backup_files))


def peek_pack(src: Path) -> dict:
    """读取便携包的 manifest（不落盘，用于导入前确认）。"""
    src = Path(src)
    try:
        with zipfile.ZipFile(src) as zf:
            with zf.open(MANIFEST_NAME) as fh:
                obj = json.loads(fh.read().decode("utf-8"))
    except KeyError as exc:
        raise PortableError("这不是修改器导出的方案包（缺少 manifest.json）。") from exc
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise PortableError(f"无法读取方案包：{exc}") from exc
    if not isinstance(obj, dict) or obj.get("kind") != "limbus_patcher_portable":
        raise PortableError("方案包类型不匹配（不是本工具导出的文件）。")
    if int(obj.get("format_version") or 0) > PACK_FORMAT:
        raise PortableError("方案包版本比当前程序新，请先更新修改器。")
    return obj


def import_pack(src: Path, profiles_dir: Path, cache_dir: Path,
                restore_backups_dir: Path | None = None,
                profile_name: str | None = None,
                target: Path | None = None) -> ImportResult:
    """导入便携包：写方案 + 剧本覆盖表（覆盖前自动备份现有方案）。

    ``target`` 指定方案落盘路径（应用内导入用当前方案文件，导入后即为当前方案）；
    缺省按包内方案名生成文件名。
    """
    src = Path(src)
    manifest = peek_pack(src)
    profiles_dir = Path(profiles_dir)
    cache_dir = Path(cache_dir)
    result = ImportResult(profile_name=str(manifest.get("profile_name") or "默认方案"))

    try:
        with zipfile.ZipFile(src) as zf:
            names = set(zf.namelist())
            if PROFILE_NAME not in names:
                raise PortableError("方案包里缺少 profile.json。")
            raw = zf.read(PROFILE_NAME).decode("utf-8-sig")
            obj = json.loads(raw)
            profile = Profile.from_obj(obj)  # 结构校验（非法直接抛错）
            overrides = {}
            if OVERRIDES_NAME in names:
                overrides = json.loads(zf.read(OVERRIDES_NAME).decode("utf-8-sig"))
            backup_names = [n for n in names if n.startswith(BACKUP_DIR + "/") and n.endswith(".zip")]
            blobs = [(n, zf.read(n)) for n in backup_names]
    except ProfileError as exc:
        raise PortableError(f"方案内容不合法：{exc}") from exc
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PortableError(f"无法读取方案包：{exc}") from exc

    name = (profile_name or profile.name or "默认方案").strip() or "默认方案"
    profile.name = name
    profiles_dir.mkdir(parents=True, exist_ok=True)
    dest = Path(target) if target is not None else profiles_dir / f"{_safe_name(name)}.json"
    if dest.is_file():  # 覆盖前留一份 .bak，误导入可手工还原
        try:
            dest.replace(dest.with_suffix(".json.bak"))
            result.notes.append(f"原有方案已备份为 {dest.name}.bak")
        except OSError:
            pass
    try:
        atomic_write_text(dest, json.dumps(profile.to_obj(), ensure_ascii=False, indent=2))
    except OSError as exc:
        raise PortableError(f"无法写入方案文件：{exc}") from exc
    result.profile_path = dest
    result.entries = profile.count()

    if overrides:
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / OVERRIDES_NAME
        if target.is_file():
            try:
                existing = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
            if isinstance(existing, dict):
                merged = _merge_overrides(existing, overrides)
                result.notes.append(
                    f"剧本对应已与现有 {_count_rules(existing)} 条合并"
                    f"（本次导入 {_count_rules(overrides)} 条）"
                )
                overrides = merged
        atomic_write_text(target, json.dumps(overrides, ensure_ascii=False, indent=2))
        result.story_rules = _count_rules(overrides)

    if blobs and restore_backups_dir is not None:
        out = Path(restore_backups_dir)
        out.mkdir(parents=True, exist_ok=True)
        for arcname, blob in blobs:
            (out / Path(arcname).name).write_bytes(blob)
        result.backups = len(blobs)
    return result


def _merge_overrides(base: dict, incoming: dict) -> dict:
    """合并剧本覆盖表：以导入的规则为准（同 key 覆盖），其余保留。"""
    out = {page: dict(rules) for page, rules in base.items() if isinstance(rules, dict)}
    for page, rules in incoming.items():
        if not isinstance(rules, dict):
            continue
        out.setdefault(page, {}).update(rules)
    return out


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
    return cleaned or "default"
