"""Track Intelligence context helper for AI prompt injection (Group 17H).

Called by ai_planner.py and driving_advisor.py to inject resolved Track
Intelligence context into AI prompts.

Design rules:
  - Delegates to data.track_model_resolver.build_resolved_track_context_for_prompt().
  - Returns a compact warning if track/layout IDs are missing or on resolver error.
  - Never raises — all exceptions are caught and returned as warning text.
  - Does NOT guess or infer track_location_id from display names.
  - Does NOT call the AI API — prompt construction only.
"""
from __future__ import annotations


def get_track_context_for_ai(
    track_location_id: str | None,
    layout_id: str | None,
    car_name: str = "",
) -> str:
    """Return resolved Track Intelligence context string for AI prompt injection.

    If track/layout IDs are not provided, returns a compact unavailability
    warning so AI callers know location-level intelligence is absent.

    If the resolver raises for any reason, returns a safe error note rather
    than crashing the prompt builder.

    car_name is used to look up the per-car rev_limit_threshold_pct from the
    SessionDB before calling the resolver, so the resolver does not open a
    second DB connection.
    """
    if not track_location_id or not layout_id:
        return (
            "## Track Intelligence\n"
            "Track Intelligence unavailable: no selected track/layout was provided. "
            "Use general track knowledge only."
        )
    # Resolve rev_limit_threshold_pct here so the resolver receives a plain float.
    rev_limit_threshold_pct: float = 0.90
    if car_name:
        try:
            from data.session_db import SessionDB as _SessionDB
            rev_limit_threshold_pct = _SessionDB().get_rev_limit_threshold_for_car(car_name)
        except Exception:
            pass
    try:
        from data.track_model_resolver import build_resolved_track_context_for_prompt
        return build_resolved_track_context_for_prompt(
            track_location_id,
            layout_id,
            rev_limit_threshold_pct=rev_limit_threshold_pct,
            active_car_name=car_name,
        )
    except Exception as exc:
        return (
            "## Track Intelligence\n"
            f"Track Intelligence unavailable: resolver error "
            f"({type(exc).__name__}: {exc}). Use general track knowledge only."
        )
