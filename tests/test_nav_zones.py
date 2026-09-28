"""导航分区的守卫：确保「导航里点得到全部文本类别」这件事不回退。

背景：改版前 `NavPanel.set_counts` 只渲染出 人格图鉴 / 敌方图鉴 / 剧本模式 与
「系统与界面」组，人格、E.G.O、技能、镜牢、异想体、战斗效果等十几类在导航里
**根本点不到**，只能去列表顶部的分类下拉里翻。改版按游戏原版分区重排后，
`NAV_ZONES` 的叶子必须恰好覆盖 `CATEGORIES` 的全部键。

规范见 `docs/ui-redesign/DESIGN_SYSTEM.md` §5。
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from limbus_patcher import categories
from limbus_patcher.ui import theme
from limbus_patcher.ui.nav import NavPanel

#: `NAV_ZONES` 里的虚拟入口 —— 不是 `CATEGORIES` 的键，但导航要暴露
VIRTUAL_KEYS = {"script"}


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app, "bus")
    return app


def _zone_real_keys() -> list[str]:
    return [
        k for _z, _l, leaves in categories.NAV_ZONES
        for k, _n in leaves
        if k not in VIRTUAL_KEYS and not k.startswith(("role:", "entities:"))
    ]


def test_分区叶子覆盖全部文本类别() -> None:
    """这是"补齐可达性"的核心断言。"""
    real = _zone_real_keys()
    assert len(real) == len(set(real)), f"分区里有重复键：{real}"
    assert set(real) == set(categories.CATEGORIES), (
        f"缺失：{sorted(set(categories.CATEGORIES) - set(real))}；"
        f"多余：{sorted(set(real) - set(categories.CATEGORIES))}"
    )


def test_工作站覆盖全部伪分类() -> None:
    keys = [k for k, _l in categories.NAV_WORKBENCH]
    assert keys[0] == "all"          # 全部文本必须在最前
    assert set(keys) == set(categories.PSEUDO_CATEGORIES)
    assert len(keys) == 5            # 工作台 5 个入口


def test_分区结构完整() -> None:
    zids = [z for z, _l, _lv in categories.NAV_ZONES]
    assert zids == ["theater", "mirror", "identity", "ego", "rpg", "battle", "system"]
    for _z, label, leaves in categories.NAV_ZONES:
        assert label and leaves, f"{label} 分区为空"


def test_剧本模式计数是剧情类之和() -> None:
    """「剧本模式」不是分类键，它的计数应等于剧院分区里各剧情分类之和。"""
    counts = {k: 7 for k in categories.CATEGORIES}
    expect = sum(counts[k] for k in categories.STORY_MEMBER_KEYS)
    assert expect == 7 * len(categories.STORY_MEMBER_KEYS)
    assert "script" not in categories.STORY_MEMBER_KEYS


def test_面包屑能解析每一条导航键() -> None:
    for k, _l in categories.NAV_WORKBENCH:
        assert categories.nav_zone_of(k) == ("工作台", _l)
    for _z, zlabel, leaves in categories.NAV_ZONES:
        for k, label in leaves:
            found = categories.nav_zone_of(k)
            assert found is not None, k
            assert found[0] == zlabel and found[1] == label, (k, found, zlabel, label)
    # 不在导航里的键（图鉴页由顶栏按钮进入）返回 None
    assert categories.nav_zone_of("codex") is None


def test_导航渲染出全部可点条目(qapp) -> None:
    nav = NavPanel()
    counts = {k: i + 1 for i, k in enumerate(categories.CATEGORIES)}
    nav.set_counts(counts, {}, {"identity_skill": 21, "ego_skill": 18,
                                "identity_voice": 9, "ego_voice": 7},
                   {"personality": 148, "ego": 64})
    # 工作台 5 + 分区叶子（含虚拟入口）+ role/entities
    assert len(nav._cats) == 5 + sum(len(lv) for _z, _l, lv in categories.NAV_ZONES)
    # 默认只展开工作台（先查，因为下面的 set_current 会自动展开所在分区）
    assert nav._zone_headers["workbench"].isExpanded()
    assert not nav._zone_headers["battle"].isExpanded()
    # 每个分类键都能被 set_current 命中
    for k in categories.CATEGORIES:
        assert k in nav._cats, f"{k} 在导航里点不到"
        nav.set_current(k)
        assert nav.tree.currentItem() is not None


def test_选中条目会自动展开其分区(qapp) -> None:
    nav = NavPanel()
    nav.set_counts({}, {}, {}, {})
    assert not nav._zone_headers["battle"].isExpanded()
    nav.set_current("enemy")
    assert nav._zone_headers["battle"].isExpanded()


def test_点击发的是原来的信号与键(qapp) -> None:
    """信号契约不能变：仍然只有 category_selected(key)。"""
    from PySide6.QtCore import Qt

    nav = NavPanel()
    nav.set_counts({}, {}, {}, {})
    got = []
    nav.category_selected.connect(got.append)
    item = nav._cats["role:ego_skill"]
    item.setData(0, Qt.ItemDataRole.UserRole, "role:ego_skill")
    nav._on_click(item, 0)
    assert got == ["role:ego_skill"]


def test_旧分组结构没被动过() -> None:
    """`CATEGORY_GROUPS` 是分类规则用的，导航改版不该碰它。"""
    assert categories.group_of("identity") == "battle"
    assert categories.group_of("mirror") == "story"
    assert categories.group_of("item") == "system"
    members = [c for _g, (_l, ms) in categories.CATEGORY_GROUPS.items() for c in ms]
    assert set(members) == set(categories.CATEGORIES)
