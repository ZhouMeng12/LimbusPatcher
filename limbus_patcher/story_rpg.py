"""RPG 关卡剧本数据（第十二章起的新形态：一章里夹着 RPG 探索关）。

第十章 10-4 是第一个 RPG 关卡：它的剧情不在 ``StoryData`` 的过场文件里，
而是分散在 ``RPGSystem/`` 的楼层对话 / 选项 / 旁白文件里，与过场交替出现。
本地化文件里**没有**触发器数据（触发器在游戏资源里），所以「玩家游玩顺序」
只能靠编排表人工确定：

``limbus_patcher/data/story_rpg_plan.json`` 是本模块的**唯一事实源**——
每个 stage 下按玩家顺序列出 ``branches``，每个 branch 由若干 ``parts``
（文件 + dataList 记录区间）组成，并记录该段顺序的 ``evidence``（依据）
与 ``confidence``（把握度）。改顺序只改编排表，重跑
``scripts/build_story_rpg.py`` 即幂等重建。

文本一律以零协包（``Lang/LLC_zh-CN``）为准；零协没有该文件时才回退
``data/supplement``，仍没有才用英文基线（并在 ``warnings`` 里点名）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .patch import EntryRef
from .season import package_data_dir

PLAN_FILENAME = "story_rpg_plan.json"

#: 「0901追加」这类开发遗留的任务描述（零协包原文即如此），不进剧本骨架
_JUNK_QUEST_DESC = re.compile(r"^\s*\d+\s*追加\s*$")
#: 标题里带「未使用」的任务是游戏里没启用的内容，不进骨架
_JUNK_QUEST_TITLE = "未使用"

_ROLE_MARKERS = {
    "choice": "◇ 选择项",
    "narration": "◇ 旁白",
}


def plan_path(data_dir: Path | None = None) -> Path:
    return (Path(data_dir) / PLAN_FILENAME) if data_dir else (package_data_dir() / PLAN_FILENAME)


def load_plan(data_dir: Path | None = None) -> dict:
    """读取编排表；文件不存在或损坏时返回空表（调用方按「无 RPG 编排」处理）。"""
    p = plan_path(data_dir)
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"format_version": 1, "stages": {}}
    if not isinstance(obj, dict) or not isinstance(obj.get("stages"), dict):
        return {"format_version": 1, "stages": {}}
    return obj


def stage_plan(plan: dict, stage_code: str) -> dict | None:
    st = (plan.get("stages") or {}).get(stage_code)
    return st if isinstance(st, dict) and st.get("branches") else None


def _read_json(path: Path) -> dict | None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def _part_role(rel: str, part: dict) -> str:
    role = part.get("role")
    if isinstance(role, str) and role:
        return role
    name = Path(rel).name
    if "-choice" in name:
        return "choice"
    if "narration" in name:
        return "narration"
    return "dialogue"


def _record_lines(rec: dict):
    """把一条 dataList 记录摊平成 (text, speaker, title, text_index, field)。

    ``field`` 是该文本在记录里的字段名，编辑定位要用：
    过场是 ``content``、RPG 选项/地点是 ``text``、RPG 对话是 ``texts[i].text``。
    """
    texts = rec.get("texts")
    if isinstance(texts, list):
        for pos, t in enumerate(texts):
            if not isinstance(t, dict):
                continue
            text = t.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            idx = t.get("index")
            yield text, t.get("speaker"), None, (idx if isinstance(idx, int) else pos), "texts"
        return
    content = rec.get("content")
    if isinstance(content, str) and content.strip():
        yield content, rec.get("teller"), rec.get("title"), None, "content"
        return
    text = rec.get("text")
    if isinstance(text, str) and text.strip():
        yield text, None, None, None, "text"


def load_quests(llc_dir: Path, rels: list[str], supplement_dir: Path | None = None) -> dict[str, dict]:
    """读取任务表（RPG 的任务标题/描述 = 剧本骨架）。返回 {key: {...}}。"""
    out: dict[str, dict] = {}
    for rel in rels:
        data = _read_json(Path(llc_dir) / rel)
        if data is None and supplement_dir is not None:
            data = _read_json(Path(supplement_dir) / rel)
        if data is None:
            continue
        for rec in data.get("dataList") or []:
            if not isinstance(rec, dict) or not rec.get("key"):
                continue
            out[str(rec["key"])] = {
                "key": str(rec["key"]),
                "title": (rec.get("title") or "").strip(),
                "description": (rec.get("description") or "").strip(),
                "file": rel,
            }
    return out


def is_skeleton_quest(q: dict) -> bool:
    """该任务是否值得进剧本骨架（去掉空描述、开发遗留、未启用任务）。"""
    title = q.get("title") or ""
    desc = q.get("description") or ""
    if not title or _JUNK_QUEST_TITLE in title:
        return False
    if not desc or _JUNK_QUEST_DESC.match(desc):
        return False
    return True


def quest_scene_text(q: dict) -> str:
    title = q.get("title") or ""
    desc = q.get("description") or ""
    return f"【任务】{q.get('key')} {title}：{desc}" if desc else f"【任务】{q.get('key')} {title}"


def build_stage(
    stage: dict,
    llc_dir: Path,
    supplement_dir: Path | None = None,
    en_dir: Path | None = None,
) -> dict:
    """按编排表展开一个 RPG 关卡，返回 {"branches", "pages", "items", "warnings"}。"""
    llc_dir = Path(llc_dir)
    quests = load_quests(llc_dir, list(stage.get("quest_files") or []), supplement_dir)

    branches: list[dict] = []
    pages: list[dict] = []
    items: list[dict] = []
    warnings: list[str] = []

    for br in stage.get("branches") or []:
        bid = str(br.get("id") or "")
        label = str(br.get("label") or bid)
        kind = str(br.get("kind") or "rpg")
        kind_label = str(br.get("kind_label") or "")
        if not bid:
            warnings.append("编排表里有分支缺少 id，已跳过")
            continue

        branch = {
            "branch_id": bid,
            "label": label,
            "kind": kind,
            "kind_label": kind_label,
            "confidence": br.get("confidence") or "",
            "evidence": br.get("evidence") or "",
            "files": [str(p.get("file")) for p in br.get("parts") or [] if p.get("file")],
        }
        branches.append(branch)
        pages.append({
            "segment": kind_label or kind,
            "title": label,
            "file": branch["files"][0] if branch["files"] else None,
            "files": list(branch["files"]),
            "branch_id": bid,
            "kind": kind,
        })

        # 分支标题行 + 任务骨架行（骨架行不可编辑，只是给读者看推进线）
        items.append({
            "type": "scene", "branch": bid, "text": label, "file": None, "record": None,
            "page": label, "kind": kind, "source": "plan",
        })
        for qkey in br.get("quests") or []:
            q = quests.get(str(qkey))
            if q is None:
                warnings.append(f"{label}：任务表里没有 {qkey}")
                continue
            if not is_skeleton_quest(q):
                continue
            # 任务行同样只存位置：文本（标题 + 目标）运行时从 quest 文件取，
            # 数据文件里不留任何零协译文
            items.append({
                "type": "scene", "branch": bid, "file": q.get("file"), "record": None,
                "page": label, "source": "quest", "quest": q["key"],
            })

        for pi, part in enumerate(br.get("parts") or []):
            rel = str(part.get("file") or "")
            if not rel:
                continue
            role = _part_role(rel, part)
            part_label = part.get("label")
            if part_label:
                # 段内小节标题（例如「◆ 过场·克罗默之姐」「◆ 探索·扶梯厅」）
                items.append({
                    "type": "scene", "branch": bid, "text": f"◆ {part_label}",
                    "file": None, "record": None, "page": label, "source": "plan",
                })
            elif role != "dialogue" and pi > 0:
                items.append({
                    "type": "scene", "branch": bid, "text": _ROLE_MARKERS.get(role, "◇"),
                    "file": None, "record": None, "page": label, "source": "plan",
                })
            data, source = _load_part(rel, llc_dir, supplement_dir, en_dir)
            if data is None:
                warnings.append(f"{label}：找不到文件 {rel}（零协/supplement/英文基线都没有）")
                continue
            if source != "llc":
                warnings.append(f"{label}：{rel} 零协包没有，改用 {source}")
            dl = data.get("dataList")
            if not isinstance(dl, list):
                warnings.append(f"{label}：{rel} 缺少 dataList")
                continue
            lo, hi = _record_range(part, len(dl))
            for ri in range(lo, hi):
                rec = dl[ri]
                if not isinstance(rec, dict):
                    continue
                rkey = rec.get("key")
                for _text, _speaker, _title, tindex, field in _record_lines(rec):
                    # 只记位置：文本（含说话人）运行时从当前语言文件取——
                    # 不随包分发第三方译文，也让同一份数据能配英文基线（没装零协时）。
                    items.append({
                        "type": "line",
                        "branch": bid,
                        "file": rel,
                        "record": ri,
                        "text_index": tindex,
                        "field": field,
                        "key": str(rkey) if rkey is not None else None,
                        "page": label,
                        "source": source,
                    })

    return {"branches": branches, "pages": pages, "items": items, "warnings": warnings}


def _load_part(rel: str, llc_dir: Path, supplement_dir: Path | None, en_dir: Path | None):
    """零协优先 → supplement → 英文基线。返回 (data, source)。"""
    data = _read_json(llc_dir / rel)
    if data is not None:
        return data, "llc"
    if supplement_dir is not None:
        data = _read_json(Path(supplement_dir) / rel)
        if data is not None:
            return data, "supplement"
    if en_dir is not None:
        p = Path(rel)
        data = _read_json(Path(en_dir) / p.parent / f"EN_{p.name}")
        if data is not None:
            return data, "en"
    return None, ""


def _record_range(part: dict, total: int) -> tuple[int, int]:
    """part 的 records: [起, 止]（闭区间，止为 null = 到末尾）→ (lo, hi) 半开区间。"""
    rng = part.get("records")
    if not isinstance(rng, (list, tuple)) or not rng:
        return 0, total
    lo = rng[0] if isinstance(rng[0], int) else 0
    hi_raw = rng[1] if len(rng) > 1 else None
    hi = total if hi_raw is None else int(hi_raw) + 1
    lo = max(0, lo)
    hi = min(total, max(lo, hi))
    return lo, hi


def entry_ref_for_item(item: dict, record: dict | None = None) -> EntryRef:
    """剧本行 → 编辑器条目（EntryRef）。

    - 过场（StoryData）：文本叶子是记录的 ``content``，定位靠 ``record`` 下标 + id；
    - RPG 对话：文本叶子是 ``texts[i].text``（记录没有 KeyID），
      定位靠 ``record`` 下标 + ``text_index``，只认同下标，不做 id 回退；
    - RPG 选项/地点：文本叶子是记录的 ``text``。
    """
    rel = str(item.get("file") or "")
    rec_index = int(item.get("record") or 0)
    tindex = item.get("text_index")
    field = item.get("field")
    rid = record.get("id") if isinstance(record, dict) else None
    if field == "texts" and isinstance(tindex, int):
        field_path = [{"k": "texts"}, {"i": tindex, "h": {"index": tindex}}, {"k": "text"}]
    elif field == "text":
        field_path = [{"k": "text"}]
    else:
        field_path = [{"k": "content"}]
    return EntryRef(file=rel, id=rid, record_index=rec_index, field_path=field_path)


def dump_json_crlf(path: Path, obj: object, indent: int = 2) -> None:
    """按仓库既有风格写 JSON（UTF-8、CRLF、末尾换行）。"""
    text = json.dumps(obj, ensure_ascii=False, indent=indent)
    text = text.replace("\r\n", "\n").replace("\n", "\r\n") + "\r\n"
    Path(path).write_text(text, encoding="utf-8", newline="")
