"""应用状态中枢：配置 / 方案 / 环境 / 索引 / 部署 的编排。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import paths as pathmod
from .backup import BackupManager
from .baseline import baseline_text
from .categories import set_user_data_dir
from .config import AppConfig, AppPaths, ConfigStore
from .deploy import Deployer, original_text
from .envcheck import EnvironmentStatus, check_environment
from .entities import set_enemy_map_overlay
from .history import HistoryStore
from .index import Indexer
from .patch import EntryRef, Profile, default_profile_path
from .search import SearchEngine
from .season import MetaMaps
from .textsource import TextSource
from .story_edit import StoryEdit
from .supplement import SupplementPack
from .storybook import Storybook


@dataclass
class PatchEntryResult:
    ok: bool
    message: str
    entry: object | None = None


def _sourced_name(rel: str, prefix: str) -> str:
    """零协相对路径 → 当前来源下的相对路径（英文基线文件名带 EN_ 前缀）。"""
    if not prefix:
        return rel
    from pathlib import PurePosixPath

    p = PurePosixPath(rel)
    return str(p.with_name(prefix + p.name))


class AppContext:
    """UI 与各子系统之间的唯一粘合层。"""

    def __init__(self, app_paths: AppPaths | None = None):
        self.app_paths = app_paths or AppPaths.from_root()
        self.app_paths.ensure_dirs()
        set_user_data_dir(self.app_paths.data_dir)  # 便携 data/ 中的 category_rules.json 优先
        self.config_store = ConfigStore(self.app_paths)
        self.config: AppConfig = self.config_store.load()
        self.profile = Profile()
        self.profile_path = default_profile_path(self.app_paths.profiles_dir)
        self.backup = BackupManager(self.app_paths)
        self.deployer = Deployer(self.app_paths.cache_dir)
        self.history = HistoryStore(self.app_paths.history_dir)
        self.indexer = Indexer(
            self.app_paths.cache_dir / "index.sqlite",
            self.app_paths.cache_dir / "manifest.json",
            meta_overlay=self.app_paths.cache_dir,
            supplement_dir=self.app_paths.data_dir / "supplement",
        )
        self.search = SearchEngine(self.app_paths.cache_dir / "index.sqlite")
        self.maps = MetaMaps(overlay_dir=self.app_paths.cache_dir)
        set_enemy_map_overlay(self.app_paths.cache_dir)  # enemy_map.json 覆盖（新增章节敌人元数据）
        self.storybook = Storybook(overlay_dir=self.app_paths.cache_dir)
        self.supplement = SupplementPack(self.app_paths.data_dir)
        self._story_edit: StoryEdit | None = None
        self.env: EnvironmentStatus = EnvironmentStatus()
        self._profile_dirty = False
        self.load_profile()
        self.refresh_env()

    # ---- 数据加载 ----

    def load_profile(self) -> None:
        try:
            self.profile.load(self.profile_path)
        except Exception:
            # 损坏时保留文件供排查（load 内已对 JSON 错误抛 ProfileError），回退为空方案。
            self.profile = Profile()
        self._profile_dirty = False

    def save_profile(self) -> None:
        self.profile.save(self.profile_path)
        self._profile_dirty = False

    @property
    def profile_dirty(self) -> bool:
        return self._profile_dirty

    # ---- 环境 ----

    def refresh_env(self) -> EnvironmentStatus:
        self.env = check_environment(self.config.game_dir, self.config.patch_pack_name)
        self._text_source = None          # 来源随环境变化，重新探测
        # 登记游戏侧目录：图鉴/主线剧情预览这些不走 TextSource 的显示路径
        # 靠它把 model（韩文角色键）翻成显示名（c10p2 起过场文件没有 teller）
        from .textsource import set_game_dirs

        set_game_dirs(self.env.llc_pack_dir if self.env.llc_ok else None,
                      self.env.base_dir if self.env.base_ok else None)
        self.storybook.text_source = self.text_source
        return self.env

    def set_game_dir(self, game_dir: str | None) -> None:
        self.config.game_dir = game_dir
        self.config_store.save(self.config)
        self.refresh_env()

    @property
    def game_paths(self):
        return pathmod.resolve_game_paths(self.config.game_dir)

    @property
    def baseline_dir(self) -> Path | None:
        """英文基线目录（Localize/<lang>）；游戏目录无效或目录不存在时返回 None。"""
        if not self.env.game_dir_ok:
            return None
        d = self.game_paths.baseline_dir(self.config.baseline_lang or "en")
        return d if d.is_dir() else None

    def baseline_of(self, ref: EntryRef) -> tuple[str | None, str | None]:
        """取条目的英文原文（只读）。返回 (文本, 中文原因)，失败不抛异常。"""
        return baseline_text(self.baseline_dir, ref)

    @property
    def text_source(self):
        """当前文本来源（零协优先，没装零协则用英文基线；缺的文件回退补译目录）。

        条目里存的永远是「零协包内相对路径 + 记录下标 + 字段路径」，
        文本本身现从该来源读，不落库、不随包分发。
        新章节（如 c10p2）零协还没跟时，文件只在补译目录里，靠回退读到自己的译文。
        """
        src = getattr(self, "_text_source", None)
        key = (self.env.llc_pack_dir, self.env.base_dir, self.env.text_source)
        if src is None or getattr(src, "_key", None) != key:
            from .textsource import TextSource

            src = TextSource.detect(self.env.llc_pack_dir if self.env.llc_ok else None,
                                    self.env.base_dir if self.env.base_ok else None,
                                    self.supplement.root)
            src._key = key  # type: ignore[attr-defined]
            self._text_source = src
        return src

    # ---- 索引 ----

    def ensure_index(self, progress=None, force: bool = False) -> bool:
        """索引缺失或文本来源变化时重建。返回是否执行了重建。

        没有零协汉化时，索引改为基于**英文基线**构建：相对路径去掉 ``EN_`` 前缀，
        与零协包的位置一一对应，所以索引、方案、剧本数据都不用换一套。
        """
        env = self.env
        src = self.text_source
        if not src.ok or src.root is None:
            return False
        root = Path(src.root)
        base = self.baseline_dir if src.mode == "llc" else None
        strip = src.prefix
        if force or not self.indexer.manifest_matches(root, base, strip_prefix=strip):
            self.indexer.build(root, progress, baseline_dir=base, strip_prefix=strip)
            return True
        return False

    # ---- 剧本手动映射 ----

    @property
    def story_edit(self) -> StoryEdit:
        llc = Path(self.env.llc_pack_dir) if self.env.llc_ok and self.env.llc_pack_dir else Path(".")
        if self._story_edit is None or self._story_edit.llc_dir != llc:
            self._story_edit = StoryEdit(self.app_paths.cache_dir, llc)
        return self._story_edit

    def apply_story_mapping(self, page: str, key: str, record: int | None = None, skip: bool = False,
                            deleted: bool = False) -> int:
        """建立对应 / 标记跳过 / 删除该行 / 清除覆盖，并重建运行时剧本数据；返回应用条数。"""
        se = self.story_edit
        if deleted:
            se.mark_deleted(page, key)
        elif skip:
            se.mark_skip(page, key)
        elif record is None:
            se.clear(page, key)  # 清除覆盖：已删除/已跳过的行也会随之恢复
        else:
            se.set_record(page, key, record)
        applied = se.rebuild()
        self.storybook.reload()
        return applied

    # ---- 条目编辑 ----

    def _resolve_ref_path(self, ref: EntryRef) -> Path | None:
        """定位条目所在文件：零协包优先，零协包无该文件 → supplement 目录回退。

        与 :meth:`original_of` 的 supplement 回退同款逻辑，集中为统一入口。
        """
        env = self.env
        if not env.llc_ok:
            return None
        llc = Path(env.llc_pack_dir)
        if (llc / ref.file).is_file():
            return llc / ref.file
        sup = self.supplement.root / ref.file
        return sup if sup.is_file() else None

    def read_ref(self, ref: EntryRef) -> tuple[dict | None, str | None]:
        """统一回退读取条目所在文件内容。返回 (JSON 对象, 错误)；失败不抛异常。"""
        from .fsutil import load_json

        path = self._resolve_ref_path(ref)
        if path is None:
            return None, "文件不存在（零协包与 supplement 均无此文件）"
        data, err = load_json(path)
        if data is None:
            return None, err
        return data, None

    def load_pack_json(self, relfile: str) -> tuple[dict | None, str | None]:
        """按零协相对路径读取 JSON（当前文本来源优先，无则回退 supplement）。"""
        from .fsutil import load_json

        src = self.text_source
        if not src.ok:
            return None, "没有可用的文本来源（未装零协汉化，也没找到英文基线）"
        path = src.file_path(relfile)
        if path is None or not path.is_file():
            path = self.supplement.root / relfile
            if not path.is_file():
                return None, "文件不存在（当前文本来源与 supplement 均无此文件）"
        data, err = load_json(path)
        if data is None:
            return None, err
        return data, None

    def original_of(self, ref: EntryRef) -> tuple[str | None, str | None]:
        src = self.text_source
        if not src.ok or src.root is None:
            return None, "没有可用的文本来源（未装零协汉化，也没找到英文基线）"
        path = src.file_path(ref.file)
        if path is None or not path.is_file():
            # 来源里没有这个文件 → 可能是补译文件（如新章节），从 supplement/ 读
            sup = self.supplement.root / ref.file
            if sup.is_file():
                return original_text(sup.parent, EntryRef(file=sup.name, id=ref.id,
                                                          record_index=ref.record_index,
                                                          field_path=ref.field_path))
        return original_text(Path(src.root), EntryRef(file=_sourced_name(ref.file, src.prefix),
                                                      id=ref.id, record_index=ref.record_index,
                                                      field_path=ref.field_path))

    def load_record(self, ref: EntryRef) -> tuple[dict | None, str | None]:
        """读取条目所在记录（用于显示名称、角色等）。零协包无文件时回退 supplement。"""
        data, err = self.read_ref(ref)
        if data is None:
            return None, err
        dl = data.get("dataList") if isinstance(data, dict) else None
        if not isinstance(dl, list):
            return None, "文件缺少 dataList"
        if 0 <= ref.record_index < len(dl) and isinstance(dl[ref.record_index], dict) and dl[ref.record_index].get("id") == ref.id:
            return dl[ref.record_index], None
        if ref.id is None:
            # 无 KeyID 的记录只认下标：按 id 回退会匹配到别的无 id 记录（等于改错文本）。
            return None, f"记录定位失败：第 {ref.record_index} 条已不是原来的记录（该条目缺少 KeyID，只能按下标定位）"
        for r in dl:
            if isinstance(r, dict) and r.get("id") == ref.id:
                return r, None
        return None, f"找不到 id={ref.id!r} 的记录"

    def upsert_entry(self, ref: EntryRef, value: str) -> PatchEntryResult:
        text, err = self.original_of(ref)
        if text is None:
            return PatchEntryResult(ok=False, message=f"无法读取原文：{err}")
        old = self.profile.get(ref)
        old_value = old.value if old else None
        new_entry = self.profile.upsert(ref, value, text)
        self.history.record(ref.key(), old_value, value)
        self._profile_dirty = True
        if new_entry is None:
            return PatchEntryResult(ok=True, message="已还原为原文", entry=None)
        return PatchEntryResult(ok=True, message="已保存到方案", entry=new_entry)

    def remove_entry(self, ref: EntryRef) -> bool:
        existed = self.profile.remove(ref)
        if existed:
            self._profile_dirty = True
        return existed

    # ---- 应用 / 清空 / 停用 ----

    def apply(self, progress=None):
        """备份 → 同步副本包 → 切换 config.json → 记录应用状态。"""
        env = self.refresh_env()
        if not env.llc_ok:
            raise RuntimeError("零协汉化不可用，无法应用补丁")
        if self._profile_dirty:
            self.save_profile()
        self.backup.backup("apply")
        report = self.deployer.enable(self.game_paths, self.config.patch_pack_name, self.profile, progress,
                                      supplements=self.supplement.enabled_map())
        if report.ok:
            self.config.applied.revision = self.profile.revision
            self.config.applied.previous_lang = report.previous_lang
            self.config.applied.enabled = True
            self.config.applied.at = None
            self.config_store.save(self.config)
        return report

    def clear_all(self, progress=None):
        """清空全部修改并把副本包恢复为纯镜像（保持启用）。"""
        self.backup.backup("clear")
        self.profile.clear()  # 加锁清空 + 递增修订号（部署线程可能正在遍历快照）
        self.save_profile()
        return self.deployer.enable(self.game_paths, self.config.patch_pack_name, self.profile, progress,
                                    supplements=self.supplement.enabled_map())

    def disable(self):
        """停用修改：lang 改回之前的语言包（副本包数据保留）。"""
        self.backup.backup("disable")
        self.deployer.disable(self.game_paths, self.config.patch_pack_name, self.config.applied.previous_lang)
        self.config.applied.enabled = False
        self.config_store.save(self.config)

    def apply_view(self):
        if not self.env.llc_ok:
            return None
        return self.deployer.view(self.game_paths, self.config.patch_pack_name, self.profile)

    def compat_status(self) -> dict[str, tuple[str, str]]:
        if not self.env.llc_ok:
            return {}
        return self.deployer.check_entries(self.game_paths, self.profile, self.supplement)
