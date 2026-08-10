"""Owner-baseline service — thin caller that fetches DB data and drives the pure arbiter.

This module is the ONLY server-side entry point for the owner-baseline proposal
pipeline (Part B). It:

  1. Fetches the session run, session meta, laps, feedback and owner baseline from DB.
  2. Builds TWO setup diagnoses — one with all clean laps (telemetry) and one with
     ``laps=[]`` (feedback only) — using the existing ``build_setup_diagnosis`` helper.
  3. Calls ``run_rule_engine`` twice, passing the owner baseline as the ``setup=``
     argument both times (so the engine evaluates modifications to the owner's own values).
  4. Passes both plans to the pure arbiter (``build_owner_proposals``).
  5. Saves the resulting proposals to the DB via ``save_owner_proposal``.

Advisory-only: nothing is applied. No UI, no Qt, no threads. Never raises.

The "two-plan" pattern is identical to the one explained in the brief: we call
the rule engine with real laps (telemetry plan) and again with laps=[] (feedback
plan). The arbiter compares the two plans' proposed directions per field to detect
corroboration / contradiction / unresolved riders — without needing to know any
rule-to-feel-flag internal mappings.
"""
from __future__ import annotations

import types
from typing import Optional, Sequence


# ---------------------------------------------------------------------------
# Min-lap constant — mirrors data.session_db.MIN_EVIDENCE_CLEAN_LAPS
# ---------------------------------------------------------------------------
_MIN_CLEAN_LAPS_TELEMETRY = 5  # telemetry primary threshold (TELEMETRY_PRIMARY_THRESHOLD)


def _lap_dict_to_ns(row: dict) -> types.SimpleNamespace:
    """Convert a lap_record DB dict to a SimpleNamespace compatible with build_setup_diagnosis.

    build_setup_diagnosis uses ``getattr(l, "field_name", default)`` throughout,
    so a SimpleNamespace is accepted anywhere a LapStats object is expected.
    Fields not in the DB row default to 0 / 0.0 / [] so all getattr calls succeed.
    """
    return types.SimpleNamespace(
        lap_num=int(row.get("lap_num") or 0),
        lap_time_ms=int(row.get("lap_time_ms") or 0),
        lock_up_count=int(row.get("lock_up_count") or 0),
        wheelspin_count=int(row.get("wheelspin_count") or 0),
        brake_consistency_m=float(row.get("brake_consistency_m") or 0.0),
        max_speed_kmh=float(row.get("max_speed_kmh") or 0.0),
        avg_throttle_pct=float(row.get("avg_throttle_pct") or 0.0),
        avg_brake_pct=float(row.get("avg_brake_pct") or 0.0),
        oversteer_count=int(row.get("oversteer_count") or 0),
        oversteer_throttle_on_count=int(row.get("oversteer_throttle_on") or 0),
        kerb_count=int(row.get("kerb_count") or 0),
        bottoming_count=int(row.get("bottoming_count") or 0),
        snap_throttle_count=int(row.get("snap_throttle_count") or 0),
        max_lat_g=float(row.get("max_lat_g") or 0.0),
        spin_count=int(row.get("spin_count") or 0),
        tyre_temp_fl_avg=float(row.get("tyre_temp_fl_avg") or 0.0),
        tyre_temp_fr_avg=float(row.get("tyre_temp_fr_avg") or 0.0),
        tyre_temp_rl_avg=float(row.get("tyre_temp_rl_avg") or 0.0),
        tyre_temp_rr_avg=float(row.get("tyre_temp_rr_avg") or 0.0),
        rev_limiter_count=0,
        rev_limiter_by_gear={},
        frames=[],  # no frame-level data in lap_record rows
        is_pit_lap=bool(row.get("is_pit_lap")),
        is_out_lap=bool(row.get("is_out_lap")),
    )


def _count_clean_laps(lap_ns_list: list) -> int:
    """Count laps that are neither pit laps, out laps, nor spin laps."""
    return sum(
        1 for l in lap_ns_list
        if not getattr(l, "is_pit_lap", False)
        and not getattr(l, "is_out_lap", False)
        and getattr(l, "spin_count", 0) == 0
        and getattr(l, "lap_time_ms", 0) > 0
    )


def run_for_session(
    db,
    *,
    session_run_id: str,
    discipline: str,
) -> dict:
    """Build and persist owner-baseline proposals for one recorded session.

    The caller must ensure that:
      - An owner baseline has been entered for this event + discipline before
        calling this function.  If none exists, returns immediately with no proposals.
      - ``session_run_id`` corresponds to a completed ("complete") Practice session.
        On a Qualifying session the caller should pass discipline="qualifying".
        The function does not enforce session_type here — the caller (the backend
        dispatcher / the coordinator) applies that gate.

    Returns a plain dict:
    ``{ok, proposals_saved, unresolved_count, suppressed_count, error}``
    Never raises.
    """
    result: dict = {
        "ok": False, "proposals_saved": 0,
        "unresolved_count": 0, "suppressed_count": 0, "error": "",
    }
    try:
        return _run_inner(db, session_run_id=str(session_run_id or ""),
                          discipline=str(discipline or ""))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def _run_inner(db, *, session_run_id: str, discipline: str) -> dict:
    """Inner implementation — may raise; always wrapped by run_for_session."""
    from strategy.setup_diagnosis import build_setup_diagnosis
    from strategy.setup_driver_profile import build_driver_profile
    from strategy.setup_ranges import resolve_ranges
    from strategy.setup_rule_engine import run_rule_engine
    from strategy.owner_baseline_arbiter import build_owner_proposals

    result: dict = {
        "ok": False, "proposals_saved": 0,
        "unresolved_count": 0, "suppressed_count": 0, "error": "",
    }

    # --- 1. Resolve session run ---
    run = db.get_session_run(session_run_id)
    if not run:
        result["error"] = f"session_run_id={session_run_id!r} not found"
        return result

    session_id = int(run.get("session_id") or 0)
    event_id = int(run.get("event_id") or 0)

    # --- 2. Resolve session meta (car, track) ---
    meta = db.get_session_meta(session_id) if session_id else None
    if not meta:
        result["error"] = f"no session meta for session_id={session_id}"
        return result

    car_id = int(meta.get("car_id") or 0)
    car_name = str(meta.get("car_name") or "")
    track = str(meta.get("track") or "")

    # --- 3. Fetch the owner baseline ---
    owner_baseline = db.get_owner_baseline(event_id, discipline)
    if not owner_baseline:
        result["error"] = (
            f"no owner baseline entered for event_id={event_id}, discipline={discipline!r}"
        )
        return result
    baseline_revision = db.get_owner_baseline_revision(event_id, discipline)

    # Strip the bookkeeping keys (baseline_revision, provenance) that save_owner_baseline
    # adds — the rule engine only sees genuine setup parameter keys.
    setup_for_engine = {
        k: v for k, v in owner_baseline.items()
        if k not in ("baseline_revision", "provenance")
    }

    # --- 4. Fetch and classify laps ---
    raw_laps = db.get_session_laps(session_id) if session_id else []
    all_ns = [_lap_dict_to_ns(r) for r in (raw_laps or [])]

    # Clean laps: exclude pit, out, and spin laps.
    clean_ns = [
        l for l in all_ns
        if not getattr(l, "is_pit_lap", False)
        and not getattr(l, "is_out_lap", False)
        and getattr(l, "spin_count", 0) == 0
        and getattr(l, "lap_time_ms", 0) > 0
    ]
    clean_laps = len(clean_ns)

    # --- 5. Fetch the most recent feedback for this session ---
    feedback_row = db.get_feedback_for_session(session_id) if session_id else None
    feedback_dict: Optional[dict] = dict(feedback_row) if feedback_row else None

    # --- 6. Build event_ctx ---
    event_ctx: dict = {
        "track": track,
        "layout_id": str(meta.get("config_id") or ""),
        "track_location_id": "",
        "location_confidence": "low",  # conservative — no live sensor
    }

    # --- 7. Build ranges and driver profile ---
    ranges = resolve_ranges(car_name)
    profile = build_driver_profile()

    # --- 8. Build the telemetry diagnosis (full laps + feedback) ---
    telemetry_diagnosis = build_setup_diagnosis(
        clean_ns,
        setup_for_engine,
        car_name,
        event_ctx,
        feeling=None,  # structured feedback carries the signal
        feedback=feedback_dict,
    )

    # --- 9. Build the feedback-only diagnosis (laps=[]) ---
    # This represents what driver feedback ALONE implies, independent of telemetry.
    feedback_diagnosis = build_setup_diagnosis(
        [],  # deliberate: no laps — feedback signal only
        setup_for_engine,
        car_name,
        event_ctx,
        feeling=None,
        feedback=feedback_dict,
    )

    # --- 10. Run the rule engine twice ---
    telemetry_plan = run_rule_engine(
        telemetry_diagnosis,
        setup_for_engine,
        ranges,
        profile,
        car=str(car_id) if car_id else "",
        track=track,
    )
    feedback_plan = run_rule_engine(
        feedback_diagnosis,
        setup_for_engine,
        ranges,
        profile,
        car=str(car_id) if car_id else "",
        track=track,
    )

    # --- 11. Get parameter model and suppression keys ---
    parameter_model = None
    try:
        from data.car_parameter_model import resolve_parameter_model
        parameter_model = resolve_parameter_model(car_name)
    except Exception:
        pass

    suppression_keys = frozenset()
    try:
        suppression_keys = db.get_rejected_proposal_suppression_keys(event_id, discipline)
    except Exception:
        pass

    # --- 12. Build proposals ---
    proposals, suppressed, unresolved = build_owner_proposals(
        clean_laps=clean_laps,
        telemetry_plan=telemetry_plan,
        feedback_plan=feedback_plan,
        owner_baseline=setup_for_engine,
        parameter_model=parameter_model,
        discipline=discipline,
        baseline_revision=baseline_revision,
        session_run_id=session_run_id,
        event_id=event_id,
        suppression_keys=suppression_keys,
    )

    # --- 13. Persist proposals to DB ---
    saved = 0
    for prop in proposals:
        pid = db.save_owner_proposal(event_id, prop.as_dict())
        if pid:
            saved += 1

    result.update({
        "ok": True,
        "proposals_saved": saved,
        "unresolved_count": len(unresolved),
        "suppressed_count": len(suppressed),
    })
    return result


def get_proposals_for_event(db, event_id: int) -> list:
    """Return all proposals for an event. Thin delegation — never raises."""
    try:
        return db.get_owner_proposals_for_event(int(event_id or 0))
    except Exception:
        return []


def accept_proposal(db, proposal_id: str) -> bool:
    """Accept a proposal. Never raises."""
    try:
        return db.update_proposal_status(str(proposal_id or ""), "accepted")
    except Exception:
        return False


def reject_proposal(db, proposal_id: str, reason: str = "") -> bool:
    """Reject a proposal. Never raises."""
    try:
        return db.update_proposal_status(str(proposal_id or ""), "rejected",
                                         rejection_reason=str(reason or ""))
    except Exception:
        return False


def edit_proposal(db, proposal_id: str, edit_value: float, reason: str = "") -> bool:
    """Accept a proposal with an edited value (driver override). Never raises."""
    try:
        return db.update_proposal_status(
            str(proposal_id or ""), "edited",
            edit_value=float(edit_value),
            rejection_reason=str(reason or ""),
        )
    except Exception:
        return False
