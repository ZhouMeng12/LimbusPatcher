"""文件与 JSON 基础工具：容忍 BOM 读取、原子写入、哈希。"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .categories import relpath_of


def load_json(path: Path) -> tuple[object | None, str | None]:
    """容忍 BOM 的 JSON 读取，返回 (对象, 错误信息)。"""
    try:
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "utf-8"):
            try:
                return json.loads(raw.decode(enc)), None
            except UnicodeDecodeError:
                continue
            except json.JSONDecodeError as e:
                return None, f"JSON 格式异常：{e.msg}（第 {e.lineno} 行）"
        return None, "文件编码无法识别"
    except OSError as e:
        return None, f"文件不可读：{e.strerror or e}"


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """同目录临时文件 + 原子替换。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def collect_rel_files(root: Path) -> dict[str, Path]:
    """递归收集 root 下所有文件，key 为 posix 相对路径。"""
    return {relpath_of(p, root): p for p in root.rglob("*") if p.is_file()}
