"""ManualMatchDialog 候选列表：相似度排序、百分比显示与过滤行为（离屏断言）。

不需要 exec()：对话框可直接构造，列表项在构造后即可检查。
"""
from __future__ import annotations

import difflib
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from limbus_patcher.storybook import norm_text
from limbus_patcher.ui.mapping_dialog import ManualMatchDialog

FILE = "StoryData/S001B.json"
ROW_RE = re.compile(r"^\[(\d+)\] (\d+)% (.*)$")

# wiki 句带说话人前缀；候选沿用真实数据形态：teller 与 content 分开。
WIKI = "狼：总算明白了吗？"
CANDS = [
    {"record": 7, "teller": "狼", "content": "总算明白了吗？", "used": True},
    {"record": 12, "teller": "狼", "content": "总算明白了吧？", "used": False},
    {"record": 3, "teller": "但丁", "content": "今天天气不错啊。", "used": False},
    {"record": 20, "teller": "希斯克利夫", "content": "滚开！", "used": False},
    {"record": 9, "teller": "", "content": "   ", "used": False},
]

WIKI_SEARCH = "但丁：总算明白了吗？"
CANDS_SEARCH = [
    {"record": 4, "teller": "狼", "content": "总算明白了吧？", "used": False},
    {"record": 8, "teller": "狼", "content": "明白了。", "used": False},
    {"record": 11, "teller": "狼", "content": "滚开！", "used": False},
    {"record": 5, "teller": "但丁", "content": "总算明白了吗？", "used": False},
    {"record": 2, "teller": "狼", "content": "总算明白了吗？还有别的吗？", "used": True},
]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _dialog(wiki_text: str, candidates: list[dict]) -> ManualMatchDialog:
    return ManualMatchDialog(None, wiki_text, FILE, [dict(c) for c in candidates])


def _rows(dlg: ManualMatchDialog) -> list[tuple[int, int, str]]:
    """按列表当前顺序返回 [(record, 百分比, 行文本)]。"""
    out = []
    for i in range(dlg.listw.count()):
        it = dlg.listw.item(i)
        m = ROW_RE.match(it.text())
        assert m, f"行文本不符合「[记录] 百分比% 内容」格式：{it.text()!r}"
        out.append((int(it.data(Qt.ItemDataRole.UserRole)), int(m.group(2)), it.text()))
    return out


def _records(dlg: ManualMatchDialog) -> list[int]:
    return [r for r, _p, _t in _rows(dlg)]


def _pcts(dlg: ManualMatchDialog) -> list[int]:
    return [p for _r, p, _t in _rows(dlg)]


def _expected_pct(wiki_text: str, content: str) -> int:
    """测试侧独立算出的期望百分比（归一化后 SequenceMatcher.ratio）。"""
    a, b = norm_text(wiki_text), norm_text(content)
    if not a or not b:
        return 0
    return round(difflib.SequenceMatcher(None, a, b).ratio() * 100)


def test_unused_first_then_similarity_desc(qapp):
    dlg = _dialog(WIKI, CANDS)
    try:
        rows = _rows(dlg)
        recs = [r for r, _p, _t in rows]
        by_record = {c["record"]: c for c in CANDS}

        # 未被占用优先、同组按相似度降序：12（最相似）> 3/20/9（0%）> 已占用的 7。
        assert recs == [12, 3, 20, 9, 7], recs
        # 最相似且未被占用的候选在最前，且百分比来自归一化相似度。
        assert not by_record[recs[0]]["used"]
        expected_top = _expected_pct(WIKI, by_record[12]["content"])
        assert rows[0][1] == expected_top
        assert rows[0][1] == max(p for r, p, _t in rows if not by_record[r]["used"])
        # 行文本形如「[12] 77% 狼：总算明白了吧？」。
        assert rows[0][2] == f"[12] {expected_top}% 狼：总算明白了吧？"
        # 已占用的仍可见，只是排在最后（相似度 92% 也不能置顶）。
        used_rows = [row for row in rows if by_record[row[0]]["used"]]
        assert len(used_rows) == 1
        assert recs.index(7) == len(recs) - 1
        assert used_rows[0][1] == _expected_pct(WIKI, by_record[7]["content"]) == 92
        assert "｜已被占用" in used_rows[0][2]
        assert "｜已被占用" not in rows[0][2]
        # 未占用组的百分比单调不增；无内容的候选显示 0%。
        unused_pcts = [p for r, p, _t in rows if not by_record[r]["used"]]
        assert unused_pcts == sorted(unused_pcts, reverse=True)
        assert dict((r, p) for r, p, _t in rows)[9] == 0
        assert all(0 <= p <= 100 for p in _pcts(dlg))
        # 构造不执行 exec()，也没有默认结果。
        assert dlg.result_value is None and not dlg.isVisible()
    finally:
        dlg.deleteLater()


def test_search_filter_keeps_ordering(qapp):
    dlg = _dialog(WIKI_SEARCH, CANDS_SEARCH)
    try:
        # 未过滤：未占用按相似度降序（5 > 4 > 8 > 11），已占用的 2 排最后。
        assert _records(dlg) == [5, 4, 8, 11, 2]
        assert _pcts(dlg) == sorted(_pcts(dlg)[:4], reverse=True) + [_pcts(dlg)[4]]

        dlg.search.setText("明白")
        rows = _rows(dlg)
        assert [r for r, _p, _t in rows] == [5, 4, 8, 2]  # 只剩内容含「明白」的记录
        assert all("明白" in t for _r, _p, t in rows)
        # 过滤后排序规则不变：未占用按相似度降序，已占用的仍排最后。
        unused = [p for r, p, _t in rows if r != 2]
        assert unused == sorted(unused, reverse=True)
        assert rows[-1][0] == 2
        assert rows[-1][1] == _expected_pct(WIKI_SEARCH, CANDS_SEARCH[4]["content"])
        assert "｜已被占用" in rows[-1][2]
        assert rows[-1][1] > rows[2][1]  # 已占用相似度更高也不置顶

        # 记录号过滤沿用原行为。
        dlg.search.setText("11")
        assert _records(dlg) == [11]

        dlg.search.setText("")
        assert _records(dlg) == [5, 4, 8, 11, 2]
    finally:
        dlg.deleteLater()


def test_result_value_semantics(qapp):
    """result_value 取值与按钮语义保持不变（"record"/"skip"/"clear"）。"""
    dlg = _dialog(WIKI, CANDS)
    try:
        dlg.skip_btn.click()
        assert dlg.result_value == ("skip", None)
    finally:
        dlg.deleteLater()

    dlg = _dialog(WIKI, CANDS)
    try:
        dlg.clear_btn.click()
        assert dlg.result_value == ("clear", None)
    finally:
        dlg.deleteLater()

    dlg = _dialog(WIKI, CANDS)
    try:
        dlg.listw.setCurrentRow(0)
        dlg.listw.itemDoubleClicked.emit(dlg.listw.item(0))
        assert dlg.result_value == ("record", 12)
    finally:
        dlg.deleteLater()
