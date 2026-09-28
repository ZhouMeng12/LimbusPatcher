"""扫描界面源码里所有「当符号用」的字符，报告哪些在实际字体下缺字形（会画成豆腐块）。

用法：.venv/Scripts/python.exe scripts/scan_glyphs.py
结果写到 .workbuddy/scan_glyphs.log
"""
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

#: 这些是中文标点，字体一定有；不必检查。
CJK_PUNCT = set("「」『』（）【】〈〉《》〔〕、。，；：？！…—～·‘’“”％＃＆＊＋－／＝｜")
#: 中日韩汉字区间（直接判为有字形）
def is_han(ch: str) -> bool:
    o = ord(ch)
    return (0x3400 <= o <= 0x9FFF) or (0xF900 <= o <= 0xFAFF) or (0x20000 <= o <= 0x2FA1F)


INTERESTING = (
    (0x2000, 0x2BFF),   # 通用标点 / 上下标 / 货币 / 字母符号 / 箭头 / 数学 / 制表 / 几何
    (0x2E00, 0x2E7F),   # 补充标点
    (0xFE00, 0xFE0F),   # 变体选择符
    (0xFF00, 0xFFEF),   # 全角形式
    (0x1F300, 0x1FAFF),  # emoji
    (0x2190, 0x21FF),   # 箭头
    (0x2600, 0x27BF),   # 杂项符号 / 装饰符号
)


def interesting(ch: str) -> bool:
    if is_han(ch) or ch in CJK_PUNCT:
        return False
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in INTERESTING)


def has_glyph(ch: str, fam: str = "Microsoft YaHei UI") -> tuple[bool, int]:
    f = QFont(fam)
    f.setPixelSize(28)
    fm = QFontMetrics(f)
    in_font = fm.inFontUcs4(ord(ch))
    img = QImage(46, 46, QImage.Format.Format_ARGB32)
    img.fill(0xFF000000)
    p = QPainter(img)
    p.setFont(f)
    p.setPen(0xFFFFFFFF)
    p.drawText(img.rect(), 0x84, ch)
    p.end()
    nonbg = sum(1 for y in range(46) for x in range(46) if img.pixel(x, y) & 0x00FFFFFF)
    return in_font, nonbg


#: 缺字形时的「豆腐块」像素数（同一字号下是常数）
TOFU = 216

UI_DIR = ROOT / "limbus_patcher" / "ui"
files = sorted(UI_DIR.glob("*.py"))
found: dict[str, list[str]] = {}
for path in files:
    src = path.read_text(encoding="utf-8")
    for ch in src:
        if interesting(ch):
            found.setdefault(ch, [])
            if path.name not in found[ch]:
                found[ch].append(path.name)

lines: list[str] = []
bad: list[tuple[str, list[str]]] = []
for ch in sorted(found, key=ord):
    in_font, nonbg = has_glyph(ch)
    ok = in_font and nonbg not in (0, TOFU)
    tag = "OK " if ok else "BAD"
    lines.append(f"{tag} U+{ord(ch):04X} {ch}  inFont={in_font} px={nonbg}  {found[ch]}")
    if not ok:
        bad.append((ch, found[ch]))

lines.append("")
lines.append(f"共 {len(found)} 个符号，缺字形 {len(bad)} 个：")
for ch, where in bad:
    lines.append(f"  U+{ord(ch):04X} {ch}  ← {', '.join(where)}")

(ROOT / ".workbuddy" / "scan_glyphs.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("written", len(found), "symbols,", len(bad), "bad")
