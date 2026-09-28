"""TextSource 的记录定位：零协优先合并 + 按键定位（防官方包更新后错位）。

背景：剧本数据（story_stages.json）里存的是「文件 + 记录下标 + key」。零协更新后
同一文件的记录数/顺序会变（我们补的 wiki 独有记录会把后面的整体顶位），只按下标读
就会张冠李戴；补译目录里「零协缺的记录」以前也读不到（只在文件整体缺失时才回退）。
"""
from __future__ import annotations

import json
from pathlib import Path

from limbus_patcher.textsource import TextSource, merge_records, record_id_of


def write_pack(root: Path, rel: str, rows: list[dict], prefix: str = "") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}{p.name}"
    target = p.parent / name
    target.write_text(json.dumps({"dataList": rows}, ensure_ascii=False), encoding="utf-8")
    return target


def test_record_id_of_认id_key_code():
    assert record_id_of({"id": 1109}) == "1109"
    assert record_id_of({"key": "D-20001"}) == "D-20001"
    assert record_id_of({"code": "Q1011"}) == "Q1011"
    assert record_id_of({"text": "x"}) is None
    assert record_id_of({"key": "  "}) is None
    assert record_id_of("nope") is None


def test_merge_records_零协优先且只在有新增时才复制():
    primary = [{"id": 1, "name": "官方一"}, {"id": 2, "name": "官方二"}]
    extra = [{"id": 2, "name": "我们的二"}, {"id": 3, "name": "我们的三"}]
    merged = merge_records(primary, extra)
    assert [r["name"] for r in merged] == ["官方一", "官方二", "我们的三"]
    assert merge_records(primary, [{"id": 1}]) is primary      # 没有新增 → 原对象


def test_同名文件两处都有时合并出我们多出的记录(tmp_path: Path):
    llc = tmp_path / "LLC_zh-CN"
    sup = tmp_path / "supplement"
    rel = "RPGSystem/rpg-loc-dialogue-floor-b2.json"
    write_pack(llc, rel, [{"key": "A", "texts": [{"index": 0, "text": "官方A"}]},
                          {"key": "B", "texts": [{"index": 0, "text": "官方B"}]}])
    write_pack(sup, rel, [{"key": "A", "texts": [{"index": 0, "text": "我们的A"}]},
                          {"key": "B", "texts": [{"index": 0, "text": "我们的B"}]},
                          {"key": "C", "texts": [{"index": 0, "text": "我们的C"}]}])
    src = TextSource.detect(llc, None, sup)
    dl = src.data_list(rel)
    assert [record_id_of(r) for r in dl] == ["A", "B", "C"]
    assert dl[0]["texts"][0]["text"] == "官方A"                 # 零协优先
    assert dl[2]["texts"][0]["text"] == "我们的C"


def test_记录按键定位不受顺序变化影响(tmp_path: Path):
    llc = tmp_path / "LLC_zh-CN"
    sup = tmp_path / "supplement"
    rel = "RPGSystem/rpg-loc-dialogue-floor-b2.json"
    # 官方包顺序换过（老数据的下标是构建时的顺序）
    write_pack(llc, rel, [{"key": "B", "texts": [{"index": 0, "text": "官方B"}]},
                          {"key": "A", "texts": [{"index": 0, "text": "官方A"}]}])
    write_pack(sup, rel, [{"key": "A", "texts": [{"index": 0, "text": "我们的A"}]},
                          {"key": "B", "texts": [{"index": 0, "text": "我们的B"}]}])
    src = TextSource.detect(llc, None, sup)
    text, _spk, _t = src.resolve(rel, 0, 0, None, "A")           # 下标指向 B，但 key 是 A
    assert text == "官方A"
    text_i, _s, _tt = src.resolve(rel, 0, 0)                     # 没有 key → 按下标
    assert text_i == "官方B"


def test_resolve_item_按键取文本且不再要求下标(tmp_path: Path):
    llc = tmp_path / "LLC_zh-CN"
    sup = tmp_path / "supplement"
    rel = "RPGSystem/rpg-loc-dialogue-floor-b2.json"
    write_pack(llc, rel, [{"key": "B", "texts": [{"index": 0, "text": "官方B"}]},
                          {"key": "A", "texts": [{"index": 1, "text": "官方A", "speaker": "但丁"}]}])
    write_pack(sup, rel, [{"key": "A", "texts": [{"index": 1, "text": "我们的A"}]},
                          {"key": "B", "texts": [{"index": 0, "text": "我们的B"}]}])
    src = TextSource.detect(llc, None, sup)
    item = {"type": "line", "file": rel, "record": 7, "text_index": 1, "field": "texts", "key": "A"}
    out = src.resolve_item(item)
    assert out["text"] == "官方A"
    assert out["speaker"] == "但丁"
    # 下标越界但有 key 也能取到
    assert src.resolve_item({**item, "record": 99})["text"] == "官方A"
    # key 找不到时退回下标（老数据没有 key）
    assert src.resolve_item({**item, "record": 0, "text_index": 0,
                             "key": None})["text"] == "官方B"


def test_补译文件里的独有记录也能读到(tmp_path: Path):
    """零协有同名文件、但没有那条记录（wiki 独有/官方 Localize 已删的未使用台词）。"""
    llc = tmp_path / "LLC_zh-CN"
    sup = tmp_path / "supplement"
    rel = "RPGSystem/rpg-loc-dialogue-floor-b2.json"
    write_pack(llc, rel, [{"key": "A", "texts": [{"index": 0, "text": "官方A"}]}])
    write_pack(sup, rel, [{"key": "A", "texts": [{"index": 0, "text": "我们的A"}]},
                          {"key": "Z", "texts": [{"index": 0, "text": "我们的Z", "speaker": "普伊"}]}])
    src = TextSource.detect(llc, None, sup)
    out = src.resolve_item({"type": "line", "file": rel, "record": 1,
                            "text_index": 0, "field": "texts", "key": "Z"})
    assert out["text"] == "我们的Z"
    assert out["speaker"] == "普伊"
