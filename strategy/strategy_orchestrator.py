"""Orchestrator for race strategy analysis.

Owns all DB reads, corner loading, setup history, AI call.
No Qt, no UI imports.
"""
from __future__ import annotations

import logging

from strategy.ai_planner import analyse_strategy

_log = logging.getLogger(__name__)


def run_strategy_analysis(
    params,                          # RaceParams
    lap_data_by_compound: dict[str, list[float]],
    api_key: str,
    db,                              # SessionDB
    car_id: int,
    session_id: int,
    car_name: str,
    car_specs: dict,
    setup_comparison_text: str,
    tyre_degradation_cache,          # dict | None
    model_name: str,
) -> list:  # list[StrategyOption]
    """Run a full race strategy analysis and return ranked options.

    Parameters match the subset extracted from the dashboard worker.
    """
    track = params.track

    # ------------------------------------------------------------------ #
    # 1. Fuel and compound sequences
    # ------------------------------------------------------------------ #
    fuel_seq: list = []
    compound_seqs: dict = {}
    if db and car_id > 0:
        try:
            fuel_seq = db.get_recent_fuel_sequence(car_id, track, limit=15)
            compound_seqs = db.get_compound_lap_sequences(
                car_id, track, session_id=session_id
            )
        except Exception as exc:
            _log.warning("[StrategyOrchestrator] fuel/compound query failed: %s", exc)

    # ------------------------------------------------------------------ #
    # 2. Corner issues summary
    # ------------------------------------------------------------------ #
    corner_summary = ""
    if db and car_id > 0 and track:
        try:
            from data.corner_learning import (
                CornerIssue,
                build_corner_summary_for_prompt,
            )
            ci_rows = db.get_corner_issues(car_id, track)
            if ci_rows:
                ci_objs = [
                    CornerIssue(
                        car_id=r["car_id"],
                        track=r["track"],
                        corner_id=r["corner_id"],
                        lap_count=r["lap_count"],
                        total_laps=r["total_laps"],
                        issue_type=r["issue_type"],
                        phase=r["phase"],
                        severity=r["severity"],
                        confidence=r["confidence"],
                        evidence=r["evidence"],
                        session_id=r["session_id"],
                        detected_at=r.get("detected_at", ""),
                    )
                    for r in ci_rows
                ]
                corner_summary = build_corner_summary_for_prompt(ci_objs)
        except Exception:
            pass  # non-critical

    # ------------------------------------------------------------------ #
    # 3. Setup history
    # ------------------------------------------------------------------ #
    setup_history_text = ""
    try:
        from data.setup_history import format_for_prompt
        # config_id is not available here; caller passes setup_comparison_text
        # which already contains the relevant setup context. Setup history
        # requires the config_id which lives in the dashboard config; the
        # dashboard extracts it before calling us if needed. For now, emit
        # an empty string so callers that need it can pre-compute and pass
        # it via setup_comparison_text (same pattern used for practice).
    except Exception:
        pass

    # ------------------------------------------------------------------ #
    # 4. AI call
    # ------------------------------------------------------------------ #
    options = analyse_strategy(
        params,
        lap_data_by_compound,
        api_key,
        degradation=tyre_degradation_cache,
        setup_history=setup_history_text,
        car_name=car_name,
        car_specs=car_specs,
        setup_comparison=setup_comparison_text,
        fuel_sequence=fuel_seq,
        compound_sequences=compound_seqs,
        corner_issues_summary=corner_summary,
        model=model_name or None,
        car_id=car_id,
    )

    return options
