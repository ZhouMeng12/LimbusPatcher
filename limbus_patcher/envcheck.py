"""环境检查：游戏目录 / 零协汉化 / 基线文本 / config.json / 补丁包状态。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .fsutil import load_json
from .paths import detect_llc_pack, is_valid_game_dir, resolve_game_paths

#: 零协工具箱下载/安装指引（没装零协时给玩家的去处）
TOOLBOX_URL = "https://www.zeroasso.top/docs/install/autoinstall"


@dataclass
class EnvIssue:
    code: str
    message: str
    next_action: str


@dataclass
class EnvironmentStatus:
    game_dir: str | None = None
    game_dir_ok: bool = False
    llc_ok: bool = False
    llc_layout: str = "none"
    llc_pack_dir: str | None = None
    llc_file_count: int = 0
    base_ok: bool = False
    base_dir: str | None = None
    base_file_count: int = 0
    config_exists: bool = False
    config_valid: bool = False
    config_lang: str | None = None
    font_ok: bool = False
    patch_pack_exists: bool = False
    #: 当前文本来源："llc"（零协汉化）/ "en"（游戏英文基线）/ "none"
    text_source: str = "none"
    issues: list[EnvIssue] = field(default_factory=list)

    @property
    def text_ok(self) -> bool:
        """有没有可用的文本来源（零协或英文基线，任一即可）。"""
        return self.text_source in ("llc", "en")

    def healthy(self) -> bool:
        """游戏目录 + 任一文本来源就算可用（没零协时走英文原文）。"""
        return self.game_dir_ok and self.text_ok

    def brief(self) -> str:
        if not self.game_dir_ok:
            return "未选择游戏目录"
        if self.llc_ok:
            return "游戏目录正常"
        if self.text_source == "en":
            return "未装零协汉化 · 当前用英文原文"
        return "未找到可用的文本（缺零协汉化与英文基线）"


def check_environment(game_dir: str | None, patch_pack_name: str = "LLC_zh-CN_custom") -> EnvironmentStatus:
    st = EnvironmentStatus(game_dir=game_dir)
    if not game_dir:
        st.issues.append(EnvIssue("no_game_dir", "尚未找到《边狱巴士》游戏目录。", "点击「自动扫描 Steam 库」或「手动选择游戏目录」。"))
        return st
    g = Path(game_dir)
    st.game_dir_ok = is_valid_game_dir(g)
    if not st.game_dir_ok:
        st.issues.append(
            EnvIssue(
                "bad_game_dir",
                "所选目录不是有效的《边狱巴士》游戏目录（缺少 LimbusCompany.exe）。",
                "点击「重新扫描 / 重新选择」，选择 Steam 库中 Limbus Company 的安装目录。",
            )
        )
        return st
    paths = resolve_game_paths(g)

    llc_dir, layout = detect_llc_pack(paths)
    st.llc_layout = layout
    if llc_dir is None:
        # 没装零协也能用：文本改从游戏英文基线取（位置一一对应），只是界面文本是英文。
        st.issues.append(
            EnvIssue(
                "no_llc",
                "未检测到零协会汉化（LimbusCompany_Data/Lang/LLC_zh-CN）。"
                "当前改用游戏自带的**英文原文**做文本来源，仍可浏览 / 对照 / 翻译。",
                "想要中文底本？用零协工具箱安装汉化后点「重新检测」："
                f"{TOOLBOX_URL}",
            )
        )
    else:
        st.llc_ok = True
        st.llc_pack_dir = str(llc_dir)
        st.llc_file_count = sum(1 for p in llc_dir.rglob("*.json") if p.is_file())
        if layout == "legacy_root":
            st.issues.append(
                EnvIssue(
                    "legacy_layout",
                    "零协汉化位于游戏根目录（旧版布局），工具仍可读取，但建议重装为零协新结构。",
                    "可继续使用；或使用零协工具箱重新安装汉化后点击「重新检测」。",
                )
            )
        st.font_ok = (llc_dir / "Font").is_dir()

    # 英文基线：只读参考（编辑器并排显示 + 搜索范围）。缺失不影响任何既有功能，
    # 因此这里只记录状态，不追加 issue。
    base = paths.en_base_dir()
    st.base_dir = str(base)
    if base.is_dir():
        st.base_file_count = sum(1 for p in base.rglob("*.json") if p.is_file())
    st.base_ok = st.base_file_count > 0

    cfg, err = load_json(paths.config_path) if paths.config_path.is_file() else (None, None)
    st.config_exists = paths.config_path.is_file()
    st.config_valid = isinstance(cfg, dict)
    if isinstance(cfg, dict):
        st.config_lang = cfg.get("lang")
    elif paths.config_path.is_file():
        st.issues.append(
            EnvIssue(
                "bad_config",
                f"汉化语言配置 config.json 异常：{err or '格式不正确'}。",
                "进入高级模式可导出该文件排查；或删除后由本工具重建。",
            )
        )

    st.patch_pack_exists = (paths.lang_dir / patch_pack_name).is_dir()

    # 文本来源：零协优先，其次英文基线
    st.text_source = "llc" if st.llc_ok else ("en" if st.base_ok else "none")
    if st.text_source == "en":
        st.issues.append(
            EnvIssue(
                "english_source",
                "正在使用英文原文（游戏基线）作为文本来源：界面里看到的是英文，你的译文会正常保存与导出。",
                "装零协汉化即可切回中文底本（中文译文与术语照零协）：" + TOOLBOX_URL,
            )
        )
    elif st.text_source == "none" and st.llc_ok is False:
        st.issues.append(
            EnvIssue(
                "no_text",
                "既没有零协汉化，也没有找到游戏英文基线（Assets/Resources_moved/Localize/en）。",
                "请确认游戏完整安装（Steam 里「验证文件完整性」），或安装零协汉化后重试：" + TOOLBOX_URL,
            )
        )
    return st
