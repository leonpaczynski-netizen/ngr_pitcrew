"""Tests for fuel calculations in strategy/engine.py."""
import pytest
from unittest.mock import MagicMock
from strategy.engine import RaceStrategyEngine, Stint, _FUEL_MULTIPLIERS


def _make_engine(avg_fuel: float = 3.0, fuel_strategy: str = "balanced"):
    tracker = MagicMock()
    tracker.avg_fuel_per_lap = avg_fuel
    tracker.laps_recorded = 0

    announcer = MagicMock()
    bridge = MagicMock()
    config = {"fuel": {"strategy": fuel_strategy}}

    engine = RaceStrategyEngine(tracker, announcer, config, bridge)
    return engine, tracker


def _make_stints(*laps_list) -> list[Stint]:
    return [
        Stint(
            stint_num=i + 1,
            laps=laps,
            compound="Hard",
            ref_lap_ms=95_000,
            pace_threshold_ms=3000,
        )
        for i, laps in enumerate(laps_list)
    ]


# ---------------------------------------------------------------------------
# _FUEL_MULTIPLIERS constants
# ---------------------------------------------------------------------------

def test_fuel_multipliers_values():
    assert _FUEL_MULTIPLIERS["safe"]       == pytest.approx(1.08)
    assert _FUEL_MULTIPLIERS["balanced"]   == pytest.approx(1.05)
    assert _FUEL_MULTIPLIERS["aggressive"] == pytest.approx(1.02)


# ---------------------------------------------------------------------------
# _fuel_target_for_next — percentage multiplier formula
# ---------------------------------------------------------------------------

def test_fuel_target_balanced_next_stint():
    # avg=3.0L, next stint 12 laps, balanced (1.05): 3.0 × 12 × 1.05 = 37.8
    engine, _ = _make_engine(avg_fuel=3.0, fuel_strategy="balanced")
    stints = _make_stints(10, 12)
    engine._stints = stints
    target = engine._fuel_target_for_next(stints[0])
    assert target == pytest.approx(37.8)


def test_fuel_target_safe_multiplier():
    # avg=3.0L, 10 laps remaining, safe (1.08): 3.0 × 10 × 1.08 = 32.4
    engine, _ = _make_engine(avg_fuel=3.0, fuel_strategy="safe")
    stints = _make_stints(10)
    stints[0].start_lap = 0
    stints[0].end_lap = 10
    engine._stints = stints
    target = engine._fuel_target_for_next(stints[0])
    assert target == pytest.approx(32.4)


def test_fuel_target_aggressive_multiplier():
    # avg=3.0L, 10 laps remaining, aggressive (1.02): 3.0 × 10 × 1.02 = 30.6
    engine, _ = _make_engine(avg_fuel=3.0, fuel_strategy="aggressive")
    stints = _make_stints(10)
    stints[0].start_lap = 0
    stints[0].end_lap = 10
    engine._stints = stints
    target = engine._fuel_target_for_next(stints[0])
    assert target == pytest.approx(30.6)


def test_fuel_target_zero_when_no_fuel_data():
    engine, tracker = _make_engine(avg_fuel=0.0)
    stints = _make_stints(10, 12)
    engine._stints = stints
    target = engine._fuel_target_for_next(stints[0])
    assert target == 0.0


def test_fuel_target_last_stint_uses_remaining_laps():
    # avg=2.5L, laps_recorded=8, end_lap=10 → remaining=max(1,10-8)=2
    # balanced: 2.5 × 2 × 1.05 = 5.25
    engine, tracker = _make_engine(avg_fuel=2.5, fuel_strategy="balanced")
    tracker.laps_recorded = 8
    stints = _make_stints(10)
    stints[0].start_lap = 0
    stints[0].end_lap = 10
    engine._stints = stints
    target = engine._fuel_target_for_next(stints[0])
    assert target == pytest.approx(5.25)


def test_fuel_target_unknown_strategy_defaults_balanced():
    # Unknown strategy string falls back to balanced multiplier (1.05)
    engine, _ = _make_engine(avg_fuel=4.0, fuel_strategy="turbo")
    stints = _make_stints(10, 8)
    engine._stints = stints
    # next stint 8 laps: 4.0 × 8 × 1.05 = 33.6
    target = engine._fuel_target_for_next(stints[0])
    assert target == pytest.approx(33.6)


# ---------------------------------------------------------------------------
# _check_fuel_drift — verify 15% threshold triggers announcement
# ---------------------------------------------------------------------------

def test_fuel_drift_triggers_at_15_percent():
    engine, tracker = _make_engine(avg_fuel=3.0)
    engine._stints = _make_stints(10)
    engine._recalc_cooldown_until = 0.0

    # Establish reference
    engine._check_fuel_drift()
    assert engine._last_avg_fuel_ref == pytest.approx(3.0)

    # Drift by 20% → should announce
    tracker.avg_fuel_per_lap = 3.6
    engine._check_fuel_drift()
    engine._announcer.announce.assert_called()


def test_fuel_drift_suppressed_below_15_percent():
    engine, tracker = _make_engine(avg_fuel=3.0)
    engine._stints = _make_stints(10)
    engine._recalc_cooldown_until = 0.0

    engine._check_fuel_drift()
    engine._announcer.announce.reset_mock()

    # Drift by 10% — should NOT announce
    tracker.avg_fuel_per_lap = 3.3
    engine._check_fuel_drift()
    engine._announcer.announce.assert_not_called()
