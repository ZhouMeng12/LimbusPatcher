"""离屏截图 + 像素校验：人格一览按赛季/获取方式分组的实际渲染效果（用真实零协包）。"""
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["DSH_NO_MODAL"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from limbus_patcher.app_state import AppContext  # noqa: E402
from limbus_patcher.config import AppPaths  # noqa: E402
from limbus_patcher.ui import theme  # noqa: E402
from limbus_patcher.ui.main_window import MainWindow  # noqa: E402

TMP = ROOT / "data" / "tmp" / "shot"
shutil.rmtree(TMP, ignore_errors=True)
app = QApplication.instance() or QApplication([])
theme.apply_theme(app)
ctx = AppContext(AppPaths.from_root(TMP))
ctx.set_game_dir("D:/SteamLibrary/steamapps/common/Limbus Company")
ctx.ensure_index()
win = MainWindow(ctx)
win.resize(1400, 900)
win.show()
win._index_ready()

out = ROOT / "data" / "tmp"
out.mkdir(parents=True, exist_ok=True)
panel = win.list_panel
for key, name in (("", "group_off"), ("season", "group_season"), ("acq", "group_acq")):
    win._on_nav_category("entities:personality")
    panel.group_combo.setCurrentIndex(panel.group_combo.findData(key))
    win.refresh_list()
    app.processEvents()
    panel.grab().save(str(out / f"{name}.png"))
    rows = panel.model.hits()
    print(f"[{name}] 行 {len(rows)} · {panel.count_label.text()}")
    print("   标题:", [v.header for v in rows if v.is_header][:6])

    # 像素校验：用 visualRect 精确定位标题行，取竖条与底色
    model = panel.model
    view = panel.view
    img = panel.grab().toImage()
    accent, hover = QColor(theme.ACCENT), QColor(theme.HOVER)
    heads = [i for i, v in enumerate(rows) if v.is_header]
    sampled = []
    for i in heads[:3]:
        r = view.visualRect(model.index(i, 0))
        left = view.viewport().mapTo(panel, QPoint(r.left() + 1, r.center().y()))
        mid = view.viewport().mapTo(panel, QPoint(r.center().x(), r.center().y()))
        sampled.append((i, img.pixelColor(left.x(), left.y()).name(),
                        img.pixelColor(mid.x(), mid.y()).name()))
    print(f"   像素：标题行 {len(heads)} 个 · 竖条/底色 {sampled}（期望 {accent.name()}/{hover.name()}）")
    if len(heads) > 1:  # 再滚到中间那个标题，确认非首行也画得对
        view.scrollTo(model.index(heads[1], 0), view.ScrollHint.PositionAtTop)
        app.processEvents()
        img2 = panel.grab().toImage()
        r = view.visualRect(model.index(heads[1], 0))
        left = view.viewport().mapTo(panel, QPoint(r.left() + 1, r.center().y()))
        mid = view.viewport().mapTo(panel, QPoint(r.center().x(), r.center().y()))
        print(f"   像素：滚动后第 {heads[1]} 行 → {img2.pixelColor(left.x(), left.y()).name()}"
              f"/{img2.pixelColor(mid.x(), mid.y()).name()}（{rows[heads[1]].header}）")
    heights = [view.itemDelegate().sizeHint(None, panel.model.index(i, 0)).height()
               for i in range(min(3, len(rows)))]
    heights = [view.itemDelegate().sizeHint(None, model.index(i, 0)).height()
               for i in range(min(3, len(rows)))]
    print(f"   行高 {heights}")

win.close()
shutil.rmtree(TMP, ignore_errors=True)
print("截图目录:", out)
