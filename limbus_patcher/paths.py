"""游戏目录识别与路径解析。

零协汉化（LocalizeLimbusCompany）自 1.73 官方自定义翻译接口起，
语言包安装于 ``LimbusCompany_Data/Lang/LLC_zh-CN``，
由 ``LimbusCompany_Data/Lang/config.json`` 的 ``lang`` 字段决定启用哪个包。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

GAME_APP_ID = "1973530"
GAME_DIR_NAME = "Limbus Company"
LLC_PACK_NAME = "LLC_zh-CN"
DEFAULT_PATCH_PACK_NAME = "LLC_zh-CN_custom"

_VDF_PATH_RE = re.compile(r'"path"\s+"((?:[^"\\]|\\.)*)"')


@dataclass(frozen=True)
class GamePaths:
    """与一次游戏目录解析相关的全部路径。"""

    game_dir: Path
    data_dir: Path
    lang_dir: Path
    config_path: Path
    llc_pack_dir: Path
    llc_layout: str  # "lang" | "legacy_root"
    base_localize_dir: Path

    @property
    def exe_path(self) -> Path:
        return self.game_dir / "LimbusCompany.exe"

    def patch_pack_dir(self, name: str) -> Path:
        return self.lang_dir / name

    def baseline_dir(self, lang: str = "en") -> Path:
        """指定语言的基线目录（如 ``en`` / ``jp`` / ``kr``）。"""
        return self.base_localize_dir / (lang or "en")

    def en_base_dir(self) -> Path:
        """英文基线目录（带 EN_ 前缀的文件）。"""
        return self.baseline_dir("en")


def is_valid_game_dir(path: os.PathLike | str) -> bool:
    p = Path(path)
    return (p / "LimbusCompany.exe").is_file() and (p / "LimbusCompany_Data").is_dir()


def detect_llc_pack(paths: GamePaths) -> tuple[Path | None, str]:
    """返回 (零协包目录, 布局)。布局为 lang / legacy_root / none。"""
    primary = paths.lang_dir / LLC_PACK_NAME
    if primary.is_dir():
        return primary, "lang"
    legacy = paths.game_dir / LLC_PACK_NAME
    if legacy.is_dir():
        return legacy, "legacy_root"
    return None, "none"


def resolve_game_paths(game_dir: os.PathLike | str) -> GamePaths:
    g = Path(game_dir)
    return GamePaths(
        game_dir=g,
        data_dir=g / "LimbusCompany_Data",
        lang_dir=g / "LimbusCompany_Data" / "Lang",
        config_path=g / "LimbusCompany_Data" / "Lang" / "config.json",
        llc_pack_dir=g / "LimbusCompany_Data" / "Lang" / LLC_PACK_NAME,
        llc_layout="lang",
        base_localize_dir=g / "LimbusCompany_Data" / "Assets" / "Resources_moved" / "Localize",
    )


def parse_libraryfolders_vdf(text: str) -> list[Path]:
    """解析 Steam ``libraryfolders.vdf``，返回各库根目录。"""
    dirs: list[Path] = []
    for m in _VDF_PATH_RE.finditer(text):
        raw = m.group(1)
        try:
            raw = raw.encode("utf-8", "surrogateescape").decode("unicode_escape")
        except Exception:
            pass
        p = Path(raw)
        if (p / "steamapps").is_dir() and p not in dirs:
            dirs.append(p)
    return dirs


def read_steam_install_path() -> Path | None:
    """从注册表读取 Steam 安装目录；失败则尝试常见默认位置。"""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            value, _ = winreg.QueryValueEx(key, "SteamPath")
            if value:
                return Path(value)
    except OSError:
        pass
    for cand in (
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Steam",
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"D:\Steam"),
        Path(r"E:\Steam"),
    ):
        if (cand / "steamapps").is_dir():
            return cand
    return None


def find_steam_library_dirs(steam_path: os.PathLike | str | None = None) -> list[Path]:
    """返回全部 Steam 库目录（含主目录）。"""
    steam = Path(steam_path) if steam_path else read_steam_install_path()
    libs: list[Path] = []
    if steam and (steam / "steamapps").is_dir():
        libs.append(steam)
    vdf = steam / "steamapps" / "libraryfolders.vdf" if steam else None
    if vdf and vdf.is_file():
        try:
            libs.extend(parse_libraryfolders_vdf(vdf.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            pass
    seen: set[Path] = set()
    return [p for p in libs if not (p in seen or seen.add(p))]


def find_steam_game_dirs() -> list[Path]:
    """扫描全部 Steam 库，返回检测到的《边狱巴士》游戏目录。"""
    found: list[Path] = []
    for lib in find_steam_library_dirs():
        game = lib / "steamapps" / "common" / GAME_DIR_NAME
        if is_valid_game_dir(game):
            found.append(game)
    return found
