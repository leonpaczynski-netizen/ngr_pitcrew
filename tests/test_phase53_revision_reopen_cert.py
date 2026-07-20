"""Phase 53 — event revision impact, setup-lock reopening, operational certification (items 24-26)."""
from __future__ import annotations

from strategy.event_revision_impact import assess_event_revision
from strategy.setup_lock_reopen import SetupLockReopenReason as RR, assess_lock_reopen
from strategy.operational_certification import (
    ProofLevel as P, CertificationState as C, CertificationArea, build_certification,
)


# --- event revision impact -------------------------------------------------

def test_no_change_is_no_revision():
    ctx = {"car": "P", "track": "Fuji", "tyre_multiplier": "1"}
    i = assess_event_revision(ctx, dict(ctx))
    assert i.revision_detected is False and i.prior_evidence_compatible is True


def test_tyre_multiplier_change_flags_incompatible_and_strategy_recalc():
    old = {"car": "P", "track": "Fuji", "tyre_multiplier": "1", "fuel_multiplier": "1"}
    new = {"car": "P", "track": "Fuji", "tyre_multiplier": "5", "fuel_multiplier": "1"}
    i = assess_event_revision(old, new)
    assert i.revision_detected is True
    assert i.prior_evidence_compatible is False
    assert "tyre_multiplier" in i.incompatible_fields
    assert i.lock_reopen_required is True
    assert i.strategy_recalc_required is True


def test_non_evidence_field_change_keeps_evidence_compatible():
    old = {"car": "P", "track": "Fuji", "penalties": "standard"}
    new = {"car": "P", "track": "Fuji", "penalties": "strict"}
    i = assess_event_revision(old, new)
    assert i.revision_detected is True
    assert i.prior_evidence_compatible is True and i.lock_reopen_required is False


def test_revision_never_rewrites_history():
    # assess is a pure function of its inputs; the inputs are not mutated
    old = {"car": "P", "track": "Fuji"}
    new = {"car": "GT3", "track": "Fuji"}
    _ = assess_event_revision(old, new)
    assert old == {"car": "P", "track": "Fuji"}  # unchanged


# --- setup-lock reopening (Audit C) ----------------------------------------

def test_noisy_lap_alone_does_not_reopen():
    d = assess_lock_reopen(noisy_lap=True)
    assert d.eligible is False and d.reason == RR.NOISE_ONLY


def test_subjective_complaint_alone_does_not_reopen():
    d = assess_lock_reopen(subjective_complaint=True)
    assert d.eligible is False and d.reason == RR.SUBJECTIVE_ONLY


def test_corroborated_critical_regression_reopens():
    d = assess_lock_reopen(corroborated_regression=True, critical_instability=True)
    assert d.eligible is True and d.reason == RR.CONFIRMED_CRITICAL_REGRESSION
    assert d.requires_visible_consequence is True


def test_event_context_revision_reopens():
    assert assess_lock_reopen(event_context_revision=True).reason == RR.EVENT_CONTEXT_REVISION
    assert assess_lock_reopen(event_context_revision=True).eligible is True


def test_fingerprint_mismatch_rules_and_physics_reopen():
    assert assess_lock_reopen(fingerprint_mismatch=True).reason == RR.FINGERPRINT_MISMATCH
    assert assess_lock_reopen(rules_change=True).reason == RR.RULES_CHANGE
    assert assess_lock_reopen(physics_version_change=True).reason == RR.PHYSICS_VERSION_CHANGE


def test_independent_corroborated_evidence_reopens():
    d = assess_lock_reopen(independent_corroborated_evidence=True)
    assert d.eligible is True and d.reason == RR.INDEPENDENT_CORROBORATED_EVIDENCE


def test_explicit_override_reopens_with_visible_consequence():
    d = assess_lock_reopen(explicit_override=True)
    assert d.eligible is True and d.reason == RR.EXPLICIT_DRIVER_OVERRIDE
    assert d.requires_visible_consequence is True


def test_noise_plus_valid_trigger_still_reopens():
    # noise never blocks a genuine trigger
    d = assess_lock_reopen(noisy_lap=True, event_context_revision=True)
    assert d.eligible is True and d.reason == RR.EVENT_CONTEXT_REVISION


# --- operational certification ---------------------------------------------

def _areas(level):
    return [CertificationArea("home", level), CertificationArea("live", level)]


def test_certification_bounded_by_weakest_area():
    areas = [CertificationArea("home", P.LIVE_VALIDATED), CertificationArea("live", P.AUTOMATED)]
    cert = build_certification(areas)
    assert cert.overall_state == C.AUTOMATED_ONLY and cert.weakest_area == "live"


def test_automated_only_cannot_be_operationally_ready():
    cert = build_certification(_areas(P.AUTOMATED), operationally_ready_granted=True)
    assert cert.overall_state == C.AUTOMATED_ONLY  # grant ignored without live evidence


def test_offscreen_validated_state():
    assert build_certification(_areas(P.OFFSCREEN)).overall_state == C.OFFSCREEN_VALIDATED


def test_live_validated_and_operationally_ready_with_grant():
    assert build_certification(_areas(P.LIVE_VALIDATED)).overall_state == C.LIVE_GT7_VALIDATED
    granted = build_certification(_areas(P.LIVE_VALIDATED), operationally_ready_granted=True)
    assert granted.overall_state == C.OPERATIONALLY_READY
    partial = build_certification(_areas(P.LIVE_PARTIAL), operationally_ready_granted=True)
    assert partial.overall_state == C.OPERATIONALLY_READY_WITH_LIMITATIONS


def test_certification_deterministic():
    a = build_certification(_areas(P.OFFSCREEN))
    b = build_certification(_areas(P.OFFSCREEN))
    assert a.fingerprint == b.fingerprint
