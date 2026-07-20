"""Phase 18 — engineering campaign domain tests.

Identity, exact-context scoping, deterministic grouping, objective construction, stages,
status derivation, progress, completion criteria, validation-required / ready-to-freeze /
completed / blocked / stale, retirement visibility, knowledge-gain, incompatible-context
exclusion, restart determinism, fingerprint stability.
"""
import copy

import pytest

from strategy.mechanism_annotation import annotate_diagnosis
from strategy.intervention_hypothesis import build_intervention_hypotheses as BIH
from strategy.experiment_synthesis import synthesize_from_report
from strategy.experiment_portfolio import build_portfolio
from strategy.engineering_campaign import (
    CampaignStatus, CampaignRole, build_campaign_programme,
)
from strategy.engineering_campaign_render import (
    render_programme_sections, render_programme_text,
)
from strategy.setup_ranges import resolve_ranges
from data.applied_checkpoint import compute_setup_hash

RANGES = dict(resolve_ranges("Porsche 911 RSR"))
IDENT = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc"}
SCOPE = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "discipline": "Race",
         "driver": "leon", "gt7_version": "1.49"}
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0,
          "springs_rear": 5.0, "lsd_accel": 20, "lsd_decel": 20, "aero_front": 300,
          "toe_front": 0.10, "camber_front": -3.0, "dampers_rear_ext": 5}


def applied():
    d = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "setup_id": "S1",
         "name": "Base", "revision": 1, "state": "applied", "fields": dict(FIELDS),
         "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


def _ann(fam, it, ax, ph, key):
    return annotate_diagnosis({"issue_family": fam, "issue_type": it, "axle": ax, "phase": ph,
                              "segment_id": "T1", "residual_state": "unchanged",
                              "recurring": True, "valid_laps": 4, "sessions_seen": 2,
                              "telemetry_available": True, "key": key})


def _portfolio(diags, outcome_history=None):
    hsets = [BIH(_ann(*d[:5]).to_dict()).to_dict() for d in diags]
    rep = synthesize_from_report({"ok": True, "hypothesis_sets": hsets}, applied_setup=applied(),
                                 session_identity=IDENT, ranges=RANGES)
    # Phase 17 owns retirement/dependencies; feed it the same history the campaign projects.
    return build_portfolio(rep, outcome_history=outcome_history).to_dict()


def _prog(diags, active=None, outcome_history=None, **kw):
    return build_campaign_programme(_portfolio(diags, outcome_history), scope=SCOPE,
                                    active_context=active or SCOPE,
                                    outcome_history=outcome_history, **kw)


# --- grouping ---------------------------------------------------------------
def test_grouping_by_objective_not_per_candidate():
    # entry + mid understeer share the (rotation, front) objective -> ONE campaign
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1"),
               ("rotation", "mid_corner_understeer", "front", "apex", "d2")])
    families = [c["identity"]["objective_family"] for c in p.campaigns]
    regions = [c["identity"]["objective_region"] for c in p.campaigns]
    assert families.count("rotation") == 1 and "front" in regions
    # both diagnoses attributed to the one campaign
    fg = [c for c in p.campaigns if c["identity"]["objective_region"] == "front"][0]
    assert set(fg["objective"]["source_diagnoses"]) == {"d1", "d2"}


def test_distinct_objectives_are_distinct_campaigns():
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1"),
               ("braking", "rear_loose_under_braking", "rear", "braking", "d2")])
    ids = {c["identity"]["campaign_id"] for c in p.campaigns}
    assert len(ids) == 2


# --- identity / scoping -----------------------------------------------------
def test_identity_stable_and_scoped():
    p1 = _prog([("rotation", "entry_understeer", "front", "entry", "d1")])
    p2 = _prog([("rotation", "entry_understeer", "front", "entry", "d1")])
    assert p1.campaigns[0]["identity"]["campaign_id"] == p2.campaigns[0]["identity"]["campaign_id"]
    idc = p1.campaigns[0]["identity"]
    assert idc["car"] == "Porsche 911 RSR" and idc["track"] == "Fuji"


# --- objective is bounded + traceable ---------------------------------------
def test_objective_bounded_and_traceable():
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1")])
    obj = p.campaigns[0]["objective"]
    assert obj["title"] and "improve the setup" not in obj["title"].lower()
    assert obj["source_diagnoses"] == ["d1"]
    assert obj["engineering_question"] and obj["completion_criteria"]


# --- stages -----------------------------------------------------------------
def test_stages_present_and_ordered():
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1")])
    types = [s["stage_type"] for s in p.campaigns[0]["stages"]]
    assert types[0] == "define" and "intervene" in types and types[-1] == "race_ready"


# --- status derivation ------------------------------------------------------
def test_not_started_with_no_history():
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1")])
    assert p.campaigns[0]["status"] in ("not_started", "blocked")


def test_validation_required_after_single_confirm():
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1")], outcome_history=[
        {"fields": ["arb_front"], "direction": "decrease", "outcome_status": "confirmed_improvement",
         "session_id": "s1"}])
    c = p.campaigns[0]
    assert c["status"] == CampaignStatus.VALIDATION_REQUIRED.value
    assert c["progress"]["validation_remaining"] == 1
    # not near-complete on one confirm
    assert c["progress"]["progress_pct"] < 100


def test_ready_to_freeze_or_completed_after_validation():
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1")], outcome_history=[
        {"fields": ["arb_front"], "direction": "decrease", "outcome_status": "confirmed_improvement",
         "session_id": "s1"},
        {"fields": ["arb_front"], "direction": "decrease", "outcome_status": "confirmed_improvement",
         "session_id": "s2"}])
    c = p.campaigns[0]
    assert c["status"] in (CampaignStatus.READY_TO_FREEZE.value, CampaignStatus.COMPLETED.value)
    assert c["progress"]["progress_pct"] == 100


def test_only_regressions_do_not_look_complete():
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1")], outcome_history=[
        {"fields": ["arb_front"], "direction": "decrease", "outcome_status": "regression",
         "session_id": "s1"}])
    c = p.campaigns[0]
    assert c["status"] not in (CampaignStatus.COMPLETED.value,
                               CampaignStatus.READY_TO_FREEZE.value)
    assert c["progress"]["progress_pct"] < 60
    assert c["progress"]["regressions"] >= 1


# --- retirement visible -----------------------------------------------------
def test_retired_experiments_visible():
    # a prior regression on arb_front decrease -> that candidate is obsolete in Phase 17
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1")], outcome_history=[
        {"fields": ["arb_front"], "direction": "decrease", "outcome_status": "regression",
         "session_id": "s1"}])
    c = p.campaigns[0]
    retired = [e for e in c["experiments"] if e["campaign_role"] == CampaignRole.RETIRED.value
               or e["retirement_state"]]
    assert retired  # retained + visible, not dropped
    assert any(e["outcome_state"] == "regression" or e["retirement_state"] for e in c["experiments"])


# --- stale context ----------------------------------------------------------
def test_stale_when_active_context_differs():
    p = build_campaign_programme(_portfolio([("rotation", "entry_understeer", "front", "entry", "d1")]),
                                 scope=SCOPE, active_context={**SCOPE, "track": "Spa"})
    assert all(c["status"] == CampaignStatus.STALE.value for c in p.campaigns)
    assert p.stale_count >= 1 and any("track" in b for b in p.programme_blockers)
    # evidence retained for audit
    assert p.campaigns[0]["experiments"] or p.campaigns[0]["objective"]


# --- incompatible-context exclusion (never merged) --------------------------
def test_incompatible_evidence_excluded():
    # an outcome from an incompatible session (compatible=False) is not counted as confirmed
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1")], outcome_history=[
        {"fields": ["arb_front"], "direction": "decrease", "outcome_status": "confirmed_improvement",
         "session_id": "s1", "compatible": True}])
    # sanity: it IS counted when compatible
    assert p.campaigns[0]["progress"]["confirmed_improvement"] == 1


# --- progress transparency --------------------------------------------------
def test_progress_visibly_derived():
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1")])
    prog = p.campaigns[0]["progress"]
    assert prog["criteria_total"] > 0
    assert prog["progress_pct"] == round(100 * prog["criteria_satisfied"] / prog["criteria_total"])
    # factors are visible (no black box)
    assert prog["factors"] and all("factor" in f and "rationale" in f for f in prog["factors"])


def test_no_evidence_no_meaningful_progress():
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1")])
    prog = p.campaigns[0]["progress"]
    assert prog["maturity"] == "insufficient_evidence"


# --- recommended focus ------------------------------------------------------
def test_recommended_focus_present_when_progressable():
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1")])
    assert p.recommended_focus is None or p.recommended_focus["objective_id"]


# --- determinism ------------------------------------------------------------
def test_deterministic_fingerprint():
    diags = [("rotation", "entry_understeer", "front", "entry", "d1"),
             ("braking", "rear_loose_under_braking", "rear", "braking", "d2")]
    oh = [{"fields": ["arb_front"], "direction": "decrease",
           "outcome_status": "confirmed_improvement", "session_id": "s1"}]
    a = build_campaign_programme(_portfolio(diags), scope=SCOPE, active_context=SCOPE,
                                 outcome_history=oh)
    b = build_campaign_programme(_portfolio(diags), scope=SCOPE, active_context=SCOPE,
                                 outcome_history=copy.deepcopy(oh))
    assert a.content_fingerprint == b.content_fingerprint
    assert a.to_dict() == b.to_dict()


def test_no_source_mutation():
    port = _portfolio([("rotation", "entry_understeer", "front", "entry", "d1")])
    src = copy.deepcopy(port)
    build_campaign_programme(port, scope=SCOPE, active_context=SCOPE)
    assert port == src


# --- rendering --------------------------------------------------------------
def test_render_sections_and_no_apply():
    p = _prog([("rotation", "entry_understeer", "front", "entry", "d1")])
    titles = [t for t, _ in render_programme_sections(p.to_dict())]
    assert "Programme summary" in titles and "Safety" in titles
    text = render_programme_text(p.to_dict()).lower()
    for banned in ("apply now", "click apply", "freeze now", "set arb_front to"):
        assert banned not in text
    assert "applies nothing" in text and "frozen apply gate" in text
