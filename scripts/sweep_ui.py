"""UI 全路径冒烟：把主窗口上「用户可能点到」的分支都跑一遍，任何异常都记录。

用途：找出像 `_diff_html` 那样「单元测试覆盖不到、一点就崩」的隐藏路径。
在临时游戏副本上运行，安全（不动真实零协包）。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["DSH_NO_MODAL"] = "1"

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from PySide6.QtWidgets import QApplication  # noqa: E402

from limbus_patcher.app_state import AppContext  # noqa: E402
from limbus_patcher.config import AppPaths  # noqa: E402
from limbus_patcher.ui import theme  # noqa: E402
from limbus_patcher.ui.main_window import MainWindow  # noqa: E402

ERRORS: list[tuple[str, str]] = []


def step(name: str, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except Exception:  # noqa: BLE001
        ERRORS.append((name, traceback.format_exc()))
        print(f"  [CRASH] {name}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="lbc_sweep_"))
    game = tmp / "game"
    shutil.copytree(REPO / "tests" / "fixtures" / "game", game)
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    ctx = AppContext(AppPaths.from_root(tmp / "app"))
    ctx.set_game_dir(str(game))
    ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)
    win = MainWindow(ctx)
    win.show()
    win._index_ready()

    print("A. 导航/筛选/搜索/条目激活")
    cats = ["all", "main_story", "identity", "ego", "enemy", "sinner:04:identity",
            "sinner:04:ego", "main_story:c1", "theater", "battle"]
    for cat in cats:
        step(f"nav {cat}", win._on_nav_category, cat)
        for combo in (win.list_panel.chapter_combo, win.list_panel.level_combo,
                      win.list_panel.season_combo, win.list_panel.kind_combo):
            step(f"nav {cat} filter {combo.objectName()}",
                 lambda c=combo: win._on_filters_changed() if c.count() > 1 else None)

    hits = list(win.list_panel.model._hits)
    print(f"  命中 {len(hits)} 条")
    for i, hit in enumerate(hits[:12]):
        step(f"activate #{i}", win._on_hit_activated, hit)
        ed = win.editor
        step(f"diff toggle #{i}", ed.diff_btn.setChecked, True)
        step(f"diff toggle off #{i}", ed.diff_btn.setChecked, False)
        step(f"advanced #{i}", win.act_advanced.setChecked, True)
        step(f"advanced off #{i}", win.act_advanced.setChecked, False)
        step(f"favorite #{i}", win._on_favorite, ed._ref, True)
        step(f"favorite off #{i}", win._on_favorite, ed._ref, False)
        step(f"history #{i}", win._on_history, ed._ref)
        step(f"story #{i}", win.editor.story_requested.emit)
        step(f"exit story #{i}", win._exit_script_mode)
        step(f"show source #{i}", win._on_show_source, hit)
        step(f"save #{i}", win._on_save, ed._ref, "冒烟文本")

    print("B. 剧本模式：章节/关卡切换 + 行激活 + 跳过/批量")
    step("open script mode", win.open_script_mode)
    if win._script_active:
        for ch in win.ctx.storybook.chapter_list():
            step(f"chapter {ch['chapter_id']}", win._on_script_chapter, ch["chapter_id"])
            for st in win.ctx.storybook.stages_of(ch["chapter_id"])[:3]:
                step(f"stage {ch['chapter_id']}/{st['stage_code']}",
                     win._script_stage_changed, st["stage_code"])
        rows = win.script_panel.line_rows()
        for r in rows[:8]:
            step("row click", win._on_script_line, r.item)
            step("row skip", win._on_script_skip, r.item)
            step("row batch", win._on_script_batch, r.item)
        step("script back", win._exit_script_mode)

    print("C. 顶部/菜单操作")
    step("backup", win.make_backup)
    step("backups dialog", win.open_backups)
    step("apply patch", win.apply_patch)
    step("disable patch", win.disable_patch)
    step("usage", win._usage)
    step("about", win._about)
    step("focus search", win._focus_search)
    step("clear search", win._clear_search)
    step("refresh topbar", win.refresh_topbar)
    step("refresh list", win.refresh_list)
    step("retry env", win.retry_env)
    step("clear all", win.clear_all)
    step("open codex", win.open_codex)
    step("codex sinner grid", lambda: win.codex_page._show_sinners())
    for code in ("01", "03", "12"):
        step(f"codex sinner {code}", lambda c=code: win.codex_page._show_entities(c, "personality"))
    ents = win.ctx.search.list_entities("personality", "03")
    if ents:
        key = ents[0]["entity_key"]
        step("codex entity tabs", lambda k=key: win.codex_page._show_entity(k))
        step("codex identity story", lambda k=key: win.open_identity_story(k))
        step("back to panes", lambda: win.center_stack.setCurrentIndex(0))
        page = win.codex_page
        step("codex passive edit ref", lambda: page._edit(
            page.entity.passives[0].file, page.entity.passives[0].record_index,
            page.entity.passives[0].record_id, page.entity.passives[0].desc_fp,
            "被动说明") if page.entity and page.entity.passives else None)
        step("codex name menu", lambda: page.name_btn.menu().actions()[0].trigger()
             if page.name_btn.menu() and page.name_btn.menu().actions() else None)
        step("codex entity replace", lambda: page._open_entity_replace(page.entity)
             if page.entity else None)

    print("C1. 敌方图鉴（新增页面：分组 / 三个筛选维度 / 实体详情）")
    step("open enemy codex", win.open_enemy_codex)
    epage = getattr(win, "enemy_codex_page", None)
    if epage is not None:
        step("enemy groups", epage._show_groups)
        try:
            groups = list(epage._group_counts())
        except Exception:  # noqa: BLE001
            groups = []
        for g in groups[:6]:
            step(f"enemy group {g}", epage._show_entities, g)
            for combo in (getattr(epage, "chapter_combo", None), getattr(epage, "enemy_combo", None),
                          getattr(epage, "danger_combo", None)):
                if combo is not None:
                    step(f"enemy filter {g}", lambda c=combo: c.setCurrentIndex(min(1, c.count() - 1)))
            step(f"enemy group {g} reset", lambda gg=g: epage._show_entities(gg))
            step("enemy back", epage._go_back)
        step("enemy format toggle", lambda: epage._on_show_format(False))
        step("enemy format toggle on", lambda: epage._on_show_format(True))
        step("enemy keyword toggle", lambda: epage._on_show_keywords(False))
        step("enemy keyword toggle on", lambda: epage._on_show_keywords(True))
        step("back to panes", lambda: win.center_stack.setCurrentIndex(0))

    print("C1.5 补译文件")
    step("supplement dialog", win.manage_supplement)
    step("supplement chip", win.refresh_topbar)

    print("C2. 一键替换（列表范围 / 全库）")
    step("replace current list", lambda: win.batch_replace())
    step("replace whole", lambda: win.batch_replace(whole=True))

    print("C3. 人格一览分组（按赛季 / 获取方式）")
    for cat in ("entities:personality", "entities:ego"):
        step(f"nav {cat}", win._on_nav_category, cat)
        for key in ("", "season", "acq"):
            idx = win.list_panel.group_combo.findData(key)
            step(f"group {cat} {key or 'off'}",
                 lambda i=idx: (win.list_panel.group_combo.setCurrentIndex(max(i, 0)), win.refresh_list()))
        rows = win.list_panel.model.hits()
        step(f"activate first row {cat}", lambda r=rows: win._on_hit_activated(r[0]) if r else None)
    step("rebuild index", lambda: win._index_ready(None))

    win.close()
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n结果: 崩溃 {len(ERRORS)} 处")
    for name, tb in ERRORS:
        print(f"\n===== {name} =====\n{tb}")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    raise SystemExit(main())
