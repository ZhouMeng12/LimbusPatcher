"""备份管理：启动与关键写入前备份 data/（zip），保留最近 N 份，支持恢复。"""
from __future__ import annotations

import json
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_KEEP = 10
# 备份包含的条目（cache 下的 sqlite 索引可重建，不备份）
BACKUP_PARTS = ("config.json", "profiles", "history", "cache/manifest.json", "cache/applied_manifest.json")


@dataclass
class BackupInfo:
    path: Path
    reason: str
    at: str


class BackupManager:
    def __init__(self, app_paths, keep: int = DEFAULT_KEEP):
        self.data_dir = app_paths.data_dir
        self.backups_dir = app_paths.backups_dir
        self.keep = keep

    def backup(self, reason: str) -> Path | None:
        """打包 data/ 关键内容为 zip；失败返回 None（调用方自行降级提示）。"""
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)
        dest = self.backups_dir / f"backup_{stamp}_{os.getpid()}_{safe}.zip"
        try:
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("backup_meta.json", json.dumps({"reason": reason, "at": stamp}, ensure_ascii=False))
                for part in BACKUP_PARTS:
                    p = self.data_dir / part
                    if p.is_file():
                        zf.write(p, arcname=part)
                    elif p.is_dir():
                        for f in p.rglob("*"):
                            if f.is_file():
                                zf.write(f, arcname=f.relative_to(self.data_dir).as_posix())
        except OSError:
            try:
                dest.unlink()
            except OSError:
                pass
            return None
        self.rotate()
        return dest

    def list(self) -> list[BackupInfo]:
        if not self.backups_dir.is_dir():
            return []
        out: list[BackupInfo] = []
        for p in sorted(self.backups_dir.glob("backup_*.zip"), reverse=True):
            try:
                with zipfile.ZipFile(p) as zf:
                    meta = json.loads(zf.read("backup_meta.json").decode("utf-8"))
                out.append(BackupInfo(path=p, reason=str(meta.get("reason", "")), at=str(meta.get("at", ""))))
            except Exception:
                out.append(BackupInfo(path=p, reason="（无法识别）", at=""))
        return out

    def rotate(self) -> None:
        infos = sorted(self.backups_dir.glob("backup_*.zip"), key=lambda p: p.stat().st_mtime)
        for old in infos[: -self.keep]:
            try:
                old.unlink()
            except OSError:
                pass

    def restore(self, backup_path: Path) -> list[str]:
        """恢复备份：校验 zip → 解到临时目录 → 校验关键 JSON → 覆盖回 data/。返回恢复的文件列表。"""
        errors: list[str] = []
        names: list[str] = []
        with zipfile.ZipFile(backup_path) as zf:
            infos = zf.infolist()
            total = sum(i.file_size for i in infos)
            if total > 200 * 1024 * 1024:
                raise ValueError("备份包异常过大，已拒绝恢复")
            for i in infos:
                if i.filename.startswith("..") or i.filename.startswith("/"):
                    raise ValueError("备份包包含非法路径")
            tmp = self.data_dir.parent / f".restore_tmp_{datetime.now():%Y%m%d_%H%M%S_%f}"
            try:
                zf.extractall(tmp)
                # 校验关键 JSON 可解析
                for name in ("config.json", "profiles/default.json", "cache/applied_manifest.json"):
                    p = tmp / name
                    if p.is_file():
                        json.loads(p.read_text(encoding="utf-8-sig"))
                for part in ("config.json", "profiles", "history", "cache"):
                    src = tmp / part
                    if not src.exists():
                        continue
                    dst = self.data_dir / part
                    if src.is_dir():
                        if dst.is_dir():
                            shutil.rmtree(dst)
                        shutil.copytree(src, dst)
                    else:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                    names.append(part)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        return names
