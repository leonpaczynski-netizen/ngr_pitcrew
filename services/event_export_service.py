"""Event export service — thin caller for the pure export spec builder.

CORRECTION 1 compliance: this module handles ALL database access for the export.
The pure spec builder in ``strategy/event_export_spec.py`` is never given a DB
handle — it receives pre-fetched plain dicts only.

This service:
  1. Fetches event identity, owner baselines, proposals, unresolved riders and
     suppressed changes from DB.
  2. Resolves ``scope_fingerprint`` (``EngineeringContextKey.scope_fingerprint()``)
     and per-discipline ``MemoryContextKey.key()`` values.
  3. Builds a ``generated_at_human`` timestamp (ISO — excluded from the content
     fingerprint by the spec builder).
  4. Calls ``build_event_export_spec`` with the pre-fetched data.
  5. Returns the spec dict to the caller; file I/O is done separately by
     ``data/event_export_writer.py``.

Never raises. No Qt. No AI. No side-effects other than DB reads.
"""
from __future__ import annotations

from datetime import datetime, timezone


def build_export_for_event(
    db,
    event_id: int,
    *,
    car: str = "",
    track: str = "",
    layout_id: str = "",
) -> dict:
    """Assemble the complete event export spec dict. Never raises.

    Parameters
    ----------
    db
        ``SessionDB`` instance — the ONLY DB access point in this module.
    event_id
        Integer event id.
    car, track, layout_id
        Optional override strings.  When supplied, these override what is
        fetched from the events table (useful when the caller already has
        the resolved values).  If absent, the function resolves them from
        the events table.

    Returns
    -------
    dict with all ``SCHEMA_KEY_ORDER`` fields as per ``build_event_export_spec``.
    ``ok`` is not a key — the spec always has at least an empty ``proposals``
    list; callers check ``content_fingerprint != ""`` for a write-ready spec.
    """
    try:
        return _build_inner(db, int(event_id or 0),
                            car=str(car or ""), track=str(track or ""),
                            layout_id=str(layout_id or ""))
    except Exception:
        from strategy.event_export_spec import _empty_spec
        return _empty_spec(int(event_id or 0), str(car or ""))


def _build_inner(db, event_id: int, *, car: str, track: str, layout_id: str) -> dict:
    """Inner implementation — may raise; always wrapped by build_export_for_event."""
    from strategy.event_export_spec import build_event_export_spec, export_filename
    from data.engineering_context_key import EngineeringContextKey
    from strategy.development_history import MemoryContextKey

    # --- Resolve event identity from DB if not supplied ----
    event_name = str(car or "")  # fallback
    event_row = db.get_event_by_id(event_id)
    if event_row:
        event_name = str(event_row.get("name") or "")
        if not car:
            car = str(event_row.get("car") or "")
        if not track:
            track = str(event_row.get("track") or "")

    # --- Owner baselines ---
    race_baseline = db.get_owner_baseline(event_id, "race")
    qual_baseline = db.get_owner_baseline(event_id, "qualifying")
    owner_baselines: dict = {
        "race": race_baseline,
        "qualifying": qual_baseline,
    }

    # --- Proposals ---
    raw_proposals = db.get_owner_proposals_for_event(event_id)
    proposals = [p for p in (raw_proposals or [])]

    # --- Unresolved riders (C1/I5 fix) ---
    # B9 riders (feedback at 5+ laps on fields telemetry is SILENT on) are fetched
    # from the dedicated owner_baseline_riders table, NOT filtered from proposals.
    # Proposals with status="unresolved" are B11 contradictions (telemetry and
    # feedback oppose each other on the SAME field) — a structurally different concept
    # that remains in the proposals list with its status intact.
    unresolved_riders = db.get_owner_riders_for_event(event_id)

    # --- Suppressed changes (C3 fix) ---
    # B16 suppressed changes are fetched from the dedicated
    # owner_baseline_suppressed_changes table.  Nothing silently disappears.
    suppressed_changes = db.get_suppressed_changes_for_event(event_id)

    # --- Session evidence ---
    session_runs = db.get_session_runs_for_event(event_id)
    session_evidence: list = []
    for run in (session_runs or []):
        session_id = int(run.get("session_id") or 0)
        session_type = str(run.get("session_type") or "")
        run_id = str(run.get("run_id") or "")
        clean_lap_count = 0
        feedback_signals: dict = {}
        if session_id:
            try:
                laps = db.get_session_laps(session_id,
                                           exclude_pit=True, exclude_out=True)
                clean_lap_count = len([
                    l for l in laps
                    if int(l.get("spin_count") or 0) == 0
                    and int(l.get("lap_time_ms") or 0) > 0
                ])
            except Exception:
                pass
            try:
                fb = db.get_feedback_for_session(session_id)
                if fb:
                    feedback_signals = {
                        k: str(fb.get(k) or "")
                        for k in (
                            "corner_entry", "mid_corner", "exit_stability",
                            "rear_braking", "traction", "rotation",
                        )
                        if fb.get(k)
                    }
            except Exception:
                pass
        session_evidence.append({
            "session_run_id": run_id,
            "session_type": session_type,
            "discipline": _session_type_to_discipline(session_type),
            "clean_lap_count": clean_lap_count,
            "feedback_signals": feedback_signals,
        })

    # --- Feedback rows and lap_cov_list for profile evolution (C20) ---
    feedback_rows: list = []
    lap_cov_list: list = []
    try:
        car_id = int(event_row.get("car_id") or 0) if event_row else 0
        if car_id:
            feedback_rows = db.get_recent_feedback(car_id, track, limit=12)
            lap_cov_list = db.get_recent_session_consistency(limit=8, min_laps=3)
    except Exception:
        pass

    # --- scope_fingerprint ---
    # Built from what we know: car_id is not always available from the event row
    # (some events reference the car by name only), so we use the car name as
    # the car_id string, which is accepted by EngineeringContextKey (any non-None
    # string counts as "known").
    scope_fingerprint = ""
    try:
        car_id_str = str(car) if car else None
        track_location_id_str = str(track) if track else None
        layout_id_str = str(layout_id) if layout_id else None
        eck = EngineeringContextKey(
            car_id=car_id_str,
            track_location_id=track_location_id_str,
            layout_id=layout_id_str,
        )
        scope_fingerprint = eck.scope_fingerprint()
    except Exception:
        scope_fingerprint = ""

    # --- memory_context_keys (per discipline) ---
    memory_context_key_race = ""
    memory_context_key_qualifying = ""
    try:
        mck_race = MemoryContextKey(
            car=str(car or ""),
            track=str(track or ""),
            layout_id=str(layout_id or ""),
            discipline="race",
        )
        memory_context_key_race = mck_race.key()
    except Exception:
        pass
    try:
        mck_qual = MemoryContextKey(
            car=str(car or ""),
            track=str(track or ""),
            layout_id=str(layout_id or ""),
            discipline="qualifying",
        )
        memory_context_key_qualifying = mck_qual.key()
    except Exception:
        pass

    # --- generated_at_human (ISO, excluded from fingerprint) ---
    generated_at_human = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # --- Build the spec ---
    spec = build_event_export_spec(
        event_id=event_id,
        event_name=event_name,
        car=car,
        track=track,
        scope_fingerprint=scope_fingerprint,
        memory_context_key_race=memory_context_key_race,
        memory_context_key_qualifying=memory_context_key_qualifying,
        owner_baselines=owner_baselines,
        proposals=proposals,
        unresolved_riders=unresolved_riders,
        suppressed_changes=suppressed_changes,
        session_evidence=session_evidence,
        feedback_rows=feedback_rows,
        lap_cov_list=lap_cov_list,
        generated_at_human=generated_at_human,
    )

    return spec


def export_to_file(
    db,
    event_id: int,
    destination_dir: str,
    *,
    car: str = "",
    track: str = "",
    layout_id: str = "",
    allow_overwrite: bool = False,
) -> dict:
    """Build the spec and write it to ``destination_dir``. Never raises.

    Returns ``EventExportWriteResult.to_dict()``.  The result's ``ok`` field
    indicates success.  ``filename`` is the deterministic name used.
    """
    try:
        from data.event_export_writer import write_event_export
        from strategy.event_export_spec import export_filename

        spec = build_export_for_event(db, event_id, car=car, track=track,
                                       layout_id=layout_id)
        event_name = str(spec.get("event_name") or str(car or ""))
        scope_fp = str(spec.get("scope_fingerprint") or "")
        fname = export_filename(event_name, scope_fp)

        result = write_event_export(
            spec,
            destination_dir,
            fname,
            allow_overwrite=allow_overwrite,
        )
        return result.to_dict()
    except Exception as exc:
        return {
            "ok": False,
            "destination": str(destination_dir or ""),
            "filename": "",
            "file_sha256": "",
            "content_fingerprint": "",
            "bytes_written": 0,
            "warnings": [],
            "errors": [f"{type(exc).__name__}: {exc}"],
        }


def _session_type_to_discipline(session_type: str) -> str:
    """Map a session_type string to a discipline name. Never raises."""
    mapping = {
        "Practice": "practice",
        "Qualifying": "qualifying",
        "Race": "race",
    }
    return mapping.get(str(session_type or ""), str(session_type or "").lower())
