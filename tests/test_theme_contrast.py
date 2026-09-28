"""设计系统的可访问性守卫：把「文字与状态色必须达 WCAG AA」变成自动测试。

背景：改版前 `ERROR #b45f4d` 在背景上仅 4.12、面板上 3.69，均未达 4.5，
而它恰好用于「环境异常 / 未选目录 / 缺失」这类最要紧的状态 —— 属于实打实的
可用性缺陷。三主题改版时又发现两个同类问题：`mini-dark` 的 ERROR `#c4685a`
在卡片底（SURFACE_2）上仅 4.12，`mini-light` 的 ACCENT/SUCCESS 在卡片底上也
只有 4.26 / 4.32。本测试确保这类问题不会再悄悄回来。

规范见 `docs/ui-redesign/DESIGN_SYSTEM.md` §2.3。
"""
from __future__ import annotations

import pytest

from limbus_patcher.ui import theme

#: 三套主题
MODES = list(theme.THEME_IDS)

# 必须达 AA 正文（4.5）的组合：颜色 token → 所在底
# 注意 SURFACE_2 也要查 —— 卡片/输入框的底色就是它，状态色经常压在上面。
REQUIRED_PAIRS = [
    ("TEXT", "BG"),
    ("TEXT", "SURFACE_1"),
    ("TEXT", "SURFACE_2"),
    ("TEXT_DIM", "BG"),
    ("TEXT_DIM", "SURFACE_1"),
    ("TEXT_DIM", "SURFACE_2"),
    ("ACCENT", "BG"),
    ("ACCENT", "SURFACE_1"),
    ("ACCENT", "SURFACE_2"),
    ("SUCCESS", "BG"),
    ("SUCCESS", "SURFACE_2"),
    ("WARNING", "BG"),
    ("WARNING", "SURFACE_2"),
    ("ERROR", "BG"),
    ("ERROR", "SURFACE_1"),
    ("ERROR", "SURFACE_2"),
    ("INFO", "BG"),
    ("INFO", "SURFACE_2"),
    ("STATUS_PENDING", "SURFACE_2"),
]

# 作为「文字压在自身色块上」的组合（如主按钮）
ON_PAIRS = [("ON_ACCENT", "ACCENT")]


def _srgb_to_lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _srgb_to_lin(r) + 0.7152 * _srgb_to_lin(g) + 0.0722 * _srgb_to_lin(b)


def contrast(a: str, b: str) -> float:
    """WCAG 2.x 对比度。"""
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("mode", MODES)
def test_文字与状态色达_WCAG_AA(mode: str) -> None:
    tk = theme.tokens(mode)
    bad = []
    for fg, bg in REQUIRED_PAIRS:
        ratio = contrast(tk[fg], tk[bg])
        if ratio < 4.5:
            bad.append(f"{mode}: {fg} on {bg} = {ratio:.2f} < 4.5")
    assert not bad, "以下组合未达 AA 正文标准：\n" + "\n".join(bad)


@pytest.mark.parametrize("mode", MODES)
def test_强调底色上的文字达_AA(mode: str) -> None:
    tk = theme.tokens(mode)
    for fg, bg in ON_PAIRS:
        ratio = contrast(tk[fg], tk[bg])
        assert ratio >= 4.5, f"{mode}: {fg} on {bg} = {ratio:.2f} < 4.5"


@pytest.mark.parametrize("mode", MODES)
def test_极弱文字至少达大字号标准(mode: str) -> None:
    """TEXT_FAINT 只允许用在 ≥18px 或图标上，门槛放宽到 3.0。"""
    tk = theme.tokens(mode)
    ratio = contrast(tk["TEXT_FAINT"], tk["BG"])
    assert ratio >= 3.0, f"{mode}: TEXT_FAINT on BG = {ratio:.2f} < 3.0"


def test_错误色已修复不再是不达标值() -> None:
    """回归守卫：旧值 #b45f4d 在背景上仅 4.12，必须已替换。"""
    assert theme.tokens("dark")["ERROR"].lower() != "#b45f4d"
    # 三主题里都不允许再出现这个值
    for mode in MODES:
        assert theme.tokens(mode)["ERROR"].lower() != "#b45f4d"


def test_主题切换会改变_token() -> None:
    assert theme.tokens("dark")["ACCENT"] != theme.tokens("light")["ACCENT"]
    # 亮色下金色必须换深，否则白底上对比不足
    assert contrast(theme.tokens("light")["ACCENT"], theme.tokens("light")["BG"]) >= 4.5


# --------------------------------------------------------------------------
# 三主题体系
# --------------------------------------------------------------------------
def test_三主题都在册且默认是第一版暗金() -> None:
    assert set(theme.THEME_IDS) == {"bus", "mini-dark", "mini-light"}
    # 默认必须是第一版的 AURUM 暗金，不是巴士那套纯黑底
    assert theme.DEFAULT_THEME == "mini-dark"
    assert theme.resolve_theme(None) == "mini-dark"
    # 空值/非法值也回落默认
    assert theme.resolve_theme("") == "mini-dark"


def test_巴士默认是纯黑白观感_所以不做默认() -> None:
    """回归守卫：巴士主题是纯黑底 + 近白字，用户明确不要它当默认。"""
    tk = theme.tokens("bus")
    assert tk["BG"].lower() == "#0b0b0d"
    assert theme.tokens("mini-dark")["BG"].lower() == "#101215"
    assert theme.DEFAULT_THEME != "bus"


def test_旧主题名向后兼容() -> None:
    assert theme.resolve_theme("dark") == "mini-dark"
    assert theme.resolve_theme("light") == "mini-light"
    assert theme.resolve_theme("DARK") == "mini-dark"
    assert theme.resolve_theme("nope") == theme.DEFAULT_THEME
    # tokens() 也要认旧名
    assert theme.tokens("dark") == theme.tokens("mini-dark")
    assert theme.tokens("light") == theme.tokens("mini-light")


def test_巴士主题用的是原版品牌金() -> None:
    """巴士主题必须贴原版：#F1BF02（Corn）/ #B48600（Pirate Gold）。"""
    tk = theme.tokens("bus")
    assert tk["ACCENT"].lower() == "#f1bf02"
    assert tk["ACCENT_PRESSED"].lower() == "#b48600"
    assert tk["ON_ACCENT"].lower() == "#0b0b0d"


def test_巴士主题是直角而简约保留圆角() -> None:
    """形状语言随主题走：巴士的**容器/按钮/行**一律直角，简约保留圆角。

    但 ``RADIUS_PILL`` 三主题统一 999（完全圆头）—— 原型里 ``--radius-pill:999px``
    对**所有**主题成立，所以「巴士 = 直角」不作用于药丸/胶囊/徽标。
    """
    assert theme.geometry("bus")["RADIUS_MD"] == 0
    assert theme.geometry("bus")["RADIUS_SM"] == 0
    assert theme.geometry("bus")["RADIUS_ITEM"] == 0
    assert theme.geometry("mini-dark")["RADIUS_MD"] == 6
    assert theme.geometry("mini-light")["RADIUS_MD"] == 6
    # 药丸三主题一致：全圆头
    for mode in MODES:
        assert theme.geometry(mode)["RADIUS_PILL"] == 999, mode
    # logo 斜切角（原型 --cut）：巴士有切口，简约没有
    assert theme.geometry("bus")["LOGO_CUT"] == 10
    assert theme.geometry("mini-dark")["LOGO_CUT"] == 0


def test_三主题表面各不相同() -> None:
    """三个主题必须是三套真正的配色，不能有两个是同一张表。"""
    tables = [tuple(sorted(theme.tokens(m).items())) for m in MODES]
    assert len(set(tables)) == 3


def test_chip_qss_契约只有一个占位符(monkeypatch) -> None:
    """调用方固定用 .format(color=...)，模板必须只留一个 {color} 且无残留花括号。"""
    for mode in MODES:
        monkeypatch.setattr(theme, "_current", mode)
        rendered = theme.CHIP_QSS.format(color="#63ae94")
        assert "#63ae94" in rendered, mode
        assert "{color}" not in rendered, mode
        assert "{{" not in rendered and "}}" not in rendered, mode
        assert "QLabel#chip" in rendered, mode


def test_向后兼容别名仍然指向正确语义() -> None:
    assert theme._ALIASES["PANEL"] == "SURFACE_1"
    assert theme._ALIASES["PANEL_LIGHT"] == "SURFACE_2"
    assert theme._ALIASES["ACCENT_DARK"] == "ACCENT_PRESSED"
    # 别名按**当前**主题解析（其它测试可能已经切换过全局主题，这里不能写死某主题）
    tk = theme.tokens(theme.current_mode())
    assert theme.PANEL == tk["SURFACE_1"]
    assert theme.PANEL_LIGHT == tk["SURFACE_2"]
    assert theme.ACCENT_DARK == tk["ACCENT_PRESSED"]


def test_品牌强调色未被改动() -> None:
    """暗色 ACCENT 是品牌色，必须保持 #c8a24a（UI/测试多处直接引用）。"""
    assert theme.tokens("dark")["ACCENT"].lower() == "#c8a24a"


def test_主题分组是_1_加_1加1() -> None:
    """切换器结构：左侧「巴士」不可展开，右侧「简约」展开出暗/亮。"""
    assert len(theme.THEME_GROUPS) == 2
    bus, mini = theme.THEME_GROUPS
    assert bus["id"] == "bus" and bus["children"] == ()
    assert mini["label"] == "简约"
    assert [c[0] for c in mini["children"]] == ["mini-dark", "mini-light"]
    # 分组里出现的所有主题都必须真实存在
    ids = [g["id"] for g in theme.THEME_GROUPS] + [c[0] for g in theme.THEME_GROUPS for c in g["children"]]
    assert set(ids) - {"mini"} == set(theme.THEME_IDS)
