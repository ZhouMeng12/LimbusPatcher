"""应用自身配置（data/config.json）与数据目录管理。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

FORMAT_VERSION = 1


def app_dir() -> Path:
    """应用目录：打包后为 exe 所在目录，开发时为项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class AppPaths:
    root: Path
    data_dir: Path
    config_path: Path
    profiles_dir: Path
    backups_dir: Path
    history_dir: Path
    cache_dir: Path

    @classmethod
    def from_root(cls, root: Path | None = None) -> "AppPaths":
        root = Path(root) if root else app_dir()
        data = root / "data"
        return cls(
            root=root,
            data_dir=data,
            config_path=data / "config.json",
            profiles_dir=data / "profiles",
            backups_dir=data / "backups",
            history_dir=data / "history",
            cache_dir=data / "cache",
        )

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.profiles_dir, self.backups_dir, self.history_dir, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)


@dataclass
class AppliedState:
    """工具在游戏侧的应用记录（用于判定「已应用到游戏」）。"""

    revision: int = 0
    previous_lang: str | None = None
    enabled: bool = False
    at: str | None = None

    def to_dict(self) -> dict:
        return {
            "revision": self.revision,
            "previous_lang": self.previous_lang,
            "enabled": self.enabled,
            "at": self.at,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "AppliedState":
        d = d or {}
        return cls(
            revision=int(d.get("revision") or 0),
            previous_lang=d.get("previous_lang"),
            enabled=bool(d.get("enabled")),
            at=d.get("at"),
        )


@dataclass
class UiState:
    """界面会话记忆：下次启动回到上次的样子（关闭窗口时写入）。"""

    geometry: str = ""           # 主窗口位置/大小（QWidget.saveGeometry 的 base64）
    splitter: str = ""           # 三栏分栏宽度
    compare_splitter: str = ""   # 编辑器「原文 / 自定义」分栏
    category: str = "all"        # 上次的分类
    search: str = ""             # 上次的搜索词
    hit_key: str = ""            # 上次打开的条目（EntryRef.key()）
    chapter: str = ""
    level: str = ""
    season: str = ""
    kind: str = ""
    script_active: bool = False  # 上次停在剧本模式
    script_chapter: str = ""
    script_stage: str = ""
    script_branch: str = ""       # RPG 关卡下的分支 id（10-04 的「1F 探索」等）
    script_show_deleted: bool = False
    script_unaligned_only: bool = False
    show_baseline: bool = False   # 编辑器是否显示「英语原文」第三栏
    search_scope: str = "original"  # 搜索范围：original / baseline / custom / all
    theme: str = "mini-dark"      # 界面主题：mini-dark(默认，第一版暗金) / mini-light / bus

    def to_dict(self) -> dict:
        return {
            "geometry": self.geometry,
            "splitter": self.splitter,
            "compare_splitter": self.compare_splitter,
            "category": self.category,
            "search": self.search,
            "hit_key": self.hit_key,
            "chapter": self.chapter,
            "level": self.level,
            "season": self.season,
            "kind": self.kind,
            "script_active": self.script_active,
            "script_chapter": self.script_chapter,
            "script_stage": self.script_stage,
            "script_branch": self.script_branch,
            "script_show_deleted": self.script_show_deleted,
            "script_unaligned_only": self.script_unaligned_only,
            "show_baseline": self.show_baseline,
            "search_scope": self.search_scope,
            "theme": self.theme,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "UiState":
        d = d or {}
        state = cls()
        for name in ("geometry", "splitter", "compare_splitter", "category", "search",
                     "hit_key", "chapter", "level", "season", "kind",
                     "script_chapter", "script_stage", "script_branch", "search_scope"):
            value = d.get(name)
            if isinstance(value, str):
                setattr(state, name, value)
        for name in ("script_active", "script_show_deleted", "script_unaligned_only", "show_baseline"):
            setattr(state, name, bool(d.get(name)))
        if not state.category:
            state.category = "all"
        if state.search_scope not in ("original", "baseline", "custom", "all"):
            state.search_scope = "original"
        # 主题白名单（与 ui.theme.THEME_IDS 保持一致；此处不 import Qt，避免拖入 GUI 依赖）
        # 同时接受旧名 dark / light，避免老配置被静默重置回默认主题。
        theme = d.get("theme")
        if isinstance(theme, str):
            theme = theme.strip().lower()
            theme = {"dark": "mini-dark", "light": "mini-light"}.get(theme, theme)
            if theme in ("bus", "mini-dark", "mini-light"):
                state.theme = theme
        return state


@dataclass
class AppConfig:
    game_dir: str | None = None
    patch_pack_name: str = "LLC_zh-CN_custom"
    baseline_lang: str = "en"  # 英文基线语言目录名（Localize/<lang>）
    advanced_mode: bool = False
    applied: AppliedState = field(default_factory=AppliedState)
    ui: UiState = field(default_factory=UiState)

    def to_dict(self) -> dict:
        return {
            "format_version": FORMAT_VERSION,
            "game_dir": self.game_dir,
            "patch_pack_name": self.patch_pack_name,
            "baseline_lang": self.baseline_lang,
            "advanced_mode": self.advanced_mode,
            "applied": self.applied.to_dict(),
            "ui": self.ui.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "AppConfig":
        d = d or {}
        return cls(
            game_dir=d.get("game_dir") or None,
            patch_pack_name=d.get("patch_pack_name") or "LLC_zh-CN_custom",
            baseline_lang=d.get("baseline_lang") or "en",
            advanced_mode=bool(d.get("advanced_mode")),
            applied=AppliedState.from_dict(d.get("applied")),
            ui=UiState.from_dict(d.get("ui")),
        )


class ConfigStore:
    """data/config.json 的读写（临时文件 + 原子替换 + 回读校验）。"""

    def __init__(self, app_paths: AppPaths):
        self.app_paths = app_paths

    def load(self) -> AppConfig:
        p = self.app_paths.config_path
        if not p.is_file():
            return AppConfig()
        try:
            obj = json.loads(p.read_text(encoding="utf-8-sig"))
            return AppConfig.from_dict(obj)
        except Exception:
            # 配置损坏时不让应用崩溃：保留一份损坏副本供排查，回退默认。
            try:
                p.replace(p.with_name(p.name + ".broken"))
            except OSError:
                pass
            return AppConfig()

    def save(self, cfg: AppConfig) -> None:
        p = self.app_paths.config_path
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2)
        # 序列化后回读校验，禁止直接拼接 JSON。
        json.loads(payload)
        fd, tmp = tempfile.mkstemp(prefix=".config.", dir=str(p.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(payload)
            os.replace(tmp, p)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
