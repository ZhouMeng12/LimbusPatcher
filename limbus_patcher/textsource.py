"""文本来源：应用里只存「位置」，文本现从语言文件取。

存的永远是**零协包内的相对路径 + 记录下标 + 字段路径**（索引里的 EntryRef、
剧本 items 里的 ``file/record/text_index/field``）；文本本身不落库、不随包分发。
读的时候按当前环境选来源：

- 装了零协汉化（``Lang/LLC_zh-CN``）→ 直接读它；
- 没装 → 读游戏自带的英文基线（``Assets/Resources_moved/Localize/en/EN_*.json``），
  位置一一对应（同一个相对路径，文件名多一个 ``EN_`` 前缀）；
- 该文件在当前来源里不存在（新章节零协还没跟，如 c10p2）→ 回退补译目录
  ``data/supplement``（相对路径一致），这样不点「应用到游戏」也能看到自己的译文。

这样同一份剧本结构与索引可以配任意来源：换来源不用重建数据，玩家没装零协也能用
（看到的是英文原文 + 自己的译文）。文本一律**零协/游戏原始文件为准**，本工具不改它们。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["TextSource", "read_record_text", "load_model_names",
           "set_game_dirs", "model_name_of", "speaker_of"]

#: 记录里可能承载文本的字段（按优先级）
TEXT_FIELDS = ("content", "text", "dlg", "desc", "summary")

#: 角色键对照表（韩文 model 键 → 显示名）。零协包里是中文名，英文基线是英文名。
CODES_FILE = "ScenarioModelCodes-AutoCreated.json"
#: 本工具自带的补充表文件名，只登记零协对照表里查不到的键（新章节角色）。
#: 放在包内置 data 目录（打包后在 exe 内），与其它 ``*.json`` 同款加载方式。
OVERRIDE_NAME = "scenario_model_names.json"


def _read_codes_file(path: Path) -> dict[str, str]:
    """读角色键对照表：{model 键: 显示名}。读不到或结构不符返回空表。"""
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    for rec in (obj.get("dataList") if isinstance(obj, dict) else None) or []:
        if not isinstance(rec, dict):
            continue
        key = rec.get("id")
        name = rec.get("name")
        if isinstance(key, str) and key and isinstance(name, str) and name.strip():
            out[key] = name.strip()
    return out


def _load_override() -> dict[str, str]:
    """本工具自带的补充表（去掉 ``_`` 开头的说明键）。"""
    from .season import package_data_dir

    try:
        obj = json.loads((package_data_dir() / OVERRIDE_NAME).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, ImportError):
        return {}
    if not isinstance(obj, dict):
        return {}
    return {k: v for k, v in obj.items()
            if not k.startswith("_") and isinstance(v, str) and v.strip()}


def load_model_names(codes_dirs) -> dict[str, str]:
    """拼出 ``model`` 键 → 显示名的对照表。

    优先级（低 → 高，逐层覆盖）：英文基线（英文名）→ 本工具补充表（中文）→
    零协对照表（中文，最权威）。``codes_dirs`` 按优先级从高到低给目录，
    每个目录里找 ``ScenarioModelCodes-AutoCreated.json`` 或 ``EN_`` 前缀版。
    """
    dirs = [Path(d) for d in (codes_dirs or []) if d]
    out: dict[str, str] = {}
    for d in reversed(dirs):                      # 低优先级先装
        for name in (CODES_FILE, f"EN_{CODES_FILE}"):
            if (d / name).is_file():
                out.update(_read_codes_file(d / name))
                break
    out.update(_load_override())
    if dirs:                                      # 零协（最高优先级）最后覆盖
        for name in (CODES_FILE, f"EN_{CODES_FILE}"):
            if (dirs[0] / name).is_file():
                out.update(_read_codes_file(dirs[0] / name))
                break
    return out


# ---------------------------------------------------------------- 全局便捷入口
# 图鉴 / 主线剧情预览这类显示路径拿不到 TextSource，用下面这套：
# 应用启动时 set_game_dirs() 登记游戏侧目录，之后 model_name_of() 就能查名字。
_GAME_DIRS: tuple[str, ...] = ()
_GLOBAL_NAMES: dict[str, str] | None = None


def set_game_dirs(llc_dir=None, base_dir=None) -> None:
    """登记游戏侧目录（优先级从高到低：零协 → 英文基线），供全局查角色名。

    目录没变就不重建表。应用启动 / 切游戏目录时调一次即可。
    """
    global _GAME_DIRS, _GLOBAL_NAMES
    new = tuple(str(Path(d)) for d in (llc_dir, base_dir) if d)
    if new != _GAME_DIRS:
        _GAME_DIRS = new
        _GLOBAL_NAMES = None


def global_model_names() -> dict[str, str]:
    """全局对照表（惰性构建；没登记目录时只剩本工具自带的补充表）。"""
    global _GLOBAL_NAMES
    if _GLOBAL_NAMES is None:
        _GLOBAL_NAMES = load_model_names(_GAME_DIRS)
    return _GLOBAL_NAMES


def model_name_of(model, codes_dirs=None) -> str | None:
    """``model`` 角色键（韩文）→ 显示名；查不到返回 None。"""
    if not isinstance(model, str) or not model.strip():
        return None
    table = load_model_names(codes_dirs) if codes_dirs else global_model_names()
    return table.get(model.strip())


def speaker_of(rec: dict, codes_dirs=None) -> str | None:
    """记录 → 说话人显示名：``teller`` / ``speaker`` 优先，其次按 ``model`` 反查。

    过场文件（c10p2 起）不填 ``teller``，名字只在 ``model`` 里，这里统一兜底。
    """
    got = rec.get("teller") or rec.get("speaker")
    if isinstance(got, str) and got.strip():
        return got.strip()
    return model_name_of(rec.get("model"), codes_dirs)


#: 记录标识字段的优先级（老文件用 id，RPG/UI 这类用 key，少数用 code）
RECORD_ID_KEYS = ("id", "key", "code")


def record_id_of(rec) -> str | None:
    """记录的唯一标识（id/key/code）；拿不到返回 None。"""
    if not isinstance(rec, dict):
        return None
    for k in RECORD_ID_KEYS:
        v = rec.get(k)
        if v is not None and str(v).strip():
            return str(v)
    return None


def merge_records(primary: list, extra: list) -> list:
    """零协优先的合并：主来源记录全留，只追加主来源没有（按 id/key/code）的记录。

    与部署器 ``Deployer._merge_records`` 同一套规则，保证「软件里看到的」和
    「部署到游戏里的」是同一份内容。
    """
    out = list(primary)
    have = {k for k in (record_id_of(r) for r in primary) if k}
    appended = 0
    for r in extra:
        if not isinstance(r, dict):
            continue
        k = record_id_of(r)
        if k is None or k in have:
            continue
        out.append(r)
        have.add(k)
        appended += 1
    return out if appended else primary


@dataclass
class TextSource:
    #: "llc" = 零协汉化；"en" = 英文基线；"none" = 都不可用
    mode: str = "none"
    root: Path | None = None
    #: 文件名前缀（英文基线为 "EN_"）
    prefix: str = ""
    #: 回退目录：当前来源缺该文件时从这里读（补译目录，结构同零协）
    fallback_root: Path | None = None
    #: 找角色键对照表的目录（按优先级从高到低；用于补说话人）
    codes_dirs: tuple = ()
    _cache: dict = field(default_factory=dict, repr=False)
    _model_names: dict | None = field(default=None, repr=False)

    # ---------- 构造 ----------

    @classmethod
    def detect(cls, llc_dir: Path | str | None, base_dir: Path | str | None,
               supplement_dir: Path | str | None = None,
               codes_dirs=None) -> "TextSource":
        """零协优先；没有零协就用英文基线；都没有则 none。

        ``supplement_dir`` 给的话，主来源里读不到的文件会回退到补译目录
        （新章节零协没跟时，剧本模式照样能显示自己的译文）。

        ``codes_dirs`` 是找角色键对照表（``ScenarioModelCodes-AutoCreated.json``）
        的目录，优先级从高到低；不给就按「零协 → 英文基线」推。
        """
        fb = Path(supplement_dir) if supplement_dir else None
        if fb is not None and not fb.is_dir():
            fb = None
        if codes_dirs is None:
            codes_dirs = [d for d in (llc_dir, base_dir) if d]
        codes = tuple(str(Path(d)) for d in codes_dirs if d)
        if llc_dir:
            p = Path(llc_dir)
            if p.is_dir():
                return cls(mode="llc", root=p, prefix="", fallback_root=fb, codes_dirs=codes)
        if base_dir:
            p = Path(base_dir)
            if p.is_dir():
                return cls(mode="en", root=p, prefix="EN_", fallback_root=fb, codes_dirs=codes)
        return cls(mode="none", root=None, prefix="", fallback_root=fb, codes_dirs=codes)

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

    def _read_data_list(self, path: Path | None) -> list | None:
        if path is None or not path.is_file():
            return None
        try:
            obj = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(obj, dict) and isinstance(obj.get("dataList"), list):
            return obj["dataList"]
        return None

    def data_list(self, rel: str) -> list | None:
        """读取该文件的 dataList（按来源缓存；读不到返回 None）。

        主来源（零协 / 英文基线）里没有该文件时，回退补译目录；**两边都有**时按
        部署器的同一套规则合并（零协优先，只追加零协缺的记录）——否则剧本数据里
        那些只有我们有的记录（如 wiki 独有、官方 Localize 已删的未使用台词）
        在运行时根本读不到，条目会退化成空行或错位。
        """
        if not self.ok or not rel:
            return None
        key = (self.mode, rel, bool(self.fallback_root))
        if key in self._cache:
            return self._cache[key]
        data = self._read_data_list(self.file_path(rel))
        extra = (self._read_data_list(Path(self.fallback_root) / rel)
                 if self.fallback_root is not None else None)
        if data is None:
            data = extra
        elif extra:
            data = merge_records(data, extra)
        self._cache[key] = data
        return data

    def record(self, rel: str, record_index: int | None, key=None) -> dict | None:
        """定位一条记录：给了 ``key``（id/key/code）就按键找，找不到再退回下标。

        键优先是必须的：补译文件的记录顺序跟零协包不一定一致（我们多出的记录会
        把后面的整体顶位），只按下标读会张冠李戴。记录下标来自剧本/索引数据，
        是构建时的布局，官方包一更新就可能对不上。
        """
        dl = self.data_list(rel)
        if not dl:
            return None
        want = None if key is None else str(key).strip()
        if want:
            for rec in dl:
                if isinstance(rec, dict) and record_id_of(rec) == want:
                    return rec
        if record_index is None:
            return None
        if not (0 <= int(record_index) < len(dl)):
            return None
        rec = dl[int(record_index)]
        return rec if isinstance(rec, dict) else None

    def model_name(self, model: str | None) -> str | None:
        """``model`` 角色键（韩文）→ 显示名；查不到返回 None。

        过场文件（c10p2 起）只填 ``model``、不填 ``teller``，名字要从对照表反查，
        否则整段对话都会退化成「旁白」。
        """
        if not model:
            return None
        if self._model_names is None:
            self._model_names = load_model_names(self.codes_dirs)
        return self._model_names.get(str(model))

    def resolve(self, rel: str, record_index: int | None, text_index: int | None = None,
                field_name: str | None = None, key=None) -> tuple[str | None, str | None, str | None]:
        """取某条文本：返回 (文本, 说话人, 小标题)。

        说话人优先取 ``teller`` / ``speaker``；两者都没有时按记录上的 ``model``
        反查角色名（不是叙述句，只是新版文件把名字搬到了 ``model``）。
        """
        rec = self.record(rel, record_index, key)
        if rec is None:
            return None, None, None
        text, speaker, title = read_record_text(rec, text_index, field_name)
        if speaker is None:
            speaker = self.model_name(rec.get("model"))
        return text, speaker, title

    def resolve_item(self, item: dict) -> dict:
        """给剧本 / 列表条目补上文本（只在缺文本时读文件）。"""
        if item.get("type") == "scene" or item.get("wiki_only"):
            return item
        rel, rec = item.get("file"), item.get("record")
        if not rel:
            return item
        text, speaker, title = self.resolve(rel, None if rec is None else int(rec),
                                            item.get("text_index"), item.get("field"),
                                            item.get("key"))
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
