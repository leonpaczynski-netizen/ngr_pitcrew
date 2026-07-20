"""Phase 50 — immersive Race Weekend domain tests (task items 28-35, 48)."""
from __future__ import annotations

from strategy.race_weekend import (
    build_final_arrival, BriefingItem, build_driver_briefing, acknowledge_briefing,
    ScrutineeringCheck, CheckStatus as CS, build_scrutineering, ScrutineeringVerdict as V,
    build_chief_engineer_meeting, build_qualifying_experience, build_qualifying_review,
    build_race_briefing, acknowledge_race_briefing, build_race_runtime_profile,
    RACE_RUNTIME_PRIORITY, build_post_race_debrief,
)


def test_final_arrival_summarises_accumulated_preparation():
    fa = build_final_arrival(event_name="Porsche Cup R3", series="NGR Porsche Cup", round_label="R3",
                             track="Fuji", layout="Full", driver="leon", team="NGR",
                             sessions_completed=6, total_valid_laps=142,
                             tyre_model_confidence="mature", fuel_model_confidence="capped",
                             strategy_confidence="provisional", next_required_action="acknowledge briefing")
    assert fa.sessions_completed == 6 and fa.total_valid_laps == 142
    assert fa.fingerprint.startswith("race_weekend_v1:")


def test_final_arrival_fingerprint_deterministic():
    kw = dict(event_name="E", sessions_completed=6, total_valid_laps=100)
    assert build_final_arrival(**kw).fingerprint == build_final_arrival(**kw).fingerprint


# --- briefing acknowledgement ----------------------------------------------

def test_driver_briefing_requires_explicit_acknowledgement():
    b = build_driver_briefing("NGR Driver Briefing",
                              [BriefingItem("track limits", "3-strike"), BriefingItem("pit entry")])
    assert b.acknowledged is False
    acked = acknowledge_briefing(b)
    assert acked.acknowledged is True
    # acknowledgement is runtime state, not semantic content
    assert acked.fingerprint == b.fingerprint
    # original unchanged
    assert b.acknowledged is False


# --- virtual scrutineering -------------------------------------------------

def test_scrutineering_fail_yields_garage_hold():
    checks = [ScrutineeringCheck("BoP", CS.PASS), ScrutineeringCheck("race number", CS.FAIL)]
    assert build_scrutineering(checks).verdict == V.GARAGE_HOLD


def test_scrutineering_all_pass_is_cleared():
    checks = [ScrutineeringCheck("car", CS.PASS), ScrutineeringCheck("tyres", CS.PASS)]
    assert build_scrutineering(checks).verdict == V.CLEARED


def test_scrutineering_warn_is_cleared_with_warnings():
    checks = [ScrutineeringCheck("car", CS.PASS), ScrutineeringCheck("livery", CS.WARN)]
    assert build_scrutineering(checks).verdict == V.CLEARED_WITH_WARNINGS


def test_scrutineering_unverifiable_is_not_fabricated():
    checks = [ScrutineeringCheck("car", CS.PASS), ScrutineeringCheck("telemetry", CS.UNVERIFIABLE)]
    assert build_scrutineering(checks).verdict == V.UNVERIFIABLE


def test_scrutineering_all_na_is_not_applicable():
    checks = [ScrutineeringCheck("driver swap", CS.NOT_APPLICABLE)]
    assert build_scrutineering(checks).verdict == V.NOT_APPLICABLE
    assert build_scrutineering([]).verdict == V.NOT_APPLICABLE


def test_scrutineering_is_order_independent():
    a = build_scrutineering([ScrutineeringCheck("z", CS.PASS), ScrutineeringCheck("a", CS.WARN)])
    b = build_scrutineering([ScrutineeringCheck("a", CS.WARN), ScrutineeringCheck("z", CS.PASS)])
    assert a.fingerprint == b.fingerprint


# --- chief engineer meeting ------------------------------------------------

def test_chief_engineer_meeting_separates_quali_and_race_setups():
    m = build_chief_engineer_meeting(qualifying_setup_fingerprint="fp-q",
                                     race_setup_fingerprint="fp-r", voice_state="disabled",
                                     protected_strengths=("traction",))
    assert m.qualifying_setup_fingerprint != m.race_setup_fingerprint
    assert "traction" in m.protected_strengths


# --- qualifying + race briefing --------------------------------------------

def test_qualifying_experience_is_low_density():
    q = build_qualifying_experience(setup_confirmation="confirmed", available_attempts=2,
                                    target_lap="1:29.4", critical_corners=("T1", "T13"))
    assert q.available_attempts == 2 and "T1" in q.critical_corners


def test_race_briefing_requires_acknowledgement_and_grid_ready():
    b = build_race_briefing(starting_tyre="MR", primary_strategy="2-stop", voice_state="disabled")
    assert b.acknowledged is False and b.grid_ready is False
    acked = acknowledge_race_briefing(b, grid_ready=True)
    assert acked.acknowledged is True and acked.grid_ready is True
    # grid readiness requires acknowledgement (cannot be grid-ready without ack path)
    assert acked.fingerprint == b.fingerprint


def test_race_runtime_profile_priority_and_no_pit_commands():
    p = build_race_runtime_profile(voice_enabled=False, voice_eligible=False)
    assert p.priority_order[0] == "safety"
    assert p.priority_order == RACE_RUNTIME_PRIORITY
    assert p.issues_pit_commands is False


def test_race_runtime_voice_disabled_by_default():
    p = build_race_runtime_profile()
    assert p.voice_enabled is False


# --- post-race debrief -----------------------------------------------------

def test_post_race_debrief_captures_learning():
    d = build_post_race_debrief(result="P3", race_pace="strong", setup_promotion_or_rollback="promoted",
                                lessons_for_next_event=("earlier braking T1",))
    assert d.result == "P3"
    assert "earlier braking T1" in d.lessons_for_next_event
    assert d.fingerprint.startswith("race_weekend_v1:")
