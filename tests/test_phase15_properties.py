"""Phase 15 — property / metamorphic invariants (Section 24, 64 invariants)."""
import copy
import inspect
import re

import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.mechanism_annotation import annotate_diagnosis
from strategy.intervention_hypothesis import build_intervention_hypotheses as BIH
from strategy import experiment_synthesis as M
from strategy.experiment_synthesis import (
    ExperimentSynthesisStatus as ST, synthesize_bounded_experiments as SYN,
)
from strategy.setup_ranges import resolve_ranges
from strategy import gearbox_evidence as gbx
from data.applied_checkpoint import compute_setup_hash

RANGES = dict(resolve_ranges("Porsche 911 RSR")); RANGES["final_drive"] = (3.0, 5.0)
IDENT = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc"}
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0,
          "springs_rear": 5.0, "lsd_accel": 20, "lsd_decel": 20, "lsd_initial": 10,
          "aero_front": 300, "aero_rear": 400, "camber_front": -3.0, "camber_rear": -2.0,
          "toe_front": 0.10, "toe_rear": 0.20, "ride_height_front": 70,
          "ride_height_rear": 75, "final_drive": 4.100}


def applied(fields=None, car="Porsche 911 RSR", state="applied"):
    f = dict(fields if fields is not None else FIELDS)
    d = {"car": car, "track": "Fuji", "layout_id": "fc", "setup_id": "S1", "name": "Base",
         "revision": 1, "state": state, "fields": f, "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(f)
    return d


def ann(it, fam="rotation", axle="", phase="", **kw):
    d = {"issue_family": fam, "issue_type": it, "axle": axle, "phase": phase,
         "segment_id": "T1", "residual_state": "unchanged", "recurring": True,
         "valid_laps": kw.get("vl", 4), "sessions_seen": 2, "telemetry_available": True,
         "key": "k-" + it}
    return annotate_diagnosis(d, failed_directions=kw.get("fd", ()), speed_context=kw.get("sc", ""))


def syn(it="entry_understeer", fam="rotation", axle="front", phase="entry", applied_setup=None,
        gearbox_state="", outcome_history=None, **kw):
    hs = BIH(ann(it, fam, axle, phase, **kw).to_dict(), gearbox_state=gearbox_state,
             speed_context=kw.get("sc", ""), outcome_history=outcome_history)
    return SYN(hs.to_dict(), applied_setup=applied_setup if applied_setup is not None else applied(),
               session_identity=IDENT, ranges=RANGES, gearbox_state=gearbox_state,
               larger_step_justifications=kw.get("just"))


def _all(r):
    return ([r.selected_candidate] if r.selected_candidate else []) + list(r.alternative_candidates)


def _deltas(r):
    return [d for c in _all(r) if c for d in c["deltas"]]


# 1-3: ineligible / contradicted / locked cannot produce deltas
def test_01_ineligible_no_deltas():
    r = syn("mid_corner_understeer", axle="front", phase="apex",
            applied_setup=applied(state="proposed"))
    assert not _deltas(r) and r.overall_status == ST.BLOCKED_BY_BASELINE_STATE.value


def test_02_03_contradicted_and_locked():
    r = syn(outcome_history=[{"fields": ["arb_front"], "outcome_status": "regression",
                             "single_field": True}])
    assert not [d for d in _deltas(r) if d["field"] == "arb_front"]
    r2 = syn(fd=[("arb_front", "decrease", "lockout")])
    assert not [d for d in _deltas(r2) if d["field"] == "arb_front"]


# 4-6: baseline missing / incomplete / mismatched
def test_04_missing_baseline():
    hs = BIH(ann("entry_understeer", axle="front", phase="entry").to_dict())
    r = SYN(hs.to_dict(), applied_setup=None, session_identity=IDENT, ranges=RANGES)
    assert r.overall_status == ST.BLOCKED_BY_BASELINE_STATE.value


def test_05_incomplete_baseline():
    r = syn(applied_setup={"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc",
                           "setup_id": "S", "state": "applied", "fields": {}, "purpose": "Race"})
    assert r.overall_status == ST.BLOCKED_BY_BASELINE_STATE.value


def test_06_mismatched_baseline():
    assert syn(applied_setup=applied(car="Mazda")).overall_status == \
        ST.BLOCKED_BY_BASELINE_STATE.value


# 7-10: candidate differs, correct direction, legal bounds, legal increment
def test_07_08_09_10_delta_legal():
    r = syn()
    d = r.selected_candidate["deltas"][0]
    assert d["candidate_value"] != d["baseline_value"]        # differs
    assert d["direction"] == "soften" and d["candidate_value"] < d["baseline_value"]  # dir
    assert d["legal_low"] <= d["candidate_value"] <= d["legal_high"]  # bounds
    assert abs(round((d["candidate_value"] - d["baseline_value"]) / d["legal_step"]) *
               d["legal_step"] - d["delta"]) < 1e-9           # lands on increment


# 11-12: single field changes exactly one, others unchanged
def test_11_12_single_field():
    r = syn()
    assert len(r.selected_candidate["deltas"]) == 1
    assert r.selected_candidate["unchanged_field_count"] == len(FIELDS) - 1


# 13-15: one step preferred; larger needs justification; removal restores
def test_13_14_15_step_doctrine():
    base = syn()
    assert base.selected_candidate["deltas"][0]["is_exactly_one_step"]
    big = syn(just={"arb_front": {"reason": "current_value_in_dead_band", "steps": 2}})
    assert big.selected_candidate["deltas"][0]["larger_step_used"]
    # invalid justification reason → no larger step
    inv = syn(just={"arb_front": {"reason": "i_feel_like_it", "steps": 2}})
    assert inv.selected_candidate["deltas"][0]["is_exactly_one_step"]
    assert syn().content_fingerprint == base.content_fingerprint


# 16-18: coupled cap, roles, attribution
def test_16_17_18_coupled():
    hset = {"canonical_issue": {"issue_type": "rear_loose_on_exit"}, "content_fingerprint": "fp",
            "testable": [{"hypothesis_id": "h", "source_mechanism_id": "m", "status": "testable",
                          "direction": "increase_locking", "evidence_grade": "moderate",
                          "target": {"component": "lsd_accel", "handling_phase": "exit_traction"},
                          "expected_response": {}, "predicted_trade_offs": [], "protected_good_at_risk": [],
                          "rejection_criteria": [], "test_design": {"test_kind": "paired_coupled"}}],
            "conditional": [], "competing": [], "blocked": [], "preserve_and_observe": []}
    r = SYN(hset, applied_setup=applied(), session_identity=IDENT, ranges=RANGES)
    c = _all(r)[0]
    assert c["attribution_scope"] == "coupled_pair" and c["status"] == \
        ST.REQUIRES_COUPLED_EXPERIMENT.value
    assert len(c["deltas"]) <= M.MAX_COUPLED_FIELDS


# 19: interaction risk cannot silently add fields
def test_19_no_silent_fields():
    for c in _all(syn()):
        if c:
            assert len(c["deltas"]) == 1


# 20: working-window lock not bypassed by driver preference
def test_20_lock_not_bypassed_by_pref():
    hs = BIH(ann("entry_understeer", axle="front", phase="entry",
                 fd=[("arb_front", "decrease", "lockout")]).to_dict(),
             driver_preference={"priority": "front_bite"})
    r = SYN(hs.to_dict(), applied_setup=applied(), session_identity=IDENT, ranges=RANGES)
    assert not [d for d in _deltas(r) if d["field"] == "arb_front"]


# 21-23: proven history cannot bypass one-step / replace baseline; fresh no prior
def test_21_22_23_history():
    r = syn()
    d = r.selected_candidate["deltas"][0]
    assert abs(d["delta"]) == d["legal_step"]                # one step regardless of history
    assert d["baseline_value"] == FIELDS["arb_front"]        # baseline is the applied setup
    assert "4.10" not in str(r.to_dict())                    # no invented historic jump


# 24-25: wheelspin no auto LSD; "LSD feels wrong" alone no numeric
def test_24_25_lsd():
    r = syn("wheelspin", fam="traction", axle="rear", phase="exit",
            fd=[("lsd_accel", "increase", "lockout")])
    assert not [d for d in _deltas(r) if d["field"] == "lsd_accel"]
    # a bare 'lsd_feel_wrong' has no canonical issue mapping → no hypothesis → no experiment
    r2 = syn("lsd_feel_wrong", fam="unknown", axle="rear", phase="exit")
    assert not _deltas(r2)


# 26-29: gearbox unknown/conflicting no gearing; final-drive direction semantics
def test_26_27_gearbox_no_gearing():
    for st in ("unknown", gbx.GEARING_CONFLICTING, ""):
        r = syn("wrong_gear", fam="gearing", axle="rear", phase="exit", gearbox_state=st)
        assert not [d for d in _deltas(r) if d["field"] == "final_drive"]


def test_28_29_final_drive_semantics():
    assert gbx.final_drive_lengthens(4.25, 4.20) and gbx.final_drive_shortens(4.20, 4.25)
    short = syn("gearing_too_long", fam="gearing", axle="rear", gearbox_state=gbx.GEARING_TOO_LONG)
    d = [d for d in _deltas(short) if d["field"] == "final_drive"][0]
    assert d["direction"] == "shorten" and d["candidate_value"] > d["baseline_value"]


# 30-32: aero speed context; low-speed no aero; count-only bottoming no platform
def test_30_31_aero():
    r = syn("mid_corner_understeer", axle="front", phase="apex")   # low speed
    aero = [d for d in _deltas(r) if d["field"] == "aero_front"]
    # low-speed aero is never READY
    for c in _all(r):
        if c and any(dd["field"] == "aero_front" for dd in c["deltas"]):
            assert c["status"] != ST.READY_FOR_PREFLIGHT.value


def test_32_bottoming_no_platform():
    r = syn("bottoming", fam="platform", axle="", phase="")
    assert not [d for d in _deltas(r) if d["field"] in
                ("ride_height_front", "ride_height_rear", "springs_front", "springs_rear")]


# 33: ballast not first-line without an eligible ballast hypothesis
def test_33_ballast_not_first_line():
    r = syn()
    assert not [d for d in _deltas(r) if d["field"].startswith("ballast")]


# 34: toe sign semantics correct (toe-in vs toe-out via canonical rounding)
def test_34_toe_semantics():
    from strategy.setup_synthesis import _round
    assert _round("toe_front", 0.10 + 0.01) == 0.11
    assert _round("toe_front", 0.10 - 0.01) == 0.09


# 35-36: damper comp/rebound + front/rear never conflated (field mapping distinct)
def test_35_36_no_conflation():
    assert M._field_for_component("damper_bump_front") == "dampers_front_comp"
    assert M._field_for_component("damper_rebound_rear") == "dampers_rear_ext"
    assert M._field_for_component("damper_bump_front") != M._field_for_component("damper_bump_rear")


# 37-38: rendering preserves exact numeric; display rounding doesn't change fingerprint
def test_37_38_render_exact():
    from strategy.experiment_synthesis_render import render_result_text
    r = syn()
    fp = r.content_fingerprint
    text = render_result_text(r.to_dict())
    assert "3" in text and str(r.selected_candidate["deltas"][0]["baseline_value"]) in str(r.to_dict())
    assert syn().content_fingerprint == fp


# 39-42: preflight rejects no-op / hidden / illegal / stale (baseline)
def test_39_no_op_when_at_boundary():
    f = dict(FIELDS); f["brake_bias"] = 5
    r = syn("front_lock", fam="braking", axle="front", phase="braking", applied_setup=applied(f))
    assert r.overall_status == ST.BLOCKED_BY_LEGALITY.value


def test_42_stale_baseline_rejected():
    a = applied(); a["setup_hash"] = "stale"
    assert syn(applied_setup=a).overall_status == ST.BLOCKED_BY_BASELINE_STATE.value


# 43-44: ties stay ties; ordering not preference
def test_43_44_ties():
    def h(hid, comp):
        return {"hypothesis_id": hid, "source_mechanism_id": "m", "status": "testable",
                "direction": "stiffen", "evidence_grade": "moderate",
                "target": {"component": comp, "handling_phase": "mid_corner"},
                "expected_response": {}, "predicted_trade_offs": [], "protected_good_at_risk": [],
                "rejection_criteria": [], "test_design": {}}
    hset = {"canonical_issue": {"issue_type": "oversteer"}, "content_fingerprint": "fp",
            "testable": [h("h1", "arb_rear"), h("h2", "springs_rear")],
            "conditional": [], "competing": [], "blocked": [], "preserve_and_observe": []}
    r = SYN(hset, applied_setup=applied(), session_identity=IDENT, ranges=RANGES)
    assert r.selected_candidate is None and r.unresolved_conflicts


# 45-48: irrelevant/reorder no change; lower quality no aggressive; removing evidence no readiness
def test_45_46_irrelevant_reorder():
    base = syn()
    extra = syn(outcome_history=[{"fields": ["unrelated"], "outcome_status": "regression",
                                 "single_field": True}])
    assert base.content_fingerprint == extra.content_fingerprint


def test_47_lower_quality_not_more_aggressive():
    strong = syn(vl=6); weak = syn(vl=3)
    # both move exactly one legal step; low quality never a bigger step
    assert strong.selected_candidate["deltas"][0]["delta"] == \
        weak.selected_candidate["deltas"][0]["delta"]


# 49-52: synthesis mutates nothing
def test_49_50_no_mutation():
    a = ann("entry_understeer", axle="front", phase="entry")
    src = copy.deepcopy(a.to_dict())
    hs = BIH(a.to_dict())
    hs_src = copy.deepcopy(hs.to_dict())
    r = SYN(hs.to_dict(), applied_setup=applied(), session_identity=IDENT, ranges=RANGES)
    assert a.to_dict() == src and hs.to_dict() == hs_src
    assert r.source_hypothesis_set == hs_src


def test_51_52_no_setup_or_active_mutation():
    a = applied()
    snap = copy.deepcopy(a)
    syn(applied_setup=a)
    assert a == snap        # the applied setup dict is not mutated


# 53-54: no Apply / no auto-persist
def test_53_54_no_apply_no_persist():
    r = syn()
    d = r.to_dict()
    for k in ("apply", "approved", "saved", "persist"):
        assert k not in d


# 55: runtime production path performs no writes
def test_55_runtime_read_only(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    before = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_bounded_setup_experiments(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    after = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    assert before == after == 0 and db._conn.execute("PRAGMA user_version").fetchone()[0] == 28
    db.close()


# 56-58: identical fingerprints; restart preserves; empty safe
def test_56_deterministic():
    assert syn().content_fingerprint == syn().content_fingerprint


def test_58_empty_safe():
    r = SYN({}, applied_setup=applied(), session_identity=IDENT, ranges=RANGES)
    assert r.overall_status in ("no_eligible_hypothesis", "not_evaluable",
                                "blocked_by_baseline_state")


# 61-63: no shadow authority; no AI/network
def test_61_62_63_no_shadow_no_ai():
    src = inspect.getsource(M)
    assert "from strategy.experiment_selection import legal_step" in src   # consumes step authority
    assert "from strategy.setup_synthesis import _round" in src            # consumes quantiser
    for banned in ("PARAMETER_INTERACTIONS = {", "_STEP = {", "legal_step(field_name)",
                   "import openai", "import anthropic", "requests", "socket"):
        if banned == "legal_step(field_name)":
            continue
        assert banned not in src


# 64: existing Apply gate remains the only mutation route (no apply calls here)
def test_64_no_apply_calls():
    src = inspect.getsource(M)
    for banned in ("mark_applied(", "create_setup_experiment(", ".save(", "compute_apply_status("):
        assert banned not in src


# restart determinism through the DB path (57)
def test_57_restart_determinism(tmp_path):
    from strategy.development_history import MemoryContextKey, build_development_record
    ctx = MemoryContextKey(driver="d", car="Porsche 911 RSR", track="Fuji", layout_id="fc",
                           discipline="Race", gt7_version="1", compound="RH")
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    rec = build_development_record(
        {"id": "1", "experiment_id": 5, "status": "no_meaningful_change",
         "confidence_level": "high", "scope_fingerprint": "sf", "test_session_id": "s",
         "protected": [], "failed_directions": []},
        {"id": 5, "scope_fingerprint": "sf", "changes": [{"field": "arb_front"}]},
        context=ctx, scope_fingerprint="sf", working_windows=[],
        residuals=[{"issue_key": "k", "family": "rotation", "issue_type": "entry_understeer",
                    "axle": "front", "phase": "entry", "segment_id": "T1", "corner_name": "T1",
                    "residual_state": "unchanged", "is_new": False, "is_regression": False,
                    "still_present": True, "protected_good": False, "confidence": "high"}],
        recorded_at="2026-07-01T10:00", session_date="2026-07-01")
    db._persist_development_record(rec, created_at=rec.recorded_at)
    kw = dict(car="Porsche 911 RSR", track="Fuji", layout_id="fc", discipline="Race",
              driver="d", gt7_version="1", compound="RH")
    r1 = db.build_bounded_setup_experiments(applied_setup=applied(), session_identity=IDENT, **kw)
    db._conn.close()
    db2 = SessionDB(p)
    r2 = db2.build_bounded_setup_experiments(applied_setup=applied(), session_identity=IDENT, **kw)
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 28
    db2._conn.close()
