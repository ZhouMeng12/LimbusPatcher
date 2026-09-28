"""把 prototype.html 离屏渲染成图片，方便和 Qt 落地效果逐项比对。

用法：.venv/Scripts/python.exe scripts/shoot_prototype.py [输出路径]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu --disable-software-rasterizer")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402

SRC = ROOT / "docs" / "ui-redesign" / "prototype.html"


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "ui-redesign" / "prototype-shot.png"
    app = QApplication.instance() or QApplication([])

    view = QWebEngineView()
    view.resize(1460, 920)
    view.show()

    loop = QEventLoop()
    view.loadFinished.connect(lambda ok: loop.quit())
    view.load(QUrl.fromLocalFile(str(SRC)))
    QTimer.singleShot(15000, loop.quit)
    loop.exec()

    # 等字体/布局稳定
    settle = QEventLoop()
    QTimer.singleShot(2500, settle.quit)
    settle.exec()
    for _ in range(30):
        app.processEvents()

    img = view.grab()
    img.save(str(out))
    print(f"saved={out} size={img.width()}x{img.height()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
