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
    extract_live_replan_state,
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
    generated_at: str = "",
) -> LiveReplanResult:
    """Build a read-only live replan snapshot.

    Supply either a ``live_source`` (tracker / dashboard / packet — read via the
    Group 53 adapter) or an explicit ``live_state``. Live fuel burn from the adapter
    is fed to the snapshot as ``latest_fuel_samples`` when the caller supplies none.
    ``generated_at`` is caller-supplied (no clock in this pure builder). Never raises.
    """
    try:
        live_fuel_per_lap = 0.0
        if live_state is None:
            extracted: LiveReplanStateResult = extract_live_replan_state(
                live_source, event_settings=event_settings)
            live_state = extracted.state
            if state_sources is None:
                state_sources = extracted.state_sources
            warnings = tuple(warnings) + tuple(extracted.warnings)
            live_fuel_per_lap = extracted.live_fuel_per_lap
        state_sources = dict(state_sources or {})

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
    """Plain-text advisory rendering of a live replan result."""
    lines = ["Live Replan Snapshot", f"Status: {result.status}",
             f"Confidence: {result.confidence.value}"]
    if result.driver_message:
        lines.append(f"Reason: {result.driver_message}")
    if result.missing_state:
        lines.append("Missing: " + ", ".join(result.missing_state))
    lines.append(render_replan_snapshot_text(result.snapshot))
    return "\n".join(lines)


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
