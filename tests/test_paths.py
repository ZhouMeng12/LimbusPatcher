from __future__ import annotations

from pathlib import Path

from limbus_patcher import paths
from limbus_patcher.paths import detect_llc_pack, find_steam_library_dirs, is_valid_game_dir, parse_libraryfolders_vdf, resolve_game_paths

VDF_SAMPLE = """
"libraryfolders"
{
\t"0"
\t{
\t\t"path"\t\t"Z:\\\\NoSuchSteamLib99"
\t\t"apps"
\t\t{
\t\t\t"1973530"\t\t"123"
\t\t}
\t}
\t"1"
\t{
\t\t"path"\t\t"Y:\\\\NoSuchSteamLib98"
\t}
}
"""


def test_is_valid_game_dir(game_dir, tmp_path):
    assert is_valid_game_dir(game_dir)
    assert not is_valid_game_dir(tmp_path)


def test_resolve_game_paths(game_dir):
    p = resolve_game_paths(game_dir)
    assert p.exe_path.is_file()
    assert p.lang_dir.is_dir()
    assert p.config_path.is_file()
    assert p.llc_pack_dir.is_dir()
    assert p.en_base_dir().is_dir()
    assert p.patch_pack_dir("X") == p.lang_dir / "X"


def test_detect_llc_pack(game_dir, tmp_path):
    p = resolve_game_paths(game_dir)
    d, layout = detect_llc_pack(p)
    assert d == p.llc_pack_dir and layout == "lang"
    # 旧版布局：游戏根目录
    legacy = tmp_path / "g2"
    (legacy / "LimbusCompany_Data").mkdir(parents=True)
    (legacy / "LimbusCompany.exe").write_text("x", encoding="utf-8")
    (legacy / paths.LLC_PACK_NAME).mkdir()
    lp = resolve_game_paths(legacy)
    d2, layout2 = detect_llc_pack(lp)
    assert d2 == legacy / paths.LLC_PACK_NAME and layout2 == "legacy_root"


def test_parse_libraryfolders_vdf(tmp_path):
    dirs = parse_libraryfolders_vdf(VDF_SAMPLE)
    assert len(dirs) == 0  # 这些路径在本机不存在，应被过滤


def test_find_steam_library_dirs(steam_lib):
    libs = find_steam_library_dirs(steam_path=steam_lib)
    assert steam_lib in libs


def test_find_game_in_steam_lib(steam_lib):
    found = [lib / "steamapps" / "common" / paths.GAME_DIR_NAME for lib in find_steam_library_dirs(steam_path=steam_lib)]
    assert any(is_valid_game_dir(d) for d in found)


def test_llc_pack_name_constants():
    assert paths.LLC_PACK_NAME == "LLC_zh-CN"
    assert paths.DEFAULT_PATCH_PACK_NAME == "LLC_zh-CN_custom"
