"""第十章译稿质量门（回归测试）：防止「方括号 id 被翻译 → 游戏里显示 UNKNOWN / 口口」、
空字段、韩文残留再次混进补译文件。

这些测试直接读 `data/translate/files/**` 与游戏英文基线；找不到游戏目录就跳过。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import mt_files as mf  # noqa: E402
import translate_pack as tp  # noqa: E402
import repair_ch10 as rc  # noqa: E402

HANGUL = re.compile(r"[\uac00-\ud7af]")
ID_FIELDS = rc.ID_FIELDS
DATA_FILES = mf.CH10_FILES + mf.RPG_FILES


def _pairs(rel: str):
    path, en = rc._resolve(rel)
    if path is None or en is None or not Path(en).is_file():
        pytest.skip(f"缺少文件或英文基线：{rel}")
    return (json.loads(Path(path).read_text(encoding="utf-8-sig")),
            json.loads(Path(en).read_text(encoding="utf-8-sig")))


@pytest.mark.parametrize("rel", DATA_FILES)
def test_没有空字段(rel: str) -> None:
    """英文基线有内容、译文却是空串 → 游戏里就是一片空白。"""
    zh, en = _pairs(rel)
    empty: list = []

    def walk(z, e, path: tuple = ()) -> None:
        if isinstance(z, dict) and isinstance(e, dict):
            for k, v in z.items():
                if k not in e:
                    continue
                if isinstance(v, str):
                    if v.strip() == "" and isinstance(e[k], str) and e[k].strip():
                        empty.append(path + (k,))
                else:
                    walk(v, e[k], path + (k,))
        elif isinstance(z, list) and isinstance(e, list):
            for i, v in enumerate(z):
                if i >= len(e):
                    break
                if isinstance(v, str):
                    if v.strip() == "" and isinstance(e[i], str) and e[i].strip():
                        empty.append(path + (i,))
                else:
                    walk(v, e[i], path + (i,))

    walk(zh, en)
    assert not empty, f"{rel} 有 {len(empty)} 处空译文，例如 {empty[:5]}"


@pytest.mark.parametrize("rel", DATA_FILES)
def test_说明字段里的方括号按英文原样(rel: str) -> None:
    """desc 等字段里的 [X] 是游戏内部效果 id：翻成中文游戏里会显示 UNKNOWN/口口。"""
    zh_map = rc.en_strings(_pairs(rel)[0], {})
    en_map = rc.en_strings(_pairs(rel)[1], {})
    bad: list = []
    for path, text in zh_map.items():
        src = en_map.get(path)
        field = path[-1] if path else ""
        if not isinstance(src, str) or field not in ID_FIELDS:
            continue
        want = [b for b in rc.BRACKET.findall(src) if not HANGUL.search(b)]
        have = [b for b in rc.BRACKET.findall(text) if not HANGUL.search(b) and "未使用" not in b]
        if want != have:
            bad.append((path, want, have))
    assert not bad, f"{rel} 有 {len(bad)} 处方括号 id 与英文基线不一致：{bad[:3]}"


@pytest.mark.parametrize("rel", DATA_FILES)
def test_不漏韩文(rel: str) -> None:
    zh_map = rc.en_strings(_pairs(rel)[0], {})
    en_map = rc.en_strings(_pairs(rel)[1], {})
    bad = [p for p, t in zh_map.items() if HANGUL.search(t) and not HANGUL.search(en_map.get(p) or "")]
    assert not bad, f"{rel} 有 {len(bad)} 处韩文残留：{bad[:5]}"


@pytest.mark.parametrize("name", list(tp.STORY_FILES))
def test_剧情行不漏翻(name: str) -> None:
    path = tp.ZH_DIR / f"{name}.json"
    if not path.is_file():
        pytest.skip(f"没有 {name} 的译文")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    lines = data.get("lines") or {}
    src = tp.records(name)
    need = [tp.line_key(rec, i) for i, rec in enumerate(src)
            if str(rec.get("content") or rec.get("text") or "").strip()]
    missing = [k for k in need if k not in lines]
    assert not missing, f"{name} 少了 {len(missing)} 行译文：{missing[:5]}"
    bad = [k for k, v in lines.items() if not str(v).strip()]
    assert not bad, f"{name} 有空行：{bad[:5]}"


def test_补译文件与译稿一致() -> None:
    """装好的 supplement 必须和 data/translate/files 同步（不然游戏里跑的还是旧译文）。"""
    sup = ROOT / "data" / "supplement"
    if not sup.is_dir():
        pytest.skip("还没装补译文件")
    diff: list = []
    for rel in mf.RPG_FILES + mf.CH10_FILES:
        src = mf.OUT / rel
        dst = sup / rel
        if not src.is_file() or not dst.is_file():
            continue
        if src.read_bytes() != dst.read_bytes():
            diff.append(rel)
    assert not diff, f"补译文件与译稿不一致，需要重装：{diff[:5]}"
