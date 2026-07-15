"""Deterministic RS/RM/RH tyre performance curves + crossover laps (pure).

Sprint 7 of the determinism rebuild. Race strategy must be built from MEASURED
tyre-age performance for each compound — not generic tyre-life assumptions, an
invented heat window, or one fastest lap. This module models how each compound
performs as it ages and computes the pairwise crossover lap ("RS is fastest
until lap N; after that RM is the better tyre").

Inputs are per-compound lap-time sequences (ms), ordered by tyre age within a
stint. Outputs are pace-by-age curves, degradation onset/slope/cliff, usable
stint windows, evidence quality, and crossovers. Untested compounds produce a
curve flagged ``untested`` so strategy can only surface them as unvalidated
alternatives.

Authors no setup values, calls no AI, touches no Qt/DB/files. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Optional

# Compound hardness — hardest first (lower index = harder). RS softest.
_HARDNESS = {"RH": 0, "RM": 1, "RS": 2, "IM": 5, "W": 6}


def _hardness_index(code: str) -> int:
    return _HARDNESS.get((code or "").upper(), 3)


def _is_slick(code: str) -> bool:
    return (code or "").upper() in ("RH", "RM", "RS", "SH", "SM", "SS")


@dataclass(frozen=True)
class TyreCurveConfig:
    fresh_window: int = 3            # laps used to establish fresh pace
    onset_pct: float = 0.006         # pace rise vs fresh that marks degradation onset
    cliff_pct: float = 0.015         # single-lap jump that marks a cliff
    min_laps_for_curve: int = 3      # below this, evidence quality is "low"/"untested"
    long_run_laps: int = 8           # a "long run" for high confidence


DEFAULT_CONFIG = TyreCurveConfig()


@dataclass(frozen=True)
class TyreEvidenceQuality:
    compound: str
    sample_laps: int
    tested: bool
    confidence: str                  # "high" | "medium" | "low" | "none"
    notes: str = ""


@dataclass(frozen=True)
class CompoundPerformanceCurve:
    compound: str
    hardness_index: int
    pace_by_age_ms: dict             # {age: median pace ms}
    fresh_pace_ms: float
    degradation_onset_lap: int       # first age past fresh threshold (0 = none seen)
    degradation_slope_ms_per_lap: float
    cliff_lap: int                   # first age with a cliff jump (0 = none)
    usable_stint_laps: int           # last competitive age
    sample_laps: int
    evidence: TyreEvidenceQuality

    def pace_at_age(self, age: int) -> float:
        """Median pace at ``age`` (1-based). Extrapolates past measured range
        using the degradation slope from the last measured lap."""
        if not self.pace_by_age_ms:
            return 0.0
        if age in self.pace_by_age_ms:
            return self.pace_by_age_ms[age]
        ages = sorted(self.pace_by_age_ms)
        if age < ages[0]:
            return self.pace_by_age_ms[ages[0]]
        last = ages[-1]
        return self.pace_by_age_ms[last] + self.degradation_slope_ms_per_lap * (age - last)

    @property
    def tested(self) -> bool:
        return self.evidence.tested


@dataclass(frozen=True)
class UsableStintWindow:
    compound: str
    max_usable_laps: int
    reason: str


@dataclass(frozen=True)
class TyreCrossover:
    softer: str
    harder: str
    crossover_after_lap: int          # last stint-lap the softer is still the better tyre
    softer_pace_at_crossover_ms: float
    harder_pace_at_crossover_ms: float
    confidence: str
    note: str = ""


# --------------------------------------------------------------------------- #
def build_compound_curve(
    compound: str, lap_times_ms, config: TyreCurveConfig = DEFAULT_CONFIG,
) -> CompoundPerformanceCurve:
    """Build a pace-by-tyre-age curve for one compound from a lap sequence.

    ``lap_times_ms`` is ordered by tyre age (index 0 = first stint lap). For a
    real multi-stint compound the caller should pass the median at each age; a
    single clean stint works directly for acceptance.
    """
    cfg = config or DEFAULT_CONFIG
    laps = [float(t) for t in (lap_times_ms or []) if t and float(t) > 0]
    hardness = _hardness_index(compound)

    if not laps:
        return CompoundPerformanceCurve(
            compound=compound, hardness_index=hardness, pace_by_age_ms={},
            fresh_pace_ms=0.0, degradation_onset_lap=0,
            degradation_slope_ms_per_lap=0.0, cliff_lap=0, usable_stint_laps=0,
            sample_laps=0,
            evidence=TyreEvidenceQuality(compound, 0, tested=False, confidence="none",
                                         notes="no laps recorded — untested compound"),
        )

    pace_by_age = {i + 1: t for i, t in enumerate(laps)}
    fresh = median(laps[:cfg.fresh_window]) if len(laps) >= 1 else laps[0]

    # Degradation onset: first age whose pace rises past the fresh threshold.
    onset = 0
    onset_threshold = fresh * (1.0 + cfg.onset_pct)
    for age, t in pace_by_age.items():
        if age > cfg.fresh_window and t > onset_threshold:
            onset = age
            break

    # Cliff: first age with a single-lap jump beyond cliff_pct.
    cliff = 0
    prev = None
    for age in sorted(pace_by_age):
        t = pace_by_age[age]
        if prev is not None and t > prev * (1.0 + cfg.cliff_pct):
            cliff = age
            break
        prev = t

    # Slope after onset (linear-ish): mean per-lap rise from onset to end.
    slope = 0.0
    if onset and onset < len(laps):
        tail = [pace_by_age[a] for a in sorted(pace_by_age) if a >= onset]
        if len(tail) >= 2:
            slope = (tail[-1] - tail[0]) / (len(tail) - 1)

    # Usable stint: last age still within the fresh threshold (before onset), or
    # the lap before the cliff, whichever is defined.
    if cliff:
        usable = cliff - 1
    elif onset:
        usable = onset - 1
    else:
        usable = len(laps)
    usable = max(0, usable)

    n = len(laps)
    if n >= cfg.long_run_laps:
        conf = "high"
    elif n >= cfg.min_laps_for_curve:
        conf = "medium"
    else:
        conf = "low"
    evidence = TyreEvidenceQuality(
        compound=compound, sample_laps=n, tested=True, confidence=conf,
        notes=f"{n} measured laps",
    )

    return CompoundPerformanceCurve(
        compound=compound, hardness_index=hardness, pace_by_age_ms=pace_by_age,
        fresh_pace_ms=round(fresh, 1), degradation_onset_lap=onset,
        degradation_slope_ms_per_lap=round(slope, 1), cliff_lap=cliff,
        usable_stint_laps=usable, sample_laps=n, evidence=evidence,
    )


def build_compound_curves(
    sequences_by_compound: dict, config: TyreCurveConfig = DEFAULT_CONFIG,
) -> dict:
    """Return {compound: CompoundPerformanceCurve} for every compound present."""
    return {c: build_compound_curve(c, seq, config)
            for c, seq in (sequences_by_compound or {}).items()}


def usable_stint_window(curve: CompoundPerformanceCurve) -> UsableStintWindow:
    if not curve.tested:
        return UsableStintWindow(curve.compound, 0, "untested compound — no usable window")
    if curve.cliff_lap:
        return UsableStintWindow(curve.compound, curve.usable_stint_laps,
                                 f"cliff at lap {curve.cliff_lap}")
    if curve.degradation_onset_lap:
        return UsableStintWindow(curve.compound, curve.usable_stint_laps,
                                 f"degradation onset at lap {curve.degradation_onset_lap}")
    return UsableStintWindow(curve.compound, curve.usable_stint_laps,
                             "no degradation seen within measured laps")


def compute_crossovers(curves: dict) -> list:
    """Return pairwise crossovers between each compound and the next-harder one
    that is present. A crossover is the last stint-lap on which the softer
    compound is still the better tyre; from the next lap the harder compound is
    faster (its pace-by-age is lower).
    """
    tested = [c for c in curves.values() if c.tested]
    # Order softest-first (highest hardness index first).
    tested.sort(key=lambda c: -c.hardness_index)
    crossovers: list = []
    for i in range(len(tested) - 1):
        softer = tested[i]
        harder = tested[i + 1]
        max_age = max(
            (max(softer.pace_by_age_ms) if softer.pace_by_age_ms else 0),
            (max(harder.pace_by_age_ms) if harder.pace_by_age_ms else 0),
        )
        crossover_after = 0
        s_at = h_at = 0.0
        found = False
        for age in range(1, max_age + 1):
            s_pace = softer.pace_at_age(age)
            h_pace = harder.pace_at_age(age)
            if s_pace <= 0 or h_pace <= 0:
                continue
            if s_pace > h_pace:
                crossover_after = age - 1
                s_at = softer.pace_at_age(age)
                h_at = harder.pace_at_age(age)
                found = True
                break
        conf = "low"
        if found and softer.sample_laps >= 3 and harder.sample_laps >= 3:
            conf = "high" if (softer.sample_laps >= 8 or harder.sample_laps >= 8) else "medium"
        note = "" if found else "softer stays faster across all measured laps"
        crossovers.append(TyreCrossover(
            softer=softer.compound, harder=harder.compound,
            crossover_after_lap=crossover_after,
            softer_pace_at_crossover_ms=round(s_at, 1),
            harder_pace_at_crossover_ms=round(h_at, 1),
            confidence=conf, note=note,
        ))
    return crossovers
