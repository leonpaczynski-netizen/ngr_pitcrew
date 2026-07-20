"""UAT Finding 2 — Practice Analysis VM + observation builder + structured UI.

The engine itself is covered by test_group75_practice_analysis.py. Here we test:
  * the pure VM renders the 7 structured sections (not one text box);
  * the observation builder maps slip episodes (carrying exclusions) correctly;
  * the real Practice Review tab renders a report into tables/lists.
"""
from __future__ import annotations

import os
import queue
from unittest.mock import MagicMock

import pytest

from strategy.practice_pattern_analysis import (
    analyze_practice, EpisodeObservation,
)
from strategy.practice_observation_builder import build_observations
from ui import practice_analysis_vm as pav


def _obs(lap, seg, name, phase, issue, **kw):
    return EpisodeObservation(lap_number=lap, is_clean=True, segment_id=seg,
                              corner_name=name, phase=phase, issue_type=issue, **kw)


def _report():
    observations = [
        _obs(l, "t1", "Turn 1", "braking", "front_lock", brake=0.95)
        for l in (1, 2, 3, 4)
    ]
    return analyze_practice(
        observations, clean_lap_numbers=[1, 2, 3, 4, 5],
        total_lap_numbers=[1, 2, 3, 4, 5],
        track_corners=[("t1", "Turn 1"), ("t6", "Turn 6")],
        driver_feedback={"notes": "front keeps locking into turn 1"})


# --------------------------------------------------------------------------- #
# VM
# --------------------------------------------------------------------------- #

def test_vm_sections_structured():
    r = _report()
    summary = pav.session_summary_rows(r)
    assert ("Clean laps analysed", "5") in summary

    cols = pav.CORNER_TABLE_COLUMNS
    rows = pav.corner_table_rows(r)
    assert rows and len(rows[0]) == len(cols)
    # T1 row: strongly recurring, authorable.
    t1 = rows[0]
    assert t1[0] == "Turn 1"
    assert t1[cols.index("Author?")] == "Yes"
    assert t1[cols.index("Pattern")] == "Strongly recurring"

    assert any("Turn 1" in l for l in pav.repeatable_lines(r))
    assert any("Turn 6" in l for l in pav.strong_lines(r))
    assert any("agrees" in l.lower() for l in pav.feedback_lines(r))
    assert pav.targeted_test_lines(r)
    assert pav.empty_state(r) == ""


def test_vm_empty_state_no_clean_laps():
    r = analyze_practice([], clean_lap_numbers=[], total_lap_numbers=[1, 2])
    assert "clean laps" in pav.empty_state(r).lower()


# --------------------------------------------------------------------------- #
# Observation builder
# --------------------------------------------------------------------------- #

class _Ep:
    def __init__(self, kind, axle, phase, seg, reason="", throttle=0.9, max_slip=0.3):
        self.kind = kind
        self.axle = axle
        self.corner_phase = phase
        self.segment_id = seg
        self.exclusion_reason = reason
        self.throttle = throttle
        self.brake = 0.0
        self.duration_s = 0.4
        self.max_slip = max_slip
        self.yaw_rate = 0.1


def test_builder_maps_issue_and_exclusion():
    lap_eps = {
        1: [_Ep("lockup", "front", "braking", "t1")],
        2: [_Ep("wheelspin", "rear", "exit", "t4")],
        3: [_Ep("wheelspin", "rear", "exit", "t10", reason="kerb strike")],
    }
    obs = build_observations(lap_eps, clean_lap_numbers=[1, 2, 3],
                             corner_names={"t1": "Turn 1", "t4": "Turn 4"})
    by_seg = {o.segment_id: o for o in obs}
    assert by_seg["t1"].issue_type == "front_lock"
    assert by_seg["t1"].corner_name == "Turn 1"
    assert by_seg["t4"].issue_type == "rear_wheelspin"
    assert by_seg["t10"].excluded and "kerb" in by_seg["t10"].exclusion_reason

    # Feed through the engine: kerb episode must not be authorable.
    report = analyze_practice(obs, clean_lap_numbers=[1, 2, 3],
                              total_lap_numbers=[1, 2, 3])
    t10 = next(f for f in report.findings if f.segment_id == "t10")
    assert not t10.setup_authoring_eligible


# --------------------------------------------------------------------------- #
# Structured UI rendering through the real tab
# --------------------------------------------------------------------------- #

def test_ui_renders_report_into_tables():
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    import config_paths as cp

    app = QApplication.instance() or QApplication([])
    import tempfile
    import pathlib
    d = pathlib.Path(tempfile.mkdtemp())
    cfg = str(d / "config.json")
    cp.write_default_config(cfg)
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(config=cp.load_config(cfg), logger=MagicMock(),
                     announcer=MagicMock(), bridge=SignalBridge(),
                     ui_queue=queue.Queue(), config_path=cfg, db=None)
    win._query_listener = None
    try:
        # The structured widgets exist (not a single text box).
        assert hasattr(win, "_pa_table") and hasattr(win, "_pa_repeat_list")
        win._render_practice_analysis(_report())
        # Per-corner table populated + explicitly un-hidden (isVisible() needs a
        # shown window; isHidden() reflects the widget's own visibility flag).
        assert win._pa_table.rowCount() >= 1
        assert not win._pa_table.isHidden()
        # Repeatable + strong + targeted-tests lists populated & shown.
        assert win._pa_repeat_list.count() >= 1
        assert not win._pa_repeat_list.isHidden()
        assert win._pa_strong_list.count() >= 1
        assert win._pa_tests_list.count() >= 1
        # Empty-state hidden when there's content.
        assert win._pa_empty_lbl.isHidden()
    finally:
        win.close()
