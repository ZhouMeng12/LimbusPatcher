"""用「用户真实数据目录的副本」启动，复现会话恢复（category=item + 敌方条目）时的崩溃。

只读原目录：先把 dist/data 复制到临时目录再跑。
"""
import os
import shutil
import sys
import traceback
from pathlib import Path

os.environ["DSH_NO_MODAL"] = "1"
os.environ.pop("QT_QPA_PLATFORM", None)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from limbus_patcher.app_state import AppContext  # noqa: E402
from limbus_patcher.config import AppPaths  # noqa: E402
from limbus_patcher.ui import theme  # noqa: E402
from limbus_patcher.ui.main_window import MainWindow  # noqa: E402

TMP = ROOT / "data" / "tmp" / "probe_session"
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
shutil.copytree(ROOT / "dist" / "data", TMP / "data")
print("已复制用户数据副本（含 config.json / 索引 / 图鉴卡面）", flush=True)

app = QApplication.instance() or QApplication([])
theme.apply_theme(app)
ctx = AppContext(AppPaths.from_root(TMP))
print("会话状态:", {k: ctx.config.ui.get(k) for k in ("category", "hit_key", "advanced_mode")
                    if isinstance(ctx.config.ui, dict)} if isinstance(ctx.config.ui, dict)
      else ctx.config.ui, flush=True)
print("game_dir:", ctx.config.game_dir, flush=True)
ctx.refresh_env()
print("环境:", ctx.env.llc_ok, ctx.env.issues and [i.message for i in ctx.env.issues], flush=True)

win = MainWindow(ctx)
win.resize(1400, 900)
win.show()
app.processEvents()
try:
    needs = not ctx.indexer.manifest_matches(Path(ctx.env.llc_pack_dir), ctx.baseline_dir)
    print("需要重建索引:", needs, flush=True)
    if needs:
        ctx.indexer.build(Path(ctx.env.llc_pack_dir), baseline_dir=ctx.baseline_dir)
    win._index_ready()
    app.processEvents()
    print("会话恢复后：分类 =", win._category,
          "| 当前条目 =", win._current_hit.ref.key() if win._current_hit else None, flush=True)
    print("列表行数:", len(win.list_panel.model.hits()), flush=True)
except Exception:  # noqa: BLE001
    print("!! 异常：", flush=True)
    traceback.print_exc()
print("存活检查：进程仍在运行 ✓", flush=True)
app.processEvents()
win.close()
shutil.rmtree(TMP, ignore_errors=True)
print("结束", flush=True)
