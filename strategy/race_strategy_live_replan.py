"""Group 53 — Race Strategy Brain Phase 7: live replan snapshot runner.

Combines the pre-race Race Plan result + a live current-state source (via the
Group 53 adapter) + the Group 52 ``build_replan_snapshot`` into a single, read-only,
advisory-only ``LiveReplanResult`` for the Strategy Builder to display.

SAFETY (unchanged from Group 52)
  Advisory only. It makes no pit call, sends no driver command, changes no setup,
  writes nothing, needs no API key, and invents no live state. Unknown tyre/fuel
  state is never treated as safe; missing critical state → INSUFFICIENT_EVIDENCE.
  Pure: no Qt, no DB, no I/O, never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from strategy.race_strategy_replan import (
    RaceReplanState,
    RaceReplanReadiness,
    RaceReplanSnapshot,
    ReplanConfidence,
    REPLAN_SAFETY_NOTES,
    assess_replan_readiness,
    build_replan_snapshot,
    render_replan_snapshot_text,
)
from strategy.race_strategy_live_state import (
    LiveReplanStateResult,
    apply_pit_lane_evidence,
    attach_track_progress,
    extract_live_replan_state,
    resolve_live_progress_evidence,
)
from data.live_track_progress import (
    LiveTrackProgressResult,
    TrackProgressConfidence,
    build_track_path_stations,
    format_live_track_progress_evidence,
)
from data.live_track_progress_fallback import (
    FALLBACK_SOURCE,
    format_road_distance_fallback_evidence,
    is_fallback_result,
    resolve_progress_from_road_distance,
)


@dataclass(frozen=True)
class LiveReplanResult:
    """Structured, read-only live replan snapshot for display."""
    state: RaceReplanState
    state_sources: dict
    readiness: RaceReplanReadiness
    snapshot: RaceReplanSnapshot
    driver_message: str
    missing_state: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    safety_notes: tuple[str, ...] = REPLAN_SAFETY_NOTES
    generated_at: str = ""
    # Group 55: pit-lane mapping corroboration (evidence-quality only).
    pit_state_confidence: str = "UNKNOWN"      # raw tracker pit confidence (Group 54)
    pit_evidence_confidence: str = "UNKNOWN"   # combined w/ pit-lane map (Group 55)
    pit_lane_zone: str = "UNKNOWN"
    pit_lane_source: str = "missing"
    pit_lane_mapping_confidence: str = "NONE"
    pit_corroboration: str = "none"
    # Group 56: live world-position → track-progress evidence (or None).
    track_progress: Optional[LiveTrackProgressResult] = None
    # Group 57: approved reference-path provenance (empty when none loaded).
    reference_path_source: str = ""
    reference_path_warnings: tuple = ()

    @property
    def confidence(self) -> ReplanConfidence:
        return self.snapshot.confidence

    @property
    def status(self) -> str:
        s = self.snapshot.current_plan_still_viable
        if s is True:
            return "Current plan still viable"
        if s is False:
            return "Plan needs review"
        return "Insufficient evidence"


def build_live_replan_snapshot(
    *,
    pre_race_result,
    live_source=None,
    live_state: Optional[RaceReplanState] = None,
    state_sources: Optional[dict] = None,
    warnings: Sequence[str] = (),
    event_settings: Optional[dict] = None,
    latest_fuel_samples: Optional[Sequence[float]] = None,
    track_context=None,
    live_progress=None,
    live_position=None,
    reference_stations=None,
    identity_ok: bool = True,
    reference_path_source: str = "",
    reference_path_warnings: Sequence[str] = (),
    lap_distance_m=None,
    road_distance=None,
    lap_length_m=None,
    generated_at: str = "",
) -> LiveReplanResult:
    """Build a read-only live replan snapshot.

    Supply either a ``live_source`` (tracker / dashboard / packet — read via the
    Group 53 adapter) or an explicit ``live_state``. Live fuel burn from the adapter
    is fed to the snapshot as ``latest_fuel_samples`` when the caller supplies none.

    Group 55: when a ``track_context`` (with pit-lane mapping) and a progress value
    are available, pit-event confidence is corroborated against the known pit-lane
    corridor (evidence-quality only — no pit is ever counted or fabricated here).

    Group 56: when ``live_position`` and a reference path (``reference_stations`` or a
    ``track_context`` carrying one) are available, live world position is resolved to
    normalised track progress; MEDIUM/HIGH progress then feeds the Group 55 corroboration
    (LOW/UNKNOWN never lifts pit confidence). An explicit ``live_progress`` overrides.
    ``generated_at`` is caller-supplied (no clock in this pure builder). Never raises.
    """
    try:
        live_fuel_per_lap = 0.0
        extracted: Optional[LiveReplanStateResult] = None
        if live_state is None:
            extracted = extract_live_replan_state(
                live_source, event_settings=event_settings)
            live_state = extracted.state
            if state_sources is None:
                state_sources = extracted.state_sources
            warnings = tuple(warnings) + tuple(extracted.warnings)
            live_fuel_per_lap = extracted.live_fuel_per_lap
        else:
            # Wrap an explicit live_state so pit-lane corroboration still applies.
            extracted = LiveReplanStateResult(state=live_state)
        state_sources = dict(state_sources or {})

        # Group 56: resolve live world position → normalised track progress (primary).
        if live_position is None:
            live_position = _position_from_source(live_source)
        primary: Optional[LiveTrackProgressResult] = None
        if reference_stations or (track_context is not None
                                  and build_track_path_stations(track_context)):
            primary = resolve_live_progress_evidence(
                position=live_position, reference_stations=reference_stations,
                track_context=track_context, identity_ok=identity_ok)

        # Group 58: precedence —
        #   1) usable (MEDIUM/HIGH) approved-reference-path map matching wins;
        #   2) else road-distance fallback, if it yields progress;
        #   3) else the primary's honest LOW/UNKNOWN result (or fallback UNKNOWN).
        # Fallback NEVER overrides a usable map-matched result and NEVER lifts pit conf.
        progress_result: Optional[LiveTrackProgressResult] = primary
        primary_usable = bool(primary is not None and primary.confidence in (
            TrackProgressConfidence.MEDIUM, TrackProgressConfidence.HIGH))
        if not primary_usable and (lap_distance_m is not None or road_distance is not None):
            fb = resolve_progress_from_road_distance(
                lap_distance_m=lap_distance_m, road_distance=road_distance,
                lap_length_m=lap_length_m, identity_ok=identity_ok,
                track_id=(track_context or {}).get("track_id") if isinstance(track_context, dict) else None,
                layout_id=(track_context or {}).get("layout_id") if isinstance(track_context, dict) else None,
            )
            if fb.has_progress:
                progress_result = fb
            elif primary is None or not primary.has_progress:
                # Keep whichever carries the more useful honest message.
                progress_result = primary if (primary is not None and primary.message) else fb
        if progress_result is not None:
            extracted = attach_track_progress(extracted, progress_result)

        # Group 55: corroborate pit evidence against the track's pit-lane mapping.
        # (apply_pit_lane_evidence consumes MEDIUM/HIGH track progress when
        #  ``live_progress`` is not supplied explicitly.)
        extracted = apply_pit_lane_evidence(
            extracted, track_context=track_context, live_progress=live_progress)
        warnings = tuple(warnings) + tuple(
            w for w in extracted.warnings if w not in warnings)

        readiness = assess_replan_readiness(live_state)

        if latest_fuel_samples is None and live_fuel_per_lap > 0:
            latest_fuel_samples = [live_fuel_per_lap]

        snapshot = build_replan_snapshot(
            pre_race_result=pre_race_result,
            state=live_state,
            event_settings=event_settings,
            latest_fuel_samples=latest_fuel_samples,
        )

        missing = tuple(snapshot.missing_state or readiness.missing_state)
        return LiveReplanResult(
            state=live_state,
            state_sources=state_sources,
            readiness=readiness,
            snapshot=snapshot,
            driver_message=snapshot.driver_message,
            missing_state=missing,
            warnings=tuple(warnings),
            safety_notes=snapshot.safety_notes,
            generated_at=str(generated_at or ""),
            pit_state_confidence=extracted.pit_state_confidence,
            pit_evidence_confidence=extracted.pit_evidence_confidence,
            pit_lane_zone=extracted.pit_lane_zone,
            pit_lane_source=extracted.pit_lane_source,
            pit_lane_mapping_confidence=extracted.pit_lane_mapping_confidence,
            pit_corroboration=extracted.pit_corroboration,
            track_progress=extracted.track_progress,
            reference_path_source=str(reference_path_source or ""),
            reference_path_warnings=tuple(reference_path_warnings or ()),
        )
    except Exception:
        # Absolute fallback — never raise out of the live runner.
        state = live_state if isinstance(live_state, RaceReplanState) else RaceReplanState()
        readiness = assess_replan_readiness(state)
        snapshot = build_replan_snapshot(pre_race_result=pre_race_result, state=state,
                                         event_settings=event_settings)
        return LiveReplanResult(
            state=state, state_sources=dict(state_sources or {}),
            readiness=readiness, snapshot=snapshot,
            driver_message=snapshot.driver_message,
            missing_state=tuple(snapshot.missing_state),
            warnings=tuple(warnings) + ("live replan fallback engaged",),
            safety_notes=snapshot.safety_notes, generated_at=str(generated_at or ""),
        )


def render_live_replan_text(result: LiveReplanResult) -> str:
    """Plain-text advisory rendering of a live replan result (incl. pit/tyre state)."""
    lines = ["Live Replan Snapshot", f"Status: {result.status}",
             f"Confidence: {result.confidence.value}"]
    if result.driver_message:
        lines.append(f"Reason: {result.driver_message}")

    # Group 54: honest live-state breakdown (found + missing, with provenance).
    st = result.state
    srcs = dict(result.state_sources or {})
    found: list[str] = []
    if st.current_lap is not None:
        found.append(f"current lap: {st.current_lap}")
    if st.fuel_remaining_pct is not None:
        found.append(f"fuel remaining: {st.fuel_remaining_pct:.0f}%")
    if st.current_compound:
        found.append(f"current compound: {st.current_compound}")
    if st.tyre_age_laps is not None:
        found.append(f"laps since pit: {st.tyre_age_laps} ({srcs.get('tyre_age_laps', 'live')})")
    if st.pit_stops_completed is not None:
        found.append(f"pit stops completed: {st.pit_stops_completed} ({srcs.get('pit_stops_completed', 'live')})")

    # Group 57: approved reference-path provenance (loaded from disk, read-only).
    missing_extra: list[str] = []
    prog_warnings: list[str] = []
    if result.reference_path_source:
        found.append(f"reference path: loaded ({_ref_source_label(result.reference_path_source)})")
    for w in (result.reference_path_warnings or ()):
        wl = w.lower()
        if "unavailable" in wl or "no usable stations" in wl:
            if w not in missing_extra:
                missing_extra.append(w)
        elif w not in prog_warnings:
            prog_warnings.append(w)

    # Group 56/58: track-progress evidence — map-matched (primary) OR road-distance
    # fallback (clearly labelled approximate / lower confidence).
    tp = result.track_progress
    if tp is not None:
        if is_fallback_result(tp):
            ev = format_road_distance_fallback_evidence(tp)
        else:
            ev = format_live_track_progress_evidence(tp)
        found.extend(ev.get("found", []))
        missing_extra.extend(ev.get("missing", []))
        prog_warnings.extend(ev.get("warnings", []))
        # Group 59: when fallback is active, disclose the (unvalidated) road-distance
        # zero-point assumption honestly — the confidence stays capped regardless.
        if is_fallback_result(tp) and getattr(tp, "has_progress", False):
            found.append("road-distance semantics: cumulative behaviour assumed "
                         "from lap-start reference")
            found.append("zero-point validation: insufficient evidence "
                         "(per-track validation pending)")
            prog_warnings.append(
                "road-distance fallback using unconfirmed cumulative semantics — "
                "progress remains approximate and confidence capped")
        # Only map-matched (non-fallback) progress can corroborate the pit lane.
        if (not is_fallback_result(tp)) and getattr(tp, "usable_for_pit", False) and \
                str(result.pit_corroboration or "none") not in (
                    "none", "no_mapping", "position_unknown"):
            found.append("pit-lane map used live track progress")

    # Group 55: pit-lane mapping corroboration (evidence-quality only).
    zone = str(result.pit_lane_zone or "UNKNOWN")
    corr = str(result.pit_corroboration or "none")
    if corr == "no_mapping":
        missing_extra.append("pit-lane map unavailable for this track/layout")
    elif corr == "position_unknown":
        # Group 58: distinguish "no progress at all" from "only fallback progress"
        # (fallback progress is display-only and never corroborates the pit lane).
        if is_fallback_result(tp) and getattr(tp, "has_progress", False):
            missing_extra.append(
                "pit-lane corroboration needs approved reference-path progress "
                "(road-distance fallback is not used to corroborate pits)")
        else:
            missing_extra.append("live track progress unavailable")
        if result.pit_state_confidence in ("MEDIUM", "LOW"):
            missing_extra.append("pit event not corroborated by track position")
    else:
        found.append(f"pit lane zone: {_zone_label(zone)} (track model)")
        if corr == "corroborated":
            found.append("pit detection corroborated by pit-lane map")
        elif corr == "not_corroborated" and result.pit_state_confidence in ("MEDIUM", "LOW"):
            missing_extra.append("pit event not corroborated by track position")
    if result.pit_evidence_confidence not in ("UNKNOWN", ""):
        found.append(f"pit confidence: {str(result.pit_evidence_confidence).lower()}")

    if found:
        lines.append("Found:")
        lines.extend(f"  - {f}" for f in found)
    missing_all = list(result.missing_state) + [m for m in missing_extra
                                                if m not in result.missing_state]
    if missing_all:
        lines.append("Missing:")
        lines.extend(f"  - {m}" for m in missing_all)

    # Surface honest warnings: pit-lane contradiction + track-progress cautions.
    warn_lines: list[str] = []
    for w in result.warnings:
        if "did not match pit-lane mapping" in w.lower():
            warn_lines.append(w)
    for w in prog_warnings:
        if w not in warn_lines:
            warn_lines.append(w)
    for w in warn_lines:
        lines.append(f"Warning: {w}")

    lines.append(render_replan_snapshot_text(result.snapshot))
    return "\n".join(lines)


def _position_from_source(source):
    """Best-effort live world position (x, y, z[, speed]) from a live source. None-safe.

    Reads the tracker's read-only ``live_world_position`` (Group 56), else a
    dashboard's ``_tracker``/``_last_packet``, else a packet's pos_x/pos_y/pos_z.
    Never raises.
    """
    try:
        if source is None:
            return None
        pos = getattr(source, "live_world_position", None)
        if pos:
            return pos
        tracker = getattr(source, "_tracker", None)
        if tracker is not None:
            pos = getattr(tracker, "live_world_position", None)
            if pos:
                return pos
        packet = getattr(source, "_last_packet", None) or source
        if all(hasattr(packet, a) for a in ("pos_x", "pos_y", "pos_z")):
            spd = getattr(packet, "speed_kmh", None)
            return (float(packet.pos_x), float(packet.pos_y), float(packet.pos_z),
                    float(spd) if spd is not None else 0.0)
        return None
    except Exception:
        return None


def _ref_source_label(source: str) -> str:
    return {
        "approved_track_model": "approved track model",
        "calibration_reference_path": "calibration reference path",
        "track_library": "track library",
        "missing": "unavailable",
        "malformed": "malformed",
    }.get(str(source).strip().lower(), str(source).replace("_", " ").strip() or "track model")


def _zone_label(zone: str) -> str:
    return {
        "PIT_ENTRY": "pit entry",
        "PIT_LANE": "pit lane",
        "PIT_EXIT": "pit exit",
        "NOT_PIT_LANE": "on track (not pit lane)",
        "UNKNOWN": "unknown",
    }.get(str(zone).upper(), str(zone).lower())


# ---------------------------------------------------------------------------
# Porsche RSR / Fuji live-state fixtures (pure helper data — test/UAT only)
# ---------------------------------------------------------------------------

def fuji_live_state_healthy() -> RaceReplanState:
    """Lap 12, fuel tracking within range, RM, tyre age known, one-stop viable."""
    return RaceReplanState(
        current_lap=12, elapsed_time_seconds=1200.0, remaining_laps=18,
        remaining_time_seconds=1800.0, fuel_remaining_pct=60.0,
        current_compound="RM", tyre_age_laps=12, pit_stops_completed=0,
        required_compounds_used=(), weather_status="dry", damage_status="none",
        safety_car_status="green",
    )


def fuji_live_state_fuel_short() -> RaceReplanState:
    """Lap 12, fuel BELOW expected for the planned one-stop → needs review."""
    return RaceReplanState(
        current_lap=12, elapsed_time_seconds=1200.0, remaining_laps=18,
        remaining_time_seconds=1800.0, fuel_remaining_pct=8.0,
        current_compound="RM", tyre_age_laps=12, pit_stops_completed=0,
    )


def fuji_live_state_missing() -> RaceReplanState:
    """Current lap known, but fuel / compound / remaining distance unknown."""
    return RaceReplanState(current_lap=12)


# --- Group 54: pit/tyre-age fixtures ---------------------------------------

def fuji_live_state_pre_pit_healthy() -> RaceReplanState:
    """Before any pit: lap 12, tyre age = 12 (tracked, certain), pit stops = 0.

    With tyre age + pit count known, replan confidence can rise above LOW.
    """
    return RaceReplanState(
        current_lap=12, elapsed_time_seconds=1200.0, remaining_laps=18,
        remaining_time_seconds=1800.0, fuel_remaining_pct=60.0,
        current_compound="RM", tyre_age_laps=12, pit_stops_completed=0,
    )


def fuji_live_state_just_pitted() -> RaceReplanState:
    """Just after a pit: lap 18, fresh tyres (age 1), pit stops = 1, RS compound."""
    return RaceReplanState(
        current_lap=18, elapsed_time_seconds=1800.0, remaining_laps=12,
        remaining_time_seconds=1200.0, fuel_remaining_pct=95.0,
        current_compound="RS", tyre_age_laps=1, pit_stops_completed=1,
    )


def fuji_live_state_missing_pit() -> RaceReplanState:
    """Fuel + lap + distance known, but tyre age + pit count unknown → LOW confidence."""
    return RaceReplanState(
        current_lap=12, fuel_remaining_pct=54.0, current_compound="RM",
        remaining_laps=18, remaining_time_seconds=1800.0,
    )


# --- Group 55: Fuji pit-lane mapping fixture (test/UAT only — NOT production data) ---

def fuji_pit_lane_mapping() -> dict:
    """A minimal, illustrative Fuji Full Course pit-lane mapping (test fixture only).

    The repo has no Fuji track-library entry, so this lives as a helper fixture and
    is NOT written to disk. Progress values are approximate corridor bounds (0–1):
    entry just before the line, body across it, exit just after — the exit span
    wraps past the start/finish line to exercise wrapped-range handling.
    """
    return {
        "track_id": "fuji_speedway",
        "layout_id": "full_course",
        "pit_lane": {
            "available": True,
            "source": "track_library",
            "segments": [
                {"zone": "pit_entry", "start_progress": 0.935, "end_progress": 0.955,
                 "label": "Pit entry"},
                {"zone": "pit_lane", "start_progress": 0.955, "end_progress": 0.985,
                 "label": "Pit lane"},
                {"zone": "pit_exit", "start_progress": 0.985, "end_progress": 0.025,
                 "label": "Pit exit"},
            ],
        },
    }


# --- Group 56: Fuji reference-path fixture (test/UAT only — NOT production data) ---

def fuji_reference_path(lap_length_m: float = 4563.0, n: int = 200) -> dict:
    """A minimal circular Fuji-length reference path (test fixture only, NOT on disk).

    Returns a track_context dict carrying a ``reference_path`` of evenly-spaced
    stations around a circle of the given lap length, so the Group 56 resolver can
    convert an (x, z) position into normalised progress deterministically.
    """
    import math as _m
    r = lap_length_m / (2.0 * _m.pi)
    points = []
    for i in range(n + 1):
        prog = i / n
        theta = 2.0 * _m.pi * prog
        points.append({
            "x": r * _m.cos(theta),
            "y": 0.0,
            "z": r * _m.sin(theta),
            "distance_along_lap_m": prog * lap_length_m,
            "lap_progress": prog,
        })
    return {
        "track_id": "fuji_speedway",
        "layout_id": "full_course",
        "reference_path": {"points": points},
    }


def fuji_position_at_progress(progress: float, lap_length_m: float = 4563.0) -> tuple:
    """World (x, y, z) on the Fuji reference circle at a given progress (test helper)."""
    import math as _m
    r = lap_length_m / (2.0 * _m.pi)
    theta = 2.0 * _m.pi * (progress % 1.0)
    return (r * _m.cos(theta), 0.0, r * _m.sin(theta))
