"""Orchestrator for practice session analysis.

Owns all DB reads, corner learning, AI call, recommendation persistence.
No Qt, no UI imports.
"""
from __future__ import annotations

import logging

from strategy.ai_planner import PracticeAnalysis, analyse_practice_session

_log = logging.getLogger(__name__)


def run_practice_analysis(
    params,                         # RaceParams
    lap_data_by_compound: dict[str, list[float]],
    setup_dict: dict,
    car_name: str,
    car_specs: dict,
    setup_comparison_text: str,
    api_key: str,
    db,                             # SessionDB
    car_id: int,
    session_id: int,
    model_name: str,
    session_purpose: str = "",
) -> PracticeAnalysis:
    """Run a full practice session analysis and persist results to DB.

    Parameters match the subset extracted from the dashboard worker.
    Returns the PracticeAnalysis produced by the AI planner.
    """
    track = params.track

    # ------------------------------------------------------------------ #
    # 1. DB context
    # ------------------------------------------------------------------ #
    hist: dict = {}
    driver_feedback_str = ""
    prev_ai_str = ""
    per_lap_telem: list = []
    try:
        hist = db.get_car_track_summary(car_id, track)
        if car_id > 0:
            fb_rows = db.get_recent_feedback(car_id, track, limit=5)
            if fb_rows:
                fb_parts: list[str] = []
                for row in fb_rows:
                    parts = []
                    for k in (
                        "corner_entry", "mid_corner", "exit_stability",
                        "rear_braking", "tyre_condition", "fuel_use", "free_text",
                    ):
                        v = row.get(k, "")
                        if v:
                            parts.append(f"{k}: {v}")
                    if parts:
                        fb_parts.append("- " + "; ".join(parts))
                driver_feedback_str = "\n".join(fb_parts)
            prev_ai_str = db.get_recommendations_for_context(car_id, track, limit=2)
        if session_id > 0:
            per_lap_telem = db.get_session_laps(
                session_id, exclude_pit=True, exclude_out=True, limit=5
            )
        # Resolve session_purpose from DB when the caller did not supply one.
        # The UI will NOT pass anything — the analysed session's stored type
        # is the single source of truth (RF1 approved amendment).
        # Absent / unknown → normalise_purpose yields UNKNOWN → generic block.
        if not session_purpose and session_id > 0:
            session_purpose = db.get_session_type(session_id)
    except Exception:
        hist = {}

    # ------------------------------------------------------------------ #
    # 2. Corner learning (non-critical — degrade silently on failure)
    # ------------------------------------------------------------------ #
    corner_summary = ""
    try:
        from data.corner_learning import (
            detect_issues_from_lap_records,
            verify_fix,
            build_corner_summary_for_prompt,
        )
        if session_id > 0 and car_id > 0 and track:
            all_laps = db.get_session_laps(session_id, exclude_pit=True, exclude_out=True)
            corner_issues = detect_issues_from_lap_records(all_laps, car_id, track, session_id)
            if corner_issues:
                db.save_corner_issues(corner_issues)
            prev_corner_issues = db.get_previous_corner_issues(
                car_id, track, exclude_session_id=session_id
            )
            verifications = verify_fix(prev_corner_issues, corner_issues)
            corner_summary = build_corner_summary_for_prompt(corner_issues, verifications)
    except Exception as exc:
        _log.warning("[PracticeOrchestrator] corner learning failed: %s", exc)

    # ------------------------------------------------------------------ #
    # 3. AI call
    # ------------------------------------------------------------------ #
    result = analyse_practice_session(
        params,
        lap_data_by_compound,
        setup_dict,
        hist,
        api_key,
        car_name=car_name,
        car_specs=car_specs,
        setup_comparison=setup_comparison_text,
        driver_feedback_str=driver_feedback_str,
        prev_ai_str=prev_ai_str,
        per_lap_telemetry=per_lap_telem,
        corner_issues_summary=corner_summary,
        model=model_name or None,
        car_id=car_id,
        session_id=session_id,
        session_purpose=session_purpose,
    )

    # ------------------------------------------------------------------ #
    # 4. Rec parsing
    # ------------------------------------------------------------------ #
    from strategy._rec_parser import parse_recommendations_from_response

    try:
        ai_id = db._conn.execute(
            "SELECT MAX(id) FROM ai_interactions"
        ).fetchone()[0]
    except Exception:
        ai_id = None

    recs_to_save = parse_recommendations_from_response(
        getattr(result, "raw_response", ""),
        "Practice Analysis",
        car_id,
        track,
        layout_id=params.layout_id,
        session_id=session_id,
        ai_interaction_id=ai_id,
    )

    # ------------------------------------------------------------------ #
    # 5. DB writes
    # ------------------------------------------------------------------ #
    if recs_to_save:
        db.insert_setup_recommendations(recs_to_save)
        try:
            issues = db.get_corner_issues(car_id, track)
            issue_ids = [r["id"] for r in (issues or [])]
            rec_ids = db.get_last_recommendation_ids(car_id, track, len(recs_to_save))
            for rec_id in rec_ids:
                db.set_recommendation_corner_issues(rec_id, issue_ids)
        except Exception:
            pass  # non-critical: traceability is best-effort

    # ------------------------------------------------------------------ #
    # 6. Return result
    # ------------------------------------------------------------------ #
    return result
