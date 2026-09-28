# -*- coding: utf-8 -*-
"""第10章第二部分：补「记录级缺口」（零协有同名文件、但缺这些 id）。

    python scripts/ch10p2_record_gaps.py            # 写入 + 自查
    python scripts/ch10p2_record_gaps.py --dry-run  # 只自查，不落盘

清单：data/translate/ch10p2/record_gaps.json（17 个文件 / 65 条）
落点：data/translate/files/<rel>（只含清单里那几条记录；已存在的文件按 id 追加，不删原有记录）
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EN_DIR = Path("D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data/Assets/Resources_moved/Localize/en")
LLC_DIR = Path("D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data/Lang/LLC_zh-CN")
GAPS = ROOT / "data/translate/ch10p2/record_gaps.json"
OUT_DIR = ROOT / "data/translate/files"

TEXT_FIELDS = {"name", "desc", "summary", "flavor", "content", "title", "nameWithTitle", "text", "abName"}

# ---------------------------------------------------------------- 译文表
# 说明字段里的 [Xxx] 一律原样保留；名字字段里的方括号按中文译。
TR: dict[str, dict[str, dict[str, str]]] = {}

# ===== BattleKeywords.json / Bufs.json（10 条，两文件同源，仅 ChargeKhakiAlly 的 desc 不同）=====
_COMMON = {
    "EmpathicDistressAlly": {
        "name": "感官裂痕",
        "desc": "- 最大值：5\n- 除自身外的友方单位受到攻击时，使自身的震颤 层数+1，并使本效果层数-1(每个技能最多1次)\n- 若场上没有除自身外的友方单位，则自身受到攻击时获得2级震颤 强度，并使本效果层数-1(每个技能最多1次)\n- 受到暴击攻击时，受到的伤害+(自身的震颤 强度)%(最多15%)",
        "flavor": "当察觉到心灵之形与躯体之形的差异时，裂痕便由此而生。",
    },
    "PersonalityVibration": {
        "name": "震颤人格",
        "desc": "拥有可施加震颤 强度、震颤 层数或特殊震颤的基础攻击技能的人格",
    },
    "PersonalityBreath": {
        "name": "呼吸法人格",
        "desc": "拥有可施加或获得呼吸法 强度、呼吸法 层数的基础攻击技能的人格",
    },
    "PersonalityCharge": {
        "name": "充能人格",
        "desc": "拥有可施加、获得或消耗充能 或特殊充能的基础攻击技能的人格",
    },
    "ChargeKhakiAlly": {
        "name": "漂流的惯性",
        "flavor": "如浮标般随潮而行者，或许无力改变世事的流向，却仍能助推潮水，并在其中践行自己的所为。",
    },
    "NoirScissorAlly": {
        "name": "裁剪的印记",
        "desc": "- 最大值：4\n- 带有本效果的目标被击败时，施加本效果的单位恢复5点理智值，并在下回合获得1层攻击等级提升 (每回合最多3次)",
        "flavor": "用于将面料及其他材料裁修至所需尺寸的剪裁标记。",
    },
    "NoirScissorCut": {
        "name": "花剪",
        "desc": "- 最大值：2\n- 每带有1层本效果，造成的伤害+7%",
        "flavor": "用以裁断地下所产原初素材的剪刀，更为巨大，亦更非凡。这把剪刀曾裁开、又重裁过最初织就的那匹布。花自其上绽放，自是理所当然——因它向来将万物从其根处剪断。",
    },
    "SupportAlly": {
        "name": "二元性",
        "desc": "技能可以将友方人格指定为目标\n技能自动指定目标时，或在常规遭遇战中，优先指定编队顺序最靠前的友方单位\n- 若目标为友方单位，则攻击不会命中，也不会触发守备技能(包括可拼点守备技能)\n若指定友方单位为目标，则在战斗开始时发动本技能",
    },
    "SupportEnemy": {
        "name": "二元性",
        "desc": "技能可以将友方单位指定为目标\n技能自动指定目标时，或在常规遭遇战中，随机指定友方单位\n- 若目标为友方单位，则攻击不会命中，也不会触发守备技能(包括可拼点守备技能)\n若指定友方单位为目标，则在战斗开始时发动本技能",
    },
    "NoirScissorShield": {
        "name": "第二剪·欢迎之剪",
        "desc": "- 最大值：1\n- 攻击等级+3，防御等级+3\n- 若自身为充能人格，则使用技能时恢复5点理智值(每回合最多1次)\n- 基础技能命中时，造成相当于该硬币最终伤害5%的斩击伤害\n- 回合结束时解除",
        "flavor": "剪刀因二而为一，又将曾为一体之物一分为二。",
    },
}
_CHARGE_KHAKI_DESC = "- 特殊充能\n- 最大层数：20\n- 本效果强度与层数的增减同样受普通充能 影响\n- 回合结束时，本效果的层数减少1层"

TR["BattleKeywords.json"] = copy.deepcopy(_COMMON)
TR["BattleKeywords.json"]["ChargeKhakiAlly"]["desc"] = _CHARGE_KHAKI_DESC
TR["Bufs.json"] = copy.deepcopy(_COMMON)
TR["Bufs.json"]["ChargeKhakiAlly"]["desc"] = _CHARGE_KHAKI_DESC + "\n\n<color=#1aece7>累计消耗层数：{2}</color>"

# ===== GachaTitle.json =====
TR["GachaTitle.json"] = {
    "297": {"content": "新人格定向提取 高级定制::改衣室 罗佳"},
}

# ===== IAPProduct-a1c10.json =====
_HAUTE = "高级定制::改衣室 罗佳"
TR["IAPProduct-a1c10.json"] = {
    "506": {
        "name": "特别提取组合包",
        "desc": "“新人格定向提取 - " + _HAUTE + "”发布纪念礼包，内含以下物品：\n\n· 十连提取券 x4",
    },
    "507": {
        "name": "人格养成组合包",
        "desc": "“新人格定向提取 - " + _HAUTE + "”发布纪念礼包，内含以下物品：\n\n· 跳跃成长模组 - 人格同步 x1\n· 人格训练券IV x90\n· 人格训练券III x40",
    },
}

# ===== IntroductionPreset.json =====
TR["IntroductionPreset.json"] = {
    "introduce_word_263": {"content": "面料"},
    "introduce_sentence_263": {"content": "想要上等的{0}，就得耐心等上一阵。"},
    "introduce_word_264": {"content": "手"},
    "introduce_sentence_264": {"content": "不！不不！离我远点！不要把{0}伸向我！！"},
    "introduce_word_265": {"content": "幻象"},
    "introduce_sentence_265": {"content": "……再将其带进我空洞的{0}之中。"},
}

# ===== MirrorDungeonRentalName.json =====
TR["MirrorDungeonRentalName.json"] = {"33": {"content": "充能"}}

# ===== Passive_Ego.json =====
TR["Passive_Ego.json"] = {
    "2061011": {
        "name": "无人受伤的城市",
        "desc": "[Charge]层数最大值+5\n\n消耗[Charge]层数或特殊[Charge]的技能3(E.G.O技能除外)造成的伤害+10%\n\n回合结束时，若本回合未受到攻击，则恢复4点理智值\n- 若自身拥有2个以上减号硬币基础攻击技能，则改为失去4点理智值(本效果不会使自身的理智值降至-40以下)",
    },
    "2091011": {
        "name": "分裂的触觉",
        "desc": "自身获得[Breath]强度或层数时，使自身的[Breath]层数+1(每回合最多2次)\n\n若自身为[PersonalityBreath]或[PersonalityVibration]，则攻击容量为1的基础技能或[WideAreaRampage]的基础技能造成的伤害+10%\n\n攻击结束时，若目标处于混乱状态或阵亡，则下回合将目标的[Vibration]强度1/3随机分摊给其他随机敌方单位(向上取整；集中遭遇战中改为部位)\n- 本效果不会与E.G.O饰品“镜反射触觉联觉”的效果叠加",
    },
}

# ===== Passives.json =====
TR["Passives.json"] = {
    "1091701": {
        "name": "改衣室中的花剪声",
        "desc": "回合结束时，下回合获得相当于[ChargeKhaki]层数的护盾\n自身的[ChargeKhaki]强度不低于2/3/5级时，使基础技能的最终威力+1/+2/+3",
        "summary": "基础技能的最终威力增加",
    },
    "1091702": {
        "name": "漂流的惯性",
        "desc": "本场战斗中，自身每累计消耗10层[ChargeKhaki]，便获得1级[ChargeKhaki]强度\n\n带有[NoirScissorShield]的其他友方单位攻击结束时，对该友方单位的目标发动“打版”(每回合最多1次)\n- [BeforeUse] 若该目标带有2层以上[NoirScissorAlly]，则改为发动“剪裁”(每回合最多1次)",
        "summary": "发动追加攻击",
    },
    "1091721": {
        "name": "第一剪·感恩之剪",
        "desc": "使速度值最高的1名友方单位使用斩击基础技能造成的伤害+10%",
        "summary": "追加斩击伤害",
        "flavor": "在所有剪子之中我最珍爱的那一把……也将属于你。",
    },
}

# ===== Personalities.json =====
TR["Personalities.json"] = {
    "10917": {
        "title": "高级定制::\n改衣室",
        "name": "罗佳",
        "nameWithTitle": "罗佳",
        "desc": "罗佳的第17人格",
    },
}

# ===== Personality_Get_Condition.json =====
TR["Personality_Get_Condition.json"] = {
    "10917_getCondition_normal": {"content": "高级定制::改衣室 罗佳 获得时"},
    "10917_getCondition_gacksung": {"content": "高级定制::改衣室 罗佳 3阶段同步完成"},
}

# ===== RPGSystem/rpg-loc-ui-common-a1c10p1.json =====
TR["RPGSystem/rpg-loc-ui-common-a1c10p1.json"] = {
    "FloorMoveUnboughtConfirmDesc": {"text": "本层还有尚未购买的道具。\n确定要移动到其他楼层吗？"},
    "FloorMoveUnboughtDontShowAgain": {"text": "不再显示此弹窗"},
    "LogPopup_Tab_Story": {"text": "故事日志"},
    "LogPopup_Tab_System": {"text": "系统日志"},
    "Setting_Sisyphus_LightMode": {"text": "光照模式"},
    "Setting_Sisyphus_Brightness": {"text": "亮度调节"},
    "Setting_Sisyphus_BrightnessCeiling": {"text": "亮度上限"},
    "Setting_Sisyphus_MoveAssist": {"text": "移动方向校正"},
    "Setting_Sisyphus_RunStartDelay": {"text": "奔跑限制时间"},
    "Setting_Sisyphus_VirtualPadWalkStart": {"text": "虚拟摇杆 行走阈值"},
    "Setting_Sisyphus_VirtualPadRunKeep": {"text": "虚拟摇杆 奔跑保持半径"},
    "Setting_Sisyphus_VirtualPadRunStart": {"text": "虚拟摇杆 奔跑阈值"},
    "Setting_Sisyphus_TurnAssist": {"text": "转向阈值调整"},
    "Setting_Sisyphus_RunStartDelayValue": {"text": "{0}秒"},
}

# ===== Skills_personality-09.json =====
_RETOUCHE_HEAD = "[CantDuel]\n[CantChangeTarget]\n[SupportAlly]\n"
_TR_1091701_L1 = (
    _RETOUCHE_HEAD
    + "\n[EndSkill] 若目标为友方单位，则对其施加3层[Charge]与1层[AttackUp]"
    + "\n[EndSkill] 若目标为友方单位，则发动以下效果(每回合最多1次)："
    + "\n- 施加相当于自身最大体力5%的护盾(最少1)"
    + "\n- 施加1层[NoirScissorShield]"
    + "\n- 若目标为[PersonalityCharge]，则施加1层[Enhancement]"
)
_TR_1091701_L2 = (
    _RETOUCHE_HEAD
    + "\n[EndSkill] 若目标为友方单位，则对其施加<style=\"highlight\">4</style>层[Charge]与1层[AttackUp]"
    + "\n[EndSkill] 若目标为友方单位，则发动以下效果(每回合最多1次)："
    + "\n- 施加相当于自身最大体力5%的护盾(最少1)"
    + "\n- 施加1层[NoirScissorShield]"
    + "\n- 若目标为[PersonalityCharge]，则施加1层[Enhancement]<style=\"highlight\"></style>"
)
_TR_1091701_L4 = (
    _RETOUCHE_HEAD
    + "\n[EndSkill] 若目标为友方单位，则对其施加4层[Charge]与1层[AttackUp]"
    + "\n[EndSkill] 若目标为友方单位，则发动以下效果<style=\"highlight\">(每回合最多2次)</style>："
    + "\n- 施加相当于自身最大体力<style=\"highlight\">10%</style>的护盾(最少1)"
    + "\n- 施加1层[NoirScissorShield]"
    + "\n- 若目标为[PersonalityCharge]，则施加2层[Enhancement]"
)

_TR_1091702_TAIL = (
    "\n\n[WhenUse] 若目标的[Vibration]强度不低于6级，则使本技能的硬币威力+1"
    "\n[WhenUse] 消耗5层[ChargeKhakiAlly]，使本技能的最终威力+2"
)
_TR_1091702_BULLETS = (
    "\n- 施加2层[AttackUp]"
    "\n- 施加相当于自身最大体力5%的护盾(最少1)"
    "\n- 若该人格为[PersonalityCharge]，则额外施加1层[AttackUp]与相当于自身最大体力5%的护盾"
)
_TR_1091702_L1 = (
    "[StartBattle] 使除自身外编队顺序最靠前的1名友方单位获得以下效果(优先[PersonalityCharge]；每回合最多1次)："
    + _TR_1091702_BULLETS + _TR_1091702_TAIL
)
_TR_1091702_L2 = (
    "[StartBattle] 使<style=\"highlight\">自身与</style>除自身外编队顺序最靠前的1名友方单位获得以下效果(优先[PersonalityCharge]；每回合最多1次)："
    + _TR_1091702_BULLETS + _TR_1091702_TAIL
)
_TR_1091702_L4 = (
    "[StartBattle] 使自身、除自身外编队顺序最靠前的1名友方单位(优先[PersonalityCharge])<style=\"highlight\">与现存体力比例最低的1名友方单位</style>获得以下效果(每回合最多1次)："
    + _TR_1091702_BULLETS
    + "\n\n<style=\"highlight\">[WhenUse] 目标每带有6级[Vibration]强度，使本技能的硬币威力+1(最多+2)</style>"
    + "\n[WhenUse] 消耗5层[ChargeKhakiAlly]，使本技能的最终威力+2"
)
_TR_1091702_COINS = [
    "[OnSucceedAttack] 使自身获得6层[ChargeKhakiAlly]",
    "[OnSucceedAttack] 使目标的[Vibration]层数增加2层",
    "[OnSucceedAttack] 使目标[VibrationExplosion]，并使其[Vibration]层数减少1层",
]

TR["Skills_personality-09.json"] = {
    "1091701": {
        "levelList/0/name": "改衣（Retouche）",
        "levelList/1/name": "改衣（Retouche）",
        "levelList/2/name": "改衣（Retouche）",
        "levelList/0/desc": _TR_1091701_L1,
        "levelList/1/desc": _TR_1091701_L2,
        "levelList/2/desc": _TR_1091701_L4,
    },
    "1091702": {
        "levelList/0/name": "固定，并沿纸样裁剪",
        "levelList/1/name": "固定，并沿纸样裁剪",
        "levelList/2/name": "固定，并沿纸样裁剪",
        "levelList/0/desc": _TR_1091702_L1,
        "levelList/1/desc": _TR_1091702_L2,
        "levelList/2/desc": _TR_1091702_L4,
        "levelList/0/coinlist/0/coindescs/0/desc": _TR_1091702_COINS[0],
        "levelList/0/coinlist/1/coindescs/0/desc": _TR_1091702_COINS[1],
        "levelList/0/coinlist/2/coindescs/0/desc": _TR_1091702_COINS[2],
        "levelList/1/coinlist/0/coindescs/0/desc": _TR_1091702_COINS[0] + "<style=\"highlight\"></style>",
        "levelList/1/coinlist/1/coindescs/0/desc": _TR_1091702_COINS[1] + "<style=\"highlight\"></style>",
        "levelList/1/coinlist/2/coindescs/0/desc": _TR_1091702_COINS[2] + "<style=\"highlight\"></style>",
        "levelList/2/coinlist/0/coindescs/0/desc": _TR_1091702_COINS[0] + "<style=\"highlight\"></style>",
        "levelList/2/coinlist/1/coindescs/0/desc": _TR_1091702_COINS[1] + "<style=\"highlight\"></style>",
        "levelList/2/coinlist/2/coindescs/0/desc": _TR_1091702_COINS[2] + "<style=\"highlight\"></style>",
        "levelList/2/coinlist/2/coindescs/1/desc": "[OnSucceedAttack] 对目标施加1层[AmberResistDown](每回合最多1次)<style=\"highlight\"></style>",
    },
    "1091703": {
        "levelList/0/name": "斜裁（Coupez dans le Biais）",
        "levelList/1/name": "斜裁（Coupez dans le Biais）",
        "levelList/0/desc": (
            "自身每带有1层[NoirScissorCut]，造成的伤害+15%(最多+30%)\n\n"
            "[StartBattle] 使除自身外编队顺序最靠前的1名友方单位(优先[PersonalityCharge])与现存体力比例最低的1名友方单位获得以下效果(每回合最多1次)："
            "\n- 施加1层[NoirScissorShield]"
            "\n- 施加相当于自身最大体力5%的护盾(最少1)\n\n"
            "[WhenUse] 若目标的[Vibration]强度不低于6级，则使本技能的硬币威力+1"
            "\n[WhenUse] 自身的[ChargeKhakiAlly]强度每有3级，使本技能的最终威力+1(最多+2)"
            "\n[WhenUse] 消耗5层[ChargeKhakiAlly]，使本技能的最终威力+2\n\n"
            "[EndSkill] 使自身获得5层[ChargeKhakiAlly]"
        ),
        "levelList/1/desc": (
            "自身每带有1层[NoirScissorCut]，造成的伤害<style=\"highlight\">+30%</style> <style=\"highlight\">(最多60%)</style>\n\n"
            "[StartBattle] 使自身、除自身外编队顺序最靠前的1名友方单位(优先[PersonalityCharge])与现存体力比例最低的1名友方单位获得以下效果(每回合最多1次)："
            "\n- 施加1层[NoirScissorShield]"
            "\n- 施加相当于自身最大体力<style=\"highlight\">10%</style>的护盾(最少1)\n\n"
            "<style=\"highlight\">[WhenUse] 目标每带有6级[Vibration]强度，使本技能的硬币威力+1(最多+2)</style>"
            "\n[WhenUse] 自身的[ChargeKhakiAlly]强度每有3级，使本技能的最终威力+1(最多+2)"
            "\n[WhenUse] 消耗5层[ChargeKhakiAlly]，使本技能的最终威力+2\n\n"
            "[EndSkill] 使自身获得5层[ChargeKhakiAlly]"
        ),
        "levelList/0/coinlist/0/coindescs/0/desc": "[OnSucceedAttack] 使目标的[Vibration]层数增加3层",
        "levelList/0/coinlist/0/coindescs/1/desc": "[OnSucceedAttack] 对目标施加1层[NoirScissorAlly]",
        "levelList/0/coinlist/1/coindescs/0/desc": "[OnSucceedAttack] 对目标施加3层[Vibration]",
        "levelList/0/coinlist/2/coindescs/0/desc": "[OnSucceedAttack] 对目标施加1层[NoirScissorAlly]",
        "levelList/0/coinlist/2/coindescs/1/desc": "[OnSucceedAttack] 使目标[VibrationExplosion]，并使其[Vibration]层数减少1层",
        "levelList/0/coinlist/2/coindescs/2/desc": "[OnSucceedAttack] 若自身的[ChargeKhakiAlly]层数不低于5层，则消耗5层[ChargeKhakiAlly]，使目标[VibrationExplosion]，并使其[Vibration]层数减少1层",
        "levelList/1/coinlist/0/coindescs/0/desc": "[OnSucceedAttack] 使目标的[Vibration]层数增加3层",
        "levelList/1/coinlist/0/coindescs/1/desc": "[OnSucceedAttack] 对目标施加1层[NoirScissorAlly]",
        "levelList/1/coinlist/1/coindescs/0/desc": "[OnSucceedAttack] 对目标施加3层[Vibration]",
        "levelList/1/coinlist/2/coindescs/0/desc": "[OnSucceedAttack] 对目标施加1层[NoirScissorAlly]",
        "levelList/1/coinlist/2/coindescs/1/desc": "[OnSucceedAttack] 使目标[VibrationExplosion]，并使其[Vibration]层数减少1层",
        "levelList/1/coinlist/2/coindescs/2/desc": "[OnSucceedAttack] 若自身的[ChargeKhakiAlly]层数不低于5层，则消耗5层[ChargeKhakiAlly]，使目标[VibrationExplosion]，并使其[Vibration]层数减少1层",
    },
    "1091704": {
        "levelList/0/name": "修剪",
        "levelList/1/name": "修剪",
        "levelList/0/desc": (
            "[DuelCounter]\n"
            "[StartBattle] 使自身获得5层[ChargeKhakiAlly](每回合最多2次)\n"
            "[StartBattle] 使自身与除自身外现存体力比例最低的2名友方单位获得相当于自身最大体力5%的护盾(最少1，每回合最多1次)"
        ),
        "levelList/1/desc": (
            "[DuelCounter]\n"
            "[StartBattle] 使自身获得5层[ChargeKhakiAlly](每回合最多2次)\n"
            "[StartBattle] 使自身与除自身外现存体力比例最低的2名友方单位获得相当于自身最大体力<style=\"highlight\">10%</style>的护盾(最少1，每回合最多1次)\n\n"
            "<style=\"highlight\">[WhenUse] 自身的[ChargeKhakiAlly]层数每有5层，使本技能的拼点威力+1(最多+4)</style>"
        ),
        "levelList/0/coinlist/0/coindescs/0/desc": "[OnSucceedAttack] 对目标施加2层[Vibration]",
        "levelList/1/coinlist/0/coindescs/0/desc": "[OnSucceedAttack] 对目标施加2层[Vibration]",
    },
    "1091705": {
        "levelList/0/name": "打版",
        "levelList/0/desc": "[CantDuel]\n[WhenUse] 使自身获得3层[ChargeKhakiAlly]",
        "levelList/0/coinlist/0/coindescs/0/desc": "[OnSucceedAttack] 若自身的[ChargeKhakiAlly]强度不低于3级，则重复使用本硬币(每个技能最多1次)",
        "levelList/0/coinlist/0/coindescs/1/desc": "[OnSucceedAttack] 使目标的[Vibration]层数增加1层",
        "levelList/0/coinlist/0/coindescs/2/desc": "[OnSucceedAttack] 对目标施加1层[NoirScissorAlly]",
    },
    "1091706": {
        "levelList/0/name": "剪裁",
        "levelList/0/desc": (
            "[CantDuel]\n"
            "[WhenUse] 自身的[ChargeKhakiAlly]强度每有3级，使本技能的最终威力+1(最多+2)\n"
            "[WhenUse] 使自身获得5层[ChargeKhakiAlly]\n\n"
            "[EndSkill] 消耗目标的2层[NoirScissorAlly]\n"
            "[EndSkill] 使自身获得1层[NoirScissorCut]"
        ),
        "levelList/0/coinlist/0/coindescs/0/desc": "[OnSucceedAttack] 对目标施加3层[Vibration]",
        "levelList/0/coinlist/1/coindescs/0/desc": "[OnSucceedAttack] 使目标[VibrationExplosion]，并使其[Vibration]层数减少1层",
    },
}

# ===== Skills_Ego_Personality-06.json =====
_EGO6_NAME = "拒绝宣言"
_EGO6_AB = "梅特罗波拉利斯的居民"
_EGO6_TAIL = "\n[BeforeAttack] 最多消耗自身的{consume}层[Charge]，随后使自身与随机其他友方单位获得{ff}层[ChargeForceField](最多{maxu}名单位；对象数为1 + 消耗的[Charge]层数/2，向下取整)"

TR["Skills_Ego_Personality-06.json"] = {
    "2061011": {
        "levelList/0/name": _EGO6_NAME, "levelList/1/name": _EGO6_NAME, "levelList/2/name": _EGO6_NAME,
        "levelList/0/abName": _EGO6_AB, "levelList/1/abName": _EGO6_AB, "levelList/2/abName": _EGO6_AB,
        "levelList/0/desc": (
            "[BeforeAttack] 使自身获得1层[Charge]"
            + _EGO6_TAIL.format(consume=6, ff=5, maxu=5)
        ),
        "levelList/1/desc": (
            "<style=\"highlight\">[WhenUse] 使本技能的拼点威力+自身的[Charge]强度(最多+2)</style>"
            "\n[BeforeAttack] 使自身获得<style=\"highlight\">3</style>层[Charge]"
            + _EGO6_TAIL.format(consume="<style=\"highlight\">8</style>", ff=5, maxu="<style=\"highlight\">6</style>")
        ),
        "levelList/2/desc": (
            "[WhenUse] 使本技能的拼点威力+自身的[Charge]强度(最多<style=\"highlight\">3</style>)"
            "\n[BeforeAttack] 使自身获得<style=\"highlight\">5</style>层[Charge]"
            + _EGO6_TAIL.format(consume="<style=\"highlight\">10</style>", ff=5, maxu="<style=\"highlight\">7</style>")
        ),
        "levelList/0/coinlist/0/coindescs/0/desc": "[OnSucceedAttack] 使自身获得2层[Charge]",
        "levelList/1/coinlist/0/coindescs/0/desc": "[OnSucceedAttack] 使自身获得2层[Charge]",
        "levelList/2/coinlist/0/coindescs/0/desc": "[OnSucceedAttack] 使自身获得2层[Charge]",
        "levelList/1/coinlist/1/coindescs/0/desc": "<style=\"highlight\">[OnSucceedAttack] 对目标施加1层[PhotoElectricity]</style>",
        "levelList/2/coinlist/1/coindescs/0/desc": "[OnSucceedAttack] 对目标施加<style=\"highlight\">2</style>层[PhotoElectricity]",
    },
    "2061021": {
        "levelList/0/name": _EGO6_NAME, "levelList/1/name": _EGO6_NAME, "levelList/2/name": _EGO6_NAME,
        "levelList/0/abName": _EGO6_AB, "levelList/1/abName": _EGO6_AB, "levelList/2/abName": _EGO6_AB,
        "levelList/0/desc": (
            "[CantIdentify]\n随机指定目标\n对带有护盾的目标造成的伤害+15%"
            "\n[BeforeAttack] 本技能每有1枚硬币被摧毁，使本技能的基础威力-6(最多-12)"
            "\n[BeforeAttack] 使自身获得3层[Charge]"
            + _EGO6_TAIL.format(consume=6, ff=7, maxu=5)
        ),
        "levelList/1/desc": (
            "[CantIdentify]\n随机指定目标\n对带有护盾的目标造成的伤害+<style=\"highlight\">20</style>%"
            "\n[BeforeAttack] 本技能每有1枚硬币被摧毁，使本技能的基础威力-6(最多-12)\n"
            "<style=\"highlight\">[BeforeAttack] 使本技能的最终威力+自身的[Charge]强度(最多+2)</style>"
            "\n[BeforeAttack] 使自身获得<style=\"highlight\">4</style>层[Charge]"
            + _EGO6_TAIL.format(consume="<style=\"highlight\">8</style>", ff=7, maxu="<style=\"highlight\">6</style>")
        ),
        "levelList/2/desc": (
            "[CantIdentify]\n随机指定目标\n对带有护盾的目标造成的伤害+<style=\"highlight\">25</style>%"
            "\n[BeforeAttack] 本技能每有1枚硬币被摧毁，使本技能的基础威力-6(最多-12)"
            "\n[BeforeAttack] 使本技能的最终威力+自身的[Charge]强度(最多<style=\"highlight\">3</style>)"
            "\n[BeforeAttack] 使自身获得<style=\"highlight\">5</style>层[Charge]"
            + _EGO6_TAIL.format(consume="<style=\"highlight\">10</style>", ff=7, maxu="<style=\"highlight\">7</style>")
        ),
        "levelList/0/coinlist/0/coindescs/1/desc": "[OnSucceedAttack] 使自身获得2层[Charge]",
        "levelList/1/coinlist/0/coindescs/1/desc": "[OnSucceedAttack] 使自身获得2层[Charge]",
        "levelList/2/coinlist/0/coindescs/1/desc": "[OnSucceedAttack] 使自身获得2层[Charge]",
        "levelList/0/coinlist/1/coindescs/1/desc": "[OnStartCoin] 最多消耗自身的10层[Charge]，随后使本硬币的最终威力增加消耗的层数",
        "levelList/1/coinlist/1/coindescs/1/desc": "[OnStartCoin] 最多消耗自身的10层[Charge]，随后使本硬币的最终威力增加消耗的层数",
        "levelList/2/coinlist/1/coindescs/1/desc": "[OnStartCoin] 最多消耗自身的10层[Charge]，随后使本硬币的最终威力增加消耗的层数",
        "levelList/1/coinlist/1/coindescs/2/desc": "<style=\"highlight\">[OnSucceedAttack] 对目标施加1层[PhotoElectricity]</style>",
        "levelList/2/coinlist/1/coindescs/2/desc": "[OnSucceedAttack] 对目标施加<style=\"highlight\">2</style>层[PhotoElectricity]",
    },
}

# ===== Skills_Ego_Personality-09.json =====
_EGO9_NAME = "镜之触觉"
_EGO9_AB = "迷途之心"
_EGO9_HEAD = "自身的[Breath]强度与主要目标的[Vibration]强度之和每有6级，使本技能的拼点威力+1(最多{mx})\n[BeforeAttack] 使自身增加({v} + 最大共鸣数)级[Breath]强度(最多{mx2}级)\n[BeforeAttack] 使自身获得{c}层[Breath]\n"
_EGO9_END = "[EndSkill] 在目标之间随机分配(1 + 最大共鸣数)层[EmpathicDistressAlly]，每次1层(最多5层)"
_EGO9_VIB = "[OnSucceedAttack] 使目标[VibrationExplosion]，并使其[Vibration]层数减少1层"

TR["Skills_Ego_Personality-09.json"] = {
    "2091011": {
        "levelList/0/name": _EGO9_NAME, "levelList/1/name": _EGO9_NAME, "levelList/2/name": _EGO9_NAME,
        "levelList/0/abName": _EGO9_AB, "levelList/1/abName": _EGO9_AB, "levelList/2/abName": _EGO9_AB,
        "levelList/0/desc": _EGO9_HEAD.format(mx=2, v=2, mx2=8, c=2) + _EGO9_END,
        "levelList/1/desc": _EGO9_HEAD.format(mx="<style=\"highlight\">3</style>", v="<style=\"highlight\">3</style>", mx2=8, c="<style=\"highlight\">3</style>") + _EGO9_END,
        "levelList/2/desc": _EGO9_HEAD.format(mx="<style=\"highlight\">4</style>", v="<style=\"highlight\">4</style>", mx2=8, c="<style=\"highlight\">4</style>") + _EGO9_END,
        "levelList/0/coinlist/0/coindescs/0/desc": "[OnSucceedAttack] 对目标施加2层[Vibration]",
        "levelList/1/coinlist/0/coindescs/0/desc": "[OnSucceedAttack] 对目标施加<style=\"highlight\">3</style>层[Vibration]",
        "levelList/2/coinlist/0/coindescs/0/desc": "[OnSucceedAttack] 对目标施加<style=\"highlight\">4</style>层[Vibration]",
        "levelList/0/coinlist/1/coindescs/0/desc": "[OnSucceedAttack] 使目标的[Vibration]层数增加1层",
        "levelList/1/coinlist/1/coindescs/0/desc": "[OnSucceedAttack] 使目标的[Vibration]层数增加<style=\"highlight\">2</style>层",
        "levelList/2/coinlist/1/coindescs/0/desc": "[OnSucceedAttack] 使目标的[Vibration]层数增加<style=\"highlight\">3</style>层",
        "levelList/0/coinlist/2/coindescs/0/desc": "[OnSucceedAttack] 对目标施加2层[AttackDown]",
        "levelList/1/coinlist/2/coindescs/0/desc": "[OnSucceedAttack] 对目标施加2层[AttackDown]",
        "levelList/2/coinlist/2/coindescs/0/desc": "[OnSucceedAttack] 对目标施加2层[AttackDown]",
        "levelList/0/coinlist/2/coindescs/1/desc": _EGO9_VIB,
        "levelList/1/coinlist/2/coindescs/1/desc": _EGO9_VIB,
        "levelList/2/coinlist/2/coindescs/1/desc": _EGO9_VIB,
    },
    "2091021": {
        "levelList/0/name": _EGO9_NAME, "levelList/1/name": _EGO9_NAME, "levelList/2/name": _EGO9_NAME,
        "levelList/0/abName": _EGO9_AB, "levelList/1/abName": _EGO9_AB, "levelList/2/abName": _EGO9_AB,
        "levelList/0/desc": (
            "[CantIdentify]\n随机指定目标\n"
            + _EGO9_HEAD.format(mx=2, v=2, mx2=10, c=2)
            + "[BeforeAttack] 本技能每有1枚硬币被摧毁，使本技能的基础威力-4(最多-12)\n"
            + "[BeforeAttack] 若自身的[Breath]层数不低于10层，则消耗4层[Breath]，使本技能对主要目标造成的暴击伤害+20%\n"
            + _EGO9_END
        ),
        "levelList/1/desc": (
            "[CantIdentify]\n随机指定目标\n"
            + _EGO9_HEAD.format(mx="<style=\"highlight\">3</style>", v="<style=\"highlight\">3</style>", mx2=10, c="<style=\"highlight\">3</style>")
            + "[BeforeAttack] 本技能每有1枚硬币被摧毁，使本技能的基础威力-4(最多-12)\n"
            + "[BeforeAttack] 若自身的[Breath]层数不低于10层，则消耗4层[Breath]，使本技能对主要目标造成的暴击伤害+<style=\"highlight\">30</style>%\n"
            + _EGO9_END
        ),
        "levelList/2/desc": (
            "[CantIdentify]\n随机指定目标\n"
            + _EGO9_HEAD.format(mx="<style=\"highlight\">4</style>", v="<style=\"highlight\">4</style>", mx2=10, c="<style=\"highlight\">4</style>")
            + "[BeforeAttack] 本技能每有1枚硬币被摧毁，使本技能的基础威力-4(最多-12)\n"
            + "[BeforeAttack] 若自身的[Breath]层数不低于10层，则消耗4层[Breath]，使本技能对主要目标造成的暴击伤害+<style=\"highlight\">40</style>%\n"
            + _EGO9_END
        ),
        "levelList/0/coinlist/0/coindescs/1/desc": "[OnSucceedAttack] 对目标施加3层[Vibration]",
        "levelList/1/coinlist/0/coindescs/1/desc": "[OnSucceedAttack] 对目标施加<style=\"highlight\">4</style>层[Vibration]",
        "levelList/2/coinlist/0/coindescs/1/desc": "[OnSucceedAttack] 对目标施加<style=\"highlight\">5</style>层[Vibration]",
        "levelList/0/coinlist/0/coindescs/2/desc": "[OnSucceedAttack] 使目标的[Vibration]层数增加1层",
        "levelList/1/coinlist/0/coindescs/2/desc": "[OnSucceedAttack] 使目标的[Vibration]层数增加1层",
        "levelList/2/coinlist/0/coindescs/2/desc": "[OnSucceedAttack] 使目标的[Vibration]层数增加1层",
        "levelList/0/coinlist/0/coindescs/3/desc": "[OnSucceedAttack] 若目标的[Vibration]层数不低于4层，则使目标[VibrationExplosion]，并使其[Vibration]层数减少1层",
        "levelList/1/coinlist/0/coindescs/3/desc": "[OnSucceedAttack] 若目标的[Vibration]层数不低于4层，则使目标[VibrationExplosion]，并使其[Vibration]层数减少1层",
        "levelList/2/coinlist/0/coindescs/3/desc": "[OnSucceedAttack] 若目标的[Vibration]层数不低于4层，则使目标[VibrationExplosion]，并使其[Vibration]层数减少1层",
        "levelList/0/coinlist/1/coindescs/1/desc": "[OnSucceedAttack] 使目标的[Vibration]层数增加1层",
        "levelList/1/coinlist/1/coindescs/1/desc": "[OnSucceedAttack] 使目标的[Vibration]层数增加1层",
        "levelList/2/coinlist/1/coindescs/1/desc": "[OnSucceedAttack] 使目标的[Vibration]层数增加2层",
        "levelList/0/coinlist/1/coindescs/2/desc": "[OnSucceedAttack] 若目标的[Vibration]层数不低于4层，则使目标[VibrationExplosion]，并使其[Vibration]层数减少1层",
        "levelList/1/coinlist/1/coindescs/2/desc": "[OnSucceedAttack] 若目标的[Vibration]层数不低于4层，则使目标[VibrationExplosion]，并使其[Vibration]层数减少1层",
        "levelList/2/coinlist/1/coindescs/2/desc": "[OnSucceedAttack] 若目标的[Vibration]层数不低于4层，则使目标[VibrationExplosion]，并使其[Vibration]层数减少1层",
        "levelList/0/coinlist/2/coindescs/1/desc": "[OnSucceedAttack] 对目标施加3层[AttackDown]",
        "levelList/1/coinlist/2/coindescs/1/desc": "<style=\"highlight\">[OnSucceedAttack] 使目标的[Vibration]层数增加1层</style>",
        "levelList/2/coinlist/2/coindescs/1/desc": "<style=\"highlight\">[OnSucceedAttack] 使目标的[Vibration]层数增加1层</style>",
        "levelList/0/coinlist/2/coindescs/2/desc": _EGO9_VIB,
        "levelList/1/coinlist/2/coindescs/2/desc": "[OnSucceedAttack] 对目标施加3层[AttackDown]<style=\"highlight\"></style>",
        "levelList/2/coinlist/2/coindescs/2/desc": "[OnSucceedAttack] 对目标施加3层[AttackDown]<style=\"highlight\"></style>",
        "levelList/1/coinlist/2/coindescs/3/desc": _EGO9_VIB + "<style=\"highlight\"></style>",
        "levelList/2/coinlist/2/coindescs/3/desc": _EGO9_VIB + "<style=\"highlight\"></style>",
    },
}

# ===== StoryTheaterMirrorWorldStoryTitle.json =====
TR["StoryTheaterMirrorWorldStoryTitle.json"] = {
    "MirrorWorld_Story_Title_P10917": {"content": "高级定制::改衣室，罗佳的故事"},
}

# ===== StoryTheaterUIText.json =====
TR["StoryTheaterUIText.json"] = {"B": {"content": "B"}}

# ===== UnitKeyword.json =====
TR["UnitKeyword.json"] = {"UnitKeyword_LE_KHAKI": {"content": "褐派"}}


# ---------------------------------------------------------------- 工具
def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def en_path(rel: str) -> Path:
    p = Path(rel)
    return EN_DIR / p.parent / ("EN_" + p.name)


def set_path(node, path: str, value: str) -> None:
    cur = node
    segs = path.split("/")
    for seg in segs[:-1]:
        cur = cur[int(seg)] if isinstance(cur, list) else cur[seg]
    last = segs[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


HANGUL = re.compile(r"[\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f]")
TOK_BRACKET = re.compile(r"\[[^\[\]]*\]")
TOK_TAG = re.compile(r"<[^<>]*>")
TOK_PLACE = re.compile(r"\{\d+\}")


def struct_key(s: str):
    return (TOK_BRACKET.findall(s), TOK_TAG.findall(s), TOK_PLACE.findall(s), s.count("\n"))


def walk_strings(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk_strings(v, f"{path}/{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_strings(v, f"{path}/{i}")
    elif isinstance(node, str):
        yield path, node


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--exact", action="store_true",
                    help="已存在的文件按清单「不多不少」整份覆盖（默认是保留原有记录、只追加缺的）")
    args = ap.parse_args()

    gaps = load_json(GAPS)["files"]
    problems: list[str] = []
    summary: list[str] = []
    unchanged: list[str] = []

    for entry in gaps:
        rel = entry["rel"]
        keys = [k.split("=", 1)[1] for k in entry["keys"]]
        idf = "id" if entry["keys"][0].startswith("id=") else "key"
        tr = TR.get(rel)
        if tr is None:
            problems.append(f"{rel}: 译文表缺失")
            continue
        if set(tr) != set(keys):
            problems.append(f"{rel}: 译文表 id 与清单不一致 {sorted(set(tr) ^ set(keys))}")

        en_records = load_json(en_path(rel))["dataList"]
        en_by_id = {str(r[idf]): r for r in en_records}
        out_records = []
        for key in keys:
            if key not in en_by_id:
                problems.append(f"{rel}: 英文基线里找不到 {key}")
                continue
            rec = copy.deepcopy(en_by_id[key])
            for p, v in tr[key].items():
                try:
                    set_path(rec, p, v)
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"{rel}#{key}: 路径 {p} 写入失败（{exc}）")
            # 结构自查
            for path, en_s in walk_strings(en_by_id[key]):
                zh_s = dict(walk_strings(rec))[path]
                if en_s.strip() and not zh_s.strip():
                    problems.append(f"{rel}#{key}.{path}: 英文非空但译文为空")
                if struct_key(en_s) != struct_key(zh_s):
                    problems.append(f"{rel}#{key}.{path}: 结构不一致\n    EN={struct_key(en_s)}\n    ZH={struct_key(zh_s)}")
                    continue
                if HANGUL.search(zh_s):
                    problems.append(f"{rel}#{key}.{path}: 夹了韩文")
                leaf = path.rsplit("/", 1)[-1]
                if leaf in TEXT_FIELDS and en_s == zh_s and re.search(r"[A-Za-z]", en_s) and en_s.strip() not in ("-",):
                    unchanged.append(f"{rel}#{key}.{path} = {en_s!r}")
            out_records.append(rec)

        dst = OUT_DIR / rel
        if dst.exists() and not args.exact:
            old = load_json(dst)["dataList"]
            have = {str(r.get(idf)) for r in old}
            merged = old + [r for r in out_records if str(r.get(idf)) not in have]
            payload = {"dataList": merged}
            note = f"（追加 {len(merged) - len(old)} 条，保留原有 {len(old)} 条）"
        else:
            payload = {"dataList": out_records}
            note = ""
        text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
        blob = text.replace("\n", "\r\n").encode("utf-8")
        if not args.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(blob)
        summary.append(f"{rel}: {len(out_records)} 条{note}")

        # 落盘后再验一次：文件里清单 id 恰好齐、能 load、无空字段
        if not args.dry_run:
            check = load_json(dst)["dataList"]
            got = {str(r.get(idf)) for r in check}
            miss = [k for k in keys if k not in got]
            if miss:
                problems.append(f"{rel}: 落盘后缺 {miss}")
            for r in check:
                for path, v in walk_strings(r):
                    if not isinstance(v, str):
                        continue
            raw = dst.read_bytes()
            if not raw.startswith(b"{\r\n"):
                problems.append(f"{rel}: 行尾/缩进不符合既有格式")

    print("== 写入/自查 ==")
    for line in summary:
        print("  ", line)
    print("文件数", len(summary), "记录数", sum(int(s.split(": ")[1].split(" ")[0]) for s in summary))
    if unchanged:
        print("== 与英文一致、需人工确认的字段 ==")
        for u in unchanged:
            print("  ", u)
    if problems:
        print("== 问题 ==")
        for p in problems:
            print("  ", p)
        return 1
    print("SELFTEST OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
