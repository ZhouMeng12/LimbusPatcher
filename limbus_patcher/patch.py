"""补丁数据模型：条目寻址、方案（profile）读写与校验、文本叶子遍历。

条目寻址 EntryRef = (file, id, record_index, field_path)
- file        相对零协包的 posix 路径，如 "BattleKeywords.json"
- id          dataList 记录的 id（int/str，按 JSON 原值比较）；
             记录没有 id 字段时（人格剧情等）为 None，此时定位完全依赖 record_index
- record_index 记录在 dataList 中的下标（无 id 时唯一的定位依据；重复 id 时用于消歧）
- field_path  记录内的叶子路径。段为 {"k": <key>} 或
              {"i": <下标>, "h": {k: v}}；列表段先按提示 h 匹配、再回退下标。
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .fsutil import atomic_write_text, sha256_text

FORMAT_VERSION = 1
_TEXT_LIKE_KEYS = {"content", "desc", "name", "dlg", "title", "summary", "flavor", "teller", "place", "model", "text", "value", "simpleDesc", "behaveDesc", "eventDesc", "successDesc", "failureDesc", "prevDesc", "subDesc", "nameWithTitle", "codeName", "clue", "usage", "nickName"}

FieldPath = list


def encode_fp(fp: FieldPath) -> str:
    return json.dumps(fp, ensure_ascii=False, separators=(",", ":"))


def decode_fp(s: str) -> FieldPath:
    return json.loads(s)


def _hint_for(item) -> dict | None:
    """为列表元素生成匹配提示：取第一个「非文本性质」的标量键值。"""
    if not isinstance(item, dict):
        return None
    for k, v in item.items():
        if isinstance(v, (int, float, str)) and k not in _TEXT_LIKE_KEYS:
            return {k: v}
    return None


def _resolve_list(cur: list, seg: dict) -> object:
    hint = seg.get("h")
    if hint:
        for x in cur:
            if isinstance(x, dict) and all(x.get(k) == v for k, v in hint.items()):
                return x
    i = seg.get("i", 0)
    if i >= len(cur):
        raise KeyError(f"列表段下标越界：{i} / {len(cur)}")
    return cur[i]


def _resolve_list_index(cur: list, seg: dict) -> int:
    hint = seg.get("h")
    if hint:
        for j, x in enumerate(cur):
            if isinstance(x, dict) and all(x.get(k) == v for k, v in hint.items()):
                return j
    i = seg.get("i", 0)
    if i >= len(cur):
        raise KeyError(f"列表段下标越界：{i} / {len(cur)}")
    return i


def get_value(data: object, fp: FieldPath) -> str:
    cur = data
    for seg in fp:
        if "k" in seg:
            if not isinstance(cur, dict):
                raise KeyError(f"路径段 {seg!r} 需要对象，实际为 {type(cur).__name__}")
            cur = cur[seg["k"]]
        else:
            if not isinstance(cur, list):
                raise KeyError(f"路径段 {seg!r} 需要数组，实际为 {type(cur).__name__}")
            cur = _resolve_list(cur, seg)
    if not isinstance(cur, str):
        raise KeyError(f"路径终点不是文本：{type(cur).__name__}")
    return cur


def set_value(data: object, fp: FieldPath, value: str) -> None:
    """沿路径写入叶子文本；要求路径终点为字符串。"""
    cur = data
    for idx, seg in enumerate(fp):
        last = idx == len(fp) - 1
        if "k" in seg:
            if not isinstance(cur, dict):
                raise KeyError(f"路径段 {seg!r} 需要对象，实际为 {type(cur).__name__}")
            if last:
                if not isinstance(cur.get(seg["k"]), str):
                    raise KeyError("路径终点不是文本")
                cur[seg["k"]] = value
                return
            cur = cur[seg["k"]]
        else:
            if not isinstance(cur, list):
                raise KeyError(f"路径段 {seg!r} 需要数组，实际为 {type(cur).__name__}")
            j = _resolve_list_index(cur, seg)
            if last:
                if not isinstance(cur[j], str):
                    raise KeyError("路径终点不是文本")
                cur[j] = value
                return
            cur = cur[j]


EXCLUDED_ROOT_KEYS = {"id", "model"}


#: 游戏枚举/条件数据（例："(800101, VERY_HIGH), (800102, VERY_HIGH)"），不是给人翻译的文本
_ENUM_VALUE_RE = re.compile(r"^(?:\(\s*-?\d+\s*,\s*[A-Za-z_][A-Za-z0-9_]*\s*\)\s*,?\s*)+$")


def is_data_value(text: str) -> bool:
    """该字符串是否明显是枚举/条件数据（不作为可编辑文本，也不进索引）。"""
    return bool(_ENUM_VALUE_RE.match((text or "").strip()))


def walk_leaves(data: object, prefix: FieldPath | None = None):
    """遍历 data 中的全部字符串叶子，产出 (field_path, text)。

    记录根级的 id / model 属于内部标识；形如 (800101, VERY_HIGH) 的枚举/条件值也跳过——
    它们是给程序读的，放进列表只会干扰（真实包里 12 个 AbDlg 文件共 169 处）。
    """
    prefix = prefix or []
    if isinstance(data, dict):
        for k, v in data.items():
            if not prefix and k in EXCLUDED_ROOT_KEYS:
                continue
            yield from walk_leaves(v, prefix + [{"k": k}])
    elif isinstance(data, list):
        for i, item in enumerate(data):
            seg = {"i": i, "h": _hint_for(item)}
            yield from walk_leaves(item, prefix + [seg])
    elif isinstance(data, str):
        if not is_data_value(data):
            yield prefix, data


@dataclass(frozen=True)
class EntryRef:
    file: str
    id: object
    record_index: int
    field_path: FieldPath

    def key(self) -> str:
        """唯一定位键。id 为 None（无 id 记录）时序列化成 null，
        但 record_index 始终在键里，所以键依旧唯一且可反序列化。"""
        return json.dumps(
            [self.file, self.id, self.record_index, self.field_path],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @classmethod
    def from_key(cls, key: str) -> "EntryRef":
        parts = json.loads(key)
        return cls(file=parts[0], id=parts[1], record_index=parts[2], field_path=parts[3])

    @classmethod
    def from_dict(cls, d: dict) -> "EntryRef":
        # id 允许缺失/为 null（老方案文件的 id 一定在；新格式无 id 记录写 null）
        return cls(
            file=str(d["file"]),
            id=d.get("id"),
            record_index=int(d.get("record_index", 0)),
            field_path=list(d.get("field_path", [])),
        )

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "id": self.id,
            "record_index": self.record_index,
            "field_path": self.field_path,
        }


def ref_label(ref: "EntryRef | None") -> str:
    """条目的显示键：有 id 用 id；无 id 记录用「记录 #N」，绝不显示 "None"。"""
    if ref is None:
        return "（无名称条目）"
    rid = ref.id
    if rid is None or (isinstance(rid, str) and not rid.strip()):
        return f"记录 #{ref.record_index}"
    return str(rid)


def record_title(record: dict, ref: "EntryRef | None" = None) -> str:
    """记录显示名：优先 name/teller/title，其次内容首句。

    都没命中时：给了 ref 就用 ref_label（无 id 记录显示「记录 #N」），
    否则退回「（无名称条目）」。
    """
    if isinstance(record, dict):
        for key in ("name", "teller", "title", "place"):
            v = record.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        for key in ("content", "desc", "dlg", "summary", "flavor"):
            v = record.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()[:60]
    return ref_label(ref) if ref is not None else "（无名称条目）"


@dataclass
class PatchEntry:
    ref: EntryRef
    original_hash: str
    value: str
    created_at: str = ""
    modified_at: str = ""
    favorite: bool = False

    def to_dict(self) -> dict:
        return {
            **self.ref.to_dict(),
            "original_hash": self.original_hash,
            "value": self.value,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "favorite": self.favorite,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PatchEntry":
        return cls(
            ref=EntryRef.from_dict(d),
            original_hash=str(d.get("original_hash", "")),
            value=str(d.get("value", "")),
            created_at=str(d.get("created_at", "")),
            modified_at=str(d.get("modified_at", "")),
            favorite=bool(d.get("favorite", False)),
        )


class ProfileError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class Profile:
    name: str = "默认方案"
    revision: int = 0
    entries: dict[str, PatchEntry] = field(default_factory=dict)
    # 部署/清空在工作线程执行，UI 线程可能同时增删条目 —— 全部读写走这把锁，
    # 遍历一律用 snapshot()/values() 的快照，避免
    # RuntimeError: dictionary changed size during iteration（见 tests/test_patch.py）。
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    # ---- 并发安全 ----

    def snapshot(self) -> dict[str, PatchEntry]:
        """条目字典的浅拷贝（跨线程遍历必须用这个）。"""
        with self._lock:
            return dict(self.entries)

    def values(self) -> list[PatchEntry]:
        """条目列表快照（跨线程遍历必须用这个）。"""
        with self._lock:
            return list(self.entries.values())

    def clear(self) -> int:
        """清空全部条目并递增修订号；返回清空前的条目数。"""
        with self._lock:
            n = len(self.entries)
            self.entries.clear()
            self.revision += 1
            return n

    def upsert(self, ref: EntryRef, value: str, original_text: str) -> PatchEntry | None:
        """新增或更新条目；value 与原文一致时视为删除，返回 None。"""
        with self._lock:
            return self._upsert_locked(ref, value, original_text)

    def _upsert_locked(self, ref: EntryRef, value: str, original_text: str) -> PatchEntry | None:
        now = _now()
        if value == original_text:
            self._remove_locked(ref)
            return None
        entry = self.entries.get(ref.key())
        if entry is not None and entry.value == value:
            return entry
        if entry is None:
            entry = PatchEntry(ref=ref, original_hash="", value=value, created_at=now, modified_at=now)
        else:
            entry.value = value
            entry.modified_at = now
        entry.original_hash = sha256_text(original_text)
        self.entries[ref.key()] = entry
        self.revision += 1
        return entry

    def remove(self, ref: EntryRef) -> bool:
        with self._lock:
            return self._remove_locked(ref)

    def _remove_locked(self, ref: EntryRef) -> bool:
        existed = self.entries.pop(ref.key(), None) is not None
        if existed:
            self.revision += 1
        return existed

    def get(self, ref: EntryRef) -> PatchEntry | None:
        with self._lock:
            return self.entries.get(ref.key())

    def files(self) -> set[str]:
        with self._lock:
            return {e.ref.file for e in self.entries.values()}

    def count(self) -> int:
        with self._lock:
            return len(self.entries)

    # ---- 序列化 / 校验 ----

    def to_obj(self) -> dict:
        with self._lock:
            return {
                "format_version": FORMAT_VERSION,
                "name": self.name,
                "revision": self.revision,
                "entries": [e.to_dict() for e in self.entries.values()],
            }

    @classmethod
    def validate_obj(cls, obj: object) -> list[str]:
        """结构校验，返回错误列表（空 = 通过）。"""
        errors: list[str] = []
        if not isinstance(obj, dict):
            return ["方案文件根节点必须是对象"]
        if obj.get("format_version") != FORMAT_VERSION:
            errors.append(f"不支持的方案格式版本：{obj.get('format_version')!r}")
        if not isinstance(obj.get("name"), str):
            errors.append("缺少方案名称")
        if not isinstance(obj.get("entries"), list):
            errors.append("entries 必须是数组")
            return errors
        for i, e in enumerate(obj["entries"]):
            if not isinstance(e, dict):
                errors.append(f"条目 #{i} 不是对象")
                continue
            if not isinstance(e.get("file"), str) or not e["file"]:
                errors.append(f"条目 #{i} 缺少 file")
            # id 可以缺失/为 null（无 id 记录），此时必须有 record_index 才定位得到
            if "id" not in e and "record_index" not in e:
                errors.append(f"条目 #{i} 缺少 id 与 record_index")
            if not isinstance(e.get("field_path"), list):
                errors.append(f"条目 #{i} 缺少 field_path")
            if not isinstance(e.get("value"), str):
                errors.append(f"条目 #{i} 的 value 必须是字符串")
        return errors

    @classmethod
    def from_obj(cls, obj: dict) -> "Profile":
        errors = cls.validate_obj(obj)
        if errors:
            raise ProfileError("；".join(errors))
        p = cls(name=obj.get("name") or "默认方案", revision=int(obj.get("revision") or 0))
        for e in obj.get("entries", []):
            entry = PatchEntry.from_dict(e)
            p.entries[entry.ref.key()] = entry
        return p

    def load(self, path: Path) -> None:
        try:
            raw = path.read_text(encoding="utf-8-sig")
            obj = json.loads(raw)
            loaded = Profile.from_obj(obj)
        except ProfileError:
            raise
        except json.JSONDecodeError as e:
            raise ProfileError(f"方案文件 JSON 格式异常：{e.msg}（第 {e.lineno} 行）") from e
        except OSError as e:
            raise ProfileError(f"方案文件不可读：{e}") from e
        with self._lock:
            self.name, self.revision, self.entries = loaded.name, loaded.revision, loaded.entries

    def save(self, path: Path, atomic: bool = True) -> None:
        """序列化 → 回读校验 → 原子落盘。禁止字符串拼接 JSON。"""
        payload = json.dumps(self.to_obj(), ensure_ascii=False, indent=2)
        json.loads(payload)  # 回读校验
        if atomic:
            atomic_write_text(path, payload)
        else:
            path.write_text(payload, encoding="utf-8", newline="\n")


def default_profile_path(profiles_dir: Path) -> Path:
    return profiles_dir / "default.json"
