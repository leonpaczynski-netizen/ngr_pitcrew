"""Closed-loop setup development tests (strategy/setup_lineage + rule-engine lockout).

Phase 1 of the engineering-brain plan: the app must know what changed, whether it
helped or hurt, and must NOT repeat a change that made the car worse.
"""
from __future__ import annotations

from strategy.setup_lineage import (
    FieldChange, ExperimentScope, SetupExperiment, ExperimentOutcome,
    attribute_change_outcomes, failed_directions, ineffective_directions,
    apply_direction_lockout, rollback_target, rollback_advice,
    blocked_rules_from_outcomes,
    OUTCOME_BETTER, OUTCOME_WORSE, OUTCOME_UNCHANGED,
    VERDICT_EFFECTIVE, VERDICT_INEFFECTIVE, VERDICT_HARMFUL,
)


def _scope():
    return ExperimentScope(car="Porsche 911 RSR", track="Fuji", layout="full",
                           objective="race", driver_version="v1")


def _plan_experiment():
    # The plan's exact two-stage failed experiment.
    return SetupExperiment("s19", "s18", (
        FieldChange("arb_front", 6, 5, expected_effects=("mid_corner_understeer",)),
        FieldChange("lsd_accel", 15, 17, expected_effects=("exit_traction",)),
    ), _scope(), label="Race Setup 19")


def _worse_outcome():
    return ExperimentOutcome("s19", overall=OUTCOME_WORSE,
                             symptom_outcomes={"mid_corner_understeer": OUTCOME_UNCHANGED},
                             new_problems=("rear_loose_on_exit",),
                             notes="rear harder to control")


# ------------------------------------------------------------------ attribution

def test_attribution_matches_the_plan():
    v = {x.field: x for x in attribute_change_outcomes(_plan_experiment(), _worse_outcome())}
    # ARB reduction did not help its target → INEFFECTIVE (not blamed for the rear).
    assert v["arb_front"].verdict == VERDICT_INEFFECTIVE
    # LSD accel increase caused the new rear problem → HARMFUL.
    assert v["lsd_accel"].verdict == VERDICT_HARMFUL
    assert "rear_loose_on_exit" in v["lsd_accel"].reason


def test_effective_when_target_improves():
    exp = SetupExperiment("s2", "s1", (
        FieldChange("aero_front", 400, 430, expected_effects=("mid_corner_understeer",)),
    ), _scope())
    out = ExperimentOutcome("s2", overall=OUTCOME_BETTER,
                            symptom_outcomes={"mid_corner_understeer": OUTCOME_BETTER})
    assert attribute_change_outcomes(exp, out)[0].verdict == VERDICT_EFFECTIVE


def test_targeted_symptom_worse_is_harmful():
    exp = SetupExperiment("s2", "s1", (
        FieldChange("aero_front", 400, 430, expected_effects=("mid_corner_understeer",)),
    ), _scope())
    out = ExperimentOutcome("s2", overall=OUTCOME_WORSE,
                            symptom_outcomes={"mid_corner_understeer": OUTCOME_WORSE})
    assert attribute_change_outcomes(exp, out)[0].verdict == VERDICT_HARMFUL


# ------------------------------------------------------------------ lockout

def test_failed_direction_blocks_repetition():
    v = attribute_change_outcomes(_plan_experiment(), _worse_outcome())
    fd = failed_directions(v)
    # Only the harmful LSD-accel INCREASE is a failed direction.
    assert {(k.field, k.direction) for k in fd} == {("lsd_accel", 1)}
    proposed = [{"field": "lsd_accel", "delta": +2}, {"field": "arb_front", "delta": -1}]
    allowed, blocked = apply_direction_lockout(proposed, fd, _scope())
    assert [c["field"] for c in allowed] == ["arb_front"]
    assert [c["field"] for c in blocked] == ["lsd_accel"]
    assert blocked[0]["_lockout"] and "made the car worse" in blocked[0]["_lockout_reason"]


def test_opposite_direction_is_not_blocked():
    v = attribute_change_outcomes(_plan_experiment(), _worse_outcome())
    fd = failed_directions(v)
    # A DECREASE of lsd_accel is a different direction — not blocked.
    allowed, blocked = apply_direction_lockout([{"field": "lsd_accel", "delta": -2}], fd, _scope())
    assert [c["field"] for c in allowed] == ["lsd_accel"] and not blocked


def test_lockout_is_scope_specific():
    v = attribute_change_outcomes(_plan_experiment(), _worse_outcome())
    fd = failed_directions(v)
    # Same change, DIFFERENT track → not blocked (a Fuji failure is not a global ban).
    other = ExperimentScope(car="Porsche 911 RSR", track="Suzuka", layout="east",
                            objective="race", driver_version="v1")
    allowed, blocked = apply_direction_lockout([{"field": "lsd_accel", "delta": +2}], fd, other)
    assert [c["field"] for c in allowed] == ["lsd_accel"] and not blocked


def test_override_lifts_lockout():
    v = attribute_change_outcomes(_plan_experiment(), _worse_outcome())
    fd = failed_directions(v)
    allowed, blocked = apply_direction_lockout(
        [{"field": "lsd_accel", "delta": +2}], fd, _scope(),
        override_reasons={"lsd_accel": "new telemetry shows a real traction deficit"})
    assert [c["field"] for c in allowed] == ["lsd_accel"] and not blocked


# ------------------------------------------------------------------ rollback

def test_rollback_target_when_worse():
    assert rollback_target(_plan_experiment(), _worse_outcome()) == "s18"
    adv = rollback_advice(_plan_experiment(), _worse_outcome(),
                          attribute_change_outcomes(_plan_experiment(), _worse_outcome()))
    assert adv["recommend_rollback"] and adv["target"] == "s18"
    assert any(h["field"] == "lsd_accel" for h in adv["harmful"])


def test_no_rollback_when_better():
    out = ExperimentOutcome("s19", overall=OUTCOME_BETTER)
    assert rollback_target(_plan_experiment(), out) is None
    assert rollback_advice(_plan_experiment(), out)["recommend_rollback"] is False


# ------------------------------------------------------------------ rule lockout builder

def test_blocked_rules_from_outcomes_thresholds():
    rows = [{"rule_id": "C3", "verdict": "worsened"}, {"rule_id": "C3", "verdict": "worsened"},
            {"rule_id": "C5", "verdict": "worsened"},                       # only 1 → not blocked
            {"rule_id": "B6", "verdict": "worsened"}, {"rule_id": "B6", "verdict": "worsened"},
            {"rule_id": "B6", "verdict": "improved"}]                       # improved → not blocked
    blocked = blocked_rules_from_outcomes(rows)
    assert set(blocked) == {"C3"}
    assert "worsened the car 2 time(s)" in blocked["C3"]


def test_blocked_rules_ignores_neutral_and_missing():
    rows = [{"rule_id": "X", "verdict": "neutral"}, {"rule_id": "X", "verdict": "neutral"},
            {"verdict": "worsened"}, {"rule_id": "Y"}]
    assert blocked_rules_from_outcomes(rows) == {}


# ------------------------------------------------------------------ rule-engine integration

def test_rule_engine_honours_lockout():
    from strategy.setup_rule_engine import run_rule_engine
    from strategy.setup_driver_profile import build_driver_profile
    from strategy.setup_ranges import resolve_ranges
    from strategy.setup_diagnosis import build_setup_diagnosis
    car = "Porsche 911 RSR (991) '17"
    ranges = resolve_ranges(car)
    setup = {"arb_front": 6, "aero_front": 400}
    diag = build_setup_diagnosis([], setup, car, {}, "Mid-Corner: Pushes wide")
    free = run_rule_engine(diag, setup, ranges, build_driver_profile())
    fired = [c.rule_id for c in free.proposed]
    assert fired, "need at least one fired rule to test the lockout"
    locked = run_rule_engine(diag, setup, ranges, build_driver_profile(),
                             blocked_rule_ids={fired[0]: "locked out (test)"})
    assert fired[0] not in [c.rule_id for c in locked.proposed]
    assert fired[0] in [c.rule_id for c in locked.rejected_candidates]
