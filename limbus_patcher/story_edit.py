"""剧本手动映射（应用内建立对应/标记跳过/删除行）与运行时数据合成。

- 覆盖表：<cache>/story_overrides.json
  {页面: {文本key: {"record": n} | {"skip": true} | {"deleted": true}}}
- 合成：把包内 story_stages.json 按覆盖表打补丁 → <cache>/story_stages.json（Storybook 优先加载）
- 删除（deleted）只是把该行标记为「不显示」，运行时数据里仍然保留（面板默认隐藏，
  勾选「显示已删除」可见并恢复）——零协包与包内数据都不会被改写。
"""
from __future__ import annotations

import json
from pathlib import Path

from .fsutil import atomic_write_text
from .season import package_data_dir
from .storybook import norm_text

# 自动建议对应的默认相似度阈值（0.85：只建议「几乎一字不差」的行）
DEFAULT_SUGGEST_THRESHOLD = 0.85


class StoryEdit:
    def __init__(self, cache_dir: Path, llc_dir: Path, supplement_dir: Path | None = None):
        self.cache_dir = Path(cache_dir)
        self.llc_dir = Path(llc_dir)
        self.supplement_dir = Path(supplement_dir) if supplement_dir else None
        self.overrides_path = self.cache_dir / "story_overrides.json"
        self.runtime_path = self.cache_dir / "story_stages.json"
        self.package_path = package_data_dir() / "story_stages.json"

    # ---- 覆盖表 ----

    def overrides(self) -> dict:
        if not self.overrides_path.is_file():
            return {}
        try:
            obj = json.loads(self.overrides_path.read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.overrides_path, json.dumps(data, ensure_ascii=False, indent=2))

    def set_record(self, page: str, key: str, record: int, note: str = "manual") -> None:
        data = self.overrides()
        data.setdefault(page, {})[key] = {"record": int(record), "certainty": "manual", "note": note}
        self._save(data)

    def mark_skip(self, page: str, key: str) -> None:
        data = self.overrides()
        data.setdefault(page, {})[key] = {"skip": True}
        self._save(data)

    def mark_deleted(self, page: str, key: str) -> None:
        """把该行标记为删除（剧本中不再显示；可用 clear() 还原）。"""
        data = self.overrides()
        data.setdefault(page, {})[key] = {"deleted": True}
        self._save(data)

    def mark_deleted_many(self, pairs) -> int:
        """批量删除多行（(page, key) 序列），一次落盘；返回写入条数。"""
        data = self.overrides()
        n = 0
        for page, key in pairs:
            if not page or not key:
                continue
            data.setdefault(page, {})[key] = {"deleted": True}
            n += 1
        if n:
            self._save(data)
        return n

    def deleted_count(self) -> int:
        return sum(1 for m in self.overrides().values() if isinstance(m, dict)
                   for rule in m.values() if isinstance(rule, dict) and rule.get("deleted"))

    def clear(self, page: str, key: str) -> None:
        data = self.overrides()
        if page in data and key in data[page]:
            data[page].pop(key)
            if not data[page]:
                data.pop(page)
            self._save(data)

    # ---- 候选与合成 ----

    def _read_pack_json(self, relfile: str) -> dict | None:
        """读取剧本数据文件：零协包优先，零协包无该文件时回退 supplement。"""
        try:
            p = self.llc_dir / relfile
            if not p.is_file() and self.supplement_dir is not None:
                p = self.supplement_dir / relfile
                if not p.is_file():
                    return None
            return json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return None

    def candidates(self, relfile: str, used: set[int]) -> list[dict]:
        """返回该文件可用（未被占用）的记录。"""
        d = self._read_pack_json(relfile)
        if d is None:
            return []
        out = []
        for i, r in enumerate(d.get("dataList", [])):
            if not isinstance(r, dict):
                continue
            content = r.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            out.append({
                "record": i,
                "teller": r.get("teller") if isinstance(r.get("teller"), str) else "",
                "content": content,
                "used": i in used,
            })
        return out

    # ---- 自动建议（按相似度把未对齐行配到零协记录） ----

    def suggest_matches(self, items: list[dict], used_by_page: dict | None = None,
                        threshold: float = DEFAULT_SUGGEST_THRESHOLD) -> list[dict]:
        """为一组未对齐行按文本相似度建议零协记录。

        - 只处理带 key/file/page 的未对齐行；
        - used_by_page：{page: 已占用记录下标集合}，缺省视为空；
        - 同一次建议内不会把同一条记录分配给两行；
        - 返回按相似度降序的 [{item, page, key, record, content, similarity}]，
          只保留相似度 ≥ threshold 的建议。
        """
        from difflib import SequenceMatcher

        used: dict[str, set[int]] = {}
        for page, records in (used_by_page or {}).items():
            used[page] = {int(r) for r in records if isinstance(r, int)}
        cand_cache: dict[str, list[dict]] = {}
        taken: dict[str, set[int]] = {}
        out: list[dict] = []

        for item in items or []:
            if not isinstance(item, dict) or item.get("type") != "line":
                continue
            page, key, relfile = item.get("page"), item.get("key"), item.get("file")
            if not page or not key or not relfile:
                continue
            if relfile not in cand_cache:
                cand_cache[relfile] = self.candidates(relfile, set())
            busy = used.get(page, set()) | taken.get(relfile, set())
            want = norm_text(item.get("text") or "")
            best: dict | None = None
            for cand in cand_cache[relfile]:
                if cand["record"] in busy or not str(cand.get("content") or "").strip():
                    continue
                ratio = SequenceMatcher(None, want, norm_text(cand["content"]), autojunk=False).ratio()
                if best is None or ratio > best["similarity"]:
                    best = {"record": cand["record"], "content": cand["content"], "similarity": ratio}
            if best is None or best["similarity"] < threshold:
                continue
            taken.setdefault(relfile, set()).add(best["record"])
            out.append({
                "item": item,
                "page": page,
                "key": key,
                "file": relfile,
                "text": item.get("text") or "",
                "record": best["record"],
                "content": best["content"],
                "similarity": best["similarity"],
            })
        out.sort(key=lambda s: s["similarity"], reverse=True)
        return out

    def apply_suggestions(self, suggestions: list[dict]) -> int:
        """把选中的建议写成手动对应（一次落盘；由调用方决定何时 rebuild）；返回写入条数。"""
        data = self.overrides()
        n = 0
        for s in suggestions or []:
            page, key, record = s.get("page"), s.get("key"), s.get("record")
            if not page or not key or not isinstance(record, int):
                continue
            note = "自动建议（相似度 " + str(round(float(s.get("similarity", 0)) * 100)) + "%）"
            data.setdefault(page, {})[key] = {"record": int(record), "certainty": "auto", "note": note}
            n += 1
        if n:
            self._save(data)
        return n

    def rebuild(self) -> int:
        """按覆盖表生成运行时 story_stages.json；返回应用条数。"""
        ov = self.overrides()
        if not ov or not self.package_path.is_file():
            try:
                self.runtime_path.unlink()
            except OSError:
                pass
            return 0
        data = json.loads(self.package_path.read_text(encoding="utf-8"))
        cache: dict[str, dict] = {}
        applied = 0

        def record_of(relfile: str, idx: int) -> dict | None:
            key = f"{relfile}#{idx}"
            if key not in cache:
                try:
                    d = json.loads((self.llc_dir / relfile).read_text(encoding="utf-8-sig"))
                    dl = d.get("dataList", [])
                    cache[key] = dl[idx] if 0 <= idx < len(dl) and isinstance(dl[idx], dict) else {}
                except (OSError, json.JSONDecodeError):
                    cache[key] = {}
            return cache[key] or None

        for chapter in data.get("chapters", []):
            for stage in chapter.get("stages", []):
                for item in stage.get("items", []):
                    if item.get("type") != "line":
                        continue
                    page = item.get("page")
                    key = item.get("key")
                    if not page or not key:
                        continue
                    rule = (ov.get(page) or {}).get(key)
                    if not rule:
                        item.pop("deleted", None)
                        continue
                    if rule.get("deleted"):
                        # 删除：标记后仍留在运行时数据里（面板默认隐藏，便于恢复）
                        item["deleted"] = True
                        item["wiki_only"] = True
                        item.pop("manual", None)
                        applied += 1
                        continue
                    item.pop("deleted", None)
                    if rule.get("skip"):
                        item["skip"] = True
                        applied += 1
                        continue
                    rec_idx = rule.get("record")
                    if not isinstance(rec_idx, int):
                        continue
                    rec = record_of(item.get("file", ""), rec_idx)
                    if rec is None:
                        continue
                    content = rec.get("content")
                    item["record"] = rec_idx
                    item["wiki_only"] = False
                    item.pop("skip", None)
                    item["text"] = content if isinstance(content, str) else item.get("text", "")
                    teller = rec.get("teller")
                    if isinstance(teller, str) and teller.strip():
                        item["speaker"] = teller.strip()
                    item["manual"] = True
                    applied += 1
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.runtime_path, json.dumps(data, ensure_ascii=False))
        return applied
