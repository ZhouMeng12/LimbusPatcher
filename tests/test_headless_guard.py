"""免模态（无头）开关与剧本数据自检测试。

覆盖：
* ``DSH_NO_MODAL`` / ``LIMBUS_PATCHER_HEADLESS`` 打开后，提示类对话框不弹窗、不阻塞，
  ``confirm`` 自动返回 True，且每次跳过都写日志；
* ``is_headless()`` 的真值判定（1/true/yes，大小写不敏感）；
* ``Storybook.validate()`` 对坏数据报出问题、对真实包数据无问题、缺文件时给出提示。

本文件不创建任何真实对话框（免模态分支在 QMessageBox 构造前就返回）。
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from limbus_patcher import storybook as storybook_mod
from limbus_patcher.storybook import Storybook
from limbus_patcher.ui import dialogs

ENV_VARS = ("DSH_NO_MODAL", "LIMBUS_PATCHER_HEADLESS")


@pytest.fixture
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture(scope="session")
def qapp():
    """整个会话共用一个 QApplication，避免构造/析构顺序问题。"""
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def log_dir(monkeypatch, tmp_path):
    """把 %TEMP% 指向临时目录，避免污染真实临时目录。"""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path / dialogs.LOG_NAME


def write_story_stages(dir_path: Path, payload) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    p = dir_path / "story_stages.json"
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------- 用例 1：免模态

def test_headless_info_warn_error_confirm_do_not_block(clean_env, log_dir):
    clean_env.setenv("DSH_NO_MODAL", "1")
    assert dialogs.is_headless() is True

    assert dialogs.info(None, "提示", "这是一条信息", next_action="继续") is None
    assert dialogs.warn(None, "警告", "这是一条警告") is None
    assert dialogs.error(None, "错误", "这是一条错误") is None
    # 免模态下视为用户已确认（返回 True），便于自动化推进
    assert dialogs.confirm(None, "确认", "是否继续？") is True
    assert dialogs.confirm(None, "删除", "危险操作", ok_label="删除", danger=True) is True

    assert log_dir.is_file(), "免模态跳过的对话框应写入日志"
    text = log_dir.read_text(encoding="utf-8")
    assert "info" in text and "提示" in text and "这是一条信息" in text
    assert "warn" in text and "警告" in text
    assert "error" in text and "错误" in text
    assert "confirm" in text and "是否继续？" in text
    # info/warn/error/confirm/confirm 共 5 次跳过 → 5 行
    assert len(text.strip().splitlines()) == 5


def test_headless_via_limbus_env_var(clean_env, log_dir):
    clean_env.setenv("LIMBUS_PATCHER_HEADLESS", "1")
    assert dialogs.is_headless() is True
    assert dialogs.info(None, "提示", "另一个开关") is None
    assert log_dir.is_file()


def test_history_and_backup_dialog_exec_safe_reject_in_headless(clean_env, log_dir, qapp):
    """两个对话框的 exec_safe()/exec() 在免模态下立即返回 0，不进入事件循环。"""
    clean_env.setenv("DSH_NO_MODAL", "1")
    assert qapp is not None

    hist = dialogs.HistoryDialog(None, "k", [{"ts": "2024", "new": "文本"}], "", lambda _v: None)
    assert hist.exec_safe() == 0
    assert hist.exec() == 0
    assert hist.result() == 0  # Rejected

    backup = dialogs.BackupDialog(None, [], lambda _p: None, Path(tempfile.gettempdir()))
    assert backup.exec_safe() == 0
    assert backup.exec() == 0
    assert dialogs.safe_exec(backup) == 0

    text = log_dir.read_text(encoding="utf-8")
    assert "HistoryDialog.exec_safe" in text and "BackupDialog.exec_safe" in text


# ------------------------------------------------------------ 用例 2：is_headless

@pytest.mark.parametrize("value", ["1", "true", "TRUE", "True", "yes", "YES", "Yes"])
def test_is_headless_truthy(clean_env, value):
    clean_env.setenv("DSH_NO_MODAL", value)
    assert dialogs.is_headless() is True
    clean_env.delenv("DSH_NO_MODAL")
    clean_env.setenv("LIMBUS_PATCHER_HEADLESS", value)
    assert dialogs.is_headless() is True


@pytest.mark.parametrize("value", ["", "0", "2", "false", "no", "off", "on", "tru", "yes please"])
def test_is_headless_falsy(clean_env, value):
    clean_env.setenv("DSH_NO_MODAL", value)
    assert dialogs.is_headless() is False
    clean_env.delenv("DSH_NO_MODAL")
    clean_env.setenv("LIMBUS_PATCHER_HEADLESS", value)
    assert dialogs.is_headless() is False


def test_is_headless_default_false(clean_env):
    assert clean_env is not None
    assert dialogs.is_headless() is False


# ------------------------------------------------------- 用例 3：剧本数据自检测

def test_validate_bad_data_reports_problems(tmp_path, clean_env):
    bad = tmp_path / "bad"
    write_story_stages(bad, {"format_version": 2, "chapters": [
        {"chapter_id": "c1", "chapter_label": "第一章", "stages": [
            {"stage_code": "1-01", "items": [
                {"type": "line", "text": "正常一行", "file": "StoryData/S101.json", "page": "1-01战前"},
                {"type": "narration", "text": "非法类型"},
                {"type": "line", "text": "无文件且未对齐"},
                "不是字典",
            ]},
            {"stage_code": "1-02"},  # 既无 items 也无 pages → 报空数据
        ]},
        {"chapter_label": "缺 chapter_id"},
    ]})
    book = Storybook(overlay_dir=None, data_dir=bad)
    problems = book.validate()
    assert problems, "坏数据必须报出问题"
    joined = "\n".join(problems)
    assert "chapter_id" in joined
    assert "narration" in joined                      # type 非法
    assert "缺少 file 或 wiki_only" in joined          # line 定位信息缺失
    assert "缺少 page/key" in joined                   # 未对齐提示
    assert "不是对象（dict）" in joined
    assert "既无 items 也无 pages" in joined            # v1（只有 pages）视为合法
    assert book.problems == problems                   # 加载后自检结果已存到实例属性

    # chapters 为空列表：加载不会替换 data，但自检仍报问题
    empty = tmp_path / "empty"
    write_story_stages(empty, {"format_version": 2, "chapters": []})
    book2 = Storybook(overlay_dir=None, data_dir=empty)
    assert book2.chapter_list() == []
    assert book2.validate()
    assert any("chapters" in p for p in book2.validate())


def test_reload_updates_problems(tmp_path):
    d = tmp_path / "data"
    write_story_stages(d, {"format_version": 2, "chapters": []})
    book = Storybook(overlay_dir=None, data_dir=d)
    assert book.problems

    write_story_stages(d, {"format_version": 2, "chapters": [
        {"chapter_id": "c1", "chapter_label": "第一章", "stages": [
            {"stage_code": "1-01", "items": [
                {"type": "line", "text": "一行", "file": "StoryData/S101.json",
                 "page": "1-01战前", "key": "战前"},
                {"type": "scene", "text": "场景", "file": "StoryData/S101.json", "page": "1-01战前"},
            ]},
        ]},
    ]})
    book.reload()
    assert book.problems == []
    assert book.validate() == []
    assert [s["stage_code"] for s in book.stages_of("c1")] == ["1-01"]
    assert len(book.stage_items("c1", "1-01")) == 2


def test_missing_data_file_keeps_empty_queries(tmp_path):
    empty = tmp_path / "no_data"
    empty.mkdir()
    book = Storybook(overlay_dir=None, data_dir=empty)
    assert any("未找到剧本数据文件 story_stages.json" in p for p in book.problems)
    assert book.loaded is False
    # 现有行为：其它方法仍返回空列表 / None
    assert book.chapter_list() == []
    assert book.stages_of("c1") == []
    assert book.stage_items("c1", "1-01") == []
    assert book.stage("c1", "1-01") is None
    assert book.file_stages("StoryData/S101.json") == []
    assert book.stage_pages("c1", "1-01") == []
    assert book.stage_records(tmp_path, "c1", "1-01") == []


def test_real_package_data_is_clean(clean_env):
    assert clean_env is not None
    book = Storybook()
    if not book.chapter_list():
        pytest.skip("本环境未加载到真实剧本数据")
    assert book.problems == []
    assert book.validate() == []
    assert book.loaded is True

    # 通过显式 data_dir 指向包内数据文件，同样应无问题
    book2 = Storybook(overlay_dir=None, data_dir=storybook_mod.package_data_dir())
    if book2.chapter_list():
        assert book2.validate() == []


# ---------- 崩溃现场日志（原生崩溃 / Qt 消息也留痕） ----------


def _load_main_module():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("_main_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_excepthook_writes_crash_log(tmp_path):
    """未处理异常 / 线程异常 / 被忽略异常都要落进 data/crash.log。"""
    import sys as _sys
    import threading

    mod = _load_main_module()
    data = tmp_path / "data"
    data.mkdir()
    saved = (_sys.excepthook, threading.excepthook, _sys.unraisablehook)
    try:
        mod._install_excepthook(data)
        try:
            raise ValueError("测试异常")
        except ValueError:
            _sys.excepthook(*_sys.exc_info())
    finally:
        _sys.excepthook, threading.excepthook, _sys.unraisablehook = saved
    text = (data / "crash.log").read_text(encoding="utf-8")
    assert "未处理异常" in text and "测试异常" in text


def test_native_crash_log_installed(tmp_path):
    """faulthandler 指向 data/crash_native.log（打包后没有控制台，原生崩溃靠它留现场）。"""
    mod = _load_main_module()
    data = tmp_path / "data"
    data.mkdir()
    mod._install_native_crash_log(data)
    assert (data / "crash_native.log").exists()
    assert mod._FAULT_LOG is not None and not mod._FAULT_LOG.closed


def test_qt_messages_go_to_log(tmp_path):
    from PySide6.QtCore import qInstallMessageHandler, qWarning

    mod = _load_main_module()
    data = tmp_path / "data"
    data.mkdir()
    mod._install_native_crash_log(data)
    try:
        qWarning("冒烟：Qt 警告应写进 qt_messages.log")
    finally:
        qInstallMessageHandler(None)
    assert "冒烟" in (data / "qt_messages.log").read_text(encoding="utf-8")
