"""零协汉化文本里的游戏富文本标签：解析 / 去标签 / 转 Qt 富文本。

游戏原文（Unity TextMeshPro 风格）里混着大量行内标签，例如：

    <color=#fe4b48>失去{1}点理智值</color>
    <size=75%><color=#a16a3b>持有陈旧的通行证时可选择</color></size>
    <mark color=#ff000040><b><u>回合结束时…</u></b></mark>
    <style="highlightConverted">{1}</style>
    <ruby=りょう>Ryō</ruby>
    <i>我们不是大海。</i>

本模块把「显示」和「原始文本」彻底分开，编辑框里永远保存原始文本：

- parse()      → 结构化片段（Segment），保留完整样式链，供自绘控件逐段取色 / 取字号；
- plain()      → 去标签纯文本（保留 ruby 正文与 {0} 占位符），用于 tooltip / 搜索 / 复制；
- to_html()    → Qt 富文本片段（QLabel / QTextEdit 支持的子集），直接塞给 setText()；
- has_format() → 这段文本是否有需要渲染的格式标签。

取舍说明
--------
- ruby 注音：'<ruby=读法>正文</ruby>' 渲染成 '正文<sub style="font-size:70%">读法</sub>'。
  Qt 的富文本子集没有 ruby 元素，用下标近似：读法落在正文右下角、字号 70%，
  观感与游戏里「注音在正上方」不同，但不额外占用行高、也不会撑破布局
  （自绘控件 RubyTextWidget 里仍按上方注音绘制）。
- 资源类标签（sprite / link / material / key / input …）：不渲染，只保留其内部文字；
  关闭「显示格式」时它们同样被去掉，不会残留裸标签。
- <style="highlightConverted">：渲染成「加粗 + 强调色」。强调色硬编码为
  HIGHLIGHT_COLOR（#d9a441，与 ui/theme.py 的 WARNING 一致）；本模块是纯函数、
  不依赖 Qt，故不 import theme，改动主题色时需要同步这里的常量。
- 8 位十六进制颜色：Qt 富文本子集对 #rrggbbaa 支持不稳，文本色直接丢 alpha；
  mark 的背景色把 alpha 与面板底色混合成不透明色近似半透明（见 _norm_background）。
- 字号：<size=75%> 先按原样写成 font-size:75%（游戏语义），再补一条 px 兜底声明——
  Qt 富文本子集实测只认 pt / px，百分比会被整条忽略（见 BASE_FONT_PX）。
- 容错：标签不闭合、乱序、多余闭合都不抛异常；认不出的标签按资源类忽略。

本模块是纯函数、无 Qt 依赖，可直接被测试与命令行脚本使用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "HIGHLIGHT_COLOR",
    "HIGHLIGHT_STYLES",
    "is_highlight_style",
    "KIND_PLAIN",
    "KINDS",
    "Segment",
    "StyleSpec",
    "effective_style",
    "has_format",
    "parse",
    "plain",
    "to_html",
]

#: 段落类型：无格式 / ruby 注音 / 颜色 / 字号 / 高亮底 / 粗体 / 下划线 / 斜体 / 删除线 / 特殊样式名
KIND_PLAIN = "plain"
KINDS = (
    "plain", "ruby", "color", "size", "mark",
    "bold", "underline", "italic", "strike", "style",
)

#: <style="…"> 里需要特殊渲染的样式名 → 加粗 + 强调色。
#: 实测真实包：highlight 3657 次、upgradeHighlight 395、djp* 145、den* 10、yellow 4、
#: number_highlight 1、highlightConverted 仅 3 —— 只认最后一个等于没渲染，故按家族收录。
HIGHLIGHT_STYLES = frozenset({
    "highlightconverted", "highlight", "upgradehighlight", "number_highlight",
    "yellow", "djp", "djp_cp6_2",
})


def is_highlight_style(attr: str | None) -> bool:
    """样式名是否属于高亮家族（含 djp* / den* / *highlight* 等变体）。"""
    if not attr:
        return False
    low = attr.strip().lower()
    return low in HIGHLIGHT_STYLES or "highlight" in low or low.startswith(("djp", "den"))
#: 强调色：与 ui/theme.py 的 WARNING 一致（本模块不依赖 Qt，故此处硬编码）
HIGHLIGHT_COLOR = "#d9a441"
#: 混合 <mark color=#rrggbbaa> 的 alpha 时所用的面板底色（与 ui/theme.py 的 PANEL 一致）
_PANEL_BG = (0x1B, 0x1F, 0x24)
#: 字号百分比换算基准（px，与 ui/theme.py 的 QSS 基准字号一致）。
#: Qt 富文本子集实测只认 pt / px，<span style="font-size:75%"> 会被整条忽略，
#: 所以 to_html() 里在百分比之后补一条 px 兜底声明，保证字号真的能看到变化。
BASE_FONT_PX = 13

# 标签名 → 段落类型（其余标签一律当资源类忽略，但内部文字保留）
_KIND_OF_TAG = {
    "color": "color",
    "size": "size",
    "mark": "mark",
    "b": "bold",
    "strong": "bold",
    "u": "underline",
    "i": "italic",
    "em": "italic",
    "s": "strike",
    "strike": "strike",
    "style": "style",
}

_HEX_RE = re.compile(r"#?([0-9a-fA-F]{3,8})\b")
_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)")
_NAME_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)")
_KV_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*[=:]\s*(.+)$", re.S)


# --------------------------------------------------------------------------- 数据结构


@dataclass(frozen=True)
class Segment:
    """一段可渲染的文本。

    - kind：最内层生效的标签类型（没有标签就是 plain；ruby 段固定为 ruby）；
    - text：要显示的正文（ruby 段为正文本体，标签已剥离）；
    - reading：ruby 注音读法，其它类型为 "";
    - attr：颜色 #rrggbb / 字号 "75%" / 样式名，其余为 None；
    - styles：完整样式链（外 → 内），每项 (kind, attr)，渲染时按顺序套标签。

    例：<color=#fe4b48><b>x</b></color> 里的 x →
    Segment(kind="bold", text="x", styles=(("color", "#fe4b48"), ("bold", None)))。
    """

    kind: str
    text: str
    reading: str = ""
    attr: str | None = None
    styles: tuple[tuple[str, str | None], ...] = field(default=())


@dataclass(frozen=True)
class StyleSpec:
    """一条片段折算后的具体样式（自绘控件与 HTML 渲染共用同一套换算）。"""

    color: str | None = None          # 文字色 #rrggbb（已丢 alpha）
    size: str | None = None           # 字号百分比字符串，如 "75%"
    background: str | None = None     # 背景色 #rrggbb（alpha 已与面板底色混合）
    bold: bool = False
    underline: bool = False
    italic: bool = False
    strike: bool = False

    @property
    def size_percent(self) -> float | None:
        """字号百分比数值（自绘换算字号用）；无字号标签时为 None。"""
        if not self.size:
            return None
        m = _NUM_RE.search(self.size)
        if not m:
            return None
        value = float(m.group(1))
        return value if value > 0 else None


# --------------------------------------------------------------------------- 标签解析


def _iter_tokens(text: str):
    """把文本切成 ("text", 原文) / ("tag", 标签体) 两种记号。

    没有配对的 "<" 一律当普通文字（不吞掉后续内容）。
    """
    pos = 0
    size = len(text)
    while pos < size:
        lt = text.find("<", pos)
        if lt < 0:
            yield ("text", text[pos:])
            return
        if lt > pos:
            yield ("text", text[pos:lt])
        gt = text.find(">", lt + 1)
        if gt < 0:  # 没有闭合尖括号：剩下的一律当文字
            yield ("text", text[lt:])
            return
        yield ("tag", text[lt + 1 : gt])
        pos = gt + 1


def _parse_tag(raw: str) -> tuple[bool, str, str | None]:
    """标签体 → (是否闭合标签, 小写标签名, 值)。

    支持 <b> / </b> / <color=#fff> / <mark color=#fff> / <style="x">。
    认不出来时标签名为空串（调用方会把它当普通文字处理）。
    """
    body = raw.strip()
    closing = body.startswith("/")
    if closing:
        body = body[1:].strip()
    if body.endswith("/"):  # 自闭合写法 <br/>
        body = body[:-1].strip()
    m = _NAME_RE.match(body)
    if not m:
        return (closing, "", None)
    name = m.group(1).lower()
    rest = body[m.end():].strip()
    if not rest:
        return (closing, name, None)
    if rest[0] in "=:":
        value = rest[1:]
    else:
        kv = _KV_RE.match(rest)
        value = kv.group(1) if kv else rest
    value = value.strip().strip('"').strip("'").strip()
    return (closing, name, value or None)


def _is_literal_tag(raw: str) -> bool:
    """尖括号内容是不是「伪标签」（如中文里的 a < b > c）——是的话整段当普通文字保留。

    只对「尖括号里首尾带空白 + 纯标签名（没有 = 属性）」的写法生效：
    <sprite name=Icon> 这种带属性的资源标签仍是标签（忽略），
    a < b > c / a < c > d 这类正文里的尖括号则不会被吞掉。
    """
    if raw.strip().startswith("/"):
        return False
    body = raw.strip()
    if body == raw:  # 尖括号里没有多余空白 → 按标签处理
        return False
    # 只有「纯标签名」才可能是伪标签；带 = 的写法（<color=#fff>）一律按标签处理
    return bool(_NAME_RE.fullmatch(body))


def _hex_rgba(raw: str | None) -> tuple[int, int, int, int] | None:
    """#rgb / #rrggbb / #rrggbbaa（可省 #）→ (r, g, b, a)；认不出返回 None。"""
    if not raw:
        return None
    m = _HEX_RE.search(raw)
    if not m:
        return None
    digits = m.group(1)
    if len(digits) == 3:
        r, g, b = (int(c * 2, 16) for c in digits)
        return (r, g, b, 255)
    if len(digits) == 6:
        return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16), 255)
    if len(digits) == 8:
        return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16),
                int(digits[6:8], 16))
    return None


def _norm_color(raw: str | None) -> str | None:
    """文字色：统一成 #rrggbb；8 位色丢 alpha（Qt 富文本子集对 #rrggbbaa 支持不稳）。"""
    rgba = _hex_rgba(raw)
    if rgba is None:
        return None
    return "#%02x%02x%02x" % rgba[:3]


def _norm_background(raw: str | None) -> str | None:
    """mark 背景色：8 位色把 alpha 与面板底色混合，近似出半透明效果。"""
    rgba = _hex_rgba(raw)
    if rgba is None:
        return None
    r, g, b, a = rgba
    if a >= 255:
        return "#%02x%02x%02x" % (r, g, b)
    k = a / 255.0
    mixed = tuple(round(c * k + bg * (1.0 - k)) for c, bg in zip((r, g, b), _PANEL_BG))
    return "#%02x%02x%02x" % mixed


def _norm_size(raw: str | None) -> str | None:
    """字号：统一成百分比字符串（游戏里 <size=75%> 与 <size=75> 都按百分比处理）。"""
    if not raw:
        return None
    m = _NUM_RE.search(raw)
    if not m:
        return None
    value = float(m.group(1))
    if value <= 0:
        return None
    if value.is_integer():
        return f"{int(value)}%"
    return f"{value:g}%"


def _size_px(size: str | None) -> int | None:
    """百分比字号 → 基准字号下的像素值（Qt 富文本子集忽略百分比，需要 px 兜底）。"""
    m = _NUM_RE.search(size or "")
    if not m:
        return None
    value = float(m.group(1))
    if value <= 0:
        return None
    return max(6, int(round(BASE_FONT_PX * value / 100.0)))


def _attr_for(kind: str, value: str | None) -> str | None:
    if kind == "color":
        return _norm_color(value)
    if kind == "mark":
        return _norm_background(value)
    if kind == "size":
        return _norm_size(value)
    if kind == "style":
        return (value or "").strip().lower() or None
    return None


def _make_segment(text: str, stack: list[tuple[str, str | None]],
                  kind: str | None = None, reading: str = "",
                  attr: str | None = None) -> Segment:
    """用当前样式栈把一段文字落成 Segment。"""
    if kind is None:
        kind = stack[-1][0] if stack else KIND_PLAIN
        attr = stack[-1][1] if stack else None
    return Segment(kind=kind, text=text, reading=reading, attr=attr, styles=tuple(stack))


# --------------------------------------------------------------------------- 公开 API


def parse(text: str) -> list[Segment]:
    """把零协原文拆成可渲染片段（保留嵌套样式，容忍不闭合 / 乱序 / 未知标签）。

    - 支持嵌套：<color=#f00>a<b>b</b>c</color> → 三段，样式链分别带 color / color+bold；
    - 不闭合：<color=#f00>文字 照样生效，直到结尾；
    - 乱序 / 多余闭合：</color> 找不到对应开标签时忽略，不抛异常；
    - 未知标签（sprite / link / material …）：标签本身丢掉，内部文字照常保留；
    - 认不出的「伪标签」（如中文里的 a < b > c）：整段当普通文字保留。
    """
    if not text:
        return []
    tokens = list(_iter_tokens(text))
    out: list[Segment] = []
    stack: list[tuple[str, str | None]] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        chunk = "".join(buf)
        buf.clear()
        if chunk:
            out.append(_make_segment(chunk, stack))

    i = 0
    total = len(tokens)
    while i < total:
        tkind, payload = tokens[i]
        if tkind == "text":
            buf.append(payload)
            i += 1
            continue

        closing, name, value = _parse_tag(payload)
        if not name or _is_literal_tag(payload):  # 认不出的尖括号内容：当文字保留
            buf.append(f"<{payload}>")
            i += 1
            continue

        if name == "ruby" and not closing:
            # ruby 单独处理：一直读到配对的 </ruby>，内部标签当作普通文字剥掉
            depth = 1
            j = i + 1
            inner: list[str] = []
            while j < total:
                k2, p2 = tokens[j]
                if k2 == "text":
                    inner.append(p2)
                    j += 1
                    continue
                c2, n2, _v2 = _parse_tag(p2)
                if n2 == "ruby":
                    depth += -1 if c2 else 1
                    if depth == 0:
                        break
                inner.append(f"<{p2}>")
                j += 1
            flush()
            base = plain("".join(inner))
            if base or value:
                out.append(_make_segment(base, stack, kind="ruby", reading=value or ""))
            i = j + 1 if j < total else j
            continue

        skind = _KIND_OF_TAG.get(name)
        if skind is None:  # 资源类 / 未知标签：忽略标签本身，内部文字保留
            i += 1
            continue

        if closing:
            flush()  # 先落段，避免本段文字丢掉刚闭合的样式
            for k in range(len(stack) - 1, -1, -1):
                if stack[k][0] == skind:
                    del stack[k:]  # 连同更内层没闭合的标签一起丢掉（浏览器式容错）
                    break
            # 找不到对应开标签 → 忽略这次闭合
        else:
            flush()
            stack.append((skind, _attr_for(skind, value)))
        i += 1

    flush()
    return out


def plain(text: str) -> str:
    """去掉所有标签的纯文本：保留 ruby 正文与 {0} 占位符，丢弃注音读法。

    用于 tooltip / 搜索 / 复制；编辑框里保存的仍然是原始文本（本函数不改输入）。
    """
    if not text:
        return ""
    return "".join(seg.text for seg in parse(text))


def effective_style(seg: Segment) -> StyleSpec:
    """把片段的样式链折算成一组具体样式（内层覆盖外层，粗体等取并集）。"""
    color = size = background = None
    bold = underline = italic = strike = False
    for kind, attr in seg.styles:
        if kind == "color" and attr:
            color = attr
        elif kind == "size" and attr:
            size = attr
        elif kind == "mark" and attr:
            background = attr
        elif kind == "bold":
            bold = True
        elif kind == "underline":
            underline = True
        elif kind == "italic":
            italic = True
        elif kind == "strike":
            strike = True
        elif kind == "style" and is_highlight_style(attr):
            # <style="highlightConverted">：加粗 + 强调色
            bold = True
            color = HIGHLIGHT_COLOR
    return StyleSpec(color=color, size=size, background=background, bold=bold,
                     underline=underline, italic=italic, strike=strike)


def _escape(text: str) -> str:
    """HTML 转义（& < > " '）——先转义再拼标签，杜绝标签注入。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _wrap_html(seg: Segment, inner: str) -> str:
    """按样式链套 Qt 富文本标签。

    styles 是「外 → 内」的游戏标签顺序，这里倒着遍历，让最外层标签最后套上去，
    使生成的 HTML 嵌套与原文一致（内层同名样式仍然覆盖外层）。
    """
    for kind, attr in reversed(seg.styles):
        if kind == "color" and attr:
            inner = f'<span style="color:{attr}">{inner}</span>'
        elif kind == "size" and attr:
            # 先写百分比（游戏里的语义），再补 px 兜底：Qt 富文本子集忽略百分比字号
            px = _size_px(attr)
            fallback = f"; font-size:{px}px" if px else ""
            inner = f'<span style="font-size:{attr}{fallback}">{inner}</span>'
        elif kind == "mark" and attr:
            inner = f'<span style="background-color:{attr}">{inner}</span>'
        elif kind == "bold":
            inner = f"<b>{inner}</b>"
        elif kind == "underline":
            inner = f"<u>{inner}</u>"
        elif kind == "italic":
            inner = f"<i>{inner}</i>"
        elif kind == "strike":
            inner = f"<s>{inner}</s>"
        elif kind == "style" and is_highlight_style(attr):
            inner = f'<span style="color:{HIGHLIGHT_COLOR}"><b>{inner}</b></span>'
        # 其余 style 名（游戏自定义样式）暂不渲染，只保留文字
    return inner


def to_html(text: str) -> str:
    """生成 Qt 富文本片段（QLabel / QTextEdit 支持的子集）。

    - 颜色 → <span style="color:#rrggbb">；字号 → font-size:<n>%（末尾补 px 兜底，Qt 忽略百分比）；
    - mark → background-color（8 位色的 alpha 已与面板底色混合成不透明近似色）；
    - b / u / i / s → <b> / <u> / <i> / <s>；
    - <style="highlightConverted"> → 加粗 + 强调色 HIGHLIGHT_COLOR；
    - ruby → 正文<sub style="font-size:70%">读法</sub>（Qt 没有 ruby 元素，用下标近似：
      读法在正文右下角且不占额外行高；自绘控件里仍是上方注音）；
    - 文本一律先做 HTML 转义再拼标签，标签注入无从下手；
    - 纯文本输入原样返回（除转义外不做任何改动）；空串返回空串。
    """
    if not text:
        return ""
    parts: list[str] = []
    for seg in parse(text):
        inner = _escape(seg.text)
        if seg.kind == "ruby" and seg.reading:
            inner = f'{inner}<sub style="font-size:70%">{_escape(seg.reading)}</sub>'
        parts.append(_wrap_html(seg, inner))
    return "".join(parts)


def has_format(text: str) -> bool:
    """是否存在需要渲染的格式标签（ruby / color / size / mark / b / u / i / s / style）。

    只含资源类标签（sprite / link / material …）或纯文本时返回 False —— 它们本就不渲染，
    调用方可以安全地走纯文本快路径。
    """
    if not text:
        return False
    return any(seg.kind != KIND_PLAIN for seg in parse(text))
