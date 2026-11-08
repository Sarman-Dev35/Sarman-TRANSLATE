from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Slot


class ThreadFinishRelay(QObject):
    """Deliver a per-run completion token safely to the GUI object's thread.

    QThread.finished has no payload. A dedicated QObject receiver preserves the
    generation belonging to that specific worker, so a late finish event from
    an older scan cannot clear a newer worker reference.
    """

    def __init__(self, callback: Callable[[int], None], generation: int, parent=None):
        super().__init__(parent)
        self._callback = callback
        self._generation = int(generation)

    @Slot()
    def dispatch(self) -> None:
        callback = self._callback
        self._callback = None
        try:
            if callback is not None:
                callback(self._generation)
        finally:
            self.deleteLater()


def thread_is_running(worker) -> bool:
    """Check a QThread safely when Qt may already have deleted its C++ object."""
    if worker is None:
        return False
    try:
        return bool(worker.isRunning())
    except (AttributeError, RuntimeError):
        return False
