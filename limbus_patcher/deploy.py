"""部署引擎：构建合并副本语言包、切换 config.json、判定应用状态、兼容性检查。

原则：零协原包（Lang/LLC_zh-CN）只读；
游戏侧只写两个位置 —— Lang/<副本包>/ 与 Lang/config.json（lang 字段，保留其余键）。
"""
from __future__ import annotations

import json
import shutil
import stat as stat_mod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .fsutil import atomic_write_bytes, atomic_write_text, collect_rel_files, load_json, sha256_text
from .patch import EntryRef, Profile, get_value, set_value
from .paths import GamePaths
from .supplement import validate_json_file as validate_supplement

APPLIED_FORMAT = 1


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _same_size_mtime(src: Path, dst: Path) -> bool:
    """判断「源文件与目标副本是否可视为同一个文件」（增量复制的快路径）。

    比较 (st_size, st_mtime_ns)：``shutil.copy2`` 会用 ``os.utime`` 保留源文件的
    修改时间（纳秒级），所以零协包更新后 mtime 变化一定能被识别，而没变过的文件
    可以直接跳过，不必重写 50 MB 的内容。

    已知边界（有意接受的取舍）：若源文件的内容被替换、而新内容大小与 mtime_ns 又与
    旧内容完全相同（例如从备份还原后再把时间戳 utime 回原值），这里会认为「无需
    重写」。要识别这种情况只能比对内容哈希，代价是每次同步都要读满整个包，收益远
    小于成本。因此本项目选择该边界。

    正确性优先：任何不确定的情况（stat 失败、目标不存在、目标不是普通文件）都返回
    False，即照常重写，宁可多写不漏写。
    """
    try:
        s = src.stat()
        d = dst.stat()
    except OSError:
        return False
    if not stat_mod.S_ISREG(s.st_mode) or not stat_mod.S_ISREG(d.st_mode):
        return False
    return s.st_size == d.st_size and s.st_mtime_ns == d.st_mtime_ns


def _same_bytes(path: Path, blob: bytes) -> bool:
    """目标文件现有字节是否与待写入字节完全一致（用于补丁 JSON 跳过重写）。

    任何读取失败（不存在 / 是目录 / 无权限）都当作「不一致」，即照常重写。
    只在补丁 JSON 上用：这些文件数量很少，整读一遍的成本可以接受。
    """
    try:
        if path.stat().st_size != len(blob):
            return False
        return path.read_bytes() == blob
    except OSError:
        return False


def _find_record(dl: list, ref: EntryRef) -> dict:
    """按 record_index 优先、id 回退定位记录。

    注意：记录本身没有 KeyID 时（ref.id is None）不做 id 回退——那会静默匹配到
    「文件里第一条无 id 记录」，等于改错文本。这种情况只认 record_index。
    """
    if 0 <= ref.record_index < len(dl):
        r = dl[ref.record_index]
        if isinstance(r, dict) and r.get("id") == ref.id:
            return r
    if ref.id is None:
        raise KeyError(f"记录定位失败：第 {ref.record_index} 条已不是原来的记录（该条目缺少 KeyID，只能按下标定位）")
    for r in dl:
        if isinstance(r, dict) and r.get("id") == ref.id:
            return r
    raise KeyError(f"找不到 id={ref.id!r} 的记录")


#: 记录标识字段的优先级（老文件用 id，RPG/UI 这类用 key，少数用 code）
_RECORD_ID_KEYS = ("id", "key", "code")


def _record_key(rec) -> str | None:
    """记录的唯一标识（补译文件做记录级合并时按它比对）；拿不到返回 None。"""
    if not isinstance(rec, dict):
        return None
    for k in _RECORD_ID_KEYS:
        v = rec.get(k)
        if v is not None and str(v).strip():
            return f"{k}={v}"
    return None


def original_text(llc_dir: Path, ref: EntryRef) -> tuple[str | None, str | None]:
    """读取零协包中某条目的当前原文。返回 (文本, 错误)。"""
    data, err = load_json(llc_dir / ref.file)
    if data is None:
        return None, err
    dl = data.get("dataList") if isinstance(data, dict) else None
    if not isinstance(dl, list):
        return None, "文件缺少 dataList"
    try:
        record = _find_record(dl, ref)
        return get_value(record, ref.field_path), None
    except KeyError as e:
        return None, str(e)


@dataclass
class DeployReport:
    files_written: int = 0
    files_copied: int = 0
    files_removed: int = 0
    # 增量同步新增：因内容/时间戳未变而跳过的文件数。
    # 跳过的文件不计入 files_written / files_copied（那两个字段含义保持不变），
    # 因此「已更新文件数」仍然只统计真正落盘的文件。
    files_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    previous_lang: str | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class ApplyView:
    enabled: bool = False
    revision_matches: bool = False
    config_lang: str | None = None
    applied_revision: int = 0

    @property
    def applied(self) -> bool:
        return self.enabled and self.revision_matches


class Deployer:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.applied_manifest_path = cache_dir / "applied_manifest.json"

    # ---- applied manifest ----

    def load_applied(self) -> dict | None:
        if not self.applied_manifest_path.is_file():
            return None
        try:
            obj = json.loads(self.applied_manifest_path.read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _write_applied(self, patch_pack_name: str, profile: Profile) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            self.applied_manifest_path,
            json.dumps(
                {
                    "format_version": APPLIED_FORMAT,
                    "revision": profile.revision,
                    "patch_pack_name": patch_pack_name,
                    "profile_name": profile.name,
                    "entry_count": profile.count(),
                    "at": _now(),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    # ---- 副本包同步 ----

    def sync_clone(self, paths: GamePaths, patch_pack_name: str, profile: Profile, progress=None,
                   supplements: dict[str, Path] | None = None) -> DeployReport:
        """把零协包镜像 + 补丁合并写入副本包（逐文件原子替换）。

        增量策略（正确性优先：判定不确定一律重写）：
        1) 普通文件：目标已存在且 (size, mtime_ns) 与源一致 → 跳过不写。
           ``copy2`` 保留 mtime，所以零协包更新后能被识别。已知边界见
           :func:`_same_size_mtime`（源被替换但 size/mtime 恰好不变时不重写）。
        2) 需要打补丁的 json：补丁内容可能变，所以仍然每次重新生成；
           但生成结果与副本现有字节完全一致时跳过写入（原子写与 UTF-8 BOM 行为不变）。
           注意这类文件不依赖 (size, mtime) 快路径，避免「时间戳相同但内容过期」蒙混过关。
        """
        report = DeployReport()
        llc = paths.llc_pack_dir
        clone = paths.patch_pack_dir(patch_pack_name)
        if not llc.is_dir():
            report.errors.append(f"零协包不存在：{llc}")
            return report
        clone.mkdir(parents=True, exist_ok=True)

        src_files = collect_rel_files(llc)
        entries_by_file: dict[str, list] = {}
        for entry in profile.values():  # 快照：UI 线程可能同时在增删条目
            entries_by_file.setdefault(entry.ref.file, []).append(entry)

        total = len(src_files)
        processed = 0
        for rel, src in src_files.items():
            dst = clone / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            entries = entries_by_file.get(rel)
            if rel.lower().endswith(".json") and entries:
                self._write_patched(src, dst, entries, report, rel)
            else:
                self._copy_if_needed(src, dst, report)
            processed += 1
            if progress:
                progress(processed, total)

        # 补译文件：零协包里没有的文件（例如还没汉化的新章节），按启用状态写入副本包。
        supplements = supplements or {}
        for rel, src in sorted(supplements.items()):
            rel = str(rel).replace("\\", "/")
            if rel in src_files:
                # 零协已有同名文件 → 记录级合并：只把零协缺的记录（按 id）追加进去，
                # 已有记录一律以零协为准（例如 StageChapterText 缺的第十章那几行）。
                self._merge_records(clone / rel, Path(src), report, rel)
                continue
            ok, err = validate_supplement(src)
            if not ok:
                report.errors.append(f"{rel}: 补译文件无效（{err}），未写入")
                continue
            dst = clone / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            entries = entries_by_file.get(rel)
            if entries:      # 补译文件同样支持在程序里逐条改（方案条目写在补译文件之上）
                self._write_patched(Path(src), dst, entries, report, rel)
            else:
                self._copy_if_needed(Path(src), dst, report)

        # 清理副本中零协已不存在的文件（汉化更新删文件时同步）；启用中的补译文件保留。
        keep = {str(rel).replace("\\", "/") for rel in supplements}
        clone_files = collect_rel_files(clone)
        for rel in list(clone_files):
            if rel not in src_files and rel not in keep:
                try:
                    (clone / rel).unlink()
                    report.files_removed += 1
                except OSError as e:
                    report.errors.append(f"{rel}: 清理失败（{e}）")
        self._prune_empty_dirs(clone)
        return report


    @staticmethod
    def _merge_records(dst: Path, src: Path, report: DeployReport, rel: str) -> None:
        """把补译文件里「零协没有的记录」按 id 追加到副本包的对应文件上。"""
        ok, err = validate_supplement(src)
        if not ok:
            report.errors.append(f"{rel}: 补译文件无效（{err}），未合并")
            return
        target, terr = load_json(dst)
        if target is None or not isinstance(target.get("dataList"), list):
            report.errors.append(f"{rel}: 副本包里的文件无法解析（{terr}），未合并")
            return
        add, aerr = load_json(src)          # fsutil.load_json 返回 (data, err)
        records = add.get("dataList") if isinstance(add, dict) else None
        if not isinstance(records, list):
            report.errors.append(f"{rel}: 补译文件缺少 dataList（{aerr}），未合并")
            return
        # 记录标识：老文件用 id，RPG/UI 这类用 key（个别用 code）。
        # 只认 id 的话，key 型同名文件会整份被跳过——那批补译永远进不了游戏。
        existing = {k for k in (_record_key(r) for r in target["dataList"]) if k}
        appended = 0
        for r in records:
            if not isinstance(r, dict):
                continue
            rk = _record_key(r)
            if rk is None or rk in existing:
                continue          # 零协已有同 id/key 记录 → 官方译文优先，不覆盖
            target["dataList"].append(r)
            existing.add(rk)
            appended += 1
        if not appended:
            report.files_skipped += 1
            return
        blob = (json.dumps(target, ensure_ascii=False, indent=2) + "\n").encode("utf-8-sig")
        if _same_bytes(dst, blob):
            report.files_skipped += 1
        else:
            atomic_write_bytes(dst, blob)
            report.files_written += 1
        report.supplement_records = getattr(report, "supplement_records", 0) + appended

    @staticmethod
    def _write_patched(src: Path, dst: Path, entries: list, report: DeployReport, rel: str) -> None:
        """把方案条目写进某个 json 后落盘（零协文件与补译文件共用这段逻辑）。

        - 补丁结果与副本现状字节一致 → 跳过写入（不动 mtime）；
        - 原文解析失败 / 条目定位失败 → 记录错误并按原样复制，绝不留半个补丁。
        """
        data, err = load_json(src)
        if data is None or not isinstance(data, dict) or not isinstance(data.get("dataList"), list):
            report.errors.append(f"{rel}: 无法解析原文（{err}），已按原样复制")
            Deployer._copy_if_needed(src, dst, report)
            return
        dl = data["dataList"]
        try:
            for e in entries:
                record = _find_record(dl, e.ref)
                set_value(record, e.ref.field_path, e.value)
            payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            # 游戏基线文件为 UTF-8 BOM 编码，写入带 BOM。
            blob = payload.encode("utf-8-sig")
            if _same_bytes(dst, blob):
                report.files_skipped += 1
            else:
                atomic_write_bytes(dst, blob)
                report.files_written += 1
        except KeyError as exc:
            report.errors.append(f"{rel}: 条目写入失败（{exc}），该文件未修改")
            Deployer._copy_if_needed(src, dst, report)

    @staticmethod
    def _copy_if_needed(src: Path, dst: Path, report: DeployReport) -> None:
        """按 (size, mtime_ns) 决定是否复制：一致则跳过，否则 copy2 全量复制。"""
        if _same_size_mtime(src, dst):
            report.files_skipped += 1
            return
        shutil.copy2(src, dst)
        report.files_copied += 1

    @staticmethod
    def _prune_empty_dirs(root: Path) -> None:
        for dirpath, dirnames, _ in reversed(list(root.walk())):
            for name in list(dirnames):
                d = Path(dirpath) / name
                try:
                    d.rmdir()
                except OSError:
                    pass

    # ---- config.json ----

    def set_lang_config(self, paths: GamePaths, lang: str) -> str | None:
        """把 Lang/config.json 的 lang 字段设为 lang（保留未知键），返回修改前的值。"""
        cfg_path = paths.config_path
        obj, err = load_json(cfg_path) if cfg_path.is_file() else (None, None)
        if not isinstance(obj, dict):
            obj = {"lang": "", "titleFont": "", "contextFont": "", "samplingPointSize": 78, "padding": 5}
        previous = obj.get("lang") if isinstance(obj.get("lang"), str) else None
        obj["lang"] = lang
        payload = json.dumps(obj, ensure_ascii=False, indent=2)
        json.loads(payload)
        atomic_write_text(cfg_path, payload)
        return previous

    # ---- 启用 / 停用 ----

    def enable(self, paths: GamePaths, patch_pack_name: str, profile: Profile, progress=None,
               supplements: dict[str, Path] | None = None) -> DeployReport:
        report = self.sync_clone(paths, patch_pack_name, profile, progress, supplements=supplements)
        if report.errors:
            return report
        report.previous_lang = self.set_lang_config(paths, patch_pack_name)
        self._write_applied(patch_pack_name, profile)
        return report

    def disable(self, paths: GamePaths, patch_pack_name: str, previous_lang: str | None) -> None:
        """把 lang 改回之前的语言包；仅当当前值是我们设置的副本包时才改。"""
        obj, err = load_json(paths.config_path) if paths.config_path.is_file() else (None, None)
        current = obj.get("lang") if isinstance(obj, dict) else None
        if current == patch_pack_name:
            self.set_lang_config(paths, previous_lang or "LLC_zh-CN")

    def remove_clone(self, paths: GamePaths, patch_pack_name: str) -> None:
        clone = paths.patch_pack_dir(patch_pack_name)
        if clone.is_dir():
            shutil.rmtree(clone, ignore_errors=True)

    # ---- 状态 ----

    def view(self, paths: GamePaths, patch_pack_name: str, profile: Profile) -> ApplyView:
        obj, _ = load_json(paths.config_path) if paths.config_path.is_file() else (None, None)
        config_lang = obj.get("lang") if isinstance(obj, dict) else None
        applied = self.load_applied() or {}
        return ApplyView(
            enabled=config_lang == patch_pack_name,
            config_lang=config_lang,
            revision_matches=applied.get("revision") == profile.revision
            and applied.get("patch_pack_name") == patch_pack_name,
            applied_revision=int(applied.get("revision") or 0),
        )

    # ---- 兼容性检查 ----

    def check_entries(self, paths: GamePaths, profile: Profile,
                      supplement: "SupplementPack | None" = None) -> dict[str, tuple[str, str]]:
        """对方案中每条目判定：ok / changed / missing / path_error。

        ``supplement`` 提供补译回退：零协包无该文件时改从 supplement/ 读原文
        （新章节文本只在补译目录时不再误报 missing）。
        """
        llc = paths.llc_pack_dir
        result: dict[str, tuple[str, str]] = {}
        for key, entry in profile.snapshot().items():  # 快照：部署线程可能同时在改条目
            ref = entry.ref
            src_dir = llc
            if not (llc / ref.file).is_file():
                if supplement is not None and (supplement.root / ref.file).is_file():
                    src_dir = supplement.root
                else:
                    result[key] = ("missing", "来源文件已不存在")
                    continue
            text, err = original_text(src_dir, ref)
            if text is None:
                result[key] = ("missing", f"无法定位：{err}")
                continue
            if sha256_text(text) != entry.original_hash:
                result[key] = ("changed", "原文已变化，建议确认")
            else:
                result[key] = ("ok", "可继续使用")
        return result
