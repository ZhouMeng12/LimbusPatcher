"""对话框：确认 / 异常提示（总是给出下一步）/ 历史 / 备份管理 / 关于。

免模态（无头）模式：环境变量 ``DSH_NO_MODAL=1`` 或 ``LIMBUS_PATCHER_HEADLESS=1``
任一为真（1/true/yes，大小写不敏感）时：

* :func:`info` / :func:`warn` / :func:`error` 不弹窗，直接返回 ``None``；
* :func:`confirm` 不弹窗，直接返回 ``True``（调用方视为用户已确认，便于自动化推进）；
* :class:`HistoryDialog` / :class:`BackupDialog` 的 ``exec()`` / ``exec_safe()`` 立即
  返回 ``0``（reject），不进入 Qt 事件循环。

每次被跳过的调用都会向 ``%TEMP%/limbus_patcher_ui_dialogs.log`` 追加一行日志
（UTF-8、追加模式、写入失败静默）。其它模块可用 :func:`is_headless` 判断当前模式。

其它模块新增对话框调用点时，请优先使用 :meth:`HistoryDialog.exec_safe` /
:meth:`BackupDialog.exec_safe`（或模块级 :func:`safe_exec`）代替裸 ``exec()``。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


# ---- 免模态（无头自动化）开关 -------------------------------------------------

_HEADLESS_ENV_VARS = ("DSH_NO_MODAL", "LIMBUS_PATCHER_HEADLESS")
_TRUTHY_VALUES = {"1", "true", "yes"}
LOG_NAME = "limbus_patcher_ui_dialogs.log"


def is_headless() -> bool:
    """是否处于免模态模式。

    环境变量 ``DSH_NO_MODAL`` / ``LIMBUS_PATCHER_HEADLESS`` 任一取值为
    ``1`` / ``true`` / ``yes``（大小写不敏感）时返回 True，否则 False。
    """
    for name in _HEADLESS_ENV_VARS:
        value = os.environ.get(name)
        if value and value.strip().lower() in _TRUTHY_VALUES:
            return True
    return False


def log_path() -> Path:
    """免模态模式下被跳过对话框的日志路径：``%TEMP%/limbus_patcher_ui_dialogs.log``。"""
    return Path(tempfile.gettempdir()) / LOG_NAME


def _summarize(text, limit: int = 200) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[:limit] + "…"


def _log_skipped(kind: str, title, text="", note="") -> None:
    """追加一行「已跳过对话框」日志（UTF-8、追加模式、失败静默）。"""
    try:
        line = (f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [{kind}] "
                f"{_summarize(title, 80)} | {_summarize(text)}")
        if note:
            line += f" | {_summarize(note, 80)}"
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except (OSError, ValueError):
        pass


def safe_exec(dlg) -> int:
    """免模态安全的 ``exec()`` 包装：优先走 ``dlg.exec_safe()``，避免无头环境永久阻塞。"""
    fn = getattr(dlg, "exec_safe", None)
    if callable(fn):
        return fn()
    if is_headless():
        title = ""
        get_title = getattr(dlg, "windowTitle", None)
        if callable(get_title):
            title = get_title() or ""
        _log_skipped(f"{type(dlg).__name__}.exec", title, "免模态模式：跳过该对话框")
        return 0
    return dlg.exec()


def info(parent, title: str, text: str, next_action: str | None = None) -> None:
    """信息提示。免模态模式下不弹窗、不阻塞，直接返回 None（并写日志）。"""
    if is_headless():
        _log_skipped("info", title, text, f"下一步：{next_action}" if next_action else "")
        return None
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Information)
    msg.setWindowTitle(title)
    msg.setText(text)
    if next_action:
        msg.setInformativeText(f"下一步：{next_action}")
    msg.exec()


def warn(parent, title: str, text: str, next_action: str | None = None) -> None:
    """警告提示。免模态模式下不弹窗、不阻塞，直接返回 None（并写日志）。"""
    if is_headless():
        _log_skipped("warn", title, text, f"下一步：{next_action}" if next_action else "")
        return None
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setWindowTitle(title)
    msg.setText(text)
    if next_action:
        msg.setInformativeText(f"下一步：{next_action}")
    msg.exec()


def error(parent, title: str, text: str, next_action: str | None = None) -> None:
    """错误提示。免模态模式下不弹窗、不阻塞，直接返回 None（并写日志）。"""
    if is_headless():
        _log_skipped("error", title, text, f"下一步：{next_action}" if next_action else "")
        return None
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setWindowTitle(title)
    msg.setText(text)
    if next_action:
        msg.setInformativeText(f"下一步：{next_action}")
    msg.exec()


def confirm(parent, title: str, text: str, ok_label: str = "确定", danger: bool = True) -> bool:
    """确认框。免模态模式下不弹窗、不阻塞，直接返回 True（视为用户已确认）。"""
    if is_headless():
        _log_skipped("confirm", title, text, f"免模态模式：自动确认（{ok_label}）")
        return True
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    yes = box.addButton(ok_label, QMessageBox.ButtonRole.AcceptRole)
    box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is yes


class HistoryDialog(QDialog):
    """修改历史对话框。

    调用方应优先使用 :meth:`exec_safe`（免模态时直接返回 0，不阻塞）；直接调用
    ``exec()`` 在免模态模式下同样会被拦截并立即返回 0。
    """

    restore_selected = None  # 由调用方传入回调

    def __init__(self, parent, ref_key: str, entries: list[dict], current_value: str, on_restore):
        super().__init__(parent)
        self.setWindowTitle("修改历史")
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        hint = QLabel("共保留最近 20 条。双击或点「恢复此版本」可把该版本写回编辑区。")
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        self.list = QListWidget()
        for e in entries:
            new = e.get("new") or ""
            it = QListWidgetItem(f"{e.get('ts', '')}\n{new[:120]}")
            it.setData(Qt.ItemDataRole.UserRole, e.get("new"))
            self.list.addItem(it)
        buttons = QDialogButtonBox()
        restore_btn = QPushButton("恢复此版本")
        close_btn = QPushButton("关闭")
        buttons.addButton(restore_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(hint)
        layout.addWidget(self.list, 1)
        layout.addWidget(buttons)
        self._on_restore = on_restore
        restore_btn.clicked.connect(self._restore)
        close_btn.clicked.connect(self.reject)
        self.list.itemDoubleClicked.connect(lambda _i: self._restore())

    def exec_safe(self) -> int:
        """免模态时直接返回 0（reject），否则等价于 ``exec()``。调用方应优先用它。"""
        if is_headless():
            _log_skipped(f"{type(self).__name__}.exec_safe", self.windowTitle(), "免模态模式：跳过对话框")
            return 0
        return self.exec()

    def exec(self) -> int:
        """免模态模式下不进入事件循环，立即返回 0（reject）。"""
        if is_headless():
            _log_skipped(f"{type(self).__name__}.exec", self.windowTitle(), "免模态模式：跳过对话框")
            return 0
        return super().exec()

    def _restore(self) -> None:
        it = self.list.currentItem()
        if it is not None:
            value = it.data(Qt.ItemDataRole.UserRole)
            self._on_restore(value)
            self.accept()


class BackupDialog(QDialog):
    """备份管理对话框。

    调用方应优先使用 :meth:`exec_safe`（免模态时直接返回 0，不阻塞）；直接调用
    ``exec()`` 在免模态模式下同样会被拦截并立即返回 0。
    """

    def __init__(self, parent, backups, on_restore, data_dir: Path):
        super().__init__(parent)
        self.setWindowTitle("备份管理")
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        hint = QLabel("每次启动与关键写入前自动备份。从备份恢复会替换当前方案与配置。")
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        self.list = QListWidget()
        self._backups = backups
        for b in backups:
            it = QListWidgetItem(f"{b.at}   {b.reason}")
            it.setData(Qt.ItemDataRole.UserRole, b.path)
            it.setToolTip(str(b.path))
            self.list.addItem(it)
        buttons = QDialogButtonBox()
        restore_btn = QPushButton("从选中备份恢复")
        open_btn = QPushButton("打开数据目录")
        close_btn = QPushButton("关闭")
        buttons.addButton(restore_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(open_btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(hint)
        layout.addWidget(self.list, 1)
        layout.addWidget(buttons)
        self._on_restore = on_restore
        self._data_dir = data_dir
        restore_btn.clicked.connect(self._do_restore)
        open_btn.clicked.connect(self._open_data_dir)
        close_btn.clicked.connect(self.reject)

    def exec_safe(self) -> int:
        """免模态时直接返回 0（reject），否则等价于 ``exec()``。调用方应优先用它。"""
        if is_headless():
            _log_skipped(f"{type(self).__name__}.exec_safe", self.windowTitle(), "免模态模式：跳过对话框")
            return 0
        return self.exec()

    def exec(self) -> int:
        """免模态模式下不进入事件循环，立即返回 0（reject）。"""
        if is_headless():
            _log_skipped(f"{type(self).__name__}.exec", self.windowTitle(), "免模态模式：跳过对话框")
            return 0
        return super().exec()

    def _do_restore(self) -> None:
        it = self.list.currentItem()
        if it is None:
            warn(self, "备份管理", "请先选择一个备份。")
            return
        path = Path(it.data(Qt.ItemDataRole.UserRole))
        if confirm(self, "从备份恢复", f"将用备份覆盖当前方案与配置：\n{path.name}\n确定继续吗？"):
            self._on_restore(path)
            self.accept()

    def _open_data_dir(self) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(self._data_dir))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(self._data_dir)])
        except OSError:
            pass


def open_llc_toolbox(parent=None, title: str = "安装零协汉化", english_mode: bool = False) -> None:
    """没装零协时的引导：给出零协工具箱下载地址（可打开 / 可复制）。

    免模态模式下不弹窗、只写日志，保持无头环境不阻塞。
    """
    from ..envcheck import TOOLBOX_URL

    if is_headless():
        _log_skipped("open_llc_toolbox", title, TOOLBOX_URL)
        return None

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setText("需要零协汉化（LLC_zh-CN）作为中文底本" if not english_mode else
                "当前没有零协汉化，已改用游戏自带的英文原文")
    first = ("本次操作要把译文写回游戏，而副本语言包是从零协包镜像出来的，所以必须先装零协汉化。"
             if not english_mode else
             "浏览 / 搜索 / 对照 / 翻译都能正常用（文本取的是英文原文），但「应用到游戏」需要零协汉化。")
    lines = [first, "", f"零协工具箱（一键安装汉化）：\n{TOOLBOX_URL}", "",
             "装好后回到本程序点「重新检测」即可切回中文底本。"]
    box.setInformativeText("\n".join(lines))
    open_btn = box.addButton("打开下载页", QMessageBox.ButtonRole.AcceptRole)
    copy_btn = box.addButton("复制链接", QMessageBox.ButtonRole.ActionRole)
    box.addButton("知道了", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() is open_btn:
        QDesktopServices.openUrl(QUrl(TOOLBOX_URL))
    elif box.clickedButton() is copy_btn:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(TOOLBOX_URL)
    return None
