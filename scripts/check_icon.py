"""核对生成的图标：中心是否是深色「邊」、四角/斜切处是否透明、金色是否正确。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".workbuddy" / "icon_check.txt"


def main() -> int:
    lines: list[str] = []
    for name in ("app.png",):
        im = Image.open(ROOT / "assets" / name).convert("RGBA")
        w, h = im.size
        lines.append(f"{name} {w}x{h}")
        pts = {
            "左上角(0,0)": (0, 0),
            "右下角(255,255)": (w - 1, h - 1),
            "右上角(255,0)": (w - 1, 0),
            "左下角(0,255)": (0, h - 1),
            "正中": (w // 2, h // 2),
            "上边中点": (w // 2, 8),
            "左边中点": (8, h // 2),
        }
        for label, (x, y) in pts.items():
            lines.append(f"  {label:16s} = {im.getpixel((x, y))}")
        # 统计不透明/金色/深色占比
        px = list(im.getdata())
        total = len(px)
        opaque = sum(1 for p in px if p[3] > 200)
        gold = sum(1 for p in px if p[3] > 200 and p[0] > 150 and p[1] > 110 and p[2] < 130)
        dark = sum(1 for p in px if p[3] > 200 and p[0] < 90 and p[1] < 90 and p[2] < 90)
        lines.append(f"  不透明 {opaque/total:6.1%}  金色 {gold/total:6.1%}  深色(字) {dark/total:6.1%}")
        lines.append(f"  期望：金色 > 70%（fill），深色 ~5-12%（邊 的笔画），四角透明")

    ico = ROOT / "assets" / "app.ico"
    with Image.open(ico) as f:
        lines.append("")
        lines.append(f"app.ico sizes = {sorted(s[0] for s in f.info.get('sizes', []))}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
