"""带真实窗口（非 offscreen）点一遍：真人点击路径 + 真实绘制，抓原生崩溃。

用真实零协包 + 临时数据目录（复制图鉴卡面），逐个点击顶部按钮 / 导航 / 图鉴卡片 / 筛选，
每步前打印（flush），进程若死掉，最后一行就是崩溃点。
"""
import os
import shutil
import sys
import traceback
from pathlib import Path

os.environ["DSH_NO_MODAL"] = "1"
os.environ.pop("QT_QPA_PLATFORM", None)  # 真窗口（原生绘制路径）
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from limbus_patcher.app_state import AppContext  # noqa: E402
from limbus_patcher.config import AppPaths  # noqa: E402
from limbus_patcher.ui import theme  # noqa: E402
from limbus_patcher.ui.codex_page import _Card  # noqa: E402
from limbus_patcher.ui.main_window import MainWindow  # noqa: E402

STEPS = int(os.environ.get("PROBE_STEPS", "400"))
TMP = ROOT / "data" / "tmp" / "probe_click"
shutil.rmtree(TMP, ignore_errors=True)
(TMP / "data" / "cache").mkdir(parents=True)
if (ROOT / "dist" / "data" / "portraits").is_dir():
    shutil.copytree(ROOT / "dist" / "data" / "portraits", TMP / "data" / "portraits")

app = QApplication.instance() or QApplication([])
theme.apply_theme(app)
ctx = AppContext(AppPaths.from_root(TMP))
ctx.set_game_dir("D:/SteamLibrary/steamapps/common/Limbus Company")
ctx.ensure_index()
win = MainWindow(ctx)
win.resize(1400, 900)
win.show()
app.processEvents()
win._index_ready()
app.processEvents()

n = 0


def mark(label: str) -> None:
    global n
    n += 1
    print(f"[{n:03d}] {label}", flush=True)
    if n > STEPS:
        raise SystemExit(0)


def click(widget, label: str, wait: float = 0.05) -> None:
    mark(label)
    try:
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    except Exception:  # noqa: BLE001
        print("  (click 失败)", traceback.format_exc(limit=2), flush=True)
        return
    QTest.qWait(int(wait * 1000))


try:
    # 顶部三个页面按钮
    click(win.enemy_btn_top, "顶部：敌方图鉴")
    page = win.enemy_codex_page
    for i, card in enumerate(page.findChildren(_Card)[:6]):
        click(card, f"敌方图鉴卡片 #{i}")
        QTest.qWait(120)
        click(win.enemy_btn_top, "回到敌方图鉴")
    for name in ("chapter_combo", "enemy_combo", "danger_combo"):
        combo = getattr(page, name, None)
        if combo is None:
            continue
        for i in range(min(combo.count(), 4)):
            mark(f"{name} → {i}")
            combo.setCurrentIndex(i)
            QTest.qWait(120)
    click(win.codex_btn_top, "顶部：人格图鉴")
    codex = win.codex_page
    for i, card in enumerate(codex.findChildren(_Card)[:4]):
        click(card, f"人格图鉴卡片 #{i}")
        QTest.qWait(150)
        click(win.codex_btn_top, "回到人格图鉴")
    click(win.script_btn_top, "顶部：剧本模式")
    QTest.qWait(300)
    click(win.ops_btn, "顶部：操作菜单")
    win.ops_menu.close()

    # 左侧导航逐个点
    nav = win.nav
    tree = getattr(nav, "tree", None) or getattr(nav, "list", None)
    if tree is not None:
        try:
            count = tree.topLevelItemCount() if hasattr(tree, "topLevelItemCount") else 0
        except Exception:  # noqa: BLE001
            count = 0
        mark(f"导航顶层 {count} 项")
        for i in range(count):
            item = tree.topLevelItem(i)
            mark(f"导航展开 {item.text(0)}")
            item.setExpanded(True)
            QTest.qWait(60)
            for j in range(min(item.childCount(), 8)):
                child = item.child(j)
                mark(f"导航点击 {item.text(0)} / {child.text(0)}")
                tree.setCurrentItem(child)
                QTest.qWait(120)
    mark("结束（未崩溃）")
except SystemExit:
    pass
finally:
    print("清场…", flush=True)
    try:
        win.close()
    except Exception:  # noqa: BLE001
        pass
    shutil.rmtree(TMP, ignore_errors=True)
print(f"完成 {n} 步", flush=True)
