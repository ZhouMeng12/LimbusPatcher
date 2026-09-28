"""零协更新后的收尾：把「仍会进游戏」的补译记录（零协缺的那些）对齐零协口径。

零协第十章（含 c10p2）已经出全 → 我们的补译文件基本都被撤销，只剩 5 个尚有
零协缺失记录的。这 5 个里只有「零协缺的记录」会真的进游戏（记录级合并），
所以只改这些记录：

1) 专名照零协同文件里的用词（同 EN 说话人 → 零协译名）：
   Palette 帕莱特→调色板、Needlekin Laborer 劳作的针怪→针族工人、
   Queueing Customer 排队的顾客→正在排队的客人、Putty 普蒂→油灰；
2) 标点统一：`(临时)`/`(暂时)`/`（暂时）`→`（临时）`，`！ ` 去掉多余空格，
   句首/句尾的单个 `…`→`……`（词中的 `房…间` 这种不动）。

用法：
    python scripts/ch10p2_gap_fixups.py            # 预览
    python scripts/ch10p2_gap_fixups.py --apply    # 写入（files/ + 两处 supplement）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from limbus_patcher.textsource import record_id_of  # noqa: E402

LLC = Path("D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data/Lang/LLC_zh-CN")
SUP_DIRS = [ROOT / "data" / "supplement", ROOT / "dist" / "data" / "supplement"]
SRC_DIRS = [ROOT / "data" / "translate" / "files", ROOT / "data" / "translate" / "out" / "zh"]
RECORD_ID_KEYS = ("id", "key", "code")

#: 专名（零协同文件里的实际用词；顺序敏感：先长后短）
NAMES = [("劳作的针怪2", "针族工人2"), ("劳作的针怪", "针族工人"),
         ("帕莱特", "调色板"), ("排队的顾客", "正在排队的客人"), ("普蒂", "油灰")]
#: 状态标记：零协对同一处 `(임시)` 的处理是**直接删掉**（官方译文里没有「临时」）
_TEMP = re.compile(r"[ \t]*[（(]\s*(?:临时|暂时)\s*[)）][ \t]*")
_WORD = re.compile(r"[\w\u4e00-\u9fff]")


def _fix_dots(text: str) -> str:
    """单个 `…` → `……`；断裂招牌那种（含 `→` 的 `房…间`）整句保持原样。"""
    if "→" in text:
        return text
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "…":
            if i + 1 < len(text) and text[i + 1] == "…":
                out.append("……")
                i += 2
                continue
            out.append("……")
            i += 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def tidy(text: str) -> str:
    out = text
    for a, b in NAMES:
        out = out.replace(a, b)
    out = _TEMP.sub("", out)                       # （临时）/（暂时）→ 删
    out = re.sub(r"！[ \t]+", "！", out)
    out = _fix_dots(out)
    out = re.sub(r"\[未使用][ \t]*", "[未使用] ", out)
    return out


def _rows(path: Path) -> list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")).get("dataList")
    except (OSError, json.JSONDecodeError):
        return None


def _fix(node, changes: list):
    """就地改一条记录里所有字符串叶子。"""
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if isinstance(v, str):
                new = tidy(v)
                if new != v:
                    changes.append((v, new))
                    node[k] = new
            else:
                _fix(v, changes)
    elif isinstance(node, list):
        for v in node:
            _fix(v, changes)


def process(path: Path, rel: str, llc_ids: set | None, apply: bool, label: str) -> int:
    """只改「零协缺的记录」；llc_ids 为 None 时改全部（补译文件不再被零协覆盖的情形）。"""
    if not path.is_file():
        return 0
    rows = _rows(path)
    if not isinstance(rows, list):
        return 0
    changes: list = []
    n_rec = 0
    for rec in rows:
        if not isinstance(rec, dict):
            continue
        rid = record_id_of(rec)
        if llc_ids is not None and rid is not None and rid in llc_ids:
            continue                                  # 零协有这条 → 官方译文优先，别动
        before = len(changes)
        _fix(rec, changes)
        if len(changes) > before:
            n_rec += 1
    if changes:
        print(f"{label} {path.relative_to(ROOT).as_posix()}：{len(changes)} 处 / {n_rec} 条记录")
        for a, b in changes[:6]:
            print(f"    - {a[:70]}\n    + {b[:70]}")
        if len(changes) > 6:
            print(f"    …另有 {len(changes) - 6} 处")
        if apply:
            raw = path.read_text(encoding="utf-8-sig")
            indent = 1 if raw.count("\n") > 3 else None
            path.write_text(json.dumps({"dataList": rows}, ensure_ascii=False, indent=indent) + "\n",
                            encoding="utf-8")
    return len(changes)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    # 仍在用的补译文件（零协缺记录的）
    rels = sorted(p.relative_to(ROOT / "data" / "supplement").as_posix()
                  for p in (ROOT / "data" / "supplement").rglob("*.json")
                  if p.name != "manifest.json")
    if not rels:
        print("data/supplement 里没有补译文件（零协已全覆盖），无事可做")
        return 0
    total = 0
    for rel in rels:
        llc_rows = _rows(LLC / rel) or []
        llc_ids = {record_id_of(r) for r in llc_rows if isinstance(r, dict)}
        llc_ids.discard(None)
        name = Path(rel).name
        for root in SRC_DIRS:                     # 源头（install_supplement 从这里取）
            cand = root / rel
            if not cand.is_file() and root.name == "zh":
                cand = root / name
            total += process(cand, rel, llc_ids, args.apply, "源")
        for root in SUP_DIRS:                     # 已装好的补译文件（两个数据目录）
            total += process(root / rel, rel, llc_ids, args.apply, "补译")
    print(f"合计 {total} 处" + ("" if args.apply else "（预览，未写入；加 --apply 生效）"))
    if args.apply and total:
        print("下一步：python scripts/install_supplement.py && "
              "python scripts/install_supplement.py --data-dir dist/data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
