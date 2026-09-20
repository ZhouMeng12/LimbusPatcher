"""离屏渲染「选择罪人」页，导出预览图（给人工看 2 行 × 6 列竖版卡的效果）。

只读：用真实零协包在临时目录建索引，卡面从仓库 data/portraits 复制 12 张基础人格卡。
"""
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["DSH_NO_MODAL"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QGridLayout  # noqa: E402

from limbus_patcher.app_state import AppContext  # noqa: E402
from limbus_patcher.config import AppPaths  # noqa: E402
from limbus_patcher.ui import theme  # noqa: E402
from limbus_patcher.ui.codex_page import SINNER_CARD_IMG_H, SINNER_CARD_W, CodexPage  # noqa: E402

TMP = ROOT / "data" / "tmp" / "preview"
shutil.rmtree(TMP, ignore_errors=True)
portraits = TMP / "data" / "portraits" / "identity"
portraits.mkdir(parents=True)
copied = 0
for code in range(1, 13):
    src = ROOT / "data" / "portraits" / "identity" / f"1{code:02d}01.webp"
    if src.is_file():
        shutil.copy2(src, portraits / src.name)
        copied += 1
print("复制卡面", copied, "张")

app = QApplication.instance() or QApplication([])
theme.apply_theme(app)
ctx = AppContext(AppPaths.from_root(TMP))
ctx.set_game_dir("D:/SteamLibrary/steamapps/common/Limbus Company")
ctx.ensure_index()

out = ROOT / "data" / "tmp"
out.mkdir(parents=True, exist_ok=True)
import limbus_patcher.ui.codex_page as cp  # noqa: E402

for anchor in (0.35, 0.5, 0.65):      # 三档水平锚点各出一张，挑一个不切脸的
    cp.SINNER_CROP_ANCHOR_X = anchor
    page = cp.CodexPage(ctx)
    page.resize(1150, 620)
    page.show()
    app.processEvents()
    target = out / f"罪人页预览_锚点{anchor:.2f}.png"
    page.grab().save(str(target))
    print("预览图:", target)
cp.SINNER_CROP_ANCHOR_X = 0.5

# 版面校验：2 行 × 6 列、卡尺寸、每张卡的文字
from PySide6.QtWidgets import QLabel  # noqa: E402

from limbus_patcher.ui.codex_page import _Card  # noqa: E402

cards = page.findChildren(_Card)
grid = page.findChild(QGridLayout)
positions = []
for i, card in enumerate(cards):
    idx = grid.indexOf(card) if grid else -1
    if idx >= 0:
        r, c, _rs, _cs = grid.getItemPosition(idx)
        positions.append((r, c))
    texts = [lbl.text() for lbl in card.findChildren(QLabel) if lbl.text()]
    print(f"  {card.size().width()}x{card.size().height()} 行{positions[-1] if positions else '?'} {texts}")
print("卡片数", len(cards), "· 行数", len({r for r, _c in positions}), "· 每行", len({c for _r, c in positions}))
print("卡尺寸常量", SINNER_CARD_W, "x", SINNER_CARD_IMG_H + 44)
shutil.rmtree(TMP, ignore_errors=True)
