"""Tests for grip scoring in strategy/engine.py."""
import time
from unittest.mock import MagicMock, patch
from strategy.engine import RaceStrategyEngine, Stint
from telemetry.state import TyreState


def _make_engine():
    tracker = MagicMock()
    tracker.avg_fuel_per_lap = 3.0
    tracker.laps_recorded = 0
    tracker.tyre_states = {}

    announcer = MagicMock()
    bridge = MagicMock()
    config = {}

    engine = RaceStrategyEngine(tracker, announcer, config, bridge)
    return engine


def _fake_record(lap_time_ms=95_000, lock_up_count=0, wheelspin_count=0, oversteer_count=0):
    r = MagicMock()
    r.lap_time_ms = lap_time_ms
    r.lock_up_count = lock_up_count
    r.wheelspin_count = wheelspin_count
    r.oversteer_count = oversteer_count
    return r


# ---------------------------------------------------------------------------
# _compute_grip_score
# ---------------------------------------------------------------------------

def test_grip_score_zero_for_clean_lap():
    engine = _make_engine()
    # 5 laps of identical clean times — no events, cool tyres
    for _ in range(5):
        engine._recent_lap_times.append(95_000)
        engine._recent_lockups.append(0)
        engine._recent_wheelspin.append(0)
        engine._recent_oversteer.append(0)

    engine._tracker.tyre_states = {k: TyreState.OPTIMAL for k in ("fl", "fr", "rl", "rr")}

    record = _fake_record(lap_time_ms=95_000)
    score, _ = engine._compute_grip_score(record)
    assert score == 0


def test_grip_score_high_for_degraded_lap():
    engine = _make_engine()
    # 5 prior clean laps
    for _ in range(5):
        engine._recent_lap_times.append(95_000)
        engine._recent_lockups.append(2)
        engine._recent_wheelspin.append(2)
        engine._recent_oversteer.append(1)

    # Heavily degraded current lap
    engine._tracker.tyre_states = {k: TyreState.OVERHEATING for k in ("fl", "fr", "rl", "rr")}

    record = _fake_record(
        lap_time_ms=98_500,    # 3.5s slower — pace component kicks in
        lock_up_count=8,       # 4× baseline of 2 → front_pts += 20
        wheelspin_count=6,     # 3× baseline → rear_pts += 20
        oversteer_count=4,     # 4× baseline → rear_pts += 12
    )
    score, _ = engine._compute_grip_score(record)
    assert score >= 70


def test_grip_alert_type_front_when_lockups_dominate():
    engine = _make_engine()
    for _ in range(5):
        engine._recent_lap_times.append(95_000)
        engine._recent_lockups.append(2)
        engine._recent_wheelspin.append(0)
        engine._recent_oversteer.append(0)

    engine._tracker.tyre_states = {}

    record = _fake_record(lap_time_ms=95_000, lock_up_count=6)
    _, alert_type = engine._compute_grip_score(record)
    assert alert_type == "front"


def test_grip_alert_type_rear_when_wheelspin_dominates():
    engine = _make_engine()
    for _ in range(5):
        engine._recent_lap_times.append(95_000)
        engine._recent_lockups.append(0)
        engine._recent_wheelspin.append(2)
        engine._recent_oversteer.append(2)

    engine._tracker.tyre_states = {}

    record = _fake_record(lap_time_ms=95_000, wheelspin_count=6, oversteer_count=6)
    _, alert_type = engine._compute_grip_score(record)
    assert alert_type == "rear"


# ---------------------------------------------------------------------------
# _check_grip_loss — cooldown suppresses repeat alerts
# ---------------------------------------------------------------------------

def test_grip_alert_cooldown_suppresses_second_alert():
    engine = _make_engine()
    # Pre-populate enough laps so check proceeds
    for _ in range(5):
        engine._recent_lap_times.append(95_000)
        engine._recent_lockups.append(2)
        engine._recent_wheelspin.append(2)
        engine._recent_oversteer.append(0)

    engine._tracker.tyre_states = {k: TyreState.OVERHEATING for k in ("fl", "fr", "rl", "rr")}
    # Active stint check relies on _active_stint returning None to skip laps_into_stint guard
    engine._stints = []

    record = _fake_record(lap_time_ms=98_500, lock_up_count=8, wheelspin_count=6)

    # First alert
    engine._check_grip_loss(record)
    engine._check_grip_loss(record)
    first_call_count = engine._announcer.announce.call_count

    # Set cooldown to future — next call should be suppressed
    engine._grip_alert_until = time.monotonic() + 120.0
    engine._check_grip_loss(record)
    assert engine._announcer.announce.call_count == first_call_count
