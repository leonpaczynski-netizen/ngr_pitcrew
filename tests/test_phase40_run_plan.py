"""Phase 40 — candidate selection, controlled run-plan generation, held-constant, discipline rules."""
from strategy.run_candidate_selection import select_run_candidate
from strategy.engineering_run_plan import build_engineering_run_plan, CausalConfidence


_SCOPE = {"driver": "Leon", "car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc",
          "event_id": "E1", "discipline": "race", "compound": "RH", "context_fingerprint": "cfp:x"}
_APPLIED = {"name": "B-Race", "fields": {"arb_rear": "6", "lsd_acceleration": "20", "camber_front": "2"}}


def _cand(cid="c1", scope="single_field", value=0.8, **kw):
    d = {"candidate_id": cid, "field": kw.get("field", "lsd_initial"),
         "direction": kw.get("direction", "increase"), "attribution_scope": scope,
         "engineering_value": value, "expected_learning": "reduce exit wheelspin", "rank": 1}
    d.update(kw)
    return d


# ---- 10. candidate selection ---------------------------------------------------------------- #
def test_selects_highest_value_single_field():
    sel = select_run_candidate([_cand("low", value=0.4), _cand("hi", value=0.9)])
    assert sel.posture == "experiment" and sel.selected["id"] == "hi"


def test_rejects_candidate_risking_protected_good():
    sel = select_run_candidate([_cand("risky", protected_good_at_risk=["arb_rear"])],
                               protected_behaviours=[{"field": "arb_rear"}])
    assert sel.selected is None and sel.posture == "collect"


def test_deadline_pressure_declines_high_interaction():
    sel = select_run_candidate([_cand("coupled", scope="coupled", value=0.9)],
                               event_is_near=True, available_practice_laps=4)
    assert sel.selected is None and sel.posture == "protect"


def test_retired_candidate_excluded():
    sel = select_run_candidate([_cand("old", retirement_reason="superseded"),
                                _cand("live", value=0.5)])
    assert sel.selected["id"] == "live"


# ---- 11/12. controlled run-plan + held-constant --------------------------------------------- #
def test_single_field_plan_holds_all_other_fields():
    plan = build_engineering_run_plan(_SCOPE, candidate=_cand(), applied_setup=_APPLIED,
                                      parent_setup={"name": "A"})
    assert plan.controlled_change["causal_confidence"] == CausalConfidence.SINGLE_MECHANISM.value
    assert set(plan.held_constant["setup_fields_held"]) == {"arb_rear", "lsd_acceleration",
                                                            "camber_front"}


def test_bundle_reduces_causal_confidence():
    cand = {"candidate_id": "c2", "attribution_scope": "coupled",
            "changes": [{"field": "ride_height_rear", "direction": "decrease"},
                        {"field": "natural_frequency_rear", "direction": "increase"}]}
    plan = build_engineering_run_plan(_SCOPE, candidate=cand, applied_setup=_APPLIED)
    assert plan.controlled_change["is_bundle"] is True
    assert plan.controlled_change["causal_confidence"] == CausalConfidence.COUPLED_BUNDLE.value


def test_validity_gate_includes_discipline_and_compound():
    plan = build_engineering_run_plan(_SCOPE, candidate=_cand(), applied_setup=_APPLIED)
    gate = " ".join(plan.validity_gate).lower()
    assert "compound" in gate and "qualifying run does not validate a race setup" in gate


# ---- 18. qualifying/race separation --------------------------------------------------------- #
def test_qualifying_and_race_objectives_distinct():
    race = build_engineering_run_plan({**_SCOPE, "discipline": "race"}, candidate=_cand(),
                                      applied_setup=_APPLIED).objective
    quali = build_engineering_run_plan({**_SCOPE, "discipline": "qualifying"}, candidate=_cand(),
                                       applied_setup=_APPLIED).objective
    assert "total race time" in " ".join(race["optimise"]).lower()
    assert "one-lap" in " ".join(quali["optimise"]).lower()
    assert race["primary_goal"] != quali["primary_goal"]


# ---- empty / deadline posture --------------------------------------------------------------- #
def test_no_candidate_is_collection_run():
    plan = build_engineering_run_plan(_SCOPE, candidate=None, applied_setup=_APPLIED)
    assert plan.empty_state and plan.candidate_link["is_existing"] is False
    assert plan.controlled_change["causal_confidence"] == CausalConfidence.NONE.value


def test_deadline_posture_set_when_near_and_short():
    plan = build_engineering_run_plan(_SCOPE, candidate={"candidate_id": "c", "field": "x",
                                                         "interaction_risk": "high"},
                                      applied_setup=_APPLIED, available_practice_laps=4,
                                      event_is_near=True)
    assert plan.deadline_posture


# ---- determinism ---------------------------------------------------------------------------- #
def test_run_plan_deterministic():
    a = build_engineering_run_plan(_SCOPE, candidate=_cand(), applied_setup=_APPLIED,
                                   parent_setup={"name": "A"}).content_fingerprint
    b = build_engineering_run_plan(_SCOPE, candidate=_cand(), applied_setup=_APPLIED,
                                   parent_setup={"name": "A"}).content_fingerprint
    assert a == b


def test_changed_applied_setup_alters_plan_fingerprint():
    a = build_engineering_run_plan(_SCOPE, candidate=_cand(), applied_setup=_APPLIED).content_fingerprint
    b = build_engineering_run_plan({**_SCOPE, "context_fingerprint": "cfp:y"}, candidate=_cand(),
                                   applied_setup=_APPLIED).content_fingerprint
    assert a != b
