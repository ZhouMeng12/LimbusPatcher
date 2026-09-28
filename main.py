"""《边狱巴士》汉化文本便携修改器 —— 程序入口。"""
from __future__ import annotations

import faulthandler
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSharedMemory, qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QMessageBox

from limbus_patcher import APP_NAME, __version__
from limbus_patcher.app_state import AppContext
from limbus_patcher.config import AppPaths, ConfigStore
from limbus_patcher.ui import theme
from limbus_patcher.ui.main_window import MainWindow
from limbus_patcher.ui.theme import apply_theme

_SINGLETON_KEY = "limbus_patcher_single_instance_v1"
#: faulthandler 的日志文件句柄必须一直活着，否则原生崩溃时写不出东西
_FAULT_LOG = None


#: 单个日志文件的上限（超了就清空重来，避免 Qt 警告把盘写满）
LOG_MAX_BYTES = 2 * 1024 * 1024


def _append_log(path: Path, title: str, body: str) -> None:
    try:
        if path.exists() and path.stat().st_size > LOG_MAX_BYTES:
            path.unlink()
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now().isoformat()} {title} =====\n{body}")
    except OSError:
        pass


def _install_excepthook(data_dir: Path) -> None:
    log = data_dir / "crash.log"

    def hook(exc_type, exc, tb):
        _append_log(log, "未处理异常", "".join(traceback.format_exception(exc_type, exc, tb)))
        traceback.print_exception(exc_type, exc, tb)
        try:
            from limbus_patcher.ui.dialogs import info as dlg_info, is_headless

            if is_headless():  # 无头/自动化：不弹模态（否则会永久阻塞），仅记日志
                dlg_info(None, "程序错误", f"发生未处理的错误：{exc}")
                return
            QMessageBox.critical(
                None,
                "程序错误",
                f"发生未处理的错误：{exc}\n\n详细信息已写入：\n{log}",
            )
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook

    # 后台线程（索引进度、部署）里的异常默认只打印到没人看得到的 stderr
    def thread_hook(args):
        hook(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = thread_hook

    # __del__ / 回调里吞掉的异常
    def unraisable_hook(args):
        body = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        _append_log(log, "被忽略的异常", f"{args.object!r}\n{body}")

    sys.unraisablehook = unraisable_hook


def _install_native_crash_log(data_dir: Path) -> None:
    """原生崩溃（访问越界 / 栈溢出 / abort）也要留现场。

    打包成 windowed exe 后没有控制台，这类崩溃原本什么都不留下：把 faulthandler 指向
    data/crash_native.log（Python 栈 + 线程），Qt 自己的警告写 data/qt_messages.log。
    """
    global _FAULT_LOG
    try:
        _FAULT_LOG = (data_dir / "crash_native.log").open("a", encoding="utf-8")
        faulthandler.enable(file=_FAULT_LOG, all_threads=True)
    except (OSError, ValueError):
        _FAULT_LOG = None

    qt_log = data_dir / "qt_messages.log"

    def qt_handler(mode, context, message):
        _append_log(qt_log, f"Qt {mode}", f"{message}\n")

    qInstallMessageHandler(qt_handler)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("LimbusPatcher")

    app_paths = AppPaths.from_root()
    app_paths.ensure_dirs()
    _install_excepthook(app_paths.data_dir)
    _install_native_crash_log(app_paths.data_dir)

    # 主题必须在建界面之前生效：控件在构造时读取颜色 token。
    try:
        _start_theme = ConfigStore(app_paths).load().ui.theme
    except Exception:
        _start_theme = theme.DEFAULT_THEME
    apply_theme(app, _start_theme)

    shared = QSharedMemory(_SINGLETON_KEY)
    if not shared.create(1):
        QMessageBox.information(None, APP_NAME, "修改器已在运行。")
        return 0

    ctx = AppContext(app_paths)
    win = MainWindow(ctx)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
