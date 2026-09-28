"""零协汉化包更新前后的处理（第十章切换用）。

背景：第十章原先零协没有 → 我们用「补译文件」补上。零协一旦更新出第十章，
**零协官方译文优先**（部署器已按记录级合并：同名文件只追加零协缺的 id），
但补译文件本身应该撤下来，避免界面/索引里出现两份、也避免术语打架。

用法：
    python scripts/llc_update.py snapshot        # 更新前：记录当前零协包清单（基线）
    python scripts/llc_update.py diff            # 更新后：看零协新增/改动/删除了什么
    python scripts/llc_update.py prune           # 撤销「零协已经覆盖」的补译文件（停用并从 data/supplement 移除）
    python scripts/llc_update.py sync            # 一键：prune + 重装两处补译文件 + 体检 + 术语对照
    python scripts/llc_update.py terms           # 只看术语对照（我们的旧译文 vs 零协新译文）

基线文件：data/llc_baseline.json（路径 → 大小/秒级 mtime/sha1 前 16 位）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import mt_files as mf  # noqa: E402
import translate_pack as tp  # noqa: E402

from limbus_patcher.supplement import SupplementPack  # noqa: E402

BASELINE = ROOT / "data" / "llc_baseline.json"
LLC = tp.ZH_STORY.parent                     # …/Lang/LLC_zh-CN
#: 第十章相关文件的特征（零协更新时会新增这些）
CH10_HINTS = ("a1c10", "c10", "S10", "RPGSystem/", "StageChapterText", "P10416", "P10816", "S9991B")


def inventory() -> dict:
    out = {}
    for p in sorted(LLC.rglob("*.json")):
        rel = p.relative_to(LLC).as_posix()
        data = p.read_bytes()
        st = p.stat()
        out[rel] = {"size": st.st_size, "mtime": int(st.st_mtime),
                    "sha": hashlib.sha1(data).hexdigest()[:16]}
    return out


def cmd_snapshot() -> int:
    inv = inventory()
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps({"pack": str(LLC), "count": len(inv), "files": inv},
                                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"已记录基线：{len(inv)} 个文件 → {BASELINE}")
    return 0


def _load_baseline() -> dict:
    if not BASELINE.is_file():
        print("还没有基线，先跑 snapshot（应该在零协更新**之前**跑）")
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8")).get("files") or {}


def _is_ch10(rel: str) -> bool:
    return any(h in rel for h in CH10_HINTS)


def cmd_diff() -> int:
    base = _load_baseline()
    now = inventory()
    if not base:
        return 1
    added = [r for r in now if r not in base]
    removed = [r for r in base if r not in now]
    changed = [r for r in now if r in base and now[r]["sha"] != base[r]["sha"]]
    for title, rows in (("新增", added), ("改动", changed), ("删除", removed)):
        ch10 = [r for r in rows if _is_ch10(r)]
        print(f"{title} {len(rows)} 个（其中第十章相关 {len(ch10)} 个）")
        for r in ch10[:40]:
            print(f"   ★ {r}")
        for r in [x for x in rows if x not in ch10][:10]:
            print(f"     {r}")
        if len(rows) > 50:
            print(f"     …另有 {len(rows) - 50} 个")
    return 0


def _supplement_pack(data_dir: Path) -> SupplementPack | None:
    pack = SupplementPack(data_dir)
    if not pack.root.is_dir():
        return None
    return pack


def _row_key(rec) -> str | None:
    """记录标识：老文件用 id，RPG/UI 这类用 key，少数用 code。

    只认 id 会把 key 型文件误判成「零协已完全覆盖」→ 整份补译被静默跳过。
    """
    if not isinstance(rec, dict):
        return None
    for k in ("id", "key", "code"):
        v = rec.get(k)
        if v is not None and str(v).strip():
            return f"{k}={v}"
    return None


def covers(ours: Path, rel: str) -> tuple[str, int]:
    """我们某个待装文件相对零协包的覆盖情况（none/partial/full）。"""
    llc = LLC / rel
    if not ours.is_file() or not llc.is_file():
        return "none", 0
    try:
        a = json.loads(ours.read_text(encoding="utf-8-sig"))
        b = json.loads(llc.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return "partial", 1
    rows_a = a.get("dataList") if isinstance(a, dict) else None
    rows_b = b.get("dataList") if isinstance(b, dict) else None
    if not isinstance(rows_a, list):
        return "partial", 1
    if not isinstance(rows_b, list):
        return "full", 0
    have = {k for k in (_row_key(r) for r in rows_b) if k}
    missing = []
    for r in rows_a:
        k = _row_key(r)
        if k is None or k not in have:
            missing.append(r)   # 没标识 / 零协没有 → 都算「我们要补的」
    return ("partial", len(missing)) if missing else ("full", 0)


def _coverage(rel: str) -> tuple[str, int]:
    """已装的补译文件相对零协包的覆盖情况（none/partial/full）。"""
    for base in (ROOT / "data" / "supplement", ROOT / "dist" / "data" / "supplement"):
        cand = base / rel
        if cand.is_file():
            return covers(cand, rel)
    return "none", 0


def cmd_prune(dry: bool = False) -> int:
    """撤销「零协已完全覆盖」的补译文件；零协仍缺记录的（partial）保留。"""
    total_pruned = 0
    for data_dir in (ROOT / "data", ROOT / "dist" / "data"):
        pack = _supplement_pack(data_dir)
        if pack is None:
            continue
        pruned, kept = [], []
        for f in pack.files():
            state, missing = _coverage(f.rel)
            if state == "full":
                pruned.append(f.rel)
                if not dry:
                    pack.remove(f.rel)
            elif state == "partial":
                kept.append((f.rel, missing))
        total_pruned += len(pruned)
        print(f"{data_dir}: 撤销 {len(pruned)} 个（零协已完全覆盖）"
              + ("（dry-run）" if dry else ""))
        for rel in pruned[:30]:
            print(f"   − {rel}")
        if len(pruned) > 30:
            print(f"   …另有 {len(pruned) - 30} 个")
        if kept:
            print(f"   保留 {len(kept)} 个（零协仍缺记录，走记录级合并）：")
            for rel, missing in kept[:10]:
                print(f"   + {rel}（补 {missing} 条）")
        if not dry:
            total, on = pack.count()
            print(f"   现状：补译文件 {on}/{total} 已启用")
    return 0


#: 这些叶子是程序内部键，不是译文，比对时跳过
_SKIP_LEAF = {"id", "key", "code", "model", "index", "nameKey", "textKey"}


def _leaves(node, prefix: str = "") -> dict[str, str]:
    """任意 JSON 结构 → {路径: 文本}（路径形如 /dataList/0/name）。"""
    out: dict[str, str] = {}
    stack = [(prefix, node)]
    while stack:
        path, cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                stack.append((f"{path}/{k}", v))
        elif isinstance(cur, list):
            for i, v in enumerate(cur):
                stack.append((f"{path}/{i}", v))
        elif isinstance(cur, str) and cur.strip():
            out[path] = cur.strip()
    return out


def cmd_terms() -> int:
    """术语对照：我们的旧译文 vs 零协新译文（同一条记录、同一字段路径）。

    记录标识用 id/key/code（RPG/UI 这类文件只有 key，老实现按 id 对会全部错位；
    文本用整棵结构的叶子路径对齐，因为 RPG 的正文在 texts[i].text 里、过场在 content 里）。
    """
    pairs: list[tuple[str, str, str, str]] = []          # (rel, 路径, 我们, 零协)
    gaps: list[tuple[str, str, str, str, str]] = []      # 零协缺记录 → 这几条真会进游戏
    per_file: dict[str, int] = {}
    for rel in mf.CH10_FILES + mf.RPG_FILES + [f"StoryData/{n}.json" for n in tp.STORY_FILES]:
        ours = (ROOT / "data" / "supplement" / rel)
        if not ours.is_file():
            continue
        llc = LLC / rel
        if not llc.is_file():
            continue
        try:
            a = json.loads(ours.read_text(encoding="utf-8-sig"))
            b = json.loads(llc.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        rows_a = a.get("dataList") if isinstance(a, dict) else None
        rows_b = b.get("dataList") if isinstance(b, dict) else None
        if not isinstance(rows_a, list) or not isinstance(rows_b, list):
            continue
        by_key: dict[str, dict] = {}
        for r in rows_b:
            k = _row_key(r)
            if k:
                by_key[k] = r
        for ra in rows_a:
            k = _row_key(ra)
            rb = by_key.get(k) if k else None
            covered = isinstance(rb, dict)
            if covered:
                la, lb = _leaves(ra), _leaves(rb)
                for path, va in la.items():
                    if path.rsplit("/", 1)[-1] in _SKIP_LEAF:
                        continue
                    vb = lb.get(path)
                    if vb is not None and vb != va:
                        pairs.append((rel, path, va, vb))
                        per_file[rel] = per_file.get(rel, 0) + 1
            elif k:
                # 零协没有这条记录 → 合并时整条追加进去，我们的译法会真的显示在游戏里
                for path, va in sorted(_leaves(ra).items()):
                    if path.rsplit("/", 1)[-1] in _SKIP_LEAF:
                        continue
                    gaps.append((rel, k, path, va, "(零协缺此记录)"))
    print(f"零协译文与我们的译文不同的字段：{len(pairs)} 处（{len(per_file)} 个仍在用的补译文件）")
    for rel, n in sorted(per_file.items(), key=lambda kv: -kv[1]):
        print(f"   {rel}: {n} 处")
    print(f"其中**会进游戏的**（零协缺的记录，共 {len({g[1] for g in gaps})} 条记录 / {len(gaps)} 个字段）：")
    for rel, k, path, ours, _ in gaps[:20]:
        print(f"   {rel} {k}{path}\n     我们：{ours[:70]}")
    for rel, path, ours, theirs in pairs[:20]:
        print(f"  {rel}{path}\n    我们：{ours[:60]}\n    零协：{theirs[:60]}")
    out = ROOT / "data" / "translate" / "out" / "零协第十章-术语对照.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 零协第十章译文 vs 我们的译文（逐字段对照）", "",
             "零协官方译文优先；本表用于把**仍在使用的**补译文件/术语表统一到零协口径。",
             f"共 {len(pairs)} 处差异，涉及 {len(per_file)} 个仍在用的补译文件；"
             f"另有 {len(gaps)} 处属于「零协缺的记录」（这些会真的进游戏，见文末）。", "",
             "## 一、零协已覆盖的记录（仅存档，游戏中显示零协官方译文）", ""]
    for rel, path, ours, theirs in pairs:
        lines += [f"- `{rel}`{path}", f"  - 我们：{ours}", f"  - 零协：{theirs}"]
    lines += ["", "## 二、零协缺的记录（我们会补进游戏，建议照零协口径改）", ""]
    for rel, k, path, ours, _ in gaps:
        lines += [f"- `{rel}` `{k}`{path}", f"  - 我们：{ours}"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"完整对照已写入 {out}")
    return 0


def _run(script: str, *args: str) -> None:
    proc = subprocess.run([PY, str(ROOT / "scripts" / script), *args], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = (proc.stdout or "").strip().splitlines()[-4:]
    print("  " + "\n  ".join(tail))


def cmd_sync() -> int:
    print("1) 撤销零协已覆盖的补译文件")
    cmd_prune()
    print("2) 重装补译文件（零协仍缺的才装）")
    _run("install_supplement.py")
    _run("install_supplement.py", "--data-dir", "dist/data")
    print("3) 体检")
    _run("verify_ch10.py", "--quiet")
    print("4) 学零协术语（第十章 + 基础表）")
    _run("learn_llc_terms.py", "--chapter", "10")
    print("5) 零协译文 vs 我们的译文 逐字段对照")
    cmd_terms()
    print("\n完成后：重启软件 → 点「应用到游戏」。零协已覆盖的文件会自动用官方译文（记录级合并）。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot")
    sub.add_parser("diff")
    p = sub.add_parser("prune")
    p.add_argument("--dry-run", action="store_true")
    sub.add_parser("terms")
    sub.add_parser("sync")
    args = ap.parse_args()
    if args.cmd == "snapshot":
        return cmd_snapshot()
    if args.cmd == "diff":
        return cmd_diff()
    if args.cmd == "prune":
        return cmd_prune(getattr(args, "dry_run", False))
    if args.cmd == "terms":
        return cmd_terms()
    return cmd_sync()


if __name__ == "__main__":
    raise SystemExit(main())
