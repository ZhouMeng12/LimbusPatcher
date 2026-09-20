from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GAME = FIXTURES / "game"
LLC = GAME / "LimbusCompany_Data" / "Lang" / "LLC_zh-CN"
STEAM_LIB = FIXTURES / "steam_lib"


@pytest.fixture
def game_dir() -> Path:
    return GAME


@pytest.fixture
def llc_dir() -> Path:
    return LLC


@pytest.fixture
def steam_lib() -> Path:
    return STEAM_LIB


@pytest.fixture
def tmp_game(tmp_path: Path) -> Path:
    """把 fixture 游戏目录复制到临时目录，供会修改文件系统的测试使用。"""
    dst = tmp_path / "game"
    shutil.copytree(GAME, dst)
    return dst


@pytest.fixture(autouse=True)
def isolate_global_overlays():
    """隔离 AppContext 写进模块级全局的状态。

    ``AppContext.__init__`` 会调用 ``categories.set_user_data_dir(data_dir)`` 与
    ``entities.set_enemy_map_overlay(cache_dir)``，而这两者都是**模块级全局**：
    不还原的话，先跑的测试留下的临时目录会一直影响后面所有测试
    （表现为「单独跑通过、一起跑就挂」——test_story / test_categories 都栽在这上面）。
    """
    from limbus_patcher import categories, entities

    prev_data_dir = getattr(categories, "_user_data_dir", None)
    prev_enemy_overlay = getattr(entities, "_ENEMY_MAP_OVERLAY", None)
    try:
        yield
    finally:
        categories.set_user_data_dir(prev_data_dir)
        entities.set_enemy_map_overlay(prev_enemy_overlay)
