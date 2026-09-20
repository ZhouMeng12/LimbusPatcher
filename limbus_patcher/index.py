"""零协包全量扫描 → SQLite 索引 + 文件清单（manifest）。

索引粒度：dataList 中每条记录的每个字符串叶子（含 levelList/coinlist 等嵌套）。
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .baseline import baseline_path, clear_cache as clear_baseline_cache, find_record as find_baseline_record
from .categories import chapter_hint, character_hint, classify, relpath_of, sinner_of
from .entities import (
    SINNER_NAMES,
    KIND_EGO,
    KIND_ENEMY,
    KIND_LABELS,
    KIND_PERSONALITY,
    ROLE_EGO,
    ROLE_EGO_PASSIVE,
    ROLE_EGO_SKILL,
    ROLE_EGO_VOICE,
    ROLE_ENEMY,
    ROLE_ENEMY_PASSIVE,
    ROLE_ENEMY_SKILL,
    ROLE_IDENTITY,
    ROLE_IDENTITY_PASSIVE,
    ROLE_IDENTITY_SKILL,
    ROLE_IDENTITY_STORY,
    ROLE_IDENTITY_VOICE,
    _enemy_entity_of,
    entity_id_of,
    entity_key,
    file_entity,
    is_enemy_id,
    is_ego_variant_id,
    is_excluded_entity,
    split_entity_id,
)
from .entities import sinner_name as entity_sinner_name
from .fsutil import load_json, sha256_file
from .patch import EntryRef, encode_fp, get_value, walk_leaves
from .season import MetaMaps, acq_display, kind_display, season_display, season_key
from .story import INTERVAL_CHAPTERS, story_of

MANIFEST_FORMAT = 1
#: **索引内容语义版本**：实体/角色推导、分类归属这类「代码逻辑」变了必须 +1。
#: 数据指纹（rules_stamp）只看数据文件，代码改了它看不出来 —— 结果就是
#: 「新版本程序 + 旧索引」：新加的东西（例如敌方实体）在库里根本不存在，
#: 界面只会静默变空/行为诡异。改这些逻辑时记得 +1。
BUILDER_VERSION = 9
# 5：敌方图鉴（enemy 实体 + 技能/被动/部位角色）
# 6：异想体技能 / 被动纳入敌方实体（Skills_Abnormality* / Passives_Abnormality*，支持 //1000 归属）
# 7：缺少 id 的记录（人格剧情等，id 记为 None，靠 record_index 定位）开始入索引；
# 8：并入英文基线文本（text_en / text_en_norm）供「英语原文」栏与英文搜索使用。
# 9：人格 / E.G.O 实体化（entities 表 + entries.entity_key/role），剧情/技能/语音归到实体名下。
# 12：人格/E.G.O 被动（Passives.json / Passive_Ego.json）+ entities.passive_count
# 13：12 的 entities 表可能没带上新列（升级时没重建 entities）→ 强制重建一次
# 14：重建时不再残留「已排除实体」（entity_exclude.json 里的愚人节人格曾以幽灵行留在图鉴里）
# 15：files 表加 source 列（llc / supplement）——补译文件也进索引，软件里能搜能改
# 10：分类规则与 AI 判定表（category_rules.json / misc_story_kinds.json）纳入索引指纹，改了就重建。
# 11：不再收录枚举/条件数据叶子（如 "(800101, VERY_HIGH)"），列表里不再出现这类伪条目。
# 旧库缺列/缺行，靠版本号不一致触发的整库重建补齐。
SCHEMA_VERSION = 15


#: 索引库必须齐全的关键列（缺任何一列都视为旧库，直接重建）
REQUIRED_COLUMNS: dict[str, set[str]] = {
    "files": {"file_id", "relpath", "category", "sha256", "source"},
    "entries": {"file_id", "record_index", "id_json", "field_path", "text", "text_norm",
                "entity_key", "role"},
    "entities": {"entity_key", "kind", "entity_id", "skill_count", "story_count", "voice_count",
                 "passive_count"},
}


def _fill_missing_baseline(baseline_manifest: dict, file_map: dict, baseline_dir) -> None:
    """给「被跳过的文件」补上英文基线记录（**必须**，否则每次启动都全量重建索引）。

    ``build()`` 只在能解析出 dataList 的文件上记 ``baseline_manifest``；
    零协包里有若干 2 字节的空壳文件（如 ``AbEvents-a1c5p1.json`` 内容是 ``{}``）会被结构检查跳过，
    但它们的英文基线 ``EN_*.json`` 是存在的。这样一来 ``manifest_matches()`` 会一直认为
    「新出现了英文基线文件」→ 每次启动都重建索引（实测 ~14 秒）。
    """
    if baseline_dir is None:
        return
    for rel in file_map:
        if rel in baseline_manifest:
            continue
        en_path = baseline_path(baseline_dir, rel)
        if en_path is None:
            baseline_manifest[rel] = None
            continue
        try:
            est = en_path.stat()
        except OSError:
            baseline_manifest[rel] = None
            continue
        baseline_manifest[rel] = {
            "rel": relpath_of(en_path, Path(baseline_dir)),
            "size": est.st_size,
            "mtime": est.st_mtime,
        }


def rules_stamp() -> str:
    """分类规则 + AI 判定表 + 赛季/敌方映射的**内容**指纹；变了索引必须重建。

    ⚠ 不能只看 size + mtime：打包成单文件 exe（onefile）后，这两个 json 位于
    sys._MEIPASS 的临时解包目录里，每次启动都重新解包 → mtime 每次都变 →
    指纹每次都不同 → manifest_matches() 永远返回 False → 每次启动都全量重建索引。
    （实测：manifest 里记下的指纹，对应的 mtime 正是当次启动的解包时刻。）
    改用内容 sha256：与解包时间无关，规则真的改了才重建；缺文件用固定占位，
    避免「忽有忽无」导致反复重建。
    """
    h = hashlib.sha256()
    for path in (rules_path(), kinds_path(), exclude_path(), season_path(), enemy_path()):
        h.update(path.name.encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(path.read_bytes())
        except OSError:
            h.update(b"-")
        h.update(b"\0")
    return h.hexdigest()[:16]


def rules_path():
    from .categories import rules_source

    return rules_source()


def kinds_path():
    from .season import package_data_dir

    return package_data_dir() / "misc_story_kinds.json"


def season_path():
    """赛季 / 获取方式映射（data/season_map.json）——内容变了索引里的赛季列就得重算。"""
    from .season import package_data_dir

    return package_data_dir() / "season_map.json"


def enemy_path():
    from .season import package_data_dir

    return package_data_dir() / "enemy_map.json"


def exclude_path():
    """不进图鉴的实体表（data/entity_exclude.json）——内容变了同样要重建索引。"""
    from .entities import EXCLUDE_PATH_NAME
    from .season import package_data_dir

    return package_data_dir() / EXCLUDE_PATH_NAME


def normalize(text: str) -> str:
    return "".join(text.lower().split())


@dataclass
class IndexResult:
    total_files: int = 0
    total_entries: int = 0
    baseline_hits: int = 0  # 拿到英文原文的叶子数
    entity_count: int = 0        # 人格 / E.G.O 实体数
    role_counts: dict[str, int] = field(default_factory=dict)  # 角色 → 文本叶子数
    baseline_dir: str | None = None
    warnings: list[str] = field(default_factory=list)
    category_counts: dict[str, int] = field(default_factory=dict)


class Indexer:
    def __init__(self, db_path: Path, manifest_path: Path, meta_overlay: Path | None = None,
                 supplement_dir: Path | None = None):
        self.db_path = db_path
        self.manifest_path = manifest_path
        self.meta_overlay = meta_overlay
        self.supplement_dir = Path(supplement_dir) if supplement_dir else None

    # ---- SQLite ----

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self.db_path))
        con.execute("PRAGMA journal_mode=WAL")
        if con.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            # 版本升级必须整库重建：entities 也要跟着丢掉，
            # 否则老表缺新列（如 passive_count），查询会静默失败、图鉴显示成空。
            con.executescript("DROP TABLE IF EXISTS entries; DROP TABLE IF EXISTS files;"
                              " DROP TABLE IF EXISTS entities; DROP TABLE IF EXISTS meta;")
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS files(
                file_id INTEGER PRIMARY KEY,
                relpath TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                chapter TEXT,
                sha256 TEXT NOT NULL,
                source TEXT DEFAULT 'llc',
                chapter_id TEXT,
                chapter_label TEXT,
                level_key TEXT,
                level_label TEXT
            );
            CREATE TABLE IF NOT EXISTS entries(
                file_id INTEGER NOT NULL,
                record_index INTEGER NOT NULL,
                id_json TEXT NOT NULL,
                field_path TEXT NOT NULL,
                text TEXT NOT NULL,
                text_norm TEXT NOT NULL,
                text_en TEXT,
                text_en_norm TEXT,
                entity_key TEXT,
                role TEXT,
                id_norm TEXT NOT NULL,
                character TEXT,
                season TEXT,
                season_label TEXT,
                acq_label TEXT,
                kind_group TEXT,
                kind_label TEXT,
                sinner_code TEXT,
                sinner_name TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_entries_norm ON entries(text_norm);
            CREATE INDEX IF NOT EXISTS idx_entries_en_norm ON entries(text_en_norm);
            CREATE INDEX IF NOT EXISTS idx_entries_entity ON entries(entity_key, role);
            CREATE INDEX IF NOT EXISTS idx_entries_file ON entries(file_id);
            CREATE INDEX IF NOT EXISTS idx_files_chapter ON files(chapter_id);
            CREATE INDEX IF NOT EXISTS idx_entries_season ON entries(season);
            CREATE TABLE IF NOT EXISTS entities(
                entity_key TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                sinner_code TEXT,
                sinner_name TEXT,
                seq INTEGER,
                name TEXT,
                title TEXT,
                name_with_title TEXT,
                desc TEXT,
                variant TEXT,
                season TEXT,
                season_label TEXT,
                source_file TEXT,
                skill_count INTEGER DEFAULT 0,
                story_count INTEGER DEFAULT 0,
                voice_count INTEGER DEFAULT 0,
                passive_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
            """
        )
        con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        return con

    # ---- manifest ----

    def load_manifest(self) -> dict | None:
        if not self.manifest_path.is_file():
            return None
        try:
            obj = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def source_path(root: Path, rel: str, strip_prefix: str = "") -> Path:
        """零协相对路径 → 当前来源下的实际文件（英文基线文件名带 EN_ 前缀）。"""
        if not strip_prefix:
            return Path(root) / rel
        p = Path(rel)
        return Path(root) / p.parent / f"{strip_prefix}{p.name}"

    def current_file_map(self, llc_dir: Path, strip_prefix: str = "") -> dict[str, dict]:
        files: dict[str, dict] = {}
        for p in llc_dir.rglob("*.json"):
            if not p.is_file():
                continue
            rel = relpath_of(p, llc_dir, strip_prefix=strip_prefix)
            try:
                st = p.stat()
            except OSError:
                continue
            files[rel] = {"sha256": sha256_file(p), "mtime": st.st_mtime, "size": st.st_size}
        return files

    def index_schema_ok(self) -> bool:
        """索引库存在、schema 版本与当前一致，且关键列齐全。

        SCHEMA_VERSION 变更后旧库必须整库重建；而重建仅由 manifest_matches()
        触发，所以这里一并校验索引库本身，避免「包没变 → 不重建 → 索引空」。
        另外校验关键列：老表缺新列时（例如 entities.passive_count）查询会静默失败，
        图鉴会显示成空，所以列不齐同样视为「需要重建」。
        """
        if not self.db_path.is_file():
            return False
        try:
            con = sqlite3.connect(str(self.db_path))
        except sqlite3.Error:
            return False
        try:
            if con.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                return False
            for table, columns in REQUIRED_COLUMNS.items():
                have = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
                if not columns <= have:
                    return False
            return True
        except sqlite3.Error:
            return False
        finally:
            con.close()

    def manifest_matches(self, llc_dir: Path, baseline_dir: Path | None = None,
                         strip_prefix: str = "") -> bool:
        """逐文件比较大小与修改时间，判断零协包 / 英文基线是否变化（无需全量哈希）。

        索引库缺失 / schema 版本落后时直接返回 False，促使调用方重建索引。
        ``baseline_dir`` 给了才校验英文基线（目录变化或英文文件增删改都会触发重建）。
        """
        if not self.index_schema_ok():
            return False
        m = self.load_manifest()
        if not m or m.get("format_version") != MANIFEST_FORMAT:
            return False
        if m.get("builder_version") != BUILDER_VERSION:
            return False  # 索引内容语义变了（代码逻辑升级）→ 必须重建
        if (m.get("strip_prefix") or "") != (strip_prefix or ""):
            return False  # 文本来源换了（零协 ↔ 英文基线）：相对路径体系不同，必须重建
        known = m.get("files") or {}
        current: dict[str, tuple[int, float]] = {}
        for p in llc_dir.rglob("*.json"):
            if not p.is_file():
                continue
            rel = relpath_of(p, llc_dir, strip_prefix=strip_prefix)
            try:
                st = p.stat()
            except OSError:
                return False
            current[rel] = (st.st_size, st.st_mtime)
        if set(known) != set(current):
            return False
        for rel, (size, mtime) in current.items():
            info = known[rel]
            if info.get("size") != size or abs(info.get("mtime", 0) - mtime) > 1e-6:
                return False
        if m.get("rules_stamp") != rules_stamp():
            return False  # 分类规则 / AI 判定表变了：分类与章节要重新算（与英文基线无关）
        if baseline_dir is None:
            return True  # 未要求校验英文基线
        if (m.get("baseline_dir") or "") != str(baseline_dir):
            return False  # 换了基线语言/目录，必须重建才能拿到英文列
        saved = m.get("baseline_files") or {}
        for rel in current:
            was = saved.get(rel)
            now_path = baseline_path(baseline_dir, rel)
            if was is None:
                if now_path is not None:
                    return False  # 新出现的英文基线文件
                continue
            if now_path is None:
                return False  # 英文基线文件被删了
            try:
                st = now_path.stat()
            except OSError:
                return False
            if was.get("size") != st.st_size or abs(was.get("mtime", 0) - st.st_mtime) > 1e-6:
                return False
        return True

    # ---- build ----

    # ---- 人格 / E.G.O 实体 ----

    def _collect_entities(self, file_map: dict, llc_dir: Path, result: IndexResult,
                          strip_prefix: str = "") -> list[tuple]:
        """扫描本体文件（Personalities*/Egos*）建实体表；返回可直接 executemany 的行。"""
        rows: list[tuple] = []
        seen: set[str] = set()
        # 基础本体文件（无 -xxx 后缀）优先，DLC 文件只用来补新增实体
        def _entity_sort(rel: str) -> tuple:
            return (1 if "-" in rel.rsplit("/", 1)[-1] else 0, rel)

        for rel in sorted(file_map, key=_entity_sort):
            info = file_entity(rel)
            if info is None or info.role not in (ROLE_IDENTITY, ROLE_EGO, ROLE_ENEMY):
                continue
            data, err = load_json(self.source_path(llc_dir, rel, strip_prefix))
            if not isinstance(data, dict) or not isinstance(data.get("dataList"), list):
                result.warnings.append(f"{rel}: 实体文件无法解析（{err}），已跳过")
                continue
            for record in data["dataList"]:
                if not isinstance(record, dict):
                    continue
                rid = record.get("id")
                if not isinstance(rid, int) or rid < 10000:
                    # 敌方本体有 4 位 id（如 8061）：以 enemy_map.json 为准放行
                    if not (info.role == ROLE_ENEMY and is_enemy_id(rid)):
                        continue  # 9999（维吉里乌斯之类占位条目）不算人格/EGO
                if info.role == ROLE_ENEMY:
                    if str(record.get("desc") or "") == "部位" and not is_enemy_id(rid):
                        continue  # 真·部位（无实体登记）并入本体详情，不单独建实体
                    if not is_enemy_id(rid):
                        continue
                    kind = KIND_ENEMY
                    key = entity_key(kind, rid)
                    if key in seen:  # 同一实体在多个本体文件里
                        continue
                    seen.add(key)
                    desc = record.get("desc") if isinstance(record.get("desc"), str) else ""
                    rows.append((
                        key,
                        kind,
                        rid,
                        None,
                        None,
                        None,
                        record.get("name") if isinstance(record.get("name"), str) else None,
                        None,
                        None,
                        desc or None,
                        None,
                        None,
                        None,
                        rel,
                        0,
                        0,
                        0,
                        0,
                    ))
                    continue
                if info.role == ROLE_EGO and is_ego_variant_id(rid):
                    rid = rid // 10  # E.G.O 变体（6 位）归到基础实体，避免一览出现重复行
                kind = info.kind or KIND_PERSONALITY
                if is_excluded_entity(kind, rid):
                    result.warnings.append(f"{rel}: 实体 {rid} 在 entity_exclude.json 里，已跳过（不进图鉴）")
                    continue
                key = entity_key(kind, rid)
                if key in seen:  # 同一实体在多个本体文件里（如 Egos + Egos-a1c9p3）
                    continue
                seen.add(key)
                desc = record.get("desc") if isinstance(record.get("desc"), str) else ""
                sinner_code, seq = split_entity_id(rid)
                special = rid >= 400000  # 6 位 id：活动/特殊人格（如瓦尔普吉斯之夜「狱儿园」系列）
                if not entity_sinner_name(sinner_code):
                    # 特殊 id 的罪人码取不到时，从 desc「<罪人>的…人格」反查
                    sinner_code = next((c for c, n in SINNER_NAMES.items() if desc.startswith(n + "的")), sinner_code)
                if special:
                    seq = rid % 100
                # 校验：desc 里的「第N人格」应与 id 序号一致（不一致以 id 为准并记 warning）
                if kind == KIND_PERSONALITY:
                    m = re.search(r"第\s*(\d+)\s*人格", desc or "")
                    if m and m.group(1).isdigit() and int(m.group(1)) != seq:
                        result.warnings.append(
                            f"{rel}: 人格 {rid} 的 desc 写「第{m.group(1)}人格」但 id 序号是 {seq}，以 id 为准"
                        )
                rows.append((
                    key,
                    kind,
                    rid,
                    sinner_code,
                    entity_sinner_name(sinner_code),
                    seq,
                    record.get("name") if isinstance(record.get("name"), str) else None,
                    record.get("title") if isinstance(record.get("title"), str) else None,
                    record.get("nameWithTitle") if isinstance(record.get("nameWithTitle"), str) else None,
                    desc or None,
                    "special" if special else None,  # variant：special=活动特殊人格
                    None,
                    None,
                    rel,
                    0,
                    0,
                    0,
                    0,
                ))
        result.entity_count = len(rows)
        return rows

    def _supplement_files(self, llc_dir: Path) -> dict[str, Path]:
        """补译文件里「零协没有」的那些（零协已有同名文件时以零协为准，不重复索引）。"""
        if self.supplement_dir is None or not self.supplement_dir.is_dir():
            return {}
        from .supplement import SupplementPack

        base = self.supplement_dir.parent if self.supplement_dir.name == "supplement" else self.supplement_dir
        try:
            files = SupplementPack(base).files()
        except Exception:  # noqa: BLE001 —— 补译目录坏了不该挡住索引
            return {}
        out: dict[str, Path] = {}
        for f in files:
            if not f.enabled:
                continue
            if (Path(llc_dir) / f.rel).is_file():
                continue
            out[f.rel] = f.path
        return out

    def _index_supplements(self, con, llc_dir: Path, result: "IndexResult") -> list[tuple]:
        """把补译文件也写进 entries（source='supplement'），这样软件里能搜到、能编辑。

        只做最必要的事：分类 + 文本叶子 + KeyID；英文基线、赛季、实体归属照旧尽力而为。
        另外把补译的敌方本体（Enemies-*.json 中 enemy_map 登记过的 id）收集成
        entities 行返回，由 build() 合并入库 —— 新章节敌人（零协包没有）从此能进图鉴。
        """
        from .baseline import baseline_path
        from .categories import character_hint
        from .entities import entity_id_of
        from .patch import encode_fp, walk_leaves

        sup = self._supplement_files(llc_dir)
        if not sup:
            return []
        sup_entity_rows: list[tuple] = []
        for rel, path in sorted(sup.items()):
            data, err = load_json(path)
            dl = data.get("dataList") if isinstance(data, dict) else None
            if not isinstance(dl, list):
                result.warnings.append(f"{rel}: 补译文件结构异常（{err}），未入索引")
                continue
            info = file_entity(rel)
            if info is not None and info.role == ROLE_ENEMY:
                # 补译敌方本体 → entities 行（kind='enemy'），供敌方图鉴 list_entities 查询
                seen: set[str] = set()
                for record in dl:
                    if not isinstance(record, dict):
                        continue
                    ent_key, role = _enemy_entity_of(info, record)
                    if role != ROLE_ENEMY or ent_key is None or ent_key in seen:
                        continue
                    seen.add(ent_key)
                    rid = record.get("id")
                    desc = record.get("desc") if isinstance(record.get("desc"), str) else ""
                    sup_entity_rows.append((
                        ent_key, KIND_ENEMY, rid, None, None, None,
                        record.get("name") if isinstance(record.get("name"), str) else None,
                        None, None, desc or None, None, None, None, rel,
                        0, 0, 0, 0,
                    ))
            maps = MetaMaps(overlay_dir=self.meta_overlay)
            cat = classify(rel)
            chap = chapter_hint(rel)
            story = story_of(rel)
            season_label = acq_label = None
            en_path = baseline_path(self.baseline_dir, rel) if getattr(self, "baseline_dir", None) else None
            en_data, _e = load_json(en_path) if en_path else (None, None)
            en_dl = en_data.get("dataList") if isinstance(en_data, dict) else None
            with con:
                cur = con.execute(
                    "INSERT INTO files(relpath, category, chapter, sha256, chapter_id, chapter_label,"
                    " level_key, level_label, source) VALUES(?,?,?,?,?,?,?,?,?)",
                    (rel, cat, chap, sha256_file(path),
                     story.chapter_id if story else None,
                     story.chapter_label if story else None,
                     story.level_key if story else None,
                     story.level_label if story else None,
                     "supplement"),
                )
                file_id = cur.lastrowid
                rows: list[tuple] = []
                for rec_index, record in enumerate(dl):
                    if not isinstance(record, dict):
                        continue
                    rid = record.get("id")
                    id_json = json.dumps(rid, ensure_ascii=False, separators=(",", ":"))
                    id_norm = "" if rid is None else normalize(str(rid))
                    character = character_hint(rel, record)
                    ent_key, ent_role = entity_id_of(rel, record)
                    season = None
                    if ent_key:
                        meta = (maps.identity_meta(ent_key.split(":")[-1])
                                if ent_key.startswith("P:") else maps.ego_meta(ent_key.split(":")[-1]))
                        if meta:
                            season = season_key(meta)
                            season_label = season_display(meta)
                            acq_label = acq_display(meta)
                    en_record = None
                    if isinstance(en_dl, list) and rec_index < len(en_dl) and isinstance(en_dl[rec_index], dict):
                        en_record = en_dl[rec_index]
                    for fp, text in walk_leaves(record):
                        text_en = None
                        if en_record is not None:
                            try:
                                v = get_value(en_record, fp)
                                if isinstance(v, str) and v.strip():
                                    text_en = v
                            except KeyError:
                                text_en = None
                        rows.append((
                            file_id, rec_index, id_json, encode_fp(fp), text, normalize(text),
                            text_en, normalize(text_en) if text_en else None, id_norm,
                            character, season, season_label if ent_key else None,
                            acq_label if ent_key else None, None, None,
                            None, None, ent_key, ent_role,
                        ))
                if rows:
                    con.executemany(
                        "INSERT INTO entries(file_id, record_index, id_json, field_path, text, text_norm,"
                        " text_en, text_en_norm, id_norm,"
                        " character, season, season_label, acq_label, kind_group, kind_label,"
                        " sinner_code, sinner_name, entity_key, role)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        rows,
                    )
                result.total_files += 1
                result.total_entries += len(rows)
        return sup_entity_rows

    @staticmethod
    def _fill_entity_counts(entity_rows: list[tuple], role_records: dict[tuple[str, str], int]) -> list[tuple]:
        """把 (实体, 角色) 的记录数写进 entities 的 skill/story/voice_count 列。"""
        slots = {
            ROLE_IDENTITY_SKILL: ("skill_count", 14),
            ROLE_IDENTITY_STORY: ("story_count", 15),
            ROLE_IDENTITY_VOICE: ("voice_count", 16),
            ROLE_IDENTITY_PASSIVE: ("passive_count", 17),
            ROLE_EGO_SKILL: ("skill_count", 14),
            ROLE_EGO_VOICE: ("voice_count", 16),
            ROLE_EGO_PASSIVE: ("passive_count", 17),
            ROLE_ENEMY_SKILL: ("skill_count", 14),
            ROLE_ENEMY_PASSIVE: ("passive_count", 17),
        }
        out = []
        for row in entity_rows:
            values = list(row)
            key = values[0]
            for role, (name, index) in slots.items():
                n = role_records.get((key, role))
                if n:
                    values[index] = n
            out.append(tuple(values))
        return out

    def build(self, llc_dir: Path, progress=None, baseline_dir: Path | None = None,
              strip_prefix: str = "") -> IndexResult:
        """全量重建索引与 manifest。progress 为 callable(processed, total)。

        ``baseline_dir``：游戏英文基线目录（``Localize/en``）。给了就把英文原文一并写入
        ``text_en`` / ``text_en_norm``（缺英文的行写 NULL，界面会显示具体原因）。
        """
        result = IndexResult()
        baseline_dir = Path(baseline_dir) if baseline_dir else None
        result.baseline_dir = str(baseline_dir) if baseline_dir else None
        clear_baseline_cache()
        baseline_manifest: dict[str, dict | None] = {}  # 零协 rel → 英文基线文件信息（None = 该文件没有英文）
        maps = MetaMaps(overlay_dir=self.meta_overlay)
        file_map = self.current_file_map(llc_dir, strip_prefix=strip_prefix)
        entity_rows = self._collect_entities(file_map, llc_dir, result, strip_prefix=strip_prefix)
        entity_role_records: dict[tuple[str, str], int] = {}  # (entity_key, role) → 记录数
        total = len(file_map)
        con = self._connect()
        try:
            with con:
                con.execute("DELETE FROM entries")
                con.execute("DELETE FROM files")
                con.execute("DELETE FROM meta")
                # 实体表也要清：INSERT OR REPLACE 不会删掉「这次不再收录」的实体
                # （例如把愚人节人格写进 entity_exclude.json 后重建），留着就是幽灵人格。
                con.execute("DELETE FROM entities")
            processed = 0
            for rel, info in file_map.items():
                p = self.source_path(llc_dir, rel, strip_prefix)
                data, err = load_json(p)
                if data is None or not isinstance(data, dict):
                    result.warnings.append(f"{rel}: 跳过（{err}）")
                    processed += 1
                    if progress:
                        progress(processed, total)
                    continue
                dl = data.get("dataList")
                if not isinstance(dl, list):
                    result.warnings.append(f"{rel}: 结构异常（缺少 dataList 数组）")
                    processed += 1
                    if progress:
                        progress(processed, total)
                    continue
                cat = classify(rel)
                chap = chapter_hint(rel)
                # 英文基线文件与零协文件一一对应（Localize/<lang>/<目录>/EN_<文件名>）
                en_path = baseline_path(baseline_dir, rel) if baseline_dir else None
                en_data = None
                if en_path is not None:
                    en_data, _en_err = load_json(en_path)
                en_dl = en_data.get("dataList") if isinstance(en_data, dict) else None
                if not isinstance(en_dl, list):
                    en_dl = None
                if en_path is not None:
                    try:
                        est = en_path.stat()
                        baseline_manifest[rel] = {"rel": relpath_of(en_path, baseline_dir),
                                                 "size": est.st_size, "mtime": est.st_mtime}
                    except OSError:
                        baseline_manifest[rel] = None
                else:
                    baseline_manifest[rel] = None
                story = story_of(rel)
                # 间章（3.5/4.5/5.5/6.5/7.5/7.5续/8.5/8.5EX）剧情归入「主线剧情」，
                # 使「主线剧情 + 章节=间章」可以查到间章文本
                if cat == "event" and story and story.chapter_id in INTERVAL_CHAPTERS:
                    cat = "main_story"
                with con:
                    cur = con.execute(
                        "INSERT INTO files(relpath, category, chapter, sha256, chapter_id, chapter_label, level_key, level_label)"
                        " VALUES(?,?,?,?,?,?,?,?)",
                        (
                            rel,
                            cat,
                            chap,
                            info["sha256"],
                            story.chapter_id if story else None,
                            story.chapter_label if story else None,
                            story.level_key if story else None,
                            story.level_label if story else None,
                        ),
                    )
                    file_id = cur.lastrowid
                    rows: list[tuple] = []
                    for rec_index, record in enumerate(dl):
                        if not isinstance(record, dict):
                            result.warnings.append(f"{rel}: 记录 #{rec_index} 不是对象，已跳过")
                            continue
                        # 缺少 id 字段的记录（真实零协包里约 689 条，基本都是人格剧情）
                        # 同样入索引：id 记为 None（id_json 存 JSON null，列类型不变），
                        # 定位完全依赖 record_index（见 deploy._find_record 的「先下标后 id」）。
                        rid = record.get("id")
                        id_json = json.dumps(rid, ensure_ascii=False, separators=(",", ":"))
                        # 无 id 时不做 id 归一化匹配，否则会退化成字符串 "none" 而误命中
                        id_norm = "" if rid is None else normalize(str(rid))
                        character = character_hint(rel, record)
                        sinner = sinner_of(cat, rid) if rid is not None else None
                        sinner_code, sinner_name = (sinner if sinner else (None, None))
                        if character is None and sinner_name:
                            character = sinner_name

                        # 赛季（人格/E.G.O）与敌方种类
                        season = season_label = acq = None
                        kind_group = kind_label = None
                        if cat == "identity":
                            meta = maps.identity_meta(rid)
                            season, season_label, acq = season_key(meta), season_display(meta), acq_display(meta)
                        elif cat == "ego":
                            meta = maps.ego_meta(rid)
                            season, season_label, acq = season_key(meta), season_display(meta), acq_display(meta)
                        elif cat == "enemy":
                            meta = maps.enemy_meta(rid)
                            if meta:
                                kind_group = meta.get("group")
                                kind_label = kind_display(meta)

                        # 英文基线：按 KeyID 命中（找不到才在「至少一侧无 KeyID」时用同下标）
                        en_record = None
                        if en_dl is not None and en_dl:
                            ref = EntryRef(file=rel, id=rid, record_index=rec_index, field_path=[])
                            en_record = find_baseline_record(en_dl, ref)

                        ent_key, ent_role = entity_id_of(rel, record)
                        if ent_key:
                            slot = (ent_key, ent_role)
                            entity_role_records[slot] = entity_role_records.get(slot, 0) + 1
                        if ent_role != "other":
                            result.role_counts[ent_role] = result.role_counts.get(ent_role, 0) + 1
                        else:
                            result.role_counts["other"] = result.role_counts.get("other", 0) + 1

                        for fp, text in walk_leaves(record):
                            text_en = None
                            if en_record is not None:
                                try:
                                    value = get_value(en_record, fp)
                                except (KeyError, IndexError, TypeError):
                                    value = None
                                if isinstance(value, str) and value.strip():
                                    text_en = value
                                    result.baseline_hits += 1
                            rows.append(
                                (
                                    file_id, rec_index, id_json, encode_fp(fp), text, normalize(text),
                                    text_en, normalize(text_en) if text_en else None, id_norm,
                                    character, season, season_label, acq, kind_group, kind_label,
                                    sinner_code, sinner_name,
                                    ent_key, ent_role,
                                )
                            )
                    con.executemany(
                        "INSERT INTO entries(file_id, record_index, id_json, field_path, text, text_norm,"
                        " text_en, text_en_norm, id_norm,"
                        " character, season, season_label, acq_label, kind_group, kind_label,"
                        " sinner_code, sinner_name, entity_key, role)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        rows,
                    )
                    result.total_entries += len(rows)
                result.total_files += 1
                result.category_counts[cat] = result.category_counts.get(cat, 0) + 1
                processed += 1
                if progress:
                    progress(processed, total)
            sup_entity_rows = self._index_supplements(con, llc_dir, result)
            with con:
                if entity_rows or sup_entity_rows:
                    entity_rows = self._fill_entity_counts(entity_rows + sup_entity_rows, entity_role_records)
                    con.executemany(
                        "INSERT OR REPLACE INTO entities(entity_key, kind, entity_id, sinner_code, sinner_name,"
                        " seq, name, title, name_with_title, desc, variant, season, season_label, source_file,"
                        " skill_count, story_count, voice_count, passive_count)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        entity_rows,
                    )
                con.execute(
                    "INSERT INTO meta(key, value) VALUES(?,?)",
                    ("built_at", datetime.now().isoformat(timespec="seconds")),
                )
                con.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)",
                    ("baseline_dir", result.baseline_dir or ""),
                )
                con.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)",
                    ("rules_stamp", rules_stamp()),
                )
            self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
            _fill_missing_baseline(baseline_manifest, file_map, baseline_dir)
            self.manifest_path.write_text(
                json.dumps(
                    {
                        "format_version": MANIFEST_FORMAT,
                        "builder_version": BUILDER_VERSION,
                        "generated_at": datetime.now().isoformat(timespec="seconds"),
                        "llc_dir": str(llc_dir),
                        "strip_prefix": strip_prefix,
                        "rules_stamp": rules_stamp(),
                        "baseline_dir": result.baseline_dir or "",
                        "baseline_files": baseline_manifest,
                        "files": file_map,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        finally:
            con.close()
        return result
