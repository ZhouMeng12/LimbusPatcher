"""界面里当图标用的符号，必须字形可得 —— 否则会被画成空心方框（豆腐块）。

背景（改版（二）（三）实测）：``▾``(U+25BE) / ``▴``(U+25B4) / ``▸``(U+25B8)
在 ``Microsoft YaHei UI`` / ``Microsoft YaHei`` / ``Segoe UI`` / ``SimHei``
以及 Qt 在无头环境下的兜底字体里**都没有字形**，渲染出来是一个空心方框；
``↶``(U+21B6) / ``↷``(U+21B7) / ``⋯``(U+22EF) / ``⟵``(U+27F5) 同样缺字形。
而 ``▼``(U+25BC) / ``▲``(U+25B2) / ``←``(U+2190) / ``•``(U+2022) 上述字体全都有。

本文件把这条约束固定下来：符号不只要"看着对"，还得**真的画得出来**。
全量扫描（会真的把每个符号渲染成图再数像素）见 ``scripts/scan_glyphs.py``。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from limbus_patcher.ui import theme

UI_DIR = Path(theme.__file__).resolve().parent

#: 已在真实字体上验证**缺字形**的符号 → 一律不许出现在界面源码里。
#: 这份名单由 ``scripts/scan_glyphs.py`` 全量扫描 ui/*.py 得出：
#: 扫描会把每个「当符号用」的字符真的渲染一遍，像素数与豆腐块一致即为缺字形。
FORBIDDEN: dict[str, str] = {
    "\u25be": "▾ 小实心下三角（请用 ▼ U+25BC）",
    "\u25b4": "▴ 小实心上三角（请用 ▲ U+25B2）",
    "\u25b8": "▸ 小实心右三角（请用 ▼ U+25BC，这是菜单按钮）",
    "\u2715": "✕ 乘法叉",
    "\u2713": "✓ 对勾",
    "\u2714": "✔ 粗对勾",
    "\u26a0": "⚠ 警告（请用 ※ U+203B）",
    "\u23fa": "⏺ 录制圆点",
    "\u21b5": "↵ 回车箭头",
    "\u232b": "⌫ 退格",
    "\u21b6": "↶ 逆时针弯箭头（撤销）—— 请直接用文字「撤销」",
    "\u21b7": "↷ 顺时针弯箭头（重做）—— 请直接用文字「重做」",
    "\u22ef": "⋯ 居中省略号 —— 缺字形，三点请自绘（MoreButton）",
    "\u27f5": "⟵ 长左箭头（请用 ← U+2190）",
    "\u21ba": "↺ 逆时针开圆箭头",
    "\u21bb": "↻ 顺时针开圆箭头",
}

#: 折叠指示符允许用的实心三角。
SAFE_CHEVRONS = ("\u25bc", "\u25b2")  # ▼ ▲


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("path", sorted(UI_DIR.glob("*.py")), ids=lambda p: p.name)
def test_界面源码不含缺字形的符号(path: Path) -> None:
    """界面源码里不许出现已知缺字形的符号（含注释与 docstring）。"""
    src = path.read_text(encoding="utf-8")
    # 报错用码位而不是原字符：控制台编码不可控时原字符会变成乱码，码位永远可读。
    bad = {f"U+{ord(ch):04X}": why for ch, why in FORBIDDEN.items() if ch in src}
    assert not bad, f"{path.name} 用了缺字形的符号：{bad}"


def test_折叠指示符用的是实心三角(qapp) -> None:
    """真实控件上的折叠指示符必须是 ▼ / ▲，不是 ▾ / ▴。

    改版（三）后主题切换器变成单颗「风格 · XX」按钮（原型 ``#themeBtn``），
    不再带三角；但状态药丸、``操作`` / ``改名称`` 之类的下拉按钮仍要守这条规则。
    """
    from limbus_patcher.ui.status_pill import StatusPill
    from limbus_patcher.ui.theme_switch import ThemeSwitcher

    theme.apply_theme(qapp, theme.DEFAULT_THEME)

    pill = StatusPill()
    assert pill._chev.text() in SAFE_CHEVRONS, f"状态药丸的折叠指示符是 {pill._chev.text()!r}"

    # 切换器本体：文案是「风格 · XX」，不带折叠三角
    sw = ThemeSwitcher(theme.DEFAULT_THEME)
    assert sw.text().startswith("风格 · "), sw.text()
    assert not any(g in sw.text() for g in ("\u25be", "\u25b4")), sw.text()
