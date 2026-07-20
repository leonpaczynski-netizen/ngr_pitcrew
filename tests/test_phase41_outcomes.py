"""Phase 41 — run validity, expected-vs-observed, promotion eligibility, closed-loop closure."""
from strategy.engineering_run_outcome import build_run_outcome
from strategy.engineering_run_plan import build_engineering_run_plan
from strategy.closed_loop_report import build_closed_loop_report


_BASE = dict(candidate_tested=True, applied_setup_matches_plan=True, context_matches_plan=True,
             telemetry_complete=True, clean_laps=5, min_clean_required=3, compound_used="RH",
             planned_compound="RH")
_SCOPE = {"discipline": "race", "context_fingerprint": "cfp:x"}


def _plan(candidate=None):
    return build_engineering_run_plan(_SCOPE, candidate=candidate or {"candidate_id": "c1",
                                      "field": "lsd_initial", "direction": "increase"},
                                      applied_setup={"name": "B", "fields": {"lsd_initial": "20"}},
                                      parent_setup={"name": "A"}).to_dict()


# ---- 13. run validity ----------------------------------------------------------------------- #
def test_wrong_compound_is_confounded_and_does_not_count():
    o = build_run_outcome({**_BASE, "compound_used": "RM", "target_metric_improved": True},
                          discipline="race")
    assert o.validity["validity"] == "confounded"
    assert o.validity["counts_for_learning"] is False


def test_insufficient_clean_laps():
    o = build_run_outcome({**_BASE, "clean_laps": 1}, discipline="race")
    assert o.validity["validity"] == "insufficient_evidence"


def test_candidate_not_tested_is_invalid():
    o = build_run_outcome({**_BASE, "candidate_tested": False}, discipline="race")
    assert o.validity["validity"] == "invalid"


# ---- 14. expected vs observed --------------------------------------------------------------- #
def test_faster_but_worse_race_is_mixed_not_improved():
    o = build_run_outcome({**_BASE, "target_metric_improved": True, "lap_time_delta": -0.3,
                           "consistency_effect": "worse", "tyre_effect": "worse"}, discipline="race")
    assert o.comparison["outcome_state"] == "mixed"
    assert o.promotion["eligibility"] == "not_eligible"


def test_regression_recommends_rollback():
    o = build_run_outcome({**_BASE, "new_regressions": ["rear_instability"]}, discipline="race")
    assert o.comparison["outcome_state"] == "regressed"
    assert o.promotion["eligibility"] == "rollback_recommended"


# ---- 15. promotion eligibility -------------------------------------------------------------- #
def test_valid_improvement_repeated_is_best_known_eligible():
    o = build_run_outcome({**_BASE, "target_metric_improved": True, "lap_time_delta": -0.2,
                           "consistency_effect": "better", "tyre_effect": "better",
                           "fuel_effect": "neutral"}, discipline="race", independent_repeat=True)
    assert o.promotion["eligibility"] == "best_known_eligible"


def test_valid_improvement_single_session_is_provisional():
    o = build_run_outcome({**_BASE, "target_metric_improved": True, "lap_time_delta": -0.2,
                           "consistency_effect": "better"}, discipline="race",
                          independent_repeat=False)
    assert o.promotion["eligibility"] == "provisional"


def test_qualifying_improvement_not_assumed_race():
    q = build_run_outcome({**_BASE, "target_metric_improved": True, "lap_time_delta": -0.3},
                          discipline="qualifying", independent_repeat=True)
    # eligible as best-known QUALIFYING (discipline is part of the exact context) - a separate scope.
    assert q.promotion["eligibility"] == "best_known_eligible"
    assert q.session_binding["discipline"] == "qualifying"


# ---- 16/17. closed-loop knowledge update + rollback ----------------------------------------- #
def test_invalid_run_cannot_modify_working_window():
    plan = _plan()
    o = build_run_outcome({**_BASE, "compound_used": "RM", "target_metric_improved": True},
                          plan, discipline="race")
    rep = build_closed_loop_report(_SCOPE, plan, o.to_dict())
    kinds = {k["kind"] for k in rep.knowledge_update_proposal}
    assert kinds == {"no_window_change"}


def test_coaching_only_run_does_not_alter_setup_knowledge():
    plan = _plan()
    o = build_run_outcome({**_BASE, "new_regressions": ["x"]}, plan, discipline="race")
    rep = build_closed_loop_report(_SCOPE, plan, o.to_dict(), coaching_only=True)
    assert {k["kind"] for k in rep.knowledge_update_proposal} == {"driver_coaching_priority_changed"}


def test_multi_field_regression_next_action_isolate():
    cand = {"candidate_id": "c2", "attribution_scope": "coupled",
            "changes": [{"field": "ride_height_rear"}, {"field": "natural_frequency_rear"}]}
    plan = build_engineering_run_plan(_SCOPE, candidate=cand,
                                      applied_setup={"name": "B", "fields": {"ride_height_rear": "70",
                                                     "natural_frequency_rear": "3"}}).to_dict()
    o = build_run_outcome({**_BASE, "new_regressions": ["understeer"]}, plan, discipline="race")
    rep = build_closed_loop_report(_SCOPE, plan, o.to_dict())
    assert rep.primary_next_action["kind"] == "isolate_field"


def test_best_known_near_event_freezes_for_strategy():
    plan = _plan()
    o = build_run_outcome({**_BASE, "target_metric_improved": True, "lap_time_delta": -0.2,
                           "consistency_effect": "better", "tyre_effect": "better"},
                          plan, discipline="race", independent_repeat=True)
    rep = build_closed_loop_report(_SCOPE, plan, o.to_dict(), event_is_near=True)
    assert rep.primary_next_action["kind"] == "freeze_setup_and_prepare_strategy"


# ---- property: a faster lap alone cannot promote a Race setup ------------------------------- #
def test_property_faster_lap_alone_never_promotes_race():
    for tyre in ("worse", "neutral"):
        for cons in ("worse", "better"):
            o = build_run_outcome({**_BASE, "target_metric_improved": True, "lap_time_delta": -0.5,
                                   "consistency_effect": cons, "tyre_effect": tyre},
                                  discipline="race", independent_repeat=True)
            if tyre == "worse" or cons == "worse":
                assert o.promotion["eligibility"] != "best_known_eligible"
