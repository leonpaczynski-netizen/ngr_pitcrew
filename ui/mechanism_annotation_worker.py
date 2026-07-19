"""Background worker for the Phase-13 mechanism annotation build (off the Qt thread).

``SessionDB.build_mechanism_annotations`` reads the immutable Phase-8 / Phase-11 records
and composes the Phase-12 knowledge into an immutable annotation report. That work is kept
OFF the Qt UI thread here: the worker runs a self-contained build callable and delivers the
finished, immutable dict back to the UI via a signal. The UI only ever renders the completed
result — it performs no annotation work itself and mutates nothing.

Mirrors ``ui.track_model_build_worker.TrackModelBuildWorker`` (the established pattern).
The build callable must be self-contained (no Qt widget access) — it runs on the worker
thread; the UI updates from the signal handler on the main thread.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal


class MechanismAnnotationWorker(QThread):
    finished_ok = pyqtSignal(object)   # the immutable annotation report dict
    failed = pyqtSignal(str)           # structured failure message

    def __init__(self, build_fn: Callable[[], dict], parent=None):
        super().__init__(parent)
        self._build_fn = build_fn

    def run(self) -> None:  # executes on the worker thread
        try:
            result = self._build_fn()
            self.finished_ok.emit(result)
        except Exception as exc:  # structured failure, never a silent hang
            self.failed.emit(f"{type(exc).__name__}: {exc}")
