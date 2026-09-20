"""后台任务：索引进度 / 部署进度，QThreadPool + QRunnable 封装。"""
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class WorkerSignals(QObject):
    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)


class FunctionWorker(QRunnable):
    """在线程池中执行 fn(progress_cb)，结果经信号回主线程。"""

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        def progress(done: int, total: int) -> None:
            try:
                self.signals.progress.emit(done, total)
            except RuntimeError:
                pass  # 主窗口已销毁

        try:
            result = self.fn(progress)
        except Exception as e:  # noqa: BLE001 —— 跨线程边界必须兜底
            try:
                self.signals.failed.emit(str(e))
            except RuntimeError:
                pass
        else:
            try:
                self.signals.done.emit(result)
            except RuntimeError:
                pass


class Runner:
    """简易任务提交器，返回 worker 以便连接信号。"""

    def __init__(self):
        self.pool = QThreadPool.globalInstance()

    def run(self, fn, on_done=None, on_error=None, on_progress=None) -> FunctionWorker:
        w = FunctionWorker(fn)
        if on_done:
            w.signals.done.connect(on_done)
        if on_error:
            w.signals.failed.connect(on_error)
        if on_progress:
            w.signals.progress.connect(on_progress)
        self.pool.start(w)
        return w
