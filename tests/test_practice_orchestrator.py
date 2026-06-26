"""Tests for strategy.practice_orchestrator.run_practice_analysis."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# Minimal RaceParams stub (avoids importing full ai_planner before mocking)
# ---------------------------------------------------------------------------

@dataclass
class _RaceParams:
    track: str = "Suzuka"
    total_laps: int = 25
    tyre_wear_multiplier: float = 1.0
    fuel_burn_per_lap: float = 2.0
    refuel_speed_lps: float = 10.0
    pit_loss_secs: float = 23.0
    min_mandatory_stops: int = 0
    mandatory_compounds: list = field(default_factory=list)
    race_type: str = "lap"
    duration_mins: int = 0
    tuning_locked: bool = False
    allowed_tuning: list = field(default_factory=list)
    bop: bool = False
    avail_tyres: list = field(default_factory=list)
    track_location_id: str = ""
    layout_id: str = "suzuka__full"


@dataclass
class _PracticeAnalysis:
    strategies: list = field(default_factory=list)
    setup_changes: list = field(default_factory=list)
    further_practice: list = field(default_factory=list)
    aero_fuel_analysis: str = ""
    raw_response: str = "AI response text"


def _make_db():
    db = MagicMock()
    db.get_car_track_summary.return_value = {}
    db.get_recent_feedback.return_value = []
    db.get_recommendations_for_context.return_value = ""
    db.get_session_laps.return_value = []
    db.save_corner_issues.return_value = None
    db.get_previous_corner_issues.return_value = []
    db.insert_setup_recommendations.return_value = None
    db.get_corner_issues.return_value = []
    db.get_last_recommendation_ids.return_value = [1, 2]
    db.set_recommendation_corner_issues.return_value = None
    # Simulate no ai_interactions table returning None
    _conn = MagicMock()
    _conn.execute.return_value.fetchone.return_value = [None]
    db._conn = _conn
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_calls_ai_once():
    params = _RaceParams()
    db = _make_db()
    expected_result = _PracticeAnalysis()

    with patch("strategy.practice_orchestrator.analyse_practice_session",
               return_value=expected_result) as mock_ai, \
         patch("strategy._rec_parser.parse_recommendations_from_response",
               return_value=[]):
        from strategy.practice_orchestrator import run_practice_analysis
        result = run_practice_analysis(
            params, {"Soft": [90_000.0]}, {}, "GR86", {}, "", "key",
            db, car_id=1, session_id=0, model_name="claude-3",
        )

    assert mock_ai.call_count == 1
    assert result is expected_result


def test_writes_recs_to_db():
    params = _RaceParams()
    db = _make_db()
    fake_recs = [{"text": "Lower rear wing", "category": "Aero"}]

    with patch("strategy.practice_orchestrator.analyse_practice_session",
               return_value=_PracticeAnalysis()), \
         patch("strategy._rec_parser.parse_recommendations_from_response",
               return_value=fake_recs):
        from strategy.practice_orchestrator import run_practice_analysis
        run_practice_analysis(
            params, {"Soft": [90_000.0]}, {}, "GR86", {}, "", "key",
            db, car_id=1, session_id=0, model_name="claude-3",
        )

    db.insert_setup_recommendations.assert_called_once_with(fake_recs)


def test_links_corner_issues():
    params = _RaceParams()
    db = _make_db()
    db.get_corner_issues.return_value = [{"id": 10}, {"id": 11}]
    db.get_last_recommendation_ids.return_value = [100]
    fake_recs = [{"text": "Adjust dampers"}]

    with patch("strategy.practice_orchestrator.analyse_practice_session",
               return_value=_PracticeAnalysis()), \
         patch("strategy._rec_parser.parse_recommendations_from_response",
               return_value=fake_recs):
        from strategy.practice_orchestrator import run_practice_analysis
        run_practice_analysis(
            params, {"Soft": [90_000.0]}, {}, "GR86", {}, "", "key",
            db, car_id=1, session_id=0, model_name="claude-3",
        )

    db.set_recommendation_corner_issues.assert_called_once_with(100, [10, 11])


def test_propagates_ai_exception():
    params = _RaceParams()
    db = _make_db()

    with patch("strategy.practice_orchestrator.analyse_practice_session",
               side_effect=RuntimeError("API down")):
        from strategy.practice_orchestrator import run_practice_analysis
        with pytest.raises(RuntimeError, match="API down"):
            run_practice_analysis(
                params, {"Soft": [90_000.0]}, {}, "GR86", {}, "", "key",
                db, car_id=1, session_id=0, model_name="claude-3",
            )
