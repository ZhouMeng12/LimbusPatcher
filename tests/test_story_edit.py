"""剧本手动映射（StoryEdit）测试。"""
from __future__ import annotations

import json
from pathlib import Path

from limbus_patcher.story_edit import StoryEdit
from limbus_patcher.storybook import Storybook


def make_env(tmp_path: Path) -> tuple[StoryEdit, Path]:
    # 包内数据（复制真实包数据中的最小结构）
    cache = tmp_path / "cache"
    cache.mkdir()
    llc = tmp_path / "LLC_zh-CN"
    (llc / "StoryData").mkdir(parents=True)
    (llc / "StoryData" / "S001B.json").write_text(
        json.dumps({"dataList": [
            {"id": 0, "teller": "狼", "content": "总算明白了吗？"},
            {"id": 1, "teller": "", "content": "接着，又有几条锁链将我刺穿。"},
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )
    data = {
        "format_version": 2,
        "chapters": [{
            "chapter_id": "prologue", "chapter_label": "序章",
            "stages": [{"stage_code": "0-01", "pages": [
                {"segment": "战前", "title": "0-01战前", "file": "StoryData/S001B.json"}],
                "items": [
                    {"type": "scene", "text": "黑森林", "file": "StoryData/S001B.json", "record": None, "page": "0-01战前"},
                    {"type": "line", "speaker": "狼", "text": "总算明白了吗？", "file": "StoryData/S001B.json",
                     "record": 0, "page": "0-01战前"},
                    {"type": "line", "speaker": None, "text": "接着，又有几根锁链将我刺穿。", "file": "StoryData/S001B.json",
                     "record": None, "wiki_only": True, "page": "0-01战前", "key": "接着又有几根锁链将我刺穿"},
                ]}],
        }],
    }
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "story_stages.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    se = StoryEdit(cache, llc)
    se.package_path = pkg / "story_stages.json"
    return se, cache


def test_candidates(tmp_path):
    se, _ = make_env(tmp_path)
    cands = se.candidates("StoryData/S001B.json", used={0})
    assert [c["record"] for c in cands] == [0, 1]
    assert cands[0]["used"] is True and cands[1]["used"] is False


def test_manual_mapping_and_skip(tmp_path):
    se, cache = make_env(tmp_path)
    page, key = "0-01战前", "接着又有几根锁链将我刺穿"
    assert se.rebuild() == 0
    se.set_record(page, key, 1)
    assert se.rebuild() == 1
    runtime = json.loads((cache / "story_stages.json").read_text(encoding="utf-8"))
    item = runtime["chapters"][0]["stages"][0]["items"][2]
    assert item["record"] == 1 and item["wiki_only"] is False and item.get("manual") is True
    assert item["text"] == "接着，又有几条锁链将我刺穿。"
    # Storybook 优先加载 cache 副本
    book = Storybook(overlay_dir=cache, data_dir=tmp_path / "pkg")
    assert book.stage_items("prologue", "0-01")[2]["record"] == 1
    # 跳过标记
    se.mark_skip(page, key)
    se.rebuild()
    runtime = json.loads((cache / "story_stages.json").read_text(encoding="utf-8"))
    item = runtime["chapters"][0]["stages"][0]["items"][2]
    assert item.get("skip") is True and item.get("wiki_only") is True
    # 清除
    se.clear(page, key)
    assert se.rebuild() == 0
    assert not (cache / "story_stages.json").exists()

# ---------- 删除（未对应行） ----------


def test_mark_deleted_and_restore(tmp_path):
    se, cache = make_env(tmp_path)
    page, key = "0-01战前", "接着又有几根锁链将我刺穿"
    se.mark_deleted(page, key)
    assert se.overrides()[page][key] == {"deleted": True}
    assert se.rebuild() == 1
    items = json.loads((cache / "story_stages.json").read_text(encoding="utf-8"))["chapters"][0]["stages"][0]["items"]
    item = items[2]
    # 运行时数据里仍然保留（面板默认隐藏，勾选「显示已删除」可恢复）
    assert item["deleted"] is True and item["wiki_only"] is True
    assert item.get("record") is None
    # Storybook 也能读到（由面板决定是否显示）
    book = Storybook(overlay_dir=cache, data_dir=tmp_path / "pkg")
    assert book.stage_items("prologue", "0-01")[2]["deleted"] is True
    # 还原：清除覆盖 → 行回到剧本（未对齐）
    se.clear(page, key)
    assert se.rebuild() == 0
    assert not (cache / "story_stages.json").exists()  # 无覆盖时不保留运行时副本
    assert page not in se.overrides()


def test_deleted_takes_precedence_over_record_and_skip(tmp_path):
    se, cache = make_env(tmp_path)
    page, key = "0-01战前", "接着又有几根锁链将我刺穿"
    se.set_record(page, key, 1)
    se.rebuild()
    se.mark_deleted(page, key)  # 删除覆盖已有对应
    se.rebuild()
    items = json.loads((cache / "story_stages.json").read_text(encoding="utf-8"))["chapters"][0]["stages"][0]["items"]
    assert items[2]["deleted"] is True and items[2]["wiki_only"] is True
    assert items[2].get("manual") is None
    # 每个 key 只保留一条规则：后写入的生效（skip 覆盖 deleted）
    se.mark_skip(page, key)
    assert se.overrides()[page][key] == {"skip": True}
    se.rebuild()
    items = json.loads((cache / "story_stages.json").read_text(encoding="utf-8"))["chapters"][0]["stages"][0]["items"]
    assert items[2].get("deleted") is None and items[2]["skip"] is True


def test_mark_deleted_many_and_count(tmp_path):
    se, cache = make_env(tmp_path)
    page, key = "0-01战前", "接着又有几根锁链将我刺穿"
    assert se.deleted_count() == 0
    assert se.mark_deleted_many([(page, key), (page, ""), (None, key)]) == 1  # 空 page/key 跳过
    assert se.deleted_count() == 1
    assert "deleted" in se.overrides()[page][key]
    # 批量删除多条（同一页多 key + 多页）
    assert se.mark_deleted_many([("p", "k1"), ("p", "k2"), ("q", "k3")]) == 3
    assert se.deleted_count() == 4
    assert se.rebuild() >= 1

# ---------- 自动建议对应 ----------


def test_suggest_matches_picks_best_unused_record(tmp_path):
    se, cache = make_env(tmp_path)
    page = "0-01战前"
    unaligned = {"type": "line", "page": page, "key": "k", "file": "StoryData/S001B.json",
                 "text": "接着，又有几根锁链将我刺穿。", "wiki_only": True, "record": None}
    sugg = se.suggest_matches([unaligned], {page: {0}})  # 记录 0 已被占用
    assert len(sugg) == 1
    assert sugg[0]["record"] == 1 and sugg[0]["similarity"] >= 0.85
    assert sugg[0]["content"] == "接着，又有几条锁链将我刺穿。"
    # 完全不像的行不给建议
    far = dict(unaligned, key="k2", text="完全无关的一句话内容")
    assert se.suggest_matches([far], {page: {0}}) == []
    # 阈值可调：调低到 0 就总能给出候选
    assert se.suggest_matches([far], {page: {0}}, threshold=0.0)
    # 同一条记录不会被分配给两行
    twin = dict(unaligned, key="k3")
    both = se.suggest_matches([unaligned, twin], {page: {0}})
    assert len(both) == 1
    # 缺 key/file/page 的行直接跳过
    assert se.suggest_matches([{"type": "line", "text": "x"}]) == []


def test_apply_suggestions_writes_manual_mapping(tmp_path):
    se, cache = make_env(tmp_path)
    page, key = "0-01战前", "接着又有几根锁链将我刺穿"
    unaligned = {"type": "line", "page": page, "key": key, "file": "StoryData/S001B.json",
                 "text": "接着，又有几根锁链将我刺穿。", "wiki_only": True, "record": None}
    sugg = se.suggest_matches([unaligned], {page: {0}})
    assert se.apply_suggestions(sugg) == 1
    rule = se.overrides()[page][key]
    assert rule["record"] == 1 and rule["certainty"] == "auto" and "相似度" in rule["note"]
    assert se.rebuild() == 1
    book = Storybook(overlay_dir=cache, data_dir=tmp_path / "pkg")
    item = book.stage_items("prologue", "0-01")[2]
    assert item["record"] == 1 and item["wiki_only"] is False and item.get("manual") is True
