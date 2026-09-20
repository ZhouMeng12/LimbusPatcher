"""文本来源：应用里只存「位置」，文本现从语言文件取。

存的永远是**零协包内的相对路径 + 记录下标 + 字段路径**（索引里的 EntryRef、
剧本 items 里的 ``file/record/text_index/field``）；文本本身不落库、不随包分发。
读的时候按当前环境选来源：

- 装了零协汉化（``Lang/LLC_zh-CN``）→ 直接读它；
- 没装 → 读游戏自带的英文基线（``Assets/Resources_moved/Localize/en/EN_*.json``），
  位置一一对应（同一个相对路径，文件名多一个 ``EN_`` 前缀）。

这样同一份剧本结构与索引可以配任意来源：换来源不用重建数据，玩家没装零协也能用
（看到的是英文原文 + 自己的译文）。文本一律**零协/游戏原始文件为准**，本工具不改它们。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["TextSource", "read_record_text"]

#: 记录里可能承载文本的字段（按优先级）
TEXT_FIELDS = ("content", "text", "dlg", "desc", "summary")


@dataclass
class TextSource:
    #: "llc" = 零协汉化；"en" = 英文基线；"none" = 都不可用
    mode: str = "none"
    root: Path | None = None
    #: 文件名前缀（英文基线为 "EN_"）
    prefix: str = ""
    _cache: dict = field(default_factory=dict, repr=False)

    # ---------- 构造 ----------

    @classmethod
    def detect(cls, llc_dir: Path | str | None, base_dir: Path | str | None) -> "TextSource":
        """零协优先；没有零协就用英文基线；都没有则 none。"""
        if llc_dir:
            p = Path(llc_dir)
            if p.is_dir():
                return cls(mode="llc", root=p, prefix="")
        if base_dir:
            p = Path(base_dir)
            if p.is_dir():
                return cls(mode="en", root=p, prefix="EN_")
        return cls(mode="none", root=None, prefix="")

    # ---------- 基本信息 ----------

    @property
    def ok(self) -> bool:
        return self.mode != "none" and self.root is not None

    @property
    def label(self) -> str:
        return {"llc": "零协汉化（LLC_zh-CN）", "en": "英文原文（游戏基线）"}.get(self.mode, "（无文本来源）")

    def file_path(self, rel: str) -> Path | None:
        """零协相对路径 → 当前来源下的实际文件路径。"""
        if not self.ok or not rel:
            return None
        p = Path(rel)
        name = f"{self.prefix}{p.name}" if self.prefix else p.name
        return Path(self.root) / p.parent / name  # type: ignore[arg-type]

    # ---------- 读取 ----------

    def data_list(self, rel: str) -> list | None:
        """读取该文件的 dataList（按来源缓存；读不到返回 None）。"""
        if not self.ok or not rel:
            return None
        key = (self.mode, rel)
        if key in self._cache:
            return self._cache[key]
        data = None
        path = self.file_path(rel)
        if path is not None and path.is_file():
            try:
                obj = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                obj = None
            if isinstance(obj, dict) and isinstance(obj.get("dataList"), list):
                data = obj["dataList"]
        self._cache[key] = data
        return data

    def record(self, rel: str, record_index: int) -> dict | None:
        dl = self.data_list(rel)
        if not dl or not (0 <= int(record_index) < len(dl)):
            return None
        rec = dl[int(record_index)]
        return rec if isinstance(rec, dict) else None

    def resolve(self, rel: str, record_index: int, text_index: int | None = None,
                field_name: str | None = None) -> tuple[str | None, str | None, str | None]:
        """取某条文本：返回 (文本, 说话人, 小标题)。"""
        rec = self.record(rel, record_index)
        if rec is None:
            return None, None, None
        text, speaker, title = read_record_text(rec, text_index, field_name)
        return text, speaker, title

    def resolve_item(self, item: dict) -> dict:
        """给剧本 / 列表条目补上文本（只在缺文本时读文件）。"""
        if item.get("type") == "scene" or item.get("wiki_only"):
            return item
        rel, rec = item.get("file"), item.get("record")
        if not rel or rec is None:
            return item
        text, speaker, title = self.resolve(rel, int(rec), item.get("text_index"), item.get("field"))
        if text is None:
            return item
        out = dict(item)
        out["text"] = text
        if speaker is not None:
            out["speaker"] = speaker
        elif out.get("speaker") is None:
            out["speaker"] = None
        if title is not None:
            out["title"] = title
        return out

    def resolve_items(self, items: list[dict]) -> list[dict]:
        return [self.resolve_item(i) for i in items]

    def clear_cache(self) -> None:
        self._cache.clear()


def read_record_text(rec: dict, text_index: int | None = None,
                     field_name: str | None = None) -> tuple[str | None, str | None, str | None]:
    """从一条记录里取文本 (文本, 说话人, 小标题)。

    ``text_index`` 给了就读 ``texts[i]``；``field_name`` 给了就读该字段；
    都没给时按 content / text / dlg 依次找（老数据的条目没记 field）。
    """
    if text_index is not None:
        texts = rec.get("texts")
        if isinstance(texts, list):
            for pos, t in enumerate(texts):
                if not isinstance(t, dict):
                    continue
                idx = t.get("index")
                idx = idx if isinstance(idx, int) else pos
                if idx == int(text_index):
                    return t.get("text"), t.get("speaker"), None
        return None, None, None
    if field_name:
        value = rec.get(field_name)
        if isinstance(value, str) and value.strip():
            return value, rec.get("teller") or rec.get("speaker"), rec.get("title")
        if field_name == "texts":
            texts = rec.get("texts")
            if isinstance(texts, list) and texts and isinstance(texts[0], dict):
                return texts[0].get("text"), texts[0].get("speaker"), None
        return None, None, None
    for key in TEXT_FIELDS:
        value = rec.get(key)
        if isinstance(value, str) and value.strip():
            return value, rec.get("teller") or rec.get("speaker"), rec.get("title")
    texts = rec.get("texts")
    if isinstance(texts, list) and texts and isinstance(texts[0], dict):
        return texts[0].get("text"), texts[0].get("speaker"), None
    return None, None, None
