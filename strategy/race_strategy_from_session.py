"""Group 49 — Race Strategy Brain Phase 3: build strategy evidence from SessionDB.

WHY IT EXISTS
  Bridges the read-only SessionDB adapter to Group 48's pure evidence builder.
  Given event/race settings plus a session id, it pulls the measured samples,
  hands them to :func:`strategy.race_strategy_evidence.build_strategy_evidence`,
  and returns a :class:`RaceStrategyEvidence` together with the raw samples, the
  merged missing-evidence list, warnings, and a provenance ``source_summary`` that
  records which fields came from SessionDB, which from event settings, and which
  fell back to a default.

WHAT THIS MODULE IS NOT
  • It invents nothing. Missing session data → missing evidence → lower
    confidence (or INSUFFICIENT_EVIDENCE), never fabricated numbers.
  • It authors no setup values, writes nothing, and cannot reach the Apply gate.
  • The only impure dependency (SessionDB) is isolated to the adapter call.

SAFETY
  Never raises. Deterministic. Safe when the session is missing, empty, has only
  invalid laps, or the car/track/layout mismatches.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from strategy.race_strategy_evidence import (
    RaceStrategyEvidence,
    StrategyConfidence,
    build_strategy_evidence,
)
from strategy.race_strategy_session_adapter import (
    SessionStrategySamples,
    extract_session_strategy_samples,
)


@dataclass(frozen=True)
class SessionEvidenceResult:
    """Evidence built from a SessionDB session, plus its provenance."""

    evidence: RaceStrategyEvidence
    samples: SessionStrategySamples
    missing_evidence: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    source_summary: dict = field(default_factory=dict)

    @property
    def confidence(self) -> StrategyConfidence:
        return self.evidence.evidence_confidence


# ---------------------------------------------------------------------------
# Core integration
# ---------------------------------------------------------------------------

def build_strategy_evidence_from_session(
    db,
    *,
    session_id: int,
    car_id: int = 0,
    track: str = "",
    layout_id: str = "",
    race_duration_minutes: float = 0.0,
    race_laps: int = 0,
    fuel_multiplier: float = 0.0,
    tyre_multiplier: float = 0.0,
    refuel_rate_lps: float = 0.0,
    pit_loss_seconds: float = 0.0,
    starting_fuel_pct: float = 100.0,
    available_compounds: Sequence[str] = (),
    required_compounds: Sequence[str] = (),
    mandatory_pit_stops: int = 0,
    weather_context: Optional[str] = None,
    derive_tyre_wear: bool = True,
    no_abs: bool = False,
) -> SessionEvidenceResult:
    """Build :class:`RaceStrategyEvidence` from event settings + SessionDB samples.

    Event settings (multipliers, refuel rate, pit loss, compound rules) come from
    the caller — typically sourced from the canonical EventContext (see
    :func:`build_strategy_evidence_from_event_context`). Measured samples (lap
    times, fuel use, tyre-wear proxy, per-compound pace) come from SessionDB.

    Returns a :class:`SessionEvidenceResult`. Never raises; on any failure it
    returns an INSUFFICIENT_EVIDENCE snapshot with the reason in ``warnings``.
    """
    try:
        samples = extract_session_strategy_samples(
            db,
            session_id,
            expected_car_id=car_id,
            expected_track=track,
            layout_id=layout_id,
            derive_tyre_wear=derive_tyre_wear,
        )

        # Weather: honour an explicit override; otherwise leave unknown (Group 48
        # treats "unknown"/"dry_stable" as stable — we do NOT claim dry).
        weather = weather_context if weather_context else "unknown"

        evidence = build_strategy_evidence(
            car_id=car_id or samples.car_id,
            track=track or samples.track,
            layout_id=layout_id or samples.layout_id,
            race_duration_minutes=race_duration_minutes,
            race_laps=race_laps,
            fuel_multiplier=fuel_multiplier,
            tyre_multiplier=tyre_multiplier,
            refuel_rate_lps=refuel_rate_lps,
            pit_loss_seconds=pit_loss_seconds,
            starting_fuel_pct=starting_fuel_pct,
            available_compounds=available_compounds,
            required_compounds=required_compounds,
            mandatory_pit_stops=mandatory_pit_stops,
            weather_context=weather,
            lap_time_samples=samples.lap_samples,
            fuel_use_samples=samples.fuel_samples,
            tyre_wear_samples=samples.tyre_samples,
            compound_samples={c: list(v) for c, v in samples.compound_samples.items()},
            no_abs=no_abs,
        )

        source_summary = _build_source_summary(
            samples,
            weather_supplied=bool(weather_context),
            pit_loss_seconds=pit_loss_seconds,
            refuel_rate_lps=refuel_rate_lps,
        )

        warnings = tuple(samples.warnings)

        return SessionEvidenceResult(
            evidence=evidence,
            samples=samples,
            missing_evidence=evidence.missing_evidence,
            warnings=warnings,
            source_summary=source_summary,
        )
    except Exception:
        empty = extract_session_strategy_samples(None, 0)
        evidence = build_strategy_evidence(car_id=car_id, track=track)
        return SessionEvidenceResult(
            evidence=evidence,
            samples=empty,
            missing_evidence=evidence.missing_evidence,
            warnings=("Unexpected error building evidence from session.",),
            source_summary={"source": "SessionDB", "error": True},
        )


# ---------------------------------------------------------------------------
# Canonical EventContext bridge (scope §5)
# ---------------------------------------------------------------------------

def build_strategy_evidence_from_event_context(
    db,
    *,
    session_id: int,
    event_context,
    pit_loss_seconds: float = 0.0,
    starting_fuel_pct: float = 100.0,
    weather_context: Optional[str] = None,
    derive_tyre_wear: bool = True,
) -> SessionEvidenceResult:
    """Convenience: source event settings from the canonical ``EventContext``.

    Prefers canonical event settings (multipliers, refuel rate, race length,
    compound rules, mandatory stops, layout, weather) over duplicated inputs.
    ``pit_loss_seconds`` and ``starting_fuel_pct`` are NOT in EventContext, so
    they remain caller-supplied (a missing pit loss is recorded as missing
    evidence by the evidence builder). Never raises.
    """
    ec = event_context
    race_laps = int(getattr(ec, "laps", 0) or 0) if getattr(ec, "is_lap_race", False) else 0
    duration = float(getattr(ec, "race_duration_minutes", 0) or 0) if getattr(ec, "is_timed", False) else 0.0

    # Weather: prefer explicit override, else map the EventContext weather string.
    weather = weather_context if weather_context else _map_weather(getattr(ec, "weather", ""))

    return build_strategy_evidence_from_session(
        db,
        session_id=session_id,
        car_id=0,  # resolved from the session row / not needed for evidence identity
        track=str(getattr(ec, "track", "") or ""),
        layout_id=str(getattr(ec, "layout_id", "") or ""),
        race_duration_minutes=duration,
        race_laps=race_laps,
        fuel_multiplier=float(getattr(ec, "fuel_multiplier", 0.0) or 0.0),
        tyre_multiplier=float(getattr(ec, "tyre_wear_multiplier", 0.0) or 0.0),
        refuel_rate_lps=float(getattr(ec, "refuel_rate_lps", 0.0) or 0.0),
        pit_loss_seconds=pit_loss_seconds,
        starting_fuel_pct=starting_fuel_pct,
        available_compounds=tuple(getattr(ec, "available_tyres", ()) or ()),
        required_compounds=tuple(getattr(ec, "required_tyres", ()) or ()),
        mandatory_pit_stops=int(getattr(ec, "mandatory_stops", 0) or 0),
        weather_context=weather,
        derive_tyre_wear=derive_tyre_wear,
        no_abs=not bool(getattr(ec, "abs_allowed", True)),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _map_weather(raw: str) -> str:
    """Map an EventContext weather string to a Group 48 weather_context token."""
    r = str(raw or "").lower()
    if not r:
        return "unknown"
    if "random" in r or "variable" in r or "changeable" in r:
        return "random"
    if "wet" in r or "rain" in r:
        return "wet"
    if "dry" in r or "fixed" in r or "clear" in r:
        return "dry_stable"
    return "unknown"


def _build_source_summary(
    samples: SessionStrategySamples,
    *,
    weather_supplied: bool,
    pit_loss_seconds: float,
    refuel_rate_lps: float,
) -> dict:
    """Classify each strategy input by provenance for the explanation layer."""
    sources: dict[str, str] = {}

    sources["race_pace"] = (
        f"SessionDB measured ({samples.clean_lap_count} clean laps)"
        if samples.has_laps else "missing"
    )
    sources["fuel_use"] = (
        f"SessionDB measured ({len(samples.fuel_samples)} laps)"
        if samples.fuel_samples else "missing"
    )
    if samples.tyre_samples:
        sources["tyre_degradation"] = (
            f"SessionDB derived from lap-time drift ({len(samples.tyre_samples)} increments)"
        )
    else:
        sources["tyre_degradation"] = "missing"
    sources["compound_pace"] = (
        f"SessionDB measured ({len(samples.compound_samples)} compounds)"
        if samples.compound_samples else "missing"
    )
    sources["refuel_rate"] = "event setting" if refuel_rate_lps > 0 else "missing"
    sources["pit_loss"] = "event setting" if pit_loss_seconds > 0 else "default/missing"
    sources["weather"] = "event setting" if weather_supplied else "assumed"

    return {
        "source": "SessionDB",
        "session_id": samples.session_id,
        "fields": sources,
        "adapter": dict(samples.source_summary),
    }
