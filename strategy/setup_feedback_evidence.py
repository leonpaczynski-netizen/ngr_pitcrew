"""Pure setup-outcome feedback-evidence helpers (extracted from ui/dashboard.py).

These are deterministic, best-effort domain helpers used by the learning-outcome
scoring pass to turn a driver_feedback row + before/after telemetry windows into
the richer Group 47 outcome-verification evidence that is stored *additively*
alongside a learning_outcomes record.

They contain no Qt and no UI coupling.  Both functions are best-effort and never
raise: any failure yields an empty/neutral result so the caller's persistence is
never disrupted.  This module is the canonical home; ``ui/dashboard.py`` imports
these names (see F0.1 of the UI rebuild).
"""

from __future__ import annotations

# Structured driver_feedback columns whose text feeds outcome classification.
FEEDBACK_TEXT_FIELDS: tuple[str, ...] = (
    "corner_entry", "mid_corner", "exit_stability", "rear_braking",
    "tyre_condition", "notes",
)


def combine_driver_feedback_text(feedback_row: dict) -> str:
    """Join a driver_feedback row's free-text/structured fields into one string.

    Used only as evidence for deterministic outcome classification.  Never raises.
    """
    try:
        parts = []
        for f in FEEDBACK_TEXT_FIELDS:
            v = (feedback_row.get(f) or "").strip()
            if v:
                parts.append(v)
        return "; ".join(parts)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Structured practice-feedback dropdowns -> setup-diagnosis feeling text.
#
# The Practice Review form (ui/components/practice_feedback.py) captures the
# driver's verdict through DROPDOWNS, not free text — the better system.  The
# Garage "Analyse" otherwise sees only telemetry symptoms (lock-ups, wheelspin,
# off-track); a car that understeers by *feel* with clean telemetry would read
# "inside its window".  These tables map each dropdown state to the exact phrase
# strategy.setup_diagnosis._parse_driver_feel recognises, so the driver's answers
# fire the real setup rules.
#
# ACCURACY RULE: a dropdown state is mapped ONLY when there is an existing flag
# whose remedy is unambiguous and drivetrain-independent.  States with no sound
# home are deliberately OMITTED (listed at the bottom) rather than forced onto a
# near-miss flag — wrong advice is worse than none, and this must hold to the same
# accuracy bar as the rest of the setup brain.
# ---------------------------------------------------------------------------

# Per-phase balance dropdowns (_BALANCE: Understeer / Neutral / Oversteer …).
_BALANCE_TO_PHRASE: dict[str, dict[str, str]] = {
    "corner_entry": {
        "neutral": "entry balance is good",            # -> entry_balance_good (suppress turn-in tweaks)
        "understeer": "understeer on entry",           # -> entry_understeer
        "oversteer": "rear steps out under braking",   # -> rear_loose_under_braking (entry OS is a brake-phase problem)
    },
    "mid_corner": {
        "understeer": "pushes wide",                   # -> mid_corner_understeer
        # oversteer: no mid-corner-oversteer flag exists -> omit
    },
    "exit_stability": {
        "oversteer": "oversteer on exit",              # -> rear_loose_on_exit
        "strong oversteer": "snap oversteer on exit",  # -> snap_oversteer_exit
        # understeer (power understeer): no flag -> omit
    },
}

# Scale dropdowns (_SCALE: Poor / Below par / OK / Good / Excellent) — mapped only
# at the LOW end, and only where "poor" points at one clear lever.
_SCALE_LOW = {"poor", "below par"}
_SCALE_LOW_TO_PHRASE: dict[str, str] = {
    "braking_confidence": "locks up and is nervous under braking",  # -> braking_instability
    "rotation": "won't rotate",                                     # -> mid_corner_understeer
    # traction / drive_out: "poor traction" points at rear grip on a RWD but the
    #   front on a FWD — the correct lever is drivetrain-dependent, so telemetry
    #   (wheelspin detection) owns it, not a blind feeling flag. OMITTED.
    # straight_line / confidence: no single setup lever -> OMITTED.
}

# Severity dropdowns (_SEVERITY: None / Minor / Noticeable / Severe) — high end only.
_SEVERITY_HIGH = {"noticeable", "severe"}
_SEVERITY_HIGH_TO_PHRASE: dict[str, str] = {
    "bottoming": "bottoming",                          # -> bottoming
    # kerb_behaviour: unsettled-over-kerbs is a compliance/damper judgement with no
    #   dedicated flag -> OMITTED.
}

# Gearing dropdown (_GEAR: Too short / About right / Too long).
_GEAR_TO_PHRASE: dict[str, str] = {
    "too long": "gearing too long",                    # -> gearing_too_long (veto a lengthening)
    "about right": "gearbox is good",                  # -> gearbox_good (suppress gearing tweaks)
    # "too short": no gearing-too-short flag; telemetry detects it -> OMITTED.
}

# Vs-expectation dropdown (_VS_EXPECT) — only fuel has a flag.
_VS_EXPECT_WORSE_TO_PHRASE: dict[str, str] = {
    "fuel_behaviour": "using too much fuel",           # -> fuel_use_high (acknowledged, not a lever)
    # tyre_condition: tyre wear is a strategy input, not a setup lever here -> OMITTED.
}


def feedback_to_feeling(feedback: dict | None) -> str:
    """Turn a structured practice-feedback dict (the Review dropdowns) into a
    feeling string the setup diagnosis parses.

    Every mapped dropdown state produces the exact phrase ``_parse_driver_feel``
    recognises, so the driver's answers fire the real balance / braking / gearing
    rules — the dropdowns feed the brain directly instead of being ignored.
    States with no sound flag are intentionally skipped (see the tables above).
    Free-text notes are appended verbatim.  Best-effort; never raises.
    """
    if not isinstance(feedback, dict):
        return ""
    try:
        parts: list[str] = []

        def _val(field: str) -> str:
            return str(feedback.get(field) or "").strip().lower()

        # Per-phase balance.
        for field, mapping in _BALANCE_TO_PHRASE.items():
            raw = _val(field)
            if not raw:
                continue
            phrase = mapping.get(raw)
            if phrase is None:                      # fall back to the base direction
                if "understeer" in raw:
                    phrase = mapping.get("understeer")
                elif "oversteer" in raw:
                    phrase = mapping.get("oversteer")
            if phrase:
                parts.append(phrase)

        # Low-end scales, high-end severities, gearing, fuel.
        for field, phrase in _SCALE_LOW_TO_PHRASE.items():
            if _val(field) in _SCALE_LOW:
                parts.append(phrase)
        for field, phrase in _SEVERITY_HIGH_TO_PHRASE.items():
            if _val(field) in _SEVERITY_HIGH:
                parts.append(phrase)
        gear = _val("gear_choice")
        if gear in _GEAR_TO_PHRASE:
            parts.append(_GEAR_TO_PHRASE[gear])
        for field, phrase in _VS_EXPECT_WORSE_TO_PHRASE.items():
            if _val(field) == "worse than expected":
                parts.append(phrase)

        notes = str(feedback.get("notes") or "").strip()
        if notes:
            parts.append(notes)
        # De-duplicate while preserving order (rotation + mid understeer can repeat).
        seen: set[str] = set()
        out = [p for p in parts if not (p in seen or seen.add(p))]
        return "; ".join(out)
    except Exception:
        return ""


def verify_change_outcome(
    rule_id: str,
    field: str,
    car_id: int,
    track: str,
    layout_id: str,
    before_window,
    after_window,
    feedback_text: str,
) -> dict:
    """Run the Group 47 outcome-verification model for one applied change.

    Returns a small dict {target_issue, evidence_summary, safety_notes,
    outcome_kind} used to enrich the learning_outcomes record additively.  Any
    failure returns empty strings so the caller's persistence is never disrupted.
    """
    try:
        from strategy.setup_outcome_verification import (
            MetricSnapshot, verify_outcome, infer_target_issue_from_fields,
        )
        target_issue = infer_target_issue_from_fields([field])
        result = verify_outcome(
            rule_id=rule_id,
            car_id=car_id,
            track=track,
            layout_id=layout_id,
            target_issue=target_issue,
            before=MetricSnapshot.from_window(before_window),
            after=MetricSnapshot.from_window(after_window),
            driver_feedback=feedback_text,
        )
        return {
            "target_issue": result.target_issue,
            "evidence_summary": result.evidence_summary,
            "safety_notes": result.safety_notes,
            "outcome_kind": result.outcome.value,
        }
    except Exception:
        return {
            "target_issue": "", "evidence_summary": "",
            "safety_notes": "", "outcome_kind": "",
        }
