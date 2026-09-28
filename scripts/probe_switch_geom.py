"""直接向 Qt 要「界面风格」浮层里各格的真实几何 —— 比抠像素靠谱得多。

用法：
    .venv/Scripts/python.exe scripts/probe_switch_geom.py [报告.txt]

在 offscreen 下建一个 StylePopover，分别模拟「未展开（巴士态）」与
「已展开（简约态）」，打印每颗按钮的 geometry() 与占比。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame  # noqa: E402

from limbus_patcher.ui import theme  # noqa: E402
from limbus_patcher.ui.theme_switch import StylePopover  # noqa: E402

FONTS = ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc")
DEFAULT_OUT = ROOT / ".workbuddy" / "probe_switch_geom.txt"


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    try:
        return _run(out_path)
    except Exception:  # noqa: BLE001
        import traceback

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(traceback.format_exc(), encoding="utf-8")
        return 1


def _run(out_path: Path) -> int:
    app = QApplication.instance() or QApplication([])
    for p in FONTS:
        if Path(p).is_file():
            QFontDatabase.addApplicationFont(p)
    theme.apply_theme(app, "mini-dark")

    lines: list[str] = []

    def dump(title: str, pop: StylePopover) -> None:
        pop.adjustSize()
        pop.show()
        for _ in range(3):
            app.processEvents()
        track = pop.findChild(QFrame, "switchTrack")
        lines.append(f"=== {title} — 浮层 {pop.width()}x{pop.height()} ===")
        inner = pop._bus_btn.parentWidget().width() - 6
        if track is not None:
            g = track.geometry()
            lines.append(f"  switchTrack: x={g.x()} y={g.y()} w={g.width()} h={g.height()}")
            inner = g.width() - 6
            lines.append(f"  内宽(去 3px 边) = {inner}")
        rows = [
            ("bus  巴士", pop._bus_btn),
            ("mini 简约", pop._mini_btn),
            ("tone 亮  ", pop._tone_btns.get("mini-light")),
            ("tone 暗  ", pop._tone_btns.get("mini-dark")),
        ]
        vis = [(n, b) for n, b in rows if b is not None and b.isVisible()]
        total = sum(b.width() for _, b in vis)
        for name, b in vis:
            g = b.geometry()
            pct = (b.width() / inner * 100) if inner else 0
            lines.append(
                f"  {name}: x={g.x():3d} w={g.width():3d} 占内宽 {pct:5.1f}%"
            )
        lines.append(f"  可见格总宽 = {total} (内宽 {inner})")
        lines.append("")

    pop1 = StylePopover("bus")
    dump("未展开 · 巴士态", pop1)
    pop2 = StylePopover("mini-dark")
    dump("已展开 · 简约态", pop2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
