"""QPushButton 带菜单时，Qt 到底画不画指示器？分别测「无 QSS」与「有 QSS」。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QPushButton, QStyle  # noqa: E402

from limbus_patcher.ui import theme  # noqa: E402

FONTS = ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc")
OUT = ROOT / ".workbuddy" / "probe_arrow_qss.txt"


def main() -> int:
    app = QApplication.instance() or QApplication([])
    for p in FONTS:
        if Path(p).is_file():
            QFontDatabase.addApplicationFont(p)

    lines: list[str] = []

    def measure(tag: str) -> None:
        b = QPushButton("改名称 ▼")
        b.setMenu(QMenu())
        b.setFixedSize(200, 34)
        b.show()
        for _ in range(4):
            app.processEvents()
        pm = app.style().pixelMetric(QStyle.PixelMetric.PM_MenuButtonIndicator, None, b)
        # 顺便数一下渲染里右侧有没有独立的"箭头墨团"
        img = b.grab().toImage()
        bg = img.pixel(3, 3)
        # 从右往左扫，跳过 1px 边框，看接下来 20px 内是否有墨
        right_ink = []
        for x in range(200 - 2, 200 - 26, -1):
            if any(img.pixel(x, y) != bg for y in range(3, 31)):
                right_ink.append(x)
        lines.append(
            f"{tag}: PM_MenuButtonIndicator={pm}；"
            f"右侧 24px 内墨列数={len(right_ink)}"
            + (f"（x={min(right_ink)}..{max(right_ink)}）" if right_ink else "")
        )
        b.close()

    app.setStyleSheet("")
    for _ in range(3):
        app.processEvents()
    measure("无 QSS（裸 Fusion）")

    app.setStyleSheet(theme.QSS)
    for _ in range(3):
        app.processEvents()
    measure("有 QSS（本应用）")

    # 再测：有 QSS 但把我的那条规则摘掉
    stripped = theme.QSS.replace("image: none; width: 0px; height: 0px;", "")
    app.setStyleSheet(stripped)
    for _ in range(3):
        app.processEvents()
    measure("有 QSS（摘掉新增规则）")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
