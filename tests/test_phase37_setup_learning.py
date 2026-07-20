"""Phase 37 — setup-lineage interpretation, no-repeat guard, rollback, working windows."""
from strategy.setup_outcome_learning import build_setup_outcome_learning, DirectionAction
from strategy.setup_working_window import build_setup_working_windows, FieldStatus
from tests._race_engineer_helpers import ctx, record, change


def _fp():
    return "scope_fp"


# ---- 4. setup-lineage interpretation -------------------------------------------------------- #
def test_lineage_ordered_and_verdicts():
    a = record("A", changes=[change("arb_rear", "6")], outcome="confirmed_improvement", at="2026-01-01")
    b = record("B", changes=[change("lsd_acceleration", "40")], outcome="regression", at="2026-01-02",
               regressions=[{"issue_type": "wheelspin", "corner_name": "T2", "is_new": True}])
    r = build_setup_outcome_learning(_fp(), [a, b])
    assert [s["record_key"] for s in r.lineage] == ["A", "B"]
    assert r.lineage[0]["verdict"] == "improved" and r.lineage[1]["verdict"] == "worsened"


# ---- 5. failed-direction no-repeat logic ---------------------------------------------------- #
def test_failed_direction_blocked():
    b = record("B", changes=[change("lsd_acceleration", "40", "increase")], outcome="regression")
    r = build_setup_outcome_learning(_fp(), [b])
    blocked = {(x["field"], x["direction"]) for x in r.blocked_directions}
    assert ("lsd_acceleration", "increase") in blocked


def test_block_stands_without_stronger_evidence():
    # regression (high) then a later weaker improvement (low) on the same direction -> stays blocked.
    b = record("B", changes=[change("lsd_acceleration", "40", "increase")], outcome="regression",
               confidence="high", at="2026-01-01")
    c = record("C", changes=[change("lsd_acceleration", "40", "increase")],
               outcome="confirmed_improvement", confidence="low", at="2026-01-02")
    r = build_setup_outcome_learning(_fp(), [b, c])
    g = {(x["field"], x["direction"]): x["action"] for x in r.directional_guidance}
    assert g[("lsd_acceleration", "increase")] == DirectionAction.BLOCKED.value


def test_stronger_evidence_overturns_block():
    b = record("B", changes=[change("arb_rear", "6", "increase")], outcome="regression",
               confidence="low", at="2026-01-01")
    c = record("C", changes=[change("arb_rear", "6", "increase")], outcome="confirmed_improvement",
               confidence="high", at="2026-01-02")
    r = build_setup_outcome_learning(_fp(), [b, c])
    g = {(x["field"], x["direction"]): x["action"] for x in r.directional_guidance}
    assert g[("arb_rear", "increase")] == DirectionAction.REPEAT.value


def test_protected_knowledge_failed_direction_blocks():
    rec = record("A", changes=[change("toe_front", "1")], outcome="confirmed_improvement",
                 protected_knowledge=[{"kind": "never_move_direction", "field": "camber_rear",
                                       "direction": "increase", "confidence": "high"}])
    r = build_setup_outcome_learning(_fp(), [rec])
    assert ("camber_rear", "increase") in {(x["field"], x["direction"]) for x in r.blocked_directions}


# ---- 6. rollback selection ------------------------------------------------------------------ #
def test_rollback_target_is_prior_good_state():
    a = record("A", changes=[change("arb_rear", "6")], outcome="confirmed_improvement", at="2026-01-01")
    b = record("B", changes=[change("lsd_acceleration", "40")], outcome="regression", at="2026-01-02")
    r = build_setup_outcome_learning(_fp(), [a, b])
    assert r.rollback_plan["needed"] is True
    assert r.rollback_plan["target"] == "A"


def test_protected_behaviour_from_setup_a_preserved():
    a = record("A", changes=[change("arb_rear", "6")], outcome="confirmed_improvement",
               protected=[{"behaviour": "stable entry", "verdict": "kept", "confidence": "high"}])
    b = record("B", changes=[change("lsd_acceleration", "40")], outcome="regression")
    r = build_setup_outcome_learning(_fp(), [a, b])
    assert "stable entry" in {p["behaviour"] for p in r.protected_behaviours}


def test_successful_experiment_updates_window():
    a = record("A", changes=[change("arb_rear", "5")], outcome="confirmed_improvement", session="s1",
               windows=[{"field": "arb_rear", "min": "4", "max": "6", "confidence": "high",
                         "valid_experiment_count": 3}])
    ww = build_setup_working_windows(_fp(), "race", [a], [])
    w = {x["field"]: x for x in ww.windows}["arb_rear"]
    assert w["status"] == FieldStatus.PROTECT.value
    assert w["window_min"] == "4" and w["window_max"] == "6"


# ---- 7/8. working-window derivation + incompatible-history exclusion ------------------------- #
def test_avoid_status_on_regression_value():
    b = record("B", changes=[change("lsd_acceleration", "40")], outcome="regression")
    r = build_setup_outcome_learning(_fp(), [b])
    ww = build_setup_working_windows(_fp(), "race", [b], r.blocked_directions)
    w = {x["field"]: x for x in ww.windows}["lsd_acceleration"]
    assert w["status"] == FieldStatus.AVOID.value
    assert "40" in w["regression_values"]


def test_inconclusive_not_promoted_to_window():
    a = record("A", changes=[change("camber_front", "2")], outcome="insufficient_evidence")
    ww = build_setup_working_windows(_fp(), "race", [a], [])
    w = {x["field"]: x for x in ww.windows}["camber_front"]
    assert w["status"] in (FieldStatus.INSUFFICIENT.value, FieldStatus.EXPLORE.value)
    assert w["status"] != FieldStatus.PROTECT.value


def test_windows_not_averaged():
    # two proven values 4 and 8 -> window is the union [4,8], never the mean 6 as a single optimum.
    a = record("A", changes=[change("arb_rear", "4")], outcome="confirmed_improvement", at="2026-01-01")
    b = record("B", changes=[change("arb_rear", "8")], outcome="confirmed_improvement", at="2026-01-02")
    ww = build_setup_working_windows(_fp(), "race", [a, b], [])
    w = {x["field"]: x for x in ww.windows}["arb_rear"]
    assert set(w["proven_good_values"]) == {"4", "8"}
    assert w["window_min"] == "4.0" and w["window_max"] == "8.0"


# ---- 9. discipline-specific setup separation (property) ------------------------------------- #
def test_mature_window_not_overturned_by_one_noisy_record():
    # converged window (independent count 4, high) + one later low-confidence non-regression record.
    a = record("A", changes=[change("arb_rear", "5")], outcome="confirmed_improvement",
               windows=[{"field": "arb_rear", "min": "4", "max": "6", "confidence": "high",
                         "valid_experiment_count": 4}])
    noisy = record("N", changes=[change("arb_rear", "5")], outcome="no_change", confidence="low",
                   at="2026-02-01")
    ww = build_setup_working_windows(_fp(), "race", [a, noisy], [])
    w = {x["field"]: x for x in ww.windows}["arb_rear"]
    assert w["status"] == FieldStatus.PROTECT.value  # still protected; not invalidated by noise
