"""定论：Qt 到底给 QPushButton 画不画菜单指示器？

三条证据：
1. `QStyle.pixelMetric(PM_MenuButtonIndicator)` —— 0 表示不画。
2. 同尺寸、同文案、带/不带菜单两图逐像素比对。
3. 把「改名称 ▼」放大渲染，扫右侧 x 区间里有几"团"墨 —— 1 团=只有文字三角，2 团=多画了箭头。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DSH_NO_MODAL", "1")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QMenu,
    QPushButton,
    QStyle,
)

from limbus_patcher.ui import theme  # noqa: E402

FONTS = ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc")
OUT = ROOT / ".workbuddy" / "probe_arrow_final.txt"
W, H = 200, 34


def ink_groups(img, x0: int, x1: int, bg) -> list[tuple[int, int]]:
    """在 x0..x1 的竖条里，找有"墨"的列，合并成连续段。"""
    cols = []
    for x in range(x0, x1):
        has = any(img.pixel(x, y) != bg for y in range(img.height()))
        cols.append((x, has))
    groups: list[tuple[int, int]] = []
    start = None
    for x, has in cols:
        if has and start is None:
            start = x
        elif not has and start is not None:
            groups.append((start, x - 1))
            start = None
    if start is not None:
        groups.append((start, x1 - 1))
    return groups


def main() -> int:
    app = QApplication.instance() or QApplication([])
    for p in FONTS:
        if Path(p).is_file():
            QFontDatabase.addApplicationFont(p)
    theme.apply_theme(app, "mini-dark")

    lines: list[str] = []

    plain = QPushButton("改名称 ▼")
    wm = QPushButton("改名称 ▼")
    wm.setMenu(QMenu())
    for b in (plain, wm):
        b.setFixedSize(W, H)
        b.show()
    for _ in range(5):
        app.processEvents()

    style = app.style()
    for label, b in (("无菜单", plain), ("有菜单", wm)):
        pm = style.pixelMetric(
            QStyle.PixelMetric.PM_MenuButtonIndicator, None, b
        )
        lines.append(f"{label} 按钮：PM_MenuButtonIndicator = {pm}  尺寸 {b.size().width()}x{b.size().height()}")

    ia = plain.grab().toImage()
    ib = wm.grab().toImage()
    n = sum(
        1
        for y in range(ia.height())
        for x in range(ia.width())
        if ia.pixel(x, y) != ib.pixel(x, y)
    )
    lines.append(f"两图逐像素差异 = {n} 个像素")

    bg = ia.pixel(2, 2)
    lines.append(f"按钮底色（左上角）= {bg:#010x}")
    # 只看右半边（文字三角应在右侧）
    groups = ink_groups(ia, W // 2, W, bg)
    lines.append(f"右半 x=[{W//2},{W}) 里的墨团：{groups}")
    lines.append(f"→ 墨团数 = {len(groups)}（『改名称 ▼』预期 3 团：名称2字 + 三角，或合并成更少）")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
