"""把头像压缩到指定最长边（默认 640px），原图挪到 full/ 备份。

用法：python scripts/shrink_portraits.py [--dir data/portraits] [--max 640]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=ROOT / "data" / "portraits")
    ap.add_argument("--max", type=int, default=640)
    ap.add_argument("--format", default="webp", choices=("webp", "png"),
                    help="随包格式：webp 体积约为 png 的 1/8（Qt 可直接加载，保留透明）")
    args = ap.parse_args()
    try:
        from PIL import Image
    except ImportError:
        print("需要 Pillow")
        return 2

    total_before = total_after = 0
    done = 0
    for sub in ("identity", "ego"):
        src_dir = args.dir / sub
        if not src_dir.is_dir():
            continue
        full_dir = args.dir / "full" / sub
        full_dir.mkdir(parents=True, exist_ok=True)
        for src in sorted(src_dir.glob("*.png")):
            before = src.stat().st_size
            total_before += before
            backup = full_dir / src.name
            if not backup.is_file():
                shutil.copy2(src, backup)   # 原图留一份
            dest = src.with_suffix(".webp") if args.format == "webp" else src
            try:
                with Image.open(src) as im:
                    im = im.convert("RGBA") if im.mode not in ("RGB", "RGBA") else im
                    w, h = im.size
                    scale = args.max / max(w, h)
                    if scale < 1:
                        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
                    if args.format == "webp":
                        im.save(dest, "WEBP", quality=88, method=6)
                    else:
                        im.save(dest, "PNG", optimize=True)
            except Exception as exc:  # noqa: BLE001
                print(f"  跳过 {src.name}: {exc}")
                continue
            if dest != src:
                src.unlink(missing_ok=True)   # 原 PNG 已在 full/ 备份
            total_after += dest.stat().st_size
            done += 1
    print(f"压缩 {done} 张：{total_before // 1024 // 1024} MB → {total_after // 1024 // 1024} MB"
          f"（原图备份在 {args.dir / 'full'}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
