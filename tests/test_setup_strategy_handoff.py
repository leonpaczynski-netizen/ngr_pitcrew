"""Setup → Strategy handoff tests (Engineering-Brain Phase 6).

The race Setup Brain packages its tyre/fuel/consistency evidence for the Strategy Brain
WITHOUT crossing authority — it authors no pit call, compound, stint plan or total-race-
time number.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from strategy.setup_strategy_handoff import (
    build_setup_strategy_handoff, handoff_respects_boundary, STRATEGY_OWNED,
    _FORBIDDEN_STRATEGY_KEYS,
)
from strategy.setup_engineering_context import build_setup_engineering_context
from strategy.setup_ranges import resolve_ranges
from strategy.setup_driver_profile import build_driver_profile

_CAR = "Porsche 911 RSR (991) '17"


def _ctx(objective):
    tp = SimpleNamespace(trustworthy=True, straight_fraction=0.32,
                         corner_density_per_km=3.5, summary=lambda: "Fuji")
    return build_setup_engineering_context(
        car=_CAR, objective=objective, ranges=resolve_ranges(_CAR), drivetrain="RR",
        profile=build_driver_profile(), track_profile=tp)


def test_race_handoff_describes_setup_characteristics():
    h = build_setup_strategy_handoff(_ctx("race"))
    assert h is not None and h.objective == "race"
    # A race setup targets tyre preservation, traction stability, consistency.
    assert h.tyre_preservation >= 0.3 and h.consistency >= 0.3
    assert h.strengths                                   # readable evidence for strategy


def test_non_race_returns_none():
    assert build_setup_strategy_handoff(_ctx("qualifying")) is None
    assert build_setup_strategy_handoff(_ctx("base")) is None


def test_strategy_ownership_listed():
    h = build_setup_strategy_handoff(_ctx("race"))
    owned = " ".join(h.strategy_owns)
    assert "crossover" in owned and "total-race-time" in owned and "fuel use per lap" in owned


def test_handoff_authors_no_strategy():
    h = build_setup_strategy_handoff(_ctx("race"))
    j = h.as_json()
    # The boundary marker is intact and no strategy-authoring keys leak in.
    assert j["authority"] == "setup_provides_evidence_only"
    assert handoff_respects_boundary(j)
    keys = set(j.keys()) | set(j["characteristics"].keys())
    assert not (keys & _FORBIDDEN_STRATEGY_KEYS)


def test_boundary_guard_rejects_leakage():
    # A tampered handoff that carries a strategy field or drops the marker fails the guard.
    assert not handoff_respects_boundary({"authority": "setup_provides_evidence_only",
                                          "pit_lap": 12})
    assert not handoff_respects_boundary({"authority": "something_else"})


def test_surfaced_in_race_baseline_response():
    from strategy.driving_advisor import DrivingAdvisor
    adv = DrivingAdvisor(SimpleNamespace(recent_laps=lambda n: [], last_lap=lambda: None,
                                         best_lap=lambda: None), SimpleNamespace(), {})
    r = json.loads(adv.build_baseline_setup_response(
        _CAR, resolve_ranges(_CAR), "RR", 6, None, False, session_type="Race",
        duration_mins=45.0, track_name="Fuji", layout_id="full", historical_setups=[]))
    h = r.get("setup_strategy_handoff") or {}
    assert h.get("authority") == "setup_provides_evidence_only"
    assert "characteristics" in h and h.get("strategy_owns")
    # A qualifying baseline carries no handoff.
    rq = json.loads(adv.build_baseline_setup_response(
        _CAR, resolve_ranges(_CAR), "RR", 6, None, False, session_type="Qualifying",
        duration_mins=0.0, track_name="Fuji", layout_id="full", historical_setups=[]))
    assert "setup_strategy_handoff" not in rq
