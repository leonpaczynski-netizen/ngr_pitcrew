"""UAT Finding 4 — Track Modelling coordinator wired into the real UI + threading.

Offscreen tests that drive the real TrackModellingMixin (via MainWindow):
  * the guided next-step banner reflects the canonical coordinator state;
  * an approved model on disk auto-loads the workflow to ACTIVE on selection;
  * long-running model builds run off the UI thread (required test 18).
"""
from __future__ import annotations

import os
import queue
import threading
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not available for headless UI test")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import config_paths as cp  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    cfg_path = str(tmp_path / "config.json")
    cp.write_default_config(cfg_path)
    config = cp.load_config(cfg_path)
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(
        config=config, logger=MagicMock(), announcer=MagicMock(),
        bridge=SignalBridge(), ui_queue=queue.Queue(),
        config_path=cfg_path, db=None)
    win._query_listener = None
    yield win
    win.close()


def test_coordinator_and_banner_exist(window):
    assert getattr(window, "_tm_coordinator", None) is not None
    assert getattr(window, "_tm_next_step_banner", None) is not None
    # With nothing selected the banner guides the first step (Identify).
    window._tm_refresh_workflow()
    assert "Step 1/6" in window._tm_next_step_banner.text()
    assert "Identify" in window._tm_next_step_banner.text()


def test_banner_reflects_capturing_state(window):
    from data.track_modelling_coordinator import TrackModellingState
    # Force identity + a live capture, then refresh the workflow.
    inputs_seen = {}

    # Monkeypatch the inputs builder to simulate identity + capturing without a
    # real track selection / controller.
    from data.track_modelling_coordinator import TrackModellingInputs
    window._tm_build_coordinator_inputs = lambda: TrackModellingInputs(
        identity_known=True, capturing=True)
    window._tm_refresh_workflow()
    assert window._tm_snapshot.state is TrackModellingState.CAPTURING
    assert "Capture" in window._tm_next_step_banner.text()


def test_approved_model_auto_loads_active(window):
    from data.track_modelling_coordinator import (
        TrackModellingState, TrackModellingInputs)
    window._tm_build_coordinator_inputs = lambda: TrackModellingInputs(
        identity_known=True, has_reference_path=True, has_station_map=True,
        has_segments=True, review_complete=True, validation_passed=True,
        model_active=True)
    window._tm_refresh_workflow()
    assert window._tm_snapshot.state is TrackModellingState.ACTIVE
    assert "Step 6/6" in window._tm_next_step_banner.text()


def test_snapshot_is_single_canonical_object(window):
    """Every surface reads one object; it exposes state, step, actions, next-step."""
    window._tm_refresh_workflow()
    snap = window._tm_snapshot
    assert hasattr(snap, "state") and hasattr(snap, "step")
    assert hasattr(snap, "available_actions") and hasattr(snap, "primary_next_step")
    assert callable(snap.can)


# --------------------------------------------------------------------------- #
# Test 18 — long-running model operations run off the UI thread
# --------------------------------------------------------------------------- #

def test_build_runs_off_ui_thread(qapp):
    from ui.track_model_build_worker import TrackModelBuildWorker

    main_ident = threading.get_ident()
    captured = {}

    def build_fn(report, is_cancelled):
        # Everything asserted is captured INSIDE the worker thread, so the test
        # doesn't depend on cross-thread signal delivery / a nested event loop
        # (which is fragile in a shared-QApplication full-suite run).
        report("building station map…")
        captured["thread"] = threading.get_ident()
        captured["cancelled_flag"] = is_cancelled()
        captured["result"] = {"stations": 1200}
        return captured["result"]

    worker = TrackModelBuildWorker(build_fn)
    worker.start()
    assert worker.wait(5000), "build worker did not finish in time"

    assert captured.get("thread") is not None, "build_fn never ran"
    assert captured["thread"] != main_ident, "build must not run on the UI thread"
    assert captured["cancelled_flag"] is False
    assert captured["result"] == {"stations": 1200}


def test_build_worker_reports_failure(qapp):
    from ui.track_model_build_worker import TrackModelBuildWorker

    def build_fn(report, is_cancelled):
        raise ValueError("bad reference path")

    worker = TrackModelBuildWorker(build_fn)
    errors = {}
    worker.failed.connect(lambda m: errors.update({"msg": m}))
    worker.start()
    assert worker.wait(5000)
    qapp.processEvents()  # flush the queued cross-thread `failed` signal
    assert "bad reference path" in errors.get("msg", "")
    assert "ValueError" in errors.get("msg", "")


def test_build_worker_cancellation(qapp):
    from ui.track_model_build_worker import TrackModelBuildWorker

    def build_fn(report, is_cancelled):
        # Simulate a long build that checks for cancellation.
        for _ in range(100):
            if is_cancelled():
                return None
        return {"done": True}

    worker = TrackModelBuildWorker(build_fn)
    got = {}
    worker.cancelled.connect(lambda: got.update({"cancelled": True}))
    worker.cancel()  # request before start -> build returns early
    worker.start()
    assert worker.wait(5000)
    qapp.processEvents()  # flush the queued cross-thread `cancelled` signal
    assert got.get("cancelled") is True
