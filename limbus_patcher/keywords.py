"""零协汉化文本里的方括号关键词 token：id → 中文名（显示层替换）。

游戏文本里混着大量 ``[KarmaOfIndexAlly]`` / ``[Breath]`` / ``[OnSucceedAttack]``
这类方括号 token。它们是**游戏数据引用 id**，不是排版标签：运行时由游戏把 id
替换成该关键词的本地化名字并高亮。实测真实包（LLC_zh-CN，Skills_*.json 全量）：
技能文本里出现 41,953 次、564 个不同 id，其中 561 个（99.5%）能在
BattleKeywords* / Bufs* / SkillTag 里找到同 id 记录（例如 ``KarmaOfIndexAlly`` →「业」，
``Breath`` →「呼吸法」），其它来自 SkillTag.json（``OnSucceedAttack`` →「[命中时]」）。

因此本模块**只做显示层替换**，绝不改动文本本身：

- load_map()      → {token_id: {"name": 中文名, "desc": 说明, "source": 文件名, …}}
- substitute()    → ``[id]`` → 中文名（mode="raw" 原样返回、mode="both" 输出 ``名[id]``）
- tokens_in()     → 这段文本里出现的已知 token（tooltip 用：id + 中文名）
- render_html()   → 先 substitute 再交给 richtext.to_html，替换出的名字带色高亮

取舍说明
--------
- 名字以 BattleKeywords* 为准：同一 id 在 Bufs* / SkillTag 里可能也有记录，
  但玩家在游戏里看到的是 BattleKeywords 的 name；其余候选记进 ``alternatives``。
- Bufs 记录若没有 name，只补 desc / alternatives，不覆盖已有 name。
- id 精确匹配（区分大小写、不做任何模糊 / 前缀匹配）——``[breath]`` 不会命中 ``Breath``；
  正文里中文方括号（``[肉]``）与 ``{0}`` 占位符根本不会被当成 token。
- 不碰 ``<>`` 里的标签内容（``<sprite name=[Foo]>`` 原样保留），不碰 ``{0}`` 占位符。
- 未知 token 一律原样保留：替换是纯显示层的「锦上添花」，宁可不显示也不能改坏原文。
- 文件缺失 / JSON 解析失败一律静默降级为空表，绝不抛异常（图鉴页不该因为一个坏文件打不开）。
- SkillTag 的 name 自带方括号（``OnSucceedAttack`` →「[使用时]」），原样使用，
  替换 ``[OnSucceedAttack]`` 得到「[使用时]」，不会被套成双层括号。

本模块是纯函数、无 Qt 依赖，可直接被测试与命令行脚本使用。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "EDITABLE_FIELDS",
    "FIELD_LABELS",
    "FLAVOR_COLOR",
    "KEYWORD_COLOR",
    "SCAN_FILES",
    "KeywordRecord",
    "clear_cache",
    "edit_targets",
    "load_map",
    "load_records",
    "render_html",
    "substitute",
    "tokens_in",
    "tooltip_html",
]

#: 替换出的关键词名颜色：柔和蓝，与正文（TEXT #d8d4c8）和主题暗金（ACCENT #c8a24a /
#: WARNING #d9a441）都能区分。本模块是纯函数、不依赖 Qt，故此处硬编码，
#: 与 ui/theme.py 的 QSS 改动无关。
KEYWORD_COLOR = "#6fb2e8"

#: 扫描的文件名模式（零协包根目录；BattleKeywords 优先，其次 Bufs，最后 SkillTag）。
SCAN_FILES = ("BattleKeywords*.json", "Bufs*.json", "SkillTag*.json")

#: 来源优先级：数字越大名字越权威（玩家在游戏里看到的名字来自 BattleKeywords）。
_SOURCE_PRIORITY = {"BattleKeywords": 3, "Bufs": 2, "SkillTag": 1}

#: 一次扫描：``<标签>`` 整体优先匹配（原样保留），否则匹配 ``[id]``。
#: id 允许字母 / 数字 / 下划线 / 点 / 连字符，但至少要有一个字母或下划线——
#: 这样 ``[2xPostLine]``、``[Lacrimosa-Crescendo]`` 这类 id 也认，
#: 而正文里的中文方括号（``[肉]``）与 ``{0}`` 占位符不会被当成 token。
_SCAN_RE = re.compile(r"<[^<>]*>|\[([A-Za-z0-9_.\-]*[A-Za-z_][A-Za-z0-9_.\-]*)\]")
#: render_html 用的临时占位符（\x00 不会被 richtext 的转义碰到）：\x00<序号>\x00
_MARK_RE = re.compile("\x00(\\d+)\x00")

#: tooltip 里 flavor（风味文本）的颜色：灰，与正文（TEXT #d8d4c8）区分开。
#: 对应 ui/theme.py 的 TEXT_DIM，本模块不依赖 Qt 故硬编码。
FLAVOR_COLOR = "#8b867a"

#: 关键词记录里可编辑的字段（顺序即界面顺序）。
EDITABLE_FIELDS = ("name", "desc", "flavor")
#: 字段 → 界面上的中文标签。
FIELD_LABELS = {"name": "名称", "desc": "说明", "flavor": "风味文本"}

#: 进程内缓存：{llc_dir 字符串: {id: 记录}}。load_map 返回值即缓存对象，请勿修改。
_CACHE: dict[str, dict[str, dict]] = {}
#: 进程内缓存：{llc_dir 字符串: {id: [KeywordRecord, …]}}（原始记录，供编辑用）。
_RECORD_CACHE: dict[str, dict[str, list["KeywordRecord"]]] = {}


def clear_cache() -> None:
    """清空进程内缓存（测试用；改过关键词文件后也可手动调用）。"""
    _CACHE.clear()
    _RECORD_CACHE.clear()


# --------------------------------------------------------------------------- 载入


def _source_of(file_name: str) -> str:
    """文件名 → 来源类别（BattleKeywords / Bufs / SkillTag）。"""
    low = file_name.lower()
    if low.startswith("battlekeywords"):
        return "BattleKeywords"
    if low.startswith("bufs"):
        return "Bufs"
    if low.startswith("skilltag"):
        return "SkillTag"
    return ""


def _records_of(path: Path) -> list:
    """读一个关键词文件里的记录表；缺失 / 坏文件 / 结构不符一律返回空表。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))
    except (OSError, ValueError):
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        dl = data.get("dataList")
        if isinstance(dl, list):
            return dl
    return []


def _text_of(value) -> str:
    """记录字段 → 字符串（None / 非字符串一律当空串，避免写进界面变 "None"）。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _merge(entry: dict, cand: dict) -> None:
    """把一条候选记录并入已有条目（按来源优先级决定 name；其它候选进 alternatives）。"""
    old_rank = _SOURCE_PRIORITY.get(entry.get("_source_kind", ""), 0)
    new_rank = _SOURCE_PRIORITY.get(cand["_source_kind"], 0)
    if cand["name"] and (not entry["name"] or new_rank > old_rank):
        # 名字换人：原来那个降级进 alternatives
        if entry["name"]:
            entry["alternatives"].append(
                {"name": entry["name"], "desc": entry["desc"], "source": entry["source"]})
        entry["name"] = cand["name"]
        entry["source"] = cand["source"]
        entry["_source_kind"] = cand["_source_kind"]
        if cand["desc"]:
            entry["desc"] = cand["desc"]
        return
    if cand["name"]:
        entry["alternatives"].append(
            {"name": cand["name"], "desc": cand["desc"], "source": cand["source"]})
    # Bufs / SkillTag 只有 desc 时补说明，不覆盖已有 name
    if cand["desc"] and not entry["desc"]:
        entry["desc"] = cand["desc"]


def _scan_dir(llc: Path, keep_kind: bool = False) -> dict[str, dict]:
    """扫描零协包根目录，建 {token_id: 记录}。

    keep_kind=True 时保留内部 ``_source_kind`` 键（供多目录合并做优先级判断），
    调用方合并完成后需自行 pop。
    """
    out: dict[str, dict] = {}
    files: list[tuple[int, str, Path]] = []
    for pattern in SCAN_FILES:
        try:
            found = sorted(llc.glob(pattern))
        except OSError:
            found = []
        for path in found:
            kind = _source_of(path.name)
            if kind:
                files.append((-_SOURCE_PRIORITY.get(kind, 0), path.name, path))
    for _rank, name, path in sorted(files, key=lambda it: (it[0], it[1])):
        kind = _source_of(name)
        for rec in _records_of(path):
            if not isinstance(rec, dict):
                continue
            tid = _text_of(rec.get("id"))
            if not tid:
                continue
            cand = {"name": _text_of(rec.get("name")), "desc": _text_of(rec.get("desc")),
                    "source": name, "_source_kind": kind}
            entry = out.get(tid)
            if entry is None:
                out[tid] = {"name": cand["name"], "desc": cand["desc"], "source": name,
                            "_source_kind": kind, "alternatives": []}
            else:
                _merge(entry, cand)
    if not keep_kind:
        for entry in out.values():
            entry.pop("_source_kind", None)
    return out


def load_map(llc_dir, extra_dirs=None) -> dict[str, dict]:
    """扫描 BattleKeywords* / Bufs* / SkillTag.json，返回 {token_id: 记录}。

    记录字段：``name``（中文名，可能是空串）、``desc``（说明）、``source``（文件名）、
    ``alternatives``（[{"name", "desc", "source"}]，其它来源的同 id 候选）。

    - 名字以 BattleKeywords 为准（玩家看得到的那个名字），其余候选进 alternatives；
    - Bufs 记录没有 name 时不会覆盖已有 name，只补 desc；反过来说，
      只有 desc 的记录若发现某个 id 还没名字，也允许用它的 name 补上；
    - 同一来源里出现重复 id 时取文件名排序靠前的那条，结果稳定可复现；
    - ``extra_dirs``：额外扫描目录（如 supplement），对每个目录复用与主目录相同的
      _scan_dir / _keyword_files 合并逻辑；合并优先级 BattleKeywords > Bufs > SkillTag
      保持，主目录已有 name 的 token 不会被 extra 目录的同级来源覆盖，
      extra 目录只负责补齐主目录缺失的新 token；
    - 进程内按 (llc_dir, extra_dirs 元组) 缓存（返回值即缓存对象，**请勿原地修改**）；
    - 目录不存在、文件缺失、JSON 解析失败一律静默降级（坏文件跳过，整体不抛异常）。
    """
    try:
        base_key = str(Path(llc_dir).resolve())
    except (OSError, TypeError, ValueError):
        base_key = str(llc_dir)
    extra_key: tuple[str, ...] = ()
    if extra_dirs:
        extra_key = tuple(str(Path(e).resolve()) for e in extra_dirs)
    key = (base_key, extra_key)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    table: dict[str, dict] = {}
    try:
        llc = Path(llc_dir)
        if llc.is_dir():
            table = _scan_dir(llc, keep_kind=True)
        for extra in extra_dirs or ():
            ed = Path(extra)
            if not ed.is_dir():
                continue
            for tid, cand in _scan_dir(ed, keep_kind=True).items():
                entry = table.get(tid)
                if entry is None:
                    table[tid] = cand
                else:
                    _merge(entry, cand)
    except (OSError, TypeError, ValueError):
        table = {}
    for entry in table.values():
        entry.pop("_source_kind", None)
    _CACHE[key] = table
    return table


# --------------------------------------------------------------------------- 显示层替换


def _substitute(text: str, mapping, mode: str, wrap=None) -> str:
    """统一的替换实现：``<>`` 标签原样跳过，``[id]`` 命中则按 wrap / mode 输出。"""
    out: list[str] = []
    pos = 0
    for m in _SCAN_RE.finditer(text):
        tid = m.group(1)
        if tid is None:                    # <标签>：整体原样保留
            continue
        rec = mapping.get(tid) if mapping else None
        name = (rec or {}).get("name") or ""
        if not rec or not name:            # 未知 token / 无中文名：原样保留
            continue
        out.append(text[pos:m.start()])
        if wrap is not None:
            out.append(wrap(tid, name))
        elif mode == "both":
            out.append(f"{name}[{tid}]")
        else:
            out.append(name)
        pos = m.end()
    if not out:
        return text
    out.append(text[pos:])
    return "".join(out)


def substitute(text: str, mapping, mode: str = "name") -> str:
    """把文本里的 ``[id]`` 换成中文名（显示用，不改动原文）。

    - ``mode="name"``：``[Breath]`` →「呼吸」；
    - ``mode="both"``：``[Breath]`` →「呼吸[Breath]」（中文名 + 原始 id）；
    - ``mode="raw"``：原样返回（页头「关键词名」取消勾选时走这条）；
    - 未知 token、``mapping`` 里没有中文名的记录：``[id]`` 原样保留；
    - 只认精确 id（区分大小写），不做模糊 / 前缀匹配；
    - ``<>`` 标签内容、``{0}`` 占位符一律不受影响；空串返回空串。
    """
    if not text or not mapping or mode == "raw":
        return text
    return _substitute(text, mapping, mode)


def _escape(text: str) -> str:
    """HTML 转义（与 richtext 同一套），关键词名可能含 & < > 时也安全。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _mark_html(picked: list[tuple[str, str]], m: re.Match, link_prefix: str = "") -> str:
    """占位符 → 带色 span / 锚点（序号越界时原样保留，绝不抛异常）。

    link_prefix 非空时输出 <a href="前缀id" style="…">名</a>：
    QLabel 靠锚点才能做「悬停看说明 / 点击编辑关键词」（见 ui/codex_page.py）。
    """
    idx = int(m.group(1))
    if idx >= len(picked):
        return m.group(0)
    name, tid = picked[idx]
    style = f"color:{KEYWORD_COLOR}"
    if link_prefix:
        return (f'<a href="{_escape(link_prefix + tid)}" '
                f'style="{style}; text-decoration:none">{_escape(name)}</a>')
    return f'<span style="{style}">{_escape(name)}</span>'


def render_html(text: str, mapping, mode: str = "name", link_prefix: str = "") -> str:
    """先 substitute 再交给 ``limbus_patcher.richtext.to_html``，关键词名带色高亮。

    - 颜色用模块常量 KEYWORD_COLOR（``<span style="color:#6fb2e8">名</span>``），
      与正文以及游戏自带的 <color=…> 都能区分；
    - link_prefix 非空时输出锚点 <a href="前缀id">名</a>（默认空 = 与旧版输出完全一致），
      图鉴页用它接「悬停看 desc / flavor、点击改关键词」；
    - 名字进 HTML 前先转义，标签注入无从下手；
    - ``mode="raw"`` / 空 ``mapping`` / 没有命中 → 等价于 ``richtext.to_html(text)``；
    - 原文里含 ``\\x00``（占位符会撞车）时退化成「不染色」的替换结果，不影响正确性。
    """
    from . import richtext  # 延迟导入：本模块的纯函数部分不依赖 richtext

    if not text:
        return ""
    if not mapping or mode == "raw":
        return richtext.to_html(text)
    if "\x00" in text:
        # 占位符会与原文撞车：退化成「替换但不染色」，结果依然正确
        return richtext.to_html(_substitute(text, mapping, mode))

    picked: list[tuple[str, str]] = []

    def wrap(tid: str, name: str) -> str:
        picked.append((name, tid))
        tail = f"[{tid}]" if mode == "both" else ""
        return f"\x00{len(picked) - 1}\x00{tail}"

    substituted = _substitute(text, mapping, mode, wrap=wrap)
    if not picked:
        return richtext.to_html(substituted)
    html = richtext.to_html(substituted)
    return _MARK_RE.sub(lambda m: _mark_html(picked, m, link_prefix), html)


def tokens_in(text: str, mapping) -> list[dict]:
    """该文本里出现的已知 token（按首次出现顺序、去重），供 tooltip 显示。

    每项：``{"id", "name", "desc", "source", "count"}``；未知 token 不收录。
    """
    if not text or not mapping:
        return []
    seen: dict[str, dict] = {}
    for m in _SCAN_RE.finditer(text):
        tid = m.group(1)
        if tid is None:
            continue
        rec = mapping.get(tid)
        if not isinstance(rec, dict):
            continue
        item = seen.get(tid)
        if item is None:
            seen[tid] = {"id": tid, "name": rec.get("name") or "",
                         "desc": rec.get("desc") or "", "source": rec.get("source") or "",
                         "count": 1}
        else:
            item["count"] += 1
    return list(seen.values())


# --------------------------------------------------------------------------- 原始记录（供编辑）


@dataclass(frozen=True)
class KeywordRecord:
    """关键词表里的一条原始记录。

    字段：id / 相对零协包的文件名 / 在 dataList 里的下标 / 来源类别 /
    texts（只收录记录里真实存在的字符串字段，如 name / desc / flavor）。

    有了 file + record_index + 字段名，界面就能拼出 EntryRef 把改动写进方案；
    只把记录里**存在**的字段放进 texts，避免给 Bufs 记录凭空加一个 flavor。
    """

    id: str
    file: str
    record_index: int
    source_kind: str
    texts: dict[str, str]

    def text_of(self, field: str) -> str:
        """该字段的原文；记录里没有这个字段时返回空串。"""
        return self.texts.get(field, "")

    def has(self, field: str) -> bool:
        return field in self.texts

    @property
    def name(self) -> str:
        return self.texts.get("name", "")

    @property
    def desc(self) -> str:
        return self.texts.get("desc", "")

    @property
    def flavor(self) -> str:
        return self.texts.get("flavor", "")


def _keyword_files(llc: Path) -> list[tuple[str, Path]]:
    """关键词表文件，按来源优先级（BattleKeywords → Bufs → SkillTag）+ 文件名排序。"""
    out: list[tuple[str, Path]] = []
    for pattern in SCAN_FILES:
        try:
            found = sorted(llc.glob(pattern))
        except OSError:
            found = []
        for path in found:
            kind = _source_of(path.name)
            if kind:
                out.append((path.name, path))
    out.sort(key=lambda it: (-_SOURCE_PRIORITY.get(_source_of(it[0]), 0), it[0]))
    return out


def load_records(llc_dir, extra_dirs=None) -> dict[str, list[KeywordRecord]]:
    """扫描关键词表，返回 {token_id: [KeywordRecord, …]}（BattleKeywords 在前）。

    与 load_map 的分工：load_map 只做显示层替换（id → 中文名），
    这里保留每条原始记录（文件 / 下标 / name+desc+flavor 原文），
    供图鉴页「悬停看说明」「点击进关键词编辑」使用。

    - 同一 id 在 BattleKeywords / Bufs / SkillTag 里都有记录时全部保留，便于界面同步修改；
    - ``extra_dirs``：额外扫描目录（如 supplement），复用同一 _keyword_files 逻辑，
      附加到主目录文件之后，用于补齐 c10 等不在零协包内的新效果 token；
    - 目录不存在 / 文件坏 / 结构不符：静默降级（该文件跳过，整体不抛异常）；
    - 进程内按 (llc_dir, extra_dirs 元组) 缓存（返回值即缓存对象，请勿原地修改）。
    """
    try:
        base_key = str(Path(llc_dir).resolve())
    except (OSError, TypeError, ValueError):
        base_key = str(llc_dir)
    extra_key: tuple[str, ...] = ()
    if extra_dirs:
        extra_key = tuple(str(Path(e).resolve()) for e in extra_dirs)
    key = (base_key, extra_key)
    cached = _RECORD_CACHE.get(key)
    if cached is not None:
        return cached
    table: dict[str, list[KeywordRecord]] = {}
    try:
        llc = Path(llc_dir)
        dirs = [llc] + [Path(e) for e in (extra_dirs or ())]
        for d in dirs:
            if not d.is_dir():
                continue
            for name, path in _keyword_files(d):
                kind = _source_of(name)
                for index, rec in enumerate(_records_of(path)):
                    if not isinstance(rec, dict):
                        continue
                    tid = _text_of(rec.get("id"))
                    if not tid:
                        continue
                    texts = {f: _text_of(rec.get(f)) for f in EDITABLE_FIELDS
                             if isinstance(rec.get(f), str)}
                    table.setdefault(tid, []).append(
                        KeywordRecord(id=tid, file=name, record_index=index,
                                      source_kind=kind, texts=texts))
    except (OSError, TypeError, ValueError):
        table = {}
    _RECORD_CACHE[key] = table
    return table


def edit_targets(records) -> dict[str, list[KeywordRecord]]:
    """字段名 → 含该字段的记录列表（保持 records 的顺序，BattleKeywords 在前）。

    界面用它决定「这个字段的原文来自哪条记录」「要同步写到哪几条记录」。
    """
    out: dict[str, list[KeywordRecord]] = {}
    for rec in records or []:
        for field in EDITABLE_FIELDS:
            if rec.has(field):
                out.setdefault(field, []).append(rec)
    return out


def _br(text: str) -> str:
    """多行文本 → HTML（转义 + 换行转 <br>），tooltip 里换行才生效。"""
    return _escape(text).replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def tooltip_html(token: str, records) -> str:
    """关键词悬停提示：名称 + id + 说明（desc）+ 风味文本（flavor，灰色）。

    - 名称 / 说明 / 风味各取「第一条有内容的记录」（BattleKeywords 优先）；
    - 说明与风味都没有时返回空串 —— 调用方就别弹自定义 tooltip（如 SkillTag 只有名字）；
    - 全部文本先 HTML 转义再拼标签，换行转 <br>。
    """
    recs = [r for r in (records or []) if isinstance(r, KeywordRecord)]
    if not recs:
        return ""
    name = next((r.name for r in recs if r.name), "") or token
    desc = next((r.desc for r in recs if r.desc), "")
    flavor = next((r.flavor for r in recs if r.flavor), "")
    if not desc and not flavor:
        return ""
    head = (f'<b style="color:{KEYWORD_COLOR}">{_escape(name)}</b> '
            f'<span style="color:{FLAVOR_COLOR}">[{_escape(token)}]</span>')
    blocks = [head]
    if desc:
        blocks.append(_br(desc))
    if flavor:
        blocks.append(f'<span style="color:{FLAVOR_COLOR}">{_br(flavor)}</span>')
    return "<br><br>".join(blocks)

