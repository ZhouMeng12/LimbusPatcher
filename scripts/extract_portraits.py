"""从游戏 Unity 资源里抽取人格 / E.G.O 头像（离线只读，不动游戏文件）。

原理：LimbusCompany_Data 下的 *.assets 里有 Sprite，其名字就是人格/EGO 的 id（如 10310）。
用 UnityPy 读取 Sprite（自动从图集裁切），按 id 存成 PNG：
    <out>/identity/<人格id>.png     （id 以 1 或 4 开头）
    <out>/ego/<EGO id>.png          （id 以 2 开头）

用法：
    python scripts/extract_portraits.py [--game <游戏目录>] [--out data/portraits] [--force]
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_GAME = Path(r"D:/SteamLibrary/steamapps/common/Limbus Company")
# 头像命名（优先级从高到低）：纯 id > 正常头像 > 觉醒头像 > EGO CG
NAME_RULES = [
    (re.compile(r"^(\d{5}|\d{6})$"), 0),
    (re.compile(r"^(\d{5})_normal_profile$"), 1),
    (re.compile(r"^(\d{5})_gacksung_profile$"), 2),
    (re.compile(r"^(\d{5})_cg$"), 3),
    (re.compile(r"^(\d{5})_gacksung$"), 4),
]


_ANY_ID_RE = re.compile(r"^(\d{5}|\d{6})_")


def match_portrait(name: str) -> tuple[str, int] | None:
    """Sprite 名 → (实体 id, 优先级)；不是头像返回 None。

    优先级 0：纯 id（最干净）；1-4：常见后缀；9：任何 <id>_xxx（兜底，如 20109_Yisang_DeadButterfly）。
    """
    for pattern, rank in NAME_RULES:
        m = pattern.match(name)
        if m:
            return m.group(1), rank
    m = _ANY_ID_RE.match(name)
    if m:
        return m.group(1), 9
    return None


def asset_files(game: Path) -> list[Path]:
    data = game / "LimbusCompany_Data"
    out = sorted(p for p in data.glob("*.assets") if p.is_file())
    out += sorted(p for p in data.glob("level*") if p.is_file())
    return out


def known_entity_ids(db_path: Path) -> set[str]:
    """从索引库读实体 id（人格 + EGO），避免抽出无关素材。"""
    import sqlite3

    if not Path(db_path).is_file():
        return set()
    try:
        con = sqlite3.connect(str(db_path))
        rows = con.execute("SELECT entity_id FROM entities").fetchall()
        con.close()
    except sqlite3.Error:
        return set()
    return {str(r[0]) for r in rows if r and r[0] is not None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", type=Path, default=DEFAULT_GAME)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "portraits")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    try:
        import UnityPy
    except ImportError:
        print("需要 UnityPy：pip install UnityPy")
        return 2

    out_identity = args.out / "identity"
    out_ego = args.out / "ego"
    out_identity.mkdir(parents=True, exist_ok=True)
    out_ego.mkdir(parents=True, exist_ok=True)

    saved = skipped = 0
    seen: set[str] = set()
    best_rank: dict[str, int] = {}
    known = known_entity_ids(args.out.parent.parent / "data" / "cache" / "index.sqlite")
    print(f"  已知实体 {len(known)} 个" if known else "  （未读到索引，按命名规则全收）")
    t0 = time.time()
    for path in asset_files(args.game):
        try:
            env = UnityPy.load(str(path))
        except Exception as exc:  # noqa: BLE001
            print(f"  跳过 {path.name}：{exc}")
            continue
        found = 0
        for obj in env.objects:
            if obj.type.name != "Sprite":
                continue
            try:
                sprite = obj.read()
                name = str(getattr(sprite, "m_Name", ""))
            except Exception:  # noqa: BLE001
                continue
            matched = match_portrait(name)
            if not matched:
                continue
            entity_id, rank = matched
            if known and entity_id not in known:
                continue
            if name in seen or rank >= best_rank.get(entity_id, 99):
                continue
            target = out_ego if entity_id.startswith("2") else out_identity
            dest = target / f"{entity_id}.png"
            if dest.is_file() and not args.force and rank > 0:
                best_rank[entity_id] = rank
                seen.add(name)
                skipped += 1
                continue
            try:
                image = sprite.image
                image.save(dest)
            except Exception:  # noqa: BLE001
                continue
            seen.add(name)
            best_rank[entity_id] = rank
            saved += 1
            found += 1
        print(f"  {path.name}: 新增 {found} 张")
    print(f"完成：新增 {saved} 张，跳过已存在 {skipped} 张，用时 {time.time() - t0:.1f}s → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
