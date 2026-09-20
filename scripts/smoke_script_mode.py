"""剧本模式集成冒烟（真实零协数据 + 三个并行代理的改动）。

覆盖：
A. 顶部入口进入剧本模式；真实关卡载入
B. 灰色未对齐行点击 → ManualMatchDialog（打桩） → 建立对应 → 面板刷新 + 焦点前移
C. 键盘流：↓/↑ 移动、Ctrl+↓ 跳未对齐、S 标记跳过、Enter 打开已对齐行到编辑器
D. 右键批量：contiguous_unaligned + plan_batch + _on_script_batch（打桩 BatchMatchDialog）
E. 候选排序：ManualMatchDialog 候选「未占用优先 + 相似度降序」
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["DSH_NO_MODAL"] = "1"

REPO = Path(r"D:\Desktop\lbc")
GAME = Path(r"D:/SteamLibrary/steamapps/common/Limbus Company")
sys.path.insert(0, str(REPO))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from limbus_patcher.app_state import AppContext  # noqa: E402
from limbus_patcher.config import AppPaths  # noqa: E402
from limbus_patcher.ui import batch_dialog as bd  # noqa: E402
from limbus_patcher.ui import main_window as mw  # noqa: E402
from limbus_patcher.ui import mapping_dialog as md  # noqa: E402
from limbus_patcher.ui import theme  # noqa: E402
from limbus_patcher.ui.main_window import MainWindow  # noqa: E402
from limbus_patcher.patch import ref_label
from limbus_patcher.ui.script_panel import ScriptLineRow  # noqa: E402

OK, FAIL = [], []


def check(name: str, cond: bool, extra: str = "") -> None:
    (OK if cond else FAIL).append(name)
    print(("  [OK]  " if cond else "  [FAIL]") + f" {name}" + (f"  {extra}" if extra else ""))


class FakeManual(QDialog):
    """打桩：直接返回 (record, 候选里第一个未占用记录)。"""

    payload: tuple = ("record", None)

    def __init__(self, parent, text, relfile, candidates, **kw):
        super().__init__(parent)
        self.result_value = self.payload if self.payload[0] != "record" else ("record", candidates[0]["record"])
        self.seen_candidates = list(candidates)
        self.seen_text = text
        FakeManual.last = self


class FakeBatch(QDialog):
    payload: tuple = (None, 0, 0)  # (start_record, count)

    def __init__(self, parent, items, candidates, **kw):
        super().__init__(parent)
        start, count = self.payload[0], self.payload[1]
        if start is None:
            free = [c for c in candidates if not c.get("used") and str(c.get("content") or "").strip()]
            start = free[0]["record"] if free else None
        self.result_value = None if start is None else (start, count)
        self.seen_items = list(items)
        self.seen_candidates = list(candidates)
        FakeBatch.last = self


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="lbc_smoke_"))
    print(f"临时数据目录: {tmp}")
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)

    ctx = AppContext(AppPaths.from_root(tmp / "app"))
    ctx.set_game_dir(str(GAME))
    check("零协汉化检测", ctx.env.llc_ok, str(ctx.env.llc_pack_dir))

    mw.MainWindow._ensure_index_async = lambda self, force=False: None  # 冒烟不建索引
    mw.safe_exec = lambda dlg, *a, **k: dlg.DialogCode.Accepted  # 打桩对话框一律“确定”
    md.ManualMatchDialog = FakeManual
    bd.BatchMatchDialog = FakeBatch

    win = MainWindow(ctx)
    win.show()
    win._index_ready()

    # ---------- A. 进入剧本模式 ----------
    print("\nA. 顶部入口 / 关卡载入")
    win.script_btn_top.click()
    check("剧本模式已激活", win._script_active and win.script_panel.isVisible())
    book = ctx.storybook
    stages = [s for c in book.chapter_list() for s in c.get("stages", []) if s.get("items")]
    check("存在含条目的关卡", bool(stages), f"{len(stages)} 个")
    check("剧本数据自检无问题", not book.problems, "; ".join(book.problems[:3]))

    # 选未对齐行最多的关卡（同时含已对齐行），便于覆盖键盘与批量流程
    cands_stage = []
    for c in book.chapter_list():
        for s in c.get("stages", []):
            items = s.get("items") or []
            un = sum(1 for i in items if i.get("type") == "line" and i.get("wiki_only") and i.get("key")
                     and not i.get("skip"))
            al = sum(1 for i in items if i.get("type") == "line" and isinstance(i.get("record"), int))
            if un >= 4 and al:
                cands_stage.append((un, al, c["chapter_id"], s["stage_code"]))
    cands_stage.sort(reverse=True)
    target = (cands_stage[0][2], cands_stage[0][3]) if cands_stage else None
    check("找到同时含已对齐/未对齐行的关卡", target is not None, str(target))
    if not target:
        return 1
    cid, code = target
    win._enter_script_mode(cid, code)
    rows = win.script_panel.line_rows()
    grey = [r for r in rows if r.wiki_only and not r.skipped]
    aligned = [r for r in rows if r.is_aligned]
    print(f"  关卡 {cid}/{code}: 行 {len(rows)}，未对齐 {len(grey)}，已对齐 {len(aligned)}")
    check("未对齐行渲染为灰色（wiki_only）", bool(grey))
    check("焦点默认落在首条对话行", win.script_panel.current_row() is not None)

    # ---------- B. 灰行点击 → 手动对应 ----------
    print("\nB. 灰色行点击 → 建立对应")
    row = grey[0]
    page, key, relfile = row.item["page"], row.item["key"], row.item["file"]
    QTest.mouseClick(row, Qt.MouseButton.LeftButton)
    dlg = getattr(FakeManual, "last", None)
    check("点击灰行打开「建立对应」对话框", dlg is not None)
    check("对话框中给出可用候选记录", bool(dlg and dlg.seen_candidates))
    ov_path = ctx.story_edit.overrides_path
    ov = json.loads(ov_path.read_text("utf-8")) if ov_path.is_file() else {}
    rec = ov.get(page, {}).get(key, {}).get("record")
    check("覆盖表写入手动对应", isinstance(rec, int), f"{page}/{key} -> {rec}")
    rows2 = win.script_panel.line_rows()
    same = [r for r in rows2 if r.item.get("page") == page and r.item.get("key") == key]
    check("刷新后该行变为已对齐（可编辑）", bool(same) and same[0].is_aligned)
    nxt = win.script_panel.current_item()
    check("焦点前移到下一条未对齐行", bool(nxt) and nxt.get("key") != key and bool(nxt.get("wiki_only")),
          str(nxt and nxt.get("key")))

    # ---------- C. 键盘流 ----------
    print("\nC. 键盘流")
    rows = win.script_panel.line_rows()
    first_un = next(i for i, r in enumerate(rows) if r.is_unaligned)
    win.script_panel.setFocus()
    win.script_panel.set_focus_index(0)
    QTest.keyClick(win.script_panel, Qt.Key.Key_Down)
    check("↓ 下移一行", win.script_panel.focus_index() == 1)
    QTest.keyClick(win.script_panel, Qt.Key.Key_Up)
    check("↑ 上移一行", win.script_panel.focus_index() == 0)
    win.script_panel.set_focus_index(first_un - 1 if first_un > 0 else first_un)
    base = win.script_panel.focus_index()
    QTest.keyClick(win.script_panel, Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier)
    i1 = win.script_panel.focus_index()
    cur1 = win.script_panel.current_row()
    check("Ctrl+↓ 跳到未对齐行", cur1 is not None and cur1.is_unaligned and i1 > base, f"index={i1}")
    QTest.keyClick(win.script_panel, Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier)
    i2 = win.script_panel.focus_index()
    check("Ctrl+↓ 继续跳到下一条未对齐行", i2 > i1 and win.script_panel.current_row().is_unaligned)
    QTest.keyClick(win.script_panel, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier)
    check("Ctrl+↑ 回到上一条未对齐行", win.script_panel.focus_index() == i1)

    # S：标记跳过
    skip_row = win.script_panel.current_row()
    check("当前行是未对齐行（可标记跳过）", skip_row is not None and skip_row.is_unaligned)
    spage, skey = skip_row.item["page"], skip_row.item["key"]
    QTest.keyClick(win.script_panel, Qt.Key.Key_S)
    ov = json.loads(ov_path.read_text("utf-8")) if ov_path.is_file() else {}
    check("S 标记跳过写入覆盖表", ov.get(spage, {}).get(skey, {}).get("skip") is True, f"{spage}/{skey}")
    rows3 = win.script_panel.line_rows()
    chk = [r for r in rows3 if r.item.get("page") == spage and r.item.get("key") == skey]
    menu_items = [a.text() for a in win.script_panel.row_menu(chk[0]).actions() if a.text()] if chk else []
    check("跳过行不再算未对齐（菜单改为取消跳过/删除）",
          bool(chk) and not chk[0].is_unaligned
          and menu_items == ["取消跳过（恢复为未对齐）", "删除该行（从剧本中移除）"], str(menu_items))
    # 取消跳过 → 回到未对齐
    win._on_script_unskip(chk[0].item)
    ov = json.loads(ov_path.read_text("utf-8")) if ov_path.is_file() else {}
    back = [r for r in win.script_panel.line_rows() if r.item.get("key") == skey]
    check("取消跳过：覆盖被清除、行回到未对齐",
          bool(back) and back[0].is_unaligned and skey not in ov.get(spage, {}))

    # Enter：打开已对齐行到编辑器
    rows4 = win.script_panel.line_rows()
    ai = next(i for i, r in enumerate(rows4) if r.is_aligned)
    win.script_panel.set_focus_index(ai)
    QTest.keyClick(win.script_panel, Qt.Key.Key_Return)
    hit = win._current_hit
    check("Enter 打开已对齐行到编辑器", hit is not None and hit.ref.file == rows4[ai].item["file"],
          str(hit and hit.ref.file))
    check("编辑器显示出零协原文", bool(win.editor.original_edit.toPlainText().strip()),
          repr(win.editor.original_edit.toPlainText()[:24]))

    # ---------- D. 右键批量 ----------
    print("\nD. 右键批量对应")
    win._enter_script_mode(cid, code)
    rows = win.script_panel.line_rows()
    g = next((r for r in rows if r.is_unaligned), None)
    check("仍有未对齐行可用于批量", g is not None)
    if g:
        run = win.script_panel.contiguous_unaligned(g.item)
        check("连续未对齐段识别", bool(run) and run[0]["key"] == g.item["key"], f"{len(run)} 条")
        FakeBatch.payload = (None, min(3, len(run)))
        used = win._used_records(g.item["page"])
        cands = ctx.story_edit.candidates(g.item["file"], used)
        plan = bd.plan_batch(run, cands[0]["record"] if cands else 0, 3, used, cands)
        check("plan_batch 顺序分配", len(plan) >= 1 and len({r for _, r in plan}) == len(plan), str(plan[:3]))
        before = dict(json.loads(ov_path.read_text("utf-8")) if ov_path.is_file() else {})
        win._on_script_batch(g.item)
        ov2 = json.loads(ov_path.read_text("utf-8")) if ov_path.is_file() else {}
        new = {(p, k) for p, d in ov2.items() for k, v in d.items()
               if v.get("record") is not None
               and before.get(p, {}).get(k, {}).get("record") != v.get("record")}
        check("批量写入多条对应", len(new) >= 1, f"新增 {len(new)} 条: {sorted(new)[:3]}")
        rows5 = win.script_panel.line_rows()
        got = [r for r in rows5 if (r.item.get("page"), r.item.get("key")) in new]
        check("批量后这些行变为已对齐", len(got) == len(new),
              f"{len(got)}/{len(new)}（已对齐 {sum(1 for r in got if r.is_aligned)}）")

    # ---------- D2. 删除未对应行 / 恢复 ----------
    print("\nD2. 删除未对应行")
    win._enter_script_mode(cid, code)
    target = next((r for r in win.script_panel.line_rows() if r.is_unaligned), None)
    check("仍有未对齐行可用于删除", target is not None)
    if target:
        dpage, dkey = target.item["page"], target.item["key"]
        win.script_panel.set_focus_index(win.script_panel.line_rows().index(target))
        QTest.keyClick(win.script_panel, Qt.Key.Key_Delete)
        ov = json.loads(ov_path.read_text("utf-8")) if ov_path.is_file() else {}
        check("Delete 写入删除覆盖", ov.get(dpage, {}).get(dkey, {}).get("deleted") is True, f"{dpage}/{dkey}")
        keys = [r.item.get("key") for r in win.script_panel.line_rows()]
        check("删除后该行从剧本中消失", dkey not in keys)
        check("统计显示已删除行数", "删除 1" in win.script_panel.info_label.text(),
              win.script_panel.info_label.text()[-24:])
        # 勾选「显示已删除」→ 删除线灰字 → 恢复
        win.script_panel.show_deleted_cb.setChecked(True)
        hidden = next((r for r in win.script_panel.line_rows() if r.item.get("key") == dkey), None)
        check("显示已删除：行带删除线样式", hidden is not None and hidden.is_deleted
              and hidden.text_widget.font().strikeOut())
        if hidden:
            check("已删除行菜单为「恢复该行」",
                  [a.text() for a in win.script_panel.row_menu(hidden).actions()] == ["恢复该行"])
            win._on_script_restore(hidden.item)
            ov = json.loads(ov_path.read_text("utf-8")) if ov_path.is_file() else {}
            check("恢复该行：覆盖清除", dkey not in ov.get(dpage, {}))
            win.script_panel.show_deleted_cb.setChecked(False)
            back2 = [r for r in win.script_panel.line_rows() if r.item.get("key") == dkey]
            check("恢复后回到未对齐行", bool(back2) and back2[0].is_unaligned)

    # ---------- E. 候选排序（真实对话框构造，不 exec） ----------
    print("\nE. 候选排序")
    rows = win.script_panel.line_rows()
    g = next((r for r in rows if r.is_unaligned), None)
    if g:
        import importlib
        mod = importlib.reload(importlib.import_module("limbus_patcher.ui.mapping_dialog"))
        used = win._used_records(g.item["page"])
        cands = ctx.story_edit.candidates(g.item["file"], used)
        d = mod.ManualMatchDialog(None, g.item.get("text", ""), g.item["file"], cands[:80])
        n = min(12, d.listw.count())
        order = [d.listw.item(i).data(Qt.ItemDataRole.UserRole) for i in range(n)]
        by_rec = {c["record"]: c for c in cands}
        flags = [bool(by_rec[r]["used"]) for r in order]
        from difflib import SequenceMatcher
        tgt = mod.norm_text(g.item.get("text", ""))
        sims = [SequenceMatcher(None, tgt, mod.norm_text(by_rec[r]["content"])).ratio() for r in order]
        top = flags[:sum(1 for f in flags if not f)] if False else flags
        check("未占用记录整体排在已占用之前", flags == sorted(flags), str(flags[:8]))
        free_sims = [s for f, s in zip(flags, sims) if not f]
        check("未占用组内按相似度降序", free_sims == sorted(free_sims, reverse=True),
              str([round(s, 2) for s in free_sims[:5]]))
        check("显示文本含百分比与记录号",
              bool(d.listw.count()) and "%" in d.listw.item(0).text() and "[" in d.listw.item(0).text(),
              d.listw.item(0).text()[:48])
        # 过滤框可用
        d.search.setText(str(order[0]))
        check("过滤后仍有结果", d.listw.count() >= 1, f"{d.listw.count()} 条")
    else:
        print("  （已无未对齐行，跳过 E）")

    # ---------- F. 只看未对应 + 自动建议对应 ----------
    print("\nF. 只看未对应 + 自动建议")
    win._enter_script_mode(cid, code)
    win.script_panel.unaligned_only_cb.setChecked(True)
    only = win.script_panel.line_rows()
    check("只看未对应：只剩未对齐行",
          bool(only) and all(r.is_unaligned for r in only), f"{len(only)} 行")
    check("进度统计可见", "本关" in win.script_panel.info_label.text() and "%" in win.script_panel.info_label.text(),
          win.script_panel.info_label.text())
    win._enter_script_mode(cid, code)  # 重新载入关卡，清掉筛选
    win.script_panel.unaligned_only_cb.setChecked(False)
    check("取消筛选后恢复全部行", len(win.script_panel.line_rows()) > len(only))

    from limbus_patcher.ui import suggest_dialog as sd
    real_suggest = sd.SuggestDialog

    class FakeSuggest(sd.SuggestDialog):
        """打桩：直接全选通过（减少真实鼠标操作）。"""

        def __init__(self, parent, suggestions, scope_label=""):
            super().__init__(parent, suggestions, scope_label)
            self.result_value = list(suggestions)

    used_all = win._used_records_all()
    suggestions = ctx.story_edit.suggest_matches(win.script_panel.unaligned_items(), used_all)
    pct = round(max((s["similarity"] for s in suggestions), default=0) * 100)
    check("自动建议：本关找到可配对的行", bool(suggestions), f"{len(suggestions)} 条，最高 {pct}%")
    if suggestions:
        sd.SuggestDialog = FakeSuggest
        before_keys = {r.item.get("key") for r in win.script_panel.line_rows() if r.is_aligned}
        win._on_script_suggest(win.script_panel.unaligned_items()[0])
        sd.SuggestDialog = real_suggest
        after_rows = win.script_panel.line_rows()
        new_aligned = [r for r in after_rows if r.is_aligned and r.item.get("key") not in before_keys]
        check("自动建议写入后行变为已对齐", len(new_aligned) >= 1, f"新增已对齐 {len(new_aligned)} 行")
        ov = json.loads(ov_path.read_text("utf-8")) if ov_path.is_file() else {}
        auto = [(p, k) for p, d in ov.items() for k, v in d.items()
                if isinstance(v, dict) and v.get("certainty") == "auto"]
        check("覆盖表标记为自动建议", len(auto) >= 1, f"{len(auto)} 条")

    # ---------- G. 无 KeyID 记录（人格剧情）端到端 ----------
    print("\nG. 无 KeyID 记录可搜索可编辑")
    import sqlite3

    db = ctx.app_paths.cache_dir / "index.sqlite"
    if not db.is_file():
        ctx.indexer.build(ctx.game_paths.llc_pack_dir, baseline_dir=ctx.baseline_dir)  # 真实包约 9s
    con = sqlite3.connect(str(db))
    row = con.execute(
        "select f.relpath, e.record_index, e.text from entries e "
        "join files f on f.file_id = e.file_id "
        "where f.relpath like 'StoryData/P%' and e.id_json = 'null' limit 1"
    ).fetchone()
    con.close()
    check("索引里存在无 KeyID 的记录", row is not None, str(row and row[0]))
    if row:
        rel, rec_index, text = row
        hits = ctx.search.search((text or "")[:8], limit=20)
        match = [h for h in hits if h.ref.file == rel]
        check("无 KeyID 记录能被搜索到", bool(match), f"{len(match)} 条命中（{rel}）")
        if match:
            hit = match[0]
            label = getattr(hit, "display_key", None) or ref_label(hit.ref)
            check("显示为「记录 #N」而不是 None", "None" not in str(label), str(label))
            original, err = ctx.original_of(hit.ref)
            check("能读到原文", original is not None and original.strip() != "", str(err))
            res = ctx.upsert_entry(hit.ref, "冒烟：无 KeyID 记录修改")
            check("能保存到方案", res.ok, res.message)
            ctx.remove_entry(hit.ref)

    # ---------- H. 英语原文（真实基线） ----------
    print("\nH. 英语原文对照")
    win._enter_script_mode(cid, code)
    row = next((r for r in win.script_panel.line_rows() if r.is_aligned and r.item.get("record") is not None), None)
    check("找到已对齐行用于英文对照", row is not None)
    if row:
        win._on_script_line(row.item)
        en_hits, en_total = ctx.search.baseline_stats()
        check("索引里英文覆盖达到预期（≥160000 条）", en_hits >= 160000, f"{en_hits}/{en_total}")
        check("编辑器存在英语原文栏", hasattr(win.editor, "baseline_edit") and win.editor.baseline_edit.isReadOnly())
        win.editor.set_baseline_visible(True)
        en_text = win.editor.baseline_edit.toPlainText()
        check("英文栏有内容或给出中文原因",
              bool(en_text.strip()) or bool(win.editor.baseline_edit.placeholderText().strip()),
              (en_text or win.editor.baseline_edit.placeholderText())[:36])
        win.editor.set_baseline_visible(False)
        check("英文栏可收起", not win.editor.baseline_visible())
        # 英文搜索：用英文栏里的词反查，应当能找回同一条
        word = (en_text.strip().split()[0] if en_text.strip() else "")
        if len(word) >= 3:
            hits = ctx.search.search(word, scope="baseline", limit=40)
            both = ctx.search.search(word, scope="all", limit=40)
            check("英文关键词能搜到条目", bool(hits), f"{word!r} → {len(hits)} 条；全部范围 {len(both)} 条")
    baseline_dir = ctx.baseline_dir
    check("英文基线目录已定位", baseline_dir is not None and baseline_dir.is_dir(),
          str(baseline_dir))

    # ---------- I. 人格 / E.G.O 实体 ----------
    print("\nI. 人格 / E.G.O 实体化")
    win._exit_script_mode()  # 实体导航在条目模式下
    eng = ctx.search
    pers = eng.list_entities("personality")
    egos = eng.list_entities("ego")
    # 愚人节整活人格按需求已从图鉴剔除（entity_exclude.json），这里按「≥180」兜底
    check("人格实体齐全（≥180）", len(pers) >= 180, f"{len(pers)} 个")
    check("E.G.O 实体齐全（≥110）", len(egos) >= 110, f"{len(egos)} 个")
    roles = eng.count_by_role()
    check("人格剧情已从主线拆出", roles.get("identity_story", 0) >= 20000, f"{roles.get('identity_story')} 叶子")
    check("人格技能/语音/EGO 技能都有归属",
          roles.get("identity_skill", 0) >= 5000 and roles.get("identity_voice", 0) >= 5000
          and roles.get("ego_skill", 0) >= 3000,
          f"技能 {roles.get('identity_skill')} · 语音 {roles.get('identity_voice')} · EGO技能 {roles.get('ego_skill')}")
    sample = next((e for e in pers if e["entity_key"] == "P:10310"), None) or pers[-1]
    info = eng.entity_summary(sample["entity_key"])
    check("实体卡片信息可用", bool(info and info["name"]),
          f"{info['entity_key']} {info['name']} · 技能 {info['skill_count']} · 剧情 {info['story_count']} · 语音 {info['voice_count']}")
    for role, label in (("identity_skill", "技能"), ("identity_story", "剧情"), ("identity_voice", "语音")):
        rows = eng.search("", entity_key=sample["entity_key"], roles=[role], order="natural", limit=5)
        check(f"该人格的{label}可列出", bool(rows), f"{label}示例：{(rows[0].text[:16] if rows else '—')}")
    # 目录导航：实体入口存在
    win._on_nav_category("entities:personality")
    check("人格一览每实体一行", len(win.list_panel.model._hits) == len(pers),
          f"{len(win.list_panel.model._hits)} 行")
    win._open_entity(sample["entity_key"])
    check("从一览跳进实体内容", win.list_panel.current_entity() == sample["entity_key"]
          and len(win.list_panel.model._hits) > 0, f"{len(win.list_panel.model._hits)} 条")
    win._on_nav_category("role:identity_story")
    check("人格剧情跨罪人入口可用", bool(win.list_panel.model._hits),
          f"{len(win.list_panel.model._hits)} 行")

    win.close()
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n结果: OK={len(OK)} FAIL={len(FAIL)}")
    for f in FAIL:
        print("  FAIL:", f)
    return 0 if not FAIL else 2


if __name__ == "__main__":
    raise SystemExit(main())
