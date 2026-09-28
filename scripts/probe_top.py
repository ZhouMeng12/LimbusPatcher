"""探查截图顶部黑条：逐行采样，找出颜色分界（判断是不是菜单栏没上色）。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "ui-redesign" / "review" / "01-工作台.png"


def hexc(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb[:3])


im = Image.open(IMG).convert("RGB")
w, h = im.size
lines = [f"{IMG.name} {w}x{h}", "[列 x=100 逐行颜色变化]"]
prev = None
for y in range(0, 90):
    c = hexc(im.getpixel((100, y)))
    if c != prev:
        lines.append(f"  y={y:>3} -> {c}")
        prev = c

lines.append("[列 x=700（顶栏中部）]")
prev = None
for y in range(0, 90):
    c = hexc(im.getpixel((700, y)))
    if c != prev:
        lines.append(f"  y={y:>3} -> {c}")
        prev = c

lines.append("[底部 30 行 x=700]")
prev = None
for y in range(h - 30, h):
    c = hexc(im.getpixel((700, y)))
    if c != prev:
        lines.append(f"  y={y:>3} -> {c}")
        prev = c

lines.append("[左右边缘 y=400]")
for x in list(range(0, 20)) + list(range(w - 20, w)):
    c = hexc(im.getpixel((x, 400)))
    lines.append(f"  x={x:>4} -> {c}")

(ROOT / ".workbuddy" / "probe_top.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("written")
