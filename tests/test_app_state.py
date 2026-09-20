"""AppContext 端到端：首次引导 → 索引 → 编辑 → 应用 → 清空 → 停用。"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppPaths
from limbus_patcher.fsutil import load_json
from limbus_patcher.patch import EntryRef
from limbus_patcher.paths import resolve_game_paths

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def ctx(tmp_path):
    game = tmp_path / "game"
    shutil.copytree(FIXTURES / "game", game)
    ap = AppPaths.from_root(tmp_path / "app")
    c = AppContext(ap)
    yield c, game, ap


def test_full_flow(ctx):
    c, game, ap = ctx
    # 首次：无目录
    assert not c.env.healthy()
    c.set_game_dir(str(game))
    assert c.env.llc_ok

    # 索引
    assert c.ensure_index() is True
    hits = c.search.search("群体攻击")
    assert hits

    # 编辑
    hit = next(h for h in hits if h.text == "群体攻击")
    res = c.upsert_entry(hit.ref, "群体攻击！")
    assert res.ok and res.entry is not None
    assert c.profile_dirty
    c.save_profile()
    assert not c.profile_dirty

    # 应用
    report = c.apply()
    assert report.ok, report.errors
    cfg, _ = load_json(c.game_paths.config_path)
    assert cfg["lang"] == c.config.patch_pack_name
    view = c.apply_view()
    assert view.applied

    # 兼容状态全 ok
    statuses = c.compat_status()
    assert statuses and all(s == "ok" for s, _ in statuses.values())

    # 单条还原（原文 = 群体攻击）
    res = c.upsert_entry(hit.ref, "群体攻击")
    assert res.entry is None
    c.save_profile()

    # 历史已记录
    hist = c.history.get(hit.ref.key())
    assert hist and hist[0]["new"] == "群体攻击"

    # 清空 → 副本包仍启用、内容与零协一致
    report = c.clear_all()
    assert report.ok
    view = c.apply_view()
    assert view.applied
    clone_bk = c.game_paths.patch_pack_dir(c.config.patch_pack_name) / "BattleKeywords.json"
    data, _ = load_json(clone_bk)
    area = next(e for e in data["dataList"] if e["id"] == "AreaAtk")
    assert area["name"] == "群体攻击"

    # 停用 → lang 回到 LLC_zh-CN
    c.disable()
    cfg, _ = load_json(c.game_paths.config_path)
    assert cfg["lang"] == "LLC_zh-CN"


def test_index_rebuild_on_change(ctx):
    c, game, ap = ctx
    c.set_game_dir(str(game))
    assert c.ensure_index() is True
    assert c.ensure_index() is False  # 未变化不重建
    llc = c.game_paths.llc_pack_dir
    (llc / "BattleKeywords.json").write_text(
        (llc / "BattleKeywords.json").read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    assert c.ensure_index() is True


def test_corrupted_profile_falls_back(ctx):
    c, game, ap = ctx
    ap.profiles_dir.mkdir(parents=True, exist_ok=True)
    (ap.profiles_dir / "default.json").write_text("{bad", encoding="utf-8")
    c2 = AppContext(ap)
    assert c2.profile.count() == 0


def test_upsert_uses_original_text(ctx):
    c, game, ap = ctx
    c.set_game_dir(str(game))
    c.ensure_index()
    hit = c.search.search("清除缓存")[0]
    res = c.upsert_entry(hit.ref, "清除全部缓存")
    assert res.ok
    entry = c.profile.get(hit.ref)
    assert entry is not None and entry.original_hash
    # 与原文一致 → 还原
    res2 = c.upsert_entry(hit.ref, "清除缓存")
    assert res2.ok and res2.entry is None
