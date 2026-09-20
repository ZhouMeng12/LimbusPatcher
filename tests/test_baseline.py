"""英语原文（英文基线）解析测试：只读、容错、不猜记录。"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from limbus_patcher import baseline
from limbus_patcher.patch import EntryRef

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def game(tmp_path) -> Path:
    dst = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", dst)
    baseline.clear_cache()
    yield dst
    baseline.clear_cache()


def base_dir(game: Path) -> Path:
    return game / "LimbusCompany_Data/Assets/Resources_moved/Localize/en"


def llc_dir(game: Path) -> Path:
    return game / "LimbusCompany_Data/Lang/LLC_zh-CN"


def ref(file="BattleKeywords.json", rid="AreaAtk", index=0, fields=(("desc",),)):
    return EntryRef(file=file, id=rid, record_index=index,
                    field_path=[{"k": f[0]} for f in fields])


def test_relpath_rules():
    assert baseline.baseline_relpaths("StoryData/S001B.json") == [
        "StoryData/EN_S001B.json", "StoryData/S001B.json"]
    assert baseline.baseline_relpaths("EN_AbDlg.json")[0] == "EN_AbDlg.json"
    assert baseline.baseline_relpaths("") == []


def test_baseline_langs(game):
    assert baseline.baseline_langs(base_dir(game).parent) == ["en"]
    assert baseline.baseline_langs(game / "nope") == []


def test_text_by_key_id(game):
    text, reason = baseline.baseline_text(base_dir(game), ref())
    assert reason is None and text == "Attacks 2 or more enemies at once."
    # name 字段
    text, reason = baseline.baseline_text(base_dir(game), ref(fields=(("name",),)))
    assert text == "Mass Attack" and reason is None


def test_missing_field_reports_reason(game):
    # 英文的 Enhancement 没有 name 字段
    text, reason = baseline.baseline_text(base_dir(game), ref(rid="Enhancement", index=1, fields=(("name",),)))
    assert text is None and reason == baseline.REASON_NO_FIELD
    # 同一条记录的 desc 有英文
    text, reason = baseline.baseline_text(base_dir(game), ref(rid="Enhancement", index=1))
    assert reason is None and text.startswith("Final power")


def test_index_fallback_only_when_no_key_id(game):
    """英文记录没有 KeyID 时按同下标取；两边都有 KeyID 却不相等时必须判定为无对应。"""
    # Egos 的英文记录没有 id → 按同下标兜底
    text, reason = baseline.baseline_text(base_dir(game),
                                         ref(file="Egos.json", rid=20101, index=0, fields=(("name",),)))
    assert reason is None and text == "Crew's Eye View".replace("Crew", "Crow")
    # 英文文件里有 KeyID 却对不上 → 不给英文，避免显示别的台词
    text, reason = baseline.baseline_text(base_dir(game),
                                         ref(file="BattleKeywords.json", rid="NoSuchId", index=0,
                                             fields=(("desc",),)))
    assert text is None and reason == baseline.REASON_NO_RECORD


def test_missing_file_and_missing_dir(game):
    text, reason = baseline.baseline_text(base_dir(game), ref(file="Skills_Ego_Personality-01.json"))
    assert text is None and reason == baseline.REASON_NO_FILE
    text, reason = baseline.baseline_text(game / "no-such-lang", ref())
    assert text is None and reason == baseline.REASON_NO_DIR
    text, reason = baseline.baseline_text(None, ref())
    assert text is None and reason == baseline.REASON_NO_DIR


def test_baseline_path_and_encoding(game):
    # 夹具的 EN_MainUIText.json 带 BOM，StoryData/EN_1D101A.json 不带：两种都要能读
    p = baseline.baseline_path(base_dir(game), "MainUIText.json")
    assert p is not None and p.name == "EN_MainUIText.json"
    text, reason = baseline.baseline_text(base_dir(game),
                                          ref(file="MainUIText.json", rid="clear_cache", index=0,
                                              fields=(("content",),)))
    assert reason is None and text == "Clear all caches"
    assert baseline.baseline_path(base_dir(game), "Nope.json") is None


def test_cache_returns_same_object_and_clears(game):
    r = ref()
    baseline.baseline_text(base_dir(game), r)
    key = str(baseline.baseline_path(base_dir(game), r.file))
    first = baseline._file_cache.get(key)
    baseline.baseline_text(base_dir(game), r)
    assert baseline._file_cache.get(key) is first  # 命中缓存
    baseline.clear_cache()
    assert baseline._file_cache == {}


def test_baseline_is_read_only(game):
    """跑一遍取值流程后，英文基线目录内容必须逐字节未变。"""
    def digest() -> str:
        h = hashlib.sha256()
        for p in sorted(base_dir(game).rglob("*")):
            if p.is_file():
                h.update(p.relative_to(base_dir(game)).as_posix().encode())
                h.update(p.read_bytes())
        return h.hexdigest()

    before = digest()
    for rel, rid, idx in (("BattleKeywords.json", "AreaAtk", 0),
                          ("StoryData/1D101A.json", 0, 0),
                          ("Egos.json", 20101, 0),
                          ("MainUIText.json", "clear_cache", 0)):
        baseline.baseline_text(base_dir(game), ref(file=rel, rid=rid, index=idx))
        baseline.baseline_text(base_dir(game), ref(file=rel, rid=rid, index=idx, fields=(("content",),)))
    assert digest() == before
