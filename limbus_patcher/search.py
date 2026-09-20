"""索引检索：原文 / 自定义文本 / KeyID 搜索 + 章节/关卡/赛季/种类筛选。"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .index import normalize
from .patch import EntryRef, decode_fp, encode_fp, ref_label
from .story import chapter_sort_key


@dataclass(frozen=True)
class SearchHit:
    file: str
    category: str
    chapter: str | None
    ref: EntryRef
    text: str
    character: str | None = None
    chapter_id: str | None = None
    chapter_label: str | None = None
    level_key: str | None = None
    level_label: str | None = None
    season: str | None = None
    season_label: str | None = None
    acq_label: str | None = None
    kind_group: str | None = None
    kind_label: str | None = None
    sinner_code: str | None = None
    sinner_name: str | None = None
    text_en: str | None = None  # 英文基线原文（None = 英文侧缺该字段/该文件无基线）
    role: str = ""  # 实体角色：identity / identity_skill / identity_story / identity_voice / ego…
    entity_key: str | None = None  # 所属人格/EGO（"P:10310" / "E:20106"）
    source: str = "llc"            # 文本来自零协包（llc）还是补译文件（supplement）

    @property
    def ref_key(self) -> str:
        return self.ref.key()

    @property
    def display_key(self) -> str:
        """列表/详情显示用的键：无 id 的记录显示「记录 #N」，不会出现 "None"。"""
        return ref_label(self.ref)


def _row_to_hit(row: tuple) -> SearchHit:
    (
        relpath, cat, chapter, rec_index, id_json, fp_json, text, character,
        chapter_id, chapter_label, level_key, level_label,
        season, season_label, acq_label, kind_group, kind_label,
        sinner_code, sinner_name, text_en, role, entity_key, source,
    ) = row
    # 无 id 的记录在库里存的是 JSON null → rid 为 None（不会崩，也不影响定位）
    rid = json.loads(id_json) if id_json else None
    ref = EntryRef(file=relpath, id=rid, record_index=rec_index, field_path=decode_fp(fp_json))
    return SearchHit(
        file=relpath, category=cat, chapter=chapter, ref=ref, text=text, character=character,
        chapter_id=chapter_id, chapter_label=chapter_label, level_key=level_key, level_label=level_label,
        season=season, season_label=season_label, acq_label=acq_label,
        kind_group=kind_group, kind_label=kind_label,
        sinner_code=sinner_code, sinner_name=sinner_name, text_en=text_en,
        role=role or "", entity_key=entity_key, source=source or "llc",
    )


_SELECT = (
    "SELECT f.relpath, f.category, f.chapter, e.record_index, e.id_json, e.field_path, e.text, e.character,"
    " f.chapter_id, f.chapter_label, f.level_key, f.level_label,"
    " e.season, e.season_label, e.acq_label, e.kind_group, e.kind_label,"
    " e.sinner_code, e.sinner_name, e.text_en, e.role, e.entity_key, f.source"
    " FROM entries e JOIN files f ON f.file_id = e.file_id"
)

# 搜索范围（界面下拉取值）
SCOPE_LABELS: dict[str, str] = {
    "original": "原文",
    "baseline": "英文",
    "custom": "自定义",
    "all": "全部",
}


class SearchEngine:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)

    def baseline_stats(self) -> tuple[int, int]:
        """(有英文原文的叶子数, 总叶子数)；索引不可用时返回 (0, 0)。"""
        try:
            con = self._connect()
        except sqlite3.OperationalError:
            return 0, 0
        try:
            row = con.execute(
                "SELECT COUNT(*), COUNT(text_en) FROM entries"
            ).fetchone()
        except sqlite3.Error:
            return 0, 0
        finally:
            con.close()
        return int(row[1] or 0), int(row[0] or 0)

    # ---- 元数据查询（自定义文本搜索用） ----

    def lookup_meta(self, refs: list[EntryRef]) -> dict[str, dict]:
        """按 (file, record_index) 批量取索引元数据，键为 EntryRef.key()。

        方案里的自定义条目不在索引检索结果里（它们在 profiles/*.json），但筛选
        （分类/章节/赛季/种类/罪人）与列表展示需要索引里的元数据，这里一次性取回。
        """
        pairs = [(r.file, int(r.record_index)) for r in (refs or []) if r is not None]
        if not pairs:
            return {}
        out: dict[str, dict] = {}
        try:
            con = self._connect()
        except sqlite3.OperationalError:
            return {}
        try:
            for i in range(0, len(pairs), 400):  # 分批，避开 SQLite 变量上限
                chunk = pairs[i:i + 400]
                placeholders = ",".join("(?,?)" for _ in chunk)
                args: list = []
                for rel, idx in chunk:
                    args += [rel, idx]
                sql = _SELECT + f" WHERE (f.relpath, e.record_index) IN (VALUES {placeholders})"
                for row in con.execute(sql, args):
                    hit = _row_to_hit(row)
                    out[hit.ref.key()] = hit
        except sqlite3.Error:
            return out
        finally:
            con.close()
        return out

    # ---- 实体（人格 / E.G.O） ----

    def list_entities(self, kind: str, sinner_code: str | None = None) -> list[dict]:
        """按罪人+序号列出实体；kind 为 personality / ego。"""
        sql = ("SELECT entity_key, kind, entity_id, sinner_code, sinner_name, seq, name, title,"
               " name_with_title, desc, variant, skill_count, story_count, voice_count, passive_count,"
               " source_file"
               " FROM entities WHERE kind = ?"
               + (" AND sinner_code = ?" if sinner_code else "")
               + " ORDER BY sinner_code, seq")
        args: list = [kind] + ([sinner_code] if sinner_code else [])
        rows = self._query(sql, tuple(args))
        keys = ("entity_key", "kind", "entity_id", "sinner_code", "sinner_name", "seq", "name",
                "title", "name_with_title", "desc", "variant", "skill_count", "story_count",
                "voice_count", "passive_count", "source_file")
        return [dict(zip(keys, r)) for r in rows]

    def entity_summary(self, entity_key: str) -> dict | None:
        """实体详情 + 各角色条目数（用于实体卡片）。"""
        rows = self._query(
            "SELECT entity_key, kind, entity_id, sinner_code, sinner_name, seq, name, title,"
            " name_with_title, desc, variant, source_file,"
            " skill_count, story_count, voice_count, passive_count FROM entities WHERE entity_key = ?",
            (entity_key,),
        )
        if not rows:
            return None
        keys = ("entity_key", "kind", "entity_id", "sinner_code", "sinner_name", "seq", "name",
                "title", "name_with_title", "desc", "variant", "source_file",
                "skill_count", "story_count", "voice_count", "passive_count")
        out = dict(zip(keys, rows[0]))
        out["role_counts"] = {r: n for r, n in self._query(
            "SELECT role, COUNT(*) FROM entries WHERE entity_key = ? GROUP BY role", (entity_key,))}
        return out

    def count_by_role(self) -> dict[str, int]:
        """角色 → 条目数（导航计数用）。"""
        return {r: n for r, n in self._query("SELECT role, COUNT(*) FROM entries GROUP BY role")}

    def count_by_entity_role(self, roles: list[str]) -> dict[tuple[str, str], int]:
        """{(entity_key, role): 条目数}（实体一览的行内计数）。"""
        roles = [r for r in (roles or []) if r]
        if not roles:
            return {}
        placeholders = ",".join("?" * len(roles))
        rows = self._query(
            f"SELECT entity_key, role, COUNT(DISTINCT file_id || '#' || record_index) FROM entries"
            f" WHERE entity_key IS NOT NULL AND role IN ({placeholders}) GROUP BY entity_key, role",
            tuple(roles),
        )
        return {(r[0], r[1]): r[2] for r in rows}

    def count_entities(self, kind: str) -> int:
        rows = self._query("SELECT COUNT(*) FROM entities WHERE kind = ?", (kind,))
        return int(rows[0][0]) if rows else 0

    def search(
        self,
        text: str | None = None,
        category: str | None = None,
        categories: list[str] | None = None,
        chapter: str | None = None,
        level: str | None = None,
        season: str | None = None,
        kind_label: str | None = None,
        sinner_code: str | None = None,
        limit: int = 500,
        scope: str = "original",
        entity_key: str | None = None,
        source: str | None = None,
        roles: list[str] | None = None,
        order: str = "relevance",
        field_path: list | None = None,
    ) -> list[SearchHit]:
        """按关键词搜索。scope：original（零协原文）/ baseline（英语原文）/ all（两者+KeyID）。

        order：relevance（默认，短文本优先）/ natural（按文件与记录顺序，浏览实体内容时用）。


        ``custom``（自定义文本）由调用方在 Python 侧合并——方案体量小，见 main_window。
        """
        where: list[str] = []
        params: list = []
        if text:
            # 无 id 记录的 id_norm 是空串（不是 "none"），所以 KeyID 搜索不会误命中它们
            q = f"%{normalize(text)}%"
            if scope == "baseline":
                where.append("e.text_en_norm LIKE ?")
                params.append(q)
            elif scope == "all":
                where.append("(e.text_norm LIKE ? OR e.text_en_norm LIKE ? OR e.id_norm LIKE ?)")
                params += [q, q, q]
            else:
                where.append("(e.text_norm LIKE ? OR e.id_norm LIKE ?)")
                params += [q, q]
        if field_path:
            where.append("e.field_path = ?")
            params.append(encode_fp(field_path))
        if entity_key:
            where.append("e.entity_key = ?")
            params.append(entity_key)
        if source:
            where.append("f.source = ?")
            params.append(source)
        if roles:
            where.append(f"e.role IN ({','.join('?' * len(roles))})")
            params.extend(roles)
        if categories is None and category:
            categories = [category]
        if categories:
            where.append(f"f.category IN ({','.join('?' * len(categories))})")
            params.extend(categories)
        if chapter:
            where.append("f.chapter_id = ?")
            params.append(chapter)
        if level:
            where.append("f.level_key = ?")
            params.append(level)
        if season:
            where.append("e.season = ?")
            params.append(season)
        if kind_label:
            where.append("e.kind_label = ?")
            params.append(kind_label)
        if sinner_code:
            where.append("e.sinner_code = ?")
            params.append(sinner_code)
        # relevance：短文本优先（搜索命中更贴切）；natural：按文件/记录/字段顺序（浏览技能、剧情、语音用）
        if order == "natural":
            tail = " ORDER BY f.relpath ASC, e.record_index ASC, e.field_path ASC LIMIT ?"
        else:
            tail = " ORDER BY length(e.text) ASC, f.relpath ASC LIMIT ?"
        sql = _SELECT + (" WHERE " + " AND ".join(where) if where else "") + tail
        params.append(limit)
        hits: list[SearchHit] = []
        try:
            con = self._connect()
        except sqlite3.OperationalError:
            return hits
        try:
            for row in con.execute(sql, params):
                hits.append(_row_to_hit(row))
        finally:
            con.close()
        return hits

    def iter_refs(self, entity_key: str | None = None):
        """流式产出全部条目的定位信息（文件 / 记录 / KeyID / 字段路径 / 所属罪人）。

        用于「一键替换」里无法用 LIKE 预筛的场景（正则、自定义文本）——一次只取一行，
        不会把 17 万条命中全读进内存。
        """
        sql = ("SELECT f.relpath, e.record_index, e.id_json, e.field_path, e.sinner_name, e.character"
               " FROM entries e JOIN files f ON f.file_id = e.file_id")
        params: tuple = ()
        if entity_key:
            sql += " WHERE e.entity_key = ?"
            params = (entity_key,)
        try:
            con = self._connect()
        except sqlite3.OperationalError:
            return
        try:
            for relpath, rec_index, id_json, fp_json, sinner, character in con.execute(sql, params):
                rid = json.loads(id_json) if id_json else None
                yield (relpath, EntryRef(file=relpath, id=rid, record_index=rec_index,
                                         field_path=decode_fp(fp_json)), sinner or "", character or "")
        finally:
            con.close()

    # ---- 筛选下拉数据 ----

    def list_chapters(self) -> list[tuple[str, str]]:
        rows = self._query("SELECT DISTINCT chapter_id, chapter_label FROM files WHERE chapter_id IS NOT NULL")
        rows.sort(key=lambda r: chapter_sort_key(r[0]))
        return rows

    def list_levels(self, chapter_id: str) -> list[tuple[str, str]]:
        rows = self._query(
            "SELECT DISTINCT level_key, level_label FROM files WHERE chapter_id = ? AND level_key IS NOT NULL",
            (chapter_id,),
        )

        def key(row: tuple[str, str]) -> tuple:
            k = row[0]
            if k.startswith("p") and k[1:].isdigit():
                return (0, int(k[1:]), "")
            return (1, 0, row[1] or k)

        rows.sort(key=key)
        return rows

    def list_seasons(self) -> list[tuple[str, str]]:
        rows = self._query(
            "SELECT DISTINCT season, season_label FROM entries WHERE season IS NOT NULL AND season != ''"
        )
        # 同一 season 可能带不同展示名（常驻/基础），去重并优先「基础」
        seen: dict[str, str] = {}
        for k, label in rows:
            if k not in seen or (label == "基础" and seen[k] != "基础"):
                seen[k] = label

        def key(item: tuple[str, str]) -> tuple:
            k = item[0]
            if k == "base":
                return (0, 0)
            if k.startswith("s") and k[1:].isdigit():
                return (0, int(k[1:]))
            return (1, 0)

        out = sorted(seen.items(), key=key)
        return out

    def list_kinds(self) -> list[tuple[str, str]]:
        """返回 (kind_label, kind_label)，异想体危险等级优先。"""
        rows = self._query(
            "SELECT DISTINCT kind_label, kind_group FROM entries WHERE kind_label IS NOT NULL AND kind_label != ''"
        )
        risk = {"ZAYIN": 0, "TETH": 1, "HE": 2, "WAW": 3, "ALEPH": 4}

        def key(row: tuple[str, str]) -> tuple:
            label, group = row
            if label in risk:
                return (0, risk[label])
            if group == "abnormality":
                return (1, 0)
            if group == "faction":
                return (2, 0)
            return (3, 0)

        rows.sort(key=key)
        return [(label, label) for label, _ in rows]

    def count_by_sinner(self) -> dict[str, int]:
        """人格/E.G.O 文件按罪人编码的文件数（导航树用）。"""
        rows = self._query(
            "SELECT e.sinner_code, COUNT(DISTINCT e.file_id) FROM entries e"
            " JOIN files f ON f.file_id = e.file_id"
            " WHERE f.category IN ('identity','ego') AND e.sinner_code IS NOT NULL"
            " GROUP BY e.sinner_code"
        )
        return {code: n for code, n in rows}

    # ---- 其他 ----

    def count_by_category(self) -> dict[str, int]:
        return dict(self._query("SELECT category, COUNT(*) FROM files GROUP BY category"))

    def categories_present(self) -> list[str]:
        counts = self.count_by_category()
        return sorted(counts, key=lambda c: -counts[c])

    def _query(self, sql: str, params: tuple = ()) -> list[tuple]:
        """查库；索引还没建好 / 版本过旧时返回空表，绝不把启动流程炸掉。

        （界面在索引重建完成前也会查一次：旧库缺少新列时 execute 会抛
        ``no such column``，那属于「暂时查不到」，重建后即可正常。）
        """
        try:
            con = self._connect()
        except sqlite3.Error:
            return []
        try:
            return list(con.execute(sql, params))
        except sqlite3.Error:
            return []
        finally:
            con.close()
