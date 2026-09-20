from __future__ import annotations

from limbus_patcher.envcheck import check_environment
from limbus_patcher.paths import resolve_game_paths


def test_no_game_dir():
    st = check_environment(None)
    assert not st.game_dir_ok and any(i.code == "no_game_dir" for i in st.issues)
    assert "未选择" in st.brief()


def test_bad_game_dir(tmp_path):
    st = check_environment(str(tmp_path))
    assert any(i.code == "bad_game_dir" for i in st.issues)


def test_valid_game(game_dir):
    st = check_environment(str(game_dir))
    assert st.game_dir_ok and st.llc_ok
    assert st.llc_layout == "lang"
    assert st.llc_file_count == 9  # 新增 StoryData/S101A.json 主线夹具
    assert st.base_ok
    assert st.config_valid and st.config_lang == "LLC_zh-CN"
    assert st.font_ok
    assert st.patch_pack_exists is False
    assert st.healthy()


def test_no_llc(tmp_path):
    g = tmp_path / "game"
    (g / "LimbusCompany_Data").mkdir(parents=True)
    (g / "LimbusCompany.exe").write_text("x", encoding="utf-8")
    st = check_environment(str(g))
    assert st.game_dir_ok and not st.llc_ok
    assert any(i.code == "no_llc" for i in st.issues)


def test_bad_config(tmp_game):
    p = resolve_game_paths(tmp_game)
    p.config_path.write_text("{ not json", encoding="utf-8")
    st = check_environment(str(tmp_game))
    assert not st.config_valid
    assert any(i.code == "bad_config" for i in st.issues)
