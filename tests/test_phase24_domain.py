"""Phase 24 — engineering-playbook domain tests.

Deterministic theme construction (grounded, not keyword-only), recurrence counts, confirmed-good
extraction, failed-direction preservation, contradiction handling, boundary creation, unknown-
attribute handling, fingerprint stability (no timestamps), stable ordering, empty/single safety.
"""
import inspect

import pytest

from strategy.engineering_playbook import build_engineering_playbook, ENGINEERING_PLAYBOOK_VERSION
from strategy.stable_themes import build_stable_themes
from strategy.investigation_priority import (
    classify_priorities, InvestigationCategory, CATEGORY_PRIORITY,
)
from strategy.knowledge_boundary import build_boundaries, BoundaryType
from strategy.new_programme_brief import build_briefs

SRC = {"car": "Porsche 911 RSR (991) '17", "discipline": "Race", "gt7_version": "1.49",
       "driver": "leon"}
CUP = {"car": "Porsche 911 GT3 Cup", "discipline": "Race", "gt7_version": "1.49", "driver": "leon"}
TOY = {"car": "Toyota GR Supra Racing Concept Gr.3", "discipline": "Race", "gt7_version": "1.49",
       "driver": "leon", "manufacturer": "toyota", "drivetrain": "unknown", "layout": "unknown",
       "category": "gr3"}


def rec(domain, established=True, confirmed_good=False, maturity="mature", confidence="high",
        confirmations=2, regressions=0, conflicting=False, mechs=("load_transfer",),
        dcls="architecture_dependent", transfers=None, unc="low"):
    return {"domain": domain, "mechanisms": list(mechs), "maturity": maturity,
            "confidence": confidence, "knowledge_state": "well_understood",
            "remaining_uncertainty": unc, "confirmations": confirmations,
            "regressions": regressions, "executed": confirmations + regressions,
            "conflicting": conflicting, "supporting_campaigns": ["c1"],
            "known_limitations": (["conflicting evidence present"] if conflicting else []),
            "established": established, "confirmed_good": confirmed_good,
            "domain_transfer_class": dcls, "source_programme": dict(SRC),
            "transfers": transfers or []}


def _transfer(tgt, level, rules=(), dcls="architecture_dependent"):
    return {"target": dict(tgt), "transfer_level": level, "reason": "r",
            "limitations": [], "rules_satisfied": list(rules), "domain_transfer_class": dcls}


# --- stable themes ----------------------------------------------------------
def test_theme_only_for_established():
    recs = [rec("differential", established=True), rec("springs", established=False)]
    themes = build_stable_themes(recs, SRC)
    assert [t["engineering_domain"] for t in themes] == ["differential"]


def test_recurrence_counts_source_plus_reusable_targets():
    r = rec("differential", transfers=[
        _transfer(CUP, "supported", ["same_manufacturer", "same_drivetrain", "same_race_category"]),
        _transfer(TOY, "low", ["same_race_category"])])
    themes = build_stable_themes([r], SRC)
    # 1 source + 1 reusable target (CUP supported; TOY low is not reusable)
    assert themes[0]["recurrence_count"] == 2
    assert len(themes[0]["compatible_target_programmes"]) == 1


def test_theme_is_grounded_not_keyword():
    # two records with the SAME mechanism word but different domains -> two distinct themes,
    # never merged into one by word matching.
    recs = [rec("differential", mechs=("load_transfer",)),
            rec("weight_transfer", dcls="handling_drivetrain", mechs=("load_transfer",))]
    themes = build_stable_themes(recs, SRC)
    assert {t["engineering_domain"] for t in themes} == {"differential", "weight_transfer"}
    assert themes[0]["theme_id"] != themes[1]["theme_id"]


def test_confirmed_good_protection_extracted():
    r = rec("differential", confirmed_good=True)
    themes = build_stable_themes([r], SRC)
    assert themes[0]["confirmed_good_protections"]


def test_failed_direction_preserved():
    r = rec("springs", regressions=1, confirmations=1)
    themes = build_stable_themes([r], SRC)
    assert any("harmful" in n for n in themes[0]["known_negative_outcomes"])


def test_contradiction_reduces_not_averages():
    r = rec("springs", conflicting=True, confirmations=1, regressions=1)
    themes = build_stable_themes([r], SRC)
    assert any("conflicting" in n.lower() for n in themes[0]["known_negative_outcomes"])


def test_theme_carries_no_setup_values():
    r = rec("differential", transfers=[_transfer(CUP, "supported")])
    blob = str(build_stable_themes([r], SRC)).lower()
    # no numeric setup value assignment patterns
    for banned in ("arb_front=", "lsd_accel=", "set to ", "=20", "=25", "start with 5"):
        assert banned not in blob


# --- investigation priority -------------------------------------------------
def test_priority_protect_first_for_confirmed_good():
    p = classify_priorities([rec("differential", confirmed_good=True)])
    assert p[0]["category"] == InvestigationCategory.PROTECT_FIRST.value


def test_priority_do_not_reuse_for_pure_regression():
    p = classify_priorities([rec("springs", confirmed_good=False, confirmations=0, regressions=2)])
    assert p[0]["category"] == InvestigationCategory.DO_NOT_REUSE.value


def test_priority_recollect_for_conflict():
    p = classify_priorities([rec("springs", conflicting=True, confirmations=1, regressions=1)])
    assert p[0]["category"] == InvestigationCategory.RECOLLECT_EVIDENCE.value


def test_priority_investigate_for_unestablished():
    p = classify_priorities([rec("dampers", established=False, confirmations=0)])
    assert p[0]["category"] == InvestigationCategory.INVESTIGATE.value


def test_priority_dimensions_and_weights_visible():
    p = classify_priorities([rec("differential", transfers=[_transfer(CUP, "supported")])])[0]
    assert p["dimensions"] and p["weights"]
    for k in ("recurrence_across_programmes", "masking_risk_of_confirmed_good",
              "known_negative_outcomes", "version_compatibility"):
        assert k in p["weights"]


def test_masking_conflict_marked():
    # confirmed-good domain that also has a harmful direction -> protect + mark masking
    p = classify_priorities([rec("differential", confirmed_good=True, regressions=1)])[0]
    assert p["masking_conflict"] is True


# --- boundaries -------------------------------------------------------------
def test_boundary_gearbox_car_specific():
    b = build_boundaries([rec("gearbox", dcls="car_track_specific")])
    assert any(x["boundary_type"] == BoundaryType.CAR_SPECIFIC.value for x in b)


def test_boundary_unknown_attribute():
    r = rec("differential", transfers=[_transfer(TOY, "low", ["same_race_category"])])
    b = build_boundaries([r])
    assert any(x["boundary_type"] == BoundaryType.UNKNOWN_VEHICLE_ATTRIBUTE.value for x in b)


def test_boundary_insufficient_evidence():
    b = build_boundaries([rec("dampers", established=False)])
    assert any(x["boundary_type"] == BoundaryType.INSUFFICIENT_EVIDENCE.value for x in b)


def test_boundary_conflicting_and_failed():
    b = build_boundaries([rec("springs", conflicting=True, regressions=1, confirmations=1)])
    types = {x["boundary_type"] for x in b}
    assert BoundaryType.CONFLICTING_EVIDENCE.value in types
    assert BoundaryType.FAILED_HISTORICAL_OUTCOME.value in types


def test_boundary_proxy_labelled():
    r = rec("springs", transfers=[_transfer(CUP, "supported",
            ["same_manufacturer", "same_race_category", "same_suspension_architecture"])])
    b = build_boundaries([r])
    assert any(x["boundary_type"] == BoundaryType.UNVERIFIED_TRANSFER_PROXY.value for x in b)


# --- briefs -----------------------------------------------------------------
def test_brief_states_no_setup_transfer():
    r = rec("differential", transfers=[_transfer(CUP, "supported")])
    briefs = build_briefs([r], SRC, [CUP], [])
    assert briefs[0]["no_setup_statement"]
    assert "No setup values" in briefs[0]["no_setup_statement"]


def test_brief_reuse_only_hypothesis():
    r = rec("differential", transfers=[_transfer(CUP, "supported")])
    briefs = build_briefs([r], SRC, [CUP], [])
    reuse = briefs[0]["eligible_for_cautious_reuse"]
    assert reuse and "hypothesis" in reuse[0]["note"].lower()


# --- playbook fingerprint / ordering ---------------------------------------
def _programme_transfer():
    programme = {"content_fingerprint": "p22", "knowledge_graph": {
        "domains": [
            {"domain": "differential", "knowledge_state": {"value": "well_understood"},
             "confidence": {"value": "very_high"}, "maturity": {"value": "complete"},
             "remaining_uncertainty": {"value": "none"},
             "supporting_campaigns": ["c1"], "supporting_experiments": [],
             "supporting_mechanisms": ["load_transfer"],
             "supporting_evidence": {"confirmations": 2, "regressions": 0, "executed": 2},
             "known_limitations": []}],
        "known_domains": ["differential"], "missing_domains": ["springs"]},
        "compatibility": {"primary_key": SRC, "other_groups": [{"compatibility_key": CUP}]}}
    transfer = {"content_fingerprint": "p23", "candidates": [
        {"engineering_domain": "differential", "target_context": {**CUP, "manufacturer": "porsche",
         "drivetrain": "rr", "layout": "rear_engine", "category": "gr3"},
         "transfer_level": "supported", "reason": "r",
         "supporting_evidence": {"domain_transfer_class": "architecture_dependent"},
         "supporting_campaigns": ["c1"], "supporting_mechanisms": ["load_transfer"],
         "confidence": {"value": "very_high"}, "limitations": [],
         "rules_satisfied": ["same_manufacturer", "same_drivetrain", "same_race_category",
                             "compatible_gt7_version"]}]}
    return programme, transfer


def test_playbook_deterministic_fingerprint():
    prog, tr = _programme_transfer()
    a = build_engineering_playbook(prog, tr).to_dict()
    b = build_engineering_playbook(prog, tr).to_dict()
    assert a["content_fingerprint"] == b["content_fingerprint"]


def test_playbook_fingerprint_has_no_timestamp():
    src = inspect.getsource(__import__("strategy.engineering_playbook", fromlist=["x"]))
    assert "_fp(" in src
    for banned in ("time.time", "datetime.now", "utcnow", "date.today", "recorded_at",
                   "created_at", "now_date"):
        assert banned not in src


def test_playbook_empty_safe():
    pb = build_engineering_playbook({}, {}).to_dict()
    assert pb["stable_themes"] == [] and pb["safety_statement"]


def test_playbook_single_context_no_targets():
    prog, tr = _programme_transfer()
    prog["compatibility"]["other_groups"] = []
    pb = build_engineering_playbook(prog, {"candidates": []}).to_dict()
    assert pb["new_programme_briefs"] == []


def test_playbook_never_raises_on_garbage():
    for junk in (None, {"knowledge_graph": None}, {"knowledge_graph": {"domains": [None]}}):
        pb = build_engineering_playbook(junk, junk)
        assert pb.safety_statement


def test_priority_ordering_stable():
    prog, tr = _programme_transfer()
    a = build_engineering_playbook(prog, tr).to_dict()["investigation_priorities"]
    b = build_engineering_playbook(prog, tr).to_dict()["investigation_priorities"]
    assert [p["domain"] for p in a] == [p["domain"] for p in b]
    # protect_first sorts before investigate
    cats = [p["category"] for p in a]
    order = [CATEGORY_PRIORITY.get(c, 99) for c in cats]
    assert order == sorted(order)


def test_version_string():
    assert ENGINEERING_PLAYBOOK_VERSION == "engineering_playbook_v1"
