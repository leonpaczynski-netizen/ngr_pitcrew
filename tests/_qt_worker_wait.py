"""Deterministic off-thread worker waiting for Qt UI tests (Audit D — shared QApplication.exec fix).

The historical UI off-thread tests drove the ONE shared ``QApplication`` event loop with
``app.exec()`` + ``QTimer.singleShot(..., app.quit)``. Running many such tests in a single process
corrupted the shared loop: a prior test's queued ``quit`` made a later ``app.exec()`` return before
the worker ran, so the build never executed and the assertion failed intermittently (the "10 combined
UI failures" artifact). Each test passed in isolation.

``drive_worker`` removes the nested/repeated application ``exec()`` entirely. It starts the
``QThread`` worker, joins it with ``QThread.wait`` (deterministic — no event loop), then drains the
queued cross-thread ``finished_ok`` / ``failed`` signal to the main thread via ``processEvents`` so the
connected slots run on the main thread exactly as they do in production. This is a TEST-ONLY change:
the production worker, its signals, the off-thread guarantee and the stale-worker guard are untouched.

Purity: no product import; deterministic; never raises on timeout (returns whether the worker joined).
"""
from __future__ import annotations


def drive_worker(worker, timeout_ms: int = 5000) -> bool:
    """Start ``worker`` (a QThread with finished_ok/failed signals), wait for it deterministically
    without a nested application ``exec()``, then deliver its queued signal(s) on the main thread.
    Returns True if the worker thread finished within ``timeout_ms``."""
    from PyQt6.QtWidgets import QApplication

    worker.start()
    finished = worker.wait(int(timeout_ms))   # join the worker thread; no event loop involved
    # deliver the queued cross-thread signal(s) to the main thread so connected slots run there,
    # exactly as they would under a live event loop — but without touching the shared app loop.
    for _ in range(8):
        QApplication.processEvents()
    return bool(finished)
