"""RPG 关卡剧本数据（第十章 10-04）的结构、生成与定位测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from limbus_patcher.story_rpg import (
    build_stage,
    entry_ref_for_item,
    is_skeleton_quest,
    load_plan,
    _record_range,
)
from limbus_patcher.storybook import Storybook

PACKAGE_DATA = Path(__file__).resolve().parent.parent / "limbus_patcher" / "data"
STORY = PACKAGE_DATA / "story_stages.json"


# ---------- 生成器（合成数据） ----------

def make_llc(tmp_path: Path) -> Path:
    llc = tmp_path / "LLC_zh-CN"
    (llc / "RPGSystem").mkdir(parents=True)
    (llc / "StoryData").mkdir(parents=True)
    (llc / "RPGSystem" / "rpg-loc-dialogue-floor-1.json").write_text(json.dumps({
        "dataList": [
            {"key": "D1001", "texts": [{"index": 0, "text": "第一句", "speaker": "但丁"},
                                        {"index": 1, "text": "第二句", "speaker": "默尔索"}]},
            {"key": "D1002", "texts": [{"index": 0, "text": "第三句", "speaker": None}]},
        ]
    }, ensure_ascii=False), encoding="utf-8")
    (llc / "RPGSystem" / "rpg-loc-dialogue-choice-floor-1.json").write_text(json.dumps({
        "dataList": [{"key": "DC1", "text": "选项一"}]
    }, ensure_ascii=False), encoding="utf-8")
    (llc / "RPGSystem" / "rpg-loc-quest-floor-1.json").write_text(json.dumps({
        "dataList": [
            {"key": "Q1001", "title": "探索", "description": "四处看看"},
            {"key": "Q1002", "title": "未使用", "description": "不该出现"},
            {"key": "Q1003", "title": "遗留", "description": "0901追加"},
        ]
    }, ensure_ascii=False), encoding="utf-8")
    (llc / "StoryData" / "S1000B.json").write_text(json.dumps({
        "dataList": [{"id": 1, "teller": "广播", "title": "百货", "content": "欢迎光临"}]
    }, ensure_ascii=False), encoding="utf-8")
    return llc


STAGE_PLAN = {
    "mode": "rpg",
    "label": "测试关",
    "quest_files": ["RPGSystem/rpg-loc-quest-floor-1.json"],
    "branches": [
        {
            "id": "b01", "label": "01 过场", "kind": "story", "kind_label": "过场",
            "confidence": "high", "evidence": "测试",
            "parts": [{"file": "StoryData/S1000B.json"}],
        },
        {
            "id": "b02", "label": "02 探索", "kind": "rpg", "kind_label": "RPG 探索",
            "quests": ["Q1001", "Q1002", "Q1003"],
            "parts": [
                {"file": "RPGSystem/rpg-loc-dialogue-floor-1.json", "records": [0, 0]},
                {"file": "RPGSystem/rpg-loc-dialogue-choice-floor-1.json"},
            ],
        },
        {
            "id": "b03", "label": "03 收尾", "kind": "rpg", "kind_label": "RPG 探索",
            "parts": [{"file": "RPGSystem/rpg-loc-dialogue-floor-1.json", "records": [1, None]}],
        },
    ],
}


def test_build_stage_orders_and_fields(tmp_path):
    """生成的是「位置」（路径 + 记录下标 + 字段），文本运行时从语言文件取。"""
    llc = make_llc(tmp_path)
    built = build_stage(STAGE_PLAN, llc)
    items = built["items"]
    assert [b["branch_id"] for b in built["branches"]] == ["b01", "b02", "b03"]
    lines = [i for i in items if i["type"] == "line"]
    assert lines and all("text" not in i for i in lines), "数据里不该存游戏文本"
    assert [(i["file"], i["record"], i.get("text_index")) for i in lines] == [
        ("StoryData/S1000B.json", 0, None),
        ("RPGSystem/rpg-loc-dialogue-floor-1.json", 0, 0),
        ("RPGSystem/rpg-loc-dialogue-floor-1.json", 0, 1),
        ("RPGSystem/rpg-loc-dialogue-choice-floor-1.json", 0, None),
        ("RPGSystem/rpg-loc-dialogue-floor-1.json", 1, 0),
    ]
    # RPG 行带 text_index/key/field，过场行不带
    assert lines[1]["text_index"] == 0 and lines[1]["key"] == "D1001"
    assert lines[1]["field"] == "texts"
    assert lines[0]["text_index"] is None and lines[0]["field"] == "content"
    assert lines[3]["field"] == "text"  # 选项记录是单文本记录
    # 按位置取文本（当前来源 = 零协）
    from limbus_patcher.textsource import TextSource

    src = TextSource.detect(llc, None)
    assert [src.resolve(i["file"], i["record"], i.get("text_index"), i.get("field"))[0]
            for i in lines] == ["欢迎光临", "第一句", "第二句", "选项一", "第三句"]
    # 分支归属按编排表
    assert [i["branch"] for i in lines] == ["b01", "b02", "b02", "b02", "b03"]
    # 任务骨架只留有效任务，且插在分支开头
    quests = [i for i in items if i.get("source") == "quest"]
    assert [q["quest"] for q in quests] == ["Q1001"]
    assert items.index(quests[0]) < items.index(lines[1])
    assert all(i["source"] == "llc" for i in lines)


def test_selection_marker_for_choice(tmp_path):
    built = build_stage(STAGE_PLAN, make_llc(tmp_path))
    markers = [i["text"] for i in built["items"] if i.get("source") == "plan"]
    assert "◇ 选择项" in markers


def test_pages_declare_all_files(tmp_path):
    built = build_stage(STAGE_PLAN, make_llc(tmp_path))
    page = next(p for p in built["pages"] if p["branch_id"] == "b02")
    assert page["file"] == "RPGSystem/rpg-loc-dialogue-floor-1.json"
    assert set(page["files"]) == {"RPGSystem/rpg-loc-dialogue-floor-1.json",
                                 "RPGSystem/rpg-loc-dialogue-choice-floor-1.json"}


def test_missing_file_is_warned_not_fatal(tmp_path):
    plan = json.loads(json.dumps(STAGE_PLAN))
    plan["branches"][1]["parts"].append({"file": "RPGSystem/不存在.json"})
    built = build_stage(plan, make_llc(tmp_path))
    assert any("找不到文件" in w for w in built["warnings"])
    assert any(i["type"] == "line" for i in built["items"])


def test_record_range():
    assert _record_range({}, 10) == (0, 10)
    assert _record_range({"records": [2, 4]}, 10) == (2, 5)
    assert _record_range({"records": [8, None]}, 10) == (8, 10)
    assert _record_range({"records": [8, 99]}, 10) == (8, 10)
    assert _record_range({"records": [-3, 1]}, 10) == (0, 2)


def test_is_skeleton_quest():
    assert is_skeleton_quest({"title": "探索", "description": "四处看看"})
    assert not is_skeleton_quest({"title": "未使用", "description": "说明"})
    assert not is_skeleton_quest({"title": "遗留", "description": "0901追加"})
    assert not is_skeleton_quest({"title": "空", "description": ""})


# ---------- 定位（剧本行 → 编辑器条目） ----------

def test_entry_ref_for_rpg_line():
    ref = entry_ref_for_item({
        "file": "RPGSystem/rpg-loc-dialogue-floor-1.json", "record": 3, "text_index": 2,
        "field": "texts", "text": "x", "source": "llc",
    }, {"key": "D1090", "texts": []})
    assert ref.file.endswith("floor-1.json")
    assert ref.record_index == 3
    assert ref.id is None  # RPG 记录没有 KeyID，只认下标
    assert ref.field_path == [{"k": "texts"}, {"i": 2, "h": {"index": 2}}, {"k": "text"}]


def test_entry_ref_for_choice_line():
    """选项/地点记录是单文本记录（字段是 text），不能按 content 定位。"""
    ref = entry_ref_for_item({
        "file": "RPGSystem/rpg-loc-dialogue-choice-floor-1.json", "record": 0,
        "text_index": None, "field": "text", "text": "选项一",
    }, {"key": "DC1"})
    assert ref.field_path == [{"k": "text"}]


def test_entry_ref_for_story_line():
    ref = entry_ref_for_item({
        "file": "StoryData/S1000B.json", "record": 0, "text_index": None, "text": "x",
    }, {"id": 1001, "content": "x"})
    assert ref.id == 1001
    assert ref.field_path == [{"k": "content"}]


# ---------- 出厂的 story_stages.json ----------

@pytest.fixture(scope="module")
def story():
    if not STORY.is_file():
        pytest.skip("没有 story_stages.json")
    return json.loads(STORY.read_text(encoding="utf-8-sig"))


def find_stage(story, code):
    for ch in story.get("chapters", []):
        for st in ch.get("stages", []):
            if st.get("stage_code") == code:
                return st
    return None


def test_plan_covers_shipped_branches(story):
    """编排表与出厂数据必须一致（改了一个忘了另一个就会被这里拦住）。"""
    plan = load_plan()
    for code, stage in ((c, find_stage(story, c)) for c in (plan.get("stages") or {})):
        if stage is None:
            continue
        assert [b["branch_id"] for b in stage.get("branches") or []] == \
               [b["id"] for b in plan["stages"][code]["branches"]], f"{code} 分支顺序与编排表不一致"


def test_rpg_stage_structure(story):
    stage = find_stage(story, "10-04")
    if stage is None or not stage.get("branches"):
        pytest.skip("本仓库数据里没有 10-04 分支")
    branches = stage["branches"]
    ids = [b["branch_id"] for b in branches]
    assert ids == sorted(ids, key=lambda x: int(x[1:]))  # 分支按 ID 递增 = 游玩顺序
    items = stage["items"]
    known = set(ids)
    assert all(i.get("branch") in known for i in items)
    # items 的分支顺序 == branches 顺序（允许重复出现同一分支的连续块）
    seen: list[str] = []
    for i in items:
        if not seen or seen[-1] != i["branch"]:
            seen.append(i["branch"])
    assert seen == ids
    # 每个 RPG 对话行都能定位到编辑器：file + record + (text_index)
    rpg_lines = [i for i in items if i.get("type") == "line" and i.get("file", "").startswith("RPGSystem/")]
    assert rpg_lines
    assert all(isinstance(i.get("record"), int) for i in rpg_lines)
    assert all(i.get("field") in ("texts", "text", "content") for i in rpg_lines)
    assert all(isinstance(i.get("text_index"), int) for i in rpg_lines if i.get("field") == "texts")
    # 场景行不会被当成可编辑行：只有任务行（source=quest）带 file（用来现取任务文本）
    for it in items:
        if it.get("type") != "scene":
            continue
        assert not it.get("file") or (it.get("source") == "quest" and it.get("quest")), it
    # 数据里不留任何游戏文本（只存位置）
    assert all("text" not in i for i in items if i.get("type") == "line")


def test_storybook_branch_api(story, tmp_path):
    data_dir = tmp_path / "meta"
    data_dir.mkdir()
    (data_dir / "story_stages.json").write_text(
        json.dumps(story, ensure_ascii=False), encoding="utf-8")
    book = Storybook(data_dir=data_dir)
    assert book.problems == [], book.problems[:3]
    branches = book.branches_of("c10", "10-04")
    if not branches:
        pytest.skip("没有分支数据")
    all_items = book.stage_items("c10", "10-04")
    one = book.stage_items("c10", "10-04", branches[0]["branch_id"])
    assert one and len(one) < len(all_items)
    assert all(i["branch"] == branches[0]["branch_id"] for i in one)
    # 分支声明的每个文件都能反查回该关卡（含多文件分支）
    for br in branches:
        for rel in br.get("files") or []:
            hits = book.file_stages(rel)
            assert any(cid == "c10" and code == "10-04" for cid, code, _pg in hits), rel


# ---------- 剧本面板：分支挂在关卡下面 ----------

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from limbus_patcher.ui.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


def test_script_panel_stage_combo_lists_branches(qapp):
    from limbus_patcher.ui.script_panel import ScriptPanel

    panel = ScriptPanel()
    stages = [
        {"stage_code": "10-03", "pages": [{"segment": "战前", "title": "10-03战前"}]},
        {"stage_code": "10-04",
         "branches": [{"branch_id": "b01", "label": "01 进店广播", "kind": "story"},
                      {"branch_id": "b02", "label": "02 1F·坠落与苏醒", "kind": "story"}],
         "pages": [{"segment": "过场", "title": "01 进店广播",
                    "file": "StoryData/S1000B.json", "files": ["StoryData/S1000B.json"]}]},
    ]
    got: list = []
    panel.stage_selected.connect(lambda d: got.append(d))
    panel.load_stage("第10章", stages, "10-04", [{"type": "line", "text": "t", "speaker": "A"}],
                     branch_id="b02")
    labels = [panel.stage_combo.itemText(i) for i in range(panel.stage_combo.count())]
    assert any(l.startswith("10-04") for l in labels)
    assert any("└ 01 进店广播" in l for l in labels)
    assert any("└ 02 1F·坠落与苏醒" in l for l in labels)
    # 选中的是「关卡 → 分支」而不是整关
    assert panel.stage_combo.currentData() == {"stage": "10-04", "branch": "b02"}
    # 切到整关（不带分支）也要能选回去
    panel.load_stage("第10章", stages, "10-04", [{"type": "line", "text": "t"}], branch_id=None)
    assert panel.stage_combo.currentData() == {"stage": "10-04", "branch": None}


def test_script_panel_renders_in_chunks(qapp):
    """大关卡分批渲染：切换只建一屏控件，其余按需补齐（卡顿修复）。"""
    from limbus_patcher.ui.script_panel import ScriptPanel

    panel = ScriptPanel()
    items = [{"type": "line", "text": f"行{i}", "speaker": "A", "record": i,
              "file": "f.json", "page": "p"} for i in range(500)]
    panel.show_items(items)
    chunk = ScriptPanel._CHUNK
    assert len(panel.line_rows()) == chunk
    assert panel.remaining_items() == 500 - chunk
    # 「继续载入」补一批
    assert panel.load_more() == chunk
    assert len(panel.line_rows()) == chunk * 2
    # 按 ↓ 越过已渲染末尾：自动补齐到目标行
    target = chunk * 2 + 5
    idx = panel.set_focus_index(target)
    assert idx == target and len(panel.line_rows()) >= target + 1
    assert panel.focus_index() == target
    # 移到最后一行再按 ↓ 也会继续补齐
    last = len(panel.line_rows()) - 1
    panel.set_focus_index(last)
    panel.move_focus(1)
    assert len(panel.line_rows()) > last + 1 or panel.remaining_items() == 0


def test_unaligned_helpers_cover_unrendered_rows(qapp):
    from limbus_patcher.ui.script_panel import ScriptPanel

    panel = ScriptPanel()
    items = [{"type": "line", "text": f"r{i}", "wiki_only": True, "key": f"k{i}",
              "record": i, "file": "f.json", "page": "p"} for i in range(300)]
    panel.show_items(items)
    # 只渲染了前 120 行，但「删除全部未对应」必须看到全部 300 条
    assert len(panel.line_rows()) < 300
    assert len(panel.unaligned_items()) == 300
    assert panel.next_unaligned_key(items[0]) == "k1"
    assert len(panel.contiguous_unaligned(items[0])) == 300


def test_scroll_to_bottom_loads_more(qapp):
    """滚到底自动补齐下一批（大关卡不靠一次渲染）。"""
    from limbus_patcher.ui.script_panel import ScriptPanel

    panel = ScriptPanel()
    items = [{"type": "line", "text": f"行{i}", "speaker": "A", "record": i,
              "file": "f.json", "page": "p"} for i in range(600)]
    panel.show_items(items)
    before = panel.remaining_items()
    bar = panel.scroll.verticalScrollBar()
    panel._on_scroll(bar.maximum())  # 模拟滚到底
    assert panel.remaining_items() < before


# ---------- 剧本行渲染：<...> 不能被当成格式标签吃掉 ----------

def test_angle_bracket_lines_are_rendered(qapp):
    """但丁的内心台词整行包在 <...> 里，必须原样显示。

    旧实现（parse_ruby 的 `<[^>]*>`）会把它整段删掉：文本不显示、控件高度塌成 0，
    整行跟着点不中（用户报的「<…>文本不显示 / 战斗气泡点不了」就是这个）。
    """
    from limbus_patcher.ui.script_panel import RubyTextWidget

    w = RubyTextWidget()
    text = "<黄金皮革……她难道是在说某种类似金枝的东西吗？>"
    w.set_text(text)
    assert "".join(s.text for s in w._spans) == text
    assert w.sizeHint().height() >= 24          # 高度不塌
    # 真标签仍然要按格式渲染（不能因为修这个把格式弄丢）
    w.set_text("<color=#4457b1>……那就向大海去吧……</color>")
    assert "".join(s.text for s in w._spans) == "……那就向大海去吧……"
    # 空文本也不许塌陷
    w.set_text("")
    assert w.sizeHint().height() >= 24


def test_script_row_click_anywhere(qapp):
    """点行内任何位置（含文本区）都算点这一行。"""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from limbus_patcher.ui.script_panel import ScriptLineRow

    row = ScriptLineRow("但丁", None, "<这地方……看起来像是店铺……>", False)
    row.resize(900, 34)
    got = []
    row.clicked_line.connect(lambda r: got.append(r))
    for widget in (row, row.text_widget):
        got.clear()
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton,
                         pos=QPoint(max(1, widget.width() // 2), max(1, widget.height() // 2)))
        assert got, f"点在 {type(widget).__name__} 上没触发行点击"
