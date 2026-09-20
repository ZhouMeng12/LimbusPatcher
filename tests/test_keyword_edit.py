"""关键词交互：悬停看说明（desc + 灰色 flavor）、点击进关键词编辑（不是改技能文本）。

显示层替换（[Breath] → 中文名）本身在 tests/test_keywords.py 里测；这里覆盖新增部分：
- keywords.load_records / tooltip_html / edit_targets：flavor 与「可编辑定位」；
- 图鉴页：标签带锚点、命中测试、悬停 tooltip、点击关键词分流；
- KeywordEditDialog：改的写进方案、还原清掉方案、同步开关。
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QHelpEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPlainTextEdit

from limbus_patcher import keywords
from limbus_patcher.patch import EntryRef
from limbus_patcher.ui.codex_page import (
    KEYWORD_LINK_PREFIX,
    CodexEditDialog,
    CodexPage,
    KeywordEditDialog,
)

KARMA = "KarmaOfIndexAlly"
DESC = "- 回合开始时\n每带有10层本效果，对自身施加1层防御等级降低"
FLAVOR = "接受指令，并将其执行。这将化为一种业，于循环往复中不断积累。"


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def llc(tmp_path: Path) -> Path:
    """关键词夹具：同一 id 在 BattleKeywords 与 Bufs 各一条（带 flavor），SkillTag 只有名字。"""
    d = tmp_path / "LLC_zh-CN"
    d.mkdir()
    _write(d / "BattleKeywords.json", {"dataList": [
        {"id": KARMA, "name": "业", "desc": DESC, "flavor": FLAVOR},
        {"id": "Breath", "name": "呼吸法", "desc": "暴击率提升"},
    ]})
    _write(d / "Bufs.json", {"dataList": [
        {"id": KARMA, "name": "业", "desc": DESC, "flavor": FLAVOR},
    ]})
    _write(d / "SkillTag.json", {"dataList": [
        {"id": "OnSucceedAttack", "name": "[命中时]"},
    ]})
    keywords.clear_cache()
    return d


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _StubCtx:
    """图鉴页 + 关键词对话框需要的最小上下文：只记录写方案的动作，不碰真实文件。"""

    def __init__(self, llc: Path, data_dir: Path):
        self.env = SimpleNamespace(llc_pack_dir=str(llc), llc_ok=True)
        self.app_paths = SimpleNamespace(data_dir=data_dir)
        self.search = SimpleNamespace(list_entities=lambda *a, **k: [])
        self.profile = SimpleNamespace(get=lambda ref: None)
        self.upserts: list[tuple[EntryRef, str]] = []
        self.removes: list[EntryRef] = []
        self.saved = 0

    def upsert_entry(self, ref: EntryRef, value: str):
        self.upserts.append((ref, value))
        return SimpleNamespace(ok=True, message="")

    def remove_entry(self, ref: EntryRef) -> bool:
        self.removes.append(ref)
        return True

    def save_profile(self) -> None:
        self.saved += 1


@pytest.fixture
def page(qapp, llc: Path, tmp_path: Path):
    p = CodexPage(_StubCtx(llc, tmp_path))
    yield p
    p.close()


def _shown(label, width: int = 420, height: int = 60):
    """让标签有真实几何（镜像文档按宽度排版）。"""
    label.resize(width, height)
    label.show()
    QApplication.processEvents()
    return label


def _x_of_token(page, label) -> int:
    """第一个关键词在首行的横向位置（用于构造「点在关键词上」的坐标）。"""
    doc = page._mirror_doc(label)
    spans = page._keyword_ranges(label)
    assert spans, "标签里应当有关键词锚点"
    return label.fontMetrics().horizontalAdvance(doc.toPlainText()[: spans[0][0]]) + 2


def _press(x: int, y: int = 8) -> QMouseEvent:
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y), QPointF(x + 100, y + 100),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _move(x: int, y: int = 8) -> QMouseEvent:
    return QMouseEvent(QEvent.Type.MouseMove, QPointF(x, y), QPointF(x + 100, y + 100),
                       Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


# --------------------------------------------------------------------------- keywords 数据


def test_load_records_keeps_flavor_and_edit_position(llc: Path):
    records = keywords.load_records(llc)[KARMA]
    # BattleKeywords 在前，Bufs 在后；两条都带 flavor 与「文件 + 下标」定位信息
    assert [r.file for r in records] == ["BattleKeywords.json", "Bufs.json"]
    assert [r.source_kind for r in records] == ["BattleKeywords", "Bufs"]
    assert all(r.id == KARMA and r.flavor == FLAVOR and r.desc == DESC for r in records)
    assert [r.record_index for r in records] == [0, 0]
    # SkillTag 记录只有 name，不会凭空多出 desc / flavor
    assert keywords.load_records(llc)["OnSucceedAttack"][0].texts == {"name": "[命中时]"}
    # 字段 → 含该字段的记录（同步更新用）
    targets = keywords.edit_targets(records)
    assert [r.file for r in targets["desc"]] == ["BattleKeywords.json", "Bufs.json"]


def test_tooltip_html_shows_desc_and_gray_flavor(llc: Path):
    html = keywords.tooltip_html(KARMA, keywords.load_records(llc)[KARMA])
    assert "业" in html and f"[{KARMA}]" in html
    assert "每带有10层本效果" in html
    assert FLAVOR in html and keywords.FLAVOR_COLOR in html      # flavor 用灰色
    assert "<br>" in html                                        # 换行转 <br>，tooltip 里能换行
    # 只有名字（SkillTag）时没有可说的内容 → 不弹自定义 tooltip
    assert keywords.tooltip_html("OnSucceedAttack",
                                 keywords.load_records(llc)["OnSucceedAttack"]) == ""
    assert keywords.tooltip_html("NoSuch", []) == ""


def test_tooltip_html_escapes_text(llc: Path):
    records = [keywords.KeywordRecord(id="X", file="Bufs.json", record_index=0,
                                      source_kind="Bufs",
                                      texts={"name": "<b>", "desc": "a & b", "flavor": '"c"'})]
    html = keywords.tooltip_html("X", records)
    assert "<b>&" not in html and "&lt;b&gt;" in html and "&amp;" in html and "&quot;" in html


# --------------------------------------------------------------------------- 页面接线


def test_label_renders_keyword_links(page, llc: Path):
    label = _shown(QLabel())
    page._set_rich_text(label, f"施加[{KARMA}]")
    assert f'href="{KEYWORD_LINK_PREFIX}{KARMA}"' in label.text()
    assert keywords.KEYWORD_COLOR in label.text()
    assert page._token_at(label, QPoint(_x_of_token(page, label), 8)) == KARMA


def test_hover_marks_token_and_tooltip_has_desc_flavor(page, llc: Path, monkeypatch):
    label = _shown(QLabel())
    page._set_rich_text(label, f"施加[{KARMA}]")
    x = _x_of_token(page, label)
    # 悬停：立刻不弹，先记下 token 并起计时器
    page.eventFilter(label, _move(x))
    assert page._hover_token.get(label) == KARMA
    assert page._hover_timer.isActive()
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(page, "_popup_keyword_tip",
                        lambda lb, token: shown.append((lb.objectName(), token)))
    page._show_hover_tip()
    assert shown and shown[0][1] == KARMA
    # 悬停在关键词上时自己弹说明：吃掉普通 tooltip 事件
    tip = QHelpEvent(QEvent.Type.ToolTip, QPoint(x, 8), QPoint(x + 100, 108))
    monkeypatch.setattr(page, "_popup_keyword_tip", lambda lb, token: None)
    assert page.eventFilter(label, tip) is True
    # 移开 → 状态清空、计时器停止，普通 tooltip 恢复
    page.eventFilter(label, _move(5))
    assert page._hover_token.get(label) is None and not page._hover_timer.isActive()
    assert page.eventFilter(label, tip) is False


def test_popup_tooltip_uses_keyword_desc(page, llc: Path, monkeypatch):
    label = _shown(QLabel())
    page._set_rich_text(label, f"施加[{KARMA}]")
    captured: list[str] = []
    monkeypatch.setattr("limbus_patcher.ui.codex_page.QToolTip.showText",
                        lambda pos, html, *a, **k: captured.append(html))
    page._popup_keyword_tip(label, KARMA)
    assert captured and "每带有10层本效果" in captured[0] and FLAVOR in captured[0]


def test_click_keyword_opens_keyword_edit(page, llc: Path, monkeypatch):
    label = _shown(QLabel())
    page._set_rich_text(label, f"施加[{KARMA}]，随后结束")
    got: list[tuple] = []
    monkeypatch.setattr(page, "_edit_keyword", lambda token, records: got.append((token, records)))
    x = _x_of_token(page, label)
    # 点在关键词上：事件被吃掉（不会再去编辑技能文本），并打开关键词编辑
    assert page.eventFilter(label, _press(x)) is True
    QApplication.processEvents()          # _open_keyword 走 singleShot(0)，等事件循环跑完
    assert got and got[0][0] == KARMA
    assert [r.file for r in got[0][1]] == ["BattleKeywords.json", "Bufs.json"]


def test_click_plain_text_still_edits_skill_text(page, llc: Path):
    label = _shown(QLabel())
    page._set_rich_text(label, f"施加[{KARMA}]，随后结束")
    # 点正文（非关键词）：事件不被过滤 → 原来的「点击编辑技能文本」照旧生效
    assert page.eventFilter(label, _press(2)) is False
    assert page.eventFilter(label, _press(_x_of_token(page, label) + 400)) is False


def test_skill_text_editor_keeps_raw_token(qapp, llc: Path, tmp_path: Path):
    """点正文进的是技能文本编辑：编辑框里是原始 [id]，不会被显示层的中文名替换。"""
    ctx = _StubCtx(llc, tmp_path)
    ctx.original_of = lambda ref: (f"每层[{KARMA}]使护盾减少1%", None)
    ctx.baseline_of = lambda ref: ("", "（无英语基线）")
    ref = EntryRef(file="Skills_Personality-01.json", id=1031001, record_index=0,
                   field_path=[{"k": "levelList"}])
    dlg = CodexEditDialog(None, ctx, ref, "技能说明")
    assert f"[{KARMA}]" in dlg.original_view.toPlainText()
    assert dlg.custom_edit.toPlainText() == ""


# --------------------------------------------------------------------------- 关键词编辑对话框


def _dialog(page, llc: Path):
    records = keywords.load_records(llc)[KARMA]
    return KeywordEditDialog(page, page.ctx, KARMA, records)


def test_keyword_dialog_saves_name_desc_flavor(qapp, page, llc: Path):
    dlg = _dialog(page, llc)
    assert isinstance(dlg.editors["name"], QLineEdit)
    assert isinstance(dlg.editors["desc"], QPlainTextEdit)
    assert isinstance(dlg.editors["flavor"], QPlainTextEdit)
    assert dlg.editors["desc"].toPlainText() == DESC        # 初值 = 原文
    assert dlg.sync_cb.isChecked() and "Bufs.json" in dlg.sync_cb.text()   # 默认同步到 Bufs

    dlg.editors["desc"].setPlainText("改过的说明")
    dlg._save()
    assert dlg.saved
    desc_upserts = [(r.file, r.field_path, v) for r, v in page.ctx.upserts
                    if r.field_path == [{"k": "desc"}]]
    assert desc_upserts == [("BattleKeywords.json", [{"k": "desc"}], "改过的说明"),
                            ("Bufs.json", [{"k": "desc"}], "改过的说明")]
    # 没改的字段不写方案
    assert not [r for r, _v in page.ctx.upserts if r.field_path == [{"k": "name"}]]
    assert page.ctx.upserts[0][0].id == KARMA and page.ctx.upserts[0][0].record_index == 0


def test_keyword_dialog_sync_off_only_touches_primary(qapp, page, llc: Path):
    dlg = _dialog(page, llc)
    dlg.sync_cb.setChecked(False)
    dlg.editors["flavor"].setPlainText("新的风味文本")
    dlg._save()
    assert [(r.file, v) for r, v in page.ctx.upserts] == [("BattleKeywords.json", "新的风味文本")]


def test_keyword_dialog_restore_clears_profile(qapp, page, llc: Path):
    dlg = _dialog(page, llc)
    dlg._restore()
    assert dlg.saved
    assert {(r.file, r.field_path[0]["k"]) for r in page.ctx.removes} == {
        ("BattleKeywords.json", "name"), ("BattleKeywords.json", "desc"),
        ("BattleKeywords.json", "flavor"), ("Bufs.json", "name"),
        ("Bufs.json", "desc"), ("Bufs.json", "flavor"),
    }


def test_keyword_dialog_uses_saved_value_as_initial(qapp, llc: Path, tmp_path: Path):
    """方案里已经改过的关键词：打开对话框时显示改过的值，而不是原文。

    方案条目是按 (文件, 记录, 字段) 定位的，所以这里给「主记录」（BattleKeywords）造一条。
    """
    ref = EntryRef(file="BattleKeywords.json", id=KARMA, record_index=0,
                   field_path=[{"k": "name"}])
    ctx = _StubCtx(llc, tmp_path)
    ctx.profile = SimpleNamespace(
        get=lambda r: SimpleNamespace(value="改过的名字") if r == ref else None)
    dlg = KeywordEditDialog(None, ctx, KARMA, keywords.load_records(llc)[KARMA])
    assert dlg.editors["name"].text() == "改过的名字"
    dlg.editors["name"].setText("改过的名字")     # 与方案一致 → 只写有改动的那条
    dlg.sync_cb.setChecked(False)
    dlg._save()
    assert [(r.file, v) for r, v in ctx.upserts] == [("BattleKeywords.json", "改过的名字")]
