"""剧情文件里的元数据字段（place 场景名 / title 称号 / teller 说话人）翻译。

剧情正文已译；这些字段是屏幕上显示的场景名与说话人标签，之前留了英文。
做法同 mt_translate：术语与标签占位符保护 → Bing → 填回。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import mt_translate as mt  # noqa: E402
import translate_pack as tp  # noqa: E402

FIELDS = ("place", "title", "teller")
LATIN = __import__("re").compile(r"[A-Za-z]{3,}")


def targets() -> list[tuple[str, str, str, str]]:
    """[(文件, 记录 id 键, 字段, 原值)]。"""
    out = []
    for name in tp.STORY_FILES:
        path = tp.ZH_DIR / f"{name}.json"
        if not path.is_file():
            continue
        lines = json.loads(path.read_text(encoding="utf-8")).get("lines") or {}
        meta = json.loads(path.read_text(encoding="utf-8")).get("meta") or {}
        for idx, r in enumerate(tp.records(name)):
            if not isinstance(r, dict):
                continue
            key = tp.line_key(r, idx)
            for f in FIELDS:
                v = str(r.get(f) or "")
                if v and LATIN.search(v) and "???" not in v and v not in ("Announcement",):
                    out.append((name, key, f, v))
    return out


def main() -> int:
    terms = mt.term_map()
    items = targets()
    print(f"待译元数据 {len(items)} 处")
    if not items:
        return 0
    outs, problems = [], []
    for start in range(0, len(items), mt.CHUNK):
        chunk = items[start:start + mt.CHUNK]
        masked, maps = [], []
        for _n, _k, _f, text in chunk:
            m, mapping = mt.protect(text, terms)
            masked.append(m)
            maps.append(mapping)
        raw = mt.gt("\n".join(masked))
        parts = [p.strip() for p in raw.split("\n") if p.strip()] if raw else []
        if len(parts) == len(chunk):
            outs.extend(mt.normalize_zh(mt.restore(p, m)) for p, m in zip(parts, maps))
        else:
            problems.append(f"{start}~{start + len(chunk)}: 整批失败，逐条重试")
            for masked_line, mapping in zip(masked, maps):
                outs.append(mt.normalize_zh(mt.restore(mt.gt(masked_line) or "", mapping)))
                time.sleep(mt.THROTTLE)
        time.sleep(mt.THROTTLE)

    by_file: dict[str, dict] = {}
    for (name, key, field, _v), zh in zip(items, outs):
        by_file.setdefault(name, {}).setdefault(key, {})[field] = zh
    for name, mapping in by_file.items():
        path = tp.ZH_DIR / f"{name}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data.setdefault("meta", {})
        for key, fields in mapping.items():
            meta.setdefault(key, {}).update(fields)
            # teller/title 若原本就在 lines 结构外，这里靠 merge 写入；顺带把 '???' 统一成中文问号
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {name}: {sum(len(v) for v in mapping.values())} 处")
    if problems:
        print("问题：", problems[:3])
    print("下一步：python scripts/translate_pack.py merge <文件>（或 scripts/finalize_ch10.py）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
