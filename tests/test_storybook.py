"""剧本对照表（storybook）测试。"""
from __future__ import annotations

import json
from pathlib import Path

from limbus_patcher.storybook import Storybook, SEGMENT_ORDER


def make_data(tmp_path: Path) -> Path:
    d = tmp_path / "meta"
    d.mkdir()
    (d / "story_stages.json").write_text(
        json.dumps({
            "format_version": 1,
            "chapters": [{
                "chapter_id": "prologue",
                "chapter_label": "序章",
                "stages": [
                    {"stage_code": "0-01", "pages": [
                        {"segment": "战前", "title": "0-01战前", "file": "StoryData/S001B.json"},
                        {"segment": "战后", "title": "0-01战后", "file": "StoryData/S001A.json"},
                    ]},
                    {"stage_code": "0-02", "pages": [
                        {"segment": "战前", "title": "0-02战前", "file": "StoryData/S002B.json"},
                    ]},
                ],
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return d


def make_llc(tmp_path: Path) -> Path:
    llc = tmp_path / "LLC_zh-CN"
    (llc / "StoryData").mkdir(parents=True)

    def write(name: str, tellers: list[str], texts: list[str]):
        (llc / "StoryData" / name).write_text(
            json.dumps({"dataList": [
                {"id": i, "teller": tellers[i], "content": texts[i]} for i in range(len(tellers))
            ]}, ensure_ascii=False),
            encoding="utf-8",
        )

    write("S001B.json", ["狼", None], ["总算明白了吗？", "你现在插翅难飞了。"])
    write("S001A.json", ["豹", None], ["真是不能理解。", "喂喂，等一下！"])
    write("S002B.json", ["维吉里乌斯"], ["看来你比刚才更有用了。"])
    return llc


def test_storybook_load_and_query(tmp_path):
    book = Storybook(overlay_dir=None, data_dir=make_data(tmp_path))
    chapters = book.chapter_list()
    assert chapters[0]["chapter_id"] == "prologue"
    stages = book.stages_of("prologue")
    assert [s["stage_code"] for s in stages] == ["0-01", "0-02"]
    pages = book.stage_pages("prologue", "0-01")
    assert [p["segment"] for p in pages] == ["战前", "战后"]
    assert book.file_stages("StoryData/S001B.json")[0][1] == "0-01"


def test_stage_records_order(tmp_path):
    llc = make_llc(tmp_path)
    book = Storybook(overlay_dir=None, data_dir=make_data(tmp_path))
    rows = book.stage_records(llc, "prologue", "0-01")
    # 战前(S001B) 先于 战后(S001A)，段内按记录顺序
    assert rows[0]["segment"] == "战前" and rows[0]["text"] == "总算明白了吗？"
    assert rows[2]["segment"] == "战后"
    # 说话人：teller 为空视为旁白（speaker=None）
    assert rows[1]["speaker"] is None
    assert len(rows) == 4
    # 排序函数：战前<战中<战后
    assert SEGMENT_ORDER["战前"] < SEGMENT_ORDER["战中"] < SEGMENT_ORDER["战后"]
