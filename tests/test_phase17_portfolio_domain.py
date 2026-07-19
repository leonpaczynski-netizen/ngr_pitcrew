"""Phase 17 — experiment portfolio domain tests.

Portfolio generation, ranking (engineering value / information-gain first, not lap time),
visible dimensions, dependency resolution, retirement, roadmap, ties, session awareness,
determinism, rendering.
"""
import copy

import pytest

from strategy.mechanism_annotation import annotate_diagnosis
from strategy.intervention_hypothesis import build_intervention_hypotheses as BIH
from strategy.experiment_synthesis import synthesize_from_report
from strategy.experiment_portfolio import (
    DIMENSION_WEIGHTS, PortfolioRole, SessionSuitability, build_portfolio,
)
from strategy.experiment_portfolio_render import (
    render_portfolio_sections, render_portfolio_text,
)
from strategy.setup_ranges import resolve_ranges
from data.applied_checkpoint import compute_setup_hash

RANGES = dict(resolve_ranges("Porsche 911 RSR"))
IDENT = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc"}
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0,
          "springs_rear": 5.0, "lsd_accel": 20, "aero_front": 300, "toe_front": 0.10,
          "camber_front": -3.0}


def applied():
    d = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "setup_id": "S1",
         "name": "Base", "revision": 1, "state": "applied", "fields": dict(FIELDS),
         "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


def _ann(it, axle, phase, key):
    return annotate_diagnosis({"issue_family": "rotation", "issue_type": it, "axle": axle,
                              "phase": phase, "segment_id": "T1", "residual_state": "unchanged",
                              "recurring": True, "valid_laps": 4, "sessions_seen": 2,
                              "telemetry_available": True, "key": key})


def _report(diags):
    hsets = [BIH(_ann(*d).to_dict()).to_dict() for d in diags]
    return synthesize_from_report({"ok": True, "hypothesis_sets": hsets},
                                  applied_setup=applied(), session_identity=IDENT, ranges=RANGES)


def _port(diags, **kw):
    return build_portfolio(_report(diags), **kw)


# --- generation + ranking ---------------------------------------------------
def test_portfolio_generates_and_ranks():
    p = _port([("entry_understeer", "front", "entry", "d1"),
               ("mid_corner_understeer", "front", "apex", "d2")],
              session_context={"practice_minutes_remaining": 30, "tyre_sets_available": 3})
    assert p.valuations
    # ranks are a stable 0..n-1 permutation
    assert sorted(v["rank"] for v in p.valuations) == list(range(len(p.valuations)))
    # highest-value (if any) is rank 0
    if p.highest_value:
        assert p.highest_value["rank"] == 0
        assert p.highest_value["role"] == PortfolioRole.HIGHEST_VALUE.value


def test_information_gain_is_primary_weight():
    assert DIMENSION_WEIGHTS["information_gain"] == max(DIMENSION_WEIGHTS.values())


def test_dimensions_individually_visible_no_black_box():
    p = _port([("entry_understeer", "front", "entry", "d1")],
              session_context={"practice_minutes_remaining": 30, "tyre_sets_available": 3})
    v = p.valuations[0]
    names = {d["name"] for d in v["dimensions"]}
    assert len(v["dimensions"]) == 13
    for req in ("information_gain", "mechanism_discrimination", "attribution_quality",
                "reversibility", "protection_of_confirmed_good", "session_suitability",
                "remaining_uncertainty", "prediction_calibration_benefit",
                "future_engineering_value"):
        assert req in names
    # weights exposed on the portfolio (transparent, not hidden)
    assert p.dimension_weights == DIMENSION_WEIGHTS
    # engineering value is the transparent weighted mean of the visible dimensions
    assert 0.0 <= v["engineering_value"] <= 1.0


def test_competing_discrimination_scores_higher_info_gain():
    # a competing-mechanism diagnosis (wheelspin) should score higher mechanism discrimination
    hs = BIH(annotate_diagnosis({"issue_family": "traction", "issue_type": "wheelspin",
                                 "axle": "rear", "phase": "exit", "segment_id": "T4",
                                 "residual_state": "unchanged", "recurring": True,
                                 "valid_laps": 4, "key": "dw"}).to_dict()).to_dict()
    rep = synthesize_from_report({"ok": True, "hypothesis_sets": [hs]}, applied_setup=applied(),
                                 session_identity=IDENT, ranges=RANGES)
    p = build_portfolio(rep, session_context={"practice_minutes_remaining": 30,
                                              "tyre_sets_available": 3})
    for v in p.valuations:
        md = next(d for d in v["dimensions"] if d["name"] == "mechanism_discrimination")
        assert md["score"] >= 0.5   # competing set present


# --- retirement -------------------------------------------------------------
def test_retirement_already_confirmed():
    p = _port([("entry_understeer", "front", "entry", "d1")],
              outcome_history=[{"fields": ["arb_front"], "direction": "decrease",
                                "outcome_status": "confirmed_improvement"}])
    obs = [v for v in p.valuations if v["role"] == PortfolioRole.OBSOLETE.value]
    assert any(v["field"] == "arb_front" for v in obs)
    assert all("confirmed" in v["retirement_reason"] for v in obs)


def test_retirement_already_rejected():
    p = _port([("entry_understeer", "front", "entry", "d1")],
              outcome_history=[{"fields": ["arb_front"], "direction": "decrease",
                                "outcome_status": "regression"}])
    obs = [v for v in p.valuations if v["role"] == PortfolioRole.OBSOLETE.value]
    assert any("rejected" in v["retirement_reason"] for v in obs)


# --- redundancy / supersession / dependencies -------------------------------
def test_redundant_same_field_direction_deduped():
    # two diagnoses that both soften front ARB -> one redundant, one kept
    p = _port([("entry_understeer", "front", "entry", "d1"),
               ("mid_corner_understeer", "front", "apex", "d2")])
    arb = [v for v in p.valuations if v["field"] == "arb_front" and v["direction"] == "soften"]
    assert len(arb) == 2
    roles = {v["role"] for v in arb}
    assert PortfolioRole.REDUNDANT.value in roles
    # a supersedes dependency is recorded
    assert any(d["kind"] == "supersedes" for d in p.dependencies)


def test_experiments_never_duplicated():
    p = _port([("entry_understeer", "front", "entry", "d1"),
               ("entry_understeer", "front", "entry", "d1b")])
    ids = [v["candidate_id"] for v in p.valuations]
    assert len(ids) == len(set(ids))


# --- roadmap ----------------------------------------------------------------
def test_roadmap_is_deterministic_sequence():
    p = _port([("entry_understeer", "front", "entry", "d1")],
              session_context={"practice_minutes_remaining": 30, "tyre_sets_available": 3})
    kinds = [s["kind"] for s in p.roadmap]
    assert kinds[:2] == ["experiment", "review"]
    assert "freeze" in kinds and kinds[-1] == "race"


# --- ties -------------------------------------------------------------------
def test_ties_not_auto_won():
    # two independent single-field candidates of identical value stay alternatives
    def cand(cid, field):
        return {"candidate_id": cid, "status": "ready_for_preflight",
                "attribution_scope": "single_field", "evidence_grade": "moderate",
                "protected_good_behaviours": [],
                "deltas": [{"field": field, "direction": "stiffen", "is_exactly_one_step": True,
                            "source_mechanism_id": "m"}], "content_fingerprint": cid}
    res = {"source_hypothesis_set": {"source_diagnosis_key": "d", "canonical_issue":
           {"issue_type": "oversteer"}, "competing": []},
           "selected_candidate": cand("c-a", "arb_rear"),
           "alternative_candidates": [cand("c-b", "springs_rear")], "overall_status":
           "ready_for_preflight"}
    p = build_portfolio({"ok": True, "synthesis_results": [res], "content_fingerprint": "fp"},
                        session_context={"practice_minutes_remaining": 30,
                                         "tyre_sets_available": 3})
    assert p.highest_value is None and len(p.alternatives) >= 2


# --- session awareness ------------------------------------------------------
def test_unknown_session_lowers_suitability():
    p = _port([("entry_understeer", "front", "entry", "d1")])
    assert p.session_suitability == SessionSuitability.UNKNOWN.value


def test_no_time_or_tyres_is_unsuitable():
    p = _port([("entry_understeer", "front", "entry", "d1")],
              session_context={"practice_minutes_remaining": 0, "tyre_sets_available": 3})
    assert p.session_suitability == SessionSuitability.UNSUITABLE.value


def test_session_context_never_invented():
    # an empty session context must NOT fabricate values; suitability = unknown
    p = _port([("entry_understeer", "front", "entry", "d1")], session_context={})
    assert p.session_suitability == "unknown"
    assert p.session_context == {}


# --- determinism ------------------------------------------------------------
def test_deterministic_fingerprint():
    diags = [("entry_understeer", "front", "entry", "d1"),
             ("wheelspin", "rear", "exit", "d2")]
    sc = {"practice_minutes_remaining": 30, "tyre_sets_available": 3}
    a = build_portfolio(_report(diags), session_context=sc)
    b = build_portfolio(_report(diags), session_context=copy.deepcopy(sc))
    assert a.content_fingerprint == b.content_fingerprint
    assert a.to_dict() == b.to_dict()


def test_reordering_irrelevant_history_no_change():
    diags = [("entry_understeer", "front", "entry", "d1")]
    base = build_portfolio(_report(diags))
    extra = build_portfolio(_report(diags), outcome_history=[
        {"fields": ["unrelated"], "direction": "increase", "outcome_status": "regression"}])
    assert base.content_fingerprint == extra.content_fingerprint


# --- no source mutation -----------------------------------------------------
def test_no_source_mutation():
    rep = _report([("entry_understeer", "front", "entry", "d1")])
    src = copy.deepcopy(rep)
    build_portfolio(rep, session_context={"practice_minutes_remaining": 30})
    assert rep == src


# --- rendering --------------------------------------------------------------
def test_render_shows_dimensions_roadmap_no_apply():
    p = _port([("entry_understeer", "front", "entry", "d1")],
              session_context={"practice_minutes_remaining": 30, "tyre_sets_available": 3})
    titles = [t for t, _ in render_portfolio_sections(p.to_dict())]
    assert "Highest-value next experiment" in titles
    assert any("dimensions" in t.lower() for t in titles)
    assert any("roadmap" in t.lower() for t in titles)
    text = render_portfolio_text(p.to_dict()).lower()
    assert "information gain first" in text and "not lap time" in text
    for banned in ("apply now", "click apply", "fastest setup", "optimal setup"):
        assert banned not in text
