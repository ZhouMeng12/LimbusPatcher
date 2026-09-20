"""richtext：零协富文本标签的解析 / 去标签 / 转 Qt 富文本（纯函数，无 Qt 依赖）。"""
from __future__ import annotations

from limbus_patcher import richtext as rt

COLOR_LINE = "<color=#fe4b48>失去{1}点理智值</color>"
SIZE_LINE = "<size=75%><color=#a16a3b>持有陈旧的通行证时可选择</color></size>"
MARK_LINE = "<mark color=#ff000040><b><u>回合结束时{0}</u></b></mark>"
STYLE_LINE = '<style="highlightConverted">{1}</style>'


def test_plain_strips_color_and_keeps_placeholder():
    """plain() 去掉颜色标签，但 {1} 占位符原样保留。"""
    assert rt.plain(COLOR_LINE) == "失去{1}点理智值"
    assert rt.plain("失去{1}点理智值") == "失去{1}点理智值"


def test_plain_handles_nested_size_color():
    assert rt.plain(SIZE_LINE) == "持有陈旧的通行证时可选择"
    assert rt.plain("<size=75%><b>粗</b>体</size>") == "粗体"


def test_plain_keeps_ruby_base_drops_reading():
    """ruby 注音：保留正文，丢掉读法。"""
    text = "前<ruby=りょう>Ryō</ruby>后"
    assert rt.plain(text) == "前Ryō后"
    segs = rt.parse(text)
    assert [(s.kind, s.text, s.reading) for s in segs] == [
        ("plain", "前", ""), ("ruby", "Ryō", "りょう"), ("plain", "后", ""),
    ]


def test_plain_strips_resource_tags_but_keeps_text():
    """sprite / link / material 等资源类标签：标签丢掉，内部文字保留。"""
    text = "<sprite=Icon>甲<link=abc>乙</link><material=1>丙"
    assert rt.plain(text) == "甲乙丙"
    assert rt.has_format(text) is False           # 资源标签本就不渲染
    assert [s.kind for s in rt.parse(text)] == ["plain"]


def test_plain_keeps_literal_angle_brackets():
    """正文里的尖括号（a < b > c）不是标签，不能被吞掉。"""
    assert rt.plain("a < b > c") == "a < b > c"
    assert rt.plain("伤害 < 上限 > 时") == "伤害 < 上限 > 时"


def test_parse_nested_color_with_bold_and_underline():
    """嵌套：样式链按外 → 内保留，kind 取最内层。"""
    segs = rt.parse("<color=#fe4b48>a<b><u>粗</u></b>c</color>")
    assert [s.text for s in segs] == ["a", "粗", "c"]
    assert segs[0].kind == "color" and segs[0].attr == "#fe4b48"
    assert segs[1].kind == "underline"
    assert segs[1].styles == (("color", "#fe4b48"), ("bold", None), ("underline", None))
    style = rt.effective_style(segs[1])
    assert style.color == "#fe4b48" and style.bold and style.underline


def test_parse_mark_two_forms():
    """<mark color=#fff> 与 <mark=#fff> 两种写法都要认。"""
    for text in ("<mark color=#ff0000>高亮</mark>", "<mark=#ff0000>高亮</mark>"):
        segs = rt.parse(text)
        assert [s.kind for s in segs] == ["mark"]
        assert segs[0].text == "高亮" and segs[0].attr == "#ff0000"
        assert rt.effective_style(segs[0]).background == "#ff0000"
        assert "background-color:#ff0000" in rt.to_html(text)


def test_parse_mark_alpha_is_blended():
    """8 位色 <mark color=#ff000040>：alpha 与面板底色混合，不原样塞给 Qt。"""
    seg = rt.parse(MARK_LINE)[0]
    bg = rt.effective_style(seg).background
    assert bg and bg.startswith("#") and len(bg) == 7
    assert bg != "#ff0000"                        # 半透明 → 混合成偏暗的红
    assert "#ff000040" not in rt.to_html(MARK_LINE)
    assert "background-color:" in rt.to_html(MARK_LINE)
    assert rt.effective_style(seg).bold and rt.effective_style(seg).underline


def test_parse_size_percent():
    segs = rt.parse("<size=75%>小字</size>")
    assert [s.kind for s in segs] == ["size"]
    assert segs[0].attr == "75%"
    assert rt.effective_style(segs[0]).size_percent == 75.0
    assert rt.effective_style(rt.parse("<size=60>小字</size>")[0]).size_percent == 60.0


def test_parse_unclosed_and_misordered_never_raise():
    """不闭合 / 乱序 / 多余闭合：不抛异常，文字不丢。"""
    assert rt.plain("<color=#f00>没闭合") == "没闭合"
    assert rt.plain("</color>多余闭合") == "多余闭合"
    assert rt.plain("<b>粗</i>还是粗</b>尾") == "粗还是粗尾"
    assert rt.plain("<color=#f00>红</color></b>红") == "红红"
    assert [s.kind for s in rt.parse("<i>斜</i>")] == ["italic"]
    assert rt.parse("") == []
    assert rt.plain("") == "" and rt.to_html("") == ""
    assert rt.has_format("") is False


def test_to_html_escapes_special_characters():
    """< > & " 必须转义后再拼标签：既不破坏显示，也无从注入标签。"""
    raw = '<color=#fe4b48>a & b < c > d "e"</color>'
    html = rt.to_html(raw)
    assert "&amp;" in html and "&lt;" in html and "&gt;" in html and "&quot;" in html
    assert "< c >" not in html
    assert html.count("<") == 2                   # 只有自己拼的那对 <span>
    assert rt.plain(raw) == 'a & b < c > d "e"'


def test_to_html_contains_expected_style_tags():
    html = rt.to_html(COLOR_LINE)
    assert html == '<span style="color:#fe4b48">失去{1}点理智值</span>'
    assert 'font-size:75%' in rt.to_html(SIZE_LINE)
    assert "font-size:" in rt.to_html(SIZE_LINE)
    nested = rt.to_html("<b>粗</b><u>下</u><i>斜</i><s>删</s>")
    assert nested == "<b>粗</b><u>下</u><i>斜</i><s>删</s>"


def test_to_html_mark_style():
    html = rt.to_html("<mark color=#ff0000><b>高亮</b></mark>")
    assert 'background-color:#ff0000' in html
    assert "<b>高亮</b>" in html


def test_to_html_highlight_converted_style():
    """<style="highlightConverted"> 渲染成加粗 + 强调色（与 theme.WARNING 同色）。"""
    html = rt.to_html(STYLE_LINE)
    assert rt.HIGHLIGHT_COLOR == "#d9a441"
    assert rt.HIGHLIGHT_COLOR in html
    assert "<b>{1}</b>" in html
    assert rt.plain(STYLE_LINE) == "{1}"          # 未知名样式只丢标签、不丢文字
    assert rt.plain('<style="somethingElse">x</style>') == "x"


def test_to_html_ruby_uses_sub_annotation():
    html = rt.to_html("前<ruby=りょう>Ryō</ruby>后")
    assert html.startswith("前Ryō<sub")
    assert "りょう" in html and "font-size:70%" in html
    assert html.endswith("</sub>后")


def test_to_html_plain_and_empty_text_unchanged():
    assert rt.to_html("") == ""
    assert rt.to_html("纯文本，没有标签。") == "纯文本，没有标签。"
    assert rt.parse("纯文本") == [
        rt.Segment(kind="plain", text="纯文本", reading="", attr=None, styles=())
    ]
    assert rt.plain("") == ""


def test_has_format_true_and_false():
    for text in (COLOR_LINE, SIZE_LINE, MARK_LINE, STYLE_LINE, "<i>斜</i>",
                 "<b>粗</b>", "<u>下</u>", "<s>删</s>", "<ruby=かん>漢</ruby>",
                 "<color=#f00>没闭合"):
        assert rt.has_format(text) is True, text
    for text in ("", "纯文本", "失去{1}点理智值", "<sprite=Icon>甲", "<link=abc>乙</link>",
                 "a < b > c"):
        assert rt.has_format(text) is False, text


def test_parse_kinds_are_documented_kinds():
    """所有产出的 kind 都在公开的 KINDS 里（自绘控件按此分支取色/取字体）。"""
    corpus = [COLOR_LINE, SIZE_LINE, MARK_LINE, STYLE_LINE, "前<ruby=りょう>Ryō</ruby>后",
              "<i>斜</i>", "<color=#f00>a<b>b</b></color>", "纯文本"]
    for text in corpus:
        for seg in rt.parse(text):
            assert seg.kind in rt.KINDS, (text, seg)


def test_ruby_inside_color_keeps_style_chain():
    """注音嵌在颜色里：注音段仍带颜色，正文与读法都不丢标签外文字。"""
    seg = rt.parse("<color=#fe4b48><ruby=りょう>Ryō</ruby></color>")[0]
    assert seg.kind == "ruby" and seg.reading == "りょう" and seg.text == "Ryō"
    assert rt.effective_style(seg).color == "#fe4b48"
    assert rt.plain("<color=#fe4b48><ruby=りょう>Ryō</ruby></color>") == "Ryō"


def test_highlight_family_renders():
    """实包里最常见的 highlight / upgradeHighlight 也必须渲染成加粗+强调色（不能只认 highlightConverted）。"""
    from limbus_patcher import richtext

    for style in ("highlight", "upgradeHighlight", "highlightConverted", "djp", "djp_CP6_2", "den_x"):
        text = f'<style="{style}">关键数字</style>'
        html = richtext.to_html(text)
        assert "<b>" in html or "font-weight" in html, style  # 加粗（用 <b> 或 font-weight 都可）
        assert richtext.HIGHLIGHT_COLOR.lower() in html.lower(), style
        assert richtext.is_highlight_style(style)

    assert not richtext.is_highlight_style("somethingelse")
    assert not richtext.is_highlight_style(None)
    # 普通样式名不会被误渲染
    html = richtext.to_html('<style="plainStyle">文字</style>')
    assert richtext.HIGHLIGHT_COLOR.lower() not in html.lower()
