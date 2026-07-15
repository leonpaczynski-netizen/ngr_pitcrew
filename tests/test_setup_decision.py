"""Sprint 6 — setup decision arbitration + Fixture E.

Key guarantees:
  * one decision status per analysis;
  * never "approved" AND "validation failed" together;
  * low-confidence / non-recurring telemetry cannot override explicit positive
    driver feedback → EVIDENCE_CONFLICT, setup preserved, no LSD change (Fixture E);
  * LSD initial/accel/braking are arbitrated independently;
  * good traction with no eligible evidence → APPROVED_NO_CHANGE.
"""
from __future__ import annotations

from strategy.cross_lap_persistence import (
    PersistenceClass, CornerIssueSignature, IssuePersistenceResult,
)
from strategy.setup_decision import (
    DriverFeedback, DecisionStatus, arbitrate_setup_decision,
)


def _pres(issue_type, cls, eligible, *, pct=0.25, affected=2, total=8, axle="rear",
          seg="T3"):
    sig = CornerIssueSignature(
        track="fuji", layout_id="fuji__full", setup_checkpoint_id="cp1",
        segment_id=seg, corner_phase="exit", issue_type=issue_type, axle=axle,
        subtype_family="power_traction" if issue_type == "wheelspin" else "brake_lock")
    return IssuePersistenceResult(
        classification=cls, signature=sig, affected_representative_laps=affected,
        total_representative_laps=total, recurrence_pct=pct, sessions=1,
        median_severity=0.3, median_duration_s=0.3, confidence=0.5,
        eligible_for_setup=eligible, excluded_laps=(), reason="", next_action="")


# --------------------------------------------------------------------------- #
# Fixture E — positive feedback + low-confidence slip → EVIDENCE_CONFLICT
# --------------------------------------------------------------------------- #
def test_fixture_e_positive_feedback_conflict_no_lsd_change():
    proposed = [{"field": "lsd_accel", "delta": 5}]
    persistence = [_pres("wheelspin", PersistenceClass.EMERGING_PATTERN, eligible=False,
                         pct=0.25, affected=2, total=8)]
    fb = DriverFeedback(traction="good", braking="good", stability="good",
                        better_than_previous=True)
    d = arbitrate_setup_decision(proposed, persistence, fb)
    assert d.status is DecisionStatus.EVIDENCE_CONFLICT
    assert "lsd_accel" in d.fields_by_outcome("preserved")
    assert "lsd_accel" not in d.fields_by_outcome("approved")
    assert not d.is_approved
    assert d.controlled_test  # a test is prescribed instead of a change


def test_never_approved_and_validation_failed_together():
    proposed = [{"field": "lsd_accel"}]
    d = arbitrate_setup_decision(proposed, [], DriverFeedback(),
                                 validation_failed=True,
                                 validation_errors=["contradiction"])
    assert d.status is DecisionStatus.ENGINEERING_FAILURE
    assert d.validation_failed is True
    assert not d.is_approved
    assert "lsd_accel" in d.fields_by_outcome("rejected")


def test_persistent_evidence_with_neutral_feedback_is_approved():
    proposed = [{"field": "lsd_accel"}]
    persistence = [_pres("wheelspin", PersistenceClass.PERSISTENT_PATTERN, eligible=True,
                         pct=0.75, affected=6, total=8)]
    d = arbitrate_setup_decision(proposed, persistence, DriverFeedback())
    assert d.status is DecisionStatus.APPROVED_WITH_CHANGES
    assert "lsd_accel" in d.fields_by_outcome("approved")
    assert d.is_approved


def test_good_feedback_no_evidence_is_approved_no_change():
    d = arbitrate_setup_decision([], [], DriverFeedback(traction="good", better_than_previous=True))
    assert d.status is DecisionStatus.APPROVED_NO_CHANGE
    assert d.is_approved


def test_emerging_evidence_neutral_feedback_is_controlled_test():
    proposed = [{"field": "aero_rear"}]
    persistence = [_pres("wheelspin", PersistenceClass.EMERGING_PATTERN, eligible=False,
                         pct=0.375, affected=3, total=8)]
    d = arbitrate_setup_decision(proposed, persistence, DriverFeedback())
    assert d.status is DecisionStatus.CONTROLLED_TEST_REQUIRED
    assert "aero_rear" in d.fields_by_outcome("deferred_test")
    assert not d.is_approved


def test_lsd_axes_arbitrated_independently():
    # Good traction (accel preserved) but a PERSISTENT rear lockup (decel approved).
    proposed = [{"field": "lsd_accel"}, {"field": "lsd_decel"}]
    persistence = [
        _pres("wheelspin", PersistenceClass.ISOLATED_ANOMALY, eligible=False, affected=1),
        _pres("lockup", PersistenceClass.PERSISTENT_PATTERN, eligible=True,
              pct=0.75, affected=6, total=8, axle="rear"),
    ]
    fb = DriverFeedback(traction="good")   # good traction, braking neutral
    d = arbitrate_setup_decision(proposed, persistence, fb)
    assert "lsd_accel" in d.fields_by_outcome("preserved")     # good traction preserved
    assert "lsd_decel" in d.fields_by_outcome("approved")      # persistent lockup approved
    assert d.status is DecisionStatus.APPROVED_WITH_CHANGES


def test_unsafe_change_rejected():
    proposed = [{"field": "ride_height_rear"}]
    d = arbitrate_setup_decision(proposed, [], DriverFeedback(),
                                 unsafe_fields={"ride_height_rear"})
    assert d.status is DecisionStatus.REJECTED_UNSAFE
    assert "ride_height_rear" in d.fields_by_outcome("rejected")
    assert not d.is_approved


def test_good_traction_persistent_wheelspin_telemetry_wins_but_flagged():
    # If wheelspin genuinely PERSISTS at the same corner, recurring telemetry
    # outranks the positive report (precedence tier 1) — but only when eligible.
    proposed = [{"field": "lsd_accel"}]
    persistence = [_pres("wheelspin", PersistenceClass.CROSS_SESSION_CONFIRMED, eligible=True,
                         pct=0.7, affected=6, total=8)]
    d = arbitrate_setup_decision(proposed, persistence, DriverFeedback(traction="good"))
    assert d.status is DecisionStatus.APPROVED_WITH_CHANGES
    assert "lsd_accel" in d.fields_by_outcome("approved")


def test_deterministic_repeatable():
    proposed = [{"field": "lsd_accel"}]
    persistence = [_pres("wheelspin", PersistenceClass.EMERGING_PATTERN, eligible=False)]
    fb = DriverFeedback(traction="good")
    assert (arbitrate_setup_decision(proposed, persistence, fb)
            == arbitrate_setup_decision(proposed, persistence, fb))
