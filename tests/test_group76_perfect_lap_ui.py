"""Holistic brain — perfect-lap coach rendered through the real Practice panel."""
from __future__ import annotations

import os
import queue
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not available for headless UI test")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402
import config_paths as cp  # noqa: E402

from strategy.lap_corner_extraction import CornerReferencePoints
from strategy.perfect_lap_coach import perfect_lap_report


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


def _corner(brake, apex, throttle):
    return CornerReferencePoints(
        turn_number=1, corner_name="Turn 1", segment_ids=("t1",), frame_count=5,
        braking_point_m=brake, min_speed_kmh=apex, entry_speed_kmh=240,
        exit_speed_kmh=180, entry_gear=5, exit_gear=4, apex_gear=3,
        throttle_on_m=throttle, max_brake=0.9, max_throttle=1.0)


def test_coach_widgets_exist(window):
    assert hasattr(window, "_btn_coach_lap")
    assert hasattr(window, "_coach_ideal_list")
    assert hasattr(window, "_coach_advice_list")


def test_render_coaching_report(window):
    per_lap = [
        [_corner(110, 118, 175)],
        [_corner(112, 119, 178)],
        [_corner(130, 126, 158)],  # best exec
    ]
    report = perfect_lap_report(per_lap)
    window._render_perfect_lap(report)
    assert window._coach_ideal_list.count() >= 1
    assert not window._coach_ideal_list.isHidden()
    assert window._coach_advice_list.count() >= 1
    # An ideal-lap target line mentions the corner + apex.
    ideal_text = window._coach_ideal_list.item(0).text()
    assert "Turn 1" in ideal_text and "apex" in ideal_text


def test_render_empty_report_safe(window):
    window._render_perfect_lap(None)
    assert window._coach_ideal_list.isHidden()
    assert "No coached laps" in window._coach_summary_lbl.text()


def _drain(window, qapp):
    for w in list(window._analysis_workers):
        w.wait(3000)
    qapp.processEvents()


def test_coach_handler_no_db_is_safe(window, qapp):
    # db=None -> _build_perfect_lap_report returns None; handler must not raise.
    window._coach_perfect_lap()
    _drain(window, qapp)
    assert window._coach_ideal_list.isHidden()


def test_coach_runs_off_thread_with_loading_feedback(window, qapp):
    per_lap = [[_corner(110, 118, 175)], [_corner(130, 126, 158)]]
    report = perfect_lap_report(per_lap)
    window._build_perfect_lap_report = lambda: report
    window._coach_perfect_lap()
    # Button shows a busy state immediately while the worker runs.
    assert not window._btn_coach_lap.isEnabled()
    assert window._btn_coach_lap.text() == "Coaching…"
    _drain(window, qapp)
    # Restored + rendered after completion.
    assert window._btn_coach_lap.isEnabled()
    assert window._btn_coach_lap.text() == "Coach My Perfect Lap"
    assert window._coach_ideal_list.count() >= 1
