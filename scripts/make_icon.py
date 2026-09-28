"""生成打包用资源：应用图标（``assets/app.ico`` / ``app.png``）+ 版本信息（``assets/version_info.txt``）。

为什么放在 ``assets/`` 而不是 spec 原来写的 ``build/``
------------------------------------------------------
``limbus_patcher.spec`` 原本引用 ``build/app.ico``，但 ``build/`` 是 PyInstaller 的
workpath，而 ``scripts/build.ps1`` 用了 ``--clean`` —— **``--clean`` 会把 workpath 整个删掉**，
所以那份图标在打包前就没了，之前的 exe 一直没有图标与版本信息。
这里把资源改放**版本库里的** ``assets/``，并把本脚本接进 ``build.ps1``，从此可复现。

图标设计 = 沿用界面里的品牌标记（``ui/brand.py`` 的 ``LogoMark``）：
金色「品牌金」方块 + **对角两处斜切**（原型 ``--cut``）+ 居中单字「邊」。
小尺寸（<32px）文字会糊成一团，所以 16/20/24 三档只留金色切角方块。

用法：
    .venv/Scripts/python.exe scripts/make_icon.py
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPainterPath  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from limbus_patcher import APP_NAME, __version__  # noqa: E402
from limbus_patcher.ui import theme  # noqa: E402

ASSETS = ROOT / "assets"
MASTER = 256
#: ICO 里要包含的尺寸（Windows 会按显示场景挑最合适的一档）
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
#: 低于这个尺寸就不画「邊」——笔画糊成一团反而像脏点
TEXT_MIN_SIZE = 32
CUT_RATIO = 0.28     # 斜切量占边长的比例（原型 bus 主题是 10/28 ≈ 0.36，图标收一点更清爽）
MARGIN_RATIO = 0.04  # 四周留一点白，斜切口才不会贴边像被裁掉
TEXT_RATIO = 0.54    # 「邊」的边长占比（笔画多，再大就糊成一团）
FONTS = ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc")


def _register_fonts(app: QApplication) -> None:
    for p in FONTS:
        if Path(p).is_file():
            QFontDatabase.addApplicationFont(p)


def _render_master(app: QApplication, *, with_text: bool) -> Image.Image:
    """按品牌标记渲染一张 MASTER×MASTER 的透明底 PNG，返回 PIL Image。"""
    img = QImage(MASTER, MASTER, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    m = MASTER * MARGIN_RATIO
    side = MASTER - 2 * m
    cut = side * CUT_RATIO

    path = QPainterPath()
    # 与 LogoMark 一致：切掉「左上」与「右下」两个对角
    path.moveTo(m + cut, m)
    path.lineTo(m + side, m)
    path.lineTo(m + side, m + side - cut)
    path.lineTo(m + side - cut, m + side)
    path.lineTo(m, m + side)
    path.lineTo(m, m + cut)
    path.closeSubpath()

    p.fillPath(path, QColor(theme.ACCENT))

    if with_text:
        font = QFont()
        font.setBold(True)
        font.setPixelSize(int(side * TEXT_RATIO))
        p.setFont(font)
        p.setPen(QColor(theme.ON_ACCENT))
        p.drawText(QRectF(m, m, side, side), Qt.AlignmentFlag.AlignCenter, "邊")

    p.end()

    buf = io.BytesIO()
    # QImage.save 需要文件名或 QIODevice；用 QBuffer 写进字节流
    qb = QBuffer()
    qb.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(qb, "PNG")
    buf.write(bytes(qb.data()))
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def write_version_info(path: Path) -> None:
    """写 PyInstaller 的 ``--version-file``（VSVersionInfo 的字符串序列化）。"""
    parts = [int(x) for x in __version__.split(".") if x.isdigit()]
    while len(parts) < 4:
        parts.append(0)
    v = tuple(parts[:4])
    text = (
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers={v}, prodvers={v},\n"
        "    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)\n"
        "  ),\n"
        "  kids=[\n"
        "    StringFileInfo([\n"
        "      StringTable(\n"
        "        '080404B0',\n"
        "        [StringStruct('CompanyName', 'LimbusPatcher contributors'),\n"
        f"         StringStruct('FileDescription', '{APP_NAME}'),\n"
        f"         StringStruct('FileVersion', '{__version__}'),\n"
        "         StringStruct('InternalName', 'limbus_patcher'),\n"
        "         StringStruct('LegalCopyright', 'MIT License (c) 2025 LimbusPatcher contributors'),\n"
        f"         StringStruct('OriginalFilename', '{APP_NAME}.exe'),\n"
        f"         StringStruct('ProductName', '{APP_NAME}'),\n"
        f"         StringStruct('ProductVersion', '{__version__}')]\n"
        "      )\n"
        "    ]),\n"
        "    VarFileInfo([VarStruct('Translation', [2052, 1200])])\n"
        "  ]\n"
        ")\n"
    )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    _register_fonts(app)
    theme.apply_theme(app, theme.DEFAULT_THEME)

    master = _render_master(app, with_text=True)
    png = ASSETS / "app.png"
    master.save(png)

    # 小尺寸用「无文字」版单独渲染，避免 16px 下糊成一团
    small = _render_master(app, with_text=False)
    frames: list[Image.Image] = []
    for s in ICO_SIZES:
        src = master if s >= TEXT_MIN_SIZE else small
        frames.append(src.resize((s, s), Image.Resampling.LANCZOS))

    ico = ASSETS / "app.ico"
    # 以最大帧为底，其余通过 append_images 带上（Pillow 会保留每档的位图）
    frames_sorted = sorted(frames, key=lambda im: im.width)
    biggest = frames_sorted[-1]
    biggest.save(
        ico,
        format="ICO",
        sizes=[(im.width, im.height) for im in frames_sorted],
        append_images=[im for im in frames_sorted if im is not biggest],
    )

    write_version_info(ASSETS / "version_info.txt")

    with Image.open(ico) as chk:
        got = sorted(chk.info.get("sizes", []))
    print(f"[ok] {ico.relative_to(ROOT)}  含尺寸 {[s[0] for s in got]}")
    print(f"[ok] {png.relative_to(ROOT)}  {master.size[0]}x{master.size[1]}")
    print(f"[ok] {(ASSETS / 'version_info.txt').relative_to(ROOT)}  {APP_NAME} v{__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
