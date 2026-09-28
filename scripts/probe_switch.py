"""量一下「界面风格」浮层里分段控件的实际比例。

用法：
    .venv/Scripts/python.exe scripts/probe_switch.py [图] [报告.txt]

把 03-风格切换器.png 里 switchTrack 那一行横着扫一遍，按颜色分段，
报告每段的起止 x、宽度、占比 —— 用来核对「巴士 50% / 亮 25% / 暗 25%」。

注：Windows 控制台会把中文输出转成 GBK 再被管道二次编码成乱码，
所以这里**直接把报告写成 UTF-8 文件**，不依赖 stdout。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "docs" / "ui-redesign" / "review" / "03-风格切换器.png"
DEFAULT_OUT = ROOT / ".workbuddy" / "probe_switch.txt"


def main() -> int:
    args = [a for a in sys.argv[1:]]
    img_path = Path(args[0]) if len(args) > 0 else DEFAULT
    out_path = Path(args[1]) if len(args) > 1 else DEFAULT_OUT

    lines: list[str] = []

    def say(s: str = "") -> None:
        lines.append(s)

    im = Image.open(img_path).convert("RGB")
    W, H = im.size
    px = im.load()
    say(f"图 {img_path.name} 尺寸 {W}x{H}")

    def runs_of(y: int) -> list[tuple[int, int, tuple[int, int, int]]]:
        row = [px[x, y] for x in range(W)]
        segs: list[tuple[int, int, tuple[int, int, int]]] = []
        start = 0
        for x in range(1, W):
            if row[x] != row[start]:
                segs.append((start, x - 1, row[start]))
                start = x
        segs.append((start, W - 1, row[start]))
        return segs

    # switchTrack 那行的特征：存在多段"宽而平"的色块（每格按钮一块底），
    # 而文字行的段都很窄（笔画）。所以取"宽段数量最多"的行。
    best_y, best_wide = 0, -1
    for y in range(H):
        wide = sum(1 for a, b, _ in runs_of(y) if (b - a + 1) >= 20)
        if wide > best_wide:
            best_wide, best_y = wide, y
    say(f"宽色块最多的一行 y={best_y}（{best_wide} 块），按此横扫：")
    say()

    segs = [s for s in runs_of(best_y) if s[1] - s[0] + 1 >= 8]
    for a, b, c in segs:
        w = b - a + 1
        say(f"  x=[{a:4d},{b:4d}] w={w:4d} ({w / W * 100:5.1f}%)  RGB{c}")

    # "按钮格"估算：把宽度 >= 20 的段视作格底，按它们算内部比例
    inner_segs = [s for s in segs if s[1] - s[0] + 1 >= 20]
    if len(inner_segs) >= 2:
        span = inner_segs[-1][1] - inner_segs[0][0] + 1
        say()
        say(f"  以第一块到最末块计，内宽≈{span}px：")
        for a, b, c in inner_segs:
            w = b - a + 1
            say(f"    格 w={w:4d} → {w / span * 100:5.1f}%  RGB{c}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
