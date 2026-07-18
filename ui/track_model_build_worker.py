"""Background worker for long-running Track Modelling builds (UAT Finding 4).

Model building (reference path → station map → segment detection) used to run
synchronously inside Qt button-click slots on the main thread, freezing the UI
with no progress or cancellation. This QThread wrapper runs any build callable
off the UI thread and reports progress / completion / failure via signals, and
supports cooperative cancellation.

The build callable receives a ``report`` callback (``report(message: str)``) and
a ``is_cancelled`` callback (``() -> bool``) so it can emit progress and stop
early. It must be self-contained (no direct Qt widget access) — it runs on the
worker thread; the UI updates from the signal handlers on the main thread.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal


class TrackModelBuildWorker(QThread):
    progress = pyqtSignal(str)       # human-readable progress line
    finished_ok = pyqtSignal(object)  # the build result
    failed = pyqtSignal(str)          # structured failure message
    cancelled = pyqtSignal()

    def __init__(self, build_fn: Callable, parent=None):
        super().__init__(parent)
        self._build_fn = build_fn
        self._cancel = False

    def cancel(self) -> None:
        """Request cooperative cancellation; the build callable should check
        ``is_cancelled`` and stop at the next safe point."""
        self._cancel = True

    def is_cancelled(self) -> bool:
        return self._cancel

    def run(self) -> None:  # executes on the worker thread
        try:
            result = self._build_fn(self._report, self.is_cancelled)
            if self._cancel:
                self.cancelled.emit()
                return
            self.finished_ok.emit(result)
        except Exception as exc:  # structured failure, never a silent hang
            self.failed.emit(f"{type(exc).__name__}: {exc}")

    def _report(self, message: str) -> None:
        self.progress.emit(str(message))
