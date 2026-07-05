"""Shared setup-brain constants imported by both setup_diagnosis and driving_advisor.

Defined here (not in either of those modules) to avoid a circular import:
  driving_advisor  imports  setup_diagnosis  (lazy, at module level)
  setup_diagnosis  imports  driving_advisor  (lazy, inside validate_setup_engineering
                                              for _validate_setup_response)

Placing ENG_SAFETY_PREFIXES here lets both modules import it from a third file
that has no dependency on either.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Engineering-safety rule prefixes
# ---------------------------------------------------------------------------
# When ANY reason string returned by validate_setup_engineering starts with
# one of these prefixes it is considered a BLOCKING engineering-safety failure.
# Structural / schema / range errors (malformed_schema, invalid_units,
# "change field …", "too many") are NOT in this set — those are cosmetic
# (the AI can still produce useful output even with minor schema issues) and
# do not zero-out the approved changes list by themselves.
#
# The new rules added in the "Setup Builder Engineering Validation Gate" sprint
# (snap_throttle_lsd_accel_gate, kerb_strike_rh_over_increment,
#  gearbox_fake_field, gearbox_ratio_inversion) are included here because they
# represent real physical / UX invariants that must never surface to the driver.
ENG_SAFETY_PREFIXES: tuple[str, ...] = (
    "rh_for_minor_bottoming",
    "rh_low_confidence_location",
    "aero_cut_with_wheelspin",
    "aero_at_min_floaty",
    "gearbox_category_mismatch",
    "rh_increment_exceeds_confidence",
    "rh_rake_risk",
    "lsd_large_change_gated",
    "lsd_blocked_driver_feel",
    "lsd_reversal_without_evidence",
    # New blocking rules (sprint: Setup Builder Engineering Validation Gate)
    "snap_throttle_lsd_accel_gate",
    "kerb_strike_rh_over_increment",
    "gearbox_fake_field",
    "gearbox_ratio_inversion",
)

# Statuses that mean the recommendation is safe to surface to the driver
# and write to the primary history bucket.
APPROVED_STATUSES: frozenset[str] = frozenset({
    "approved",
    "approved_with_warnings",
    "fallback_generated",
})

# ---------------------------------------------------------------------------
# Group 42 — Rule-First Setup Brain constants
# ---------------------------------------------------------------------------

# AC26: rule-engine version string — non-empty, bumped with each pack change.
RULE_ENGINE_VERSION: str = "42.0"

# AC21: minimum outcome samples before the success-rate gate fires.
MIN_OUTCOME_SAMPLES: int = 3

# AC21: success rate threshold below which confidence is downgraded one step.
LOW_SUCCESS_RATE: float = 0.40

# Status written to setup_history when the AI audit rejected the plan.
# NOT in APPROVED_STATUSES → routes to the _rejected_ bucket automatically.
AI_AUDIT_REJECTED_ADVISORY: str = "ai_audit_rejected_advisory"
