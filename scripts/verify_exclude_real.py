"""真实包验证：愚人节人格已从图鉴剔除，文本仍可搜可改。"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from limbus_patcher import codex  # noqa: E402
from limbus_patcher.app_state import AppContext  # noqa: E402
from limbus_patcher.config import AppPaths  # noqa: E402

ROOT = Path("data/tmp/excheck")
shutil.rmtree(ROOT, ignore_errors=True)
ctx = AppContext(AppPaths.from_root(ROOT))
ctx.set_game_dir("D:/SteamLibrary/steamapps/common/Limbus Company")
ctx.ensure_index()

rows = ctx.search.list_entities("personality")
keys = [r["entity_key"] for r in rows]
print("人格数:", len(rows), "（剔除前 198）")
print("愚人节还在吗:", [k for k in keys if k in {f"P:{i}" for i in range(400025, 400037)}] or "已全部剔除")
print("40501 仍在:", "P:40501" in keys)
roles = ctx.search.count_by_role()
print("角色条目:", {k: v for k, v in roles.items() if k.startswith(("identity", "ego"))})

# 文本还在：搜愚人节技能/被动
for term in ("我来正理", "心息团递"):
    hits = ctx.search.search(text=term, limit=5)
    print(f"搜「{term}」:", [(h.file, h.entity_key, h.role) for h in hits][:2])
    if hits:
        text, err = ctx.original_of(hits[0].ref)
        print("   原文:", text[:24] if text else err)

# 罪人卡片计数不再包含愚人节文件
ents_by_sinner = {r["sinner_code"]: 0 for r in rows}
for r in rows:
    ents_by_sinner[r["sinner_code"]] = ents_by_sinner.get(r["sinner_code"], 0) + 1
print("每罪人人格数:", ents_by_sinner)

# 某个正常人格不受影响
ent = codex.build_entity(Path(ctx.game_paths.llc_pack_dir), ctx.search.entity_summary("P:10101"))
print("P:10101 技能", len(ent.skills), "被动", len(ent.passives))
shutil.rmtree(ROOT, ignore_errors=True)
print("OK")
