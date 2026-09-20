"""章节/关卡推导测试。"""
from __future__ import annotations

from limbus_patcher.story import chapter_sort_key, story_of

CASES = [
    # level_key/level_label 由 category_rules.json 推出：上一轮把 ^AbEvents 归到「战斗剧情」，
    # 所以这些间章文件的分级标签是 type:battle_story（章节仍是「间章 N」）。
    # (文件名, chapter_id, chapter_label, level_key, level_label)
    ("StageNode-a1c7p3.json", "c7", "第7章", "p3", "第3部分"),
    ("AbEvents-a1c6p2.json", "c6", "第6章", "p2", "第2部分"),
    ("Enemies-a1c5p1.json", "c5", "第5章", "p1", "第1部分"),
    ("BattleKeywords-a1c8p2.json", "c8", "第8章", "p2", "第2部分"),
    ("StoryData/1D101A.json", "c1", "第1章", "1D10", "对话 1D10"),
    ("StoryData/S001A.json", "prologue", "序章", "S001", "剧情 S001"),
    ("StoryData/S101B.json", "c1", "第1章", "S101", "剧情 S101"),
    ("StoryData/P10102.json", "c1", "第1章", "P101", "演出 P101"),
    ("StoryData/E003X.json", "prologue", "序章", "E003", "事件 E003"),
    ("StoryData/E041X.json", "c4", "第4章", "E041", "事件 E041"),
    ("DungeonNode1-4.json", "c1", "第1章", "node1", "节点 1"),
    ("DungeonArea1-3.json", "c1", "第1章", "area1", "区域 1"),
    ("StageNode1-4.json", "c1", "第1章", "stage1", "关卡 1"),
    ("AbEvents-tkt.json", "i45", "间章 4.5", "type:battle_story", "战斗剧情"),
    ("AbEvents-tktRe.json", "i45", "间章 4.5", "type:battle_story", "战斗剧情"),
    ("EventTKTText.json", "i45", "间章 4.5", "type:event", "间章与活动"),
    ("AbEvents_mowe.json", "i55", "间章 5.5", "type:battle_story", "战斗剧情"),
    ("EventMiracleText.json", "i55", "间章 5.5", "type:event", "间章与活动"),
    ("AbEvents-twth.json", "i65", "间章 6.5", "type:battle_story", "战斗剧情"),
    ("AbEvents_lcbcheckup.json", "i75", "间章 7.5", "type:battle_story", "战斗剧情"),
    ("AbEvents-night-clean-up.json", "i75b", "间章 7.5·续", "type:battle_story", "战斗剧情"),
    ("AbEvents-cultivation.json", "i85", "间章 8.5", "type:battle_story", "战斗剧情"),
    ("AbEvents-pilgrimage.json", "i85ex", "间章 8.5EX", "type:battle_story", "战斗剧情"),
    ("HellsChicken.json", "i35", "间章 3.5", "type:event", "间章与活动"),
    ("Skills_fools.json", "fools", "愚人节活动", "type:skill", "技能"),
    ("BattleKeywords-fools.json", "fools", "愚人节活动", "type:combat", "战斗效果"),
    ("Walpu4EventText.json", "walpu4", "瓦夜4", "all", "全部关卡"),
    ("Enemies-walpu5.json", "walpu5", "瓦夜5", "all", "全部关卡"),
    ("MirrorDungeonUI_2.json", "mirror2", "镜牢2", "all", "全部关卡"),
    ("MirrorDungeonUI_7_Achievement.json", "mirror7", "镜牢7", "all", "全部关卡"),
    ("BattleKeywords_Mirror3.json", "mirror3", "镜牢3", "all", "全部关卡"),
    ("DungeonStartBuffs.json", "mirror", "镜牢", "all", "全部关卡"),
    ("DungeonStartBuffs_MD6.json", "mirror6", "镜牢6", "all", "全部关卡"),
    ("Passives_Abnormality-mr7.json", "mirror7", "镜牢7", "all", "全部关卡"),
    ("RailwayDungeonUI_1001.json", "railway", "折射轨道1号线", "all", "全部关卡"),
    ("RailwayDungeonStationName1002.json", "railway", "折射轨道2号线", "all", "全部关卡"),
    ("RailwayDungeonUI_6.json", "railway", "折射轨道6号线", "all", "全部关卡"),
    ("RailwayDungeonNode1-1.json", "railway", "折射轨道1号线", "all", "全部关卡"),
    ("Limbus3rdAnniversary.json", "anniv", "周年活动", "all", "全部关卡"),
    ("AbEvents_exme.json", "events", "活动", "type:battle_story", "战斗剧情"),
    ("MainUIText.json", None, None, None, None),
    ("Personalities.json", None, None, None, None),
    ("BgmLyrics/x.json", None, None, None, None),
]


def test_story_of():
    for filename, cid, clabel, lkey, llabel in CASES:
        ref = story_of(filename)
        if cid is None:
            assert ref is None, f"{filename} 期望无章节，实际 {ref}"
            continue
        assert ref is not None, f"{filename} 期望有章节"
        assert (ref.chapter_id, ref.chapter_label, ref.level_key, ref.level_label) == (cid, clabel, lkey, llabel), filename


def test_sort_key():
    keys = ["c9", "prologue", "walpu4", "i45", "mirror3", "railway", "c1", "events", "zzz"]
    ordered = sorted(keys, key=chapter_sort_key)
    assert ordered.index("prologue") < ordered.index("c1") < ordered.index("c9")
    assert ordered.index("c9") < ordered.index("i45") < ordered.index("walpu4")
    assert ordered.index("walpu4") < ordered.index("mirror3") < ordered.index("railway") < ordered.index("events")
    assert ordered[-1] == "zzz"
