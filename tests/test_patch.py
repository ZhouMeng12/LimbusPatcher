from __future__ import annotations

import json
from pathlib import Path

import pytest

from limbus_patcher.patch import (
    EntryRef,
    Profile,
    ProfileError,
    decode_fp,
    encode_fp,
    get_value,
    is_data_value,
    record_title,
    ref_label,
    set_value,
    walk_leaves,
)

DATA = {
    "dataList": [
        {
            "id": 1,
            "model": "dummy",
            "levelList": [
                {"level": 1, "name": "往昔", "desc": "L1", "coinlist": [{"coindescs": [{"desc": "coin1"}]}]},
                {"level": 3, "name": "往昔", "desc": "", "coinlist": [{"coindescs": [{"desc": "coin3"}]}]},
            ],
        }
    ]
}


def test_walk_excludes_id_and_model():
    record = DATA["dataList"][0]
    leaves = dict((encode_fp(fp), t) for fp, t in walk_leaves(record))
    for fp_str in leaves:
        assert '"id"' not in fp_str and '"model"' not in fp_str
    assert any(leaves.values())


def test_fp_roundtrip():
    fp = [{"k": "levelList"}, {"i": 1, "h": {"level": 3}}, {"k": "desc"}]
    assert decode_fp(encode_fp(fp)) == fp


def test_get_set_value_with_hint():
    record = DATA["dataList"][0]
    fp = [{"k": "levelList"}, {"i": 99, "h": {"level": 3}}, {"k": "desc"}]
    # 下标越界但提示命中 → 仍能定位
    assert get_value(record, fp) == ""
    set_value(record, fp, "新等级3描述")
    assert get_value(record, fp) == "新等级3描述"
    assert record["levelList"][1]["desc"] == "新等级3描述"


def test_set_value_nested_coin():
    record = DATA["dataList"][0]
    fp = [{"k": "levelList"}, {"i": 0, "h": {"level": 1}}, {"k": "coinlist"}, {"i": 0, "h": None}, {"k": "coindescs"}, {"i": 0, "h": None}, {"k": "desc"}]
    assert get_value(record, fp) == "coin1"
    set_value(record, fp, "coin-new")
    assert record["levelList"][0]["coinlist"][0]["coindescs"][0]["desc"] == "coin-new"


def test_set_value_errors():
    record = DATA["dataList"][0]
    with pytest.raises(KeyError):
        set_value(record, [{"k": "nope"}], "x")
    with pytest.raises(KeyError):
        set_value(record, [{"k": "levelList"}], "x")  # 终点不是字符串


def test_record_title():
    assert record_title({"name": "强壮", "desc": "……"}) == "强壮"
    assert record_title({"content": "很长的一句话"}) == "很长的一句话"
    assert record_title({}) == "（无名称条目）"


# ---- Profile ----

def ref(file="BattleKeywords.json", id="Enhancement", fp=None, ri=1):
    return EntryRef(file=file, id=id, record_index=ri, field_path=fp or [{"k": "desc"}])


def test_profile_upsert_remove():
    p = Profile()
    e = p.upsert(ref(), "新描述", "旧描述")
    assert e is not None and p.count() == 1 and p.revision == 1
    # 相同值不重复计数
    assert p.upsert(ref(), "新描述", "旧描述") is not None and p.revision == 1
    # 与原文一致 → 视为还原（删除）
    assert p.upsert(ref(), "旧描述", "旧描述") is None and p.count() == 0 and p.revision == 2
    assert not p.remove(ref())


def test_profile_snapshot_under_concurrent_mutation():
    """回归：部署线程遍历条目时 UI 线程增删 → 不能抛 dictionary changed size。"""
    import threading

    p = Profile()
    for i in range(200):
        p.upsert(EntryRef(file=f"f{i}.json", id=i, record_index=0, field_path=[{"k": "desc"}]), f"v{i}", f"o{i}")

    stop = threading.Event()
    errors: list[BaseException] = []

    def writer():
        i = 1000
        while not stop.is_set():
            r = EntryRef(file=f"f{i}.json", id=i, record_index=0, field_path=[{"k": "desc"}])
            p.upsert(r, f"v{i}", f"o{i}")
            p.remove(r)
            p.clear()
            i += 1

    def reader():
        try:
            while not stop.is_set():
                snap = p.snapshot()  # 快照必须是「当时那一刻」的副本，遍历它不会炸
                vals = p.values()
                for _k, entry in snap.items():
                    assert entry.ref.file
                for entry in vals:
                    assert entry.value is not None
                p.to_obj()
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    threading.Event().wait(0.35)
    stop.set()
    for t in threads:
        t.join(3)
    assert not errors, errors


def test_profile_clear_bumps_revision():
    p = Profile()
    p.upsert(ref(), "新描述", "旧描述")
    assert p.clear() == 1
    assert p.count() == 0 and p.revision == 2
    assert p.clear() == 0 and p.revision == 3


def test_profile_roundtrip(tmp_path):
    p = Profile(name="测试方案")
    p.upsert(ref(), "新描述", "旧描述")
    p.save(tmp_path / "p.json")
    q = Profile()
    q.load(tmp_path / "p.json")
    assert q.name == "测试方案" and q.revision == p.revision
    assert q.get(ref()).value == "新描述"


def test_profile_validate():
    ok = Profile.validate_obj({"format_version": 1, "name": "x", "revision": 0, "entries": []})
    assert ok == []
    bad = Profile.validate_obj({"format_version": 99, "name": 1, "entries": [{"value": 1}]})
    assert len(bad) >= 3


def test_profile_load_corrupted(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not json", encoding="utf-8")
    q = Profile()
    with pytest.raises(ProfileError):
        q.load(p)


def test_profile_load_bad_schema(tmp_path):
    p = tmp_path / "bad2.json"
    p.write_text(json.dumps({"format_version": 1, "name": "x", "entries": [{"file": ""}]}, ensure_ascii=False), encoding="utf-8")
    q = Profile()
    with pytest.raises(ProfileError):
        q.load(p)


def test_entry_ref_key_roundtrip():
    r = ref(id="AreaAtk", fp=[{"k": "name"}], ri=0)
    r2 = EntryRef.from_key(r.key())
    assert r == r2


def test_profile_atomic_save(tmp_path):
    p = Profile()
    p.upsert(ref(), "新", "旧")
    dest = tmp_path / "p.json"
    p.save(dest)
    # 文件是合法 JSON 且内容含条目
    obj = json.loads(dest.read_text(encoding="utf-8"))
    assert obj["entries"][0]["value"] == "新"
    assert len(list(tmp_path.glob(".p.json.*"))) == 0  # 无残留临时文件


# ---- 无 id 记录（真实包里的人格剧情） ----


def no_id_ref(ri=1, fp=None) -> EntryRef:
    return EntryRef(file="StoryData/P10210.json", id=None, record_index=ri, field_path=fp or [{"k": "content"}])


def test_entry_ref_key_without_id_is_unique_and_roundtrips():
    r1 = no_id_ref(ri=1)
    r2 = no_id_ref(ri=2)
    assert r1.key() != r2.key()  # record_index 保证无 id 时键仍唯一
    assert "null" in r1.key()  # id 序列化为 JSON null（不是字符串 "None"）
    assert "None" not in r1.key()
    back = EntryRef.from_key(r1.key())
    assert back == r1 and back.id is None and back.record_index == 1
    # 有 id 的条目（含 id=0）行为不变
    zero = EntryRef(file="StoryData/1D101A.json", id=0, record_index=0, field_path=[{"k": "content"}])
    assert EntryRef.from_key(zero.key()) == zero
    assert ref_label(zero) == "0"


def test_ref_label_never_shows_none():
    assert ref_label(no_id_ref(ri=7)) == "记录 #7"
    assert ref_label(ref()) == "Enhancement"
    assert ref_label(None) == "（无名称条目）"


def test_record_title_falls_back_to_record_number():
    r = no_id_ref(ri=7)
    assert record_title({}, r) == "记录 #7"
    assert record_title({}, None) == "（无名称条目）"  # 老调用方式不变
    assert record_title({"content": "很长的一句话"}, r) == "很长的一句话"


def test_entry_ref_from_dict_without_id():
    r = EntryRef.from_dict({"file": "StoryData/P10210.json", "record_index": 2, "field_path": [{"k": "content"}]})
    assert r.id is None and r.record_index == 2
    assert EntryRef.from_dict(r.to_dict()) == r


def test_profile_roundtrip_without_id(tmp_path):
    p = Profile()
    r = no_id_ref(ri=3)
    assert p.upsert(r, "改写后的台词", "原台词") is not None
    assert p.count() == 1
    p.save(tmp_path / "p.json")
    obj = json.loads((tmp_path / "p.json").read_text(encoding="utf-8"))
    assert obj["entries"][0]["id"] is None
    assert obj["entries"][0]["record_index"] == 3

    q = Profile()
    q.load(tmp_path / "p.json")
    entry = q.get(r)
    assert entry is not None and entry.value == "改写后的台词"
    assert entry.ref.id is None and entry.ref.record_index == 3
    # 还原（值 = 原文）→ 条目移除
    assert q.upsert(r, "原台词", "原台词") is None and q.count() == 0


def test_profile_validate_accepts_record_index_only_entry():
    ok = Profile.validate_obj(
        {
            "format_version": 1,
            "name": "x",
            "revision": 0,
            "entries": [
                {"file": "StoryData/P10210.json", "record_index": 3, "field_path": [{"k": "content"}], "value": "v"}
            ],
        }
    )
    assert ok == []
    # 既没有 id 也没有 record_index → 定位不到，必须报错
    bad = Profile.validate_obj(
        {
            "format_version": 1,
            "name": "x",
            "revision": 0,
            "entries": [{"file": "StoryData/P10210.json", "field_path": [{"k": "content"}], "value": "v"}],
        }
    )
    assert any("record_index" in e for e in bad)


def test_walk_leaves_skips_enum_data():
    """枚举/条件值（如 "(800101, VERY_HIGH), (800102, HIGH)"）不是可编辑文本，不进索引。"""
    record = {"id": 36, "teller": "堂吉诃德", "dialog": "请派吾上阵！",
              "usage": "(800101, VERY_HIGH), (800102, VERY_HIGH), (800104, HIGH)"}
    assert [t for _fp, t in walk_leaves(record)] == ["堂吉诃德", "请派吾上阵！"]
    assert is_data_value("(800101, VERY_HIGH)") and is_data_value("(1, A), (2, B_C)")
    assert not is_data_value("请派吾上阵！") and not is_data_value("VERY_HIGH")
    assert not is_data_value("(这是一句普通台词)") and not is_data_value("")
