"""OFR-1 Between-Race Learning Loop — UI trigger wiring tests.

Two categories, following the house pattern from test_legacy_fanout_phase_4/5.py:

1. Source-scan tests: assert the method bodies contain the expected fragments
   (or do NOT contain forbidden ones) without importing PyQt6 or constructing
   MainWindow.

2. Behavioural stub test: bind the REAL _trigger_scoring_pass to a minimal
   stub (types.MethodType + MagicMock, matching the _make_fanout_stub pattern
   from test_legacy_fanout_phase_4.py) and exercise the happy path, the
   same-session skip, and the no-db guard.
"""
from __future__ import annotations

import re
import types
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Source helpers (mirror test_legacy_fanout_phase_5._method_body)
# ---------------------------------------------------------------------------

def _method_body(src: str, name: str) -> str:
    m = re.search(
        rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
        src, re.DOTALL,
    )
    assert m, f"method {name!r} not found in source"
    return m.group(0)


@pytest.fixture(scope="module")
def dash_src() -> str:
    return (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8") + (ROOT / "ui" / "live_ui.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Source-scan: _trigger_scoring_pass body contracts
# ---------------------------------------------------------------------------

class TestTriggerScoringPassBody:
    def test_method_exists(self, dash_src):
        body = _method_body(dash_src, "_trigger_scoring_pass")
        assert body

    def test_calls_get_previous_session_id(self, dash_src):
        body = _method_body(dash_src, "_trigger_scoring_pass")
        assert "get_previous_session_id" in body

    def test_calls_get_applied_unverified_recs(self, dash_src):
        body = _method_body(dash_src, "_trigger_scoring_pass")
        assert "get_applied_unverified_recs" in body

    def test_calls_aggregate_lap_window(self, dash_src):
        body = _method_body(dash_src, "_trigger_scoring_pass")
        assert "aggregate_lap_window" in body

    def test_calls_compute_verdict_and_confidence(self, dash_src):
        body = _method_body(dash_src, "_trigger_scoring_pass")
        assert "compute_verdict_and_confidence" in body

    def test_calls_persist_score(self, dash_src):
        body = _method_body(dash_src, "_trigger_scoring_pass")
        assert "persist_score" in body

    def test_no_config_strategy_read(self, dash_src):
        body = _method_body(dash_src, "_trigger_scoring_pass")
        assert 'config.get("strategy"' not in body, (
            "_trigger_scoring_pass must never read config['strategy']")

    def test_no_outcome_session_id(self, dash_src):
        body = _method_body(dash_src, "_trigger_scoring_pass")
        assert "outcome_session_id" not in body, (
            "outcome_session_id is never populated — use get_previous_session_id")

    def test_fully_try_wrapped(self, dash_src):
        body = _method_body(dash_src, "_trigger_scoring_pass")
        assert "except Exception" in body, (
            "_trigger_scoring_pass must be fully wrapped in try/except "
            "so it can never raise")

    def test_calls_get_recent_feedback(self, dash_src):
        """I1: the feedback query must be wired — get_recent_feedback appears in body."""
        body = _method_body(dash_src, "_trigger_scoring_pass")
        assert "get_recent_feedback" in body, (
            "_trigger_scoring_pass must call get_recent_feedback to populate "
            "has_driver_feedback")

    def test_no_hardcoded_has_driver_feedback_false(self, dash_src):
        """I1: has_driver_feedback=False must no longer be hardcoded."""
        body = _method_body(dash_src, "_trigger_scoring_pass")
        assert "has_driver_feedback=False" not in body, (
            "has_driver_feedback must be wired from get_recent_feedback, "
            "not hardcoded to False")


# ---------------------------------------------------------------------------
# 2. Source-scan: call sites wired correctly
# ---------------------------------------------------------------------------

class TestCallSiteWiring:
    def test_call_in_on_live_mode_changed(self, dash_src):
        body = _method_body(dash_src, "_on_live_mode_changed")
        assert "self._trigger_scoring_pass(" in body

    def test_call_after_open_session_in_live_mode(self, dash_src):
        body = _method_body(dash_src, "_on_live_mode_changed")
        open_idx = body.index("open_session")
        trigger_idx = body.index("self._trigger_scoring_pass(")
        assert trigger_idx > open_idx, (
            "_trigger_scoring_pass must come AFTER open_session in "
            "_on_live_mode_changed")

    def test_call_in_save_session_to_db(self, dash_src):
        body = _method_body(dash_src, "_save_session_to_db")
        assert "self._trigger_scoring_pass(" in body

    def test_call_after_open_session_in_save_session(self, dash_src):
        body = _method_body(dash_src, "_save_session_to_db")
        open_idx = body.index("open_session")
        trigger_idx = body.index("self._trigger_scoring_pass(")
        assert trigger_idx > open_idx, (
            "_trigger_scoring_pass must come AFTER open_session in "
            "_save_session_to_db")


# ---------------------------------------------------------------------------
# 3. Source-scan: _build_home_dashboard_state passes learning_saved
# ---------------------------------------------------------------------------

class TestHomeDashboardLearningGate:
    def test_has_learning_for_car_track_called(self, dash_src):
        body = _method_body(dash_src, "_build_home_dashboard_state")
        assert "has_learning_for_car_track" in body

    def test_passes_learning_saved_kwarg(self, dash_src):
        body = _method_body(dash_src, "_build_home_dashboard_state")
        assert "learning_saved=" in body


# ---------------------------------------------------------------------------
# 4. Behavioural stub test
# ---------------------------------------------------------------------------

def _make_scoring_stub():
    """Build a minimal stub with the REAL _trigger_scoring_pass bound to it.

    Follows the _make_fanout_stub pattern from test_legacy_fanout_phase_4.py:
    MagicMock shell, real config dict, then bind the method with types.MethodType.
    No QApplication or MainWindow construction required.
    """
    from ui import dashboard as _dash_mod

    stub = MagicMock()
    stub._db = MagicMock()
    stub._home_refresh_if_visible = MagicMock()
    stub._trigger_scoring_pass = types.MethodType(
        _dash_mod.MainWindow._trigger_scoring_pass, stub
    )
    return stub


def _make_clean_lap(lap_time_ms: int = 89000) -> dict:
    return {
        "lap_time_ms": lap_time_ms,
        "is_pit_lap": 0,
        "is_out_lap": 0,
        "compound": "RM",
        "lock_up_count": 1,
        "wheelspin_count": 1,
        "oversteer_count": 0,
        "oversteer_throttle_on": 0,
        "bottoming_count": 0,
        "brake_consistency_m": 2.0,
    }


def _make_rec(rec_id: int = 1, session_id: int = 3) -> dict:
    import json
    return {
        "id": rec_id,
        "session_id": session_id,
        "recommendation_text": json.dumps({
            "changes": [
                {"field": "arb_front", "from": "5", "to": "3",
                 "why": "reduce understeer"},
            ]
        }),
        "before_metrics": json.dumps({
            "best_lap_ms": 90000,
            "avg_fuel_per_lap": 2.0,
            "lap_count": 8,
        }),
    }


class TestTriggerScoringPassBehaviour:

    def test_happy_path_persist_score_called(self):
        """Full happy path: one scoreable rec → persist_score called once."""
        stub = _make_scoring_stub()
        after_laps = [_make_clean_lap() for _ in range(8)]
        before_laps = [_make_clean_lap(90000) for _ in range(8)]
        rec = _make_rec(rec_id=1, session_id=3)

        stub._db.get_previous_session_id.return_value = 7
        stub._db.get_applied_unverified_recs.return_value = [rec]
        stub._db.get_laps_for_scoring.side_effect = [after_laps, before_laps]
        stub._db.persist_score.return_value = True

        stub._trigger_scoring_pass(42, "Fuji Speedway", "fuji_gp", 99)

        stub._db.persist_score.assert_called_once()
        args = stub._db.persist_score.call_args
        # First positional arg is rec_id
        assert args[0][0] == 1
        # Second positional arg is verdict string
        verdict = args[0][1]
        assert isinstance(verdict, str) and verdict  # non-empty string

    def test_rec_with_same_session_as_after_sid_is_skipped(self):
        """A rec whose session_id matches the after_sid must be skipped."""
        stub = _make_scoring_stub()
        # after_sid = 7; rec was created in session 7 → should be skipped
        rec = _make_rec(rec_id=2, session_id=7)

        stub._db.get_previous_session_id.return_value = 7
        stub._db.get_applied_unverified_recs.return_value = [rec]
        # get_laps_for_scoring should NOT be called (no scoreable recs)

        stub._trigger_scoring_pass(42, "Fuji Speedway", "fuji_gp", 99)

        stub._db.persist_score.assert_not_called()

    def test_no_db_guard_never_raises(self):
        """When _db is None the method must return immediately without raising."""
        stub = _make_scoring_stub()
        stub._db = None

        # Must not raise
        stub._trigger_scoring_pass(42, "Fuji Speedway", "fuji_gp", 99)

        # No db calls possible; _home_refresh_if_visible not called either
        stub._home_refresh_if_visible.assert_not_called()

    def test_zero_car_id_returns_early(self):
        """car_id <= 0 → return immediately (guard check)."""
        stub = _make_scoring_stub()
        stub._trigger_scoring_pass(0, "Fuji Speedway", "fuji_gp", 99)
        stub._db.get_previous_session_id.assert_not_called()

    def test_empty_track_returns_early(self):
        """Empty track string → return immediately (guard check)."""
        stub = _make_scoring_stub()
        stub._trigger_scoring_pass(42, "", "fuji_gp", 99)
        stub._db.get_previous_session_id.assert_not_called()

    def test_no_previous_session_returns_early(self):
        """get_previous_session_id returns 0 → no further DB calls."""
        stub = _make_scoring_stub()
        stub._db.get_previous_session_id.return_value = 0
        stub._trigger_scoring_pass(42, "Fuji Speedway", "fuji_gp", 99)
        stub._db.get_applied_unverified_recs.assert_not_called()

    def test_home_refresh_called_when_non_trivial_verdict_written(self):
        """When ≥1 non-insufficient_data verdict is persisted, home refreshes."""
        from data.recommendation_scoring import ScoringResult
        stub = _make_scoring_stub()

        after_laps = [_make_clean_lap() for _ in range(8)]
        before_laps = [_make_clean_lap(92000) for _ in range(8)]
        rec = _make_rec(rec_id=5, session_id=3)

        stub._db.get_previous_session_id.return_value = 7
        stub._db.get_applied_unverified_recs.return_value = [rec]
        stub._db.get_laps_for_scoring.side_effect = [after_laps, before_laps]
        stub._db.persist_score.return_value = True
        stub._db.get_recent_feedback.return_value = []

        stub._trigger_scoring_pass(42, "Fuji Speedway", "fuji_gp", 99)

        # persist_score was called and verdict was not insufficient_data,
        # so _home_refresh_if_visible must have been called.
        stub._db.persist_score.assert_called_once()
        verdict = stub._db.persist_score.call_args[0][1]
        if verdict != "insufficient_data":
            stub._home_refresh_if_visible.assert_called_once()

    def test_feedback_true_when_rows_exist(self):
        """I1: when get_recent_feedback returns rows, has_driver_feedback=True flows through."""
        from unittest.mock import patch, call as mock_call
        stub = _make_scoring_stub()

        after_laps = [_make_clean_lap() for _ in range(8)]
        before_laps = [_make_clean_lap(92000) for _ in range(8)]
        rec = _make_rec(rec_id=10, session_id=3)

        stub._db.get_previous_session_id.return_value = 7
        stub._db.get_applied_unverified_recs.return_value = [rec]
        stub._db.get_laps_for_scoring.side_effect = [after_laps, before_laps]
        stub._db.persist_score.return_value = True
        # Simulate feedback rows present
        stub._db.get_recent_feedback.return_value = [{"notes": "oversteery"}]

        captured = {}
        original_compute = None

        import data.recommendation_scoring as _rs
        original_compute = _rs.compute_verdict_and_confidence

        def _spy_compute(rec, before_w, after_w, **kwargs):
            captured["has_driver_feedback"] = kwargs.get("has_driver_feedback")
            return original_compute(rec, before_w, after_w, **kwargs)

        with patch.object(_rs, "compute_verdict_and_confidence", side_effect=_spy_compute):
            stub._trigger_scoring_pass(42, "Fuji Speedway", "fuji_gp", 99)

        assert captured.get("has_driver_feedback") is True, (
            "has_driver_feedback must be True when feedback rows are present")
        # Also verify get_recent_feedback was called with the correct car+track
        stub._db.get_recent_feedback.assert_called_once_with(42, "Fuji Speedway")

    def test_feedback_false_when_no_rows(self):
        """I1: when get_recent_feedback returns empty list, has_driver_feedback=False."""
        import data.recommendation_scoring as _rs
        from unittest.mock import patch

        stub = _make_scoring_stub()

        after_laps = [_make_clean_lap() for _ in range(8)]
        before_laps = [_make_clean_lap(92000) for _ in range(8)]
        rec = _make_rec(rec_id=11, session_id=3)

        stub._db.get_previous_session_id.return_value = 7
        stub._db.get_applied_unverified_recs.return_value = [rec]
        stub._db.get_laps_for_scoring.side_effect = [after_laps, before_laps]
        stub._db.persist_score.return_value = True
        stub._db.get_recent_feedback.return_value = []

        captured = {}
        original_compute = _rs.compute_verdict_and_confidence

        def _spy_compute(rec, before_w, after_w, **kwargs):
            captured["has_driver_feedback"] = kwargs.get("has_driver_feedback")
            return original_compute(rec, before_w, after_w, **kwargs)

        with patch.object(_rs, "compute_verdict_and_confidence", side_effect=_spy_compute):
            stub._trigger_scoring_pass(42, "Fuji Speedway", "fuji_gp", 99)

        assert captured.get("has_driver_feedback") is False, (
            "has_driver_feedback must be False when no feedback rows exist")
