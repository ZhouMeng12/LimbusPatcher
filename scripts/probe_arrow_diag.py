"""诊断：Qt 菜单指示器到底画在哪、哪种 QSS 能真的关掉它。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DSH_NO_MODAL", "1")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QPushButton  # noqa: E402

from limbus_patcher.ui import theme  # noqa: E402

FONTS = ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc")
OUT = ROOT / ".workbuddy" / "probe_arrow_diag.txt"
W, H = 130, 30


def main() -> int:
    app = QApplication.instance() or QApplication([])
    for p in FONTS:
        if Path(p).is_file():
            QFontDatabase.addApplicationFont(p)
    theme.apply_theme(app, "mini-dark")

    lines: list[str] = []
    base_qss = theme.QSS
    i = base_qss.find("menu-indicator")
    lines.append("--- 生成的 QSS 里 menu-indicator 附近 ---")
    lines.append(repr(base_qss[i - 40 : i + 120]) if i >= 0 else "（没找到 menu-indicator）")
    lines.append("")

    def shots():
        a = QPushButton("改名称 ▼")
        b = QPushButton("改名称 ▼")
        b.setMenu(QMenu())
        for x in (a, b):
            x.setFixedSize(W, H)
            x.show()
        for _ in range(4):
            app.processEvents()
        return a.grab().toImage(), b.grab().toImage()

    def diff(ia, ib):
        xs, ys, n = [], [], 0
        for y in range(ia.height()):
            for x in range(ia.width()):
                if ia.pixel(x, y) != ib.pixel(x, y):
                    n += 1
                    xs.append(x)
                    ys.append(y)
        if not n:
            return "完全一致"
        return f"{n} px 不同，范围 x=[{min(xs)},{max(xs)}] y=[{min(ys)},{max(ys)}]"

    variants = {
        "无规则（对照）": base_qss.replace(
            "QPushButton::menu-indicator {\n    image: none; width: 0px; height: 0px;\n}\n", ""
        ),
        "image:none 单行": base_qss.replace(
            "image: none; width: 0px; height: 0px;", "image: none;"
        ),
        "只有 image:none 空格": base_qss.replace(
            "image: none; width: 0px; height: 0px;", "image: none; width: 0px;"
        ),
        "image: url()": base_qss.replace(
            "image: none; width: 0px; height: 0px;", "image: url();"
        ),
    }

    for name, qss in variants.items():
        app.setStyleSheet(qss)
        for _ in range(3):
            app.processEvents()
        ia, ib = shots()
        lines.append(f"{name:16s} → {diff(ia, ib)}")

    # 关键：确认"摘掉规则"的替换是否真的改到了字符串
    stripped = variants["无规则（对照）"]
    lines.append("")
    lines.append(f"对照替换是否生效: {stripped != base_qss}")
    lines.append(f"base 长度 {len(base_qss)} / 对照长度 {len(stripped)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
