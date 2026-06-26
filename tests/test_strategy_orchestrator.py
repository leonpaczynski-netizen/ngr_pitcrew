"""Tests for strategy.strategy_orchestrator.run_strategy_analysis."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

@dataclass
class _RaceParams:
    track: str = "Spa"
    total_laps: int = 44
    tyre_wear_multiplier: float = 1.0
    fuel_burn_per_lap: float = 2.5
    refuel_speed_lps: float = 10.0
    pit_loss_secs: float = 23.0
    min_mandatory_stops: int = 1
    mandatory_compounds: list = field(default_factory=list)
    race_type: str = "lap"
    duration_mins: int = 0
    tuning_locked: bool = False
    allowed_tuning: list = field(default_factory=list)
    bop: bool = False
    avail_tyres: list = field(default_factory=list)
    track_location_id: str = ""
    layout_id: str = "spa__full"


@dataclass
class _StrategyOption:
    rank: int = 1
    name: str = "1-stop Medium"
    stints: list = field(default_factory=list)
    estimated_time_s: float = 3600.0
    pit_time_s: float = 23.0
    summary: str = ""
    risks: str = ""


def _make_db():
    db = MagicMock()
    db.get_recent_fuel_sequence.return_value = [2.5, 2.4, 2.6]
    db.get_compound_lap_sequences.return_value = {"Medium": [90_000.0]}
    db.get_corner_issues.return_value = []
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_calls_ai_once():
    params = _RaceParams()
    db = _make_db()
    expected = [_StrategyOption()]

    with patch("strategy.strategy_orchestrator.analyse_strategy",
               return_value=expected) as mock_ai:
        from strategy.strategy_orchestrator import run_strategy_analysis
        result = run_strategy_analysis(
            params, {"Medium": [90_000.0]}, "key", db,
            car_id=1, session_id=5, car_name="GR86", car_specs={},
            setup_comparison_text="", tyre_degradation_cache=None,
            model_name="claude-3",
        )

    assert mock_ai.call_count == 1
    assert result is expected


def test_passes_fuel_sequence():
    params = _RaceParams()
    db = _make_db()
    db.get_recent_fuel_sequence.return_value = [2.1, 2.2]

    with patch("strategy.strategy_orchestrator.analyse_strategy",
               return_value=[]) as mock_ai:
        from strategy.strategy_orchestrator import run_strategy_analysis
        run_strategy_analysis(
            params, {}, "key", db,
            car_id=1, session_id=5, car_name="GR86", car_specs={},
            setup_comparison_text="", tyre_degradation_cache=None,
            model_name="claude-3",
        )

    call_kwargs = mock_ai.call_args.kwargs
    assert call_kwargs["fuel_sequence"] == [2.1, 2.2]


def test_propagates_ai_exception():
    params = _RaceParams()
    db = _make_db()

    with patch("strategy.strategy_orchestrator.analyse_strategy",
               side_effect=RuntimeError("timeout")):
        from strategy.strategy_orchestrator import run_strategy_analysis
        with pytest.raises(RuntimeError, match="timeout"):
            run_strategy_analysis(
                params, {}, "key", db,
                car_id=1, session_id=0, car_name="GR86", car_specs={},
                setup_comparison_text="", tyre_degradation_cache=None,
                model_name="claude-3",
            )
