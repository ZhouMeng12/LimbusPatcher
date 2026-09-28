"""敌方图鉴的数据层：把散落的敌人本体、部位、技能、被动、元数据组装成实体卡片。

数据来源（全部只读）：
  · entities 表（敌方本体 name/desc、计数；faction 仅英文名录）
  · Enemies*.json（本体 / 部位：id/name/desc，desc 区分 本体/部位/敌方单位/敌方头目）
  · Skills_Enemy*.json（技能：id/levelList[{level,name,desc,coinlist}]）
  · Passives_Enemy*.json（被动：id/name/desc）
  · enemy_map.json（598 条：id → group/label/name_en/dimensions）

实体关联规则（已实测）：
  · 本体 id 本身（Enemies*.json 中 desc != "部位"）
  · 部位 id 6 位且 id // 100 是本体 id（或 desc == "部位"）→ 并入本体详情标注展示
  · 技能 id // 100 == 敌人 id
  · 被动 id 本身是敌人 id 或 id // 100 是敌人 id
  · 章节变体按 id 聚合（同一敌人 id 分布在多个 Enemies-*.json 只算一个实体）
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .bubble_map import lines_for as bubble_lines_for
from .codex import CodexPassive, CodexSkill, CodexSkillLevel, CodexVoice, _records, walk_leaves
from .entities import (
    KIND_ENEMY,
    ROLE_ENEMY,
    ROLE_ENEMY_PASSIVE,
    ROLE_ENEMY_SKILL,
    _enemy_parent_id,
    file_entity,
    parse_entity_key,
)
from .season import MetaMaps, kind_display

#: 一级分组 → 中文名（与 enemy_map.json 的 group 字段一致）
GROUP_LABELS: dict[str, str] = {
    "abnormality": "异想体",
    "unit": "敌方单位",
    "faction": "阵营",
}

#: 二级筛选维度枚举的中文映射
CHAPTER_TYPE_LABELS: dict[str, str] = {
    "main": "主线",
    "interchapter": "间章",
    "other": "其他",
    "walpurgis": "瓦夜",
}
ENEMY_TYPE_LABELS: dict[str, str] = {
    "normal": "普通",
    "elite": "精英",
    "branch": "支线",
}
DANGER_LEVEL_LABELS: dict[str, str] = {
    "ZAYIN": "ZAYIN",
    "TETH": "TETH",
    "HE": "HE",
    "WAW": "WAW",
    "ALEPH": "ALEPH",
}

#: 本体记录里可编辑文本的中文标签（敌方）
SELF_TEXT_LABELS: dict[str, str] = {"name": "名称", "desc": "简介"}
SELF_TEXT_ORDER = ("name", "desc")


@dataclass
class EnemyPart:
    """敌方部位（并入本体详情标注展示，不可单独成实体）。"""
    record_index: int
    record_id: object = None
    file: str = ""
    seq: int = 0
    name: str = ""
    name_fp: list = field(default_factory=list)
    desc: str = ""
    desc_fp: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.name or f"部位 {self.seq}"


@dataclass
class CodexSelfText:
    """实体本体（Enemies 记录）上可编辑的文本，如「名称」「简介」。"""
    key: str
    label: str
    text: str = ""
    fp: list = field(default_factory=list)


@dataclass
class CodexEnemy:
    entity_key: str
    kind: str = KIND_ENEMY
    entity_id: int = 0
    name: str = ""
    desc: str = ""
    group: str = ""          # abnormality / unit / faction
    group_label: str = ""    # 异想体 / 敌方单位 / 阵营
    name_en: str = ""
    dimensions: dict = field(default_factory=dict)  # chapter_type / enemy_type / danger_level
    parts: list[EnemyPart] = field(default_factory=list)
    skills: list[CodexSkill] = field(default_factory=list)
    passives: list[CodexPassive] = field(default_factory=list)
    self_file: str = ""
    self_record_index: int = 0
    self_record_id: object = None
    self_texts: list[CodexSelfText] = field(default_factory=list)
    bubbles: list[CodexVoice] = field(default_factory=list)  # 战中气泡（前1-9章，只读展示）

    def self_text(self, key: str) -> CodexSelfText | None:
        return next((t for t in self.self_texts if t.key == key), None)

    @property
    def kind_label(self) -> str:
        return "敌方"

    @property
    def is_faction(self) -> bool:
        return self.group == "faction"

    def dimension_label(self, key: str) -> str:
        raw = self.dimensions.get(key) if isinstance(self.dimensions, dict) else None
        if not raw:
            return ""
        table = {"chapter_type": CHAPTER_TYPE_LABELS,
                 "enemy_type": ENEMY_TYPE_LABELS,
                 "danger_level": DANGER_LEVEL_LABELS}.get(key, {})
        return table.get(raw, raw)


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _self_texts_of_record(record: dict) -> list[CodexSelfText]:
    found: dict[str, CodexSelfText] = {}
    for fp, text in walk_leaves(record):
        kinds = [seg.get("k") for seg in fp if "k" in seg]
        if len(kinds) != 1 or kinds[0] not in SELF_TEXT_LABELS:
            continue
        found[kinds[0]] = CodexSelfText(key=kinds[0], label=SELF_TEXT_LABELS[kinds[0]],
                                        text=text, fp=fp)
    return [found[k] for k in SELF_TEXT_ORDER if k in found]


def _enemy_skill_of_record(record: dict, record_index: int, rel: str = "") -> CodexSkill | None:
    """敌方技能记录 → 技能卡片（levelList 各等级 + coinlist 硬币效果）。"""
    rid = record.get("id")
    if not isinstance(rid, int):
        return None
    skill = CodexSkill(record_index=record_index, skill_id=rid, seq=rid % 100, file=rel)
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
            if text.strip() or not level.desc:
                level.desc = text
                level.desc_fp = fp
        elif last == "desc" and "coinlist" in kinds:
            level.coins.append((text, fp))
        elif last == "flavor":
            level.flavor, level.flavor_fp = text, fp
        if level.name and not skill.name:
            skill.name = level.name
            skill.name_fp = fp
    skill.levels = [levels[i] for i in sorted(levels)]
    return skill


def _enemy_passive_of_record(record: dict, record_index: int, rel: str, entity_id: int) -> CodexPassive | None:
    """敌方被动记录 → 被动卡片（id 本身是敌人 id 或 id//100 是敌人 id）。"""
    rid = record.get("id")
    if not isinstance(rid, int):
        return None
    if rid != entity_id and rid // 100 != entity_id:
        return None
    psv = CodexPassive(record_index=record_index, record_id=rid, file=rel,
                       seq=(rid if rid == entity_id else rid % 100))
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


#: 多阶段敌人的形态缓存：(文件集合指纹) → {(name, desc): {文件: [id, ...]}}
_VARIANT_CACHE: dict = {}


def _enemy_files(dirs: list[Path]) -> list[Path]:
    out: list[Path] = []
    for d in dirs:
        if d and Path(d).is_dir():
            out.extend(sorted(Path(d).glob("Enemies*.json")))
    return [p for p in out if "ResultLog" not in p.name]


def _variant_index(dirs: list[Path]) -> dict:
    """{（名字, 描述）: {文件: [id…]}}：用于判断同一个敌人的多个形态。"""
    key = tuple(str(p) for p in _enemy_files(dirs))
    cached = _VARIANT_CACHE.get(key)
    if cached is not None:
        return cached
    table: dict = {}
    for p in _enemy_files(dirs):
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        for rec in data.get("dataList") or []:
            if not isinstance(rec, dict):
                continue
            rid, name = rec.get("id"), rec.get("name")
            desc = rec.get("desc") or ""
            if not isinstance(rid, int) or not name or desc == "部位":
                continue
            table.setdefault((name, desc), {}).setdefault(p.name, []).append(rid)
    _VARIANT_CACHE[key] = table
    return table


#: 已知多阶段 BOSS：同文件同名同 desc 但 id 不连续，连续规则识别不到，
#: 这里显式声明形态组（键 = (文件名, 名字, desc)，值 = 按战斗顺序的 id 列表）。
MULTI_PHASE_OVERRIDES: dict[tuple[str, str, str], list[int]] = {
    # c7-36 堂吉诃德：8390 摩天轮形态（部位 839001 大摩天轮、技能 838005-838010）→ 8410 最终形态
    ("Enemies-a1c7p3.json", "堂吉诃德", "头目"): [8390, 8410],
    # c8 贾丘：1137 第一形态 → 1141 第二形态（咒杀）
    ("Enemies-a1c8p2.json", "贾丘", ""): [1137, 1141],
}

#: 技能归属覆盖：部分 BOSS 的技能 id 用了其它敌人的 id 段（//100 规则会挂错父）。
#: 如堂吉诃德 8390 的摩天轮技能 838005-838010 实际是 8380 桑丘的 id 段。
_SKILL_PARENT_OVERRIDES: dict[int, int] = {
    838005: 8390, 838006: 8390, 838007: 8390,
    838008: 8390, 838009: 8390, 838010: 8390,
}


def phase_variants(llc_dir: Path, entity_id: int, extra_dirs: list | None = None) -> list[dict]:
    """同一敌人的多个形态（含自身）；只有一个形态时返回单个元素。

    判定：**同一个 Enemies 文件 + 名字与描述完全相同 + id 连续**。
    例：里恩 1347/1348（9-50 打的是第二阶段 1348）、折射里恩 9551/9552。
    只按名字分组会把「不识数的流氓 90004/99005/…」这类跨难度同名的 12 个 id 也算进来，
    所以要求 id 连续——游戏里 BOSS 的多阶段就是这么编号的。
    个别 BOSS 形态 id 不连续（堂吉诃德 8390/8410、贾丘 1137/1141），
    由 :data:`MULTI_PHASE_OVERRIDES` 显式声明。
    """
    dirs = [Path(llc_dir)] + [Path(d) for d in (extra_dirs or [])]
    table = _variant_index(dirs)
    for (name, desc), by_file in table.items():
        for fname, ids in by_file.items():
            if entity_id not in ids:
                continue
            override = MULTI_PHASE_OVERRIDES.get((fname, name, desc))
            if override and entity_id in override:
                return [{"id": i, "name": name, "desc": desc, "file": fname,
                         "label": f"形态 {n + 1}" if len(override) > 1 else "形态 1"}
                        for n, i in enumerate(override)]
            run = sorted(ids)
            # 只取包含自身的那段连续 id
            start = run.index(entity_id)
            lo = start
            while lo > 0 and run[lo - 1] == run[lo] - 1:
                lo -= 1
            hi = start
            while hi + 1 < len(run) and run[hi + 1] == run[hi] + 1:
                hi += 1
            group = run[lo:hi + 1]
            return [{"id": i, "name": name, "desc": desc, "file": fname,
                     "label": f"形态 {n + 1}" if len(group) > 1 else "形态 1"}
                    for n, i in enumerate(group)]
    return [{"id": entity_id, "name": "", "desc": "", "file": "", "label": "形态 1"}]


def build_enemy(llc_dir: Path, summary: dict, maps: MetaMaps | None = None,
                extra_dirs: list | None = None) -> CodexEnemy:
    """按 entities 表的一行（summary）组装完整敌方卡片。

    ``extra_dirs``：除零协包外额外扫描的 JSON 目录（如 supplement 补译目录），
    新章节敌人（零协包无文件）的 self_texts / skills / passives 从这些目录读取。
    """
    key = summary["entity_key"]
    parsed = parse_entity_key(key)
    kind, entity_id = parsed if parsed else (KIND_ENEMY, int(summary.get("entity_id") or 0))
    ent = CodexEnemy(
        entity_key=key, kind=kind, entity_id=entity_id,
        name=summary.get("name") or "", desc=summary.get("desc") or "",
        self_file=summary.get("source_file") or "",
    )
    meta = (maps or MetaMaps()).enemy_meta(entity_id)
    if meta:
        ent.group = str(meta.get("group") or "")
        ent.group_label = GROUP_LABELS.get(ent.group, kind_display(meta) or ent.group)
        ent.name_en = str(meta.get("name_en") or "")
        dims = meta.get("dimensions")
        ent.dimensions = dict(dims) if isinstance(dims, dict) else {}

    llc = Path(llc_dir)
    self_rel = ent.self_file
    roots: list[Path] = [llc]
    for d in extra_dirs or []:
        p = Path(d)
        if p.is_dir():
            roots.append(p)
    for root in roots:
        for path in sorted(root.rglob("*.json")):
            rel = path.relative_to(root).as_posix()
            info = file_entity(rel)
            if info is None or info.role not in (ROLE_ENEMY, ROLE_ENEMY_SKILL, ROLE_ENEMY_PASSIVE):
                continue
            if info.role == ROLE_ENEMY:
                # 本体 / 部位同文件（Enemies*.json）
                for i, rec in enumerate(_records(path)):
                    if not isinstance(rec, dict):
                        continue
                    rid = rec.get("id")
                    if not isinstance(rid, int):
                        continue
                    is_part = (str(rec.get("desc") or "") == "部位") or (rid >= 100000 and rid // 100 == entity_id)
                    if rid == entity_id and not is_part:
                        # 本体记录：取「名称 / 简介」可编辑文本的字段路径
                        # 注意不能 break：本体记录之后可能还有部位记录（如 1484 → 148401），
                        # 提前跳出会漏掉该文件里排在本体后面的部位。
                        if rel == self_rel or not ent.self_texts:
                            ent.self_record_index = i
                            ent.self_record_id = rid
                            ent.self_texts = _self_texts_of_record(rec)
                    elif is_part and rid // 100 == entity_id:
                        if any(p.record_id == rid for p in ent.parts):
                            continue
                        part = EnemyPart(record_index=i, record_id=rid, file=rel, seq=rid % 100)
                        for fp, text in walk_leaves(rec):
                            kinds = [seg.get("k") for seg in fp if "k" in seg]
                            if not kinds:
                                continue
                            if kinds[-1] == "name":
                                part.name, part.name_fp = text, fp
                            elif kinds[-1] == "desc":
                                part.desc, part.desc_fp = text, fp
                        ent.parts.append(part)
                continue
            if info.role == ROLE_ENEMY_SKILL:
                for i, rec in enumerate(_records(path)):
                    if not isinstance(rec, dict):
                        continue
                    rid = rec.get("id")
                    if not isinstance(rid, int):
                        continue
                    parent = _SKILL_PARENT_OVERRIDES.get(rid, _enemy_parent_id(rid))
                    if parent != entity_id:
                        continue
                    skill = _enemy_skill_of_record(rec, i, rel)
                    if skill:
                        ent.skills.append(skill)
                continue
            if info.role == ROLE_ENEMY_PASSIVE:
                for i, rec in enumerate(_records(path)):
                    if not isinstance(rec, dict):
                        continue
                    psv = _enemy_passive_of_record(rec, i, rel, entity_id)
                    if psv:
                        ent.passives.append(psv)
    ent.skills.sort(key=lambda s: (s.seq, s.file))
    ent.passives.sort(key=lambda p: (p.seq, p.file))
    ent.parts.sort(key=lambda p: (p.seq, p.file))
    # 战中气泡（前1-9章）：按敌人 id 关联 BattleSpeechBubbleDlg 台词，只读展示
    ent.bubbles = [CodexVoice(record_index=b.record_index, record_id=b.record_id, file=b.file,
                              fp=[{"k": "dlg"}], key=b.key, category=b.category, text=b.text)
                   for b in bubble_lines_for(str(llc), entity_id)]
    return ent
