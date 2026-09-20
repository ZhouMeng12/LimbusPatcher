"""剧情章节/关卡推导：从文件名确定性推导「章节 → 关卡分组」。

关卡组名即文件名编码（如「第3部分」「对话 1D10」「剧情 S101」），
组内直接列出文件条目；无法推导的文件返回 None。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .categories import category_label, classify

# 规范章节顺序（章节下拉按此排序；未在表中的动态章节追加在后）
CHAPTER_ORDER: list[str] = [
    "prologue",
    "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9", "c10",
    "i35", "i45", "i55", "i65", "i75", "i75b", "i85", "i85ex",
    "walpu", "mirror", "railway", "anniv", "fools", "events",
]

CHAPTER_BASE_LABELS: dict[str, str] = {
    "prologue": "序章",
    "c1": "第1章", "c2": "第2章", "c3": "第3章", "c4": "第4章", "c5": "第5章",
    "c6": "第6章", "c7": "第7章", "c8": "第8章", "c9": "第9章", "c10": "第10章",
    "i35": "间章 3.5", "i45": "间章 4.5", "i55": "间章 5.5", "i65": "间章 6.5",
    "i75": "间章 7.5", "i75b": "间章 7.5·续", "i85": "间章 8.5", "i85ex": "间章 8.5EX",
    "anniv": "周年活动", "fools": "愚人节活动", "events": "活动",
}

_CHAPTER_RE = re.compile(r"a1c(\d+)p(\d+)", re.I)
_RAILWAY_RE = re.compile(r"Railway(?:Dungeon)?(?:Node|StationName|UI)?_?(\d+)", re.I)
_MIRROR_RE = re.compile(r"Mirror(?:Dungeon)?[A-Za-z]*[-_]?(\d+)", re.I)
_MD_RE = re.compile(r"[-_](?:MD|mr)(\d+)", re.I)
_WALPU_RE = re.compile(r"walpu(\d+)", re.I)
_ANNIV_RE = re.compile(r"Limbus\d.*Anniversary", re.I)

# 间章/活动文件名后缀（去尾部 text）→ 章节
_SUFFIX_CHAPTERS: dict[str, str] = {
    "hellschicken": "i35",
    "tkt": "i45",
    "miracle": "i55",
    "mowe": "i55",
    "twth": "i65",
    "lcbcheckup": "i75",
    "nightcleanup": "i75b",
    "night-clean-up": "i75b",
    "cultivation": "i85",
    "pilgrimage": "i85ex",
    "fools": "fools",
    "umida": "events",
    "dawnofgreenevent": "events",
    "twiningthreads": "events",
    "recordmemory": "events",
    "ycgd": "events",
    "exme": "events",
}

_LEVEL_PART = "p"

# 间章章节 id（间章剧情归入「主线剧情」分类）
INTERVAL_CHAPTERS: set[str] = {
    "i35", "i45", "i55", "i65", "i75", "i75b", "i85", "i85ex",
}


def _part_level(n: str) -> tuple[str, str]:
    return f"p{n}", f"第{n}部分"


@dataclass(frozen=True)
class StoryRef:
    chapter_id: str
    chapter_label: str
    level_key: str
    level_label: str

    def chapter_base(self) -> str:
        """去掉编号后缀的章节基名（walpu4 → walpu）。"""
        for base in ("walpu", "mirror", "railway"):
            if self.chapter_id.startswith(base):
                return base
        return self.chapter_id


def _railway_label(m: re.Match) -> str:
    num = int(m.group(1))
    if num >= 1000:
        n = int(str(num)[-3:].lstrip("0") or "1")
    else:
        n = num
    return f"折射轨道{n}号线"


def story_of(relpath: str) -> StoryRef | None:
    """返回 (章节id, 章节名, 关卡key, 关卡label)；无章节信息返回 None。"""
    # 1) 主线章节码 a1cXpY（对全部分类生效：剧情/敌方/技能…）
    m = _CHAPTER_RE.search(relpath)
    if m:
        c = m.group(1)
        level_key, level_label = _part_level(m.group(2))
        return StoryRef(f"c{c}", f"第{c}章", level_key, level_label)

    # 2) 折射轨道 / 镜牢 / 瓦夜 / 周年（先于后缀规则）
    m = _RAILWAY_RE.search(relpath)
    if m:
        label = _railway_label(m)
        return StoryRef("railway", label, "all", "全部关卡")
    m = _MD_RE.search(relpath)
    if m:
        return StoryRef(f"mirror{m.group(1)}", f"镜牢{m.group(1)}", "all", "全部关卡")
    m = _MIRROR_RE.search(relpath)
    if m:
        return StoryRef(f"mirror{m.group(1)}", f"镜牢{m.group(1)}", "all", "全部关卡")
    if relpath.lower().startswith("mirrordungeon") or relpath.lower().startswith("dungeonstartbuffs"):
        return StoryRef("mirror", "镜牢", "all", "全部关卡")
    m = _WALPU_RE.search(relpath)
    if m:
        return StoryRef(f"walpu{m.group(1)}", f"瓦夜{m.group(1)}", "all", "全部关卡")
    if _ANNIV_RE.search(relpath):
        return StoryRef("anniv", "周年活动", "all", "全部关卡")

    # 3) 间章/活动后缀
    stem = Path(relpath).stem.lower().removesuffix("text")
    for suffix, chapter in _SUFFIX_CHAPTERS.items():
        if stem.endswith(suffix) or f"-{suffix}" in stem:
            label = CHAPTER_BASE_LABELS.get(chapter, "活动")
            # 间章/活动章节内按文本类型分组
            cat = classify(relpath)
            return StoryRef(chapter, label, f"type:{cat}", category_label(cat))

    # 4) StoryData 编码
    sd = _story_data_ref(relpath)
    if sd is not None:
        return sd

    # 5) 章节节点文件
    m = re.match(r"^DungeonNode(\d)", relpath, re.I)
    if m:
        return StoryRef(f"c{m.group(1)}", f"第{m.group(1)}章", f"node{m.group(1)}", f"节点 {m.group(1)}")
    m = re.match(r"^DungeonArea(\d)", relpath, re.I)
    if m:
        return StoryRef(f"c{m.group(1)}", f"第{m.group(1)}章", f"area{m.group(1)}", f"区域 {m.group(1)}")
    m = re.match(r"^StageNode(\d)", relpath, re.I)
    if m:
        return StoryRef(f"c{m.group(1)}", f"第{m.group(1)}章", f"stage{m.group(1)}", f"关卡 {m.group(1)}")
    return None


def _story_data_ref(relpath: str) -> StoryRef | None:
    """StoryData 目录内 S/P/E/D 编码的章节与关卡。"""
    m = re.match(r"^StoryData/(\d)D(\d{3})", relpath, re.I)
    if m:
        c = m.group(1)
        level = f"{c}D{m.group(2)[:2]}"
        return StoryRef(f"c{c}", f"第{c}章", level, f"对话 {level}")
    # S999 特判：S9991B 为第10章（Canto X）隐藏文本，须在两位数正则之前拦截，
    # 否则会被 S(\d{2})(\d{2}) 误读为第99章。
    m = re.match(r"^StoryData/S999", relpath, re.I)
    if m:
        return StoryRef("c10", "第10章", "S9991", "剧情 S9991")
    # S 两位数章节优先（S1000B → 第10章 关卡00；S901B 等 3 位数字不匹配自动回退）
    m = re.match(r"^StoryData/S(\d{2})(\d{2})", relpath, re.I)
    if m:
        c = m.group(1)
        level = f"S{c}{m.group(2)}"
        return StoryRef(f"c{c}", f"第{c}章", level, f"剧情 {level}")
    m = re.match(r"^StoryData/S(\d)(\d{2})", relpath, re.I)
    if m:
        c = m.group(1)
        if c == "0":
            return StoryRef("prologue", "序章", f"S0{m.group(2)}", f"剧情 S0{m.group(2)}")
        level = f"S{c}{m.group(2)}"
        return StoryRef(f"c{c}", f"第{c}章", level, f"剧情 {level}")
    # P 两位数章节（6 位数字，如 P120101 → 第12章）
    m = re.match(r"^StoryData/P(\d{2})(\d{2})(\d{2})", relpath, re.I)
    if m:
        c = m.group(1)
        level = f"P{c}{m.group(2)}"
        return StoryRef(f"c{c}", f"第{c}章", level, f"演出 {level}")
    # P 第10章演出（5 位数字，仅 P10416 / P10816 两个补译文件）
    m = re.match(r"^StoryData/P(10)(?:[48])16", relpath, re.I)
    if m:
        return StoryRef("c10", "第10章", f"P{m.group(1)}", f"演出 P{m.group(1)}")
    m = re.match(r"^StoryData/P(\d)(\d{2})(\d{2})", relpath, re.I)
    if m:
        c = m.group(1)
        level = f"P{c}{m.group(2)}"
        return StoryRef(f"c{c}", f"第{c}章", level, f"演出 {level}")
    m = re.match(r"^StoryData/E(\d{2})(\d)", relpath, re.I)
    if m:
        code = m.group(1)
        level = f"E{code}{m.group(2)}"
        if code == "00":
            return StoryRef("prologue", "序章", level, f"事件 {level}")
        c = str(int(code))
        return StoryRef(f"c{c}", f"第{c}章", level, f"事件 {level}")
    return None


def chapter_sort_key(chapter_id: str) -> tuple[int, int, str]:
    """章节下拉排序：按 CHAPTER_ORDER，未知章节按字符串追加在后。"""
    base = chapter_id
    if chapter_id.startswith("walpu") or chapter_id.startswith("mirror") or chapter_id.startswith("railway"):
        base = chapter_id.rstrip("0123456789") or chapter_id
    if base in CHAPTER_ORDER:
        return (0, CHAPTER_ORDER.index(base), chapter_id)
    return (1, 0, chapter_id)
