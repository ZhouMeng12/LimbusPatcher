"""验证面板卡片化：采样间隙像素应为窗口底色 BG，面板内部为 s1。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from limbus_patcher.ui.theme import tokens  # noqa: E402

IMG = ROOT / "docs" / "ui-redesign" / "review" / "01-工作台.png"


def hexc(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb[:3])


def main() -> None:
    t = tokens("mini-dark")
    bg = t["BG"]
    s1 = t["SURFACE_1"]
    s2 = t["SURFACE_2"]
    print(f"[theme] BG={bg} S1={s1} S2={s2}")

    im = Image.open(IMG).convert("RGB")
    w, h = im.size
    print(f"[image] {IMG.name} size={w}x{h}")

    # 顶部栏高度约 44；工作区外 8px 边距 + 卡片间隙 8px
    # 采样整行像素，统计颜色直方图，看 BG 是否出现为一个独立的窄条
    def scan_row(y, label):
        counts = {}
        for x in range(w):
            c = hexc(im.getpixel((x, y)))
            counts[c] = counts.get(c, 0) + 1
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:6]
        print(f"  y={y:>4} {label}: " + ", ".join(f"{c}x{n}" for c, n in top))

    def scan_col(x, label):
        counts = {}
        for y in range(h):
            c = hexc(im.getpixel((x, y)))
            counts[c] = counts.get(c, 0) + 1
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:6]
        print(f"  x={x:>4} {label}: " + ", ".join(f"{c}x{n}" for c, n in top))

    print("[rows]")
    for y in (2, 6, 10, 30, 50, 60, 100, 200, 300):
        if y < h:
            scan_row(y, "")
    print("[cols]")
    for x in (2, 6, 10, 40, 120, 260, 300, 340, 600):
        if x < w:
            scan_col(x, "")

    # 统计整图 BG 出现次数
    bgcount = 0
    for y in range(h):
        for x in range(w):
            if hexc(im.getpixel((x, y))) == bg:
                bgcount += 1
    total = w * h
    print(f"[BG ratio] {bgcount}/{total} = {bgcount/total:.1%}")
    print("OK if BG ratio > 1.5% (gaps between cards) ")


if __name__ == "__main__":
    main()
