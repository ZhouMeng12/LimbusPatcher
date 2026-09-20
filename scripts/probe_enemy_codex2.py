"""用真实零协包驱动「敌方图鉴」（离屏）：分组 → 三级详情 → 全实体数据层，找崩溃点。

只读：临时数据目录，不动 dist/data 与真实方案。
"""
import os
import shutil
import sys
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["DSH_NO_MODAL"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from limbus_patcher import enemy_codex  # noqa: E402
from limbus_patcher.app_state import AppContext  # noqa: E402
from limbus_patcher.config import AppPaths  # noqa: E402
from limbus_patcher.ui import theme  # noqa: E402
from limbus_patcher.ui.main_window import MainWindow  # noqa: E402

TMP = ROOT / "data" / "tmp" / "probe_enemy"
shutil.rmtree(TMP, ignore_errors=True)
(TMP / "data" / "cache").mkdir(parents=True)
USE_PACKAGED = "--packaged" in sys.argv   # 用打包版那份索引（不重建）
if USE_PACKAGED:
    shutil.rmtree(TMP, ignore_errors=True)
    shutil.copytree(ROOT / "dist" / "data", TMP / "data")
else:
    if (ROOT / "dist" / "data" / "portraits").is_dir():
        shutil.copytree(ROOT / "dist" / "data" / "portraits", TMP / "data" / "portraits")
    for name, sub in (("season_map.json", "cache"), ("enemy_map.json", "cache"),
                      ("category_rules.json", "")):
        src = (ROOT / "dist" / "data" / sub / name) if sub else (ROOT / "dist" / "data" / name)
        if src.is_file():
            shutil.copy2(src, TMP / "data" / sub / name)

ERRORS: list[tuple[str, str]] = []


def step(name, fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception:  # noqa: BLE001
        tb = traceback.format_exc()
        ERRORS.append((name, tb))
        print("  [CRASH] " + name)
        print(tb)
        return None


app = QApplication.instance() or QApplication([])
theme.apply_theme(app)
ctx = AppContext(AppPaths.from_root(TMP))
ctx.set_game_dir("D:/SteamLibrary/steamapps/common/Limbus Company")
ctx.ensure_index()
win = MainWindow(ctx)
win.resize(1400, 900)
win.show()
win._index_ready()
page = win.enemy_codex_page
win.open_enemy_codex()

maps = ctx.maps.enemy_map.get("enemies", {})
with_dims = sum(1 for v in maps.values() if isinstance(v, dict) and v.get("dimensions"))
print(f"敌方映射 {len(maps)} 条，其中带 dimensions 的 {with_dims} 条")

print("\nA. 分组页 + 二级列表 + 筛选")
step("groups", page._show_groups)
group_keys = list(page._group_counts())
for g in group_keys:
    step(f"group {g}", page._show_entities, g)
    for combo_name in ("chapter_combo", "enemy_combo", "danger_combo"):
        combo = getattr(page, combo_name, None)
        if combo is None:
            continue
        n = combo.count()
        for i in range(n):
            step(f"{g}/{combo_name}#{i}",
                 lambda c=combo, k=i: (c.setCurrentIndex(k), page._rebuild_entity_list()))

print("\nB. 三级详情（前 20 个敌方实体）")
enemies = ctx.search.list_entities("enemy")
print("敌方实体数:", len(enemies))
for e in enemies[:20]:
    step(f"detail {e['entity_key']}", page._show_entity, e["entity_key"])

print("\nC. 数据层：全部敌方实体 build_enemy")
llc = Path(ctx.game_paths.llc_pack_dir)
bad = 0
for e in enemies:
    summary = ctx.search.entity_summary(e["entity_key"])
    if not summary:
        continue
    if step(f"build {e['entity_key']}", enemy_codex.build_enemy, llc, summary) is None:
        bad += 1
        if bad >= 3:
            break

print("\n崩溃", len(ERRORS), "处")
for name, tb in ERRORS[:4]:
    print(f"===== {name} =====\n{tb}")
win.close()
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if ERRORS else 0)
