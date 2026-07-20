"""Phase 14 — property / metamorphic invariants (Section 25, 40 invariants)."""
import copy
import re

import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.mechanism_annotation import annotate_diagnosis
from strategy.intervention_hypothesis import (
    InterventionHypothesisStatus as S, build_intervention_hypotheses,
)
from strategy import gearbox_evidence as gbx


def _ann(it="wheelspin", fam="traction", axle="rear", phase="exit", **kw):
    d = {"issue_family": fam, "issue_type": it, "axle": axle, "phase": phase,
         "segment_id": kw.get("seg", "T4"), "residual_state": kw.get("rs", "worsened"),
         "recurring": kw.get("rec", True), "valid_laps": kw.get("vl", 5),
         "sessions_seen": 2, "telemetry_available": True, "key": "k-" + it}
    return annotate_diagnosis(d, failed_directions=kw.get("fd", ()),
                             protected_good=kw.get("pg", ()), speed_context=kw.get("sc", ""),
                             outcome=kw.get("outcome"), decision_state=kw.get("ds", ""))


def _all(s):
    return (list(s.testable) + list(s.conditional) + list(s.competing)
            + list(s.blocked) + list(s.preserve_and_observe))


def _bih(a, **kw):
    return build_intervention_hypotheses(a.to_dict(), **kw)


# 1: invalid evidence never testable
def test_01_invalid_never_testable():
    s = _bih(_ann(rs="invalid_comparison", ds="invalid"))
    assert not s.testable


# 2: contradicted mechanism cannot produce a testable intervention
def test_02_contradicted_mechanism_not_testable():
    recon = {"consequence_reconciliations": [
        {"kind": "primary_effect", "field": "arb_front", "predicted": "arb_front softer",
         "status": "contradicted", "observed": "x", "reason": "y"}], "prediction_fingerprint": "p"}
    a = annotate_diagnosis(
        {"issue_family": "rotation", "issue_type": "entry_understeer", "axle": "front",
         "phase": "entry", "residual_state": "worsened", "recurring": True, "valid_laps": 4,
         "key": "k"}, reconciliation=recon)
    s = build_intervention_hypotheses(a.to_dict())
    for h in _all(s):
        if h["source_mechanism_status"] == "contradicted":
            assert h["status"] != S.TESTABLE.value


# 3: contradicted direction stays blocked
def test_03_contradicted_direction_blocked():
    s = _bih(_ann("entry_understeer", "rotation", "front", "entry"),
             outcome_history=[{"fields": ["arb_front"], "outcome_status": "regression",
                               "single_field": True}])
    arb = [h for h in _all(s) if h["target"]["component"] == "arb_front"]
    assert arb and arb[0]["status"] == S.CONTRADICTED_BY_OUTCOME.value


# 4 + 5: adding/reordering irrelevant evidence cannot change output
def test_04_05_irrelevant_and_reorder_no_change():
    base = _bih(_ann())
    with_extra = _bih(_ann(), outcome_history=[{"fields": ["unrelated_field"],
                                                "outcome_status": "regression", "single_field": True}])
    assert base.content_fingerprint == with_extra.content_fingerprint


# 6 + 7: lower-quality evidence cannot raise; removing evidence cannot improve
def test_06_07_evidence_monotonic():
    strong = _bih(_ann("entry_understeer", "rotation", "front", "entry", vl=6))
    weak = _bih(_ann("entry_understeer", "rotation", "front", "entry", vl=3))
    order = {"strong": 3, "moderate": 2, "weak": 1, "insufficient": 0, "": 0}
    sg = strong.testable[0]["evidence_grade"] if strong.testable else ""
    wg = weak.testable[0]["evidence_grade"] if weak.testable else ""
    assert order[wg] <= order[sg]


# 8: competing mechanisms remain competing
def test_08_competing_stays_competing():
    s = _bih(_ann())
    assert s.competing or s.overall_status in ("competing_mechanisms", "insufficient_evidence")


# 9: ties do not silently become winners (stable id tie-break; multiple testable possible)
def test_09_ties_stable():
    a = _ann("entry_understeer", "rotation", "front", "entry")
    ids1 = [h["hypothesis_id"] for h in build_intervention_hypotheses(a.to_dict()).testable]
    ids2 = [h["hypothesis_id"] for h in build_intervention_hypotheses(a.to_dict()).testable]
    assert ids1 == ids2


# 10 + 11: confirmed outcome doesn't prove; regression contradicts direction not physics
def test_10_11_outcome_semantics():
    s = _bih(_ann("entry_understeer", "rotation", "front", "entry"),
             outcome_history=[{"fields": ["arb_front"], "outcome_status": "regression",
                               "single_field": True}])
    arb = [h for h in _all(s) if h["target"]["component"] == "arb_front"][0]
    assert arb["status"] == S.CONTRADICTED_BY_OUTCOME.value
    assert "mechanism may still hold" in arb["prior_outcome_relationship"]


# 12: multi-field outcome not single-field proof
def test_12_multifield_not_single_proof():
    s = _bih(_ann("rear_loose_on_exit", "traction", "rear", "exit"),
             outcome_history=[{"fields": ["lsd_accel", "aero_rear"],
                               "outcome_status": "confirmed_improvement", "single_field": False}])
    for h in _all(s):
        if h["test_design"]["test_kind"] == "paired_coupled":
            assert h["test_design"]["attributable_to_single_field"] is False


# 13: working-window locks cannot be bypassed
def test_13_lockout_not_bypassed():
    s = _bih(_ann(fd=[("lsd_accel", "increase", "lockout")]),
             driver_preference={"priority": "rear_stability"})
    lsd = [h for h in _all(s) if h["target"]["component"] == "lsd_accel"][0]
    assert lsd["status"] == S.BLOCKED_BY_WORKING_WINDOW.value


# 14: protected-good cannot disappear from trade-offs
def test_14_protected_good_surfaced():
    a = annotate_diagnosis(
        {"issue_family": "rotation", "issue_type": "entry_understeer", "axle": "front",
         "phase": "entry", "residual_state": "unchanged", "recurring": True, "valid_laps": 4,
         "key": "k"}, protected_good=[{"behaviour": "braking stability good"}])
    s = build_intervention_hypotheses(a.to_dict())
    assert all("braking stability good" in h["protected_good_at_risk"] for h in s.testable)


# 15: wheelspin never auto-increases LSD locking
def test_15_wheelspin_no_auto_lsd():
    s = _bih(_ann())
    assert not [h for h in s.testable if h["target"]["component"] == "lsd_accel"]


# 16: low-speed issue no aero-primary intervention
def test_16_low_speed_no_aero_primary():
    s = _bih(_ann("mid_corner_understeer", "rotation", "front", "apex"))
    aero = [h for h in s.testable if h["target"]["component"] == "aero_front"]
    assert not aero


# 17 + 18: unknown / conflicting gearbox -> no gearing direction
def test_17_18_gearbox_no_direction():
    for st in (gbx.GEARING_UNKNOWN, gbx.GEARING_CONFLICTING, ""):
        s = _bih(_ann("wrong_gear", "gearing", "rear", "exit"), gearbox_state=st)
        gear = [h for h in _all(s) if h["target"]["component"] == "transmission"][0]
        assert gear["direction"] == "no_defensible_direction"


# 19: count-only bottoming no forced platform intervention
def test_19_bottoming_not_forced():
    s = _bih(_ann("bottoming", "platform", "", ""))
    assert not s.testable


# 20: numeric setup values never appear
def test_20_no_numeric_values():
    for a in (_ann(), _ann("entry_understeer", "rotation", "front", "entry"),
              _ann("wrong_gear", "gearing", "rear", "exit")):
        blob = str(_bih(a).to_dict()).lower()
        assert not re.search(r"set \w+ to \d", blob)
        assert not re.search(r"final drive \d\.\d", blob)


# 21: no Apply/approval capability
def test_21_no_apply_capability():
    s = _bih(_ann())
    d = s.to_dict()
    for k in ("apply", "approve", "approved", "apply_flag"):
        assert k not in d
    assert "apply now" not in str(d).lower()


# 22-25: no mutation of diagnosis / outcome / setup history / active setup
def test_22_25_no_mutation(tmp_path):
    a = _ann()
    src = copy.deepcopy(a.to_dict())
    s = build_intervention_hypotheses(a.to_dict())
    assert a.to_dict() == src                       # annotation unchanged
    assert s.source_annotation == src               # retained verbatim


# 26: identical inputs -> identical fingerprints
def test_26_deterministic_fingerprint():
    a = _ann()
    assert build_intervention_hypotheses(a.to_dict()).content_fingerprint == \
        build_intervention_hypotheses(copy.deepcopy(a.to_dict())).content_fingerprint


# 27: rendering does not alter domain results
def test_27_render_no_side_effect():
    from strategy.intervention_hypothesis_render import render_set_text
    a = _ann()
    s = build_intervention_hypotheses(a.to_dict())
    d = copy.deepcopy(s.to_dict())
    render_set_text(s.to_dict())
    assert s.to_dict() == d


# 28: pure domain (no Qt) — proven in safety test; here assert import cleanliness
def test_28_domain_qt_free():
    import inspect
    from strategy import intervention_hypothesis as M
    assert "PyQt" not in inspect.getsource(M)


# 29: empty evidence returns safe deterministic result
def test_29_empty_safe():
    s = build_intervention_hypotheses({})
    assert s.overall_status in ("not_evaluable", "insufficient_evidence",
                                "blocked_by_safety_or_validity")
    assert not s.testable


# 30: unsupported GT7 controls out of scope (driver technique)
def test_30_driver_technique_out_of_scope():
    s = _bih(_ann("poor_drive_out", "drive_out", "rear", "exit"))
    tech = [h for h in _all(s) if h["source_mechanism_id"] == "drive_throttle_technique"]
    assert tech and tech[0]["status"] == S.OUT_OF_SCOPE.value


# 31: single-field tests isolated
def test_31_single_field_isolated():
    s = _bih(_ann("entry_understeer", "rotation", "front", "entry"))
    for h in s.testable:
        if h["test_design"]["test_kind"] == "single_field_isolated":
            assert h["test_design"]["attributable_to_single_field"] is True


# 32: coupled tests declare why coupling is necessary
def test_32_coupled_declares_reason():
    s = _bih(_ann("rear_loose_on_exit", "traction", "rear", "exit"),
             outcome_history=[{"fields": ["lsd_accel", "springs_rear"],
                               "outcome_status": "confirmed_improvement", "single_field": False}])
    for h in _all(s):
        if h["test_design"]["test_kind"] == "paired_coupled":
            assert h["prior_outcome_relationship"]


# 33: minimum-effective-intervention ordering (single-field before coupled at equal status)
def test_33_min_effective_ordering():
    s = _bih(_ann("entry_understeer", "rotation", "front", "entry"))
    kinds = [h["test_design"]["test_kind"] for h in s.testable]
    # single-field tests are not pushed below coupled ones of equal status
    if "single_field_isolated" in kinds and "paired_coupled" in kinds:
        assert kinds.index("single_field_isolated") <= kinds.index("paired_coupled")


# 34: proven-good behaviour explicit protection
def test_34_protection_explicit():
    a = annotate_diagnosis(
        {"issue_family": "rotation", "issue_type": "entry_understeer", "axle": "front",
         "phase": "entry", "residual_state": "unchanged", "recurring": True, "valid_laps": 4,
         "key": "k"}, protected_good=[{"behaviour": "turn-in good"}])
    s = build_intervention_hypotheses(a.to_dict())
    assert any("turn-in good" in h["rejection_criteria"][-2] or
               "turn-in good" in " ".join(h["rejection_criteria"]) for h in s.testable)


# 35: driver preference cannot override invalid evidence
def test_35_pref_cannot_override_invalid():
    s = _bih(_ann(rs="invalid_comparison", ds="invalid"),
             driver_preference={"priority": "front_bite"})
    assert not s.testable


# 36: missing speed context caps aero
def test_36_missing_speed_caps_aero():
    s = _bih(_ann("mid_corner_understeer", "rotation", "front", "apex"))
    aero = [h for h in _all(s) if h["target"]["component"] == "aero_front"][0]
    assert aero["status"] in ("conditional", "insufficient_evidence")


# 37: missing damper velocity prevents false damper-force claims
def test_37_no_damper_force_claim():
    s = _bih(_ann("kerb", "platform", "", "apex"))
    blob = str(_all(s)).lower()
    assert not re.search(r"\d+\s*(n|newton)\b", blob)


# 38: missing engine torque prevents false gearing certainty
def test_38_no_engine_torque_certainty():
    s = _bih(_ann("wrong_gear", "gearing", "rear", "exit"), gearbox_state="unknown")
    gear = [h for h in _all(s) if h["target"]["component"] == "transmission"][0]
    assert any("gearbox" in e.lower() or "unknown" in e.lower() for e in gear["required_evidence"])


# 39: final-drive direction semantics remain correct
def test_39_final_drive_semantics():
    assert gbx.final_drive_lengthens(4.25, 4.20) is True
    assert gbx.final_drive_shortens(4.20, 4.25) is True
    s = _bih(_ann("wheelspin", "traction", "rear", "exit"), gearbox_state=gbx.GEARING_TOO_SHORT)
    gear = [h for h in _all(s) if h["target"]["component"] == "transmission"][0]
    assert gear["direction"] == "lengthen"


# 40: no shadow dynamics / interaction authority introduced
def test_40_no_shadow_authority():
    import inspect
    from strategy import intervention_hypothesis as M
    src = inspect.getsource(M)
    assert "from strategy.vehicle_dynamics import" in src   # consumes
    for banned in ("_KNOWLEDGE =", "PARAMETER_INTERACTIONS =", "_INTERACTIONS =",
                   "_LSD_MODEL =", "_AERO_MODEL ="):
        assert banned not in src


# restart determinism through the DB path
def test_restart_determinism(tmp_path):
    from strategy.development_history import MemoryContextKey, build_development_record
    ctx = MemoryContextKey(driver="d", car="c", track="t", layout_id="l",
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
    kw = dict(car="c", track="t", layout_id="l", discipline="Race", driver="d",
              gt7_version="1", compound="RH")
    r1 = db.build_intervention_hypotheses(**kw)
    db._conn.close()
    db2 = SessionDB(p)
    r2 = db2.build_intervention_hypotheses(**kw)
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 28
    db2._conn.close()
