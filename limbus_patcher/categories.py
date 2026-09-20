"""文件名 → 中文分类映射，以及章节/角色辅助信息的派生。

分类规则可从 data/category_rules.json 加载（用户手工维护）：
- 应用 data/ 目录（随 exe 便携目录）优先；
- 其次包内 limbus_patcher/data/category_rules.json；
- 缺失/损坏时回退到下方代码内置默认值。

JSON 格式（format_version=1）：
{
  "categories": {"identity": "人格", ...},
  "groups": {"battle": {"label": "角色与战斗", "members": ["identity", ...]}, ...},
  "rules": [["^Personalities", "identity"], ...],   // 按序匹配，正则自动加 re.I
  "event_hints": {"tkt": "间章 4.5", ...}
}
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .season import package_data_dir

# ---------- 内置默认（与 data/category_rules.json 保持一致） ----------

CATEGORIES: dict[str, str] = {
    "identity": "人格",
    "identity_story": "人格剧情",
    "ego": "E.G.O",
    "skill": "技能",
    "combat": "战斗效果",
    "abnormality": "异想体",
    "enemy": "敌方单位",
    "battle_dialog": "战斗对话",
    "sinner": "罪人",
    "main_story": "主线剧情",
    "misc_story": "其他剧情",
    "dungeon_story": "迷宫剧情",
    "event": "间章与活动",
    "railway": "折射轨道",
    "mirror": "镜牢",
    "ego_gift": "饰品",
    "mirror_event": "镜牢探索事件",
    "ui": "界面文本",
    "system": "系统提示",
    "tutorial": "教程",
    "item": "道具与货币",
    "other": "其他",
}

CATEGORY_GROUPS: dict[str, tuple[str, list[str]]] = {
    "battle": ("图鉴与战斗", [
        "identity", "ego", "skill", "combat", "abnormality", "enemy", "battle_dialog", "sinner",
    ]),
    "story": ("剧情", [
        "main_story", "identity_story", "dungeon_story", "misc_story", "event", "railway", "mirror",
        "ego_gift", "mirror_event",
    ]),
    "system": ("系统与界面", [
        "ui", "system", "tutorial", "item", "other",
    ]),
}

PSEUDO_CATEGORIES: dict[str, str] = {
    "all": "全部文本",
    "favorites": "我的收藏",
    "recent": "最近修改",
    "pending": "待确认",
    "supplement": "补译文本",
}

_R = re.compile  # noqa: N816

_RULES: list[tuple[re.Pattern, str]] = [
    (_R(r"^Skills_Ego", re.I), "ego"),
    (_R(r"^Skills_personality", re.I), "identity"),
    (_R(r"^Skills_Abnormality", re.I), "abnormality"),
    (_R(r"^Skills_Enemy", re.I), "enemy"),
    (_R(r"^Skills_Assist", re.I), "combat"),
    (_R(r"^Skills_Tutorial", re.I), "tutorial"),
    (_R(r"^Skills", re.I), "skill"),
    (_R(r"^SkillTag", re.I), "skill"),
    (_R(r"^Personalities", re.I), "identity"),
    (_R(r"^Personality_Get_Condition", re.I), "identity"),
    (_R(r"^StoryTheaterMirrorWorld", re.I), "identity_story"),
    (_R(r"^StoryTheaterPersonality", re.I), "identity_story"),
    (_R(r"^AssociationName", re.I), "identity"),
    (_R(r"^Egos", re.I), "ego"),
    (_R(r"^EGO_Get_Condition", re.I), "ego"),
    (_R(r"^Passive_Ego", re.I), "ego"),
    (_R(r"^BattleKeywords", re.I), "combat"),
    (_R(r"^Bufs", re.I), "combat"),
    (_R(r"^Passives_Enemy", re.I), "enemy"),
    (_R(r"^Passives_Abnormality", re.I), "abnormality"),
    (_R(r"^Passives_Assist", re.I), "combat"),
    (_R(r"^Passives", re.I), "combat"),
    (_R(r"^BuffAbilities", re.I), "combat"),
    (_R(r"^MentalCondition", re.I), "combat"),
    (_R(r"^UnitKeyword", re.I), "combat"),
    (_R(r"^KeywordDictionary", re.I), "combat"),
    (_R(r"^ResistText", re.I), "combat"),
    (_R(r"^AttributeText", re.I), "combat"),
    (_R(r"^ChoiceEventKeyword", re.I), "combat"),
    (_R(r"^DanteAbilityUIText", re.I), "ui"),
    (_R(r"^DanteAbility", re.I), "combat"),
    (_R(r"^Assist-", re.I), "combat"),
    (_R(r"^Passive", re.I), "combat"),
    (_R(r"^AbnormalityGuides", re.I), "abnormality"),
    (_R(r"^Enemies", re.I), "enemy"),
    (_R(r"^BattleSpeechBubbleDlg", re.I), "battle_dialog"),
    (_R(r"^AbDlg_", re.I), "battle_dialog"),
    (_R(r"^PanicInfo", re.I), "battle_dialog"),
    (_R(r"^Announcer", re.I), "battle_dialog"),
    (_R(r"^BattleAnnouncerDlg/", re.I), "battle_dialog"),
    (_R(r"^PersonalityVoiceDlg/", re.I), "battle_dialog"),
    (_R(r"^EGOVoiceDig/", re.I), "battle_dialog"),
    (_R(r"^Characters", re.I), "sinner"),
    (_R(r"^IntroduceCharacter", re.I), "sinner"),
    # 人格剧情 StoryData/P<人格id>.json（实体化后归到「人格剧情」分类）
    (_R(r"^StoryData/P\d{5}", re.I), "identity_story"),
    # 迷宫/活动/待确认剧情：PC*、ES*、<章>D*（先用「其他剧情」，豆包答案可细化）
    (_R(r"^StoryData/(PC|ES)\d", re.I), "misc_story"),
    (_R(r"^StoryData/\d+D", re.I), "misc_story"),
    (_R(r"^StoryData/", re.I), "main_story"),
    (_R(r"^StoryTheaterUIText", re.I), "ui"),
    (_R(r"^StoryTheater", re.I), "main_story"),
    (_R(r"^StageNode", re.I), "main_story"),
    (_R(r"^StageChapterText", re.I), "main_story"),
    (_R(r"^StagePartText", re.I), "main_story"),
    (_R(r"^StageContinueText", re.I), "main_story"),
    (_R(r"^StageStatisticUIText", re.I), "ui"),
    (_R(r"^DungeonNode", re.I), "main_story"),
    (_R(r"^DungeonArea", re.I), "main_story"),
    (_R(r"^StoryDungeonUI", re.I), "main_story"),
    (_R(r"^Story-", re.I), "main_story"),
    (_R(r"^AbEvents", re.I), "event"),
    (_R(r"^ActionEvents", re.I), "event"),
    (_R(r"^ChoiceEventUI", re.I), "ui"),
    (_R(r"^ChoiceEvent", re.I), "event"),
    (_R(r"^Event[A-Z]", re.I), "event"),
    (_R(r"EventText[^/.]*\.json$", re.I), "event"),
    (_R(r"^HellsChicken", re.I), "event"),
    (_R(r"^CultivationEvent", re.I), "event"),
    (_R(r"^TwiningThreadsEvent", re.I), "event"),
    (_R(r"^DawnOfGreenEventText", re.I), "event"),
    (_R(r"^NightCleanUpEvent", re.I), "event"),
    (_R(r"^DailyLoginEvent", re.I), "event"),
    (_R(r"^Fools\d", re.I), "event"),
    (_R(r"^RecordMemoryEvent", re.I), "event"),
    (_R(r"^Limbus\d.*Anniversary", re.I), "event"),
    (_R(r"^DungeonName_Event", re.I), "event"),
    (_R(r"^RailwayDungeon", re.I), "railway"),
    (_R(r"^MirrorDungeon", re.I), "mirror"),
    (_R(r"^DungeonStartBuffs", re.I), "mirror"),
    (_R(r"^MirrorEvent", re.I), "mirror_event"),
    (_R(r"^DungeonEvent", re.I), "mirror_event"),
    (_R(r"^EGOgift", re.I), "ego_gift"),
    (_R(r"^EgoGiftCategory", re.I), "ego_gift"),
    (_R(r"^Tutorial", re.I), "tutorial"),
    (_R(r"^BattleHint", re.I), "tutorial"),
    (_R(r"^ShotcutKeyManual", re.I), "tutorial"),
    (_R(r"^ErrorCodeMsg", re.I), "system"),
    (_R(r"^UserAgreements", re.I), "system"),
    (_R(r"^FAQ", re.I), "system"),
    (_R(r"^ReturnPolicy", re.I), "system"),
    (_R(r"^FileDownloadDesc", re.I), "system"),
    (_R(r"^CouponUIText", re.I), "system"),
    (_R(r"^Items", re.I), "item"),
    (_R(r"^IAPProduct", re.I), "item"),
    (_R(r"^IAPSticker", re.I), "item"),
    (_R(r"^ShopItemCount", re.I), "item"),
    (_R(r"^AttendanceRewardsText", re.I), "item"),
    (_R(r"^UI_", re.I), "ui"),
    (_R(r"UIText\.json$", re.I), "ui"),
    (_R(r"^MainUIText", re.I), "ui"),
    (_R(r"^LoginUIText", re.I), "ui"),
    (_R(r"^ShopUI", re.I), "ui"),
    (_R(r"^SelectDUI", re.I), "ui"),
    (_R(r"^SkinUI", re.I), "ui"),
    (_R(r"^Formation", re.I), "ui"),
    (_R(r"^Gacha", re.I), "ui"),
    (_R(r"^BattlePass", re.I), "ui"),
    (_R(r"^BattleResultHint", re.I), "ui"),
    (_R(r"^BattleUIText", re.I), "ui"),
    (_R(r"^BossRaidUI", re.I), "ui"),
    (_R(r"^UserBanner", re.I), "ui"),
    (_R(r"^UserTicket", re.I), "ui"),
    (_R(r"^UserInfo", re.I), "ui"),
    (_R(r"^LobbyBGM", re.I), "ui"),
    (_R(r"^Filter", re.I), "ui"),
    (_R(r"^SeasonTitle", re.I), "ui"),
    (_R(r"^SuccessRate", re.I), "ui"),
    (_R(r"^ThreadDungeon", re.I), "ui"),
    (_R(r"^RewardDungeonUI", re.I), "ui"),
    (_R(r"^UpgradeCharacterUI", re.I), "ui"),
    (_R(r"^IntegrateAccountUI", re.I), "ui"),
    (_R(r"^IntroductionPreset", re.I), "ui"),
    (_R(r"^MissionUIText", re.I), "ui"),
    (_R(r"^Quest", re.I), "ui"),
    (_R(r"^TooltipUIText", re.I), "ui"),
    (_R(r"^StoryUIText", re.I), "ui"),
    (_R(r"^PilgrimageUIText", re.I), "ui"),
    (_R(r"^UnlockCode", re.I), "ui"),
    (_R(r"^kr_settings-ui", re.I), "ui"),
]

_EVENT_HINTS: dict[str, str] = {
    "tkt": "间章 4.5",
    "twth": "间章 6.5",
    "mowe": "间章 5.5",
    "lcbcheckup": "间章 7.5",
    "night-clean-up": "间章 7.5·续",
    "cultivation": "间章 8.5",
    "pilgrimage": "间章 8.5EX",
    "fools": "愚人节活动",
    "ycgd": "间章",
}

# ---------- 数据文件加载 ----------

_user_data_dir: Path | None = None
_rules_source = "builtin"


def _classification_dirs() -> list[Path]:
    dirs: list[Path] = []
    if _user_data_dir:
        dirs.append(Path(_user_data_dir))
    dirs.append(package_data_dir())
    return dirs


def set_user_data_dir(path: Path | str | None) -> None:
    """设置用户数据目录（data/ 便携目录），其中的 category_rules.json 优先加载。"""
    global _user_data_dir
    _user_data_dir = Path(path) if path else None
    reload_classification()


def reload_classification() -> bool:
    """从 data/category_rules.json 重载分类；失败保留上次内容并返回 False。"""
    global CATEGORIES, CATEGORY_GROUPS, _RULES, _EVENT_HINTS, _rules_source
    for d in _classification_dirs():
        p = d / "category_rules.json"
        if not p.is_file():
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if obj.get("format_version") != 1:
                continue
            cats = obj.get("categories")
            if isinstance(cats, dict) and cats:
                CATEGORIES = {str(k): str(v) for k, v in cats.items()}
            groups: dict[str, tuple[str, list[str]]] = {}
            for gid, g in (obj.get("groups") or {}).items():
                if isinstance(g, dict) and isinstance(g.get("members"), list):
                    groups[str(gid)] = (str(g.get("label", gid)), [str(m) for m in g["members"]])
            if groups:
                CATEGORY_GROUPS = groups
            rules: list[tuple[re.Pattern, str]] = []
            for r in obj.get("rules") or []:
                if isinstance(r, list) and len(r) == 2 and isinstance(r[0], str) and isinstance(r[1], str):
                    try:
                        rules.append((re.compile(r[0], re.I), r[1]))
                    except re.error:
                        continue
            if rules:
                _RULES = rules
            hints = obj.get("event_hints")
            if isinstance(hints, dict):
                _EVENT_HINTS = {str(k): str(v) for k, v in hints.items()}
            _rules_source = str(p)
            return True
        except (OSError, json.JSONDecodeError):
            continue
    return False


# ---------- 查询 ----------

def relpath_of(path: str | Path, root: str | Path, strip_prefix: str = "") -> str:
    """计算相对 root 的 posix 风格相对路径。

    ``strip_prefix``：去掉**文件名**上的前缀（英文基线的文件都叫 ``EN_xxx.json``，
    去掉后与零协包的 ``xxx.json`` 位置一一对应，索引/方案/剧本数据可以共用一套键）。
    """
    rp = Path(path).resolve()
    try:
        rel = rp.relative_to(Path(root).resolve())
    except ValueError:
        rel = Path(Path(path).name)
    if strip_prefix and rel.name.startswith(strip_prefix):
        rel = rel.with_name(rel.name[len(strip_prefix):])
    return rel.as_posix()


def rules_source() -> Path:
    """当前生效的分类规则文件路径（用户 data/ 优先，其次包内；都没有则返回包内路径）。"""
    for d in _classification_dirs():
        p = d / "category_rules.json"
        if p.is_file():
            return p
    dirs = list(_classification_dirs())
    return (dirs[-1] if dirs else package_data_dir()) / "category_rules.json"


# 导入时就按「用户数据目录 > 包内数据」加载一次 rules，别让内置默认表与
# limbus_patcher/data/category_rules.json 长期不一致：
# 不一致时 classify() 的结果会取决于「有没有人先触发过 reload」——同一个文件
# 单跑测试归 event、整套测试归 battle_story，这种顺序依赖极难排查。
# 读不到文件时 reload_classification() 返回 False 并保留内置默认表，行为不变。
reload_classification()


def classify(relpath: str) -> str:
    """根据相对路径（posix 风格）返回分类 id。

    优先用 AI 判定表（misc_story_kinds.json）：这批剧情文件（迷宫/活动等）只看文件名定不了归属。
    """
    from .misc_kinds import category_of

    by_answer = category_of(relpath)
    if by_answer:
        return by_answer
    for pattern, cat in _RULES:
        if pattern.search(relpath):
            return cat
    return "other"


def category_label(cat: str) -> str:
    return CATEGORIES.get(cat, cat)


def group_of(cat: str) -> str:
    for gid, (_label, members) in CATEGORY_GROUPS.items():
        if cat in members:
            return gid
    return "misc"


_CHAPTER_RE = re.compile(r"a1c(\d+)p(\d+)", re.I)
_WALPU_RE = re.compile(r"walpu(\d+)", re.I)
_MIRROR_RE = re.compile(r"Mirror(?:Dungeon)?[A-Za-z]*[-_]?(\d+)", re.I)
_RAILWAY_RE = re.compile(r"Railway(?:Dungeon)?(?:Node|StationName|UI)?_?(\d+)", re.I)


def _railway_label(m: re.Match) -> str:
    num = int(m.group(1))
    if num >= 1000:
        n = int(str(num)[-3:].lstrip("0") or "1")
    else:
        n = num
    return f"折射轨道{n}号线"


def chapter_hint(relpath: str) -> str | None:
    """从文件名派生章节/模式提示（wiki 风格，用于列表副标题）。

    AI 判定表里有章节的（迷宫剧情 / 间章活动等）优先用答案里的章节名。
    """
    from .misc_kinds import chapter_of

    by_answer = chapter_of(relpath)
    if by_answer:
        return by_answer
    m = _RAILWAY_RE.search(relpath)
    if m:
        return _railway_label(m)
    m = _WALPU_RE.search(relpath)
    if m:
        return f"瓦夜{m.group(1)}"
    m = _MIRROR_RE.search(relpath)
    if m:
        return f"镜牢{m.group(1)}"
    m = _CHAPTER_RE.search(relpath)
    if m:
        return f"第{m.group(1)}章 第{m.group(2)}部分"
    stem = Path(relpath).stem.lower()
    for suffix, label in _EVENT_HINTS.items():
        if stem.endswith(suffix) or f"-{suffix}" in stem:
            return label
    return None


_SINNER_NAMES = {
    "YiSang": "李箱",
    "Faust": "浮士德",
    "DonQuixote": "堂吉诃德",
    "Ryoshu": "良秀",
    "Merusault": "默尔索",
    "HongLu": "鸿璐",
    "Heathcliff": "希斯克里夫",
    "Ishmael": "以实玛利",
    "Rodion": "罗佳",
    "Sinclair": "辛克莱",
    "Outis": "奥提斯",
    "Gregor": "格里高尔",
}

# 罪人编码（人格/E.G.O id 的第 2~3 位）→ 中文名
SINNER_CODES: dict[str, str] = {
    "01": "李箱",
    "02": "浮士德",
    "03": "堂吉诃德",
    "04": "良秀",
    "05": "默尔索",
    "06": "鸿璐",
    "07": "希斯克里夫",
    "08": "以实玛利",
    "09": "罗佳",
    "10": "辛克莱",
    "11": "奥提斯",
    "12": "格里高尔",
}


def sinner_of(category: str, entry_id: object) -> tuple[str, str] | None:
    """从人格/E.G.O 条目 id 推导 (罪人编码, 罪人中文名)。

    人格 id 形如 1 01 02（首位 1=人格，01=罪人码）；E.G.O 形如 2 01 01。
    兼容字符串 id（如 "10102_getCondition_normal"）与数字 id。
    """
    if category not in ("identity", "ego"):
        return None
    if entry_id is None:
        return None  # 无 id 的记录：不做罪人推导，避免 str(None) 被当成 id
    s = str(entry_id)
    if len(s) >= 3 and s[0] in ("1", "2") and s[1:3].isdigit():
        name = SINNER_CODES.get(s[1:3])
        if name:
            return s[1:3], name
    return None


def character_hint(relpath: str, record: dict) -> str | None:
    """从路径与记录字段派生角色名（无 id 的记录同样适用，只看 teller/model）。"""
    if not isinstance(record, dict):
        return None
    m = re.search(r"AbDlg_([A-Za-z]+)", relpath)
    if m:
        return _SINNER_NAMES.get(m.group(1))
    for field in ("teller", "model"):
        v = record.get(field)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None
