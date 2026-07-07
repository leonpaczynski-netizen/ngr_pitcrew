"""Group 52 — Race Strategy Brain Phase 6: read-only live-replan readiness foundation.

WHY IT EXISTS
  A future sprint may compare the pre-race Race Plan to the LIVE race state and
  advise whether the plan still holds. This module is the *foundation* for that:
  a pure, deterministic, ADVISORY-ONLY model of current race state, a readiness
  grade over it, and a read-only "replan snapshot" that says whether the plan is
  still viable and what the alternatives are — WITHOUT connecting live telemetry,
  making a pit call, sending a driver command, or applying anything.

WHAT THIS MODULE IS NOT
  • It is NOT a live pit-wall engineer. It subscribes to nothing, loops over
    nothing, and applies nothing. Every output is advisory text + numbers already
    computed by the Group 48 engine.
  • It authors no setup values, exposes no Apply/approve, writes no files, and
    invents no live telemetry: unknown state is recorded as missing, never guessed.
    Unknown tyre state is NEVER treated as safe.
  • No Qt, no DB, no I/O. Never raises — every builder degrades to an honest
    INSUFFICIENT_EVIDENCE result.

GROUNDING
  Advisory option deltas are the PRE-RACE Group 48 scored-candidate gaps (labelled
  as pre-race estimates), not invented live numbers. Fuel viability compares the
  reported fuel remaining to the pre-race fuel-per-lap over the laps to the next
  planned stop — no new strategy maths.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

# GT7 domain constant: full tank is always 100 litres (100 % == 100 L).
_GT7_TANK_L = 100.0

# Fuel is "below expected" when the reported remaining is under this fraction of
# what the pre-race burn rate needs to reach the next planned stop.
_FUEL_MARGIN = 1.0


class ReplanReadinessLevel(str, Enum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

    @property
    def label(self) -> str:
        return {
            ReplanReadinessLevel.READY: "Ready",
            ReplanReadinessLevel.PARTIAL: "Partial",
            ReplanReadinessLevel.LOW_CONFIDENCE: "Low confidence",
            ReplanReadinessLevel.INSUFFICIENT_EVIDENCE: "Insufficient evidence",
        }[self]


class ReplanConfidence(str, Enum):
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class RaceReplanReason(str, Enum):
    VIABLE = "VIABLE"
    FUEL_LOW = "FUEL_LOW"
    FUEL_HIGH = "FUEL_HIGH"
    TYRE_UNKNOWN = "TYRE_UNKNOWN"
    INSUFFICIENT_STATE = "INSUFFICIENT_STATE"
    PLAN_MISSING = "PLAN_MISSING"


# Standing advisory-only safety notes on every replan output.
REPLAN_SAFETY_NOTES = (
    "Advisory only — no pit call, setup change, or driver command is applied.",
    "Read-only: this reads pre-race strategy + reported race state and changes nothing.",
)


def _known_num(x) -> bool:
    """True when x is a known, non-negative number (None / negative = unknown)."""
    try:
        return x is not None and float(x) >= 0.0
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Current race state
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RaceReplanState:
    """Reported current race state. Every field defaults to UNKNOWN (None).

    Nothing here is fabricated — a caller supplies only what it genuinely knows,
    and everything left as None is treated as missing (never assumed safe).
    """

    current_lap: Optional[int] = None
    elapsed_time_seconds: Optional[float] = None
    remaining_laps: Optional[int] = None
    remaining_time_seconds: Optional[float] = None
    fuel_remaining_pct: Optional[float] = None
    current_compound: Optional[str] = None
    tyre_age_laps: Optional[int] = None
    pit_stops_completed: Optional[int] = None
    required_compounds_used: tuple[str, ...] = ()
    weather_status: Optional[str] = None
    damage_status: Optional[str] = None
    safety_car_status: Optional[str] = None

    # -- convenience --
    def has_fuel(self) -> bool:
        return _known_num(self.fuel_remaining_pct)

    def has_compound(self) -> bool:
        return bool(self.current_compound)

    def has_distance(self) -> bool:
        return _known_num(self.remaining_laps) or _known_num(self.remaining_time_seconds)

    def has_tyre_age(self) -> bool:
        return _known_num(self.tyre_age_laps)


@dataclass(frozen=True)
class RaceReplanStateValidation:
    """Honest validation of the reported race state (never blocks; never invents)."""
    warnings: list[str] = field(default_factory=list)
    field_status: dict = field(default_factory=dict)
    missing_state: list[str] = field(default_factory=list)
    can_snapshot: bool = False


@dataclass(frozen=True)
class RaceReplanReadiness:
    """Readiness to compute a replan snapshot from the current state."""
    level: ReplanReadinessLevel
    missing_state: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    message: str = ""


@dataclass(frozen=True)
class RaceReplanOption:
    """One advisory alternative, grounded in a pre-race scored candidate."""
    label: str
    basis: str
    estimated_delta: str        # e.g. "+8.2s (pre-race estimate)" or "reference"


@dataclass(frozen=True)
class RaceReplanSnapshot:
    """Read-only, advisory-only assessment of the plan vs the current state."""
    original_plan_status: str
    current_plan_still_viable: Optional[bool]   # None when it cannot be judged
    reason: RaceReplanReason
    remaining_strategy_options: list[RaceReplanOption] = field(default_factory=list)
    confidence: ReplanConfidence = ReplanConfidence.INSUFFICIENT_EVIDENCE
    missing_state: list[str] = field(default_factory=list)
    driver_message: str = ""
    safety_notes: tuple[str, ...] = REPLAN_SAFETY_NOTES


# ---------------------------------------------------------------------------
# State validation (scope §5)
# ---------------------------------------------------------------------------

def validate_replan_state(state: RaceReplanState) -> RaceReplanStateValidation:
    """Validate reported race state. Never crashes; never invents; unknown tyre
    state is never treated as safe."""
    try:
        status: dict[str, str] = {}
        warnings: list[str] = []
        missing: list[str] = []

        def _mark(key: str, ok: bool, warn: str) -> None:
            status[key] = "OK" if ok else "MISSING"
            if not ok:
                missing.append(key)
                warnings.append(warn)

        _mark("fuel_remaining_pct", state.has_fuel(),
              "Fuel remaining missing — cannot compare live fuel burn to the planned strategy.")
        _mark("current_compound", state.has_compound(),
              "Current compound missing — cannot verify required-compound compliance.")
        _mark("remaining_distance", state.has_distance(),
              "Remaining race distance missing — cannot estimate replan options.")
        _mark("current_lap", _known_num(state.current_lap),
              "Current lap missing — pit-window position is unknown.")

        # Tyre age: not required to run, but its absence must be visible and must
        # never be treated as 'fresh/safe'.
        if state.has_tyre_age():
            status["tyre_age_laps"] = "OK"
        else:
            status["tyre_age_laps"] = "MISSING"
            missing.append("tyre_age_laps")
            warnings.append("Tyre age unknown — tyre state is NOT assumed safe; confidence is reduced.")

        status["pit_stops_completed"] = "OK" if _known_num(state.pit_stops_completed) else "MISSING"
        if not _known_num(state.pit_stops_completed):
            missing.append("pit_stops_completed")

        can_snapshot = state.has_fuel() and state.has_compound() and state.has_distance()
        return RaceReplanStateValidation(
            warnings=warnings, field_status=status,
            missing_state=missing, can_snapshot=can_snapshot,
        )
    except Exception:
        return RaceReplanStateValidation(
            warnings=["Could not read race state."],
            field_status={}, missing_state=["fuel_remaining_pct", "current_compound",
                                            "remaining_distance"],
            can_snapshot=False,
        )


# ---------------------------------------------------------------------------
# Readiness (scope §3)
# ---------------------------------------------------------------------------

def assess_replan_readiness(state: RaceReplanState) -> RaceReplanReadiness:
    """Grade whether there is enough current state to safely compute a snapshot.

    INSUFFICIENT_EVIDENCE — no fuel, or no compound, or no remaining distance.
    LOW_CONFIDENCE       — core present but tyre age unknown (never assumed safe).
    PARTIAL              — core + tyre present but current lap / pit count unknown.
    READY                — all of the above known.
    """
    try:
        v = validate_replan_state(state)
        missing = list(v.missing_state)
        assumptions: list[str] = []

        if not v.can_snapshot:
            return RaceReplanReadiness(
                level=ReplanReadinessLevel.INSUFFICIENT_EVIDENCE,
                missing_state=missing,
                assumptions=assumptions,
                message="Not enough current race state to compute a replan snapshot.",
            )

        if not state.has_tyre_age():
            assumptions.append("Tyre wear is unknown and is NOT assumed safe.")
            return RaceReplanReadiness(
                level=ReplanReadinessLevel.LOW_CONFIDENCE,
                missing_state=missing,
                assumptions=assumptions,
                message="Core state present, but tyre age is unknown — low confidence.",
            )

        if not _known_num(state.current_lap) or not _known_num(state.pit_stops_completed):
            return RaceReplanReadiness(
                level=ReplanReadinessLevel.PARTIAL,
                missing_state=missing,
                assumptions=assumptions,
                message="Most state present; pit-window position is partially known.",
            )

        return RaceReplanReadiness(
            level=ReplanReadinessLevel.READY,
            missing_state=missing,
            assumptions=assumptions,
            message="Current race state is sufficient for a replan check.",
        )
    except Exception:
        return RaceReplanReadiness(
            level=ReplanReadinessLevel.INSUFFICIENT_EVIDENCE,
            missing_state=["fuel_remaining_pct", "current_compound", "remaining_distance"],
            message="Could not assess replan readiness.",
        )


# ---------------------------------------------------------------------------
# Snapshot (scope §4)
# ---------------------------------------------------------------------------

def build_replan_snapshot(
    *,
    pre_race_result,
    state: RaceReplanState,
    event_settings: Optional[dict] = None,
    latest_fuel_samples: Optional[Sequence[float]] = None,
    latest_pace_samples: Optional[Sequence[float]] = None,
) -> RaceReplanSnapshot:
    """Read-only, advisory-only snapshot: is the pre-race plan still viable?

    Compares reported fuel remaining to the pre-race burn rate over the laps to the
    next planned stop. Advisory options are the pre-race Group 48 scored candidates
    (labelled as pre-race estimates). Never applies anything; returns
    INSUFFICIENT_EVIDENCE when critical state or a pre-race plan is missing.
    """
    try:
        rec = getattr(getattr(pre_race_result, "recommendation", None), "recommended", None)
        has_plan = bool(getattr(getattr(pre_race_result, "recommendation", None),
                                "has_recommendation", False)) and rec is not None
        if not has_plan:
            return RaceReplanSnapshot(
                original_plan_status="No pre-race plan available.",
                current_plan_still_viable=None,
                reason=RaceReplanReason.PLAN_MISSING,
                confidence=ReplanConfidence.INSUFFICIENT_EVIDENCE,
                missing_state=["pre_race_plan"],
                driver_message="No pre-race strategy to check. Build a Race Plan first.",
            )

        readiness = assess_replan_readiness(state)
        if readiness.level == ReplanReadinessLevel.INSUFFICIENT_EVIDENCE:
            return RaceReplanSnapshot(
                original_plan_status=f"Pre-race plan: {_plan_name(rec.candidate_id)}.",
                current_plan_still_viable=None,
                reason=RaceReplanReason.INSUFFICIENT_STATE,
                confidence=ReplanConfidence.INSUFFICIENT_EVIDENCE,
                missing_state=readiness.missing_state,
                driver_message=(
                    "Not enough live race data to check the plan. Missing: "
                    + ", ".join(readiness.missing_state) + "."),
            )

        # --- fuel viability vs the next planned stop ---
        fuel_per_lap = _fuel_per_lap(pre_race_result, latest_fuel_samples)
        laps_to_next = _laps_to_next_stop(pre_race_result, rec, state)
        fuel_remaining_l = float(state.fuel_remaining_pct) / 100.0 * _GT7_TANK_L
        options = _advisory_options(pre_race_result, rec)

        # Confidence is capped at MEDIUM for a live snapshot (tyre/pace are proxies),
        # and drops to LOW when tyre age is unknown.
        confidence = ReplanConfidence.LOW if not state.has_tyre_age() else ReplanConfidence.MEDIUM

        if fuel_per_lap <= 0 or laps_to_next <= 0:
            # We know core state but cannot size the fuel window (no burn rate).
            return RaceReplanSnapshot(
                original_plan_status=f"Pre-race plan: {_plan_name(rec.candidate_id)}.",
                current_plan_still_viable=None,
                reason=RaceReplanReason.INSUFFICIENT_STATE,
                confidence=ReplanConfidence.LOW,
                missing_state=readiness.missing_state + (["fuel_burn_rate"] if fuel_per_lap <= 0 else []),
                remaining_strategy_options=options,
                driver_message=(
                    "Plan check limited — the pre-race fuel burn rate is unavailable, "
                    "so fuel margin cannot be sized. Options are pre-race estimates."),
            )

        fuel_needed = fuel_per_lap * laps_to_next
        tyre_note = "" if state.has_tyre_age() else " Tyre state is unknown, so this is low confidence."

        if fuel_remaining_l + 1e-6 >= fuel_needed * _FUEL_MARGIN:
            return RaceReplanSnapshot(
                original_plan_status=f"Pre-race plan: {_plan_name(rec.candidate_id)}.",
                current_plan_still_viable=True,
                reason=RaceReplanReason.VIABLE,
                confidence=confidence,
                missing_state=readiness.missing_state,
                remaining_strategy_options=options,
                driver_message=(
                    f"Current plan still viable. Fuel remaining ({fuel_remaining_l:.1f} L) is "
                    f"tracking within the expected range for the next {laps_to_next} lap(s) "
                    f"(need ~{fuel_needed:.1f} L)." + tyre_note),
            )

        # Fuel below expected → plan needs review.
        deficit = fuel_needed - fuel_remaining_l
        return RaceReplanSnapshot(
            original_plan_status=f"Pre-race plan: {_plan_name(rec.candidate_id)}.",
            current_plan_still_viable=False,
            reason=RaceReplanReason.FUEL_LOW,
            confidence=confidence,
            missing_state=readiness.missing_state,
            remaining_strategy_options=options,
            driver_message=(
                f"Plan needs review. Fuel remaining ({fuel_remaining_l:.1f} L) is below the "
                f"expected range for the planned {_plan_name(rec.candidate_id).lower()} — about "
                f"{deficit:.1f} L short over the next {laps_to_next} lap(s). Consider the options "
                f"below (pre-race estimates)." + tyre_note),
        )
    except Exception:
        return RaceReplanSnapshot(
            original_plan_status="Plan check unavailable.",
            current_plan_still_viable=None,
            reason=RaceReplanReason.INSUFFICIENT_STATE,
            confidence=ReplanConfidence.INSUFFICIENT_EVIDENCE,
            missing_state=["race_state"],
            driver_message="Could not build a replan snapshot from the available data.",
        )


# ---------------------------------------------------------------------------
# Internals (grounded in the pre-race Group 48 result)
# ---------------------------------------------------------------------------

def _plan_name(candidate_id: str) -> str:
    names = {
        "nostop": "no-stop plan", "1stop": "one-stop plan", "2stop": "two-stop plan",
        "3stop": "three-stop plan", "1stop_fuelsave": "fuel-save one-stop plan",
        "2stop_push": "push two-stop plan", "1stop_compound_switch": "compound-switch one-stop plan",
    }
    return names.get(candidate_id, str(candidate_id).replace("_", " ") + " plan")


def _fuel_per_lap(pre_race_result, latest_fuel_samples) -> float:
    """Prefer freshly-supplied live samples; else the pre-race measured burn."""
    try:
        if latest_fuel_samples:
            vals = [float(x) for x in latest_fuel_samples if float(x) > 0]
            if vals:
                return sum(vals) / len(vals)
    except Exception:
        pass
    try:
        return float(pre_race_result.evidence.mean_fuel_per_lap())
    except Exception:
        return 0.0


def _laps_to_next_stop(pre_race_result, rec, state: RaceReplanState) -> int:
    """Laps from the current lap to the next planned pit (or the finish).

    Uses the recommended candidate's stint plan and the reported pit_stops_completed
    / current_lap. Falls back to the reported remaining_laps when the plan cannot
    be located.
    """
    try:
        cand = None
        for c in getattr(pre_race_result, "candidates", ()) or ():
            if getattr(c, "candidate_id", None) == rec.candidate_id:
                cand = c
                break
        laps_per = list(getattr(cand, "estimated_laps_per_stint", []) or []) if cand else []
        stops_done = int(state.pit_stops_completed) if _known_num(state.pit_stops_completed) else 0
        current = int(state.current_lap) if _known_num(state.current_lap) else 0

        if laps_per:
            # Cumulative pit lap after each stint (last boundary = finish).
            cumulative = 0
            boundaries = []
            for laps in laps_per:
                cumulative += int(laps)
                boundaries.append(cumulative)
            # The next boundary after the completed stops.
            idx = min(stops_done, len(boundaries) - 1)
            next_boundary = boundaries[idx]
            to_next = next_boundary - current
            if to_next > 0:
                return to_next
        # Fallback: reported remaining laps.
        if _known_num(state.remaining_laps):
            return int(state.remaining_laps)
        return 0
    except Exception:
        return 0


def _advisory_options(pre_race_result, rec) -> list[RaceReplanOption]:
    """Advisory alternatives = the pre-race scored candidates (labelled pre-race)."""
    try:
        opts: list[RaceReplanOption] = []
        rec_id = rec.candidate_id
        for score in getattr(pre_race_result, "scored_candidates", ()) or ():
            if score.candidate_id == rec_id:
                continue
            gap = score.estimated_gap_to_best_seconds
            delta = "reference" if gap <= 0 else f"+{gap:.1f}s (pre-race estimate)"
            opts.append(RaceReplanOption(
                label=_plan_name(score.candidate_id),
                basis="pre-race scored candidate",
                estimated_delta=delta,
            ))
            if len(opts) >= 3:
                break
        return opts
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Read-only UI placeholder message (scope §6 — no live wiring in this group)
# ---------------------------------------------------------------------------

REPLAN_PLACEHOLDER_MESSAGE = (
    "Live Replan Readiness: not connected yet. A future live-telemetry replan will "
    "require current lap, fuel remaining, current compound, tyre age, and remaining "
    "race distance. This is a read-only foundation — it makes no pit calls, sends no "
    "driver commands, and applies nothing."
)


def replan_placeholder_message() -> str:
    """The read-only 'not connected yet' text for the Strategy Builder placeholder."""
    return REPLAN_PLACEHOLDER_MESSAGE


# ---------------------------------------------------------------------------
# Rendering (pure) — for the optional read-only UI placeholder
# ---------------------------------------------------------------------------

def render_replan_snapshot_text(snapshot: RaceReplanSnapshot) -> str:
    """Plain-text advisory rendering of a snapshot (no HTML dependency)."""
    lines = [snapshot.original_plan_status, ""]
    if snapshot.current_plan_still_viable is True:
        lines.append("Current plan still viable.")
    elif snapshot.current_plan_still_viable is False:
        lines.append("Plan needs review.")
    else:
        lines.append("Plan cannot be checked yet.")
    if snapshot.driver_message:
        lines.append(snapshot.driver_message)
    if snapshot.remaining_strategy_options:
        lines.append("Options:")
        for o in snapshot.remaining_strategy_options:
            lines.append(f"  - {o.label} ({o.estimated_delta})")
    lines.append(f"Confidence: {snapshot.confidence.value}")
    if snapshot.missing_state:
        lines.append("Missing: " + ", ".join(snapshot.missing_state))
    for note in snapshot.safety_notes:
        lines.append(note)
    return "\n".join(lines)
