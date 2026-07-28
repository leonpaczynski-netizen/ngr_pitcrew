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


# Structured balance-field value -> the PHASE-SPECIFIC phrase the setup diagnosis
# actually recognises.  Every phrase here was verified to fire the intended flag
# in strategy.setup_diagnosis._parse_driver_feel; combos with no clean flag
# (exit understeer / mid-corner oversteer) are deliberately OMITTED so we never
# mis-attribute a complaint to the wrong corner phase and give bad advice.
_BALANCE_TO_PHRASE: dict[str, dict[str, str]] = {
    "corner_entry": {
        "understeer": "understeer on entry",
        "oversteer": "rear loose under braking",
    },
    "mid_corner": {
        "understeer": "pushes wide",
    },
    "exit_stability": {
        "understeer": "power understeer on exit",  # no flag today; harmless, future-proof
        "oversteer": "oversteer on exit",
        "strong oversteer": "snap oversteer on exit",
    },
}


def feedback_to_feeling(feedback: dict | None) -> str:
    """Turn a structured practice-feedback dict into a feeling string the setup
    diagnosis parses.

    The Garage "Analyse" only sees telemetry symptoms (lock-ups, wheelspin,
    off-track); it never sees the driver's handling verdict.  A car that
    understeers by *feel* but has clean telemetry would therefore read
    "inside its window".  This maps each balance field
    (corner_entry / mid_corner / exit_stability, values like "Understeer",
    "Strong oversteer") to the exact phase-specific phrase
    ``_parse_driver_feel`` recognises, so the balance rules actually fire.
    Free-text notes are appended verbatim.  Best-effort; never raises.
    """
    if not isinstance(feedback, dict):
        return ""
    try:
        parts: list[str] = []
        for field, mapping in _BALANCE_TO_PHRASE.items():
            raw = str(feedback.get(field) or "").strip().lower()
            if not raw or raw == "neutral":
                continue
            # Prefer the strongest specific match ("strong oversteer" before
            # "oversteer"), else fall back to the base balance direction.
            phrase = mapping.get(raw)
            if phrase is None:
                if "understeer" in raw:
                    phrase = mapping.get("understeer")
                elif "oversteer" in raw:
                    phrase = mapping.get("oversteer")
            if phrase:
                parts.append(phrase)
        notes = str(feedback.get("notes") or "").strip()
        if notes:
            parts.append(notes)
        return "; ".join(parts)
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
