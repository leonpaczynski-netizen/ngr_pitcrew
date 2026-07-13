"""Group 63 — authoritative gearbox evidence model (pure, Qt-free).

Two responsibilities, both previously implicit and bug-prone:

1. **Final-drive directional invariant.** GT7 final-drive numbers are inverse to
   gearing length:

       lower numerical final-drive ratio  = LONGER gearing (taller, higher top speed)
       higher numerical final-drive ratio = SHORTER gearing (more acceleration)

   So ``4.25 -> 4.20`` (a −0.05 delta) *lengthens* the gearing. The UAT failure
   authored exactly this for a car whose sixth gear was **not fully used** — i.e.
   the gearing was already too long. This module is the single tested source of
   truth for that direction; the delta resolvers, rules, renderer and validator
   all reason through these helpers instead of re-deriving the sign.

2. **Canonical five-state gearing model.** The wired classifier
   (``setup_diagnosis._classify_gearing``) emits a fine-grained category for rule
   preconditions; ``derive_gearing_state`` folds that category plus the driver's
   own report into the five states the driver-facing brain reasons about:

       TOO_SHORT | APPROPRIATE | TOO_LONG | UNKNOWN | CONFLICTING_EVIDENCE

   The point of CONFLICTING_EVIDENCE / UNKNOWN is to make honest non-answers
   first-class: they must lead to a *targeted test*, never an applyable gearbox
   change authored on invalid or contradicted evidence.

This module authors NO setup values and applies nothing.
"""
from __future__ import annotations

# One conservative one-step final-drive change (matches the delta resolvers).
FINAL_DRIVE_STEP = 0.05

# Canonical gearing states.
GEARING_TOO_SHORT = "too_short"
GEARING_APPROPRIATE = "appropriate"
GEARING_TOO_LONG = "too_long"
GEARING_UNKNOWN = "unknown"
GEARING_CONFLICTING = "conflicting_evidence"

# Directional labels.
GEARING_LONGER = "longer"
GEARING_SHORTER = "shorter"
GEARING_UNCHANGED = "unchanged"


def final_drive_effect(delta: float) -> str:
    """Return the *gearing* effect of a final-drive numeric ``delta``.

    lower ratio (delta < 0) -> longer gearing; higher ratio (delta > 0) -> shorter.
    """
    try:
        d = float(delta)
    except (TypeError, ValueError):
        return GEARING_UNCHANGED
    if d < 0:
        return GEARING_LONGER
    if d > 0:
        return GEARING_SHORTER
    return GEARING_UNCHANGED


def final_drive_lengthens(old_ratio: float, new_ratio: float) -> bool:
    """True when moving from ``old_ratio`` to ``new_ratio`` LENGTHENS the gearing
    (i.e. the numeric ratio goes DOWN, e.g. 4.25 -> 4.20)."""
    try:
        return float(new_ratio) < float(old_ratio)
    except (TypeError, ValueError):
        return False


def final_drive_shortens(old_ratio: float, new_ratio: float) -> bool:
    """True when moving from ``old_ratio`` to ``new_ratio`` SHORTENS the gearing
    (i.e. the numeric ratio goes UP, e.g. 4.20 -> 4.25)."""
    try:
        return float(new_ratio) > float(old_ratio)
    except (TypeError, ValueError):
        return False


# Fine categories emitted by _classify_gearing that mean "gearing is fine as-is".
_APPROPRIATE_CATEGORIES = frozenset({"limiter_limited"})
# Fine categories that are honest non-answers.
_UNKNOWN_CATEGORIES = frozenset({
    "insufficient_data", "traction_limited_acceleration",
    "drag_or_power_limited", "top_gear_power_band_limited",
})


def derive_gearing_state(
    category: str,
    *,
    driver_says_too_long: bool = False,
    driver_says_gearbox_good: bool = False,
) -> str:
    """Fold the fine telemetry ``category`` + the driver's report into one of the
    five canonical states.

    The driver's direct report is treated as strong structured evidence:
      * telemetry says TOO_SHORT but the driver reports an unused top gear
        -> CONFLICTING_EVIDENCE (targeted test, never an applyable change).
      * telemetry is a non-answer (UNKNOWN set) and the driver reports unused top
        -> still UNKNOWN here (driver report alone cannot author a change without
        corroborating terminal-RPM/limiter telemetry) — it drives a targeted test.
      * telemetry independently says TOO_LONG (+ driver agrees) -> TOO_LONG.
    """
    cat = str(category or "").strip()
    if driver_says_gearbox_good:
        return GEARING_APPROPRIATE
    if cat == "gear_too_short":
        return GEARING_CONFLICTING if driver_says_too_long else GEARING_TOO_SHORT
    if cat == "gear_too_long":
        return GEARING_TOO_LONG
    if cat in _APPROPRIATE_CATEGORIES:
        return GEARING_APPROPRIATE
    # Non-answer categories: honest UNKNOWN (driver-too-long report surfaces as a
    # targeted test, not a change).
    return GEARING_UNKNOWN
