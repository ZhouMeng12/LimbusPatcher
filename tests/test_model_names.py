"""说话人兜底：c10p2 起过场文件没有 ``teller``，名字只在 ``model``（韩文角色键）里。

覆盖：
* ``load_model_names`` 的优先级（零协中文 > 本工具补充表 > 英文基线英文名）；
* ``TextSource.resolve`` 在 ``teller`` 为空时按 ``model`` 反查（这才是「全是旁白」的真凶）；
* ``speaker_of`` 的取值顺序；
* 自带的 ``scenario_model_names.json`` 结构合法——它是打包进 exe 的资源，
  写错一个字符不会报错，只会静默退化成旁白，所以在这里拦。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from limbus_patcher.season import package_data_dir
from limbus_patcher.textsource import (
    OVERRIDE_NAME,
    TextSource,
    load_model_names,
    speaker_of,
)

CODES_NAME = "ScenarioModelCodes-AutoCreated.json"


def _write_codes(dir_path: Path, payload: dict[str, str], en: bool = False) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    name = f"EN_{CODES_NAME}" if en else CODES_NAME
    path = dir_path / name
    path.write_text(json.dumps(
        {"dataList": [{"id": k, "name": v} for k, v in payload.items()]},
        ensure_ascii=False), encoding="utf-8")
    return path


# ----------------------------------------------------------- load_model_names

def test_零协中文优先于英文基线(tmp_path):
    llc = tmp_path / "llc"
    en = tmp_path / "en"
    _write_codes(llc, {"오티스": "奥提斯"}, en=False)
    _write_codes(en, {"오티스": "Outis"}, en=True)

    table = load_model_names([llc, en])
    assert table["오티스"] == "奥提斯"


def test_英文基线在零协缺表时兜底(tmp_path):
    llc = tmp_path / "llc"
    en = tmp_path / "en"
    llc.mkdir()
    _write_codes(en, {"오티스": "Outis"}, en=True)

    assert load_model_names([llc, en])["오티스"] == "Outis"


def test_补充表能补零协查不到的键(tmp_path):
    """补充表（内置）优先级在英文基线之上、零协之下。"""
    llc = tmp_path / "llc"
    en = tmp_path / "en"
    _write_codes(llc, {"오티스": "奥提斯"}, en=False)
    _write_codes(en, {"뷔페어린이": "Pwie"}, en=True)

    table = load_model_names([llc, en])
    assert table["오티스"] == "奥提斯"
    assert table["뷔페어린이"] == "普伊"      # 英文的 Pwie 被中文补充表盖上


def test_空目录与坏文件都不抛异常(tmp_path):
    assert load_model_names([])  # 至少有内置补充表
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / CODES_NAME).write_text("{ 不是 JSON", encoding="utf-8")
    load_model_names([bad])      # 不该抛


# ------------------------------------------------------------- TextSource

def test_过场文件没有teller时按model取说话人(tmp_path):
    """c10p2 真凶：teller 为空 + model 有值 → 以前退化成旁白。"""
    game = tmp_path / "game"
    llc = game / "llc"
    codes = llc
    _write_codes(codes, {"오티스": "奥提斯", "잔느": "让娜"})
    story = llc / "StoryData"
    story.mkdir(parents=True)
    (story / "S1019B.json").write_text(json.dumps({"dataList": [
        {"id": 0, "model": "오티스", "place": "3F 走廊", "content": "……没有人——"},
        {"id": 1, "model": "잔느", "content": "我并非西西弗百货的顾客。"},
        {"id": 2, "model": None, "content": "纯叙述句。"},
        {"id": 3, "model": "오티스", "teller": "旁白", "content": "teller 优先。"},
    ]}, ensure_ascii=False), encoding="utf-8")

    src = TextSource.detect(llc, None)
    assert src.resolve("StoryData/S1019B.json", 0)[1] == "奥提斯"
    assert src.resolve("StoryData/S1019B.json", 1)[1] == "让娜"
    assert src.resolve("StoryData/S1019B.json", 2)[1] is None
    assert src.resolve("StoryData/S1019B.json", 3)[1] == "旁白"


def test_报错不改文本只补说话人(tmp_path):
    game = tmp_path / "game"
    llc = game / "llc"
    _write_codes(llc, {"단테": "但丁"})
    story = llc / "StoryData"
    story.mkdir(parents=True)
    (story / "S1.json").write_text(json.dumps({"dataList": [
        {"id": 0, "model": "단테", "content": "原文不动。"},
    ]}, ensure_ascii=False), encoding="utf-8")

    text, speaker, _title = TextSource.detect(llc, None).resolve("StoryData/S1.json", 0)
    assert text == "原文不动。"
    assert speaker == "但丁"


# ---------------------------------------------------------------- speaker_of

def test_speaker_of取值顺序(tmp_path):
    """teller / speaker 优先；都为空时按 model 反查（这里用显式目录，不依赖全局登记）。"""
    _write_codes(tmp_path, {"오티스": "奥提斯"})
    dirs = [tmp_path]

    assert speaker_of({"teller": "广播", "model": "오티스"}, dirs) == "广播"
    assert speaker_of({"speaker": "罗佳", "model": "오티스"}, dirs) == "罗佳"
    assert speaker_of({"teller": "   ", "model": "오티스"}, dirs) == "奥提斯"
    assert speaker_of({"teller": "", "model": ""}, dirs) is None
    assert speaker_of({}, dirs) is None
    assert speaker_of({"teller": "  ", "model": "查不到的键"}, dirs) is None


def test_speaker_of可用自带补充表(tmp_path):
    """补充表是包内资源，不依赖游戏目录。"""
    assert speaker_of({"model": "뷔페어린이"}) == "普伊"


# ------------------------------------------------- 内置补充表（打包资源）

def test_内置补充表结构合法():
    path = package_data_dir() / OVERRIDE_NAME
    assert path.is_file(), f"补充表不在包内：{path}"
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    assert isinstance(obj, dict)
    entries = {k: v for k, v in obj.items() if not k.startswith("_")}
    assert entries, "补充表不能是空的"
    for key, value in entries.items():
        assert isinstance(key, str) and key.strip(), f"键不合法：{key!r}"
        assert isinstance(value, str) and value.strip(), f"{key} 的名字为空"
    # c10p2 新角色：零协对照表里还没有，漏一个就会在那段剧情里退化成旁白
    for key in ("과거뫼르소", "법정 경위", "뷔페어른", "뷔페어린이",
                "뷔페어린이신발", "뷔페어린이옷", "카르멘"):
        assert key in entries, f"补充表缺 {key}"


@pytest.mark.parametrize("key, expected", [
    ("뷔페어른", "自助餐"),
    ("뷔페어린이", "普伊"),
    ("카르멘", "卡门"),
])
def test_内置补充表关键译名(key, expected):
    assert speaker_of({"model": key}) == expected
