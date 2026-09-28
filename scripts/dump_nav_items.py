"""打印导航树的全部条目，确认 role:/entities: 虚拟入口确实在界面上。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from limbus_patcher import categories  # noqa: E402
from limbus_patcher.ui import theme  # noqa: E402
from limbus_patcher.ui.nav import NavPanel  # noqa: E402

OUT = ROOT / ".workbuddy" / "nav_items.txt"


def main() -> int:
    app = QApplication.instance() or QApplication([])
    for p in ("C:/Windows/Fonts/msyh.ttc",):
        if Path(p).is_file():
            QFontDatabase.addApplicationFont(p)
    theme.apply_theme(app, "mini-dark")

    nav = NavPanel()
    counts = {k: i + 1 for i, k in enumerate(categories.CATEGORIES)}
    nav.set_counts(counts, {}, {"identity_skill": 21, "ego_skill": 18,
                                "identity_voice": 9, "ego_voice": 7},
                   {"personality": 148, "ego": 64})

    lines = []
    root = nav.tree.invisibleRootItem()
    for i in range(root.childCount()):
        it = root.child(i)
        lines.append(f"[{it.text(0)}]")
        for j in range(it.childCount()):
            c = it.child(j)
            key = c.data(0, 256)  # Qt.UserRole
            mark = "  ← 虚拟入口" if str(key).startswith(("role:", "entities:")) else ""
            lines.append(f"    {c.text(0)}{mark}")
    lines.append("")
    lines.append(f"总共可点条目 = {len(nav._cats)}")
    virtual = sorted(k for k in nav._cats if k.startswith(("role:", "entities:")))
    lines.append(f"虚拟入口 {len(virtual)} 个：{virtual}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
