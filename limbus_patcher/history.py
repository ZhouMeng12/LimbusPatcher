"""条目修改历史：history/ 下按条目 key 存 jsonl，保留最近 N 条。"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

KEEP = 20


class HistoryStore:
    def __init__(self, history_dir: Path, keep: int = KEEP):
        self.dir = history_dir
        self.keep = keep

    def _path(self, ref_key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in ref_key)
        if len(safe) > 120:
            safe = safe[:120]
        return self.dir / f"{safe}.jsonl"

    def record(self, ref_key: str, old_value: str | None, new_value: str) -> None:
        """追加一条历史：old_value=None 表示首次修改。"""
        self.dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime

        line = json.dumps(
            {"ts": datetime.now().isoformat(timespec="seconds"), "old": old_value, "new": new_value},
            ensure_ascii=False,
        )
        p = self._path(ref_key)
        lines = p.read_text(encoding="utf-8").splitlines() if p.is_file() else []
        lines = [l for l in lines if l.strip()]
        lines.append(line)
        lines = lines[-self.keep :]
        payload = "\n".join(lines) + "\n"
        fd, tmp = tempfile.mkstemp(prefix=".hist.", dir=str(self.dir))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(payload)
            os.replace(tmp, p)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def get(self, ref_key: str) -> list[dict]:
        p = self._path(ref_key)
        if not p.is_file():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(out))

    def clear(self, ref_key: str) -> None:
        try:
            self._path(ref_key).unlink()
        except OSError:
            pass
