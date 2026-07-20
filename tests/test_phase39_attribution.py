"""Phase 39 — regression bundle/field attribution, setup independence, production validation."""
from strategy.regression_attribution import build_regression_attribution
from strategy.setup_independence import assess_setup_independence, attribute_issue, SetupIndependenceLevel
from strategy.production_history_validation import validate_production_history
from strategy.engineering_context_scope import build_engineering_context_scope
from tests._race_engineer_helpers import ctx, record, change


def _rec(k, changes, out="regression", at="2026-01-01", sess="s1"):
    return {"record_key": k, "context": ctx(), "changes": changes, "outcome_status": out,
            "confidence_level": "high", "test_session_id": sess, "recorded_at": at, "experiment_id": k}


# ---- 5. regression bundle attribution ------------------------------------------------------- #
def test_multi_field_bundle_blocks_bundle_fields_suspect():
    r = build_regression_attribution([_rec("B", [change("lsd_acceleration"), change("ride_height_rear")])])
    assert r.bundles[0]["state"] == "bundle_regression_confirmed"
    assert {f["state"] for f in r.field_attributions} == {"field_direction_suspect"}
    assert r.confirmed_field_directions == ()


def test_multi_field_regression_cannot_prove_every_field_causal():
    r = build_regression_attribution([_rec("B", [change("a"), change("b"), change("c")])])
    assert all(f["state"] == "field_direction_suspect" for f in r.field_attributions)


# ---- 6. individual field causal confirmation ------------------------------------------------ #
def test_single_field_regression_confirmed():
    r = build_regression_attribution([_rec("S", [change("lsd_acceleration", direction="increase")])])
    assert r.field_attributions[0]["state"] == "field_direction_confirmed"


def test_reversal_evidence_confirms_direction():
    recs = [_rec("B", [change("arb_rear", direction="increase"), change("toe_front")]),
            _rec("R", [change("arb_rear", direction="decrease")], out="confirmed_improvement",
                 at="2026-01-02", sess="s2")]
    r = build_regression_attribution(recs)
    arb = [f for f in r.field_attributions if f["field"] == "arb_rear"][0]
    assert arb["state"] == "field_direction_confirmed"
    assert "valid_reversal_evidence" in arb["corroboration"]


def test_coupled_bundle_repeated_is_interaction_suspected():
    recs = [_rec("B1", [change("ride_height_rear"), change("natural_frequency_rear")], sess="s1"),
            _rec("B2", [change("ride_height_rear"), change("natural_frequency_rear")], sess="s2",
                 at="2026-01-02")]
    r = build_regression_attribution(recs)
    assert any(b["state"] == "interaction_suspected" for b in r.bundles)


# ---- 7/8. setup independence + driver/setup attribution ------------------------------------- #
def test_irrelevant_variation_not_independent():
    a = assess_setup_independence([change("brake_balance")],
                                  [change("brake_balance"), change("toe_rear")], "exit_wheelspin")
    assert a.level == SetupIndependenceLevel.IRRELEVANT_VARIATION.value


def test_relevant_variation_independent():
    a = assess_setup_independence([change("lsd_initial")], [change("gear_ratio")], "exit_wheelspin")
    assert a.level == SetupIndependenceLevel.INDEPENDENT.value


def test_persistence_across_non_independent_setups_is_not_driver():
    occ = [{"changes": [change("brake_balance")], "corner": "T2", "session": "s1", "driver_input": True},
           {"changes": [change("brake_balance"), change("toe_front")], "corner": "T2", "session": "s2",
            "driver_input": True}]
    assert attribute_issue("exit_wheelspin", occ).attribution == "interaction_unresolved"


def test_independent_setups_with_driver_input_is_technique():
    occ = [{"changes": [change("lsd_initial")], "corner": "T2", "session": "s1", "driver_input": True},
           {"changes": [change("gear_ratio")], "corner": "T3", "session": "s2", "driver_input": True}]
    assert attribute_issue("exit_wheelspin", occ).attribution == "driver_technique_likely"


# ---- 9. production-history validation -------------------------------------------------------- #
def test_production_validation_flags_and_no_repair():
    from tests._race_engineer_helpers import scope as _scope
    s = _scope()   # matches the helper's default ctx() (Fuji / full_course / RH)
    recs = [record("A", changes=[change("arb_rear")], outcome="confirmed_improvement",
                   context=ctx()),
            record("B", changes=[change("lsd_acceleration"), change("ride_height_rear")],
                   outcome="regression", context=ctx(), regressions=[{"issue_type": "x"}]),
            {"record_key": "C", "context": {"car": "P"}, "changes": []}]
    v = validate_production_history(s, recs).to_dict()
    assert v["performed_repair"] is False
    assert "C" in v["orphan_setup_references"]
    assert v["ambiguous_multi_field_regressions"]
    assert v["unsafe_attribution"]
