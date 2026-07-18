"""Live per-lap capture runs OFF the UI thread (worker-thread capture item).

The heavy work at lap completion — per-frame XYZ resolution + DB persist — must
run on a worker thread so lap completion never stutters, with the Practice
Analysis buffers folded in on the main thread afterwards.
"""
from __future__ import annotations

import os
import queue
import threading
import types
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not available for headless UI test")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402
import config_paths as cp  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    cfg = str(tmp_path / "config.json")
    cp.write_default_config(cfg)
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(config=cp.load_config(cfg), logger=MagicMock(),
                     announcer=MagicMock(), bridge=SignalBridge(),
                     ui_queue=queue.Queue(), config_path=cfg, db=None)
    win._query_listener = None
    yield win
    win.close()


def _drain(window, qapp):
    for w in list(window._analysis_workers):
        w.wait(4000)
    qapp.processEvents()


def _episode():
    return types.SimpleNamespace(
        kind="lockup", axle="front", corner_phase="braking", segment_id="t1",
        exclusion_reason="", subtype="", throttle=0.0, brake=0.95,
        duration_s=0.4, max_slip=0.3, confidence=0.5, speed_kmh=120.0, gear=3,
        yaw_rate=0.1)


def test_capture_runs_off_thread_and_folds_buffers(window, qapp, monkeypatch):
    main_ident = threading.get_ident()
    seen = {}
    ep = _episode()

    def fake_extract(frames, drivetrain="", *, config=None, segment_resolver=None):
        seen["thread"] = threading.get_ident()
        return [ep]

    monkeypatch.setattr("telemetry.slip_events.extract_slip_episodes", fake_extract)

    fake_stats = types.SimpleNamespace(lap_num=1, frames=[object(), object()])
    window._recorder = types.SimpleNamespace(
        get_lap=lambda n: fake_stats, last_lap=lambda: fake_stats)
    window._logger.best_lap_ms = lambda: 90000

    window._capture_practice_lap(
        types.SimpleNamespace(lap=1, lap_time_ms=90000, is_valid=True))

    # The heavy work is dispatched to a worker; buffers fill only after drain.
    _drain(window, qapp)

    assert seen.get("thread") is not None, "extractor never ran"
    assert seen["thread"] != main_ident, "capture must not run on the UI thread"
    assert window._practice_lap_episodes.get(1) == [ep]
    assert 1 in window._practice_clean_laps
    assert 1 in window._practice_total_laps


def test_apply_lap_capture_folds_result(window):
    ep = _episode()
    window._apply_lap_capture({
        "lap_num": 3, "episodes": [ep], "is_clean": True,
        "names": {"t1": "Turn 1"}, "disk_names": {"t4": "Turn 4"},
        "track_corners": [("t1", "Turn 1")],
    })
    assert window._practice_lap_episodes[3] == [ep]
    assert 3 in window._practice_clean_laps
    assert window._practice_corner_names["t1"] == "Turn 1"
    assert window._practice_corner_names["t4"] == "Turn 4"
    assert window._practice_track_corners == [("t1", "Turn 1")]

    # None / empty result is safe.
    window._apply_lap_capture(None)


def test_dirty_lap_not_marked_clean(window, qapp, monkeypatch):
    ep = _episode()
    monkeypatch.setattr("telemetry.slip_events.extract_slip_episodes",
                        lambda *a, **k: [ep])
    fake_stats = types.SimpleNamespace(lap_num=2, frames=[object()])
    window._recorder = types.SimpleNamespace(
        get_lap=lambda n: fake_stats, last_lap=lambda: fake_stats)
    window._logger.best_lap_ms = lambda: 90000
    # A lap 30s off the best is an outlier -> captured but not clean.
    window._capture_practice_lap(
        types.SimpleNamespace(lap=2, lap_time_ms=120000, is_valid=True))
    _drain(window, qapp)
    assert 2 in window._practice_total_laps
    assert 2 not in window._practice_clean_laps
