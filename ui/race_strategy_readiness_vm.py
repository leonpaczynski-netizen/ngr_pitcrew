"""Group 51 — Race Strategy Brain Phase 5: Race Plan readiness & diagnostics.

WHY IT EXISTS
  Group 50 made the Race Plan visible. Group 51 makes it *understandable* before
  the driver relies on it: which session is being used, whether it matches the
  event, what evidence was found, what is missing, how confident the plan can be,
  and — crucially — what to record next to improve it.

WHAT THIS MODULE IS
  A PURE, Qt-free readiness / diagnostics / validation layer over the Group 49
  SessionDB samples and the event settings. It computes:
    • a RacePlanReadiness (per-field status + overall level + next-best action)
    • SessionDiagnostics (which session, car/track/layout match, evidence found)
    • an EventSettingsValidation (honest warnings; never blocks unnecessarily)
    • driver-readable empty/missing-evidence messages
    • a read-only recent-matching-sessions list (data layer for an optional selector)

WHAT THIS MODULE IS NOT
  • Not PyQt — no Qt import. The Strategy Builder renders these; it does not
    compute them.
  • It invents nothing: missing data stays missing. It authors no setup values,
    exposes no Apply/approve, and its SessionDB use is strictly read-only.

PURITY
  Deterministic and offline; never raises — every builder wraps its internals and
  degrades to a safe, honest "insufficient evidence" result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from strategy.race_strategy_session_adapter import (
    SessionStrategySamples,
    MISS_SESSION, MISS_LAPS, MISS_FUEL, MISS_TYRE, MISS_COMPOUND,
    MISS_CAR_TRACK_MISMATCH,
)

# Minimum clean laps before a race-strategy estimate is trustworthy at all
# (matches strategy.race_strategy_evidence.MIN_LAP_SAMPLES).
MIN_CLEAN_LAPS = 3


class ReadinessLevel(str, Enum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

    @property
    def label(self) -> str:
        return {
            ReadinessLevel.READY: "Ready",
            ReadinessLevel.PARTIAL: "Partial",
            ReadinessLevel.LOW_CONFIDENCE: "Low confidence",
            ReadinessLevel.INSUFFICIENT_EVIDENCE: "Insufficient evidence",
        }[self]


class CheckStatus(str, Enum):
    OK = "OK"
    MISSING = "MISSING"
    DEGRADED = "DEGRADED"      # present but weak (e.g. short-run tyre proxy)
    MISMATCH = "MISMATCH"
    MANUAL = "MANUAL"
    DEFAULT = "DEFAULT"
    NA = "NA"                  # not applicable (e.g. layout unknown)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionSummary:
    """One recent session, for a read-only selector."""
    session_id: int
    label: str
    total_laps: int = 0
    tagged_laps: int = 0
    date_utc: str = ""


@dataclass(frozen=True)
class SessionDiagnostics:
    """What the Race Plan knows about the session it is using."""
    session_id: int
    session_label: str
    car_id: int
    track: str
    layout_id: str
    matches_event: CheckStatus
    match_note: str
    clean_lap_count: int
    fuel_available: bool
    tyre_proxy_available: bool
    compound_available: bool
    message: str


@dataclass(frozen=True)
class RacePlanReadiness:
    """Per-field readiness checklist + overall level and guidance."""
    event_settings_status: CheckStatus
    session_status: CheckStatus
    car_track_layout_match_status: CheckStatus
    lap_sample_status: CheckStatus
    fuel_sample_status: CheckStatus
    tyre_degradation_status: CheckStatus
    compound_sample_status: CheckStatus
    pit_loss_status: CheckStatus
    refuel_rate_status: CheckStatus
    overall_readiness: ReadinessLevel
    readiness_message: str
    next_best_action: str
    found: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EventSettingsValidation:
    """Honest validation of the event/race inputs (never blocks unnecessarily)."""
    warnings: list[str] = field(default_factory=list)
    field_status: dict = field(default_factory=dict)
    can_run: bool = True


# ---------------------------------------------------------------------------
# Helpers on event settings
# ---------------------------------------------------------------------------

def _pos(v) -> bool:
    try:
        return float(v) > 0.0
    except (TypeError, ValueError):
        return False


def _has_race_length(es: dict) -> bool:
    return _pos(es.get("race_duration_minutes")) or _pos(es.get("race_laps"))


# ---------------------------------------------------------------------------
# Event settings validation (scope §3)
# ---------------------------------------------------------------------------

def validate_event_settings(event_settings: dict) -> EventSettingsValidation:
    """Validate Race Plan event inputs. Never crashes, never invents values.

    Produces honest warnings and a per-field status. ``can_run`` is False only
    when the strategy pipeline genuinely cannot produce even a low-confidence
    estimate (no race length at all).
    """
    es = dict(event_settings or {})
    warnings: list[str] = []
    status: dict[str, CheckStatus] = {}

    if _pos(es.get("car_id")):
        status["car_id"] = CheckStatus.OK
    else:
        status["car_id"] = CheckStatus.MISSING
        warnings.append("Car not identified — session matching may be unreliable.")

    if str(es.get("track") or "").strip():
        status["track"] = CheckStatus.OK
    else:
        status["track"] = CheckStatus.MISSING
        warnings.append("Track not set — set the event track in Event Planner.")

    status["layout_id"] = CheckStatus.OK if str(es.get("layout_id") or "").strip() else CheckStatus.NA

    if _has_race_length(es):
        status["race_length"] = CheckStatus.OK
    else:
        status["race_length"] = CheckStatus.MISSING
        warnings.append(
            "Missing race duration or lap count — strategy can only produce "
            "low-confidence estimates. Set it in Event Planner.")

    status["fuel_multiplier"] = CheckStatus.OK if _pos(es.get("fuel_multiplier")) else CheckStatus.MISSING
    status["tyre_multiplier"] = CheckStatus.OK if _pos(es.get("tyre_multiplier")) else CheckStatus.MISSING

    if _pos(es.get("refuel_rate_lps")):
        status["refuel_rate_lps"] = CheckStatus.OK
    else:
        status["refuel_rate_lps"] = CheckStatus.MISSING
        warnings.append("Missing refuel rate — refuel time cannot be calculated accurately.")

    if _pos(es.get("pit_loss_seconds")):
        status["pit_loss_seconds"] = CheckStatus.MANUAL if es.get("pit_loss_is_manual") else CheckStatus.OK
        if es.get("pit_loss_is_manual"):
            warnings.append("Pit loss is a manual value — measure pit-lane delta for better accuracy.")
    else:
        status["pit_loss_seconds"] = CheckStatus.MISSING
        warnings.append("Pit loss not set — measure pit-lane delta or enter Pit loss seconds.")

    sf = es.get("starting_fuel_pct", 100.0)
    status["starting_fuel_pct"] = CheckStatus.OK if (_pos(sf) and float(sf) <= 100.0) else CheckStatus.DEFAULT

    status["required_compounds"] = CheckStatus.OK if (es.get("required_compounds") or ()) else CheckStatus.NA
    status["mandatory_pit_stops"] = CheckStatus.OK

    return EventSettingsValidation(
        warnings=warnings,
        field_status=status,
        can_run=_has_race_length(es),
    )


# ---------------------------------------------------------------------------
# Session diagnostics (scope §2)
# ---------------------------------------------------------------------------

def build_session_diagnostics(
    samples: Optional[SessionStrategySamples],
    *,
    event_car_id: int = 0,
    event_track: str = "",
    event_layout: str = "",
) -> SessionDiagnostics:
    """Summarise which session the Race Plan is using and whether it matches."""
    try:
        if samples is None or not samples.session_id:
            return SessionDiagnostics(
                session_id=0, session_label="No session selected",
                car_id=0, track="", layout_id="",
                matches_event=CheckStatus.NA,
                match_note="Using event settings only.",
                clean_lap_count=0, fuel_available=False,
                tyre_proxy_available=False, compound_available=False,
                message="No session selected — the plan uses event settings only, so confidence is lower.",
            )

        mf = set(samples.missing_fields or ())
        if MISS_SESSION in mf:
            return SessionDiagnostics(
                session_id=samples.session_id,
                session_label=f"Session {samples.session_id} (not found)",
                car_id=samples.car_id, track=samples.track, layout_id=samples.layout_id,
                matches_event=CheckStatus.NA,
                match_note="Session not found in SessionDB.",
                clean_lap_count=0, fuel_available=False,
                tyre_proxy_available=False, compound_available=False,
                message="Session not found. Select a different practice session.",
            )

        # Match status
        if MISS_CAR_TRACK_MISMATCH in mf:
            match = CheckStatus.MISMATCH
            note = "Session car or track does not match this event."
        else:
            car_ok = (not event_car_id) or (not samples.car_id) or (event_car_id == samples.car_id)
            track_ok = (not event_track) or (not samples.track) or _norm(event_track) == _norm(samples.track)
            match = CheckStatus.OK if (car_ok and track_ok) else CheckStatus.MISMATCH
            note = "Session matches the current event." if match == CheckStatus.OK \
                else "Session car or track does not match this event."

        clean = samples.clean_lap_count
        fuel_ok = bool(samples.fuel_samples)
        tyre_ok = samples.tyre_wear_derived
        comp_ok = bool(samples.compound_samples)

        if match == CheckStatus.MISMATCH:
            message = "This session is for a different car or track — pick a matching session."
        elif clean == 0:
            message = f"No clean laps in session {samples.session_id} — record at least {MIN_CLEAN_LAPS} clean laps."
        else:
            message = (
                f"Using session {samples.session_id}: {clean} clean lap(s), "
                f"fuel {'yes' if fuel_ok else 'no'}, tyre proxy {'yes' if tyre_ok else 'no'}."
            )

        return SessionDiagnostics(
            session_id=samples.session_id,
            session_label=f"Session {samples.session_id}",
            car_id=samples.car_id, track=samples.track, layout_id=samples.layout_id,
            matches_event=match, match_note=note,
            clean_lap_count=clean, fuel_available=fuel_ok,
            tyre_proxy_available=tyre_ok, compound_available=comp_ok,
            message=message,
        )
    except Exception:
        return SessionDiagnostics(
            session_id=0, session_label="No session selected",
            car_id=0, track="", layout_id="",
            matches_event=CheckStatus.NA, match_note="",
            clean_lap_count=0, fuel_available=False,
            tyre_proxy_available=False, compound_available=False,
            message="Session diagnostics unavailable.",
        )


# ---------------------------------------------------------------------------
# Readiness (scope §1)
# ---------------------------------------------------------------------------

def build_race_plan_readiness(
    *,
    samples: Optional[SessionStrategySamples],
    event_settings: dict,
) -> RacePlanReadiness:
    """Grade Race Plan readiness from session samples + event settings.

    Levels:
      • INSUFFICIENT_EVIDENCE — no clean laps, or no fuel, or no race length:
        the pipeline cannot estimate a total race time at all.
      • LOW_CONFIDENCE — core evidence present but pit loss or refuel rate is
        missing (pit maths is weak); a plan still runs.
      • PARTIAL — core + pit maths present, but tyre degradation / compound pace /
        long-run is missing.
      • READY — everything present.
    """
    try:
        es = dict(event_settings or {})
        found: list[str] = []
        missing: list[str] = []

        # --- event settings ---
        ev_valid = validate_event_settings(es)
        event_status = CheckStatus.OK if ev_valid.can_run else CheckStatus.MISSING

        # --- session presence + match ---
        has_session = bool(samples is not None and samples.session_id
                           and MISS_SESSION not in set(samples.missing_fields or ()))
        session_status = CheckStatus.OK if has_session else CheckStatus.MISSING

        mf = set(samples.missing_fields or ()) if samples is not None else set()
        if not has_session:
            match_status = CheckStatus.NA
        elif MISS_CAR_TRACK_MISMATCH in mf:
            match_status = CheckStatus.MISMATCH
        else:
            match_status = CheckStatus.OK

        # --- session-derived evidence ---
        clean = samples.clean_lap_count if samples is not None else 0
        has_laps = clean >= MIN_CLEAN_LAPS and match_status != CheckStatus.MISMATCH
        has_fuel = bool(samples.fuel_samples) if samples is not None else False
        has_tyre = bool(samples.tyre_wear_derived) if samples is not None else False
        has_compound = bool(samples.compound_samples) if samples is not None else False

        lap_status = CheckStatus.OK if has_laps else CheckStatus.MISSING
        fuel_status = CheckStatus.OK if has_fuel else CheckStatus.MISSING
        tyre_status = CheckStatus.DEGRADED if has_tyre else CheckStatus.MISSING
        compound_status = CheckStatus.OK if has_compound else CheckStatus.MISSING

        # --- event-supplied pit maths ---
        has_pit_loss = _pos(es.get("pit_loss_seconds"))
        has_refuel = _pos(es.get("refuel_rate_lps"))
        has_race_len = _has_race_length(es)
        pit_status = (CheckStatus.MANUAL if es.get("pit_loss_is_manual") else CheckStatus.OK) \
            if has_pit_loss else CheckStatus.MISSING
        refuel_status = CheckStatus.OK if has_refuel else CheckStatus.MISSING

        # --- found / missing text ---
        if has_laps:
            found.append(f"{clean} clean laps from SessionDB")
        else:
            missing.append("clean lap samples")
        if has_fuel:
            found.append(f"fuel use from {len(samples.fuel_samples)} lap(s)")
        else:
            missing.append("fuel-use samples")
        if has_tyre:
            found.append("tyre degradation (derived lap-drift proxy)")
        else:
            missing.append("explicit tyre-wear telemetry")
        if has_compound:
            found.append("per-compound pace")
        else:
            missing.append("compound-tagged laps")
        if has_refuel:
            found.append("refuel rate from event setting")
        else:
            missing.append("refuel rate")
        if has_pit_loss:
            found.append("pit loss (manual/event value)")
        else:
            missing.append("measured pit loss")
        if not has_race_len:
            missing.append("race duration or lap count")

        # --- overall grading ---
        if not has_laps or not has_fuel or not has_race_len:
            level = ReadinessLevel.INSUFFICIENT_EVIDENCE
        elif not has_pit_loss or not has_refuel:
            level = ReadinessLevel.LOW_CONFIDENCE
        elif not has_tyre or not has_compound:
            level = ReadinessLevel.PARTIAL
        else:
            level = ReadinessLevel.READY

        return RacePlanReadiness(
            event_settings_status=event_status,
            session_status=session_status,
            car_track_layout_match_status=match_status,
            lap_sample_status=lap_status,
            fuel_sample_status=fuel_status,
            tyre_degradation_status=tyre_status,
            compound_sample_status=compound_status,
            pit_loss_status=pit_status,
            refuel_rate_status=refuel_status,
            overall_readiness=level,
            readiness_message=f"Race Plan readiness: {level.label}",
            next_best_action=_next_best_action(
                has_laps=has_laps, has_fuel=has_fuel, has_race_len=has_race_len,
                has_refuel=has_refuel, has_pit_loss=has_pit_loss,
                has_tyre=has_tyre, has_compound=has_compound,
                match_status=match_status, has_session=has_session,
            ),
            found=found,
            missing=missing,
        )
    except Exception:
        return RacePlanReadiness(
            event_settings_status=CheckStatus.MISSING,
            session_status=CheckStatus.MISSING,
            car_track_layout_match_status=CheckStatus.NA,
            lap_sample_status=CheckStatus.MISSING,
            fuel_sample_status=CheckStatus.MISSING,
            tyre_degradation_status=CheckStatus.MISSING,
            compound_sample_status=CheckStatus.MISSING,
            pit_loss_status=CheckStatus.MISSING,
            refuel_rate_status=CheckStatus.MISSING,
            overall_readiness=ReadinessLevel.INSUFFICIENT_EVIDENCE,
            readiness_message="Race Plan readiness: Insufficient evidence",
            next_best_action="Record a practice session with clean laps to build a race plan.",
        )


def _next_best_action(
    *, has_laps, has_fuel, has_race_len, has_refuel, has_pit_loss,
    has_tyre, has_compound, match_status, has_session,
) -> str:
    if match_status == CheckStatus.MISMATCH:
        return ("The selected session is for a different car or track. Select a session "
                "recorded on this car and track.")
    if not has_session or not has_laps:
        return (f"Record at least {MIN_CLEAN_LAPS} clean practice laps on this car and track "
                "so the strategy can estimate race pace.")
    if not has_fuel:
        return ("Record laps where fuel use is captured so the strategy can size fuel and "
                "refuel stops.")
    if not has_race_len:
        return "Set the race duration or lap count in Event Planner."
    if not has_refuel:
        return "Set the refuel rate in Event Planner so refuel time can be calculated."
    if not has_pit_loss:
        return ("Measure the pit-lane delta (enter it in Pit loss seconds) so pit-stop cost "
                "is accurate.")
    if not has_tyre:
        return ("Record a 10-lap practice stint on one compound so the strategy can estimate "
                "tyre drop-off.")
    if not has_compound:
        return "Tag your laps with the compound used so per-compound pace can be compared."
    return "Evidence looks good — the recommendation can be relied on with normal caution."


# ---------------------------------------------------------------------------
# Empty / missing-evidence messages (scope §4)
# ---------------------------------------------------------------------------

def empty_state_messages(
    samples: Optional[SessionStrategySamples],
    event_settings: dict,
) -> list[str]:
    """Short, actionable driver-readable lines for each detected input problem.

    Ordered by severity, deduplicated. Empty when nothing is wrong.
    """
    es = dict(event_settings or {})
    out: list[str] = []
    mf = set(samples.missing_fields or ()) if samples is not None else set()

    # Session-level
    if samples is None or not getattr(samples, "session_id", 0):
        out.append("No session selected. Using event settings only — load or select a "
                   "practice session for higher confidence.")
    elif MISS_SESSION in mf:
        out.append("Session not found. Select a different practice session.")
    elif MISS_CAR_TRACK_MISMATCH in mf:
        out.append("Selected session is for a different car or track. Pick a session that "
                   "matches this event.")
    else:
        if samples.clean_lap_count == 0:
            out.append(f"No clean laps found for this session. Record at least {MIN_CLEAN_LAPS} "
                       "clean practice laps before relying on race strategy estimates.")
        elif samples.clean_lap_count < MIN_CLEAN_LAPS:
            out.append(f"Only {samples.clean_lap_count} clean lap(s) in this session. Record at "
                       f"least {MIN_CLEAN_LAPS} clean laps for a trustworthy race-pace estimate.")
        if MISS_FUEL in mf:
            out.append("No fuel-use data in this session. Record laps where fuel telemetry is "
                       "captured so fuel and refuel stops can be sized.")
        if MISS_TYRE in mf:
            out.append("No tyre-wear signal available. Run a longer single-compound stint "
                       "(8+ laps) so tyre drop-off can be estimated.")
        if MISS_COMPOUND in mf:
            out.append("Laps are not tagged with a compound. Tag compounds so per-compound "
                       "pace can be compared.")

    # Event-level
    if not _has_race_length(es):
        out.append("No race duration or lap count set. Set it in Event Planner for anything "
                   "better than a low-confidence estimate.")
    if not _pos(es.get("refuel_rate_lps")):
        out.append("Refuel rate is not set. Enter it in Event Planner so refuel time is accurate.")
    if not _pos(es.get("pit_loss_seconds")):
        out.append("Pit loss is not set. Measure the pit-lane delta or enter Pit loss seconds.")

    # Dedup preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for m in out:
        if m not in seen:
            seen.add(m)
            deduped.append(m)
    return deduped


def strategy_result_message(result) -> str:
    """A driver-readable line when a scored result has no recommendation.

    Surfaces the honest Group 48 reason (e.g. every candidate illegal / no pace),
    or "" when a recommendation exists.
    """
    rec = getattr(result, "recommendation", None)
    if rec is None:
        return ""
    if getattr(rec, "has_recommendation", False):
        return ""
    reason = getattr(rec, "reason", "") or "Not enough evidence to recommend a strategy."
    return str(reason)


# ---------------------------------------------------------------------------
# Recent matching sessions (read-only data layer for an optional selector)
# ---------------------------------------------------------------------------

def list_recent_matching_sessions(db, car_id: int, track: str, limit: int = 10) -> list[SessionSummary]:
    """Read-only list of recent sessions for this car+track, newest first.

    Uses only `db.get_practice_sessions(car_id, track)`. Returns [] on any error
    or when car/track is unknown. Never writes.
    """
    try:
        if db is None or not car_id or not str(track or "").strip():
            return []
        rows = db.get_practice_sessions(int(car_id), str(track)) or []
        out: list[SessionSummary] = []
        for r in rows[: max(0, int(limit))]:
            sid = int(r.get("id", 0) or 0)
            total = int(r.get("total_laps", 0) or 0)
            tagged = int(r.get("tagged_laps", 0) or 0)
            date = str(r.get("date_utc", "") or "")
            day = date[:10] if date else ""
            label = f"Session {sid} — {total} laps" + (f" ({day})" if day else "")
            out.append(SessionSummary(
                session_id=sid, label=label, total_laps=total,
                tagged_laps=tagged, date_utc=date,
            ))
        return out
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Rendering (pure)
# ---------------------------------------------------------------------------

_LEVEL_COLOURS = {
    ReadinessLevel.READY: "#8BC34A",
    ReadinessLevel.PARTIAL: "#C9D14A",
    ReadinessLevel.LOW_CONFIDENCE: "#F5C542",
    ReadinessLevel.INSUFFICIENT_EVIDENCE: "#E8A9A3",
}


def render_readiness_html(readiness: RacePlanReadiness, diagnostics: Optional[SessionDiagnostics] = None) -> str:
    """Render the readiness banner + session line + found/missing + next action."""
    def esc(s: str) -> str:
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    colour = _LEVEL_COLOURS.get(readiness.overall_readiness, "#AAA")
    parts: list[str] = []
    parts.append(
        f"<p style='margin:2px 0;'><b style='color:{colour};'>"
        f"{esc(readiness.readiness_message)}</b></p>"
    )
    if diagnostics is not None:
        parts.append(f"<p style='margin:2px 0; color:#AAA; font-size:11px;'>{esc(diagnostics.message)}</p>")
    if readiness.found:
        parts.append("<p style='margin:4px 0 1px; color:#8BC34A; font-size:11px;'><b>Found</b></p><ul style='margin:1px 0;'>")
        for f in readiness.found:
            parts.append(f"<li style='font-size:11px;'>{esc(f)}</li>")
        parts.append("</ul>")
    if readiness.missing:
        parts.append("<p style='margin:4px 0 1px; color:#F5C542; font-size:11px;'><b>Missing</b></p><ul style='margin:1px 0;'>")
        for m in readiness.missing:
            parts.append(f"<li style='font-size:11px;'>{esc(m)}</li>")
        parts.append("</ul>")
    if readiness.next_best_action:
        parts.append(
            "<p style='margin:4px 0 1px; color:#64B5F6; font-size:11px;'><b>Next best action</b></p>"
            f"<p style='margin:1px 0; font-size:11px;'>{esc(readiness.next_best_action)}</p>"
        )
    return "\n".join(parts)


def _norm(s: str) -> str:
    return "".join(str(s).lower().split())
