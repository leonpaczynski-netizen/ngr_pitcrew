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

def test_rule_to_field_direction_resolver():
    from strategy.setup_lineage import _rule_field_directions, _delta_fn_direction
    assert _delta_fn_direction("increase_rear_aero") == 1
    assert _delta_fn_direction("decrease_front_arb") == -1
    assert _delta_fn_direction("final_drive_up") == 1
    assert _delta_fn_direction("brake_bias_front") == -1
    assert _delta_fn_direction("brake_bias_rear") == 1
    assert _delta_fn_direction("noop") == 0
    res = _rule_field_directions()
    assert res.get("B4") == ("aero_rear", 1)          # increase_rear_aero
    assert res.get("A3") == ("ride_height_front", 1)  # raise_front_rh


def test_field_lockout_from_learning_outcomes_blocks_balance_move():
    from strategy.setup_lineage import (
        failed_directions_from_learning_outcomes, apply_direction_lockout,
    )
    scope = _scope()
    outcomes = [{"rule_id": "B4", "verdict": "worsened"},
                {"rule_id": "B4", "verdict": "worsened"}]   # raising rear aero worsened it
    fd = failed_directions_from_learning_outcomes(outcomes, scope)
    assert {(k.field, k.direction) for k in fd} == {("aero_rear", 1)}
    # A balance-shaped set that raises rear aero → that move is blocked, others allowed.
    changes = [{"field": "aero_rear", "delta": 30}, {"field": "toe_rear", "delta": 0.05},
               {"field": "brake_bias", "delta": -1}]
    allowed, blocked = apply_direction_lockout(changes, fd, scope)
    assert [c["field"] for c in allowed] == ["toe_rear", "brake_bias"]
    assert [c["field"] for c in blocked] == ["aero_rear"]


def test_balance_solver_respects_field_lockout_end_to_end():
    """A worsened 'increase rear aero' history blocks the balance solver's rear-aero
    move on the telemetry path (the balance solver doesn't consult outcomes itself)."""
    import json
    from types import SimpleNamespace
    import strategy.driving_advisor as da
    from tests.test_group63_setup_brain_uat2 import (
        _uat_advisor, _uat_history, _UAT_FEELING, _CAR as UCAR,
    )
    da.call_api = lambda *a, **k: json.dumps(
        {"status": "APPROVED", "warnings": [], "contradictions": [],
         "missing_evidence": [], "explanation_notes": "ok"})

    class _StubDB:
        def get_learning_outcomes(self, car_id, track, layout):
            return [{"rule_id": "B4", "verdict": "worsened"},
                    {"rule_id": "B4", "verdict": "worsened"}]
        def __getattr__(self, name):
            return lambda *a, **k: []      # every other DB call → benign empty result

    adv = _uat_advisor()
    adv._db = _StubDB()
    adv._car_id_ref = [1]
    setup = {"final_drive": 4.25, "transmission_max_speed_kmh": 0, "num_gears": 6,
             "aero_front": 450, "aero_rear": 590, "lsd_initial": 10, "lsd_accel": 15,
             "lsd_decel": 10, "camber_front": 1.0, "camber_rear": 1.5, "arb_front": 6,
             "arb_rear": 5, "toe_front": 0.0, "toe_rear": 0.05, "brake_bias": 0}
    r = json.loads(adv.build_combined_setup_response(
        setup_dict=setup, car_name=UCAR, feeling=_UAT_FEELING, purpose="Race",
        drivetrain="RR", historical_setups=_uat_history(), track_name="Fuji",
        fuel_multiplier=3.0, refuel_rate_lps=1.0))
    # The balance solver would normally raise rear aero; the lockout blocks it.
    authored = {c["field"] for c in r.get("changes", [])}
    assert "aero_rear" not in authored
    lockouts = r.get("closed_loop_lockouts") or []
    assert any(l.get("field") == "aero_rear" for l in lockouts)


# ------------------------------------------------------------------ contradiction hard-fail

def test_detect_contradictions():
    from strategy.setup_diagnosis import detect_diagnosis_contradictions, contradicted_fields
    assert [c["kind"] for c in detect_diagnosis_contradictions(
        {"gearing_state": "conflicting"})] == ["gearing_conflicting"]
    assert [c["kind"] for c in detect_diagnosis_contradictions(
        {"wheelspin_subtype": "conflicting_evidence"})] == ["wheelspin_conflicting"]
    assert [c["kind"] for c in detect_diagnosis_contradictions(
        {"bottoming_display_state": {"state": "address", "performance_relevant": False}})] \
        == ["bottoming_incoherent"]
    # Coherent diagnosis → no contradictions.
    assert detect_diagnosis_contradictions(
        {"gearing_state": "appropriate", "wheelspin_subtype": "unknown"}) == []
    contras = detect_diagnosis_contradictions({"gearing_state": "conflicting"})
    assert contradicted_fields(contras) == {"final_drive", "gear_5", "gear_6"}


# ------------------------------------------------------------------ lineage persistence (DB)

def test_lineage_persistence_and_rollback_db():
    import json as _json
    from data.session_db import SessionDB
    from strategy.setup_lineage import rollback_from_lineage
    db = SessionDB(":memory:")
    # DB_VERSION reached 16 with the Practice Review capture columns (_migrate_v16).
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 16
    for ch in ([{"field": "arb_front", "from": "6", "to": "5"}],
               [{"field": "lsd_accel", "from": "15", "to": "17"}]):
        db._conn.execute(
            "INSERT INTO setup_recommendations (car_id, track, layout_id, status, "
            "approved_changes_json, created_at) VALUES (1,'Fuji','full','proposed',?,'t')",
            (_json.dumps(ch),))
    db._conn.commit()
    r_first = db.apply_recommendation_for_car_track(1, "Fuji", 101)   # newest rec first
    r_second = db.apply_recommendation_for_car_track(1, "Fuji", 102)
    lin = db.get_lineage(1, "Fuji", "full")
    assert len(lin) == 2
    # The second node is auto-parented to the first.
    assert lin[0]["parent_id"] == lin[1]["id"]
    # Stamp the last-applied setup as worse → rollback recommends reverting it.
    db.record_lineage_outcome_by_rec(r_second, "worsened", 103)
    rb = rollback_from_lineage(db.get_lineage(1, "Fuji", "full"))
    assert rb["recommend_rollback"] is True
    assert rb["target_id"] == lin[1]["id"]
    assert rb["revert_changes"]                       # a concrete revert exists


def test_rollback_none_when_last_setup_improved():
    from strategy.setup_lineage import rollback_from_lineage
    rows = [{"id": 2, "parent_id": 1, "changes_json": "[]", "outcome_verdict": "improved"},
            {"id": 1, "parent_id": None, "changes_json": "[]", "outcome_verdict": "neutral"}]
    assert rollback_from_lineage(rows)["recommend_rollback"] is False


def test_rollback_skips_unscored_to_newest_scored():
    from strategy.setup_lineage import rollback_from_lineage
    import json as _json
    rows = [{"id": 3, "parent_id": 2, "changes_json": "[]", "outcome_verdict": ""},   # unscored
            {"id": 2, "parent_id": 1,
             "changes_json": _json.dumps([{"field": "aero_rear", "from": "600", "to": "630"}]),
             "outcome_verdict": "worsened"},
            {"id": 1, "parent_id": None, "changes_json": "[]", "outcome_verdict": "improved"}]
    rb = rollback_from_lineage(rows)
    assert rb["recommend_rollback"] and rb["target_id"] == 1


def test_closed_loop_ui_render():
    from ui.setup_builder_ui import _closed_loop_html
    data = {
        "rollback": {"recommend_rollback": True, "reason": "Last setup tested worse.",
                     "revert_changes": [{"field": "aero_rear", "to": "600"}]},
        "diagnosis_contradictions": [{"kind": "gearing_conflicting",
                                      "detail": "telemetry vs report disagree"}],
        "closed_loop_lockouts": [{"field": "lsd_accel", "reason": "worsened the car"}],
    }
    h = _closed_loop_html(data)
    assert "<table" not in h  # (grouped divs, not a table) but the three sections render
    assert "roll" in h.lower() and "Withheld" in h and "Not repeating" in h
    # Self-guards.
    assert _closed_loop_html({}) == "" and _closed_loop_html(None) == ""


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
