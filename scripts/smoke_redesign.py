"""改版后的冒烟自检：构建主窗口并检查关键控件在位。"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DSH_NO_MODAL", "1")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from limbus_patcher.app_state import AppContext  # noqa: E402
from limbus_patcher.config import AppPaths  # noqa: E402
from limbus_patcher.ui import theme  # noqa: E402
from limbus_patcher.ui.main_window import MainWindow  # noqa: E402

app = QApplication.instance() or QApplication([])
for p in ("C:/Windows/Fonts/msyh.ttc",):
    if Path(p).is_file():
        QFontDatabase.addApplicationFont(p)
theme.apply_theme(app, theme.DEFAULT_THEME)

_LOG = ROOT / ".workbuddy" / "smoke.log"
_LOG.parent.mkdir(parents=True, exist_ok=True)
_buf: list[str] = []
_LOG.write_text("start\n", encoding="utf-8")


def log(*parts) -> None:
    line = " ".join(str(p) for p in parts)
    _buf.append(line)
    _LOG.write_text("start\n" + "\n".join(_buf) + "\n", encoding="utf-8")


tmp = Path(tempfile.mkdtemp(prefix="smoke-"))
game = tmp / "game"
shutil.copytree(ROOT / "tests" / "fixtures" / "game", game)
ctx = AppContext(AppPaths.from_root(tmp / "app"))
ctx.set_game_dir(str(game))
ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)

win = MainWindow(ctx, startup_backup=False)
win.resize(1460, 920)
win.show()
win._index_ready()
for _ in range(6):
    app.processEvents()

_LOG.write_text("start\n", encoding="utf-8")
log("brand logo:", win.brand_logo.size().width(), "x", win.brand_logo.size().height())
log("brand name:", win.brand_name.text())
log("profile   :", win.profile_chip.text())
log("crumb txt :", repr(win.crumb.text()[:40]))
log("crumb plain:", win._crumb)
log("theme btn :", win.theme_switch.text(), type(win.theme_switch).__name__)
log("status pill:", win.status_pill._text.text())
log("more menu items:", [a.text() for a in win.more_menu.actions() if not a.isSeparator()][:6])
log("ops alias :", win.script_btn_top.text(), "|", win.codex_btn_top.text(), "|", win.enemy_btn_top.text())
log("page tabs :", [b.text() for b in (win.page_codex, win.page_enemy, win.page_script)])
log("tabs in topbar:", all(b.parent() is win.topbar for b in (win.page_codex, win.page_enemy, win.page_script)))
log("tabs checkable:", all(b.isCheckable() for b in (win.page_codex, win.page_enemy, win.page_script)))
log("menu has pages:", any(a.text() in ("人格图鉴", "敌方图鉴", "剧本模式") for a in win.more_menu.actions()))
log("apply btn :", win.apply_btn.text(), win.apply_btn.height())

win._on_nav_category("main_story")
for _ in range(4):
    app.processEvents()
hits = win.list_panel.model._hits
log("hits:", len(hits))
if hits:
    win._on_hit_activated(hits[0])
    for _ in range(4):
        app.processEvents()
log("ref tabs  :", win.editor.ref_tab_zh.text(), "/", win.editor.ref_tab_en.text())
log("ref meta  :", win.editor.ref_meta.text()[:70])
log("baseline? :", win.editor.baseline_visible())
win.editor.set_baseline_visible(True)
log("baseline? :", win.editor.baseline_visible(), "en=", win.editor.baseline_edit.toPlainText())
win.editor.set_baseline_visible(False)
log("baseline? :", win.editor.baseline_visible())
log("compare splitter visible:", win.editor.compare_splitter.isVisible())
log("drawer width:", win.editor.drawer.width())
log("SMOKE OK")
