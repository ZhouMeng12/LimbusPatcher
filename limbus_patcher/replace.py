"""一键替换（批量查找替换）：纯逻辑层，不依赖界面。

规则（不碰零协原文文件，只写方案）：
- 「零协原文」命中 → 把替换后的整段文本写进方案的自定义文本；
- 「自定义文本」命中 → 在自定义文本上改（保留其余改动）；
- 替换结果与原文相同 → 视为还原，删掉该条方案条目；
- 每条改动都进历史记录，可逐条撤销；批量替换另外提供一次性撤销（见 undo_batch）。

范围由调用方给出候选命中（SearchHit 列表）：当前列表筛选结果 / 某个实体 / 全库。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .deploy import _find_record as find_record
from .fsutil import load_json
from .patch import EntryRef, encode_fp, get_value

#: 文本来源
SOURCE_ORIGINAL = "original"
SOURCE_CUSTOM = "custom"
SOURCE_BOTH = "both"
SOURCE_LABELS = {SOURCE_ORIGINAL: "零协原文", SOURCE_CUSTOM: "自定义文本", SOURCE_BOTH: "两者都替换"}

#: 一次批量替换的安全上限（避免误操作把整库都改了）
MAX_ITEMS = 5000
#: 预览表格最多显示多少行（超过仍会全部应用勾选项）
PREVIEW_ROWS = 2000


@dataclass
class ReplaceRule:
    find: str
    repl: str = ""
    regex: bool = False
    case_sensitive: bool = True
    source: str = SOURCE_BOTH
    #: 整段文本完全等于 find 才算命中（只对普通模式有意义）
    whole: bool = False

    def validate(self) -> str | None:
        """返回错误信息（None = 规则可用）。"""
        if not self.find:
            return "请填写要查找的内容"
        if self.regex:
            try:
                re.compile(self.find)
            except re.error as exc:
                return f"正则表达式有误：{exc}"
        return None


@dataclass
class ReplaceItem:
    """一条待替换的文本。"""

    ref: EntryRef
    label: str = ""            # 列表里显示的定位（文件 · 记录）
    original: str = ""         # 零协原文（只读参考）
    current: str = ""          # 当前生效文本（自定义优先，否则原文）
    after: str = ""            # 替换后的文本
    from_custom: bool = False  # 命中来自自定义文本
    custom_before: str | None = None  # 替换前的自定义文本（None = 之前没改过）；撤销用
    count: int = 0             # 这条文本里命中的次数

    @property
    def ref_key(self) -> str:
        return self.ref.key()

    @property
    def changed(self) -> bool:
        return self.after != self.current


def compile_pattern(rule: ReplaceRule) -> re.Pattern | None:
    """普通模式也编译成正则（转义），统一处理大小写与整段匹配。"""
    err = rule.validate()
    if err:
        return None
    body = rule.find if rule.regex else re.escape(rule.find)
    if rule.whole and not rule.regex:
        body = rf"^(?:{body})$"
    flags = 0 if rule.case_sensitive else re.IGNORECASE
    try:
        return re.compile(body, flags)
    except re.error:
        return None


def replace_text(text: str, rule: ReplaceRule, pattern: re.Pattern | None = None) -> tuple[str, int]:
    """返回 (替换后的文本, 命中次数)。未命中时原样返回、次数为 0。

    替换串里的 ``\\1`` 这类反向引用只在正则模式下生效（普通模式按字面量写入）。
    """
    pattern = pattern or compile_pattern(rule)
    if pattern is None or text == "":
        return text, 0
    repl = rule.repl
    if not rule.regex:
        repl = repl.replace("\\", "\\\\")
    if rule.whole and not rule.regex:
        if not pattern.match(text):
            return text, 0
    new_text, n = pattern.subn(repl, text)
    return (new_text, n) if n else (text, 0)


def plan_item(rule: ReplaceRule, ref: EntryRef, original: str, label: str,
              custom: str | None, pattern: re.Pattern | None = None) -> ReplaceItem | None:
    """按规则算出一条替换（未命中返回 None）。

    命中优先级：已改过的条目先在自定义文本上找（不会把自定义改动冲掉），
    只有「只替换零协原文」才会落到原文上（该选项会覆盖这条的自定义改动）。
    """
    pattern = pattern or compile_pattern(rule)
    if pattern is None:
        return None
    check_custom = rule.source in (SOURCE_CUSTOM, SOURCE_BOTH)
    check_original = rule.source in (SOURCE_ORIGINAL, SOURCE_BOTH)
    if custom is not None and check_custom:
        text, count = replace_text(custom, rule, pattern)
        if count:
            return ReplaceItem(ref=ref, label=label, original=original, current=custom, after=text,
                               from_custom=True, custom_before=custom, count=count)
    if check_original:
        text, count = replace_text(original, rule, pattern)
        if count:
            current = custom if custom is not None else original
            return ReplaceItem(ref=ref, label=label, original=original, current=current, after=text,
                               from_custom=False, custom_before=custom, count=count)
    return None


def plan_hits(ctx, hits, rule: ReplaceRule, limit: int = MAX_ITEMS) -> list[ReplaceItem]:
    """对候选命中逐条算替换（读原文用磁盘上的零协包，避免索引过期）。"""
    return plan_candidates(ctx, candidates_from_hits(hits), rule, limit=limit)


class SourceLoader:
    """按文件缓存零协原文的读取器。

    批量替换一次要读成千上万条文本，逐条 ``original_of`` 会把同一个 JSON 文件反复解析；
    候选先按文件排好序，这里只缓存「当前文件」，实际每个文件只解析一次。
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self._file = ""
        self._records: list | None = None

    def text(self, ref: EntryRef) -> str | None:
        if ref.file != self._file:
            self._file, self._records = ref.file, None
            data, _err = load_json(Path(self.llc_dir) / ref.file)
            dl = data.get("dataList") if isinstance(data, dict) else None
            self._records = dl if isinstance(dl, list) else None
        if self._records is None:
            return None
        try:
            return get_value(find_record(self._records, ref), ref.field_path)
        except KeyError:
            return None

    @property
    def llc_dir(self) -> Path:
        env = self.ctx.env
        return Path(env.llc_pack_dir) if env.llc_ok and env.llc_pack_dir else Path(".")


def _sort_key(cand: "Candidate") -> tuple:
    return (cand.ref.file, cand.ref.record_index, encode_fp(cand.ref.field_path or []))


def plan_candidates(ctx, candidates: list["Candidate"], rule: ReplaceRule,
                    limit: int = MAX_ITEMS) -> list[ReplaceItem]:
    """候选 → 替换计划（按文件分组读原文，避免重复解析同一文件）。"""
    pattern = compile_pattern(rule)
    if pattern is None:
        return []
    loader = SourceLoader(ctx)
    items: list[ReplaceItem] = []
    for cand in sorted(candidates, key=_sort_key):
        original = loader.text(cand.ref)
        if original is None:
            continue
        entry = ctx.profile.get(cand.ref)
        custom = entry.value if entry is not None else None
        item = plan_item(rule, cand.ref, original, cand.label, custom, pattern)
        if item is not None:
            items.append(item)
        if len(items) >= limit:
            break
    return items


def plan_scan(ctx, rule: ReplaceRule, entity_key: str | None = None,
              limit: int = MAX_ITEMS) -> list[ReplaceItem]:
    """全库流式扫描出替换计划（正则里没有可预筛的字面量时用）。

    逐行取索引里的定位信息 + 按文件缓存的原文，命中多少算多少，不会一次性把所有条目读进内存。
    """
    pattern = compile_pattern(rule)
    if pattern is None:
        return []
    loader = SourceLoader(ctx)
    items: list[ReplaceItem] = []
    for relpath, ref, sinner, character in ctx.search.iter_refs(entity_key):
        original = loader.text(ref)
        if original is None:
            continue
        entry = ctx.profile.get(ref)
        custom = entry.value if entry is not None else None
        if custom is None and rule.source == SOURCE_CUSTOM:
            continue
        item = plan_item(rule, ref, original, Candidate(ref, relpath, sinner, character).label,
                         custom, pattern)
        if item is not None:
            items.append(item)
        if len(items) >= limit:
            break
    return items


def plan_scope(ctx, rule: ReplaceRule, hits=None, entity_key: str | None = None,
               limit: int = MAX_ITEMS) -> list[ReplaceItem]:
    """一键替换的统一入口：按范围 + 规则算出替换计划。"""
    if hits is not None:
        return plan_candidates(ctx, candidates_from_hits(hits), rule, limit)
    if rule.source == SOURCE_CUSTOM and not entity_key:
        cands = [Candidate(ref=e.ref, file=e.ref.file) for e in ctx.profile.values()]
        return plan_candidates(ctx, cands, rule, limit)
    if literal_seed(rule) is None:
        return plan_scan(ctx, rule, entity_key=entity_key, limit=limit)
    return plan_candidates(ctx, collect_candidates(ctx, rule, entity_key=entity_key, limit=limit),
                           rule, limit)


#: 正则里至少要有这么长的普通字符片段才能拿去 SQL 预筛
LITERAL_SEED_MIN = 2
#: 出现这些符号时字面量片段不一定在每条匹配里出现（交替 / 可选 / 字符类 / 分组）→ 只能全库扫
_UNSAFE_SEED_RE = re.compile(r"[|?*\[\]()]")


def literal_seed(rule: ReplaceRule) -> str | None:
    """从规则里取一段最长普通字符，作为 SQL LIKE 的预筛词；取不到返回 None（只能全库扫）。

    这是纯优化：取错会漏替换，所以拿不准就返回 None（慢一点但正确）。
    """
    if not rule.regex:
        return rule.find or None
    if _UNSAFE_SEED_RE.search(rule.find):
        return None
    best = ""
    run: list[str] = []
    escaped = False
    for ch in rule.find:
        if escaped:
            # \d \w 这类字符类是「非字面量」；\. 这类转义才是字面量
            if ch.isalnum() or ch == "b":
                run = []
            else:
                run.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch.isalnum() or ch in " _-":
            run.append(ch)
            continue
        if len(run) > len(best):
            best = "".join(run)
        run = []
    if len(run) > len(best):
        best = "".join(run)
    return best if len(best) >= LITERAL_SEED_MIN else None


@dataclass
class Candidate:
    """一条候选条目（只需要定位 + 显示用的信息）。"""

    ref: EntryRef
    file: str = ""
    sinner_name: str = ""
    character: str = ""

    @property
    def label(self) -> str:
        from .patch import ref_label

        who = self.sinner_name or self.character or ""
        where = f"{self.file} · {ref_label(self.ref)}"
        return f"{who}　{where}" if who else where


def candidates_from_hits(hits) -> list[Candidate]:
    return [Candidate(ref=h.ref, file=h.file, sinner_name=h.sinner_name or "",
                      character=h.character or "") for h in hits]


def collect_candidates(ctx, rule: ReplaceRule, hits=None, entity_key: str | None = None,
                       limit: int = MAX_ITEMS) -> list[Candidate]:
    """按规则收集候选条目。

    - ``hits`` 给了就用它（当前列表筛选结果，用户看到什么就替换什么）；
    - 否则「零协原文」侧用索引 LIKE 预筛（正则取字面量锚点，取不到则全库流式扫描）；
    - 「自定义文本」侧补上方案里已改过的条目（自定义文本不在索引里）。
    """
    if hits is not None:
        return candidates_from_hits(hits)[:limit]
    out: list[Candidate] = []
    seen: set[str] = set()

    def _add(cand: Candidate) -> None:
        key = cand.ref.key()
        if key in seen:
            return
        seen.add(key)
        out.append(cand)

    if rule.source in (SOURCE_CUSTOM, SOURCE_BOTH):
        for entry in ctx.profile.values():
            _add(Candidate(ref=entry.ref, file=entry.ref.file))
    if rule.source in (SOURCE_ORIGINAL, SOURCE_BOTH) or entity_key:
        seed = literal_seed(rule)
        if seed:
            for hit in ctx.search.search(text=seed, entity_key=entity_key, limit=limit, scope="original"):
                _add(Candidate(ref=hit.ref, file=hit.file, sinner_name=hit.sinner_name or "",
                               character=hit.character or ""))
        else:
            for relpath, ref, sinner, character in ctx.search.iter_refs(entity_key):
                _add(Candidate(ref=ref, file=relpath, sinner_name=sinner, character=character))
                if len(out) >= limit:
                    break
    if entity_key:
        # 实体范围内：方案里那些条目也要确认属于该实体（自定义文本不在索引里，只能这样筛）
        in_entity = {ref.key() for _rel, ref, _s, _c in ctx.search.iter_refs(entity_key)}
        out = [c for c in out if c.ref.key() in in_entity]
    return out[:limit]


def apply_items(ctx, items: list[ReplaceItem], progress=None) -> tuple[int, list[str]]:
    """写入方案。返回 (成功条数, 失败信息)。"""
    ok, errors = 0, []
    total = len(items)
    for i, item in enumerate(items, start=1):
        res = ctx.upsert_entry(item.ref, item.after)
        if res.ok:
            ok += 1
        else:
            errors.append(f"{item.label}：{res.message}")
        if progress and (i % 50 == 0 or i == total):
            progress(i, total)
    return ok, errors


def undo_items(ctx, items: list[ReplaceItem]) -> int:
    """把一次批量替换整体还原（回到替换前：没改过的删掉，改过的写回旧值）。"""
    done = 0
    for item in items:
        if item.custom_before is None:
            if ctx.remove_entry(item.ref):
                done += 1
        else:
            res = ctx.upsert_entry(item.ref, item.custom_before)
            if res.ok:
                done += 1
    return done


@dataclass
class BatchRecord:
    """一次批量替换的撤销凭证。"""

    items: list[ReplaceItem] = field(default_factory=list)
    summary: str = ""
