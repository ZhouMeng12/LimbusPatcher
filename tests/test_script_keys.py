"""剧本模式键盘流（↑↓/Enter/S/Ctrl+↓）与批量顺序分配逻辑。

QT_QPA_PLATFORM=offscreen 下运行；不 exec 任何对话框（只构造 + 直接调用方法）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from limbus_patcher.story_edit import StoryEdit
from limbus_patcher.ui import theme
from limbus_patcher.ui.batch_dialog import DEFAULT_BATCH_COUNT, BatchMatchDialog, plan_batch
from limbus_patcher.ui.script_panel import ScriptLineRow, ScriptPanel
from limbus_patcher.ui.theme import apply_theme

PAGE = "0-01战前"
FILE = "StoryData/S001B.json"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


def sample_items() -> list[dict]:
    """1 场景行 + 6 对话行：已对齐 / 未对齐×2 / 已对齐 / 已跳过 / 未对齐。"""
    return [
        {"type": "scene", "text": "黑森林", "file": FILE, "page": PAGE, "record": None},
        {"type": "line", "speaker": "狼", "title": "旁白", "text": "总算明白了吗？", "file": FILE, "page": PAGE, "record": 0},
        {"type": "line", "speaker": None, "text": "接着，锁链刺穿了我。", "file": FILE, "page": PAGE,
         "record": None, "wiki_only": True, "key": "k1"},
        {"type": "line", "speaker": None, "text": "第二条未对齐。", "file": FILE, "page": PAGE,
         "record": None, "wiki_only": True, "key": "k2"},
        {"type": "line", "speaker": "狼", "text": "第二条已对齐。", "file": FILE, "page": PAGE, "record": 3},
        {"type": "line", "speaker": None, "text": "已标记跳过。", "file": FILE, "page": PAGE,
         "record": None, "wiki_only": True, "key": "k3", "skip": True},
        {"type": "line", "speaker": None, "text": "第三条未对齐。", "file": FILE, "page": PAGE,
         "record": None, "wiki_only": True, "key": "k4"},
    ]


@pytest.fixture
def panel(qapp):
    p = ScriptPanel()
    p.resize(900, 600)
    p.show()
    p.show_items(sample_items())
    yield p
    p.close()


def clicks(panel: ScriptPanel) -> list[dict]:
    got: list[dict] = []
    panel.line_clicked.connect(got.append)
    return got


def skips(panel: ScriptPanel) -> list[dict]:
    got: list[dict] = []
    panel.skip_requested.connect(got.append)
    return got


# ---------- A. 键盘流 ----------


def test_focus_starts_on_first_line_row(panel):
    rows = panel.line_rows()
    assert len(rows) == 6  # 场景行不进焦点序列
    assert panel.focus_index() == 0
    assert panel.focusPolicy() != Qt.FocusPolicy.NoFocus
    assert rows[0].focused and not rows[1].focused
    assert rows[0].property("focused") is True
    # 焦点行有明显高亮（左侧强调色竖条 + 整行底色），其余行不带内联样式
    assert theme.ACCENT in rows[0].styleSheet() and "border-left" in rows[0].styleSheet()
    assert rows[1].styleSheet() == ""
    assert panel.current_item() is rows[0].item


def test_arrow_keys_move_focus(panel):
    QTest.keyClick(panel, Qt.Key.Key_Down)
    assert panel.focus_index() == 1
    assert panel.line_rows()[1].focused and not panel.line_rows()[0].focused
    QTest.keyClick(panel, Qt.Key.Key_Down)
    assert panel.focus_index() == 2
    QTest.keyClick(panel, Qt.Key.Key_Up)
    assert panel.focus_index() == 1
    # 两端夹取（不环绕）
    QTest.keyClick(panel, Qt.Key.Key_Up)
    QTest.keyClick(panel, Qt.Key.Key_Up)
    assert panel.focus_index() == 0
    for _ in range(20):
        QTest.keyClick(panel, Qt.Key.Key_Down)
    assert panel.focus_index() == len(panel.line_rows()) - 1


def test_enter_emits_line_clicked_for_current_row(panel):
    got = clicks(panel)
    QTest.keyClick(panel, Qt.Key.Key_Down)  # → 未对齐行 k1
    QTest.keyClick(panel, Qt.Key.Key_Return)
    assert [i.get("key") for i in got] == ["k1"]
    # 已对齐行同样触发（由 main_window 决定进编辑器）
    QTest.keyClick(panel, Qt.Key.Key_Up)
    QTest.keyClick(panel, Qt.Key.Key_Return)
    assert got[-1].get("record") == 0 and not got[-1].get("wiki_only")


def test_s_emits_skip_only_for_unaligned_row(panel):
    got = skips(panel)
    QTest.keyClick(panel, Qt.Key.Key_S)  # 焦点在已对齐行 → 无信号
    assert got == []
    QTest.keyClick(panel, Qt.Key.Key_Down)
    QTest.keyClick(panel, Qt.Key.Key_S)
    assert [i.get("key") for i in got] == ["k1"]
    # 已跳过行不算未对齐行
    panel.set_focus_index(4)
    QTest.keyClick(panel, Qt.Key.Key_S)
    assert len(got) == 1


def test_ctrl_arrows_jump_between_unaligned_rows(panel):
    QTest.keyClick(panel, Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier)
    assert panel.focus_index() == 1  # k1
    QTest.keyClick(panel, Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier)
    assert panel.focus_index() == 2  # k2
    QTest.keyClick(panel, Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier)
    assert panel.focus_index() == 5  # 跳过已对齐(3)与已跳过(4) → k4
    QTest.keyClick(panel, Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier)
    assert panel.focus_index() == 5  # 到底后保持原位
    QTest.keyClick(panel, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier)
    assert panel.focus_index() == 2
    QTest.keyClick(panel, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(panel, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier)
    assert panel.focus_index() == 1


def test_set_focus_index_and_hover_state(panel):
    idx = panel.set_focus_index(99)
    assert idx == len(panel.line_rows()) - 1
    assert panel.line_rows()[-1].focused
    assert sum(1 for r in panel.line_rows() if r.focused) == 1


def test_mouse_click_sets_focus_and_emits(panel):
    got = clicks(panel)
    row = panel.line_rows()[2]
    QTest.mouseClick(row, Qt.MouseButton.LeftButton)
    assert [i.get("key") for i in got] == ["k2"]  # 点哪行就聚焦哪行
    assert panel.focus_index() == 2 and row.focused
    # 右键不触发「打开/建立对应」（改由右键菜单处理）
    QTest.mousePress(row, Qt.MouseButton.RightButton)
    assert len(got) == 1


# ---------- B. 右键菜单与批量对话框 ----------


def test_row_menu_actions(panel):
    rows = panel.line_rows()

    def kinds(row):
        return [(a.text(), a.data()) for a in panel.row_menu(row).actions() if a.text()]

    # 已对齐：只能进编辑器
    assert rows[0].is_aligned and not rows[0].is_unaligned
    assert kinds(rows[0]) == [("在编辑器中打开", "open")]
    # 未对齐：批量对应 + 删除该行 + 删除本关全部未对应行（分隔符不计）
    assert rows[1].is_unaligned
    assert kinds(rows[1]) == [
        ("从该行起批量对应…", "batch"),
        ("自动建议对应（本关 3 行未对应）…", "suggest"),
        ("删除该行（从剧本中移除）", "delete"),
        ("删除本关全部未对应行（3 行）", "delete_all"),
    ]
    # 已跳过：可取消跳过 / 删除
    assert not rows[4].is_unaligned and not rows[4].is_aligned and rows[4].skipped
    assert kinds(rows[4]) == [("取消跳过（恢复为未对齐）", "unskip"), ("删除该行（从剧本中移除）", "delete")]
    # 既非未对齐也非已对齐的行（如占位行）没有菜单
    assert panel.row_menu(ScriptLineRow(None, None, "占位", False, item={"type": "line"})) is None


def test_row_menu_delete_all_counts_only_unaligned(panel):
    rows = panel.line_rows()
    assert [i["key"] for i in panel.unaligned_items()] == ["k1", "k2", "k4"]
    panel.row_menu(rows[1]).actions()  # 不 exec，仅构造
    assert "3 行" in [a.text() for a in panel.row_menu(rows[1]).actions() if a.text()][-1]


def test_delete_key_emits_only_for_deletable_row(panel):
    got: list[dict] = []
    panel.delete_requested.connect(got.append)
    # 已对齐行不可删
    panel.set_focus_index(0)
    QTest.keyClick(panel, Qt.Key.Key_Delete)
    assert got == []
    # 未对齐行可删
    panel.set_focus_index(1)
    QTest.keyClick(panel, Qt.Key.Key_Delete)
    assert [i.get("key") for i in got] == ["k1"]
    # 已跳过行也可删（属于「没对应」的行）
    panel.set_focus_index(4)
    QTest.keyClick(panel, Qt.Key.Key_Delete)
    assert [i.get("key") for i in got] == ["k1", "k3"]


def test_deleted_row_hidden_by_default_and_shown_after_toggle(qapp):
    items = sample_items() + [
        {"type": "line", "speaker": None, "text": "已删除的行。", "file": FILE, "page": PAGE,
         "record": None, "wiki_only": True, "key": "k5", "deleted": True},
    ]
    p = ScriptPanel()
    p.resize(900, 600)
    p.show()
    p.show_items(items)
    # 默认不显示已删除行（k5 不在；两条已对齐行没有 key）
    assert [r.item.get("key") for r in p.line_rows()] == [None, "k1", "k2", None, "k3", "k4"]
    assert "删除 1" in p.info_label.text()
    assert not p.show_deleted_cb.isChecked()
    # 勾选后显示，且是灰字删除线、菜单只有「恢复该行」
    p.show_deleted_cb.setChecked(True)
    rows = {r.item.get("key"): r for r in p.line_rows()}
    assert "k5" in rows
    row = rows["k5"]
    assert row.is_deleted and not row.is_unaligned and not row.is_deletable
    assert row.text_widget.font().strikeOut()
    assert [(a.text(), a.data()) for a in p.row_menu(row).actions()] == [("恢复该行", "restore")]
    got: list[dict] = []
    p.restore_requested.connect(got.append)
    p.set_focus_index(p.line_rows().index(row))
    QTest.keyClick(p, Qt.Key.Key_Delete)  # 已删除行不可再删
    assert got == []
    # 再取消勾选 → 又隐藏
    p.show_deleted_cb.setChecked(False)
    assert "k5" not in [r.item.get("key") for r in p.line_rows()]
    p.close()


def test_contiguous_unaligned_run(panel):
    rows = panel.line_rows()
    run = panel.contiguous_unaligned(rows[1].item)
    assert [i["key"] for i in run] == ["k1", "k2"]  # 遇到已对齐行即止
    assert [i["key"] for i in panel.contiguous_unaligned(rows[5].item)] == ["k4"]
    assert panel.contiguous_unaligned(rows[0].item) == []
    assert panel.next_unaligned_key(rows[1].item) == "k2"
    assert panel.next_unaligned_key(rows[2].item) == "k4"  # 跳过已对齐/已跳过行
    assert panel.next_unaligned_key(rows[5].item) is None


def test_batch_dialog_construction_without_exec(qapp):
    rows = [it for it in sample_items() if it.get("wiki_only")]
    cands = [
        {"record": 0, "teller": "狼", "content": "第一条", "used": True},
        {"record": 1, "teller": "", "content": "第二条", "used": False},
        {"record": 2, "teller": "猎", "content": "第三条", "used": False},
    ]
    dlg = BatchMatchDialog(None, rows + [{"type": "scene", "text": "无 key 行"}], cands)
    assert dlg.result_value is None
    assert dlg.count_spin.maximum() == len(rows)
    assert dlg.count_spin.value() == min(DEFAULT_BATCH_COUNT, len(rows))
    assert dlg.items_list.count() == len(rows)
    # 未占用记录置顶
    assert [dlg.cands_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(3)] == [1, 2, 0]
    assert not dlg.ok_btn.isEnabled()
    dlg.cands_list.setCurrentRow(0)
    assert dlg.ok_btn.isEnabled() and dlg.selected_record() == 1
    # 数量可调 → 左侧列表随之变化
    dlg.count_spin.setValue(2)
    assert dlg.items_list.count() == 2
    # 直接 accept（不 exec）
    dlg._accept()
    assert dlg.result_value == (1, 2)
    assert dlg.result() == QDialog.DialogCode.Accepted


# ---------- B. 批量顺序分配（纯函数 + StoryEdit） ----------


def story_env(tmp_path: Path) -> StoryEdit:
    """临时 LLC 目录（含空内容记录）+ 最小包内 story_stages.json。"""
    llc = tmp_path / "LLC_zh-CN"
    (llc / "StoryData").mkdir(parents=True)
    (llc / "StoryData" / "S001B.json").write_text(
        json.dumps({"dataList": [
            {"id": 0, "teller": "狼", "content": "第一条"},
            {"id": 1, "teller": "", "content": "   "},  # 空内容 → 不可用
            {"id": 2, "teller": "猎", "content": "第二条"},
            {"id": 3, "teller": "", "content": "第三条"},
            {"id": 4, "teller": "", "content": "第四条"},
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "story_stages.json").write_text(json.dumps({
        "format_version": 2,
        "chapters": [{
            "chapter_id": "prologue", "chapter_label": "序章",
            "stages": [{
                "stage_code": "0-01",
                "pages": [{"segment": "战前", "title": PAGE, "file": FILE}],
                "items": [
                    {"type": "line", "speaker": None, "text": "甲", "file": FILE, "page": PAGE,
                     "record": None, "wiki_only": True, "key": "k1"},
                    {"type": "line", "speaker": None, "text": "乙", "file": FILE, "page": PAGE,
                     "record": None, "wiki_only": True, "key": "k2"},
                    {"type": "line", "speaker": None, "text": "丙", "file": FILE, "page": PAGE,
                     "record": None, "wiki_only": True, "key": "k3"},
                ],
            }],
        }],
    }, ensure_ascii=False), encoding="utf-8")
    se = StoryEdit(cache, llc)
    se.package_path = pkg / "story_stages.json"
    return se


def test_plan_batch_skips_used_and_empty_records(tmp_path):
    se = story_env(tmp_path)
    cands = se.candidates(FILE, used={2})
    assert [c["record"] for c in cands] == [0, 2, 3, 4]
    items = [{"key": "k1"}, {"key": "k2"}, {"key": "k3"}]
    # 记录 1 空内容、记录 2 已被占用 → 0,3,4
    assert plan_batch(items, 0, 3, {2}, cands) == [("k1", 0), ("k2", 3), ("k3", 4)]
    # 从中间起始
    assert plan_batch(items, 3, 2, set(), cands) == [("k1", 3), ("k2", 4)]
    # 条数受 count 限制
    assert plan_batch(items, 0, 1, set(), cands) == [("k1", 0)]
    # 可用记录不足 → 少分配，不报错
    assert plan_batch(items * 2, 0, 6, set(), cands) == [("k1", 0), ("k2", 2), ("k3", 3), ("k1", 4)]
    # 场景行/无 key 行被忽略
    assert plan_batch([{"type": "scene", "text": "无 key"}, {"key": "k9"}], 0, 2, set(), cands) == [("k9", 0)]


def test_plan_batch_without_candidate_list_skips_used(tmp_path):
    se = story_env(tmp_path)
    items = [{"key": "k1"}, {"key": "k2"}]
    assert plan_batch(items, 5, 2, {6}) == [("k1", 5), ("k2", 7)]
    assert plan_batch(items, 0, 0, set()) == []


def test_plan_batch_applies_through_story_edit(tmp_path):
    se = story_env(tmp_path)
    cands = se.candidates(FILE, used=set())
    plan = plan_batch([{"key": "k1"}, {"key": "k2"}, {"key": "k3"}], 0, 3, set(), cands)
    for key, rec in plan:
        se.set_record(PAGE, key, rec)
    # 批量：只在最后 rebuild 一次
    assert se.rebuild() == 3
    runtime = json.loads((se.cache_dir / "story_stages.json").read_text(encoding="utf-8"))
    items = runtime["chapters"][0]["stages"][0]["items"]
    assert [(i["key"], i["record"], i["wiki_only"]) for i in items] == [
        ("k1", 0, False), ("k2", 2, False), ("k3", 3, False),
    ]


# ---------- C. main_window 端到端：批量对应 + 键盘跳过 ----------


def _find_unaligned_stage(book):
    """剧本数据里第一个含「未对齐行」的关卡。"""
    for ch in book.chapter_list():
        for st in ch.get("stages", []):
            for it in st.get("items", []):
                if it.get("type") == "line" and it.get("wiki_only") and it.get("key") and it.get("file"):
                    return ch.get("chapter_id"), st.get("stage_code"), it
    return None


def test_batch_and_skip_flow_through_main_window(qapp, tmp_path, monkeypatch):
    """右键批量对应 → 一次 rebuild + 刷新；按 S 跳过 → apply_story_mapping。"""
    import shutil

    from limbus_patcher.app_state import AppContext
    from limbus_patcher.config import AppPaths
    from limbus_patcher.ui import batch_dialog as batch_mod
    from limbus_patcher.ui import main_window as mw_mod
    from limbus_patcher.ui.main_window import MainWindow

    game = tmp_path / "game"
    shutil.copytree(Path(__file__).resolve().parent / "fixtures" / "game", game)
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)

    found = _find_unaligned_stage(ctx.storybook)
    if not found:
        pytest.skip("剧本数据中没有未对齐行")
    cid, code, target = found
    # 为未对齐行所在的本地文件补一份记录（真实夹具里没有该文件）
    relfile = target["file"]
    fake = ctx.game_paths.llc_pack_dir / relfile
    fake.parent.mkdir(parents=True, exist_ok=True)
    fake.write_text(
        json.dumps({"dataList": [{"id": i, "teller": "狼", "content": f"记录{i}"} for i in range(200)]},
                   ensure_ascii=False),
        encoding="utf-8",
    )

    messages: list[tuple] = []
    monkeypatch.setattr(mw_mod, "info", lambda *a, **k: messages.append(a))
    monkeypatch.setattr(mw_mod, "warn", lambda *a, **k: messages.append(a))
    # 不 exec：让对话框选中第一条候选 + 指定条数，再走真实的 _accept 结果契约
    def fake_exec_safe(dlg):
        dlg.count_spin.setValue(min(2, dlg.count_spin.maximum()))
        dlg.cands_list.setCurrentRow(0)
        dlg._accept()
        return dlg.result()

    monkeypatch.setattr(batch_mod.BatchMatchDialog, "exec_safe", fake_exec_safe)

    win = MainWindow(ctx)
    try:
        win._enter_script_mode(cid, code)
        rows = win.script_panel.line_rows()
        target_row = next((r for r in rows if r.item is target), None)
        assert target_row is not None and target_row.is_unaligned
        run = win.script_panel.contiguous_unaligned(target)
        assert run and run[0] is target
        count = min(2, len(run))

        win._on_script_batch(target)

        page = target["page"]
        overrides = ctx.story_edit.overrides()
        assert len(overrides.get(page, {})) == count
        for key, rec in overrides[page].items():
            assert isinstance(rec["record"], int)
        # rebuild 一次即生效：运行时数据里这些 key 已对齐
        runtime = json.loads(ctx.story_edit.runtime_path.read_text(encoding="utf-8"))
        applied = {i["key"]: i for i in win.ctx.storybook.stage_items(cid, code) if i.get("key")}
        for it in run[:count]:
            assert applied[it["key"]]["record"] is not None
            assert applied[it["key"]]["wiki_only"] is False
        assert runtime["chapters"]  # 运行时数据已生成
        assert any("已建立" in str(a[1]) for a in messages)
        # 面板已刷新：原先的未对齐行变成已对齐行
        reloaded = next(r for r in win.script_panel.line_rows() if r.item.get("key") == target["key"])
        assert reloaded.is_aligned and not reloaded.is_unaligned

        # 键盘 S：跳过未对齐行（面板信号 → main_window → apply_story_mapping）
        found2 = _find_unaligned_stage(win.ctx.storybook)  # 批量后数据已刷新
        assert found2 is not None
        cid2, code2, target2 = found2
        win._enter_script_mode(cid2, code2)
        row2 = next(r for r in win.script_panel.line_rows() if r.item is target2)
        assert row2.is_unaligned
        skips_seen: list[dict] = []
        win.script_panel.skip_requested.connect(skips_seen.append)
        win.script_panel.setFocus()
        win.script_panel.set_focus_index(win.script_panel.line_rows().index(row2))
        QTest.keyClick(win.script_panel, Qt.Key.Key_S)
        assert [i["key"] for i in skips_seen] == [target2["key"]]
        # 已写入覆盖表（skip）并刷新面板
        assert ctx.story_edit.overrides()[target2["page"]][target2["key"]] == {"skip": True}
        assert "跳过 1" in win.script_panel.info_label.text()
    finally:
        win.close()

def test_delete_restore_and_unskip_flow_through_main_window(qapp, tmp_path, monkeypatch):
    """Delete 删除未对应行 → 面板隐藏；「显示已删除」→ 恢复；S 跳过 → 取消跳过；右键全删。"""
    import shutil

    from limbus_patcher.app_state import AppContext
    from limbus_patcher.config import AppPaths
    from limbus_patcher.ui import main_window as mw_mod
    from limbus_patcher.ui.main_window import MainWindow

    game = tmp_path / "game"
    shutil.copytree(Path(__file__).resolve().parent / "fixtures" / "game", game)
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)

    found = _find_unaligned_stage(ctx.storybook)
    if not found:
        pytest.skip("剧本数据中没有未对齐行")
    cid, code, target = found

    messages: list[tuple] = []
    monkeypatch.setattr(mw_mod, "info", lambda *a, **k: messages.append(a))
    monkeypatch.setattr(mw_mod, "warn", lambda *a, **k: messages.append(a))
    monkeypatch.setattr(mw_mod, "confirm", lambda *a, **k: True)

    win = MainWindow(ctx)
    try:
        win._enter_script_mode(cid, code)
        panel = win.script_panel
        page, key = target["page"], target["key"]
        row = next(r for r in panel.line_rows() if r.item is target)
        panel.set_focus_index(panel.line_rows().index(row))

        # ---- Delete：删除该行 ----
        QTest.keyClick(panel, Qt.Key.Key_Delete)
        assert ctx.story_edit.overrides()[page][key] == {"deleted": True}
        assert key not in [r.item.get("key") for r in panel.line_rows()]  # 已隐藏
        assert "删除 1" in panel.info_label.text()

        # ---- 显示已删除 → 恢复该行 ----
        panel.show_deleted_cb.setChecked(True)
        hidden = next(r for r in panel.line_rows() if r.item.get("key") == key)
        assert hidden.is_deleted and hidden.text_widget.font().strikeOut()
        win._on_script_restore(hidden.item)
        assert key not in ctx.story_edit.overrides().get(page, {})  # 覆盖已清除
        panel.show_deleted_cb.setChecked(False)
        back = next(r for r in panel.line_rows() if r.item.get("key") == key)
        assert back.is_unaligned and not back.is_deleted

        # ---- S 跳过 → 右键「取消跳过」 ----
        panel.set_focus_index(panel.line_rows().index(back))
        QTest.keyClick(panel, Qt.Key.Key_S)
        assert ctx.story_edit.overrides()[page][key] == {"skip": True}
        skipped = next(r for r in panel.line_rows() if r.item.get("key") == key)
        assert skipped.skipped and not skipped.is_unaligned
        win._on_script_unskip(skipped.item)
        assert key not in ctx.story_edit.overrides().get(page, {})
        assert next(r for r in panel.line_rows() if r.item.get("key") == key).is_unaligned

        # ---- 右键「删除本关全部未对应行」 ----
        n_unaligned = len(panel.unaligned_items())
        assert n_unaligned >= 1
        win._on_script_delete_all(panel.unaligned_items()[0])
        assert panel.unaligned_items() == []
        assert "未对齐 0" in panel.info_label.text()
        assert ctx.story_edit.deleted_count() == n_unaligned
        assert any("已从剧本中移除" in " ".join(str(x) for x in a) for a in messages)
        # 全部删掉后数据仍在（可恢复）
        panel.show_deleted_cb.setChecked(True)
        assert len([r for r in panel.line_rows() if r.is_deleted]) == n_unaligned
    finally:
        win.close()

def test_unaligned_only_filter_and_progress_info(qapp):
    p = ScriptPanel()
    p.resize(900, 600)
    p.show()
    p.show_items(sample_items())
    # 进度统计：11? 这里 sample 共 6 条对话行，未对齐 3 条
    text = p.info_label.text()
    assert "本关" in text and "%" in text and "未对齐 3" in text
    assert "已对齐" in p.info_label.toolTip()
    # 只看未对应：只剩未对齐行（k1/k2/k4），场景行与已对齐行都不显示
    p.unaligned_only_cb.setChecked(True)
    assert [r.item.get("key") for r in p.line_rows()] == ["k1", "k2", "k4"]
    assert "只看未对应" in p.info_label.text()
    # 与「显示已删除」叠加不冲突
    p.unaligned_only_cb.setChecked(False)
    assert len(p.line_rows()) == 6
    p.close()
