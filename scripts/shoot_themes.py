"""给三套主题各出一张真机截图（离屏渲染，不需要显示器）。

用法：
    DSH_NO_MODAL=1 LIMBUS_PATCHER_HEADLESS=1 QT_QPA_PLATFORM=offscreen \\
        .venv/Scripts/python.exe scripts/shoot_themes.py [输出目录]

产出：shot-bus.png / shot-mini-dark.png / shot-mini-light.png
（外加每套主题的顶栏特写 shot-<theme>-topbar.png）
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DSH_NO_MODAL", "1")
os.environ.setdefault("LIMBUS_PATCHER_HEADLESS", "1")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from limbus_patcher.app_state import AppContext  # noqa: E402
from limbus_patcher.config import AppPaths  # noqa: E402
from limbus_patcher.ui import theme  # noqa: E402
from limbus_patcher.ui.main_window import MainWindow  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "game"

# 离屏平台默认不带字体（Qt6 起不再随包附字体），中文会全渲染成豆腐块。
# 显式注册系统字体，让截图里的中文正常显示。
_FONT_CANDIDATES = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/Deng.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
)


def _register_fonts() -> list[str]:
    loaded = []
    for path in _FONT_CANDIDATES:
        if Path(path).is_file():
            if QFontDatabase.addApplicationFont(path) != -1:
                loaded.append(path)
    return loaded


def shoot(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    loaded = _register_fonts()
    print(f"fonts: {[Path(p).name for p in loaded] or '（无，中文可能显示为方块）'}")

    tmp = Path(tempfile.mkdtemp(prefix="shoot-"))
    game = tmp / "game"
    shutil.copytree(FIXTURES, game)
    ctx = AppContext(AppPaths.from_root(tmp / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)

    written: list[Path] = []
    for tid in theme.THEME_IDS:
        theme.apply_theme(app, tid)
        win = MainWindow(ctx, startup_backup=False)
        win.resize(1460, 920)
        win.show()
        win._index_ready()
        win._on_nav_category("main_story")
        for _ in range(3):
            app.processEvents()

        full = out_dir / f"shot-{tid}.png"
        win.grab().save(str(full))
        written.append(full)

        # 顶栏特写（状态药丸 + 面包屑 + 主题切换器都在这里）
        topbar = win.profile_chip.parentWidget()
        close = out_dir / f"shot-{tid}-topbar.png"
        topbar.grab().save(str(close))
        written.append(close)

        print(f"[ok] {tid}: {full.name} + {close.name}  "
              f"(RADIUS_MD={theme.RADIUS_MD}, pill={win.status_pill._text.text()!r})")
        win.close()
    return written


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "ui-redesign"
    written = shoot(out)
    print(f"\n共 {len(written)} 张 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
