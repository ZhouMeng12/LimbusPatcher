"""诊断：主窗口背景为何没画出来（间隙应为 BG 而非纯黑）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DSH_NO_MODAL", "1")

from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

from limbus_patcher.ui import theme  # noqa: E402

app = QApplication.instance() or QApplication([])
theme.apply_theme(app, theme.DEFAULT_THEME)
t = theme.tokens()

print("BG token =", t["BG"])
print("app stylesheet first line:",
      app.styleSheet().splitlines()[0] if app.styleSheet() else "(empty)")
print("app palette Window =", app.palette().color(QPalette.Window).name())

# 1) 裸 QMainWindow 是否画出 BG
w = QMainWindow()
w.resize(200, 120)
w.show()
app.processEvents()
img = w.grab().toImage()
print("bare QMainWindow pixel(100,60) =", img.pixelColor(100, 60).name())
print("bare QMainWindow pixel(2,2)   =", img.pixelColor(2, 2).name())

# 2) 套用 QSS 后
w.setStyleSheet(theme._qss())
app.processEvents()
img = w.grab().toImage()
print("styled QMainWindow pixel(100,60) =", img.pixelColor(100, 60).name())
print("styled QMainWindow pixel(2,2)   =", img.pixelColor(2, 2).name())
