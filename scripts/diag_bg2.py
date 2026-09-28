"""验证：给根容器加显式背景后，grab 能否画出 BG。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DSH_NO_MODAL", "1")

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel  # noqa: E402

app = QApplication.instance() or QApplication([])

QSS = """
QMainWindow { background: #101215; }
QWidget { background: transparent; }
QWidget#appRoot { background: #101215; }
QLabel#probe { background: #171a1f; }
"""

app.setStyleSheet(QSS)

w = QMainWindow()
root = QWidget()
root.setObjectName("appRoot")
lay = QVBoxLayout(root)
lay.setContentsMargins(8, 8, 8, 8)
lay.setSpacing(8)
lab = QLabel("panel")
lab.setObjectName("probe")
lab.setFixedHeight(60)
lay.addWidget(lab)
lab2 = QLabel("panel2")
lab2.setObjectName("probe")
lab2.setFixedHeight(60)
lay.addWidget(lab2)
w.setCentralWidget(root)
w.resize(220, 160)
w.show()
app.processEvents()
img = w.grab().toImage()
print("size", img.width(), img.height())
for pt in [(2, 2), (110, 2), (2, 80), (110, 78), (110, 82), (110, 150), (5, 40), (110, 40)]:
    print(f"  {pt} = {img.pixelColor(*pt).name()}")
