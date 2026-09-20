"""端到端演示（离屏运行）：首次引导 → 索引 → 搜索 → 编辑 → 应用 → 兼容检查 → 清空 → 停用 → 备份恢复。

同时校验安全保证：
- 零协原包（LLC_zh-CN）全程哈希不变；
- config.json 未知键保留；
- 副本包写入为 UTF-8 BOM；
- 备份可恢复损坏的方案。

用法：python scripts/demo.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from limbus_patcher.app_state import AppContext  # noqa: E402
from limbus_patcher.config import AppPaths  # noqa: E402
from limbus_patcher.fsutil import load_json, sha256_file  # noqa: E402
from limbus_patcher.ui.main_window import MainWindow  # noqa: E402
from limbus_patcher.ui.theme import apply_theme  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "✔" if cond else "✘"
    print(f"  [{mark}] {name}" + (f"  —— {detail}" if detail and not cond else ""))
    if not cond:
        sys.exit(f"演示失败：{name}")


def llc_hashes(game: Path) -> dict[str, str]:
    llc = game / "LimbusCompany_Data" / "Lang" / "LLC_zh-CN"
    return {str(p.relative_to(llc)).replace("\\", "/"): sha256_file(p) for p in llc.rglob("*.json") if p.is_file()}


def main() -> None:
    app = QApplication([])
    apply_theme(app)

    sandbox = Path(tempfile.mkdtemp(prefix="lbc_demo_"))
    game = sandbox / "game"
    shutil.copytree(FIXTURES / "game", game)
    ap = AppPaths.from_root(sandbox / "app")
    print(f"沙盒目录：{sandbox}")

    ctx = AppContext(ap)
    win = MainWindow(ctx)
    win.show()

    print("\n1. 首次启动与环境检测")
    check("未选择目录时显示引导页", win.stack.currentWidget() is win.onboarding)

    ctx.set_game_dir(str(game))
    win._show_page()
    check("选择目录后进入工作台", win.stack.currentWidget() is win.workspace)
    check("零协汉化识别", ctx.env.llc_ok and ctx.env.llc_file_count == 8)

    print("\n2. 文本索引（同步执行）")
    llc = ctx.game_paths.llc_pack_dir
    result = ctx.indexer.build(llc)
    win._index_ready()
    check("索引完成（7 文件 / 34 文本叶子）", result.total_files == 7 and result.total_entries == 34)
    check("分类计数（战斗效果=1）", ctx.search.count_by_category()["combat"] == 1)
    check("章节筛选（第1章→StoryData）", ctx.search.search(chapter="c1") and all(
        h.file.startswith("StoryData/") for h in ctx.search.search(chapter="c1")))
    check("赛季筛选（基础→人格/E.G.O 基础条目）", ctx.search.search(season="base") and all(
        h.file in ("Personalities.json", "Egos.json") for h in ctx.search.search(season="base")))

    print("\n3. 搜索与编辑")
    win.list_panel.search_edit.setText("群体攻击")
    win._on_search_requested("群体攻击")
    hits = win.list_panel.model._hits
    check("搜索命中「群体攻击」", hits and any(v.hit.text == "群体攻击" for v in hits))
    view = next(v for v in hits if v.hit.text == "群体攻击")
    win._on_hit_activated(view)
    check("编辑区载入原文", win.editor.original_edit.toPlainText() == "群体攻击")
    win.editor.custom_edit.setPlainText("群体攻击！")
    win._on_save(view.hit.ref, "群体攻击！")
    check("保存到方案（1 条修改）", ctx.profile.count() == 1 and not ctx.profile_dirty)
    win.refresh_topbar()
    check("顶部状态：已保存", win.save_chip.text() == "已保存")

    print("\n4. 应用到游戏（安全写入）")
    before = llc_hashes(game)
    report = ctx.apply()
    check("应用成功", report.ok and report.files_written == 1, "; ".join(report.errors))
    win.refresh_topbar()
    cfg, _ = load_json(ctx.game_paths.config_path)
    check("config.json.lang 指向副本包", cfg["lang"] == ctx.config.patch_pack_name)
    check("config.json 未知键保留", cfg.get("futureKey") == "keep-me")
    check("零协原包哈希不变（未写一字）", llc_hashes(game) == before)
    clone_bk = ctx.game_paths.patch_pack_dir(ctx.config.patch_pack_name) / "BattleKeywords.json"
    check("副本包为 UTF-8 BOM", clone_bk.read_bytes().startswith(b"\xef\xbb\xbf"))
    data, _ = load_json(clone_bk)
    area = next(e for e in data["dataList"] if e["id"] == "AreaAtk")
    check("副本包中修改生效", area["name"] == "群体攻击！")
    check("顶部状态：已应用", win.apply_chip.text() == "已应用")

    print("\n5. 汉化更新兼容性")
    bk_path = llc / "BattleKeywords.json"
    bk_path.write_text(bk_path.read_text(encoding="utf-8").replace("群体攻击", "群体攻击（汉化更新后）"), encoding="utf-8")
    compat = ctx.compat_status()
    check("条目被判为「建议确认」", any(s == "changed" for s, _ in compat.values()))
    win.refresh_topbar()
    check("顶部出现待确认提醒", "待确认" in win.pending_chip.text())

    print("\n6. 清空与停用")
    report = ctx.clear_all()
    check("清空成功且副本包仍为纯镜像", report.ok and ctx.profile.count() == 0 and ctx.apply_view().applied)
    ctx.disable()
    cfg, _ = load_json(ctx.game_paths.config_path)
    check("停用后 lang 回到 LLC_zh-CN", cfg["lang"] == "LLC_zh-CN")

    print("\n7. 备份与恢复")
    ctx.profile.name = "损坏前"
    ctx.save_profile()
    z = ctx.backup.backup("demo")
    check("备份创建", z is not None and z.is_file())
    (ap.profiles_dir / "default.json").write_text("corrupted!!", encoding="utf-8")
    ctx.load_profile()
    check("损坏检测：回退为空方案", ctx.profile.count() == 0)
    names = ctx.backup.restore(z)
    ctx.load_profile()
    check("从备份恢复成功", "profiles" in names and ctx.profile.name == "损坏前")

    print("\n全部演示步骤通过 ✔")
    print(f"沙盒数据保留在：{sandbox}（可手动检查）")


if __name__ == "__main__":
    main()
