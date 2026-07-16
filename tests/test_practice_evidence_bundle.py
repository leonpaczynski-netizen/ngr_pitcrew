"""Sprint 9 — PracticeEvidenceBundle: explicit Practice → Strategy hand-off.

Practice writes the bundle; Strategy reads bundle.strategy_evidence directly
(no manual re-entry). Staleness fires when the setup, checkpoint, multipliers,
track, duration, or refuel rate move on since the bundle was built.
"""
from __future__ import annotations

from types import SimpleNamespace

from strategy.race_strategy_evidence import RaceStrategyEvidence
from strategy.race_strategy_scorer import recommend_strategy
from strategy.tyre_curves import build_compound_curves, compute_crossovers
from strategy.practice_evidence_bundle import (
    build_practice_evidence_bundle, detect_bundle_staleness, staleness_text,
    compute_bundle_change_hash,
)


def _evidence():
    return RaceStrategyEvidence(
        car_id=1, track="fuji", layout_id="fuji__full", race_laps=20,
        fuel_multiplier=1.0, tyre_multiplier=1.0, refuel_rate_lps=5.0,
        pit_loss_seconds=22.0, available_compounds=("RS", "RM"),
        lap_time_samples=tuple([100.0] * 10), fuel_use_samples=tuple([2.5] * 10),
        tyre_wear_samples=tuple([0.1] * 10),
        compound_samples={"RS": [98.0] * 8, "RM": [99.0] * 8},
        mandatory_pit_stops=1, required_compounds=("RM",),
    )


def _session_result(ev=None):
    ev = ev or _evidence()
    return SimpleNamespace(evidence=ev, missing_evidence=(), confidence="high",
                           samples=None, warnings=(), source_summary={})


def _bundle(**over):
    sr = _session_result()
    curves = build_compound_curves({"RS": [98000] * 8, "RM": [99000] * 8})
    kw = dict(
        session_result=sr, car_id=1, car_name="Porsche RSR",
        approved_setup_id="setup_42", applied_checkpoint_id="cp_1",
        setup_confirmed_in_gt7=True, compound_curves=curves,
        crossovers=tuple(compute_crossovers(curves)), session_ids=(101,),
        built_at="2026-07-15T12:00:00",
    )
    kw.update(over)
    return build_practice_evidence_bundle(**kw)


# --------------------------------------------------------------------------- #
def test_bundle_carries_identity_and_rules_from_evidence():
    b = _bundle()
    assert b.track == "fuji" and b.layout_id == "fuji__full"
    assert b.race_laps == 20 and b.fuel_multiplier == 1.0
    assert b.mandatory_pit_stops == 1 and b.required_compounds == ("RM",)
    assert b.approved_setup_id == "setup_42" and b.applied_checkpoint_id == "cp_1"
    assert b.confidence == "high"
    assert b.change_hash


def test_strategy_reads_bundle_evidence_directly():
    b = _bundle()
    assert b.is_ready_for_strategy
    rec = recommend_strategy(b.strategy_evidence)   # no re-entry — reads the bundle's evidence
    assert rec is not None


def test_not_ready_without_evidence():
    b = build_practice_evidence_bundle(session_result=SimpleNamespace(evidence=None))
    assert not b.is_ready_for_strategy


def test_compound_tested_flag():
    b = _bundle()
    assert b.compound_is_tested("RS")
    assert not b.compound_is_tested("RH")   # never measured


def test_no_staleness_when_nothing_changed_and_confirmed():
    b = _bundle()
    stale, reasons = detect_bundle_staleness(
        b, current_track="fuji", current_layout_id="fuji__full",
        current_race_laps=20, current_fuel_multiplier=1.0, current_tyre_multiplier=1.0,
        current_refuel_rate_lps=5.0, current_approved_setup_id="setup_42",
        current_applied_checkpoint_id="cp_1")
    assert not stale and reasons == ()


def test_setup_change_is_stale():
    b = _bundle()
    stale, reasons = detect_bundle_staleness(b, current_approved_setup_id="setup_99")
    assert stale and "setup_changed" in reasons


def test_checkpoint_change_is_stale():
    b = _bundle()
    stale, reasons = detect_bundle_staleness(b, current_applied_checkpoint_id="cp_2")
    assert stale and "checkpoint_changed" in reasons


def test_multiplier_and_refuel_changes_are_stale():
    b = _bundle()
    _, r1 = detect_bundle_staleness(b, current_fuel_multiplier=2.0)
    _, r2 = detect_bundle_staleness(b, current_tyre_multiplier=3.0)
    _, r3 = detect_bundle_staleness(b, current_refuel_rate_lps=10.0)
    assert "fuel_multiplier_changed" in r1
    assert "tyre_multiplier_changed" in r2
    assert "refuel_changed" in r3


def test_track_layout_duration_changes_are_stale():
    b = _bundle()
    _, r1 = detect_bundle_staleness(b, current_track="suzuka")
    _, r2 = detect_bundle_staleness(b, current_layout_id="fuji__short")
    _, r3 = detect_bundle_staleness(b, current_race_laps=30)
    assert "track_changed" in r1 and "layout_changed" in r2 and "duration_changed" in r3


def test_unconfirmed_setup_is_stale():
    b = _bundle(setup_confirmed_in_gt7=False)
    stale, reasons = detect_bundle_staleness(b, current_approved_setup_id="setup_42")
    assert stale and "not_confirmed" in reasons


def test_newer_practice_is_stale():
    b = _bundle()
    stale, reasons = detect_bundle_staleness(b, newer_practice_available=True)
    assert stale and "newer_practice" in reasons


def test_staleness_text_is_human_readable():
    txt = staleness_text(("setup_changed", "not_confirmed"))
    assert any("setup changed" in t for t in txt)


def test_change_hash_deterministic():
    a = compute_bundle_change_hash(track="fuji", layout_id="f", race_laps=20,
                                   race_duration_minutes=0, fuel_multiplier=1.0,
                                   tyre_multiplier=1.0, refuel_rate_lps=5.0,
                                   approved_setup_id="s", applied_checkpoint_id="c")
    b = compute_bundle_change_hash(track="fuji", layout_id="f", race_laps=20,
                                   race_duration_minutes=0, fuel_multiplier=1.0,
                                   tyre_multiplier=1.0, refuel_rate_lps=5.0,
                                   approved_setup_id="s", applied_checkpoint_id="c")
    assert a == b
