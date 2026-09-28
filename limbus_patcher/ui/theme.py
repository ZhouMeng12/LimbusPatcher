"""主题体系 —— 设计系统在 Qt 侧的落地。

设计规范见 `docs/ui-redesign/DESIGN_SYSTEM.md`，可交互原型见同目录 `prototype.html`。

三套主题
--------
* ``mini-dark``  —— **简约·暗（默认）**：第一版的 AURUM 暗金风格，暖调深蓝灰底 + 金，
  圆角 4/6/10。旧名 ``"dark"`` 仍可用。
* ``mini-light`` —— **简约·亮**：AURUM 的亮色变体。旧名 ``"light"`` 仍可用。
* ``bus``        —— **巴士**：贴《边狱巴士》原版。纯黑底 + 品牌金 ``#F1BF02`` /
  ``#B48600``，**直角 + 细金边**（圆角一律 0）。**可选**，不是默认。

> 默认为何是 ``mini-dark``：``bus`` 是纯黑底 + 近白字，整体观感偏"黑白"，
> 用户明确要第一版那套暖调暗金。``bus`` 与 ``mini-light`` 保留为可选风格。

向后兼容
--------
旧名 ``"dark"`` / ``"light"`` 仍然可用，分别解析为 ``mini-dark`` / ``mini-light``；
旧 token 名（``PANEL`` / ``PANEL_LIGHT`` / ``ACCENT_DARK``）继续保留。因此既有
UI 代码与测试无需改动。

要点
----
1. **色彩语义单一化**：金色只用于「主行动 / 选中 / 进度」，其余一律灰阶。
2. **四层表面**造深度：bg → surface-1 → surface-2 → surface-3，不靠阴影堆。
3. **无障碍达标**：全部文字与状态色 ≥ WCAG AA 4.5。原 ERROR ``#b45f4d``
   在背景上仅 4.12、面板上 3.69（不达标），已修为 ``#c4685a``（4.89）。
4. **形状随主题走**：几何 token 分主题取值，`bus` 圆角为 0。

实现说明
--------
token 与几何量通过模块级 ``__getattr__``（PEP 562）按当前主题**动态解析**，
因此 ``theme.TEXT`` / ``theme.RADIUS_MD`` 这类访问会跟随 ``apply_theme`` 变化。
注意：各控件在**构造时**读取颜色，切换主题需重建界面（`MainWindow.set_theme`
会走重建流程）。
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# --------------------------------------------------------------------------
# Token：巴士（贴原版 —— 近黑 + 品牌金 + 直角）
# --------------------------------------------------------------------------
_BUS: dict[str, str] = {
    # 表面
    "BG": "#0b0b0d",
    "SURFACE_1": "#141416",
    "SURFACE_2": "#1c1c1f",
    "SURFACE_3": "#252529",
    # 描边（细金边：暗金做常规分隔，亮金做强调）
    "BORDER": "#3d3826",
    "BORDER_STRONG": "#b48600",
    "BORDER_ACCENT": "#b48600",
    # 文字
    "TEXT": "#eae7e0",
    "TEXT_DIM": "#a39d8f",
    "TEXT_FAINT": "#7b7566",
    # 强调（品牌金）
    "ACCENT": "#f1bf02",
    "ACCENT_HOVER": "#ffd32e",
    "ACCENT_PRESSED": "#b48600",
    "ACCENT_SUBTLE": "rgba(241, 191, 2, 0.14)",
    "ON_ACCENT": "#0b0b0d",
    # 语义
    "SUCCESS": "#63c39a",
    "WARNING": "#e8b73c",
    "ERROR": "#e0705f",
    "INFO": "#82b3e8",
    # 列表行状态
    "STATUS_NONE": "#4b4740",
    "STATUS_MOD": "#f1bf02",
    "STATUS_PENDING": "#e8b73c",
    "STATUS_MISSING": "#e0705f",
    # 交互底色
    "HOVER": "#252529",
    "SELECTION": "#2b2410",
    "OVERLAY": "rgba(0, 0, 0, 0.62)",
}

# --------------------------------------------------------------------------
# Token：简约·暗（原 AURUM 暗色，保持不动）
# --------------------------------------------------------------------------
_MINI_DARK: dict[str, str] = {
    # 表面（由深到浅四层）
    "BG": "#101215",
    "SURFACE_1": "#171a1f",
    "SURFACE_2": "#1e232a",
    "SURFACE_3": "#252b33",
    # 描边
    "BORDER": "#2a313a",
    "BORDER_STRONG": "#3a434e",
    "BORDER_ACCENT": "#2a313a",
    # 文字
    "TEXT": "#e4e0d6",
    "TEXT_DIM": "#9a958a",
    "TEXT_FAINT": "#6e6a61",
    # 强调（品牌金）
    "ACCENT": "#c8a24a",
    "ACCENT_HOVER": "#d9b463",
    "ACCENT_PRESSED": "#a8862f",
    "ACCENT_SUBTLE": "rgba(200, 162, 74, 0.14)",
    "ON_ACCENT": "#14120e",
    # 语义
    "SUCCESS": "#63ae94",
    "WARNING": "#e0ad4d",
    # 4.63 on SURFACE_2 / 5.49 on BG —— 原 #c4685a 在卡片底上仅 4.12，仍不达标
    "ERROR": "#d16f60",
    "INFO": "#7fa8d8",
    # 列表行状态
    "STATUS_NONE": "#4a4f56",
    "STATUS_MOD": "#c8a24a",
    "STATUS_PENDING": "#e0ad4d",
    "STATUS_MISSING": "#d16f60",
    # 交互底色
    "HOVER": "#252b33",
    "SELECTION": "#252a20",
    "OVERLAY": "rgba(0, 0, 0, 0.55)",
}

# --------------------------------------------------------------------------
# Token：简约·亮（变体；亮底上金色必须换深，否则对比不足）
# --------------------------------------------------------------------------
_MINI_LIGHT: dict[str, str] = {
    "BG": "#f7f6f3",
    "SURFACE_1": "#ffffff",
    "SURFACE_2": "#f1efea",
    "SURFACE_3": "#ffffff",
    "BORDER": "#dcd8d0",
    "BORDER_STRONG": "#c3bdb2",
    "BORDER_ACCENT": "#dcd8d0",
    "TEXT": "#1c1e22",
    "TEXT_DIM": "#5c5f66",
    "TEXT_FAINT": "#8a8681",
    "ACCENT": "#83681e",
    "ACCENT_HOVER": "#9a7b1d",
    "ACCENT_PRESSED": "#6a5417",
    "ACCENT_SUBTLE": "rgba(131, 104, 30, 0.12)",
    "ON_ACCENT": "#ffffff",
    "SUCCESS": "#2d785f",
    "WARNING": "#8a6100",
    "ERROR": "#b23a2e",
    "INFO": "#2f6299",
    "STATUS_NONE": "#b8b3aa",
    "STATUS_MOD": "#83681e",
    "STATUS_PENDING": "#8a6100",
    "STATUS_MISSING": "#b23a2e",
    "HOVER": "#ecebe5",
    "SELECTION": "#f3ecd9",
    "OVERLAY": "rgba(0, 0, 0, 0.35)",
}

_THEMES: dict[str, dict[str, str]] = {
    "bus": _BUS,
    "mini-dark": _MINI_DARK,
    "mini-light": _MINI_LIGHT,
}

#: 主题 id（顺序即切换器顺序）
THEME_IDS: tuple[str, ...] = ("bus", "mini-dark", "mini-light")

#: 主题显示名
THEME_LABELS: dict[str, str] = {
    "bus": "巴士",
    "mini-dark": "简约·暗",
    "mini-light": "简约·亮",
}

#: 切换器结构：`1 + (1+1)` —— 左侧「巴士」不可展开，右侧「简约」展开出暗/亮。
#: 注意顺序不代表默认值：默认是「简约 · 暗」（第一版 AURUM 暗金）。
THEME_GROUPS: tuple[dict, ...] = (
    {"id": "bus", "label": "巴士", "hint": "边狱巴士原版：纯黑底 + 品牌金 + 直角",
     "children": ()},
    {"id": "mini", "label": "简约", "hint": "第一版 AURUM 暗金（默认）",
     "children": (("mini-dark", "暗"), ("mini-light", "亮"))},
)

#: 默认主题 —— 回到第一版的**暗金 AURUM**（暖调深蓝灰 + 金），
#: 而不是巴士那套纯黑底 + 近白字（观感偏黑白）。
DEFAULT_THEME = "mini-dark"

#: 旧主题名 → 新主题 id（向后兼容）
_THEME_ALIASES: dict[str, str] = {
    "dark": "mini-dark",
    "light": "mini-light",
    "mini": "mini-dark",
    "mini_dark": "mini-dark",
    "mini_light": "mini-light",
}


def resolve_theme(mode: str | None) -> str:
    """把任意（含旧名/大小写混杂）主题名规范化为合法主题 id。"""
    key = (mode or "").strip().lower()
    key = _THEME_ALIASES.get(key, key)
    return key if key in _THEMES else DEFAULT_THEME


# --------------------------------------------------------------------------
# 几何 / 字号 / 动效 token
# --------------------------------------------------------------------------
#: 与主题无关的部分
_GEOMETRY_COMMON: dict[str, object] = {
    # 间距（4pt 基准）
    "SPACE_1": 4, "SPACE_2": 8, "SPACE_3": 12, "SPACE_4": 16,
    "SPACE_5": 20, "SPACE_6": 24, "SPACE_8": 32,
    # 字体（px）
    "FONT_DISPLAY": 22, "FONT_TITLE": 17, "FONT_SUBTITLE": 15,
    "FONT_BODY": 13, "FONT_CAPTION": 12, "FONT_SMALL": 11,
    # 动效（ms）
    "DUR_FAST": 120, "DUR_BASE": 200, "DUR_SLOW": 320,
    "FONT_FAMILY": '"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif',
    "FONT_MONO": '"Consolas", "Cascadia Mono", monospace',
    "BORDER_W": 1,
}

#: 随主题变化的部分 —— 形状语言：巴士一律直角，简约保留圆角。
#: ``RADIUS_PILL`` 三套主题都是 999（完全圆头）：原型里 ``--radius-pill:999px``
#: 对所有主题成立，所以「巴士 = 直角」只作用于**容器/按钮/行**，药丸仍是圆的。
#: ``LOGO_CUT`` 是品牌 logo 左上/右下角的斜切量（原型 ``--cut``）：
#: 巴士 10px 有切口，简约 0（正方式）。
_GEOMETRY_BY_THEME: dict[str, dict[str, object]] = {
    "bus": {
        "RADIUS_SM": 0, "RADIUS_MD": 0, "RADIUS_LG": 0,
        "RADIUS_PILL": 999, "RADIUS_ITEM": 0,
        "BORDER_W_STRONG": 1,
        "LOGO_CUT": 10,
    },
    "mini-dark": {
        "RADIUS_SM": 4, "RADIUS_MD": 6, "RADIUS_LG": 10,
        "RADIUS_PILL": 999, "RADIUS_ITEM": 4,
        "BORDER_W_STRONG": 1,
        "LOGO_CUT": 0,
    },
    "mini-light": {
        "RADIUS_SM": 4, "RADIUS_MD": 6, "RADIUS_LG": 10,
        "RADIUS_PILL": 999, "RADIUS_ITEM": 4,
        "BORDER_W_STRONG": 1,
        "LOGO_CUT": 0,
    },
}

_THEME_GEOMETRY_KEYS: frozenset[str] = frozenset(
    k for g in _GEOMETRY_BY_THEME.values() for k in g
)

_current = DEFAULT_THEME


def current_mode() -> str:
    """返回当前主题 id（``bus`` / ``mini-dark`` / ``mini-light``）。"""
    return _current


def tokens(mode: str = DEFAULT_THEME) -> dict[str, str]:
    """返回指定主题的颜色 token 表（不依赖 Qt，便于测试与工具使用）。

    兼容旧名：``tokens("dark")`` 等价于 ``tokens("mini-dark")``。
    """
    return dict(_THEMES[resolve_theme(mode)])


def geometry(mode: str = DEFAULT_THEME) -> dict[str, object]:
    """返回指定主题合并后的几何 token 表。"""
    return {**_GEOMETRY_COMMON, **_GEOMETRY_BY_THEME[resolve_theme(mode)]}


# 向后兼容别名：旧代码/测试直接读这些名字，值等同新 token
_ALIASES = {
    "PANEL": "SURFACE_1",
    "PANEL_LIGHT": "SURFACE_2",
    "ACCENT_DARK": "ACCENT_PRESSED",
}


def _tok(name: str) -> str:
    """按当前主题取颜色 token。"""
    table = _THEMES[_current]
    return table[_ALIASES.get(name, name)]


# --------------------------------------------------------------------------
# 动态 token 解析（PEP 562）
# --------------------------------------------------------------------------
def __getattr__(name: str):
    if name in _BUS:  # 颜色 token（含别名）
        return _THEMES[_current][_ALIASES.get(name, name)]
    if name in _ALIASES:
        return _THEMES[_current][_ALIASES[name]]
    if name in _GEOMETRY_COMMON or name in _THEME_GEOMETRY_KEYS:
        return geometry(_current)[name]
    if name == "CHIP_QSS":
        return _chip_qss()
    if name == "QSS":
        return _qss()
    if name == "TOKENS":  # 便于调试/测试整表导出
        return dict(_THEMES[_current])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(__all__) | set(globals()))


def _chip_qss() -> str:
    """状态药丸样式：语义色描边 + 语义色文字 + 中性底。

    契约保持不变：调用方固定 `.format(color=...)`（见 main_window._chip /
    onboarding），因此返回的模板必须**只含一个 `{color}` 占位符**，
    且 CSS 自身的花括号要写成 `{{` / `}}` 以躲过 `.format`。
    这里用哨兵替换而不是花括号转义，避免 f-string 与 .format 双重转义互相打架。
    """
    g = geometry(_current)
    inner = (
        f" background: {_tok('SURFACE_2')}; border: 1px solid __C__;"
        f" color: __C__; padding: 3px 10px; border-radius: {g['RADIUS_PILL']}px;"
        f" font-family: {g['FONT_FAMILY']};"
        f" font-size: {g['FONT_CAPTION']}px; font-weight: 600;"
    )
    return "QLabel#chip {{" + inner.replace("__C__", "{color}") + "}}"


def _qss() -> str:
    """按当前主题生成应用级样式表。"""
    t = _THEMES[_current]
    g = geometry(_current)
    bg, s1, s2, s3 = t["BG"], t["SURFACE_1"], t["SURFACE_2"], t["SURFACE_3"]
    border, bstrong = t["BORDER"], t["BORDER_STRONG"]
    rule = t.get("BORDER_ACCENT", border)
    text, tdim, tfaint = t["TEXT"], t["TEXT_DIM"], t["TEXT_FAINT"]
    accent, ahover, apress = t["ACCENT"], t["ACCENT_HOVER"], t["ACCENT_PRESSED"]
    subtle, on_acc = t["ACCENT_SUBTLE"], t["ON_ACCENT"]
    ok, warn, err = t["SUCCESS"], t["WARNING"], t["ERROR"]
    hover, sel = t["HOVER"], t["SELECTION"]
    r_sm, r_md, r_pill, r_item = (
        g["RADIUS_SM"], g["RADIUS_MD"], g["RADIUS_PILL"], g["RADIUS_ITEM"],
    )
    bw, bw_strong = g["BORDER_W"], g["BORDER_W_STRONG"]
    fam = g["FONT_FAMILY"]
    mono = g["FONT_MONO"]
    body = g["FONT_BODY"]

    return f"""
* {{
    font-family: {fam};
    font-size: {body}px;
    color: {text};
}}
QMainWindow, QDialog {{ background: {bg}; }}
QWidget {{ background: transparent; }}
/* 根容器显式铺底色：三栏卡片的 8px 缝隙要透出窗口底色（比面板更暗一层）。
   离屏 grab 不绘制顶层窗口背景，故必须落在显式子控件上。 */
QWidget#appRoot {{ background: {bg}; }}
/* 菜单栏：Windows 默认走**原生**菜单栏，原生不吃 QSS，会和下面自绘的顶栏割裂
   （离屏截图里更会直接渲染成一条纯黑）。主窗口已 setNativeMenuBar(False)，
   这里把它调成和顶栏同色，看起来就是顶栏的一部分。 */
QMenuBar {{ background: {s1}; color: {tdim}; border: none; }}
QMenuBar::item {{ background: transparent; padding: 3px 9px; margin: 0; color: {tdim}; }}
QMenuBar::item:selected {{ background: {hover}; color: {text}; }}
QMenuBar::item:pressed {{ background: {s3}; color: {text}; }}

/* ---------- 容器层次 ---------- */
QFrame#panel  {{ background: {s1}; border: {bw}px solid {border}; border-radius: {r_md}px; }}
QFrame#topbar {{ background: {s1}; border-bottom: {bw}px solid {rule}; }}
QFrame#card   {{ background: {s2}; border: {bw}px solid {border}; border-radius: {r_md}px; }}
QFrame#vsep   {{ background: {rule}; border: none; }}
QFrame#popover {{
    background: {s3}; border: {bw}px solid {rule}; border-radius: {r_md}px;
}}
/* 编辑器右侧常驻「参考」栏（原型 .drawer）+ 它的页签（原型 .tabs button） */
QFrame#drawer {{ background: {s1}; border-left: {bw}px solid {border}; }}
QPushButton#refTab {{
    background: transparent; border: none;
    border-bottom: 2px solid transparent; border-radius: 0;
    padding: 0 10px; color: {tdim}; font-weight: 500;
}}
QPushButton#refTab:hover {{ color: {text}; }}
QPushButton#refTab:checked {{
    color: {accent}; border-bottom: 2px solid {accent}; font-weight: 600;
}}

/* ---------- 文字 ---------- */
QLabel {{ background: transparent; }}
QLabel#h1       {{ font-size: {g['FONT_DISPLAY']}px; font-weight: 700; }}
QLabel#title    {{ font-size: {g['FONT_SUBTITLE']}px; font-weight: 600; }}
QLabel#subtitle {{ font-size: {g['FONT_SUBTITLE']}px; font-weight: 600; color: {tdim}; }}
QLabel#dim      {{ color: {tdim}; }}
QLabel#faint    {{ color: {tfaint}; }}
QLabel#chip     {{ padding: 3px 8px; border-radius: {r_pill}px; font-size: {g['FONT_CAPTION']}px; }}
/* 顶栏品牌区（原型 .brand / .brand-name / .savedot / .crumb） */
QLabel#brandName {{ font-size: {g['FONT_BODY']}px; font-weight: 600; }}
QLabel#saveDot   {{ background: {ok}; border-radius: 3px; }}
QLabel#crumb     {{ font-size: {g['FONT_CAPTION']}px; color: {tdim}; }}
/* 列表行的角色胶囊徽标（原型 .row .t .rl） */
QLabel#roleBadge {{
    background: {s3}; border: {bw}px solid {border}; color: {tdim};
    border-radius: {r_pill}px; padding: 0 5px; font-size: 10px; font-weight: 600;
}}

/* ---------- 按钮：每屏 primary 至多一个 ---------- */
QPushButton {{
    background: {s2};
    border: {bw}px solid {border};
    border-radius: {r_sm}px;
    padding: 5px 14px;
    font-weight: 600;
}}
/* 「有下拉」的指示统一由我们自己的文案表达（``改名称 ▼`` / 自绘三点的 MoreButton）。
   显式把原生菜单指示器钉成 0 尺寸：实测**裸 Fusion** 会给带菜单的 QPushButton 画一个
   ``PM_MenuButtonIndicator=12`` 的箭头（右侧多 12px 墨），本应用的 QSS 虽已不画它，
   但钉死可避免将来换主题 / 换样式插件时又冒出来。 */
QPushButton::menu-indicator {{
    image: none; width: 0px; height: 0px;
}}
QPushButton:hover {{ background: {hover}; border-color: {bstrong}; }}
QPushButton:pressed {{ background: {apress}; border-color: {apress}; color: {on_acc}; }}
QPushButton:focus {{ border-color: {accent}; }}
QPushButton:disabled {{ color: {tfaint}; background: {s1}; border-color: {border}; }}
QPushButton#primary {{
    background: {accent};
    border-color: {accent};
    color: {on_acc};
    font-weight: 600;
}}
QPushButton#primary:hover {{ background: {ahover}; border-color: {ahover}; }}
QPushButton#primary:pressed {{ background: {apress}; border-color: {apress}; }}
QPushButton#primary:disabled {{ background: {s1}; border-color: {border}; color: {tfaint}; }}
QPushButton#danger {{ color: {err}; border-color: {err}; background: transparent; }}
QPushButton#danger:hover {{ background: {err}; color: {on_acc}; border-color: {err}; }}
QPushButton#ghost {{ background: transparent; border-color: transparent; color: {tdim}; }}
QPushButton#ghost:hover {{ background: {hover}; color: {text}; }}
/* 顶栏最右的「更多操作」圆点按钮（原型 moreBtn） */
QPushButton#ghostIcon {{
    background: transparent; border: {bw}px solid transparent;
    border-radius: {r_md}px; padding: 0; color: {tdim};
    font-size: 15px; font-weight: 700;
}}
QPushButton#ghostIcon:hover {{ background: {s3}; color: {text}; }}
/* 顶栏的整页入口（人格图鉴 / 敌方图鉴 / 剧本模式）：轻量 tab，选中态给底色 + 金边。
   这三颗属于「导航」而不是「操作」，所以用透明底、只在 hover / 选中时出现底与边，
   不会跟右侧那颗唯一 primary 的「应用到游戏」抢注意力。 */
QPushButton#pageTab {{
    background: transparent; border: {bw}px solid transparent;
    border-radius: {r_sm}px; padding: 4px 10px; color: {tdim}; font-weight: 600;
}}
QPushButton#pageTab:hover {{ background: {hover}; color: {text}; }}
QPushButton#pageTab:checked {{
    background: {subtle}; border-color: {rule}; color: {accent};
}}
/* 顶栏药丸按钮：状态总览入口 */
QPushButton#pill {{
    background: {s2}; border: {bw}px solid {rule}; border-radius: {r_pill}px;
    padding: 4px 12px; font-weight: 600;
}}
QPushButton#pill:hover {{ background: {hover}; }}
/* 状态药丸（QFrame 版，内含彩点 + 文字 + 雪佛龙） */
QFrame#pill {{
    background: {s2}; border: {bw}px solid {rule}; border-radius: {r_pill}px;
}}
QFrame#pill:hover {{ background: {hover}; border-color: {accent}; }}
/* 顶栏「风格 · XX」按钮 + 其浮层里的分段控件（原型 themeBtn / .switch） */
QFrame#stylePop {{
    background: {s1}; border: {bw}px solid {bstrong}; border-radius: {r_md}px;
}}
QLabel#popTitle {{
    font-size: 11px; font-weight: 700; color: {tfaint};
}}
QFrame#switchTrack {{
    background: {s2}; border: {bw}px solid {border}; border-radius: {r_pill}px;
}}
QPushButton#segOpt {{
    background: transparent; border: {bw}px solid transparent;
    border-radius: {r_pill}px; padding: 0; font-weight: 600; color: {tdim};
}}
QPushButton#segOpt:hover {{ color: {text}; }}
QPushButton#segOpt:checked {{ background: {accent}; color: {on_acc}; }}
QPushButton#segOpt:checked:hover {{ background: {ahover}; color: {on_acc}; }}

/* ---------- 状态总览面板的行 ---------- */
QFrame#srow {{ background: transparent; border: none; }}

/* ---------- 输入 ---------- */
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox, QListView, QListWidget, QTreeWidget, QTreeView {{
    background: {s2};
    border: {bw}px solid {border};
    border-radius: {r_sm}px;
    padding: 4px 6px;
    selection-background-color: {accent};
    selection-color: {on_acc};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: {accent};
}}
QLineEdit:disabled, QComboBox:disabled {{ color: {tfaint}; background: {s1}; }}
QPlainTextEdit#original, QPlainTextEdit#baseline {{
    background: {s1};
    color: {tdim};
    border: {bw}px dashed {border};
    font-family: {mono};
}}
QPlainTextEdit#baseline {{ color: {tfaint}; }}

/* ---------- 列表 / 树 ---------- */
QListView::item, QListWidget::item {{ padding: 6px; border-radius: {r_item}px; border-left: 3px solid transparent; }}
QListView::item:hover, QListWidget::item:hover {{ background: {hover}; }}
QListView::item:selected, QListWidget::item:selected {{
    background: {sel}; border-left: 3px solid {accent}; color: {text};
}}
QTreeWidget, QTreeView {{ background: transparent; border: none; padding: 0; }}
QTreeWidget::item, QTreeView::item {{
    padding: 5px 4px; border-radius: {r_item}px; border-left: 3px solid transparent;
}}
QTreeWidget::item:hover, QTreeView::item:hover {{ background: {hover}; }}
QTreeWidget::item:selected, QTreeView::item:selected {{
    background: {sel}; border-left: 3px solid {accent}; color: {text};
}}
QTreeWidget::branch {{ background: transparent; }}
QTreeWidget::item:disabled {{ color: {tdim}; }}
QHeaderView::section {{
    background: {s2}; color: {tdim}; border: none; border-bottom: {bw}px solid {border};
    padding: 6px 8px; font-weight: 600;
}}

/* ---------- 下拉列表 ---------- */
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {s3}; border: {bw}px solid {border}; border-radius: {r_sm}px;
    selection-background-color: {accent}; selection-color: {on_acc}; outline: none;
}}

/* ---------- 标签页 ---------- */
QTabWidget::pane {{ border: {bw}px solid {border}; border-radius: {r_md}px; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {tdim}; padding: 7px 14px;
    border-bottom: 2px solid transparent; font-weight: 600;
}}
QTabBar::tab:hover {{ color: {text}; }}
QTabBar::tab:selected {{ color: {accent}; border-bottom: 2px solid {accent}; }}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: {r_pill}px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {apress}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: {r_pill}px; min-width: 28px; }}
QScrollBar::handle:horizontal:hover {{ background: {apress}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- 其它 ---------- */
/* 分割条 = 卡片之间的「间隙」：透明 + 宽 {g['SPACE_2']}px，
   让窗口底色（比面板暗一档）从缝里透出来，形成原型的「卡片浮在底上」效果。
   QSplitter 自己必须透明，否则缝里会画出一条实线，卡片感全毁。 */
QSplitter {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: {g['SPACE_2']}px; }}
QSplitter::handle:vertical {{ height: {g['SPACE_2']}px; }}
QSplitter::handle:hover {{ background: {apress}; }}
QToolTip {{
    background: {s3}; color: {text}; border: {bw}px solid {border};
    border-radius: {r_sm}px; padding: 5px 8px;
}}
QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border: {bw}px solid {bstrong};
    border-radius: {3 if r_sm else 0}px; background: {s2};
}}
QCheckBox::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QCheckBox:disabled {{ color: {tfaint}; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border: {bw}px solid {bstrong}; border-radius: 7px; background: {s2}; }}
QRadioButton::indicator:checked {{ border: 4px solid {accent}; background: {s2}; }}
QProgressBar {{
    background: {s2}; border: {bw}px solid {border}; border-radius: {r_sm}px;
    text-align: center; color: {tdim}; height: 16px;
}}
QProgressBar::chunk {{ background: {accent}; border-radius: {r_sm}px; }}
QStatusBar {{ background: {s1}; color: {tdim}; border-top: {bw}px solid {border}; }}
QStatusBar::item {{ border: none; }}
QMenu {{ background: {s3}; border: {bw}px solid {border}; border-radius: {r_md}px; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: {r_item}px; }}
QMenu::item:selected {{ background: {subtle}; color: {accent}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 6px; }}
QMessageBox, QInputDialog, QFileDialog {{ background: {s1}; }}
QGroupBox {{
    border: {bw}px solid {border}; border-radius: {r_md}px;
    margin-top: 10px; padding-top: 8px; font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {tdim}; }}
"""


# --------------------------------------------------------------------------
# 应用主题
# --------------------------------------------------------------------------
def apply_theme(app: QApplication, mode: str = DEFAULT_THEME) -> str:
    """套用主题，返回实际生效的主题 id。

    ``mode`` 接受 ``bus`` / ``mini-dark`` / ``mini-light``，也接受旧名
    ``dark`` / ``light``。非法值回退到 :data:`DEFAULT_THEME`。

    注意：控件在构造时读取颜色，切换主题后需重建界面方才完全生效。
    """
    global _current
    _current = resolve_theme(mode)
    t = _THEMES[_current]

    app.setStyleSheet(_qss())

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t["BG"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(t["SURFACE_2"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(t["SURFACE_1"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t["TEXT"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(t["TEXT"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(t["TEXT_FAINT"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(t["SURFACE_2"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t["TEXT"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(t["ACCENT"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(t["ON_ACCENT"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(t["SURFACE_3"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(t["TEXT"]))
    pal.setColor(QPalette.ColorRole.Link, QColor(t["ACCENT"]))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t["TEXT_FAINT"]))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(t["TEXT_FAINT"]))
    app.setPalette(pal)
    return _current


__all__ = [
    # 主题控制
    "apply_theme", "current_mode", "tokens", "geometry", "resolve_theme",
    "THEME_IDS", "THEME_LABELS", "THEME_GROUPS", "DEFAULT_THEME",
    # 颜色 token
    "BG", "SURFACE_1", "SURFACE_2", "SURFACE_3",
    "BORDER", "BORDER_STRONG", "BORDER_ACCENT",
    "TEXT", "TEXT_DIM", "TEXT_FAINT",
    "ACCENT", "ACCENT_HOVER", "ACCENT_PRESSED", "ACCENT_SUBTLE", "ON_ACCENT",
    "SUCCESS", "WARNING", "ERROR", "INFO",
    "STATUS_NONE", "STATUS_MOD", "STATUS_PENDING", "STATUS_MISSING",
    "HOVER", "SELECTION", "OVERLAY",
    # 向后兼容别名
    "PANEL", "PANEL_LIGHT", "ACCENT_DARK",
    # 几何 / 字体 / 动效
    "RADIUS_SM", "RADIUS_MD", "RADIUS_LG", "RADIUS_PILL", "RADIUS_ITEM", "BORDER_W",
    "LOGO_CUT",
    "SPACE_1", "SPACE_2", "SPACE_3", "SPACE_4", "SPACE_5", "SPACE_6", "SPACE_8",
    "FONT_DISPLAY", "FONT_TITLE", "FONT_SUBTITLE", "FONT_BODY", "FONT_CAPTION", "FONT_SMALL",
    "FONT_FAMILY", "FONT_MONO",
    "DUR_FAST", "DUR_BASE", "DUR_SLOW",
    # 样式表
    "CHIP_QSS", "QSS",
]
