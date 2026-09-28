"""人格 / E.G.O 图鉴的数据层：把散落的技能、剧情、语音、元数据组装成实体卡片。

数据来源（全部只读）：
  · entities 表（人格/EGO 本体、赛季、计数）
  · Skills_Personality-<SS>.json / Skills_Ego*.json（技能：levelList 各等级 + coinlist 硬币效果）
  · StoryData/P<人格id>.json（人格剧情：teller/title/content/place）
  · PersonalityVoiceDlg/Voice_*_<人格id>.json（语音：id 形如 get_10310_1，desc 是类别中文名，dlg 是台词）
  · EGOVoiceDig/Voice_EGO_<罪人>_<n>.json（EGO 语音，按罪人归档）
  · Personality_Get_Condition.json / EGO_Get_Condition.json（获取条件）
  · season_map.json（赛季 / 获取方式 / 英文名）
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .bubble_map import lines_for as bubble_lines_for
from .entities import (
    KIND_EGO,
    KIND_PERSONALITY,
    ROLE_EGO,
    ROLE_EGO_PASSIVE,
    ROLE_EGO_SKILL,
    ROLE_EGO_VOICE,
    ROLE_IDENTITY,
    ROLE_IDENTITY_PASSIVE,
    ROLE_IDENTITY_SKILL,
    ROLE_IDENTITY_STORY,
    ROLE_IDENTITY_VOICE,
    entity_key,
    file_entity,
    parse_entity_key,
    split_entity_id,
)
from .patch import walk_leaves
from .season import MetaMaps
from .textsource import speaker_of

# 语音类别里挑出来做常用排序（其余按出现顺序）
VOICE_ORDER = ["获得人格", "人格出战", "进入战斗", "战斗胜利", "EX CLEAR战斗胜利", "战斗失败",
               "判定成功", "判定失败", "闲置", "早间问候", "午间问候", "晚间问候"]

_GET_COND_SUFFIX = ("_normal", "_gacksung")

#: 本体记录里可编辑文本的中文标签（人格 / E.G.O 各一套）
SELF_TEXT_LABELS: dict[str, dict[str, str]] = {
    KIND_PERSONALITY: {"title": "人格名称", "name": "罪人名", "nameWithTitle": "显示名", "desc": "简介"},
    KIND_EGO: {"title": "E.G.O 名称", "name": "E.G.O 名称", "nameWithTitle": "显示名", "desc": "简介"},
}
#: 界面上按这个顺序排（人格名称最常用）
SELF_TEXT_ORDER = ("title", "name", "nameWithTitle", "desc")


@dataclass
class CodexSkillLevel:
    level: int
    name: str
    desc: str = ""
    desc_fp: list = field(default_factory=list)      # 等级效果的字段路径（可编辑）
    coins: list[tuple[str, list]] = field(default_factory=list)  # [(硬币文本, 字段路径)]
    #: 风味小字（第 9 章起游戏开始给技能写 flavor，图鉴按小字展示）
    flavor: str = ""
    flavor_fp: list = field(default_factory=list)


@dataclass
class CodexSkill:
    record_index: int
    skill_id: int
    seq: int                  # 该人格下的技能序号（id % 100）
    file: str = ""            # 所在文件（相对零协包）
    name: str = ""
    name_fp: list = field(default_factory=list)  # 技能名字段的路径（可编辑）
    levels: list[CodexSkillLevel] = field(default_factory=list)
    # 只读数值（来自 wiki / 数据表，缺失时为空）
    stats: dict = field(default_factory=dict)

    @property
    def coin_count(self) -> int:
        return max((len(lv.coins) for lv in self.levels), default=0)

    @property
    def label(self) -> str:
        return self.name or f"技能 {self.seq}"


@dataclass
class CodexStoryLine:
    record_index: int
    record_id: object = None   # 记录自身的 id（编辑时定位用；剧情记录有 id，语音是字符串 id）
    file: str = ""
    fp: list = field(default_factory=list)
    teller: str = ""
    title: str = ""
    place: str = ""
    text: str = ""


@dataclass
class CodexVoice:
    record_index: int
    record_id: object = None
    file: str = ""
    fp: list = field(default_factory=list)
    key: str = ""             # 记录 id，如 get_10310_1
    category: str = ""        # desc，如「获得人格」「战斗胜利」
    text: str = ""            # dlg


@dataclass
class CodexPassive:
    """被动能力（人格 = Passives.json，E.G.O = Passive_Ego.json，结构同为 id/name/desc）。"""
    record_index: int
    record_id: object = None
    file: str = ""
    seq: int = 0
    name: str = ""
    name_fp: list = field(default_factory=list)
    desc: str = ""
    desc_fp: list = field(default_factory=list)
    #: 风味小字（第 9 章起的被动大量带 flavor，图鉴按小字展示）
    flavor: str = ""
    flavor_fp: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.name or f"被动 {self.seq}"


@dataclass
class CodexSelfText:
    """实体本体（Personalities / Egos 记录）上可编辑的文本，如「人格名称」。"""
    key: str
    label: str
    text: str = ""
    fp: list = field(default_factory=list)


@dataclass
class CodexEntity:
    entity_key: str
    kind: str
    entity_id: int
    name: str = ""
    title: str = ""
    seq: int = 0
    sinner_code: str = ""
    sinner_name: str = ""
    desc: str = ""
    variant: str | None = None
    season: str = ""
    season_label: str = ""
    acq_label: str = ""
    name_en: str = ""
    get_conditions: list[str] = field(default_factory=list)
    skills: list[CodexSkill] = field(default_factory=list)
    passives: list[CodexPassive] = field(default_factory=list)
    story_lines: list[CodexStoryLine] = field(default_factory=list)
    voices: list[CodexVoice] = field(default_factory=list)
    bubbles: list[CodexVoice] = field(default_factory=list)  # 战中气泡（通用文件，只读展示）
    portrait: Path | None = None
    # 本体记录（改人格/EGO 名称、简介用）
    self_file: str = ""
    self_record_index: int = 0
    self_record_id: object = None
    self_texts: list[CodexSelfText] = field(default_factory=list)

    def self_text(self, key: str) -> CodexSelfText | None:
        return next((t for t in self.self_texts if t.key == key), None)

    @property
    def kind_label(self) -> str:
        return "人格" if self.kind == KIND_PERSONALITY else "E.G.O"

    @property
    def ordinal(self) -> str:
        if self.kind == KIND_EGO:
            # 以游戏原文为准（desc 写「基础E.G.O装备」/「专用E.G.O装备」），取不到再按序号
            if "基础" in self.desc:
                return "基础"
            if "专用" in self.desc:
                return "专用"
            return "基础" if self.seq <= 1 else "专用"
        return f"第{self.seq}人格"

    def voice_groups(self) -> list[tuple[str, list[CodexVoice]]]:
        """按类别分组（常用类别优先，其余按首次出现顺序）。"""
        buckets: dict[str, list[CodexVoice]] = {}
        for v in self.voices:
            buckets.setdefault(v.category or "其他", []).append(v)
        def sort_key(cat: str) -> tuple:
            idx = VOICE_ORDER.index(cat) if cat in VOICE_ORDER else len(VOICE_ORDER)
            return (idx, cat)
        return [(c, buckets[c]) for c in sorted(buckets, key=sort_key)]


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _records(path: Path) -> list:
    data = _load(path)
    dl = data.get("dataList") if isinstance(data, dict) else None
    return dl if isinstance(dl, list) else []


def _skill_of_record(record: dict, record_index: int, rel: str = "", divisor: int = 100) -> CodexSkill | None:
    """技能记录 → 技能卡片（用 walk_leaves 记下每个可编辑文本的字段路径）。"""
    rid = record.get("id")
    if not isinstance(rid, int):
        return None
    skill = CodexSkill(record_index=record_index, skill_id=rid, seq=rid % divisor, file=rel)
    levels: dict[int, CodexSkillLevel] = {}
    for fp, text in walk_leaves(record):
        kinds = [seg.get("k") for seg in fp if "k" in seg]
        idxs = [seg.get("i") for seg in fp if "i" in seg]
        if not kinds or kinds[0] != "levelList" or not idxs:
            continue
        li = idxs[0]
        level = levels.get(li)
        if level is None:
            raw = (record.get("levelList") or [])[li] if li < len(record.get("levelList") or []) else {}
            level = CodexSkillLevel(level=int((raw or {}).get("level") or 0),
                                    name=str((raw or {}).get("name") or ""))
            levels[li] = level
        last = kinds[-1]
        if last == "desc" and kinds[1:2] != ["coinlist"]:
            # 等级说明（用最新的非空文本，等级 1 常为空）
            if text.strip() or not level.desc:
                level.desc = text
                level.desc_fp = fp
        elif last == "desc" and "coinlist" in kinds:
            level.coins.append((text, fp))
        elif last == "flavor":
            level.flavor, level.flavor_fp = text, fp
        if level.name and not skill.name:
            skill.name = level.name
    skill.levels = [levels[i] for i in sorted(levels)]
    return skill


def _passive_of_record(record: dict, record_index: int, rel: str, entity_id: int) -> CodexPassive | None:
    """被动记录 → 被动卡片（id = 实体 id × 100 + 序号）。"""
    rid = record.get("id")
    if not isinstance(rid, int) or rid // 100 != entity_id:
        return None
    psv = CodexPassive(record_index=record_index, record_id=rid, file=rel, seq=rid % 100)
    for fp, text in walk_leaves(record):
        kinds = [seg.get("k") for seg in fp if "k" in seg]
        if not kinds:
            continue
        if kinds[-1] == "name":
            psv.name, psv.name_fp = text, fp
        elif kinds[-1] == "desc":
            psv.desc, psv.desc_fp = text, fp
        elif kinds[-1] == "flavor":
            psv.flavor, psv.flavor_fp = text, fp
    return psv


def _self_texts_of_record(record: dict, kind: str) -> list[CodexSelfText]:
    labels = SELF_TEXT_LABELS.get(kind, {})
    found: dict[str, CodexSelfText] = {}
    for fp, text in walk_leaves(record):
        kinds = [seg.get("k") for seg in fp if "k" in seg]
        if len(kinds) != 1 or kinds[0] not in labels:
            continue
        found[kinds[0]] = CodexSelfText(key=kinds[0], label=labels[kinds[0]], text=text, fp=fp)
    return [found[k] for k in SELF_TEXT_ORDER if k in found]


def _is_self_record(rid: object, entity_id: int, role: str) -> bool:
    """本体记录是否属于该实体（E.G.O 的 6 位变体 id 也算基础实体）。"""
    if not isinstance(rid, int):
        return False
    if rid == entity_id:
        return True
    return role == ROLE_EGO and 200000 <= rid <= 299999 and rid // 10 == entity_id


def build_entity(llc_dir: Path, summary: dict, maps: MetaMaps | None = None) -> CodexEntity:
    """按 entities 表的一行（summary）组装完整卡片。"""
    key = summary["entity_key"]
    parsed = parse_entity_key(key)
    kind, entity_id = parsed if parsed else (KIND_PERSONALITY, 0)
    ent = CodexEntity(
        entity_key=key, kind=kind, entity_id=entity_id,
        name=summary.get("name") or "", title=summary.get("title") or "",
        seq=int(summary.get("seq") or 0), sinner_code=summary.get("sinner_code") or "",
        sinner_name=summary.get("sinner_name") or "", desc=summary.get("desc") or "",
        variant=summary.get("variant"),
        self_file=summary.get("source_file") or "",
    )
    meta = (maps or MetaMaps()).identity_meta(entity_id) if kind == KIND_PERSONALITY \
        else (maps or MetaMaps()).ego_meta(entity_id)
    if meta:
        from .season import acq_display, season_display

        ent.season = season_display(meta) or ""
        ent.season_label = season_display(meta) or ""
        # 只显示中文徽标：base/seasonal 不显示，其余（瓦夜/通行证/活动）给中文；绝不回落成 acq 原始英文值
        ent.acq_label = acq_display(meta) or ""
        ent.name_en = meta.get("name_en") or ""

    llc = Path(llc_dir)
    self_rel = ent.self_file
    for path in sorted(llc.rglob("*.json")):
        rel = path.relative_to(llc).as_posix()
        info = file_entity(rel)
        if info is None or info.role not in (ROLE_IDENTITY_SKILL, ROLE_IDENTITY_STORY,
                                             ROLE_IDENTITY_VOICE, ROLE_IDENTITY_PASSIVE,
                                             ROLE_EGO_SKILL, ROLE_EGO_PASSIVE, ROLE_EGO_VOICE,
                                             ROLE_IDENTITY, ROLE_EGO):
            continue
        if rel == self_rel and info.role in (ROLE_IDENTITY, ROLE_EGO):
            # 本体记录：取出「人格名称 / 罪人名 / 简介」等可编辑文本的字段路径
            for i, rec in enumerate(_records(path)):
                if isinstance(rec, dict) and _is_self_record(rec.get("id"), entity_id, info.role):
                    ent.self_record_index = i
                    ent.self_record_id = rec.get("id")
                    ent.self_texts = _self_texts_of_record(rec, kind)
                    break
            continue
        if not self_rel and info.role in (ROLE_IDENTITY, ROLE_EGO) and info.kind == kind:
            # 索引里没记住本体文件时兜底：扫到哪个本体文件里有这个 id 就用哪个
            for i, rec in enumerate(_records(path)):
                if isinstance(rec, dict) and _is_self_record(rec.get("id"), entity_id, info.role):
                    ent.self_file, ent.self_record_index = rel, i
                    ent.self_record_id = rec.get("id")
                    ent.self_texts = _self_texts_of_record(rec, kind)
                    break
            if ent.self_texts:
                continue
        records = _records(path)
        if info.role in (ROLE_IDENTITY_SKILL, ROLE_EGO_SKILL):
            for i, rec in enumerate(records):
                if not isinstance(rec, dict):
                    continue
                rid = rec.get("id")
                if not isinstance(rid, int) or rid // 100 != entity_id:
                    continue
                skill = _skill_of_record(rec, i, rel)
                if skill:
                    ent.skills.append(skill)
        elif info.role in (ROLE_IDENTITY_PASSIVE, ROLE_EGO_PASSIVE):
            for i, rec in enumerate(records):
                if not isinstance(rec, dict):
                    continue
                psv = _passive_of_record(rec, i, rel, entity_id)
                if psv:
                    ent.passives.append(psv)
        elif info.role == ROLE_IDENTITY_STORY:
            if info.entity_id != entity_id:
                continue
            for i, rec in enumerate(records):
                if isinstance(rec, dict):
                    ent.story_lines.append(CodexStoryLine(
                        record_index=i, record_id=rec.get("id"), file=rel, fp=[{"k": "content"}],
                        teller=speaker_of(rec, [llc]) or "",
                        title=str(rec.get("title") or ""), place=str(rec.get("place") or ""),
                        text=str(rec.get("content") or "")))
        elif info.role == ROLE_IDENTITY_VOICE:
            if info.entity_id != entity_id:
                continue
            for i, rec in enumerate(records):
                if isinstance(rec, dict):
                    ent.voices.append(CodexVoice(record_index=i, record_id=rec.get("id"),
                                                 file=rel, fp=[{"k": "dlg"}],
                                                 key=str(rec.get("id") or ""),
                                                 category=str(rec.get("desc") or ""),
                                                 text=str(rec.get("dlg") or "")))
        elif info.role == ROLE_EGO_VOICE:
            for i, rec in enumerate(records):
                if not isinstance(rec, dict):
                    continue
                # EGO 语音记录 id 里带 EGO id（battle_awaken_20301_1）→ 精确归属
                m = re.search(r"_(\d{5})_", str(rec.get("id") or ""))
                if not m or int(m.group(1)) != entity_id:
                    continue
                ent.voices.append(CodexVoice(record_index=i, record_id=rec.get("id"),
                                             file=rel, fp=[{"k": "dlg"}],
                                             key=str(rec.get("id") or ""),
                                             category=str(rec.get("desc") or ""),
                                             text=str(rec.get("dlg") or "")))
    ent.skills.sort(key=lambda s: s.seq)
    ent.passives.sort(key=lambda p: (p.seq, p.file))
    ent.get_conditions = load_get_conditions(llc, entity_id, kind)
    # 战中气泡（通用 BattleSpeechBubbleDlg.json）：按 id 内嵌单位数字关联人格/E.G.O，只读展示
    ent.bubbles = [CodexVoice(record_index=b.record_index, record_id=b.record_id, file=b.file,
                              fp=[{"k": "dlg"}], key=b.key, category=b.category, text=b.text)
                   for b in bubble_lines_for(str(llc), entity_id)]
    return ent


_SINNER_EN = {"YiSang": "01", "Faust": "02", "DonQuixote": "03", "Ryoshu": "04", "Meursault": "05",
              "HongLu": "06", "Heathcliff": "07", "Ishmael": "08", "Rodya": "09", "Sinclair": "10",
              "Outis": "11", "Gregor": "12"}


def _sinner_en(name: str) -> str | None:
    return _SINNER_EN.get(name)


def load_get_conditions(llc_dir: Path, entity_id: int, kind: str) -> list[str]:
    """获取条件（人格/EGO 各一份表）。"""
    name = "Personality_Get_Condition.json" if kind == KIND_PERSONALITY else "EGO_Get_Condition.json"
    out: list[str] = []
    for rec in _records(Path(llc_dir) / name):
        if not isinstance(rec, dict):
            continue
        rid = str(rec.get("id") or "")
        if rid.startswith(f"{entity_id}_") and rid.endswith(_GET_COND_SUFFIX):
            text = str(rec.get("content") or "").strip()
            if text:
                out.append(text)
    return out
