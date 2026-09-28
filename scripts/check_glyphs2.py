"""检查界面用到的符号在真实字体下有没有字形（渲染成图 + 像素比对）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
          "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/segoeui.ttf"):
    if Path(p).is_file():
        QFontDatabase.addApplicationFont(p)

CHARS = {
    "⋯": 0x22EF, "…": 0x2026, "›": 0x203A, "·": 0x00B7, "★": 0x2605,
    "☆": 0x2606, "↶": 0x21B6, "↷": 0x21B7, "▼": 0x25BC, "邊": 0x908A,
    "√": 0x221A, "※": 0x203B, "✓": 0x2713,
    "↺": 0x21BA, "↻": 0x21BB, "⟲": 0x27F2, "⟳": 0x27F3,
    "•": 0x2022, "‹": 0x2039, "▪": 0x25AA, "→": 0x2192, "←": 0x2190,
    "⤺": 0x293A, "⤻": 0x293B, "⎌": 0x238C, "↩": 0x21A9, "↪": 0x21AA,
}

FAMILIES = ["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "SimHei", ""]
lines = []
for name, code in CHARS.items():
    row = [f"{name} U+{code:04X}"]
    for fam in FAMILIES:
        f = QFont(fam) if fam else QFont()
        f.setPixelSize(28)
        fm = QFontMetrics(f)
        in_font = fm.inFontUcs4(code)
        # 真的画一遍：空字形会被画成一个方框（豆腐块）
        img = QImage(44, 44, QImage.Format.Format_ARGB32)
        img.fill(0xFF000000)
        p = QPainter(img)
        p.setFont(f)
        p.setPen(0xFFFFFFFF)
        p.drawText(img.rect(), 0x84, name)
        p.end()
        nonbg = 0
        for y in range(44):
            for x in range(44):
                if img.pixel(x, y) & 0x00FFFFFF:
                    nonbg += 1
        row.append(f"{fam or 'default'}={'Y' if in_font else 'n'}/{nonbg}")
    lines.append("  ".join(row))

Path(ROOT / ".workbuddy" / "glyph.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("written")
