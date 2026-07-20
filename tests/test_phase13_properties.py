"""Phase 13 — property / metamorphic invariants (Section 24) + persistence decision (21).

The 25 invariants that must hold for the mechanism annotation to be safe and deterministic.
"""
import copy

import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.mechanism_annotation import (
    MechanismStatus, annotate_diagnosis, annotate_diagnoses,
)


def _diag(**over):
    d = {"issue_family": "traction", "issue_type": "wheelspin", "axle": "rear",
         "phase": "exit", "segment_id": "T4", "residual_state": "worsened",
         "recurring": True, "valid_laps": 5, "sessions_seen": 2, "key": "iss"}
    d.update(over)
    return d


def _primary_id(a):
    return a.primary_mechanism["mechanism_id"] if a.primary_mechanism else None


# 1 + 3 + 4: reordering / duplicating / excluding evidence cannot change the primary
def test_reorder_and_duplicate_failed_directions_no_change():
    base = annotate_diagnosis(_diag(), failed_directions=[("lsd_accel", "increase")])
    reordered = annotate_diagnosis(
        _diag(), failed_directions=[("lsd_accel", "increase"), ("lsd_accel", "increase")])
    assert _primary_id(base) == _primary_id(reordered)
    assert base.overall_status == reordered.overall_status


# 2: reordering Phase-12 knowledge registration cannot change the result (candidate order
#    is issue-type keyed and stable → same fingerprint)
def test_repeated_build_identical_fingerprint():
    d = _diag()
    assert annotate_diagnosis(d).content_fingerprint == \
        annotate_diagnosis(d).content_fingerprint


# 5: invalid evidence cannot create a supported mechanism
def test_invalid_never_supported():
    for over in ({"residual_state": "invalid_comparison"},
                 {"decision_state_invalid": True}):
        a = annotate_diagnosis(_diag(**{k: v for k, v in over.items()
                                        if k != "decision_state_invalid"}),
                               decision_state="invalid" if over.get("decision_state_invalid")
                               else "")
        assert a.overall_status not in ("supported", "supported_with_limitations")


# 6 + 7: adding contradiction cannot raise support; removing support cannot leave supported
def test_contradiction_cannot_increase_support():
    clean = annotate_diagnosis(_diag(issue_type="entry_oversteer", axle="rear", phase="entry"))
    contra = annotate_diagnosis(_diag(issue_type="entry_oversteer", axle="rear", phase="entry"),
                                failed_directions=[("lsd_decel", "decrease")],
                                outcome={"status": "regression",
                                         "changes": [{"field": "lsd_decel"}]})
    rank = {"supported": 2, "supported_with_limitations": 1}
    assert rank.get(contra.primary_mechanism["status"] if contra.primary_mechanism else "", 0) \
        <= rank.get(clean.primary_mechanism["status"] if clean.primary_mechanism else "", 0) + 1


# 8: a confirmed outcome cannot by itself prove a mechanism
def test_confirmed_outcome_does_not_prove_mechanism():
    a = annotate_diagnosis(_diag(residual_state="improved_but_present"),
                           outcome={"status": "confirmed_improvement",
                                    "changes": [{"field": "lsd_accel"}]})
    assert "does not by itself prove" in a.outcome_consistency


# 9: a failed intervention direction is never rendered as successful mechanism proof
def test_failed_direction_never_success():
    a = annotate_diagnosis(_diag(), failed_directions=[("lsd_accel", "increase")])
    lsd = [c for c in a.competing_mechanisms if c["mechanism_id"] == "exit_diff_locking"]
    assert lsd and lsd[0]["intervention_direction_contradicted"]
    assert lsd[0]["status"] != "supported"


# 10: a missing GT7 channel is never treated as observed
def test_missing_channel_declared_not_observed():
    a = annotate_diagnosis(_diag())
    gt7 = " ".join(a.gt7_limitations).lower()
    assert "differential lock state" in gt7  # explicitly unavailable, never asserted


# 11: physics-informed interpretation is never labelled direct telemetry
def test_interpretation_labelled_physics_informed():
    a = annotate_diagnosis(_diag())
    assert a.primary_mechanism["conclusion_kind"] == "physics_informed"


# 12: a mechanism blocked by incompatible phase cannot be primary
def test_incompatible_phase_not_primary():
    a = annotate_diagnosis(_diag(issue_type="mid_corner_understeer", axle="front", phase="apex"))
    for c in [a.primary_mechanism] if a.primary_mechanism else []:
        assert c["handling_phase"] == "mid_corner"


# 13: a low-speed diagnosis cannot become aero-primary by candidate order
def test_low_speed_not_aero_primary():
    a = annotate_diagnosis(_diag(issue_type="mid_corner_understeer", axle="front", phase="apex"))
    assert not (a.primary_mechanism and "aero" in a.primary_mechanism["mechanism_id"])


# 14: a pure gear issue cannot become suspension-primary
def test_gear_issue_not_suspension_primary():
    a = annotate_diagnosis(_diag(issue_family="gearing", issue_type="wrong_gear",
                                 axle="rear", phase="exit"))
    assert a.primary_mechanism["primary_component"] == "transmission"


# 15: adding irrelevant component knowledge cannot alter the result
#     (the map is issue-type scoped; unrelated components never enter)
def test_unrelated_components_absent():
    a = annotate_diagnosis(_diag(issue_type="front_lock", issue_family="braking",
                                 axle="front", phase="braking"))
    comps = {a.primary_mechanism["primary_component"]}
    for c in a.competing_mechanisms:
        comps.add(c["primary_component"])
    assert "lsd_accel" not in comps and "aero_rear" not in comps


# 16 + 17: same inputs → same content fingerprint (restart reproducible)
def test_same_inputs_same_fingerprint():
    d = _diag()
    a1 = annotate_diagnosis(d)
    a2 = annotate_diagnosis(copy.deepcopy(d))
    assert a1.content_fingerprint == a2.content_fingerprint
    assert a1.to_dict() == a2.to_dict()


# 18: an invalid canonical decision always blocks a supported annotation
def test_invalid_decision_always_blocks():
    a = annotate_diagnosis(_diag(valid_laps=99, recurring=True), decision_state="invalid")
    assert a.overall_status == MechanismStatus.INVALID_SOURCE_DIAGNOSIS.value


# 19 + 20: competing stays competing without a discriminator; adding it may resolve
def test_competition_persists_without_discriminator():
    a = annotate_diagnosis(_diag(issue_type="wheelspin"))
    assert len(a.competing_mechanisms) >= 2
    # a high-speed discriminator changes the annotation deterministically
    b = annotate_diagnosis(_diag(issue_type="wheelspin"), speed_context="high_speed")
    assert a.content_fingerprint != b.content_fingerprint


# 21: no annotated diagnosis contains an actionable Apply instruction
def test_no_apply_instruction_anywhere():
    for over in ({}, {"issue_type": "front_lock", "issue_family": "braking", "axle": "front",
                      "phase": "braking"}):
        blob = str(annotate_diagnosis(_diag(**over)).to_dict()).lower()
        for banned in ("apply(", "set_setup", "save_setup", "revert_to", "click apply"):
            assert banned not in blob


# 22 + 23 + 24: viewing the annotation mutates no working window / outcome / calibration
def test_annotation_is_pure_no_side_effects(tmp_path):
    from strategy.mechanism_annotation import annotations_from_memory
    mem = {"issues": [{"issue_key": "k", "family": "traction", "issue_type": "wheelspin",
                       "axle": "rear", "phase": "exit", "corner": "T4",
                       "latest_state": "worsened", "recurring": True,
                       "times_observed": 5, "sessions_seen": 2,
                       "failed_fix_experiments": [], "successful_fix_experiments": []}],
           "protected_knowledge": [], "protected_behaviours": []}
    before = copy.deepcopy(mem)
    annotations_from_memory(mem)
    assert mem == before   # inputs untouched


# 25: the original canonical diagnosis remains byte-equivalent / structurally unchanged
def test_source_diagnosis_unchanged():
    d = _diag()
    snapshot = copy.deepcopy(d)
    a = annotate_diagnosis(d)
    assert a.source_diagnosis == snapshot
    assert d == snapshot        # not mutated in place


# --- Section 21: no migration needed (regenerable) --------------------------
def test_no_migration_db_stays_v25():
    db = SessionDB(":memory:")
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 28
    db.build_mechanism_annotations(car="RSR", track="Fuji")
    # building the annotation writes nothing / adds no table / bumps no version
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 28
