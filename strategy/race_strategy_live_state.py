"""Group 53 — Race Strategy Brain Phase 7: read-only live current-state adapter.

WHY IT EXISTS
  Group 52 built a pure replan foundation (``RaceReplanState`` +
  ``build_replan_snapshot``) but wired no live source. This module is the one place
  that reads the EXISTING read-only live telemetry / dashboard state and converts
  it into a ``RaceReplanState`` — populating ONLY the fields the app genuinely
  knows and recording everything else as missing.

LIVE-STATE DISCOVERY (what actually exists in this app)
  From ``telemetry.state.RaceStateTracker`` (the live race-state tracker) and the
  last ``GT7Packet``:
    • current_lap            → tracker.laps_recorded (reliable completed-lap count)
    • remaining_time_seconds → tracker.computed_remaining_ms()/1000 (timed races)
    • remaining_laps         → tracker.laps_remaining (lap races)
    • fuel_remaining_pct     → packet.fuel_level / packet.fuel_capacity × 100
    • (live fuel burn rate)  → tracker.avg_fuel_per_lap  (surfaced for the snapshot)
    • current_compound       → tracker._current_compound  (STRATEGY/UI tag, not a
                               packet field — GT7 does not broadcast compound)
  NOT available as structured live data (recorded as MISSING, never invented):
    • tyre_age_laps          — the app does not track laps-on-current-tyres
    • pit_stops_completed    — no live pit-stop counter exists
    • required_compounds_used — not tracked live
    • weather / damage / safety-car status — not structured for replan

WHAT THIS MODULE IS NOT
  • It never raises on partial telemetry, never invents live state, never writes
    files, never calls AI or setup-authoring code, and applies nothing.
  • Unknown tyre / fuel state is NEVER treated as safe — it is recorded as missing
    so the readiness layer can drop confidence.
  • No Qt import; the only inputs are duck-typed live objects the caller already has.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from dataclasses import replace as _dc_replace

from strategy.race_strategy_replan import RaceReplanState
from data.pit_lane_resolver import (
    PitLaneMappingConfidence,
    PitLaneZone,
    build_pit_lane_segments_from_track_context,
    normalise_progress,
    resolve_pit_lane_zone,
    segments_mapping_confidence,
)

# Provenance labels for each populated field.
SRC_LIVE = "live_telemetry"
SRC_LIVE_LOW = "live_telemetry (low confidence — not used)"
SRC_STRATEGY_TAG = "strategy/UI tag"
SRC_MANUAL = "manual input"
SRC_EVENT = "event_setting"
SRC_MISSING = "missing"


@dataclass(frozen=True)
class LiveReplanStateResult:
    """A RaceReplanState built from live data, with provenance + honesty metadata."""
    state: RaceReplanState
    state_sources: dict = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    missing_state: tuple[str, ...] = ()
    live_fuel_per_lap: float = 0.0   # measured live burn (for the snapshot), 0 = unknown
    pit_state_confidence: str = "UNKNOWN"   # HIGH/MEDIUM/LOW/UNKNOWN from the tracker
    # Group 55: pit-lane mapping corroboration (all default to "no evidence yet").
    pit_in_progress: bool = False            # tracker phase == IN_PIT (corroboration context)
    pit_lane_zone: str = "UNKNOWN"           # PitLaneZone value from the track model
    pit_lane_source: str = "missing"         # provenance of the pit-lane mapping
    pit_lane_mapping_confidence: str = "NONE"  # NONE/LOW/MEDIUM/HIGH — trust in the map
    pit_evidence_confidence: str = "UNKNOWN"   # combined pit confidence (may upgrade, capped)
    pit_corroboration: str = "none"          # corroborated/contradicted/position_unknown/no_mapping/...


# Group 55: corroboration outcome labels.
CORR_NONE = "none"
CORR_NO_MAPPING = "no_mapping"
CORR_POSITION_UNKNOWN = "position_unknown"
CORR_CORROBORATED = "corroborated"
CORR_CONTRADICTED = "contradicted"
CORR_NOT_CORROBORATED = "not_corroborated"
CORR_IN_LANE_NO_EVENT = "in_pit_lane_no_event"

# Rank helper for capping the combined pit confidence.
_PIT_CONF_RANK = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
_PIT_CONF_BY_RANK = {v: k for k, v in _PIT_CONF_RANK.items()}


# ---------------------------------------------------------------------------
# Safe numeric helpers (invalid / impossible values are dropped, never guessed)
# ---------------------------------------------------------------------------

def _num(x) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        return v
    except (TypeError, ValueError):
        return None


def _pos_int(x) -> Optional[int]:
    v = _num(x)
    if v is None or v < 0:
        return None
    return int(v)


def _fuel_pct(level, capacity) -> Optional[float]:
    """Fuel remaining % from level+capacity, or None. Impossible values dropped."""
    lv = _num(level)
    cap = _num(capacity)
    if lv is None or cap is None or cap <= 0:
        return None
    pct = lv / cap * 100.0
    if pct < 0.0 or pct > 100.0 + 1e-6:  # impossible → ignore, never clamp-and-pretend
        return None
    return min(100.0, pct)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_replan_state_from_live_packet(
    packet,
    *,
    current_lap=None,
    remaining_laps=None,
    remaining_time_seconds=None,
    current_compound=None,
    event_settings: Optional[dict] = None,
) -> LiveReplanStateResult:
    """Build state from a GT7Packet-like object (fuel_level + fuel_capacity).

    The packet's ``laps_completed`` is NOT used (GT7 flags it unreliable), so
    ``current_lap`` must be supplied explicitly if known. Never raises.
    """
    try:
        fuel_pct = _fuel_pct(getattr(packet, "fuel_level", None),
                             getattr(packet, "fuel_capacity", None))
        return _assemble(
            current_lap=_pos_int(current_lap),
            remaining_laps=_pos_int(remaining_laps),
            remaining_time_seconds=_num(remaining_time_seconds),
            fuel_remaining_pct=fuel_pct,
            current_compound=(str(current_compound).strip() if current_compound else None),
            elapsed_time_seconds=None,
            event_settings=event_settings,
            live_fuel_per_lap=0.0,
        )
    except Exception:
        return _empty_result()


def build_replan_state_from_tracker(
    tracker,
    *,
    packet=None,
    current_compound=None,
    event_settings: Optional[dict] = None,
) -> LiveReplanStateResult:
    """Build state from a RaceStateTracker-like object (+ optional last packet).

    Reads only real fields: laps_recorded, computed_remaining_ms / laps_remaining,
    avg_fuel_per_lap, and (from the packet) fuel_level/fuel_capacity. Compound comes
    from the strategy/UI tag (``_current_compound``) or the explicit arg. tyre age,
    pit-stop count, and required-compound use are NOT tracked → missing. Never raises.
    """
    try:
        current_lap = _pos_int(getattr(tracker, "laps_recorded", None))

        # Remaining distance: timed → seconds; lap race → laps.
        remaining_time = None
        remaining_laps = None
        try:
            rem_ms = tracker.computed_remaining_ms()
            if rem_ms is not None and rem_ms >= 0:
                remaining_time = float(rem_ms) / 1000.0
        except Exception:
            remaining_time = None
        rl = _pos_int(getattr(tracker, "laps_remaining", None))
        if rl and rl > 0:
            remaining_laps = rl

        # Elapsed (timed only, derived from duration - remaining).
        elapsed = None
        try:
            dur_min = float(getattr(tracker, "timed_duration_minutes", 0.0) or 0.0)
            if dur_min > 0 and remaining_time is not None:
                elapsed = max(0.0, dur_min * 60.0 - remaining_time)
        except Exception:
            elapsed = None

        # Fuel % needs a packet (level + capacity); the tracker's litres alone lack capacity.
        fuel_pct = None
        if packet is not None:
            fuel_pct = _fuel_pct(getattr(packet, "fuel_level", None),
                                 getattr(packet, "fuel_capacity", None))

        # Live burn rate (for the snapshot's fuel maths).
        live_burn = _num(getattr(tracker, "avg_fuel_per_lap", None)) or 0.0
        if live_burn < 0:
            live_burn = 0.0

        # Compound: explicit arg wins; else the strategy/UI tag if non-empty.
        comp = current_compound or getattr(tracker, "_current_compound", "") or ""
        comp = str(comp).strip() or None

        # Group 54: pit / tyre-age state from the tracker's read-only pit tracking.
        # HIGH/MEDIUM confidence → use tyre age + pit count (they lift readiness).
        # LOW confidence → keep them MISSING (never lift readiness on a guess) but
        # surface the low-confidence estimate + a warning. UNKNOWN → missing.
        pit_conf = str(getattr(tracker, "pit_state_confidence", "UNKNOWN") or "UNKNOWN")
        pit_in_progress = bool(getattr(tracker, "in_pit", False))
        tyre_age = None
        pit_stops = None
        tyre_pit_source = SRC_MISSING
        pit_warn = None
        if pit_conf in ("HIGH", "MEDIUM"):
            tyre_age = _pos_int(getattr(tracker, "tyre_age_laps", None))
            pit_stops = _pos_int(getattr(tracker, "pit_stops_completed", None))
            tyre_pit_source = SRC_LIVE
        elif pit_conf == "LOW":
            _est = _pos_int(getattr(tracker, "tyre_age_laps", None))
            tyre_pit_source = SRC_LIVE_LOW
            pit_warn = (
                f"Pit/tyre state is LOW confidence (est. {_est} laps since pit) — "
                "not used to raise replan confidence.")

        return _assemble(
            current_lap=current_lap,
            remaining_laps=remaining_laps,
            remaining_time_seconds=remaining_time,
            fuel_remaining_pct=fuel_pct,
            current_compound=comp,
            elapsed_time_seconds=elapsed,
            event_settings=event_settings,
            live_fuel_per_lap=live_burn,
            compound_from_tag=bool(comp),
            tyre_age_laps=tyre_age,
            pit_stops_completed=pit_stops,
            tyre_pit_source=tyre_pit_source,
            pit_state_confidence=pit_conf,
            extra_warning=pit_warn,
            pit_in_progress=pit_in_progress,
        )
    except Exception:
        return _empty_result()


def build_replan_state_from_dashboard_context(
    dashboard,
    *,
    event_settings: Optional[dict] = None,
) -> LiveReplanStateResult:
    """Build state from a dashboard-like object exposing ``_tracker`` + ``_last_packet``.

    Returns an all-missing result (with an explicit warning) when no live tracker is
    present, so the UI can say "live current-state source not available yet". Never raises.
    """
    try:
        tracker = getattr(dashboard, "_tracker", None)
        packet = getattr(dashboard, "_last_packet", None)
        if tracker is None:
            res = _empty_result()
            return LiveReplanStateResult(
                state=res.state, state_sources=res.state_sources,
                warnings=("Live current-state source not available yet.",),
                missing_state=res.missing_state,
            )
        return build_replan_state_from_tracker(
            tracker, packet=packet, event_settings=event_settings,
        )
    except Exception:
        return _empty_result()


def extract_live_replan_state(source, **kwargs) -> LiveReplanStateResult:
    """Generic dispatcher over a duck-typed live source. Never raises.

    Chooses the tracker path (has ``laps_recorded``), the dashboard path (has
    ``_tracker``), or the packet path (has ``fuel_capacity``); otherwise all-missing.
    """
    try:
        if source is None:
            return _empty_result()
        if hasattr(source, "laps_recorded"):
            return build_replan_state_from_tracker(source, **kwargs)
        if hasattr(source, "_tracker"):
            return build_replan_state_from_dashboard_context(source, **kwargs)
        if hasattr(source, "fuel_capacity"):
            return build_replan_state_from_live_packet(source, **kwargs)
        return _empty_result()
    except Exception:
        return _empty_result()


def summarise_live_state_sources(result: LiveReplanStateResult) -> dict:
    """Return the per-field provenance map (live_telemetry / strategy tag / missing)."""
    return dict(result.state_sources)


# ---------------------------------------------------------------------------
# Group 55: pit-lane mapping corroboration
# ---------------------------------------------------------------------------

def apply_pit_lane_evidence(
    result: LiveReplanStateResult,
    *,
    track_context=None,
    live_progress=None,
) -> LiveReplanStateResult:
    """Combine Group 54 pit-event confidence with track-specific pit-lane mapping.

    Evidence-quality only. This NEVER counts a pit stop, never fabricates one, and
    never touches ``pit_stops_completed`` / ``tyre_age_laps`` — those come solely
    from the Group 54 tracker. It only adjusts a *separate* pit-evidence confidence
    signal and records the pit-lane zone/source, per the Group 55 rules:

      • No pit-lane mapping           → Group 54 behaviour preserved exactly.
      • Live progress unknown         → no upgrade; surfaced as missing evidence.
      • Position inside the corridor + a refuel pit (MEDIUM) → upgrade to HIGH.
      • Position inside the corridor + a speed-only pit (LOW) → upgrade to MEDIUM
        at most (never HIGH).
      • Mapping contradicts detection (in-pit but position on track) → no upgrade,
        warning surfaced.
      • A LOW-confidence (estimated) map cannot lift pit evidence above MEDIUM.

    The tracker's pit confidence uses HIGH to mean "no pit yet — 0 stops is
    certain"; that is not a *detected* pit, so it is never further upgraded here.
    Returns a NEW result (never mutates); never raises.
    """
    try:
        base_conf = str(result.pit_state_confidence or "UNKNOWN").upper()
        pit_detected = base_conf in ("MEDIUM", "LOW")
        pit_in_progress = bool(result.pit_in_progress)

        segments = build_pit_lane_segments_from_track_context(track_context)
        has_mapping = bool(segments)
        map_conf = segments_mapping_confidence(segments)
        map_source = _mapping_source(track_context, segments)

        progress = normalise_progress(live_progress)
        warnings = list(result.warnings)

        # --- No mapping → keep Group 54 behaviour exactly. --------------------
        if not has_mapping:
            warnings.append("Pit-lane map unavailable for this track/layout.")
            return _dc_replace(
                result,
                pit_lane_zone=PitLaneZone.UNKNOWN.value,
                pit_lane_source="missing",
                pit_lane_mapping_confidence=PitLaneMappingConfidence.NONE.value,
                pit_evidence_confidence=base_conf,
                pit_corroboration=CORR_NO_MAPPING,
                warnings=tuple(warnings),
            )

        # --- Mapping exists but live position is unknown. --------------------
        if progress is None:
            warnings.append("Live track progress unavailable — pit-lane position not resolved.")
            if pit_detected:
                warnings.append("Pit event not corroborated by track position.")
            return _dc_replace(
                result,
                pit_lane_zone=PitLaneZone.UNKNOWN.value,
                pit_lane_source=map_source,
                pit_lane_mapping_confidence=map_conf.value,
                pit_evidence_confidence=base_conf,
                pit_corroboration=CORR_POSITION_UNKNOWN,
                warnings=tuple(warnings),
            )

        # --- Position resolved against the map. ------------------------------
        resolution = resolve_pit_lane_zone(progress, segments)
        zone = resolution.zone

        upgraded = base_conf
        corroboration = CORR_NOT_CORROBORATED

        if zone.is_inside:
            if base_conf == "MEDIUM":       # refuel pit corroborated by position
                upgraded = "HIGH"
                corroboration = CORR_CORROBORATED
            elif base_conf == "LOW":        # speed-only pit — lift to MEDIUM, never HIGH
                upgraded = "MEDIUM"
                corroboration = CORR_CORROBORATED
                warnings.append(
                    "Speed-only pit detection was not allowed to lift confidence above MEDIUM.")
            else:                           # HIGH (no pit yet) / UNKNOWN — nothing to upgrade
                corroboration = CORR_IN_LANE_NO_EVENT
            # A weak map cannot certify a HIGH pit: cap the upgrade at MEDIUM.
            if map_conf == PitLaneMappingConfidence.LOW and _PIT_CONF_RANK.get(upgraded, 0) > 2:
                upgraded = "MEDIUM"
                warnings.append(
                    "Pit-lane map is low confidence — pit evidence capped at MEDIUM.")
            if corroboration == CORR_CORROBORATED:
                warnings.append("Pit detection corroborated by pit-lane map.")
        elif zone == PitLaneZone.NOT_PIT_LANE:
            if pit_in_progress:
                corroboration = CORR_CONTRADICTED
                warnings.append(
                    "Pit event was detected but live position did not match pit-lane mapping.")
            else:
                corroboration = CORR_NOT_CORROBORATED
                if pit_detected:
                    warnings.append("Pit event not corroborated by track position.")
        else:  # UNKNOWN despite mapping + progress (defensive)
            corroboration = CORR_POSITION_UNKNOWN

        return _dc_replace(
            result,
            pit_lane_zone=zone.value,
            pit_lane_source=resolution.source or map_source,
            pit_lane_mapping_confidence=map_conf.value,
            pit_evidence_confidence=upgraded,
            pit_corroboration=corroboration,
            warnings=tuple(warnings),
        )
    except Exception:
        # Never let corroboration destabilise the live path — fall back untouched.
        return _dc_replace(
            result,
            pit_evidence_confidence=str(result.pit_state_confidence or "UNKNOWN"),
            pit_corroboration=CORR_NONE,
        )


def _mapping_source(track_context, segments) -> str:
    """Best-effort provenance label for the pit-lane mapping."""
    for s in segments:
        if getattr(s, "source", ""):
            return s.source
    if isinstance(track_context, dict):
        block = track_context.get("pit_lane")
        if isinstance(block, dict) and block.get("source"):
            return str(block["source"])
    return "track_model"


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _assemble(
    *,
    current_lap,
    remaining_laps,
    remaining_time_seconds,
    fuel_remaining_pct,
    current_compound,
    elapsed_time_seconds,
    event_settings,
    live_fuel_per_lap,
    compound_from_tag: bool = False,
    tyre_age_laps=None,
    pit_stops_completed=None,
    tyre_pit_source: str = SRC_MISSING,
    pit_state_confidence: str = "UNKNOWN",
    extra_warning: Optional[str] = None,
    pit_in_progress: bool = False,
) -> LiveReplanStateResult:
    state = RaceReplanState(
        current_lap=current_lap,
        elapsed_time_seconds=elapsed_time_seconds,
        remaining_laps=remaining_laps,
        remaining_time_seconds=remaining_time_seconds,
        fuel_remaining_pct=fuel_remaining_pct,
        current_compound=current_compound,
        tyre_age_laps=tyre_age_laps,       # Group 54: from read-only pit tracking (HIGH/MEDIUM only)
        pit_stops_completed=pit_stops_completed,
        required_compounds_used=(),        # not tracked live
        weather_status=None,
        damage_status=None,
        safety_car_status=None,
    )

    sources: dict[str, str] = {}
    missing: list[str] = []

    def _mark(field_name: str, value, src: str) -> None:
        if value is None or value == "":
            sources[field_name] = SRC_MISSING
            missing.append(field_name)
        else:
            sources[field_name] = src

    _mark("current_lap", current_lap, SRC_LIVE)
    _mark("remaining_laps" if remaining_laps is not None else "remaining_distance",
          remaining_laps if remaining_laps is not None else remaining_time_seconds, SRC_LIVE)
    _mark("fuel_remaining_pct", fuel_remaining_pct, SRC_LIVE)
    _mark("current_compound", current_compound,
          SRC_STRATEGY_TAG if compound_from_tag else SRC_LIVE)

    # Group 54: tyre age + pit-stop count. When a LOW-confidence estimate exists the
    # value is deliberately NOT populated on the state (so it can't lift readiness);
    # the source label still reveals the low-confidence estimate honestly.
    if tyre_age_laps is not None:
        sources["tyre_age_laps"] = tyre_pit_source
    else:
        sources["tyre_age_laps"] = tyre_pit_source if tyre_pit_source == SRC_LIVE_LOW else SRC_MISSING
        missing.append("tyre_age_laps")
    if pit_stops_completed is not None:
        sources["pit_stops_completed"] = tyre_pit_source
    else:
        sources["pit_stops_completed"] = tyre_pit_source if tyre_pit_source == SRC_LIVE_LOW else SRC_MISSING
        missing.append("pit_stops_completed")

    warnings: list[str] = []
    if fuel_remaining_pct is None:
        warnings.append("Fuel remaining is unavailable from live telemetry.")
    if not current_compound:
        warnings.append("Current compound is not known from live telemetry.")
    if tyre_age_laps is None and tyre_pit_source not in (SRC_LIVE_LOW, SRC_MANUAL):
        warnings.append("Tyre age and pit-stop count are not tracked yet — treated as unknown, not safe.")
    if extra_warning:
        warnings.append(extra_warning)

    return LiveReplanStateResult(
        state=state,
        pit_state_confidence=str(pit_state_confidence or "UNKNOWN"),
        pit_in_progress=bool(pit_in_progress),
        pit_evidence_confidence=str(pit_state_confidence or "UNKNOWN"),
        state_sources=sources,
        warnings=tuple(warnings),
        missing_state=tuple(missing),
        live_fuel_per_lap=float(live_fuel_per_lap or 0.0),
    )


def _empty_result() -> LiveReplanStateResult:
    state = RaceReplanState()
    sources = {f: SRC_MISSING for f in (
        "current_lap", "remaining_distance", "fuel_remaining_pct",
        "current_compound", "tyre_age_laps", "pit_stops_completed")}
    return LiveReplanStateResult(
        state=state,
        state_sources=sources,
        warnings=("No live current-state fields available.",),
        missing_state=tuple(sources.keys()),
        live_fuel_per_lap=0.0,
    )
