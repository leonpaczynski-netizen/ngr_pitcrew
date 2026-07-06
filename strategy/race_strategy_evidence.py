"""Group 48 — Race Strategy Brain Phase 2: telemetry-based strategy evidence.

WHY IT EXISTS
  The Race Strategy Brain must answer "what strategy gives the best *total race
  result*, not just the fastest lap?".  Before any candidate can be generated or
  scored, we need a single, typed, deterministic snapshot of everything the app
  actually knows about the event and the driver's real session data — and, just
  as importantly, an honest record of what it does NOT know.

  This module owns that snapshot: :class:`RaceStrategyEvidence`.  It carries the
  event rules (multipliers, refuel rate, pit loss, compound requirements) plus
  the *measured* samples (lap times, fuel use, tyre wear, per-compound pace) and
  a computed :class:`StrategyConfidence` that degrades as evidence goes missing.

WHAT THIS MODULE IS NOT
  • It is NOT an AI.  It invents no numbers.  A field that is unavailable is
    recorded in ``missing_evidence`` — never guessed.
  • It authors no setup values and touches no setup dict, the Apply gate, or any
    approved/rejected setup recommendation (Group 43-47 guarantees preserved).
  • It performs no I/O: no PyQt6, no sqlite3, no file access, no network.  The
    builder takes plain values / sample lists so it is unit-testable without a
    QApplication and free of import cycles (mirrors strategy/feasibility.py).

PURITY CONTRACT (mirrors strategy/outcome.py + strategy/setup_outcome_verification.py)
  • Never raises: the public builder wraps its internals and always returns a
    valid evidence object (worst case: everything missing, confidence
    INSUFFICIENT_EVIDENCE).
  • Deterministic: identical inputs → identical evidence and confidence.

GT7 DOMAIN FACTS
  • Full tank is always 100.0 L (100 % == 100 L; starting fuel == 100).  See
    [[reference-gt7-fuel-units]].
  • Event ``pit_loss_secs`` is authoritative; seed-track pit deltas are not used.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from statistics import mean, pstdev
from typing import Sequence

# GT7 domain constant: full tank is always 100 litres.
GT7_TANK_CAPACITY_L: float = 100.0


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

class StrategyConfidence(str, Enum):
    """Confidence in a strategy conclusion, driven by available evidence.

    Ordered worst-to-best via :meth:`rank` so callers can take the minimum of
    two confidences (evidence vs candidate) without hard-coding an ordering.
    """

    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def rank(self) -> int:
        return _CONFIDENCE_RANK[self]

    @classmethod
    def worst(cls, *values: "StrategyConfidence") -> "StrategyConfidence":
        """Return the least-confident of the given values (safe on empty)."""
        vals = [v for v in values if isinstance(v, StrategyConfidence)]
        if not vals:
            return cls.INSUFFICIENT_EVIDENCE
        return min(vals, key=lambda v: v.rank)


_CONFIDENCE_RANK: dict[StrategyConfidence, int] = {
    StrategyConfidence.INSUFFICIENT_EVIDENCE: 0,
    StrategyConfidence.LOW: 1,
    StrategyConfidence.MEDIUM: 2,
    StrategyConfidence.HIGH: 3,
}


# ---------------------------------------------------------------------------
# Missing-evidence codes (stable identifiers; the .value is human-readable)
# ---------------------------------------------------------------------------

MISSING_LAP_SAMPLES = "no_lap_time_samples"
MISSING_FUEL_SAMPLES = "no_fuel_use_samples"
MISSING_TYRE_WEAR_SAMPLES = "no_tyre_wear_samples"
MISSING_LONG_RUN_DATA = "no_long_run_data"
MISSING_PIT_LOSS = "pit_loss_unknown"
MISSING_REFUEL_RATE = "refuel_rate_unknown"
MISSING_COMPOUND_DATA = "no_per_compound_pace"
UNSTABLE_WEATHER = "weather_unstable"
POOR_DRIVER_CONSISTENCY = "driver_consistency_poor"
MISSING_FUEL_MULTIPLIER = "fuel_multiplier_unknown"
MISSING_TYRE_MULTIPLIER = "tyre_multiplier_unknown"

# Human-readable descriptions keyed by code.  Used by the explanation surface so
# the driver sees plain English, not an enum name.
MISSING_EVIDENCE_TEXT: dict[str, str] = {
    MISSING_LAP_SAMPLES: "No clean lap-time samples recorded.",
    MISSING_FUEL_SAMPLES: "No fuel-use-per-lap samples recorded.",
    MISSING_TYRE_WEAR_SAMPLES: "No tyre-wear samples recorded.",
    MISSING_LONG_RUN_DATA: "No long-run (full-stint) data — degradation is estimated from a short sample.",
    MISSING_PIT_LOSS: "Pit-lane loss is unknown — using the event default.",
    MISSING_REFUEL_RATE: "Refuel rate is unknown — refuel time cannot be calculated.",
    MISSING_COMPOUND_DATA: "No per-compound pace data — compound deltas are not modelled.",
    UNSTABLE_WEATHER: "Weather is random or unstable — degradation and pace are less predictable.",
    POOR_DRIVER_CONSISTENCY: "Driver lap-time consistency is poor — projections carry more spread.",
    MISSING_FUEL_MULTIPLIER: "Fuel multiplier is unknown.",
    MISSING_TYRE_MULTIPLIER: "Tyre-wear multiplier is unknown.",
}

# Thresholds --------------------------------------------------------------

# A comparison needs at least this many clean lap samples to be trusted at all.
MIN_LAP_SAMPLES: int = 3

# Degradation is only "long-run" (HIGH-confidence) with at least this many laps.
# Matches the 8-clean-lap eligibility rule in strategy/feasibility.py.
MIN_LONG_RUN_LAPS: int = 8

# Coefficient-of-variation (stdev / mean) above which lap-time consistency is
# considered "poor".  A tenth of a second of spread on a 100 s lap is 0.001; a
# genuinely inconsistent driver swings whole seconds → cv above ~0.015.
POOR_CONSISTENCY_CV: float = 0.015


# ---------------------------------------------------------------------------
# Evidence model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RaceStrategyEvidence:
    """Deterministic snapshot of everything known about a race-strategy problem.

    Event rules and measured samples in one place, plus an honest
    ``missing_evidence`` list and a computed ``evidence_confidence``.  Frozen so
    a candidate generator / scorer can hold a reference without fear of mutation.

    All sample lists default to empty; all optional numeric event fields default
    to a sentinel (0.0 / "") that the builder treats as "unknown" and records in
    ``missing_evidence``.  No field is ever populated with a guessed value.
    """

    # --- identity / event ------------------------------------------------
    car_id: int = 0
    track: str = ""
    layout_id: str = ""
    race_duration_minutes: float = 0.0     # timed events; 0 when lap-limited
    race_laps: int = 0                     # authoritative for lap races; estimated for timed
    fuel_multiplier: float = 0.0           # 0 == unknown
    tyre_multiplier: float = 0.0           # 0 == unknown
    refuel_rate_lps: float = 0.0           # L/sec; 0 == unknown
    pit_loss_seconds: float = 0.0          # 0 == unknown (event default used downstream)
    starting_fuel_pct: float = 100.0       # GT7 default full tank
    fuel_capacity_basis: float = GT7_TANK_CAPACITY_L

    # --- legality --------------------------------------------------------
    available_compounds: tuple[str, ...] = ()
    required_compounds: tuple[str, ...] = ()     # compounds a legal plan MUST use
    mandatory_pit_stops: int = 0

    # --- environment -----------------------------------------------------
    weather_context: str = "dry_stable"    # "dry_stable" | "random" | "wet" | "unstable" | "unknown"

    # --- measured samples (never invented) -------------------------------
    lap_time_samples: tuple[float, ...] = ()     # clean lap times, seconds
    fuel_use_samples: tuple[float, ...] = ()     # litres per lap
    tyre_wear_samples: tuple[float, ...] = ()    # per-lap wear or pace-loss proxy
    compound_samples: dict = field(default_factory=dict)  # {compound: [lap_time_s, ...]}

    # --- derived / honesty ----------------------------------------------
    driver_consistency: float = 0.0        # coefficient of variation of lap_time_samples (0 == unknown)
    evidence_confidence: StrategyConfidence = StrategyConfidence.INSUFFICIENT_EVIDENCE
    missing_evidence: tuple[str, ...] = ()

    # ------------------------------------------------------------------
    # Convenience accessors (pure, no invention)
    # ------------------------------------------------------------------

    def has_lap_data(self) -> bool:
        return len(self.lap_time_samples) >= MIN_LAP_SAMPLES

    def has_fuel_data(self) -> bool:
        return len(self.fuel_use_samples) > 0

    def has_long_run_data(self) -> bool:
        return len(self.tyre_wear_samples) >= MIN_LONG_RUN_LAPS

    def representative_lap_s(self) -> float:
        """Race-pace reference: the MEDIAN clean lap, not the fastest.

        Group 48 optimises total race result, so the representative pace is a
        robust central lap the driver can actually repeat, not a one-off flying
        lap.  Returns 0.0 when there is no lap data (caller must treat as unknown).
        """
        laps = sorted(self.lap_time_samples)
        n = len(laps)
        if n == 0:
            return 0.0
        mid = n // 2
        if n % 2 == 1:
            return laps[mid]
        return (laps[mid - 1] + laps[mid]) / 2.0

    def mean_fuel_per_lap(self) -> float:
        """Mean measured fuel use per lap, or 0.0 when unknown."""
        return mean(self.fuel_use_samples) if self.fuel_use_samples else 0.0

    def compound_pace_s(self, compound: str) -> float:
        """Median measured lap time for a compound, or 0.0 when no samples."""
        samples = self.compound_samples.get(compound) if self.compound_samples else None
        if not samples:
            return 0.0
        s = sorted(samples)
        mid = len(s) // 2
        if len(s) % 2 == 1:
            return s[mid]
        return (s[mid - 1] + s[mid]) / 2.0

    def missing_evidence_text(self) -> list[str]:
        """Human-readable descriptions for every recorded missing-evidence code."""
        return [MISSING_EVIDENCE_TEXT.get(code, code) for code in self.missing_evidence]


# ---------------------------------------------------------------------------
# Consistency helper
# ---------------------------------------------------------------------------

def compute_consistency(lap_time_samples: Sequence[float]) -> float:
    """Coefficient of variation (population stdev / mean) of lap times.

    Lower is more consistent.  Returns 0.0 when fewer than 2 samples (unknown).
    Never raises.
    """
    try:
        laps = [float(x) for x in lap_time_samples if float(x) > 0.0]
        if len(laps) < 2:
            return 0.0
        m = mean(laps)
        if m <= 0.0:
            return 0.0
        return pstdev(laps) / m
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_strategy_evidence(
    *,
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
    weather_context: str = "dry_stable",
    lap_time_samples: Sequence[float] = (),
    fuel_use_samples: Sequence[float] = (),
    tyre_wear_samples: Sequence[float] = (),
    compound_samples: dict | None = None,
) -> RaceStrategyEvidence:
    """Build a :class:`RaceStrategyEvidence` from available event + session data.

    Records — but never fabricates — missing evidence, and derives an honest
    :class:`StrategyConfidence`.  Never raises: on any internal error it returns
    an INSUFFICIENT_EVIDENCE snapshot carrying whatever identity fields parsed.

    The caller supplies only values it genuinely has; anything left at its
    sentinel default (0 / "" / empty) is treated as unknown and flagged.
    """
    try:
        laps = tuple(float(x) for x in lap_time_samples if _pos(x))
        fuel = tuple(float(x) for x in fuel_use_samples if _pos(x))
        wear = tuple(float(x) for x in tyre_wear_samples if x is not None)
        comp_samples: dict = {}
        if compound_samples:
            for k, v in compound_samples.items():
                vals = tuple(float(x) for x in (v or []) if _pos(x))
                if vals:
                    comp_samples[str(k)] = vals

        avail = tuple(str(c) for c in available_compounds if str(c))
        req = tuple(str(c) for c in required_compounds if str(c))

        consistency = compute_consistency(laps)

        missing: list[str] = []

        # --- sample coverage ---
        if len(laps) < MIN_LAP_SAMPLES:
            missing.append(MISSING_LAP_SAMPLES)
        if not fuel:
            missing.append(MISSING_FUEL_SAMPLES)
        if not wear:
            missing.append(MISSING_TYRE_WEAR_SAMPLES)
        elif len(wear) < MIN_LONG_RUN_LAPS:
            missing.append(MISSING_LONG_RUN_DATA)
        if not comp_samples:
            missing.append(MISSING_COMPOUND_DATA)

        # --- event rules ---
        if not _pos(pit_loss_seconds):
            missing.append(MISSING_PIT_LOSS)
        if not _pos(refuel_rate_lps):
            missing.append(MISSING_REFUEL_RATE)
        if not _pos(fuel_multiplier):
            missing.append(MISSING_FUEL_MULTIPLIER)
        if not _pos(tyre_multiplier):
            missing.append(MISSING_TYRE_MULTIPLIER)

        # --- environment ---
        if weather_context in ("random", "unstable", "wet"):
            missing.append(UNSTABLE_WEATHER)

        # --- driver ---
        if consistency > POOR_CONSISTENCY_CV:
            missing.append(POOR_DRIVER_CONSISTENCY)

        confidence = _grade_confidence(
            has_lap=len(laps) >= MIN_LAP_SAMPLES,
            has_fuel=bool(fuel),
            has_long_run=len(wear) >= MIN_LONG_RUN_LAPS,
            has_pit_loss=_pos(pit_loss_seconds),
            has_refuel=_pos(refuel_rate_lps),
            weather_stable=weather_context not in ("random", "unstable", "wet"),
            consistency_ok=(consistency <= POOR_CONSISTENCY_CV) if consistency > 0 else True,
        )

        return RaceStrategyEvidence(
            car_id=int(car_id or 0),
            track=str(track or ""),
            layout_id=str(layout_id or ""),
            race_duration_minutes=float(race_duration_minutes or 0.0),
            race_laps=int(race_laps or 0),
            fuel_multiplier=float(fuel_multiplier or 0.0),
            tyre_multiplier=float(tyre_multiplier or 0.0),
            refuel_rate_lps=float(refuel_rate_lps or 0.0),
            pit_loss_seconds=float(pit_loss_seconds or 0.0),
            starting_fuel_pct=float(starting_fuel_pct if starting_fuel_pct is not None else 100.0),
            fuel_capacity_basis=GT7_TANK_CAPACITY_L,
            available_compounds=avail,
            required_compounds=req,
            mandatory_pit_stops=int(mandatory_pit_stops or 0),
            weather_context=str(weather_context or "unknown"),
            lap_time_samples=laps,
            fuel_use_samples=fuel,
            tyre_wear_samples=wear,
            compound_samples=comp_samples,
            driver_consistency=consistency,
            evidence_confidence=confidence,
            missing_evidence=tuple(missing),
        )
    except Exception:
        return RaceStrategyEvidence(
            car_id=int(car_id or 0) if isinstance(car_id, (int, float)) else 0,
            track=str(track or ""),
            evidence_confidence=StrategyConfidence.INSUFFICIENT_EVIDENCE,
            missing_evidence=(MISSING_LAP_SAMPLES, MISSING_FUEL_SAMPLES),
        )


def evidence_from_race_params(
    params,
    *,
    lap_time_samples: Sequence[float] = (),
    fuel_use_samples: Sequence[float] = (),
    tyre_wear_samples: Sequence[float] = (),
    compound_samples: dict | None = None,
    weather_context: str = "dry_stable",
) -> RaceStrategyEvidence:
    """Adapt an existing :class:`strategy.ai_planner.RaceParams` into evidence.

    Convenience bridge for integration with the existing strategy pipeline.
    Reads only fields RaceParams already exposes — it does not reach into the DB
    or invent anything.  ``fuel_burn_per_lap`` on params seeds a single fuel
    sample only when no measured ``fuel_use_samples`` are supplied.
    """
    fuel = list(fuel_use_samples)
    if not fuel:
        burn = float(getattr(params, "fuel_burn_per_lap", 0.0) or 0.0)
        if burn > 0:
            fuel = [burn]

    race_laps = int(getattr(params, "total_laps", 0) or 0)
    duration = 0.0
    if getattr(params, "race_type", "lap") == "timed":
        duration = float(getattr(params, "duration_mins", 0) or 0)

    return build_strategy_evidence(
        car_id=int(getattr(params, "car_id", 0) or 0),
        track=str(getattr(params, "track", "") or ""),
        layout_id=str(getattr(params, "layout_id", "") or ""),
        race_duration_minutes=duration,
        race_laps=race_laps,
        fuel_multiplier=float(getattr(params, "fuel_multiplier", 0.0) or 0.0),
        tyre_multiplier=float(getattr(params, "tyre_wear_multiplier", 0.0) or 0.0),
        refuel_rate_lps=float(getattr(params, "refuel_speed_lps", 0.0) or 0.0),
        pit_loss_seconds=float(getattr(params, "pit_loss_secs", 0.0) or 0.0),
        available_compounds=list(getattr(params, "avail_tyres", []) or []),
        required_compounds=list(getattr(params, "mandatory_compounds", []) or []),
        mandatory_pit_stops=int(getattr(params, "min_mandatory_stops", 0) or 0),
        weather_context=weather_context,
        lap_time_samples=lap_time_samples,
        fuel_use_samples=fuel,
        tyre_wear_samples=tyre_wear_samples,
        compound_samples=compound_samples,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _pos(x) -> bool:
    """True when x is a positive real number."""
    try:
        return float(x) > 0.0
    except (TypeError, ValueError):
        return False


def _grade_confidence(
    *,
    has_lap: bool,
    has_fuel: bool,
    has_long_run: bool,
    has_pit_loss: bool,
    has_refuel: bool,
    weather_stable: bool,
    consistency_ok: bool,
) -> StrategyConfidence:
    """Grade overall evidence confidence deterministically.

    Rules (honest, conservative):
      • Without lap pace OR without fuel data we cannot estimate total race time
        at all → INSUFFICIENT_EVIDENCE.
      • With the core (lap + fuel + refuel + pit loss) plus long-run degradation,
        stable weather and acceptable consistency → HIGH.
      • Missing long-run degradation, or unstable weather, or poor consistency,
        drops one step from HIGH to MEDIUM.
      • Missing refuel rate or pit loss (pit maths weakened) drops to LOW.
    """
    if not has_lap or not has_fuel:
        return StrategyConfidence.INSUFFICIENT_EVIDENCE

    if not has_refuel or not has_pit_loss:
        return StrategyConfidence.LOW

    # Core pit maths is intact; grade on degradation / environment quality.
    soft_gaps = 0
    if not has_long_run:
        soft_gaps += 1
    if not weather_stable:
        soft_gaps += 1
    if not consistency_ok:
        soft_gaps += 1

    if soft_gaps == 0:
        return StrategyConfidence.HIGH
    if soft_gaps == 1:
        return StrategyConfidence.MEDIUM
    return StrategyConfidence.LOW
