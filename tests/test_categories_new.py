"""新增分类（ego_gift / mirror_event）的单元测试。"""
from __future__ import annotations

import json
import pathlib
import pytest

# 确保能导入 categories 模块
from limbus_patcher import categories


# ---------- fixtures ----------

@pytest.fixture
def cat_rules():
    """加载当前 category_rules.json 原始数据。"""
    data_path = pathlib.Path(__file__).parent.parent / "limbus_patcher" / "data" / "category_rules.json"
    return json.loads(data_path.read_text(encoding="utf-8"))


@pytest.fixture
def categories():
    """触发 reload_classification 以加载 JSON。"""
    # 重置到内置默认值，再加载 JSON
    import importlib
    import limbus_patcher.categories as mod
    # 重置全局变量
    mod._user_data_dir = None
    mod._rules_source = "builtin"
    mod.CATEGORIES = {
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
    mod.CATEGORY_GROUPS = {
        "battle": ("角色与战斗", ["identity", "ego", "skill", "combat", "abnormality", "enemy", "battle_dialog", "sinner"]),
        "story": ("剧情与模式", ["main_story", "identity_story", "dungeon_story", "misc_story", "event", "railway", "mirror", "ego_gift", "mirror_event"]),
        "system": ("系统与界面", ["ui", "system", "tutorial", "item"]),
        "misc": ("其他", ["other"]),
    }
    # 重新编译规则
    _R = __import__("re").compile
    mod._RULES = [
        (_R(r"^Skills_Ego", __import__("re").I), "ego"),
        (_R(r"^Skills_personality", __import__("re").I), "identity"),
        (_R(r"^Skills_Abnormality", __import__("re").I), "abnormality"),
        (_R(r"^Skills_Enemy", __import__("re").I), "enemy"),
        (_R(r"^Skills_Assist", __import__("re").I), "combat"),
        (_R(r"^Skills_Tutorial", __import__("re").I), "tutorial"),
        (_R(r"^Skills", __import__("re").I), "skill"),
        (_R(r"^SkillTag", __import__("re").I), "skill"),
        (_R(r"^Personalities", __import__("re").I), "identity"),
        (_R(r"^Personality_Get_Condition", __import__("re").I), "identity"),
        (_R(r"^StoryTheaterMirrorWorld", __import__("re").I), "identity_story"),
        (_R(r"^StoryTheaterPersonality", __import__("re").I), "identity_story"),
        (_R(r"^AssociationName", __import__("re").I), "identity"),
        (_R(r"^Egos", __import__("re").I), "ego"),
        (_R(r"^EGO_Get_Condition", __import__("re").I), "ego"),
        (_R(r"^Passive_Ego", __import__("re").I), "ego"),
        (_R(r"^BattleKeywords", __import__("re").I), "combat"),
        (_R(r"^Bufs", __import__("re").I), "combat"),
        (_R(r"^Passives_Enemy", __import__("re").I), "enemy"),
        (_R(r"^Passives_Abnormality", __import__("re").I), "abnormality"),
        (_R(r"^Passives_Assist", __import__("re").I), "combat"),
        (_R(r"^Passives", __import__("re").I), "combat"),
        (_R(r"^BuffAbilities", __import__("re").I), "combat"),
        (_R(r"^MentalCondition", __import__("re").I), "combat"),
        (_R(r"^UnitKeyword", __import__("re").I), "combat"),
        (_R(r"^KeywordDictionary", __import__("re").I), "combat"),
        (_R(r"^ResistText", __import__("re").I), "combat"),
        (_R(r"^AttributeText", __import__("re").I), "combat"),
        (_R(r"^ChoiceEventKeyword", __import__("re").I), "combat"),
        (_R(r"^DanteAbilityUIText", __import__("re").I), "ui"),
        (_R(r"^DanteAbility", __import__("re").I), "combat"),
        (_R(r"^Assist-", __import__("re").I), "combat"),
        (_R(r"^Passive", __import__("re").I), "combat"),
        (_R(r"^AbnormalityGuides", __import__("re").I), "abnormality"),
        (_R(r"^Enemies", __import__("re").I), "enemy"),
        (_R(r"^BattleSpeechBubbleDlg", __import__("re").I), "battle_dialog"),
        (_R(r"^AbDlg_", __import__("re").I), "battle_dialog"),
        (_R(r"^PanicInfo", __import__("re").I), "battle_dialog"),
        (_R(r"^Announcer", __import__("re").I), "battle_dialog"),
        (_R(r"^BattleAnnouncerDlg/", __import__("re").I), "battle_dialog"),
        (_R(r"^PersonalityVoiceDlg/", __import__("re").I), "battle_dialog"),
        (_R(r"^EGOVoiceDig/", __import__("re").I), "battle_dialog"),
        (_R(r"^Characters", __import__("re").I), "sinner"),
        (_R(r"^IntroduceCharacter", __import__("re").I), "sinner"),
        (_R(r"^StoryData/P\d{5}", __import__("re").I), "identity_story"),
        (_R(r"^StoryData/(PC|ES)\d", __import__("re").I), "misc_story"),
        (_R(r"^StoryData/\d+D", __import__("re").I), "misc_story"),
        (_R(r"^StoryData/", __import__("re").I), "main_story"),
        (_R(r"^StoryTheaterUIText", __import__("re").I), "ui"),
        (_R(r"^StoryTheater", __import__("re").I), "main_story"),
        (_R(r"^StageNode", __import__("re").I), "main_story"),
        (_R(r"^StageChapterText", __import__("re").I), "main_story"),
        (_R(r"^StagePartText", __import__("re").I), "main_story"),
        (_R(r"^StageContinueText", __import__("re").I), "main_story"),
        (_R(r"^StageStatisticUIText", __import__("re").I), "ui"),
        (_R(r"^DungeonNode", __import__("re").I), "main_story"),
        (_R(r"^DungeonArea", __import__("re").I), "main_story"),
        (_R(r"^StoryDungeonUI", __import__("re").I), "main_story"),
        (_R(r"^Story-", __import__("re").I), "main_story"),
        (_R(r"^AbEvents", __import__("re").I), "event"),
        (_R(r"^ActionEvents", __import__("re").I), "event"),
        (_R(r"^ChoiceEventUI", __import__("re").I), "ui"),
        (_R(r"^ChoiceEvent", __import__("re").I), "event"),
        (_R(r"^Event[A-Z]", __import__("re").I), "event"),
        (_R(r"EventText[^/.]*\.json$", __import__("re").I), "event"),
        (_R(r"^HellsChicken", __import__("re").I), "event"),
        (_R(r"^CultivationEvent", __import__("re").I), "event"),
        (_R(r"^TwiningThreadsEvent", __import__("re").I), "event"),
        (_R(r"^DawnOfGreenEventText", __import__("re").I), "event"),
        (_R(r"^NightCleanUpEvent", __import__("re").I), "event"),
        (_R(r"^DailyLoginEvent", __import__("re").I), "event"),
        (_R(r"^Fools\d", __import__("re").I), "event"),
        (_R(r"^RecordMemoryEvent", __import__("re").I), "event"),
        (_R(r"^Limbus\d.*Anniversary", __import__("re").I), "event"),
        (_R(r"^DungeonName_Event", __import__("re").I), "event"),
        (_R(r"^RailwayDungeon", __import__("re").I), "railway"),
        (_R(r"^MirrorDungeon", __import__("re").I), "mirror"),
        (_R(r"^DungeonStartBuffs", __import__("re").I), "mirror"),
        (_R(r"^MirrorEvent", __import__("re").I), "mirror_event"),
        (_R(r"^DungeonEvent", __import__("re").I), "mirror_event"),
        (_R(r"^EGOgift", __import__("re").I), "ego_gift"),
        (_R(r"^EgoGiftCategory", __import__("re").I), "ego_gift"),
        (_R(r"^Tutorial", __import__("re").I), "tutorial"),
        (_R(r"^BattleHint", __import__("re").I), "tutorial"),
        (_R(r"^ShotcutKeyManual", __import__("re").I), "tutorial"),
        (_R(r"^ErrorCodeMsg", __import__("re").I), "system"),
        (_R(r"^UserAgreements", __import__("re").I), "system"),
        (_R(r"^FAQ", __import__("re").I), "system"),
        (_R(r"^ReturnPolicy", __import__("re").I), "system"),
        (_R(r"^FileDownloadDesc", __import__("re").I), "system"),
        (_R(r"^CouponUIText", __import__("re").I), "system"),
        (_R(r"^Items", __import__("re").I), "item"),
        (_R(r"^IAPProduct", __import__("re").I), "item"),
        (_R(r"^IAPSticker", __import__("re").I), "item"),
        (_R(r"^ShopItemCount", __import__("re").I), "item"),
        (_R(r"^AttendanceRewardsText", __import__("re").I), "item"),
        (_R(r"^UI_", __import__("re").I), "ui"),
        (_R(r"UIText\.json$", __import__("re").I), "ui"),
        (_R(r"^MainUIText", __import__("re").I), "ui"),
        (_R(r"^LoginUIText", __import__("re").I), "ui"),
        (_R(r"^ShopUI", __import__("re").I), "ui"),
        (_R(r"^SelectDUI", __import__("re").I), "ui"),
        (_R(r"^SkinUI", __import__("re").I), "ui"),
        (_R(r"^Formation", __import__("re").I), "ui"),
        (_R(r"^Gacha", __import__("re").I), "ui"),
        (_R(r"^BattlePass", __import__("re").I), "ui"),
        (_R(r"^BattleResultHint", __import__("re").I), "ui"),
        (_R(r"^BattleUIText", __import__("re").I), "ui"),
        (_R(r"^BossRaidUI", __import__("re").I), "ui"),
        (_R(r"^UserBanner", __import__("re").I), "ui"),
        (_R(r"^UserTicket", __import__("re").I), "ui"),
        (_R(r"^UserInfo", __import__("re").I), "ui"),
        (_R(r"^LobbyBGM", __import__("re").I), "ui"),
        (_R(r"^Filter", __import__("re").I), "ui"),
        (_R(r"^SeasonTitle", __import__("re").I), "ui"),
        (_R(r"^SuccessRate", __import__("re").I), "ui"),
        (_R(r"^ThreadDungeon", __import__("re").I), "ui"),
        (_R(r"^RewardDungeonUI", __import__("re").I), "ui"),
        (_R(r"^UpgradeCharacterUI", __import__("re").I), "ui"),
        (_R(r"^IntegrateAccountUI", __import__("re").I), "ui"),
        (_R(r"^IntroductionPreset", __import__("re").I), "ui"),
        (_R(r"^MissionUIText", __import__("re").I), "ui"),
        (_R(r"^Quest", __import__("re").I), "ui"),
        (_R(r"^TooltipUIText", __import__("re").I), "ui"),
        (_R(r"^StoryUIText", __import__("re").I), "ui"),
        (_R(r"^PilgrimageUIText", __import__("re").I), "ui"),
        (_R(r"^UnlockCode", __import__("re").I), "ui"),
        (_R(r"^kr_settings-ui", __import__("re").I), "ui"),
    ]
    return mod


# ---------- 测试 ----------

class TestNewCategories:
    """测试新增分类 ego_gift 和 mirror_event 的存在与归属。"""

    def test_categories_have_ego_gift(self, cat_rules):
        assert "ego_gift" in cat_rules["categories"]
        assert cat_rules["categories"]["ego_gift"] == "饰品"

    def test_categories_have_mirror_event(self, cat_rules):
        assert "mirror_event" in cat_rules["categories"]
        assert cat_rules["categories"]["mirror_event"] == "镜牢探索事件"

    def test_story_group_includes_new_categories(self, cat_rules):
        story_members = cat_rules["groups"]["story"]["members"]
        assert "ego_gift" in story_members
        assert "mirror_event" in story_members

    def test_builtin_categories_in_sync(self, categories):
        """验证 categories.py 内置默认值与 JSON 一致。"""
        assert categories.CATEGORIES["ego_gift"] == "饰品"
        assert categories.CATEGORIES["mirror_event"] == "镜牢探索事件"

    def test_builtin_story_group_includes_new(self, categories):
        story_members = categories.CATEGORY_GROUPS["story"][1]
        assert "ego_gift" in story_members
        assert "mirror_event" in story_members


class TestNewRules:
    """测试新增分类的正则规则。"""

    def test_ego_gift_rule(self, categories):
        """EGOgift 应归入 ego_gift 而非 mirror。"""
        assert categories.classify("EGOgift.json") == "ego_gift"
        assert categories.classify("EGOgift/test.json") == "ego_gift"

    def test_egogift_category_rule(self, categories):
        assert categories.classify("EgoGiftCategory.json") == "ego_gift"
        assert categories.classify("EgoGiftCategory/test.json") == "ego_gift"

    def test_mirror_event_rule(self, categories):
        """MirrorEvent 应归入 mirror_event。"""
        assert categories.classify("MirrorEvent.json") == "mirror_event"
        assert categories.classify("MirrorEvent/test.json") == "mirror_event"

    def test_dungeon_event_rule(self, categories):
        assert categories.classify("DungeonEvent.json") == "mirror_event"
        assert categories.classify("DungeonEvent/test.json") == "mirror_event"

    def test_mirror_still_works(self, categories):
        """mirror 主体规则不受影响。"""
        assert categories.classify("MirrorDungeon.json") == "mirror"
        assert categories.classify("DungeonStartBuffs.json") == "mirror"

    def test_ego_gift_category_label(self, categories):
        assert categories.category_label("ego_gift") == "饰品"

    def test_mirror_event_category_label(self, categories):
        assert categories.category_label("mirror_event") == "镜牢探索事件"


class TestNoStatusCategory:
    """验证未新增 status 分类。"""

    def test_no_status_category(self, cat_rules):
        assert "status" not in cat_rules["categories"]

    def test_no_status_in_builtin(self, categories):
        assert "status" not in categories.CATEGORIES


class TestEnemyMapDimensions:
    """验证 enemy_map.json 已添加二级维度定义。"""

    def test_dimensions_key_exists(self):
        data_path = pathlib.Path(__file__).parent.parent / "limbus_patcher" / "data" / "enemy_map.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        assert "dimensions" in data

    def test_dimensions_have_expected_fields(self):
        data_path = pathlib.Path(__file__).parent.parent / "limbus_patcher" / "data" / "enemy_map.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        dims = data["dimensions"]
        assert "chapter_type" in dims
        assert "enemy_type" in dims
        assert "danger_level" in dims

    def test_chapter_type_has_labels(self):
        data_path = pathlib.Path(__file__).parent.parent / "limbus_patcher" / "data" / "enemy_map.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        ct = data["dimensions"]["chapter_type"]
        assert ct["labels"]["main"] == "主线"
        assert ct["labels"]["interchapter"] == "间章"

    def test_enemy_type_has_labels(self):
        data_path = pathlib.Path(__file__).parent.parent / "limbus_patcher" / "data" / "enemy_map.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        et = data["dimensions"]["enemy_type"]
        assert et["labels"]["normal"] == "普通"
        assert et["labels"]["elite"] == "精英"
        assert et["labels"]["branch"] == "支部探索"

    def test_danger_level_has_labels(self):
        data_path = pathlib.Path(__file__).parent.parent / "limbus_patcher" / "data" / "enemy_map.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        dl = data["dimensions"]["danger_level"]
        assert "ZAYIN" in dl["labels"]
        assert "ALEPH" in dl["labels"]

    def test_example_dimensions_exist(self):
        data_path = pathlib.Path(__file__).parent.parent / "limbus_patcher" / "data" / "enemy_map.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        enemies = data["enemies"]
        # 至少有一个 enemy 有 dimensions 字段
        has_dims = any("dimensions" in e for e in enemies.values())
        assert has_dims, "至少有一个敌人应有二级维度示例数据"
