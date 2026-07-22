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
