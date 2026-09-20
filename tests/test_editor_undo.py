"""右侧编辑器撤销/重做的离屏断言（QUndoStack + 合并窗口 + 载入清栈）。

覆盖：载入后栈为空 / 逐步撤销 / 多次输入合并 / 重做 / 载入新条目清栈 /
「还原为原文」可撤销 / 保存后仍可撤销 / 上限 200 / 空栈安全 / 快捷键。
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from limbus_patcher.ui.editor_panel import UNDO_LIMIT, EditorPanel
from limbus_patcher.ui.theme import apply_theme

ORIGINAL = "零协原文第一行\n零协原文第二行"


class _Ref:
    """最小 ref 替身：load_hit 只用到 id / file / field_path。"""

    def __init__(self, key: str = "k1") -> None:
        self.id = key
        self.file = "Scenario.json"
        self.field_path = [{"k": "desc"}]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


@pytest.fixture
def panel(qapp):
    p = EditorPanel()
    p.resize(700, 500)
    p.show()
    p.load_hit(ref=_Ref(), original_text=ORIGINAL, custom="起点", record=None, chapter=None,
               category="identity", character=None, favorite=False, advanced=False)
    # 测试里把合并窗口放大/缩小都由用例自己决定，默认给足时间保证「连续输入」一定合并
    p.undo_merge_window_ms = 5000
    yield p
    p.close()


def load(p: EditorPanel, original: str = ORIGINAL, custom: str | None = "起点", key: str = "k1") -> None:
    p.load_hit(ref=_Ref(key), original_text=original, custom=custom, record=None, chapter=None,
               category="identity", character=None, favorite=False, advanced=False)


def type_text(p: EditorPanel, text: str) -> None:
    """模拟逐字按键输入（每次按键都会触发一次 textChanged）。

    注意：QTest.keyClicks 只能喂 ASCII（非 ASCII 会让 Qt 崩溃），
    中文文本用 type_text_by_insert。
    """
    assert text.isascii(), "QTest.keyClicks 只支持 ASCII"
    p.custom_edit.setFocus()
    QTest.keyClicks(p.custom_edit, text)


def type_text_by_insert(p: EditorPanel, text: str) -> None:
    """逐字插入（同样是每次改动触发一次 textChanged，用于中文内容）。"""
    for ch in text:
        p.custom_edit.insertPlainText(ch)


# ---------- 基本状态 ----------


def test_load_starts_with_empty_stack(panel):
    assert (panel.can_undo(), panel.can_redo()) == (False, False)
    assert panel.undo_count() == 0
    assert panel.undo_label() == "撤销" and panel.redo_label() == "重做"
    assert panel.custom_text() == "起点"


def test_empty_stack_operations_are_safe(panel):
    """空栈时 undo/redo/label 都不抛异常，也不改内容。"""
    panel.undo()
    panel.redo()
    assert panel.custom_text() == "起点"
    assert (panel.can_undo(), panel.can_redo()) == (False, False)
    assert isinstance(panel.undo_label(), str) and isinstance(panel.redo_label(), str)


# ---------- 输入 / 撤销 / 重做 ----------


def test_typing_undo_redo_roundtrip(panel):
    type_text(panel, "abc")
    assert panel.custom_text() == "起点abc"
    assert panel.can_undo() and not panel.can_redo()
    assert panel.undo_label() == "输入"

    panel.undo()
    assert panel.custom_text() == "起点"  # 回到载入时的文本
    assert not panel.can_undo() and panel.can_redo()
    assert panel.redo_label() == "输入"

    panel.redo()
    assert panel.custom_text() == "起点abc"


def test_consecutive_typing_merges_into_one_step(panel):
    type_text(panel, "abcde")
    assert panel.custom_text() == "起点abcde"
    assert panel.undo_count() == 1  # 连续输入合并成一条，而不是一个字一条
    panel.undo()
    assert panel.custom_text() == "起点"
    assert not panel.can_undo()


def test_typing_after_save_is_a_new_step(panel):
    """保存会打断合并：保存前后的输入是两条独立撤销命令。"""
    sent: list[tuple] = []
    panel.save_requested.connect(lambda ref, value: sent.append((ref, value)))
    type_text(panel, "A")
    panel.save_btn.click()
    assert sent and sent[-1][1] == "起点A"
    type_text(panel, "B")
    assert panel.custom_text() == "起点AB"
    assert panel.undo_count() == 2
    panel.undo()
    assert panel.custom_text() == "起点A"
    panel.undo()
    assert panel.custom_text() == "起点"


def test_undo_after_save_returns_to_pre_save_text(panel):
    """保存之后仍可撤销回保存前的文本（撤销不写方案文件）。"""
    sent: list[tuple] = []
    panel.save_requested.connect(lambda ref, value: sent.append((ref, value)))

    type_text(panel, "abc")
    panel.save_btn.click()
    assert sent[-1][1] == "起点abc"

    assert panel.can_undo()
    panel.undo()
    assert panel.custom_text() == "起点"  # 回到保存前的文本
    assert panel.redo_label() == "输入"
    panel.redo()
    assert panel.custom_text() == "起点abc"


def test_multiple_sessions_undo_step_by_step(panel):
    """多组、时间上分开的输入各自成一条，可逐步回退。"""
    panel.undo_merge_window_ms = -1  # 强制不合并（模拟间隔很久的两次输入）
    type_text(panel, "A")
    type_text(panel, "B")
    assert panel.custom_text() == "起点AB"
    assert panel.undo_count() == 2
    panel.undo()
    assert panel.custom_text() == "起点A"
    panel.undo()
    assert panel.custom_text() == "起点"


# ---------- 载入新条目 ----------


def test_load_new_entry_clears_history(panel):
    type_text(panel, "abc")
    assert panel.can_undo()

    load(panel, original="另一条原文", custom="另一条自定义", key="k2")
    assert panel.custom_text() == "另一条自定义"
    assert panel.undo_count() == 0
    assert (panel.can_undo(), panel.can_redo()) == (False, False)
    panel.undo()  # 载入本身不可撤销
    assert panel.custom_text() == "另一条自定义"


def test_load_entry_without_custom_uses_empty_text(panel):
    load(panel, original="没有自定义的条目", custom=None, key="k3")
    assert panel.custom_text() == ""
    assert panel.undo_count() == 0


def test_load_clears_redo_history(panel):
    type_text(panel, "abc")
    panel.undo()
    assert panel.can_redo()
    load(panel, original="新原文", custom="新文本", key="k4")
    assert not panel.can_redo()


# ---------- 还原为原文 ----------


def test_restore_via_main_window_setplaintext_is_undoable(panel):
    """主窗口（_on_restore）直接 setPlainText(原文) 也要进撤销栈。"""
    panel.custom_edit.setPlainText(ORIGINAL)
    assert panel.custom_text() == ORIGINAL
    assert panel.undo_label() == "还原为原文"
    assert panel.can_undo()

    panel.undo()
    assert panel.custom_text() == "起点"
    panel.redo()
    assert panel.custom_text() == ORIGINAL


def test_restore_to_original_api_is_undoable(panel):
    type_text(panel, "abc")
    assert panel.custom_text() == "起点abc"
    panel.restore_to_original()
    assert panel.custom_text() == ORIGINAL
    assert panel.undo_label() == "还原为原文"

    panel.undo()
    assert panel.custom_text() == "起点abc"
    assert panel.redo_label() == "还原为原文"
    panel.redo()
    assert panel.custom_text() == ORIGINAL


def test_cjk_typing_merges_too(panel):
    """中文逐字输入同样合并成一条命令。"""
    type_text_by_insert(panel, "你好世界")
    assert panel.custom_text() == "起点你好世界"
    assert panel.undo_count() == 1
    panel.undo()
    assert panel.custom_text() == "起点"


def test_setplaintext_with_same_text_does_not_push(panel):
    """重复写入相同文本不产生撤销步骤（避免空转命令）。"""
    panel.custom_edit.setPlainText("起点")
    assert panel.undo_count() == 0


def test_clear_is_undoable(panel):
    panel.custom_edit.clear()
    assert panel.custom_text() == ""
    assert panel.undo_label() == "清空文本"
    panel.undo()
    assert panel.custom_text() == "起点"


# ---------- 撤销栈上限 ----------


def test_undo_limit_is_200(panel):
    assert UNDO_LIMIT == 200
    for i in range(UNDO_LIMIT + 5):
        panel.set_custom_text(f"t{i}")  # 每次整段替换都是一条独立命令
    assert panel.custom_text() == f"t{UNDO_LIMIT + 4}"
    assert panel.undo_count() == UNDO_LIMIT

    steps = 0
    while panel.can_undo():
        panel.undo()
        steps += 1
    assert steps == UNDO_LIMIT
    # 最早的 5 条已被丢弃，回退只能到第 5 次替换之后
    assert panel.custom_text() == "t4"
    assert not panel.can_undo()
    panel.undo()  # 到底后再撤销仍安全
    assert panel.custom_text() == "t4"


# ---------- 信号 ----------


def test_undo_redo_availability_signals(panel):
    undo_seen: list[bool] = []
    redo_seen: list[bool] = []
    panel.undo_available.connect(undo_seen.append)
    panel.redo_available.connect(redo_seen.append)

    # 编辑框内容变化 → 通知有可撤销内容（供主窗口更新菜单/按钮状态）
    panel.custom_edit.setPlainText("被改的文本")
    assert undo_seen and undo_seen[-1] is True
    assert redo_seen and redo_seen[-1] is False

    panel.undo()
    assert undo_seen[-1] is False and redo_seen[-1] is True

    panel.redo()
    assert undo_seen[-1] is True and redo_seen[-1] is False

    panel.undo()
    panel.custom_edit.setPlainText("新分支")  # 撤销后新输入会清掉重做历史
    assert redo_seen[-1] is False
    assert not panel.can_redo() and panel.can_undo()


# ---------- 快捷键 ----------


def test_shortcuts_registered_and_builtin_undo_disabled(panel):
    keys = {s.key().toString() for s in panel.findChildren(QShortcut)}
    assert {"Ctrl+Z", "Ctrl+Y", "Ctrl+Shift+Z"} <= keys
    # 关掉编辑框自带的撤销栈，避免两套栈打架
    assert panel.custom_edit.isUndoRedoEnabled() is False


def test_ctrl_z_in_edit_widget(panel):
    """直接派发按键（编辑框有焦点）时 Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z 生效。"""
    panel.undo_merge_window_ms = -1  # 两段输入 → 两条命令，便于确认只撤销一步
    type_text(panel, "A")
    type_text(panel, "B")
    assert panel.custom_text() == "起点AB" and panel.undo_count() == 2

    QTest.keyClick(panel.custom_edit, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert panel.custom_text() == "起点A"
    QTest.keyClick(panel.custom_edit, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    assert panel.custom_text() == "起点AB"
    QTest.keyClick(panel.custom_edit, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert panel.custom_text() == "起点A"
    QTest.keyClick(panel.custom_edit, Qt.Key.Key_Z,
                   Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert panel.custom_text() == "起点AB"


def test_ctrl_z_through_window_shortcut(panel):
    """走窗口快捷键系统（QShortcut 路径）时一次 Ctrl+Z 只撤销一步。"""
    handle = panel.windowHandle()
    if handle is None:  # 极端环境下没有窗口句柄，跳过（真实应用不会出现）
        pytest.skip("无窗口句柄")
    panel.undo_merge_window_ms = -1
    type_text(panel, "A")
    type_text(panel, "B")
    assert panel.custom_text() == "起点AB" and panel.undo_count() == 2

    QTest.keyClick(handle, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert panel.custom_text() == "起点A"  # 快捷键与 keyPressEvent 不会重复触发
    QTest.keyClick(handle, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    assert panel.custom_text() == "起点AB"
