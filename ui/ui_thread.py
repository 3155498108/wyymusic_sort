"""跨线程 UI 调度

后台线程里不能直接操作 Qt 控件，也不能用 QTimer.singleShot（工作线程没有事件循环，
定时器永远不会触发）。正确做法是通过信号把回调排队到 GUI 线程执行。

用法：
    from ui.ui_thread import post
    # 后台线程中
    post(self._show_tracks, tracks)
"""
import functools
import traceback

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication


class _Dispatcher(QObject):
    _invoke = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        # 接收者在 GUI 线程，来自其它线程的 emit 会被 Qt 自动排队到 GUI 线程
        self._invoke.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def _run(self, func):
        try:
            func()
        except Exception:
            traceback.print_exc()


_dispatcher: _Dispatcher | None = None


def _instance() -> _Dispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = _Dispatcher()
        # 若首次调用发生在工作线程，把调度器挪回 GUI 线程，否则排队信号永远没人处理
        app = QApplication.instance()
        if app is not None and _dispatcher.thread() is not app.thread():
            _dispatcher.moveToThread(app.thread())
    return _dispatcher


def init():
    """在 GUI 线程初始化调度器（应用启动时调用一次）"""
    _instance()


def post(func, *args, **kwargs):
    """把 func(*args, **kwargs) 投递到 GUI 线程执行（可从任意线程调用）"""
    if args or kwargs:
        func = functools.partial(func, *args, **kwargs)
    _instance()._invoke.emit(func)
