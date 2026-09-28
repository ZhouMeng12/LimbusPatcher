"""做一张「原型 vs Qt 落地」上下对照图。

原型默认是巴士主题，直接对比会被配色干扰，所以这里把它切到 data-theme="mini"
（= 第一版 AURUM 暗金，和 Qt 现在的默认主题同色系），这样差异只剩"格局"。

用法：.venv/Scripts/python.exe scripts/make_compare.py
产出：docs/ui-redesign/compare-原型vs落地.png
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS",
                      "--no-sandbox --disable-gpu --disable-software-rasterizer")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402

SRC = ROOT / "docs" / "ui-redesign" / "prototype.html"
SHOT = ROOT / "docs" / "ui-redesign" / "review" / "01-工作台.png"
OUT = ROOT / "docs" / "ui-redesign" / "compare-原型vs落地.png"
W, H = 1460, 920


def render_prototype(theme_name: str, dst: Path) -> None:
    """把原型按指定主题渲染成图片。"""
    html = SRC.read_text(encoding="utf-8")
    html = html.replace('data-theme="bus"', f'data-theme="{theme_name}"', 1)
    tmp_html = Path(tempfile.mkdtemp(prefix="proto-")) / "prototype.html"
    tmp_html.write_text(html, encoding="utf-8")

    app = QApplication.instance() or QApplication([])
    view = QWebEngineView()
    view.resize(W, H)
    view.show()

    loop = QEventLoop()
    view.loadFinished.connect(lambda ok: loop.quit())
    view.load(QUrl.fromLocalFile(str(tmp_html)))
    QTimer.singleShot(15000, loop.quit)
    loop.exec()

    settle = QEventLoop()
    QTimer.singleShot(2500, settle.quit)
    settle.exec()
    for _ in range(30):
        app.processEvents()
    view.grab().save(str(dst))
    view.close()


def main() -> int:
    proto_png = ROOT / "docs" / "ui-redesign" / "prototype-mini.png"
    render_prototype("mini", proto_png)

    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 20)
    a = Image.open(proto_png).convert("RGB")
    b = Image.open(SHOT).convert("RGB")

    pad, head = 14, 34
    width = max(a.width, b.width) + pad * 2
    height = head + a.height + pad + head + b.height + pad
    comp = Image.new("RGB", (width, height), (18, 20, 24))
    dr = ImageDraw.Draw(comp)

    y = pad
    dr.text((pad, y), "① 原型 prototype.html（切到「简约·暗」主题）", font=font, fill=(240, 235, 225))
    y += head
    comp.paste(a, (pad, y))
    y += a.height + pad

    dr.text((pad, y), "② Qt 落地（当前默认主题「简约·暗」）", font=font, fill=(240, 235, 225))
    y += head
    comp.paste(b, (pad, y))

    comp.save(str(OUT))
    print(f"saved={OUT} size={comp.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
