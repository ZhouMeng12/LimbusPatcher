"""关键词 token（[Breath] → 中文名）测试：数据表、显示层替换、与富文本组合、图鉴接入。"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from limbus_patcher import keywords, richtext
from limbus_patcher.ui.codex_page import CodexPage

TOKEN_TEXT = "命中时施加[Breath]，重复[Breath]，未知[NoSuchToken]，中文[肉]{0}"


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def llc(tmp_path: Path) -> Path:
    """最小关键词夹具：BattleKeywords / Bufs / SkillTag 三份表，含冲突与无名记录。"""
    d = tmp_path / "LLC_zh-CN"
    d.mkdir()
    _write(d / "BattleKeywords.json", {"dataList": [
        {"id": "Breath", "name": "呼吸法", "desc": "暴击率提升"},
        {"id": "KarmaOfIndexAlly", "name": "业", "desc": "回合开始时施加"},
        {"id": "Both", "name": "图鉴名", "desc": "图鉴说明"},
        {"id": "NameWins", "name": "图鉴里的名字"},
    ]})
    _write(d / "Bufs.json", {"dataList": [
        {"id": "Breath", "name": "呼吸", "desc": "Bufs 里的呼吸"},
        {"id": "Both", "name": "状态名", "desc": "状态说明"},
        {"id": "NameWins", "desc": "Bufs 只有说明"},
        {"id": "BufsOnly", "name": "只在 Bufs", "desc": "说明"},
    ]})
    _write(d / "SkillTag.json", {"dataList": [
        {"id": "OnSucceedAttack", "name": "[命中时]"},
        {"id": "WhenUse", "name": "[使用时]"},
    ]})
    return d


@pytest.fixture
def mapping(llc: Path) -> dict:
    keywords.clear_cache()
    return keywords.load_map(llc)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


# --------------------------------------------------------------------------- load_map


def test_load_map_collects_three_sources(mapping: dict):
    assert mapping["Breath"]["name"] == "呼吸法"
    assert mapping["Breath"]["desc"] == "暴击率提升"
    assert mapping["Breath"]["source"] == "BattleKeywords.json"
    assert mapping["BufsOnly"]["name"] == "只在 Bufs"
    assert mapping["BufsOnly"]["source"] == "Bufs.json"
    # SkillTag 的 name 自带方括号，原样保留（替换后是「[命中时]」，不会变成双层括号）
    assert mapping["OnSucceedAttack"] == {"name": "[命中时]", "desc": "",
                                          "source": "SkillTag.json", "alternatives": []}
    assert mapping["KarmaOfIndexAlly"]["name"] == "业"


def test_conflict_prefers_battlekeywords_and_keeps_alternatives(mapping: dict):
    # BattleKeywords 的 name 才是玩家看到的名字；Bufs 的候选记进 alternatives
    assert mapping["Both"]["name"] == "图鉴名" and mapping["Both"]["source"] == "BattleKeywords.json"
    assert [a["name"] for a in mapping["Both"]["alternatives"]] == ["状态名"]
    assert [a["source"] for a in mapping["Both"]["alternatives"]] == ["Bufs.json"]
    assert mapping["Breath"]["alternatives"][0]["name"] == "呼吸"
    assert mapping["BufsOnly"]["alternatives"] == []


def test_bufs_record_without_name_does_not_overwrite(mapping: dict):
    # 没有 name 的 Bufs 记录只补 desc，不改名字与来源
    assert mapping["NameWins"]["name"] == "图鉴里的名字"
    assert mapping["NameWins"]["source"] == "BattleKeywords.json"
    assert mapping["NameWins"]["desc"] == "Bufs 只有说明"


def test_load_map_degrades_silently(tmp_path: Path):
    keywords.clear_cache()
    assert keywords.load_map(tmp_path / "根本没有这个目录") == {}
    assert keywords.load_map(None) == {}
    # 结构不符 / 坏 JSON / 目录当文件：一律空表，不抛异常
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "BattleKeywords.json").write_text("{ 不是 JSON", encoding="utf-8")
    (broken / "Bufs.json").write_text("[1, 2, 3]", encoding="utf-8")
    (broken / "SkillTag.json").write_text('{"dataList": "不是表"}', encoding="utf-8")
    assert keywords.load_map(broken) == {}
    # 坏文件不影响好文件
    _write(broken / "Bufs-good.json", {"dataList": [{"id": "Ok", "name": "好"}]})
    keywords.clear_cache()
    assert keywords.load_map(broken) == {"Ok": {"name": "好", "desc": "",
                                                "source": "Bufs-good.json", "alternatives": []}}
    # 传进来的是文件而不是目录
    not_a_dir = tmp_path / "不是目录.json"
    not_a_dir.write_text("{}", encoding="utf-8")
    keywords.clear_cache()
    assert keywords.load_map(not_a_dir) == {}


def test_load_map_caches_until_clear(llc: Path):
    keywords.clear_cache()
    first = keywords.load_map(llc)
    assert keywords.load_map(llc) is first            # 同一目录命中缓存
    assert keywords.load_map(str(llc)) is first       # 字符串路径同样命中
    (llc / "Bufs.json").write_text(json.dumps({"dataList": [
        {"id": "BufsOnly", "name": "改过的名字"}]}, ensure_ascii=False), encoding="utf-8")
    assert keywords.load_map(llc)["BufsOnly"]["name"] == "只在 Bufs"   # 缓存没失效
    keywords.clear_cache()
    assert keywords.load_map(llc)["BufsOnly"]["name"] == "改过的名字"  # 清缓存后重读


# --------------------------------------------------------------------------- substitute


def test_substitute_modes(mapping: dict):
    text = "<color=#fff>施加[Breath]</color>"
    assert keywords.substitute(text, mapping) == "<color=#fff>施加呼吸法</color>"
    assert keywords.substitute(text, mapping, "both") == "<color=#fff>施加呼吸法[Breath]</color>"
    assert keywords.substitute(text, mapping, "raw") == text
    assert keywords.substitute("", mapping) == ""
    assert keywords.substitute(text, {}) == text      # 空表 = 原样


def test_substitute_keeps_unknown_tokens(mapping: dict):
    text = "命中[NoSuchToken]与[BufsOnly]"
    assert keywords.substitute(text, mapping) == "命中[NoSuchToken]与只在 Bufs"


def test_substitute_is_exact_and_case_sensitive(mapping: dict):
    assert keywords.substitute("[breath][BREATH][Breath]", mapping) == "[breath][BREATH]呼吸法"
    # id 不做前缀 / 模糊匹配
    assert keywords.substitute("[Brea][BreathX]", mapping) == "[Brea][BreathX]"


def test_substitute_skips_tags_and_placeholders(mapping: dict):
    text = "<size=75%><sprite name=[Breath]>获得{0}层[Breath]</sprite></size>"
    out = keywords.substitute(text, mapping)
    # <> 标签内容与 {0} 占位符都不动；正文里的 [Breath] 才替换
    assert out == "<size=75%><sprite name=[Breath]>获得{0}层呼吸法</sprite></size>"
    assert keywords.substitute("中文[肉]与[2]都不动", mapping) == "中文[肉]与[2]都不动"


def test_tokens_in_lists_known_tokens_only(mapping: dict):
    found = keywords.tokens_in(TOKEN_TEXT, mapping)
    assert [it["id"] for it in found] == ["Breath"]
    assert found[0]["name"] == "呼吸法" and found[0]["count"] == 2
    assert found[0]["source"] == "BattleKeywords.json"
    assert keywords.tokens_in("没有 token 的文本", mapping) == []
    assert keywords.tokens_in(TOKEN_TEXT, {}) == []
    assert [it["id"] for it in keywords.tokens_in("[WhenUse][OnSucceedAttack]", mapping)] == \
        ["WhenUse", "OnSucceedAttack"]


# --------------------------------------------------------------------------- render_html


def test_render_html_colors_keyword_names(mapping: dict):
    html = keywords.render_html("失去{1}点理智值，施加[Breath]", mapping)
    assert html == (f'失去{{1}}点理智值，施加<span style="color:{keywords.KEYWORD_COLOR}">'
                    f'呼吸法</span>')
    # 与游戏自带格式标签组合：原有颜色保留，关键词另上色
    html2 = keywords.render_html("<color=#fe4b48>失去理智</color>并[Breath]", mapping)
    assert html2 == (f'<span style="color:#fe4b48">失去理智</span>并'
                     f'<span style="color:{keywords.KEYWORD_COLOR}">呼吸法</span>')


def test_render_html_without_tokens_equals_richtext(mapping: dict):
    text = "<color=#ffffff><b>纯格式</b></color>{0}"
    assert keywords.render_html(text, mapping) == richtext.to_html(text)
    assert keywords.render_html(text, mapping, "raw") == richtext.to_html(text)
    assert keywords.render_html("[Breath]", {}, "name") == richtext.to_html("[Breath]")
    assert keywords.render_html("", mapping) == ""


def test_render_html_escapes_names(mapping: dict):
    evil = {"X": {"name": '<b>&"', "desc": "", "source": "Bufs.json", "alternatives": []}}
    html = keywords.render_html("[X]", evil)
    assert "<b>&" not in html and "&lt;b&gt;&amp;&quot;" in html


def test_render_html_both_mode_keeps_token(mapping: dict):
    html = keywords.render_html("[Breath]", mapping, "both")
    assert html == (f'<span style="color:{keywords.KEYWORD_COLOR}">呼吸法</span>[Breath]')


def test_render_html_degrades_on_nul_collision(mapping: dict):
    # 原文里已经含 \x00（会与内部占位符撞车）时退化：照样替换，只是不染色
    html = keywords.render_html("原文\x000\x00带[Breath]", mapping)
    assert "呼吸法" in html and keywords.KEYWORD_COLOR not in html


def test_substitute_tolerates_record_without_name(mapping: dict):
    # 表里有 id 但没有中文名（如只补了 desc 的记录）→ 原样保留
    assert keywords.substitute("[X]", {"X": {"desc": "只有说明"}}) == "[X]"


# --------------------------------------------------------------------------- 图鉴页接入


class _StubCtx:
    """只提供图鉴页渲染所需的零协包路径（不建索引、不碰真实游戏目录）。"""

    def __init__(self, llc: Path, data_dir: Path):
        self.env = SimpleNamespace(llc_pack_dir=str(llc), llc_ok=True)
        self.app_paths = SimpleNamespace(data_dir=data_dir)
        self.search = SimpleNamespace(list_entities=lambda *a, **k: [])


def test_codex_page_renders_keyword_names(qapp, llc: Path, tmp_path: Path):
    page = CodexPage(_StubCtx(llc, tmp_path))
    label = QLabel()
    page._set_rich_text(label, "获得{0}层[Breath]与[NoSuchToken]")
    assert label.textFormat() == Qt.TextFormat.RichText
    assert keywords.KEYWORD_COLOR in label.text() and "呼吸法" in label.text()
    assert "{0}" in label.text() and "[NoSuchToken]" in label.text()   # 未知 token 原样
    assert "[Breath] = 呼吸法" in label.toolTip()                      # tooltip 附 id 明细
    page.close()


def test_codex_page_keyword_toggle_switches_to_raw(qapp, llc: Path, tmp_path: Path):
    page = CodexPage(_StubCtx(llc, tmp_path))
    assert page.keyword_btn.isChecked() and page.show_keywords     # 默认勾选
    label = QLabel()
    page.keyword_btn.setChecked(False)
    page._set_rich_text(label, "获得[Breath]")
    assert label.textFormat() == Qt.TextFormat.PlainText
    assert label.text() == "获得[Breath]" and keywords.KEYWORD_COLOR not in label.text()
    page.keyword_btn.setChecked(True)
    page._set_rich_text(label, "获得[Breath]")
    assert "呼吸法" in label.text()
    page.close()


def test_codex_page_tooltip_limits_token_lines(qapp, llc: Path, tmp_path: Path):
    page = CodexPage(_StubCtx(llc, tmp_path))
    ids = [f"Tok{i}" for i in range(9)]
    index = {"Tok%d" % i: {"name": f"名{i}", "desc": "", "source": "Bufs.json",
                           "alternatives": []} for i in range(9)}
    page._kw_map = index
    label = QLabel()
    page._set_rich_text(label, "、".join(f"[{i}]" for i in ids))
    tip = label.toolTip()
    assert tip.count(" = ") == 8 and "Tok8" not in tip          # 最多 8 条
    assert "另有 1 个关键词未列出" in tip
    page.close()
