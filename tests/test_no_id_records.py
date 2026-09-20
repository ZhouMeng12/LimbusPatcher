"""无 id 记录的索引 / 编辑 / 应用 / 还原全链路回归。

真实零协包里有 689 条 dataList 记录没有 id 字段（基本都是人格剧情，分布在 27 个文件：
StoryData/P10210.json 70 条、P10211.json 85 条、P10212.json 84 条、P10709.json 73 条……），
合计约 1123 条文本叶子。以前它们被整条丢弃，工具里完全看不到。
本文件用临时目录里的假零协包验证：索引能收录（id 记为 None，靠 record_index 定位）、
能搜到、能读原文、能 upsert 到方案、生成副本包时被正确改写、还原后与零协原包一致。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppPaths
from limbus_patcher.deploy import Deployer, original_text
from limbus_patcher.fsutil import load_json, sha256_file
from limbus_patcher.index import Indexer
from limbus_patcher.patch import EntryRef, Profile, ref_label, record_title
from limbus_patcher.paths import resolve_game_paths
from limbus_patcher.search import SearchEngine

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GAME_FIXTURE = FIXTURES / "game"
LLC_REL = Path("LimbusCompany_Data") / "Lang" / "LLC_zh-CN"
CLONE = "LLC_zh-CN_custom"

# 无 id 记录所在文件（对应真实包里的人格剧情）
STORY_REL = "StoryData/P10210.json"
CONTENT = "李箱合上书，火光在封皮上晃了一下。"
NESTED = "本关卡内，全体罪人的理智值恢复量 +1。"
COIN = "硬币正面命中时，追加 1 点打击伤害。"
CONTENT_NEW = "李箱把书合上，火光在封皮上晃了两下。"
NESTED_NEW = "本关卡内，全体罪人的理智值恢复量 +2。"

# 结构模仿真实人格剧情：根级 place/content + 嵌套 levelList/coinlist，第二条没有 id
NO_ID_FILE = {
    "dataList": [
        {"id": 0, "place": "图书馆 · 三层", "content": "图书馆里安静得能听见翻页声。"},
        {
            "model": "이상",
            "teller": "李箱",
            "content": CONTENT,
            "levelList": [
                {
                    "level": 1,
                    "name": "往昔",
                    "desc": "等级 1 描述",
                    "coinlist": [{"coindescs": [{"desc": "硬币描述 1"}]}],
                },
                {
                    "level": 2,
                    "name": "往昔",
                    "desc": NESTED,
                    "coinlist": [{"coindescs": [{"desc": COIN}]}],
                },
            ],
        },
    ]
}

# fixtures 样本共 34 条叶子；同文件第一条（带 id）贡献 place/content 两条；
# 第二条（无 id）贡献 8 条：teller/content + 2 级 × (name/desc/硬币描述)
FIXTURE_ENTRIES = 34
FILE_ENTRIES = 2
NO_ID_ENTRIES = 8


def write_no_id_file(llc_dir: Path) -> Path:
    """把含「无 id 记录」的剧情文件写进假零协包。"""
    p = llc_dir / STORY_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(NO_ID_FILE, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


@pytest.fixture
def pack(tmp_path) -> Path:
    """假零协包（只做索引/搜索，不需要游戏目录结构）。"""
    d = tmp_path / "pack"
    shutil.copytree(GAME_FIXTURE / LLC_REL, d)
    write_no_id_file(d)
    return d


@pytest.fixture
def game(tmp_path) -> Path:
    """假游戏目录（走真实的 paths/deploy 流程）。"""
    g = tmp_path / "game"
    shutil.copytree(GAME_FIXTURE, g)
    write_no_id_file(g / LLC_REL)
    return g


def content_ref() -> EntryRef:
    return EntryRef(file=STORY_REL, id=None, record_index=1, field_path=[{"k": "content"}])


def nested_ref() -> EntryRef:
    return EntryRef(
        file=STORY_REL,
        id=None,
        record_index=1,
        field_path=[{"k": "levelList"}, {"i": 1, "h": {"level": 2}}, {"k": "desc"}],
    )


def test_index_and_search_without_id(pack, tmp_path):
    """索引收录无 id 记录；可搜索、可读原文；KeyID 搜索不误命中。"""
    idx = Indexer(tmp_path / "index.sqlite", tmp_path / "manifest.json")
    result = idx.build(pack)
    assert result.total_entries == FIXTURE_ENTRIES + FILE_ENTRIES + NO_ID_ENTRIES + 4 == 48
    assert not [w for w in result.warnings if "缺少 id" in w]  # 不再整条丢弃

    eng = SearchEngine(tmp_path / "index.sqlite")

    hits = eng.search(CONTENT)
    assert len(hits) == 1
    hit = hits[0]
    assert hit.file == STORY_REL and hit.category == "identity_story"
    assert hit.ref.id is None and hit.ref.record_index == 1
    assert hit.ref.field_path == [{"k": "content"}]
    # 键唯一、可反序列化，显示键不出现 "None"
    assert EntryRef.from_key(hit.ref_key) == hit.ref
    assert hit.display_key == ref_label(hit.ref) == "记录 #1"

    # 搜索拿到的 ref 能直接读原文
    text, err = original_text(pack, hit.ref)
    assert err is None and text == CONTENT

    # 嵌套叶子（levelList / coinlist）同样可搜到
    hits = eng.search(COIN)
    assert len(hits) == 1 and hits[0].ref.id is None
    assert hits[0].ref.field_path[0]["k"] == "levelList"
    assert json.loads(json.dumps(hits[0].ref.to_dict(), ensure_ascii=False))["id"] is None

    # id_norm 为空串：KeyID 搜索不会退化成匹配字符串 "none"
    assert eng.search("none") == []
    # 有 id 的记录照旧按 KeyID 命中
    assert all(h.ref.id is not None for h in eng.search("2010611"))


def test_deploy_edit_and_restore_without_id(game, tmp_path):
    """编辑无 id 记录 → 方案 → 副本包被正确改写 → 还原后与零协原包逐字节一致。"""
    paths = resolve_game_paths(game)
    llc_file = paths.llc_pack_dir / STORY_REL
    original_hash = sha256_file(llc_file)

    profile = Profile(name="无 id 记录测试")
    assert profile.upsert(content_ref(), CONTENT_NEW, CONTENT) is not None
    assert profile.upsert(nested_ref(), NESTED_NEW, NESTED) is not None
    assert profile.count() == 2

    dep = Deployer(tmp_path / "cache")
    report = dep.enable(paths, CLONE, profile)
    assert report.ok, report.errors
    assert report.files_written == 1
    assert sha256_file(llc_file) == original_hash  # 零协原包只读，一字未动

    clone_file = paths.patch_pack_dir(CLONE) / STORY_REL
    raw = clone_file.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # 与游戏基线一致的 UTF-8 BOM
    data = json.loads(raw.decode("utf-8-sig"))
    assert data["dataList"][1]["content"] == CONTENT_NEW
    assert data["dataList"][1]["levelList"][1]["desc"] == NESTED_NEW
    # 同文件其它记录与其它叶子保持原样
    assert data["dataList"][0]["content"] == "图书馆里安静得能听见翻页声。"
    assert data["dataList"][1]["teller"] == "李箱"
    assert data["dataList"][1]["levelList"][0]["desc"] == "等级 1 描述"
    assert data["dataList"][1]["levelList"][1]["coinlist"][0]["coindescs"][0]["desc"] == COIN
    assert data["dataList"][1]["levelList"][1]["name"] == "往昔"
    # 应用状态
    assert dep.view(paths, CLONE, profile).applied

    # 还原：值 = 原文 → 条目移除，副本包回到与零协完全一致
    assert profile.upsert(content_ref(), CONTENT, CONTENT) is None
    assert profile.upsert(nested_ref(), NESTED, NESTED) is None
    assert profile.count() == 0
    report = dep.sync_clone(paths, CLONE, profile)
    assert report.ok, report.errors
    assert sha256_file(clone_file) == original_hash

    # 停用 → config.json 语言恢复
    dep.disable(paths, CLONE, "LLC_zh-CN")
    cfg, err = load_json(paths.config_path)
    assert err is None and cfg["lang"] == "LLC_zh-CN"


def test_app_context_flow_without_id(game, tmp_path):
    """AppContext 全链路（索引 → 搜索 → 读记录 → upsert → 应用 → 兼容检查 → 还原 → 停用）。"""
    ctx = AppContext(AppPaths.from_root(tmp_path / "app"))
    ctx.set_game_dir(str(game))
    assert ctx.ensure_index() is True

    hits = ctx.search.search(CONTENT)
    assert len(hits) == 1 and hits[0].ref.id is None
    ref = hits[0].ref

    # 编辑器标题：load_record 按 record_index 定位无 id 记录
    record, err = ctx.load_record(ref)
    assert err is None and record is not None and record["content"] == CONTENT
    assert record_title(record, ref) == "李箱"

    # 保存到方案
    assert ctx.upsert_entry(ref, CONTENT_NEW).ok
    ctx.save_profile()
    entry = ctx.profile.get(ref)
    assert entry is not None and entry.ref.id is None and entry.ref.record_index == 1

    # 应用到副本包
    report = ctx.apply()
    assert report.ok, report.errors
    clone_file = ctx.game_paths.patch_pack_dir(ctx.config.patch_pack_name) / STORY_REL
    data, err = load_json(clone_file)
    assert err is None and data["dataList"][1]["content"] == CONTENT_NEW

    # 兼容检查（check_entries 也走 record_index 定位）
    assert ctx.compat_status()[ref.key()] == ("ok", "可继续使用")

    # 还原原文 → 清空副本包 → 与零协一致 → 停用
    assert ctx.upsert_entry(ref, CONTENT).entry is None
    assert ctx.clear_all().ok
    assert sha256_file(clone_file) == sha256_file(ctx.game_paths.llc_pack_dir / STORY_REL)
    ctx.disable()
    cfg, _ = load_json(ctx.game_paths.config_path)
    assert cfg["lang"] == "LLC_zh-CN"

def test_id_less_record_does_not_match_by_wrong_index(tmp_path):
    """无 KeyID 的记录只能按下标定位：下标失真时必须报错，不能改成别的记录。"""
    from limbus_patcher.deploy import _find_record
    from limbus_patcher.patch import EntryRef

    dl = [{"id": None, "content": "第一条无 id"}, {"id": None, "content": "第二条无 id"},
          {"id": 7, "content": "有 id"}]
    ref = EntryRef(file="f.json", id=None, record_index=1, field_path=[{"k": "content"}])
    assert _find_record(dl, ref)["content"] == "第二条无 id"
    stale = EntryRef(file="f.json", id=None, record_index=9, field_path=[{"k": "content"}])
    with pytest.raises(KeyError):
        _find_record(dl, stale)  # 下标越界：不许回退到「第一条无 id 记录」
    # 有 id 的记录仍然可以按 id 回退（下标漂移也能找到）
    moved = EntryRef(file="f.json", id=7, record_index=0, field_path=[{"k": "content"}])
    assert _find_record(dl, moved)["content"] == "有 id"
