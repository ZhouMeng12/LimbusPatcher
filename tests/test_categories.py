"""分类体系测试：表驱动断言（对齐边狱公司灰机 wiki 术语）。"""
from __future__ import annotations

from limbus_patcher.categories import (
    CATEGORIES,
    CATEGORY_GROUPS,
    PSEUDO_CATEGORIES,
    chapter_hint,
    classify,
    group_of,
)

# (文件名, 期望分类)
CASES = [
    # 人格
    ("Personalities.json", "identity"),
    ("Personalities-x1p1c1.json", "identity"),
    ("Skills_personality-01.json", "identity"),
    ("Personality_Get_Condition.json", "identity"),
    ("AssociationName.json", "identity"),
    # 人格剧情
    ("StoryTheaterPersonality.json", "identity_story"),
    ("StoryTheaterMirrorWorld.json", "identity_story"),
    ("StoryTheaterMirrorWorldStoryTitle.json", "identity_story"),
    # E.G.O
    ("Egos.json", "ego"),
    ("Egos-a1c9p3.json", "ego"),
    ("Skills_Ego.json", "ego"),
    ("Skills_Ego_Personality-01.json", "ego"),
    ("EGO_Get_Condition.json", "ego"),
    ("Passive_Ego.json", "ego"),
    # 技能
    ("Skills.json", "skill"),
    ("SkillTag.json", "skill"),
    ("Skills_fools.json", "skill"),
    # 战斗效果
    ("BattleKeywords.json", "combat"),
    ("BattleKeywords_Mirror3.json", "combat"),
    ("Bufs.json", "combat"),
    ("Passives.json", "combat"),
    ("Passives_Assist-a1c8p2.json", "combat"),
    ("Passive-walpu2.json", "combat"),
    ("BuffAbilities.json", "combat"),
    ("MentalCondition.json", "combat"),
    ("UnitKeyword.json", "combat"),
    ("KeywordDictionary.json", "combat"),
    ("ResistText.json", "combat"),
    ("AttributeText.json", "combat"),
    ("ChoiceEventKeyword.json", "combat"),
    ("DanteAbility.json", "combat"),
    ("Assist-a1c7p2.json", "combat"),
    # 异想体
    ("AbnormalityGuides.json", "abnormality"),
    ("AbnormalityGuides_Mirror.json", "abnormality"),
    ("Skills_Abnormality.json", "abnormality"),
    ("Passives_Abnormality.json", "abnormality"),
    ("Passives_Abnormality91-4.json", "abnormality"),
    # 敌方单位
    ("Enemies.json", "enemy"),
    ("Enemies-a1c7p1.json", "enemy"),
    ("Skills_Enemy.json", "enemy"),
    ("Passives_Enemy.json", "enemy"),
    # 战斗对话
    ("AbDlg_DonQuixote.json", "battle_dialog"),
    ("BattleSpeechBubbleDlg.json", "battle_story"),  # 规则表已把战斗气泡并入「战斗剧情」
    ("PanicInfo.json", "battle_dialog"),
    ("Announcer.json", "battle_dialog"),
    ("AnnouncerVoiceType.json", "battle_dialog"),
    ("BattleAnnouncerDlg/x.json", "battle_dialog"),
    ("PersonalityVoiceDlg/x.json", "battle_dialog"),
    ("EGOVoiceDig/x.json", "battle_dialog"),
    # 罪人
    ("Characters.json", "sinner"),
    ("IntroduceCharacter.json", "sinner"),
    # 主线剧情
    ("StoryData/1D101A.json", "dungeon_story"),
    ("StoryData/PC01A.json", "event"),
    ("StoryData/ES011A.json", "event"),
    ("StoryData/P10310.json", "identity_story"),
    ("StoryTheaterMain.json", "main_story"),
    ("StoryTheaterDanteNote_2.json", "main_story"),
    ("StoryTheaterUIText.json", "ui"),
    ("StageNode1-4.json", "main_story"),
    ("StageNode91-14.json", "main_story"),
    ("StageChapterText.json", "main_story"),
    ("StagePartText.json", "main_story"),
    ("StageContinueText.json", "main_story"),
    ("DungeonNode1-4.json", "main_story"),
    ("DungeonArea1-3.json", "main_story"),
    ("StoryDungeonUI.json", "main_story"),
    ("Story-a1c8p3.json", "main_story"),
    # 间章与活动
    ("AbEvents.json", "battle_story"),  # 同上：^AbEvents 现归「战斗剧情」
    ("AbEvents_Mirror3.json", "battle_story"),
    ("AbEventsResultLog-walpu4.json", "battle_story"),
    ("ActionEvents.json", "battle_story"),  # ^ActionEvents 同为「战斗剧情」
    ("ChoiceEvent.json", "event"),
    ("ChoiceEventTarget.json", "event"),
    ("EventCommonText.json", "event"),
    ("EventTKTText.json", "event"),
    ("HellsChicken.json", "event"),
    ("CultivationEvent.json", "event"),
    ("TwiningThreadsEvent.json", "event"),
    ("DawnOfGreenEventText.json", "event"),
    ("NightCleanUpEvent.json", "event"),
    ("DailyLoginEvent.json", "event"),
    ("Fools2025.json", "event"),
    ("RecordMemoryEvent.json", "event"),
    ("DungeonName_Event.json", "event"),
    ("Walpu4EventText.json", "event"),
    ("Walpu7EventText-nextupdate.json", "event"),
    ("Limbus3rdAnniversary.json", "event"),
    # 折射轨道
    ("RailwayDungeon.json", "railway"),
    ("RailwayDungeonUI_2.json", "railway"),
    ("RailwayDungeonUI_1001.json", "railway"),
    ("RailwayDungeonNode1-1.json", "railway"),
    ("RailwayDungeonStationName1001.json", "railway"),
    ("RailwayDungeonBuff.json", "railway"),
    # 镜牢
    ("MirrorDungeonUI.json", "mirror"),
    ("MirrorDungeonUI_7_Achievement.json", "mirror"),
    ("MirrorDungeonTheme-1.json", "mirror"),
    ("MirrorDungeonBattleRewardCase.json", "mirror"),
    ("DungeonStartBuffs.json", "mirror"),
    ("MirrorEvent.json", "mirror_event"),
    ("DungeonEvent.json", "mirror_event"),
    ("EGOgift_MirrorDungeon.json", "ego_gift"),
    ("EgoGiftCategory.json", "ego_gift"),
    # 界面文本
    ("UI_ModuleDevice.json", "ui"),
    ("MainUIText.json", "ui"),
    ("MainUIText_UPDATE_ON_0720.json", "ui"),
    ("LoginUIText.json", "ui"),
    ("ShopUI.json", "ui"),
    ("SelectDUI.json", "ui"),
    ("SkinUI.json", "ui"),
    ("FormationUI_S6.json", "ui"),
    ("GachaNotice.json", "ui"),
    ("BattlePass.json", "ui"),
    ("BattleResultHint.json", "ui"),
    ("BattleUIText.json", "ui"),
    ("BossRaidUI.json", "ui"),
    ("UserBanner.json", "ui"),
    ("UserTicket-L.json", "ui"),
    ("UserInfo_Friends.json", "ui"),
    ("LobbyBGM.json", "ui"),
    ("Filter.json", "ui"),
    ("SeasonTitle.json", "ui"),
    ("SuccessRate.json", "ui"),
    ("ThreadDungeon.json", "ui"),
    ("RewardDungeonUI.json", "ui"),
    ("UpgradeCharacterUI.json", "ui"),
    ("IntegrateAccountUI.json", "ui"),
    ("IntroductionPreset.json", "ui"),
    ("MissionUIText.json", "ui"),
    ("Quest.json", "ui"),
    ("TooltipUIText.json", "ui"),
    ("StoryUIText.json", "ui"),
    ("PilgrimageUIText.json", "ui"),
    ("UnlockCode-1.json", "ui"),
    ("StageStatisticUIText.json", "ui"),
    ("ChoiceEventUI.json", "ui"),
    ("DanteAbilityUIText.json", "ui"),
    ("kr_settings-ui-donttranslate.json", "ui"),
    # 系统提示
    ("ErrorCodeMsg.json", "system"),
    ("UserAgreements.json", "system"),
    ("FAQ.json", "system"),
    ("ReturnPolicy.json", "system"),
    ("FileDownloadDesc.json", "system"),
    ("CouponUIText.json", "system"),
    # 教程
    ("TutorialDesc.json", "tutorial"),
    ("TutorialMainUIText.json", "tutorial"),
    ("TutorialMirrorDungeon.json", "tutorial"),
    ("BattleHint.json", "tutorial"),
    ("ShotcutKeyManual.json", "tutorial"),
    ("Skills_Tutorial.json", "tutorial"),
    # 道具与货币
    ("Items.json", "item"),
    ("IAPProduct.json", "item"),
    ("IAPSticker.json", "item"),
    ("ShopItemCount.json", "item"),
    ("AttendanceRewardsText.json", "item"),
    # 其他
    ("BgmLyrics/x.json", "other"),
    ("ProjectGS.json", "other"),
    ("Ch8TextEffectSettings.json", "other"),
    ("reward-popup-text-ProjectGS.json", "other"),
]


def test_classify_table():
    """期望值以 limbus_patcher/data/category_rules.json（用户手工维护）为准。"""
    for filename, expected in CASES:
        assert classify(filename) == expected, f"{filename} -> 期望 {expected}，实际 {classify(filename)}"


def test_sinner_of():
    from limbus_patcher.categories import sinner_of

    assert sinner_of("identity", 10102) == ("01", "李箱")
    assert sinner_of("identity", "10102_getCondition_normal") == ("01", "李箱")
    assert sinner_of("ego", 2120511) == ("12", "格里高尔")
    assert sinner_of("ego", 2010611) == ("01", "李箱")
    assert sinner_of("identity", "acheive") is None
    assert sinner_of("enemy", 8001) is None


def test_group_structure():
    members = [c for _g, (_l, ms) in CATEGORY_GROUPS.items() for c in ms]
    assert set(members) == set(CATEGORIES)
    assert len(members) == len(CATEGORIES)  # 无重复
    assert set(PSEUDO_CATEGORIES) == {"all", "favorites", "recent", "pending", "supplement"}  # supplement=补译文本
    assert group_of("identity") == "battle"
    assert group_of("mirror") == "story"
    assert group_of("item") == "system"
    assert group_of("other") == "system"  # 规则里已无 misc 组，「其他」并入系统与界面


HINT_CASES = [
    ("StageNode-a1c8p2.json", "第8章 第2部分"),
    ("Skills_Ego_Personality-a1c9p3.json", "第9章 第3部分"),
    ("BattleKeywords_Mirror3.json", "镜牢3"),
    ("MirrorDungeonUI_2.json", "镜牢2"),
    ("MirrorDungeonUI_7_Achievement.json", "镜牢7"),
    ("RailwayDungeonUI_1001.json", "折射轨道1号线"),
    ("RailwayDungeonStationName1002.json", "折射轨道2号线"),
    ("RailwayDungeonUI_6.json", "折射轨道6号线"),
    ("RailwayDungeonNode1-1.json", "折射轨道1号线"),
    ("Walpu4EventText.json", "瓦夜4"),
    ("AbEvents-tkt.json", "间章 4.5"),
    ("AbEvents-tktRe.json", "间章 4.5"),
    ("AbEvents_mowe.json", "间章 5.5"),
    ("AbEvents-twth.json", "间章 6.5"),
    ("AbEvents_lcbcheckup.json", "间章 7.5"),
    ("AbEvents-night-clean-up.json", "间章 7.5·续"),
    ("AbEvents-cultivation.json", "间章 8.5"),
    ("AbEvents-pilgrimage.json", "间章 8.5EX"),
    ("Skills_fools.json", "愚人节活动"),
    ("BattleKeywords.json", None),
]


def test_chapter_hint():
    for filename, expected in HINT_CASES:
        assert chapter_hint(filename) == expected, f"{filename} -> 期望 {expected}，实际 {chapter_hint(filename)}"


def test_fixture_files():
    assert classify("BattleKeywords.json") == "combat"
    assert classify("Skills_Ego_Personality-01.json") == "ego"
    assert classify("MainUIText.json") == "ui"
    assert classify("StoryData/1D101A.json") == "dungeon_story"
    assert classify("StoryData/P10310.json") == "identity_story"
    assert classify("BrokenFile.json") == "other"
