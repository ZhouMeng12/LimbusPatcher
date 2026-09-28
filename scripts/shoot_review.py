"""出一套「改版看板」截图：把当前默认主题的各个界面都拍下来。

用法：
    .venv/Scripts/python.exe scripts/shoot_review.py [输出目录]

产出（默认 docs/ui-redesign/review/）：
    01-工作台.png        三栏主界面（导航 / 列表 / 编辑器）
    02-状态药丸.png      顶栏单颗状态药丸展开后的完整清单
    03-风格切换器.png     「风格 · XX」按钮展开出的界面风格浮层
    04-人格图鉴.png      罪人 → 人格卡片 → 技能/剧情/语音
    05-敌方图鉴.png      分组 → 实体卡片 → 技能/被动
    06-剧本模式.png      关卡逐行对照
    07-三主题顶栏.png    三套主题顶栏纵向对比（拼图）
    08-导航分区.png      分区全部展开后的导航（含 role:/entities: 虚拟入口）
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DSH_NO_MODAL", "1")
os.environ.setdefault("LIMBUS_PATCHER_HEADLESS", "1")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from limbus_patcher.app_state import AppContext  # noqa: E402
from limbus_patcher.config import AppPaths  # noqa: E402
from limbus_patcher.ui import theme  # noqa: E402
from limbus_patcher.ui.main_window import MainWindow  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "game"
FONTS = ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
         "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/Deng.ttf")


def _register_fonts() -> None:
    for p in FONTS:
        if Path(p).is_file():
            QFontDatabase.addApplicationFont(p)


def _pump(app: QApplication, n: int = 4) -> None:
    for _ in range(n):
        app.processEvents()


def _build_ctx(tmp: Path) -> AppContext:
    game = tmp / "game"
    shutil.copytree(FIXTURES, game)
    ctx = AppContext(AppPaths.from_root(tmp / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    return ctx


def _new_window(app: QApplication, ctx: AppContext, tid: str) -> MainWindow:
    theme.apply_theme(app, tid)
    win = MainWindow(ctx, startup_backup=False)
    win.resize(1460, 920)
    win.show()
    win._index_ready()
    _pump(app)
    return win


def _first_playable_stage(win: MainWindow) -> tuple[str, str] | None:
    book = win.ctx.storybook
    for ch in book.chapter_list():
        cid = ch.get("chapter_id")
        if not cid:
            continue
        for st in book.stages_of(cid):
            code = st.get("stage_code")
            if code and book.stage(cid, code) is not None:
                return cid, code
    return None


def shoot(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    _register_fonts()

    tmp = Path(tempfile.mkdtemp(prefix="review-"))
    ctx = _build_ctx(tmp)
    written: list[Path] = []

    # ---- 默认主题（第一版 AURUM 暗金）的各界面 ----
    win = _new_window(app, ctx, theme.DEFAULT_THEME)

    win._on_nav_category("main_story")
    _pump(app, 6)
    p = out_dir / "01-工作台.png"
    win.grab().save(str(p)); written.append(p)

    # 状态药丸：点开完整清单（浮层是独立顶层窗口，得单独抓）
    win.status_pill.toggle_popover()
    _pump(app, 4)
    pop = win.status_pill._pop
    if pop is not None and pop.isVisible():
        p = out_dir / "02-状态药丸.png"
        pop.grab().save(str(p)); written.append(p)
        pop.hide()
    _pump(app, 2)

    # 主题切换器：展开「风格 · XX」浮层（原型 #themePop）
    win.theme_switch._open_popover()
    _pump(app, 4)
    menu = win.theme_switch._pop
    if menu is not None and menu.isVisible():
        p = out_dir / "03-风格切换器.png"
        menu.grab().save(str(p)); written.append(p)
        win.theme_switch._close_popover()
    _pump(app, 2)

    # 人格图鉴
    win.open_codex()
    _pump(app, 8)
    p = out_dir / "04-人格图鉴.png"
    win.grab().save(str(p)); written.append(p)

    # 敌方图鉴
    win.open_enemy_codex()
    _pump(app, 8)
    p = out_dir / "05-敌方图鉴.png"
    win.grab().save(str(p)); written.append(p)

    # 剧本模式
    win.center_stack.setCurrentIndex(0)
    _pump(app, 2)
    stage = _first_playable_stage(win)
    if stage is not None:
        win._enter_script_mode(*stage)
        _pump(app, 8)
        p = out_dir / "06-剧本模式.png"
        win.grab().save(str(p)); written.append(p)
        print(f"[ok] 剧本模式用 {stage[0]} / {stage[1]}")
    else:
        print("[skip] 没找到可进入的关卡（剧本模式跳过）")

    # 导航分区：把分区全部展开，看清「人格 / E.G.O」下的 role:/entities: 虚拟入口
    win.center_stack.setCurrentIndex(0)
    win._on_nav_category("main_story")
    _pump(app, 4)
    for item in win.nav._zone_headers.values():
        item.setExpanded(True)
    win.nav.tree.expandAll()
    _pump(app, 4)
    p = out_dir / "08-导航分区.png"
    win.nav.grab().save(str(p)); written.append(p)

    topbars = {}
    topbars[theme.DEFAULT_THEME] = win.topbar.grab()
    win.close()
    _pump(app, 2)

    # ---- 另外两套主题的顶栏（供对比）----
    for tid in ("bus", "mini-light"):
        w2 = _new_window(app, ctx, tid)
        w2._on_nav_category("main_story")
        _pump(app, 4)
        topbars[tid] = w2.topbar.grab()
        w2.close()
        _pump(app, 2)

    # ---- 拼一张三主题顶栏对比 ----
    try:
        from PIL import Image, ImageDraw, ImageFont

        label_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
        order = [theme.DEFAULT_THEME, "bus", "mini-light"]
        imgs = []
        for tid in order:
            img = topbars[tid].toImage()
            buf = out_dir / f".tmp-{tid}.png"
            img.save(str(buf))
            imgs.append((tid, Image.open(str(buf)).convert("RGB")))
            buf.unlink()

        pad, label_w = 16, 150
        W = max(i.width for _, i in imgs) + label_w + pad * 2
        H = sum(i.height for _, i in imgs) + pad * (len(imgs) + 1)
        comp = Image.new("RGB", (W, H), (24, 26, 30))
        dr = ImageDraw.Draw(comp)
        y = pad
        for tid, im in imgs:
            mark = "（默认）" if tid == theme.DEFAULT_THEME else ""
            dr.text((pad, y + im.height // 2 - 12), f"{theme.THEME_LABELS[tid]}{mark}",
                    font=label_font, fill=(240, 235, 225))
            comp.paste(im, (label_w + pad, y))
            y += im.height + pad
        p = out_dir / "07-三主题顶栏.png"
        comp.save(str(p)); written.append(p)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 拼图失败（{exc}），跳过 07")

    return written


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "ui-redesign" / "review"
    written = shoot(out)
    print(f"\n共 {len(written)} 张 → {out}")
    for p in written:
        print(f"  {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
