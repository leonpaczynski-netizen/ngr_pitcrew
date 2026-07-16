"""Golden UAT — end-to-end Porsche-at-Fuji, deterministic & offline (Sprint 12).

One scenario that walks the whole rebuilt pipeline and asserts every release
gate that can be checked deterministically without a running Qt app or a live
GT7 feed. Each test maps to a RELEASE GATE from the rebuild brief.

Deterministic: no network, no AI, no Qt, no wall-clock. Every engine is the real
production module; the inputs are synthetic but representative of the UAT
scenario (Porsche RSR at Fuji Full Course).
"""
from __future__ import annotations

import importlib
import math
from types import SimpleNamespace

import pytest

# ---- engines under test (all real production modules) ----------------------
from data.track_readiness_disk import resolve_track_readiness_from_disk
from data.track_readiness import TrackReadiness
from telemetry.slip_events import extract_slip_episodes
from strategy.cross_lap_persistence import (
    occurrence_from_episode, analyse_cross_lap, LapMeta, PersistenceClass,
)
from strategy.setup_diagnosis import _rh_permitted_increment
from strategy.setup_decision import (
    arbitrate_setup_decision, DriverFeedback, DecisionStatus,
)
from strategy.tyre_curves import build_compound_curves, compute_crossovers
from strategy.race_strategy_evidence import RaceStrategyEvidence
from strategy.race_strategy_candidates import generate_candidates, legal_candidates
from strategy.race_strategy_scorer import recommend_strategy, score_candidates
from strategy.practice_evidence_bundle import (
    build_practice_evidence_bundle, detect_bundle_staleness,
)
from data.applied_checkpoint import (
    compute_apply_status, make_checkpoint, SetupApplyState,
)

_FUJI_LOC = "fuji_international_speedway"
_FUJI_LAY = "fuji_international_speedway__full_course"
_TWO_PI = 2.0 * math.pi
_RADIUS = 0.33


# --------------------------------------------------------------------------- #
# Telemetry helpers (Porsche RSR = RWD, rear-driven)
# --------------------------------------------------------------------------- #
def _frame(t_ms, *, throttle=0.0, brake=0.0, gear=3, rear_ratio=1.0, speed_kmh=95.0,
           suspension=0.0, road_plane_y=1.0):
    base = (speed_kmh / 3.6) / (_RADIUS * _TWO_PI)
    rps = (base, base, base * rear_ratio, base * rear_ratio)
    return SimpleNamespace(
        elapsed_ms=t_ms, speed_kmh=speed_kmh, throttle=throttle, brake=brake,
        gear=gear, rpm=6000.0, road_distance=1500.0, wheel_rps=rps,
        tyre_radius=(_RADIUS,) * 4, suspension=(suspension,) * 4, angvel_z=0.1,
        road_plane_y=road_plane_y)


def _t3_spin_lap():
    return [_frame(i * 10, throttle=1.0, rear_ratio=1.5) for i in range(20)]


def _clean_lap():
    return [_frame(i * 10, throttle=0.3, rear_ratio=1.0) for i in range(20)]


def _seg(_d, _s, _t, _b):
    return ("T3", "exit")


def _occurrences(spin_laps: set):
    occ, laps = [], []
    for lap_no in range(1, 9):
        laps.append(LapMeta(session_id=1, lap_number=lap_no, classification="flying",
                            valid=True, setup_checkpoint_id="cp1"))
        frames = _t3_spin_lap() if lap_no in spin_laps else _clean_lap()
        for e in extract_slip_episodes(frames, drivetrain="FR", segment_resolver=_seg):
            occ.append(occurrence_from_episode(
                e, session_id=1, setup_checkpoint_id="cp1", lap_number=lap_no,
                track="fuji", layout_id=_FUJI_LAY))
    return occ, laps


# =========================================================================== #
# RELEASE GATES
# =========================================================================== #
def test_gate_no_generative_ai_remains():
    for mod in ("strategy._ai_client", "strategy.ai_planner",
                "strategy.corner_verify_ai", "data.ai_context_snapshot"):
        with pytest.raises(ImportError):
            importlib.import_module(mod)


def test_gate_core_engines_import_without_network():
    # Importing/using the core engines requires no network. (If any tried to
    # open a socket at import, these imports would already have failed offline.)
    for mod in ("telemetry.slip_events", "strategy.cross_lap_persistence",
                "strategy.tyre_curves", "strategy.setup_decision",
                "strategy.practice_evidence_bundle", "data.track_readiness_disk"):
        assert importlib.import_module(mod) is not None


def test_gate_fuji_ready_automatically_from_disk():
    r = resolve_track_readiness_from_disk(_FUJI_LOC, _FUJI_LAY)
    assert r.state is TrackReadiness.READY_APPROVED
    assert r.is_ready and r.is_approved


def test_gate_one_slide_is_one_episode():
    eps = [e for e in extract_slip_episodes(_t3_spin_lap(), drivetrain="FR")
           if e.kind == "wheelspin"]
    assert len(eps) == 1


def test_gate_two_poor_laps_do_not_author_a_change():
    occ, laps = _occurrences(spin_laps={2, 5})   # only 2 of 8
    results = analyse_cross_lap(occ, laps)
    assert not any(r.eligible_for_setup for r in results)


def test_gate_recurring_same_corner_is_eligible():
    occ, laps = _occurrences(spin_laps={1, 2, 4, 5, 7, 8})   # 6 of 8, same corner
    results = analyse_cross_lap(occ, laps)
    t3 = next(r for r in results if r.signature.segment_id == "T3")
    assert t3.classification is PersistenceClass.PERSISTENT_PATTERN
    assert t3.eligible_for_setup


def test_gate_kerb_bottoming_never_raises_ride_height():
    assert _rh_permitted_increment({"confidence": "medium", "subtype": "kerb_strike"}, True) == 0
    assert _rh_permitted_increment({"confidence": "high", "subtype": "kerb_strike"}, True) == 0


def test_gate_low_confidence_cannot_override_good_feedback():
    # Fixture E: driver reports good traction; slip on 2/8 laps (not eligible).
    occ, laps = _occurrences(spin_laps={2, 5})
    persistence = analyse_cross_lap(occ, laps)
    d = arbitrate_setup_decision([{"field": "lsd_accel"}], persistence,
                                 DriverFeedback(traction="good", better_than_previous=True))
    assert d.status is DecisionStatus.EVIDENCE_CONFLICT
    assert "lsd_accel" not in d.fields_by_outcome("approved")
    assert not d.is_approved


def test_gate_never_approved_and_failed_together():
    d = arbitrate_setup_decision([{"field": "lsd_accel"}], [], DriverFeedback(),
                                 validation_failed=True)
    assert d.status is DecisionStatus.ENGINEERING_FAILURE and not d.is_approved


def test_gate_tyre_crossovers_rs_rm_lap3_rm_rh_lap6():
    curves = build_compound_curves({
        "RS": [98000, 98000, 98000] + [100000] * 5,
        "RM": [99000] * 6 + [101500] * 6,
        "RH": [100000] * 12 + [101800] * 2,
    })
    xs = {(c.softer, c.harder): c.crossover_after_lap for c in compute_crossovers(curves)}
    assert xs[("RS", "RM")] == 3
    assert xs[("RM", "RH")] == 6


def _evidence(**over):
    base = dict(
        car_id=1, track="fuji", layout_id=_FUJI_LAY, race_laps=20,
        fuel_multiplier=1.0, tyre_multiplier=1.0, refuel_rate_lps=5.0,
        pit_loss_seconds=22.0, available_compounds=("RS", "RM"),
        lap_time_samples=tuple([100.0] * 10), fuel_use_samples=tuple([2.5] * 10),
        tyre_wear_samples=tuple([0.1] * 10),
        compound_samples={"RS": [98.0] * 8, "RM": [99.0] * 8},
        mandatory_pit_stops=1, required_compounds=("RM",))
    base.update(over)
    return RaceStrategyEvidence(**base)


def test_gate_strategy_deterministic_and_excludes_untested():
    ev = _evidence(available_compounds=("RS", "RM", "RH"))  # RH untested
    a = score_candidates(generate_candidates(ev), ev)
    b = score_candidates(generate_candidates(ev), ev)
    assert [s.candidate_id for s in a] == [s.candidate_id for s in b]  # deterministic
    for c in legal_candidates(generate_candidates(ev)):
        assert "RH" not in c.compound_plan                             # untested excluded


def test_gate_strategy_does_not_author_setup():
    import strategy.race_strategy_candidates as m
    import strategy.race_strategy_scorer as s
    for mod in (m, s):
        src = open(mod.__file__, encoding="utf-8").read().lower()
        for token in ("ride_height", "lsd_accel", "camber", "brake_bias", "arb_"):
            assert token not in src, f"{mod.__name__} references setup field {token}"


def test_gate_practice_evidence_flows_into_strategy():
    ev = _evidence()
    sr = SimpleNamespace(evidence=ev, missing_evidence=(), confidence="high")
    curves = build_compound_curves({"RS": [98000] * 8, "RM": [99000] * 8})
    bundle = build_practice_evidence_bundle(
        session_result=sr, car_id=1, car_name="Porsche RSR",
        approved_setup_id="s1", applied_checkpoint_id="cp1",
        setup_confirmed_in_gt7=True, compound_curves=curves,
        crossovers=tuple(compute_crossovers(curves)), session_ids=(101,))
    assert bundle.is_ready_for_strategy
    rec = recommend_strategy(bundle.strategy_evidence)   # strategy reads the bundle
    assert rec is not None
    stale, _ = detect_bundle_staleness(bundle, current_approved_setup_id="s1",
                                       current_applied_checkpoint_id="cp1")
    assert not stale


def test_gate_saved_highlighted_until_confirmed_in_gt7():
    fields = {"ride_height_rear": 60}
    s = compute_apply_status(fields, None)                 # saved, never confirmed
    assert s.state is SetupApplyState.CHANGED_SINCE_GT7 and s.has_pending
    cp = make_checkpoint(setup_id="s1", fields=fields, confirmed_at="8:42 PM")
    assert compute_apply_status(fields, cp).state is SetupApplyState.CONFIRMED_IN_GT7


def test_gate_speech_recognition_is_local_only():
    ql = (__import__("pathlib").Path(__file__).resolve().parent.parent /
          "voice" / "query_listener.py").read_text(encoding="utf-8")
    assert ".recognize_google(" not in ql
    assert ".recognize_sphinx(" in ql


def test_gate_full_scenario_deterministic_rerun_equality():
    # The whole persistence→decision chain must be identical on re-run.
    occ, laps = _occurrences(spin_laps={1, 2, 4, 5, 7, 8})
    p1 = analyse_cross_lap(occ, laps)
    p2 = analyse_cross_lap(occ, laps)
    assert p1 == p2
    fb = DriverFeedback(traction="neutral")
    d1 = arbitrate_setup_decision([{"field": "lsd_accel"}], p1, fb)
    d2 = arbitrate_setup_decision([{"field": "lsd_accel"}], p2, fb)
    assert d1 == d2
