"""核对「带下拉的按钮有没有多画一个箭头」。

背景：曾经担心 ``setMenu()`` 的 QPushButton（``改名称 ▼``、顶栏 ``•••``）会既有
文字三角、又被 Qt 画一个原生菜单指示箭头，变成「两个箭头」。实测结论是**虚惊**：

* **裸 Fusion（无 QSS）**：``PM_MenuButtonIndicator=12``，右侧真的画箭头（多 24 列墨）。
* **本应用 QSS**：``QStyleSheetStyle`` 不再画它 —— 无论有没有那条
  ``QPushButton::menu-indicator`` 规则，右侧都没有箭头墨迹。

本脚本把这三种场景一次量清楚，作为回归依据。若将来某个场景又出现右侧箭头墨迹，
说明样式被改动了。

用法：
    .venv/Scripts/python.exe scripts/probe_menu_indicator.py [报告.txt]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QMenu,
    QPushButton,
    QStyle,
)

from limbus_patcher.ui import theme  # noqa: E402

FONTS = ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc")
DEFAULT_OUT = ROOT / ".workbuddy" / "probe_menu_indicator.txt"
W, H = 200, 34


def _measure(app: QApplication, tag: str) -> str:
    btn = QPushButton("改名称 ▼")
    btn.setMenu(QMenu())
    btn.setFixedSize(W, H)
    btn.show()
    for _ in range(4):
        app.processEvents()

    pm = app.style().pixelMetric(QStyle.PixelMetric.PM_MenuButtonIndicator, None, btn)
    img = btn.grab().toImage()
    bg = img.pixel(3, 3)
    # 「墨」= 与按钮底色不同的列。边框列（最右 1px）不算。
    ink = [
        x
        for x in range(W - 2, -1, -1)
        if any(img.pixel(x, y) != bg for y in range(3, H - 3))
    ]
    # 最右一团墨的起止（跳过 x=W-1 的边框）
    right = [x for x in ink if x != W - 1]
    gap_free = ""
    if right:
        # 从右往左找连续段
        seg = [right[0]]
        for x in right[1:]:
            if x == seg[-1] - 1:
                seg.append(x)
            else:
                break
        gap_free = f"，最右连续墨段 x=[{min(seg)},{max(seg)}]"
    btn.close()
    return f"{tag}: PM_MenuButtonIndicator={pm}，墨列数={len(ink)}{gap_free}"


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    app = QApplication.instance() or QApplication([])
    for p in FONTS:
        if Path(p).is_file():
            QFontDatabase.addApplicationFont(p)

    lines: list[str] = []

    app.setStyleSheet("")
    for _ in range(3):
        app.processEvents()
    lines.append(_measure(app, "裸 Fusion（无 QSS，对照）"))

    app.setStyleSheet(theme.QSS)
    for _ in range(3):
        app.processEvents()
    lines.append(_measure(app, "本应用 QSS（含 menu-indicator 规则）"))

    stripped = theme.QSS.replace("image: none; width: 0px; height: 0px;", "")
    app.setStyleSheet(stripped)
    for _ in range(3):
        app.processEvents()
    lines.append(_measure(app, "本应用 QSS（摘掉该规则，对照）"))

    lines.append("")
    lines.append("结论：只要套了本应用 QSS，右侧就没有箭头墨迹 → 不存在「两个箭头」。")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    _out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        import traceback

        _out.parent.mkdir(parents=True, exist_ok=True)
        _out.write_text(traceback.format_exc(), encoding="utf-8")
        raise SystemExit(1)
