"""人格 / E.G.O 实体识别：从文件名与记录 id 推导「实体 + 角色」。

游戏自带规律（均由真实包实测确认）：
  · 人格本体   Personalities(-x1p1c1)?.json          id = 1<罪人码2位><序号2位>，如 10310
  · 人格技能   Skills_Personality-<罪人码>.json        记录 id = 人格id × 100 + 技能号（1010501 → 10105）
  · 人格剧情   StoryData/P<人格id>[变体].json          文件名即人格 id（P10710A → 10710，变体 A）
  · 人格语音   PersonalityVoiceDlg/Voice_<名>_<变体>_<人格id>.json
  · E.G.O 本体 Egos(-a1c9p3)?.json                    id = 2<罪人码2位><序号2位>，如 20106
  · E.G.O 技能 Skills_Ego(_Personality-<罪人码>)?.json  记录 id = EGO id × 100 + 技能号（2010611 → 20106）
  · E.G.O 语音 EGOVoiceDig/Voice_EGO_<罪人>_<n>.json   文件名不含 EGO id，只按罪人归档

解析不出来的文件一律返回 None（归类交给 categories），不影响既有分类与兼容性判定。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# ---- 实体种类 / 角色 ----
KIND_PERSONALITY = "personality"
KIND_EGO = "ego"
KIND_ENEMY = "enemy"
KIND_LABELS = {KIND_PERSONALITY: "人格", KIND_EGO: "E.G.O", KIND_ENEMY: "敌方"}

ROLE_IDENTITY = "identity"              # 人格本体（Personalities.json）
ROLE_IDENTITY_SKILL = "identity_skill"
ROLE_IDENTITY_PASSIVE = "identity_passive"
ROLE_IDENTITY_STORY = "identity_story"
ROLE_IDENTITY_VOICE = "identity_voice"
ROLE_EGO = "ego"                        # E.G.O 本体（Egos.json）
ROLE_EGO_SKILL = "ego_skill"
ROLE_EGO_PASSIVE = "ego_passive"
ROLE_EGO_VOICE = "ego_voice"
ROLE_ENEMY = "enemy"                    # 敌方本体（Enemies*.json）
ROLE_ENEMY_PART = "enemy_part"          # 敌方部位（6 位 id，并入本体详情）
ROLE_ENEMY_SKILL = "enemy_skill"
ROLE_ENEMY_PASSIVE = "enemy_passive"
ROLE_OTHER = "other"

ROLE_LABELS = {
    ROLE_IDENTITY: "人格",
    ROLE_IDENTITY_SKILL: "技能",
    ROLE_IDENTITY_PASSIVE: "被动",
    ROLE_IDENTITY_STORY: "剧情",
    ROLE_IDENTITY_VOICE: "语音",
    ROLE_EGO: "E.G.O",
    ROLE_EGO_SKILL: "技能",
    ROLE_EGO_PASSIVE: "被动",
    ROLE_EGO_VOICE: "语音",
    ROLE_ENEMY: "敌方",
    ROLE_ENEMY_PART: "部位",
    ROLE_ENEMY_SKILL: "技能",
    ROLE_ENEMY_PASSIVE: "被动",
    ROLE_OTHER: "其他",
}
# 界面「内容类型」下拉用：角色 → 中文（按实体种类分组显示）
CONTENT_CHOICES: dict[str, list[tuple[str, str]]] = {
    KIND_PERSONALITY: [
        ("all", "全部"),
        (ROLE_IDENTITY, "本体"),
        (ROLE_IDENTITY_SKILL, "技能"),
        (ROLE_IDENTITY_PASSIVE, "被动"),
        (ROLE_IDENTITY_STORY, "剧情"),
        (ROLE_IDENTITY_VOICE, "语音"),
    ],
    KIND_EGO: [
        ("all", "全部"),
        (ROLE_EGO, "本体"),
        (ROLE_EGO_SKILL, "技能"),
        (ROLE_EGO_PASSIVE, "被动"),
        (ROLE_EGO_VOICE, "语音"),
    ],
    KIND_ENEMY: [
        ("all", "全部"),
        (ROLE_ENEMY, "本体"),
        (ROLE_ENEMY_PART, "部位"),
        (ROLE_ENEMY_SKILL, "技能"),
        (ROLE_ENEMY_PASSIVE, "被动"),
    ],
}

_RE_PERSONALITIES = re.compile(r"^Personalities(-[a-z0-9]+)?\.json$", re.I)
_RE_EGOS = re.compile(r"^Egos(-[a-z0-9]+)?\.json$", re.I)
#: 基础人格技能（LCB 罪人的 12 个人格技能在无后缀的 Skills.json 里，不在 Skills_Personality-*.json）
_RE_SKILLS_BASE = re.compile(r"^Skills\.json$", re.I)
_RE_SKILL_PERSONALITY = re.compile(r"^Skills_Personality(-[a-z0-9]+)?\.json$", re.I)
_RE_SKILL_EGO = re.compile(r"^Skills_Ego(?:_Personality-\d{2})?(-[a-z0-9]+)?\.json$", re.I)
#: 人格被动（Passives.json 是全体人格被动总表；Passives-<后缀>.json 是活动同构表，如愚人节）
_RE_PASSIVES = re.compile(r"^Passives(-[a-z0-9]+)?\.json$", re.I)
#: E.G.O 被动总表
_RE_PASSIVE_EGO = re.compile(r"^Passive_Ego\.json$", re.I)
_RE_STORY_PERSONALITY = re.compile(r"^StoryData/P(\d{5})([A-Z]\d*)?\.json$", re.I)
_RE_VOICE_PERSONALITY = re.compile(r"^PersonalityVoiceDlg/Voice_.*_(\d{5})\.json$", re.I)
_RE_VOICE_EGO = re.compile(r"^EGOVoiceDig/Voice_EGO_([A-Za-z]+)_(\d+)\.json$", re.I)
#: 敌方本体 / 敌方技能 / 敌方被动（Enemies* / Skills_Enemy* / Passives_Enemy*）
#: 后缀支持任意段（Enemies91-4.json / Enemies_Refraction.json / Skills_Enemy_Mirror7-extreme.json）
_RE_ENEMIES = re.compile(r"^Enemies(?:[-_A-Za-z0-9]+)?\.json$", re.I)
_RE_SKILL_ENEMY = re.compile(r"^Skills_Enemy(?:[-_A-Za-z0-9]+)?\.json$", re.I)
_RE_PASSIVE_ENEMY = re.compile(r"^Passives_Enemy(?:[-_A-Za-z0-9]+)?\.json$", re.I)
#: 异想体技能 / 被动（Skills_Abnormality* / Passives_Abnormality*，镜牢异想体与主线异想体共用）
#: 异想体本体 id 为 4 位（如 8001），技能 id 可为 6 位（112601 → 1126，//100）或
#: 7 位（8001001 → 8001，//1000）；被动 id 同样支持 //100 与 //1000 两种归属。
_RE_SKILL_ABNORMALITY = re.compile(r"^Skills_Abnormality(?:[-_A-Za-z0-9]+)?\.json$", re.I)
_RE_PASSIVE_ABNORMALITY = re.compile(r"^Passives_Abnormality(?:[-_A-Za-z0-9]+)?\.json$", re.I)

SINNER_NAMES = {
    "01": "李箱", "02": "浮士德", "03": "堂吉诃德", "04": "良秀", "05": "默尔索", "06": "鸿璐",
    "07": "希斯克利夫", "08": "以实玛利", "09": "罗佳", "10": "辛克莱", "11": "奥提斯", "12": "格里高尔",
}


@dataclass(frozen=True)
class FileEntity:
    """一个文件对应的实体角色（未识别时 kind/role 为 None）。"""

    kind: str | None = None
    role: str = ROLE_OTHER
    entity_id: int | None = None      # 人格/EGO id（文件名能确定的）
    id_from_record: bool = False      # entity_id 是否要按记录 id 推导（本体/技能文件）
    id_divisor: int = 1               # 本体用 1；技能用 100（技能 id = 实体 id × 100 + 序号）
    variant: str | None = None        # 变体/后缀（人格剧情 A/B/I、语音变体名）


def is_ego_variant_id(rid: object) -> bool:
    """E.G.O 的 6 位 id（基础 id + 变体位）判定。"""
    return isinstance(rid, int) and 200000 <= rid <= 299999


def valid_entity_id(entity_id: int, kind: str) -> bool:
    """实体 id 是否合理（人格 1xxxx / 4xxxxx 活动特殊，E.G.O 2xxxx）。

    「记录 id ÷ 100 = 实体 id」的推导只对这几段成立；段外的一律不挂实体，
    免得把敌人/异想体的被动表误挂到人格名下去。
    """
    if kind == KIND_EGO:
        return 20000 <= entity_id <= 29999
    return 10000 <= entity_id <= 19999 or 400000 <= entity_id <= 499999


def split_entity_id(entity_id: int) -> tuple[str, int]:
    """实体 id → (罪人码, 该罪人下的序号)。10310 → ("03", 10)。"""
    text = str(int(entity_id))
    if len(text) < 5:
        return "", int(entity_id)
    return text[1:3], int(text[3:])


def sinner_name(code: str | None) -> str | None:
    return SINNER_NAMES.get(code or "")


def entity_key(kind: str, entity_id: int) -> str:
    head = "P:" if kind == KIND_PERSONALITY else "E:" if kind == KIND_EGO else "N:"
    return head + str(int(entity_id))


def parse_entity_key(key: str) -> tuple[str, int] | None:
    if not key or ":" not in key:
        return None
    head, _, tail = key.partition(":")
    if not tail.isdigit():
        return None
    kind = KIND_PERSONALITY if head == "P" else KIND_EGO if head == "E" \
        else KIND_ENEMY if head == "N" else None
    return (kind, int(tail)) if kind else None


def file_entity(rel: str) -> FileEntity | None:
    """按文件相对路径判断实体角色；不属于人格/EGO 体系返回 FileEntity(role=other)。"""
    rel = (rel or "").replace("\\", "/").lstrip("/")
    name = rel.rsplit("/", 1)[-1]

    if _RE_ENEMIES.match(name):
        return FileEntity(kind=KIND_ENEMY, role=ROLE_ENEMY, id_from_record=True, id_divisor=1)
    if _RE_SKILL_ENEMY.match(name):
        return FileEntity(kind=KIND_ENEMY, role=ROLE_ENEMY_SKILL, id_from_record=True, id_divisor=100)
    if _RE_PASSIVE_ENEMY.match(name):
        return FileEntity(kind=KIND_ENEMY, role=ROLE_ENEMY_PASSIVE, id_from_record=True, id_divisor=100)
    if _RE_SKILL_ABNORMALITY.match(name):
        return FileEntity(kind=KIND_ENEMY, role=ROLE_ENEMY_SKILL, id_from_record=True, id_divisor=100)
    if _RE_PASSIVE_ABNORMALITY.match(name):
        return FileEntity(kind=KIND_ENEMY, role=ROLE_ENEMY_PASSIVE, id_from_record=True, id_divisor=100)
    if _RE_PERSONALITIES.match(name):
        return FileEntity(kind=KIND_PERSONALITY, role=ROLE_IDENTITY, id_from_record=True, id_divisor=1)
    if _RE_EGOS.match(name):
        return FileEntity(kind=KIND_EGO, role=ROLE_EGO, id_from_record=True, id_divisor=1)
    if _RE_SKILLS_BASE.match(name):
        return FileEntity(kind=KIND_PERSONALITY, role=ROLE_IDENTITY_SKILL, id_from_record=True, id_divisor=100)
    if _RE_SKILL_PERSONALITY.match(name):
        return FileEntity(kind=KIND_PERSONALITY, role=ROLE_IDENTITY_SKILL, id_from_record=True, id_divisor=100)
    if _RE_SKILL_EGO.match(name):
        return FileEntity(kind=KIND_EGO, role=ROLE_EGO_SKILL, id_from_record=True, id_divisor=100)
    if _RE_PASSIVES.match(name):
        return FileEntity(kind=KIND_PERSONALITY, role=ROLE_IDENTITY_PASSIVE, id_from_record=True, id_divisor=100)
    if _RE_PASSIVE_EGO.match(name):
        return FileEntity(kind=KIND_EGO, role=ROLE_EGO_PASSIVE, id_from_record=True, id_divisor=100)
    m = _RE_STORY_PERSONALITY.match(rel)
    if m:
        return FileEntity(kind=KIND_PERSONALITY, role=ROLE_IDENTITY_STORY,
                          entity_id=int(m.group(1)), variant=(m.group(2) or None))
    m = _RE_VOICE_PERSONALITY.match(rel)
    if m:
        variant = None
        parts = name[:-5].split("_")
        if len(parts) >= 4:
            variant = "_".join(parts[2:-1]) or None
        return FileEntity(kind=KIND_PERSONALITY, role=ROLE_IDENTITY_VOICE,
                          entity_id=int(m.group(1)), variant=variant)
    m = _RE_VOICE_EGO.match(rel)
    if m:
        return FileEntity(kind=KIND_EGO, role=ROLE_EGO_VOICE, variant=m.group(1))
    return FileEntity(kind=None, role=ROLE_OTHER)


#: enemy_map.json 的可写覆盖目录（用户数据目录，优先于包内数据合并读取）。
#: 由 AppContext 在启动时注册，让「新增章节敌方元数据」不必重打包 exe。
_ENEMY_MAP_OVERLAY: Path | None = None


def set_enemy_map_overlay(path: Path | str | None) -> None:
    """注册 enemy_map.json 的覆盖目录（通常为 cache_dir）。

    实体集合取「覆盖目录 ∪ 包内数据」的并集：覆盖目录只需放增量条目
    （如第十章 25 个新敌人），包内既有 613 条不受影响。
    """
    global _ENEMY_MAP_OVERLAY
    _ENEMY_MAP_OVERLAY = Path(path) if path else None
    clear_enemy_known_cache()


def _enemy_map_ids() -> set[int]:
    """合并读取 enemy_map.json（覆盖目录优先，再并入包内数据）的敌人 id 集合。"""
    ids: set[int] = set()
    if _ENEMY_MAP_OVERLAY is not None:
        try:
            obj = json.loads((_ENEMY_MAP_OVERLAY / "enemy_map.json").read_text(encoding="utf-8-sig"))
            enemies = obj.get("enemies") if isinstance(obj, dict) else {}
            ids |= {int(k) for k in enemies}
        except Exception:  # noqa: BLE001 —— 覆盖目录缺失时忽略，回退包内数据
            pass
    try:
        from .season import package_data_dir

        obj = json.loads((package_data_dir() / "enemy_map.json").read_text(encoding="utf-8-sig"))
        enemies = obj.get("enemies") if isinstance(obj, dict) else {}
        ids |= {int(k) for k in enemies}
    except Exception:  # noqa: BLE001 —— 数据缺失时按空集处理（文本照常可搜可改）
        pass
    return ids


def enemy_known_ids() -> set[int]:
    """enemy_map.json 里登记过的敌方 id（只读元数据，实体集以此为准）。"""
    if not hasattr(enemy_known_ids, "_cache"):
        enemy_known_ids._cache = _enemy_map_ids()  # type: ignore[attr-defined]
    return enemy_known_ids._cache  # type: ignore[attr-defined]


def clear_enemy_known_cache() -> None:
    if hasattr(enemy_known_ids, "_cache"):
        del enemy_known_ids._cache  # type: ignore[attr-defined]


def is_enemy_id(rid: object) -> bool:
    """记录 id 是否在敌方元数据里登记过（实体集 = enemy_map.json 的 598 条）。"""
    return isinstance(rid, int) and rid in enemy_known_ids()


def _enemy_parent_id(rid: int) -> int | None:
    """技能 / 被动记录 id → 所属敌方本体 id。

    优先按游戏惯例 ``rid // 100``（敌方单位技能 9101501 → 91015、异想体 6 位技能 112601 → 1126）；
    不在 enemy_map 时再试 ``rid // 1000``（异想体 7 位技能 8001001 → 8001），
    避免把 4 位异想体的 7 位技能误判成 5 位伪实体（80010 未登记）。
    """
    for div in (100, 1000):
        parent = rid // div
        if parent and is_enemy_id(parent):
            return parent
    return None


def _enemy_entity_of(info: FileEntity, record: dict | None) -> tuple[str | None, str]:
    """敌方实体归属：本体 id 本身；部位（6 位 id / desc=部位）归本体；
    技能 id//100（或 //1000）归本体；被动 id 本身或 id//100（或 //1000）是本体 id。"""
    rid = (record or {}).get("id")
    if not isinstance(rid, int):
        return None, info.role
    if info.role == ROLE_ENEMY:
        # 本体 id 本身在 enemy_map 登记过 → 独立实体（含个别 desc='部位' 但被单列为实体的记录）
        if is_enemy_id(rid):
            return entity_key(KIND_ENEMY, rid), ROLE_ENEMY
        desc = str(record.get("desc") or "")
        if desc == "部位" or (100000 <= rid <= 999999 and is_enemy_id(rid // 100)):
            parent = rid // 100
            if is_enemy_id(parent):
                return entity_key(KIND_ENEMY, parent), ROLE_ENEMY_PART
            return None, info.role
        return None, info.role
    if info.role in (ROLE_ENEMY_SKILL, ROLE_ENEMY_PASSIVE):
        if info.role == ROLE_ENEMY_PASSIVE and is_enemy_id(rid):
            return entity_key(KIND_ENEMY, rid), ROLE_ENEMY_PASSIVE
        parent = _enemy_parent_id(rid)
        if parent is not None:
            return entity_key(KIND_ENEMY, parent), info.role
        return None, info.role
    return None, info.role


def entity_id_of(rel: str, record: dict | None) -> tuple[str | None, str]:
    """返回 (entity_key, role)：结合文件名与记录 id 定位所属实体。"""
    info = file_entity(rel)
    if info is None or info.role == ROLE_OTHER:
        return None, ROLE_OTHER
    if info.kind == KIND_ENEMY:
        return _enemy_entity_of(info, record)
    entity_id = info.entity_id
    if info.id_from_record:
        rid = (record or {}).get("id")
        if not isinstance(rid, int):
            return None, info.role
        entity_id = rid // info.id_divisor  # 本体：rid 即实体 id；技能：rid = 实体 id × 100 + 技能号
        if info.role == ROLE_EGO and 200000 <= rid <= 299999:
            # E.G.O 的 6 位 id = 基础 EGO id + 变体位（201011 = 乌瞰刀 20101 的变体）→ 归到基础实体
            entity_id = rid // 10
        if info.role in (ROLE_IDENTITY, ROLE_EGO) and not 10000 <= rid <= 999999:
            return None, info.role
        if info.role in (ROLE_IDENTITY_SKILL, ROLE_EGO_SKILL,
                         ROLE_IDENTITY_PASSIVE, ROLE_EGO_PASSIVE) and not 100000 <= rid <= 99999999:
            return None, info.role
        if info.role in (ROLE_IDENTITY_SKILL, ROLE_EGO_SKILL, ROLE_IDENTITY_PASSIVE, ROLE_EGO_PASSIVE) \
                and not valid_entity_id(entity_id, info.kind or KIND_PERSONALITY):
            return None, info.role
    if entity_id is None:
        return None, info.role
    kind = info.kind or KIND_PERSONALITY
    if is_excluded_entity(kind, entity_id):
        # 被剔除的实体（如愚人节人格）：不挂实体 → 不进图鉴/一览/赛季统计；文本条目照常可搜可改
        return None, info.role
    return entity_key(kind, entity_id), info.role


def variant_of(rel: str) -> str | None:
    info = file_entity(rel)
    return info.variant if info else None


# ---- 不进图鉴的实体（data/entity_exclude.json） ----

EXCLUDE_PATH_NAME = "entity_exclude.json"
_exclude_cache: dict[str, set[int]] | None = None


def load_exclude_map(path: Path | None = None) -> dict[str, set[int]]:
    """读取 data/entity_exclude.json → {"identities": {...}, "egos": {...}}（缺省空表）。

    传 ``path`` 时只解析这一个文件（不写缓存），只有按数据目录加载才会进缓存。
    """
    global _exclude_cache
    explicit = path is not None
    if path is None:
        if _exclude_cache is not None:
            return _exclude_cache
        try:
            from .season import package_data_dir

            path = package_data_dir() / EXCLUDE_PATH_NAME
        except Exception:  # noqa: BLE001 —— 数据目录不可用时按空表处理
            return {"identities": set(), "egos": set()}
    out = {"identities": set(), "egos": set()}
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        obj = None
    if isinstance(obj, dict):
        for key in out:
            for value in obj.get(key) or []:
                if isinstance(value, int):
                    out[key].add(value)
    if not explicit:
        _exclude_cache = out
    return out


def clear_exclude_cache() -> None:
    global _exclude_cache
    _exclude_cache = None


def is_excluded_entity(kind: str, entity_id: int) -> bool:
    """该实体是否被排除在图鉴之外（愚人节人格等）。"""
    table = load_exclude_map()
    return int(entity_id) in (table["egos"] if kind == KIND_EGO else table["identities"])


# ---- 待确认剧情文件的类型映射（豆包答案汇总，缺省为空） ----

KIND_MAP_PATH_NAME = "misc_story_kinds.json"
_kind_map_cache: dict[str, dict] | None = None


def load_kind_map(path: Path | None = None) -> dict[str, dict]:
    """读取 data/misc_story_kinds.json（不存在则返回空表，随时可重复调用）。"""
    global _kind_map_cache
    if path is None:
        if _kind_map_cache is not None:
            return _kind_map_cache
        try:
            from .season import package_data_dir

            path = package_data_dir() / KIND_MAP_PATH_NAME
        except Exception:  # noqa: BLE001 —— 数据目录不可用时按空表处理
            return {}
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    kinds = obj.get("kinds") if isinstance(obj, dict) else None
    if not isinstance(kinds, dict):
        return {}
    if path is not None:
        _kind_map_cache = kinds
    return kinds


def clear_kind_map_cache() -> None:
    global _kind_map_cache
    _kind_map_cache = None
