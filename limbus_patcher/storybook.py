"""剧本阅读数据：wiki 关卡对照表加载（story_stages.json）。

结构（由 scripts/export_stages.py 从爬取结果生成，按章节聚合）：
{
  "format_version": 1,
  "generated_at": "...",
  "chapters": [
    {"chapter_id": "prologue", "chapter_label": "序章",
     "stages": [
        {"stage_code": "0-01", "pages": [
            {"segment": "战前", "title": "0-01战前", "file": "StoryData/S001B.json"},
            {"segment": "战后", "title": "0-01战后", "file": "StoryData/S001A.json"}
        ]}
     ]}
  ]
}

v2 数据在每个 stage 额外带 ``items``（剧本模式按序条目）：
``{"type": "line"|"scene", "text": ..., "file": ..., "page": ..., "key": ..., "wiki_only": ...}``。

加载后自检结果见 ``Storybook.problems``（:meth:`Storybook.validate`）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .season import package_data_dir
from .textsource import speaker_of

SEGMENT_ORDER = {"战前": 0, "战中": 1, "战后": 2, "前段": 0, "后段": 2}

_DATA_FILENAMES = ("story_stages.json", "export_stages.json")
_ITEM_TYPES = {"line", "scene"}
MISSING_DATA_PROBLEM = "未找到剧本数据文件 story_stages.json"

#: 开发遗留的任务描述（如「0901追加」），不进剧本骨架
_QUEST_JUNK = re.compile(r"^\s*\d+\s*追加\s*$")

_PUNCT_CHARS = "“”\"'《》<>『』「」…·!！?？。，、：；-—~～()（）_＊*#＃&＆|｜/\\"
_PUNCT_RE = re.compile("[" + re.escape(_PUNCT_CHARS) + "]")


def norm_text(text: str) -> str:
    """剧本对齐用的文本键归一化（与 scripts/_match.py 共用同一实现）。"""
    s = re.sub(r"\s+", "", text or "")
    return _PUNCT_RE.sub("", s)


def _dev_crawl_dir() -> Path | None:
    """开发态：项目根 data/wiki_story/（爬虫产物）存在时优先使用。"""
    d = Path(__file__).resolve().parent.parent / "data" / "wiki_story"
    return d if d.is_dir() else None


def _branch_problems(stag: str, stage: dict, items: list) -> list[str]:
    """RPG 关卡的分支自检（普通关卡没有 branches，直接返回空）。"""
    branches = stage.get("branches")
    if branches is None:
        return []
    if not isinstance(branches, list):
        return [f"{stag} 的 branches 不是列表"]

    problems: list[str] = []
    known: set[str] = set()
    for bi, br in enumerate(branches, start=1):
        if not isinstance(br, dict):
            problems.append(f"{stag} 第 {bi} 个分支不是对象（dict）")
            continue
        bid = br.get("branch_id")
        if not isinstance(bid, str) or not bid:
            problems.append(f"{stag} 第 {bi} 个分支缺少 branch_id")
            continue
        known.add(bid)
        if not br.get("label"):
            problems.append(f"{stag} 分支 {bid} 缺少 label")
    if not isinstance(items, list):
        return problems
    for ii, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            continue
        bid = it.get("branch")
        if bid and bid not in known:
            problems.append(f"{stag} 第 {ii} 个 item 的 branch={bid!r} 不在 branches 里")
            break
    return problems


class Storybook:
    """剧本对照：关卡（wiki 风格）→ 本地文件，按 战前/战中/战后 排序。

    加载后会做一次数据自检，结果放在 ``self.problems``（中文问题列表，无问题为空）；
    也可随时调用 :meth:`validate` 重新自检。
    """

    def __init__(self, overlay_dir: Path | None = None, data_dir: Path | None = None):
        self.overlay_dir = overlay_dir
        self.data_dir = data_dir
        #: 文本来源（TextSource）；设了就按位置现取文本——数据文件里不再存任何游戏文本
        self.text_source = None
        self.data = {"format_version": 1, "chapters": []}
        self.source: Path | None = None
        self.loaded: bool = False
        self.problems: list[str] = []
        self._load(overlay_dir, data_dir)

    def reload(self) -> None:
        self._load(self.overlay_dir, self.data_dir)

    def _load(self, overlay_dir, data_dir) -> None:
        dev = _dev_crawl_dir()
        sources: list[Path | None] = [overlay_dir]
        if data_dir is None:  # 默认包数据：开发态优先 dev 爬取目录
            sources.append(dev)
            sources.append(package_data_dir())
        else:
            sources.append(data_dir)
        found: Path | None = None
        for d in sources:
            if not d:
                continue
            for name in _DATA_FILENAMES:
                p = Path(d) / name
                if p.is_file():
                    try:
                        obj = json.loads(p.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if isinstance(obj, dict) and isinstance(obj.get("chapters"), list) and obj.get("chapters"):
                        self.data = obj
                        found = p
                        break
            if found is not None:
                break
        self.source = found
        self.loaded = found is not None
        self.problems = self.validate()
        if not self.loaded:
            self.problems.insert(0, MISSING_DATA_PROBLEM)

    def validate(self) -> list[str]:
        """自检剧本数据，返回中文问题列表（无问题返回 []）。

        检查：顶层是否 dict、chapters 是否为非空 list、每章 chapter_id/chapter_label/stages、
        每 stage 的 stage_code/items、每个 item 是否为 dict 且 type ∈ {line, scene}、
        line 是否至少含 file 或 wiki_only（缺 page/key 的未对齐行给出提示）。
        """
        problems: list[str] = []
        data = self.data
        if not isinstance(data, dict):
            return [f"剧本数据顶层应为对象（dict），实际为 {type(data).__name__}"]
        chapters = data.get("chapters")
        if not isinstance(chapters, list):
            return ["剧本数据缺少 chapters 列表（或类型不是列表）"]
        if not chapters:
            return ["剧本数据 chapters 为空列表，未加载到任何章节"]

        for ci, ch in enumerate(chapters, start=1):
            where = f"第 {ci} 章"
            if not isinstance(ch, dict):
                problems.append(f"{where}不是对象（dict）")
                continue
            cid = ch.get("chapter_id")
            if not isinstance(cid, str) or not cid:
                problems.append(f"{where}缺少 chapter_id")
            cid_label = cid if isinstance(cid, str) and cid else f"第 {ci} 章"
            if not isinstance(ch.get("chapter_label"), str) or not ch.get("chapter_label"):
                problems.append(f"章节 {cid_label} 缺少 chapter_label")
            stages = ch.get("stages")
            if not isinstance(stages, list):
                problems.append(f"章节 {cid_label} 缺少 stages 列表（或类型不是列表）")
                continue
            if not stages:
                problems.append(f"章节 {cid_label} 的 stages 为空列表")
                continue

            for si, st in enumerate(stages, start=1):
                if not isinstance(st, dict):
                    problems.append(f"章节 {cid_label} 第 {si} 个关卡不是对象（dict）")
                    continue
                code = st.get("stage_code")
                if not isinstance(code, str) or not code:
                    problems.append(f"章节 {cid_label} 第 {si} 个关卡缺少 stage_code")
                stag = f"章节 {cid_label} 关卡 {code}" if isinstance(code, str) and code else \
                    f"章节 {cid_label} 第 {si} 个关卡"
                if "items" not in st:
                    # v1 数据（只有 pages，无 items）视为合法：不报问题，仅当既无 items 也无 pages 时提示
                    if not st.get("pages"):
                        problems.append(f"{stag} 既无 items 也无 pages（剧本数据为空）")
                    continue
                items = st.get("items")
                if not isinstance(items, list):
                    problems.append(f"{stag} 的 items 不是列表")
                    continue
                for ii, it in enumerate(items, start=1):
                    if not isinstance(it, dict):
                        problems.append(f"{stag} 第 {ii} 个 item 不是对象（dict）")
                        continue
                    itype = it.get("type")
                    if not isinstance(itype, str) or itype not in _ITEM_TYPES:
                        problems.append(
                            f"{stag} 第 {ii} 个 item 的 type 非法：{itype!r}（应为 line 或 scene）")
                        continue
                    if itype != "line":
                        continue
                    if not it.get("file") and not it.get("wiki_only"):
                        problems.append(f"{stag} 第 {ii} 行缺少 file 或 wiki_only（无法定位本地文件）")
                    if not it.get("page") and not it.get("key"):
                        problems.append(f"{stag} 第 {ii} 行缺少 page/key（该行未对齐到 wiki 页面）")

                problems.extend(_branch_problems(stag, st, items))
        return problems

    def chapter_list(self) -> list[dict]:
        return list(self.data.get("chapters", []))

    def stages_of(self, chapter_id: str) -> list[dict]:
        for ch in self.data.get("chapters", []):
            if ch.get("chapter_id") == chapter_id:
                return list(ch.get("stages", []))
        return []

    def stage_pages(self, chapter_id: str, stage_code: str) -> list[dict]:
        return [p for s in self.stages_of(chapter_id) if s.get("stage_code") == stage_code
                for p in s.get("pages", [])]

    def branches_of(self, chapter_id: str, stage_code: str) -> list[dict]:
        """该关卡的分支列表（RPG 关卡按玩家游玩顺序；普通关卡为空）。

        分支由 ``limbus_patcher/data/story_rpg_plan.json`` 编排、``scripts/build_story_rpg.py``
        展开；每个分支 = 剧本模式里 10-04 下面可选的一段。
        """
        st = self.stage(chapter_id, stage_code) or {}
        branches = st.get("branches")
        return list(branches) if isinstance(branches, list) else []

    def file_stages(self, relpath: str) -> list[tuple[str, str, dict]]:
        """返回 [(chapter_id, stage_code, page)]：本地文件对应的关卡页。"""
        out: list[tuple[str, str, dict]] = []
        for ch in self.data.get("chapters", []):
            for st in ch.get("stages", []):
                for pg in st.get("pages", []):
                    if pg.get("file") == relpath or relpath in (pg.get("files") or []):
                        out.append((ch.get("chapter_id"), st.get("stage_code"), pg))
        return out

    def stage_records(self, llc_dir: Path, chapter_id: str, stage_code: str) -> list[dict]:
        """按 战前→战后 顺序拼接该关卡各文件的对白记录。"""
        pages = sorted(
            self.stage_pages(chapter_id, stage_code),
            key=lambda p: SEGMENT_ORDER.get(p.get("segment", ""), 5),
        )
        rows: list[dict] = []
        for pg in pages:
            f = llc_dir / pg.get("file", "")
            try:
                data = json.loads(f.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            for i, rec in enumerate(data.get("dataList", [])):
                if not isinstance(rec, dict):
                    continue
                content = rec.get("content")
                if not isinstance(content, str) or not content.strip():
                    continue
                rows.append({
                    "page": pg.get("title"),
                    "segment": pg.get("segment"),
                    "record": i,
                    "speaker": speaker_of(rec),
                    "text": content,
                })
        return rows

    def stage_items(self, chapter_id: str, stage_code: str, branch_id: str | None = None) -> list[dict]:
        """v2 数据：剧本模式按序 items（scene/line）。无 v2 数据返回 []。

        ``branch_id`` 非空时只返回该分支的 items（RPG 关卡用来按分支看）。
        """
        for ch in self.data.get("chapters", []):
            if ch.get("chapter_id") == chapter_id:
                for s in ch.get("stages", []):
                    if s.get("stage_code") == stage_code:
                        items = list(s.get("items", []))
                        if branch_id:
                            items = [i for i in items if i.get("branch") == branch_id]
                        return self._resolve(items)
        return []

    def _resolve(self, items: list[dict]) -> list[dict]:
        """数据里只存位置：文本（含说话人/小标题）现从当前语言文件读。

        没装零协时 text_source 指向英文基线，同一份剧本结构照样能读（显示英文）。
        任务骨架行（source=quest）同样只存 quest key，文本从这里现取。
        """
        src = self.text_source
        if src is None or not getattr(src, "ok", False):
            return items
        out: list[dict] = []
        for it in items:
            if it.get("source") == "quest" and not it.get("text"):
                it = dict(it)
                it["text"] = self._quest_text(src, it)
            out.append(src.resolve_item(it))
        return out

    def _quest_text(self, src, item: dict) -> str:
        """任务行文本：「【任务】Q1011 探索周围：<目标>」（数据里只存了 quest key）。"""
        rel = item.get("file")
        key = item.get("quest")
        if not rel or not key:
            return ""
        for rec in src.data_list(rel) or []:
            if not isinstance(rec, dict) or str(rec.get("key")) != str(key):
                continue
            title = (rec.get("title") or "").strip()
            desc = (rec.get("description") or "").strip()
            if not desc or _QUEST_JUNK.match(desc):
                return f"【任务】{key} {title}".strip()
            return f"【任务】{key} {title}：{desc}"
        return f"【任务】{key}"

    def stage(self, chapter_id: str, stage_code: str) -> dict | None:
        for ch in self.data.get("chapters", []):
            if ch.get("chapter_id") == chapter_id:
                for s in ch.get("stages", []):
                    if s.get("stage_code") == stage_code:
                        return s
        return None
