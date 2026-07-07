"""Group 59 — GT7 ``road_distance`` zero-point semantics validation (pure).

WHY IT EXISTS
  The Group 58 road-distance fallback derives per-lap distance from a captured
  lap-start reference, ASSUMING ``road_distance`` is a cumulative running total.
  That assumption has not been validated across tracks. This module is a pure,
  deterministic validator that records and compares lap-boundary road-distance
  evidence and reports whether the signal behaves cumulatively, resets per lap,
  is inconsistent, or lacks enough evidence to say — WITHOUT assuming the answer.

WHAT THIS MODULE IS
  A pure analysis tool for manual UAT and future asset/fallback decisions. It
  never changes live strategy behaviour by itself. It never raises, rejects
  NaN/inf, handles missing lap numbers and negative deltas honestly, and compares
  per-lap deltas to a TRUSTED lap length conservatively (only when one is given).

WHAT THIS MODULE IS NOT
  • Not a live controller — it produces evidence, not decisions.
  • No Qt, no DB, no AI, no filesystem writes. Deterministic and offline-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

# Per-lap delta is "plausible" when within this fraction of a trusted lap length.
_DELTA_TOL_FRAC = 0.05
# Consecutive laps are "continuous" when start(N+1) ≈ end(N) within this fraction.
_CONTINUITY_TOL_FRAC = 0.02
# A lap start counts as "reset near zero" when below this fraction of the reference.
_RESET_NEAR_ZERO_FRAC = 0.05
# Deltas are "consistent" when their spread stays within this fraction of the mean.
_DELTA_CONSISTENCY_FRAC = 0.10


class RoadDistanceSemanticsStatus(str, Enum):
    CUMULATIVE_CONFIRMED = "CUMULATIVE_CONFIRMED"
    PER_LAP_RESET_CONFIRMED = "PER_LAP_RESET_CONFIRMED"
    INCONSISTENT = "INCONSISTENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RoadDistanceSample:
    """One captured lap-boundary observation of GT7 ``road_distance``.

    ``start_distance`` is the reading at lap start; ``end_distance`` the reading at
    lap end (just before the next lap start). Both are raw cumulative-or-not metres.
    """
    lap_number: int
    start_distance: float
    end_distance: float


@dataclass(frozen=True)
class RoadDistanceLapEvidence:
    """Validated per-lap evidence derived from a sample."""
    lap_number: int
    start_distance: float
    end_distance: float
    delta: float
    matches_lap_length: Optional[bool]   # None when no trusted lap length given
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RoadDistanceSemanticsResult:
    """Outcome of analysing road-distance behaviour for a track/layout."""
    status: RoadDistanceSemanticsStatus
    laps: Tuple[RoadDistanceLapEvidence, ...] = ()
    lap_count: int = 0
    mean_delta: Optional[float] = None
    lap_length_m: Optional[float] = None
    appears_cumulative: Optional[bool] = None
    message: str = ""
    warnings: Tuple[str, ...] = ()
    missing: Tuple[str, ...] = ()

    @property
    def is_confirmed(self) -> bool:
        return self.status in (
            RoadDistanceSemanticsStatus.CUMULATIVE_CONFIRMED,
            RoadDistanceSemanticsStatus.PER_LAP_RESET_CONFIRMED,
        )


# ---------------------------------------------------------------------------
# Numeric helpers (reject NaN/inf; never raise)
# ---------------------------------------------------------------------------

def _finite(v) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _int_or_none(v) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Evidence building
# ---------------------------------------------------------------------------

def build_lap_evidence(
    samples: Sequence,
    lap_length_m=None,
) -> List[RoadDistanceLapEvidence]:
    """Build validated per-lap evidence from raw samples. Never raises.

    Skips samples with non-finite start/end. A missing lap number is tolerated
    (positional index used). Negative deltas are kept but flagged.
    """
    lap = _finite(lap_length_m)
    out: List[RoadDistanceLapEvidence] = []
    try:
        for i, s in enumerate(samples or ()):
            start = _finite(getattr(s, "start_distance", None)
                            if not isinstance(s, dict) else s.get("start_distance"))
            end = _finite(getattr(s, "end_distance", None)
                          if not isinstance(s, dict) else s.get("end_distance"))
            if start is None or end is None:
                continue
            ln = _int_or_none(getattr(s, "lap_number", None)
                              if not isinstance(s, dict) else s.get("lap_number"))
            if ln is None:
                ln = i + 1
            delta = end - start
            warns: List[str] = []
            if delta < 0:
                warns.append(f"lap {ln}: negative road-distance delta ({delta:.1f} m)")
            matches = None
            if lap is not None and lap > 0:
                matches = abs(delta - lap) <= _DELTA_TOL_FRAC * lap
                if not matches and delta >= 0:
                    warns.append(
                        f"lap {ln}: delta {delta:.1f} m not close to lap length {lap:.1f} m")
            out.append(RoadDistanceLapEvidence(
                lap_number=ln, start_distance=start, end_distance=end,
                delta=delta, matches_lap_length=matches, warnings=tuple(warns)))
        return out
    except Exception:
        return out


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyse_road_distance_semantics(
    samples: Sequence,
    lap_length_m=None,
) -> RoadDistanceSemanticsResult:
    """Classify GT7 road-distance behaviour from lap-boundary samples. Never raises.

    Returns a ``RoadDistanceSemanticsResult`` with a status:
      CUMULATIVE_CONFIRMED   — starts increase and start(N+1) ≈ end(N) (continuous).
      PER_LAP_RESET_CONFIRMED— starts reset near zero every lap; deltas ≈ lap length.
      INCONSISTENT           — conflicting / negative / wildly varying evidence.
      INSUFFICIENT_EVIDENCE  — fewer than two usable laps.
      UNKNOWN                — no usable samples at all.
    """
    try:
        lap_len = _finite(lap_length_m)
        laps = build_lap_evidence(samples, lap_length_m=lap_len)
        warnings: List[str] = []
        missing: List[str] = []
        for e in laps:
            warnings.extend(e.warnings)

        if not laps:
            return RoadDistanceSemanticsResult(
                status=RoadDistanceSemanticsStatus.UNKNOWN,
                laps=(), lap_count=0, lap_length_m=lap_len,
                message="No usable road-distance samples were provided.",
                missing=("road-distance samples",))

        if lap_len is None:
            missing.append("trusted lap length")

        deltas = [e.delta for e in laps]
        mean_delta = sum(deltas) / len(deltas) if deltas else None

        if len(laps) < 2:
            return RoadDistanceSemanticsResult(
                status=RoadDistanceSemanticsStatus.INSUFFICIENT_EVIDENCE,
                laps=tuple(laps), lap_count=len(laps), mean_delta=mean_delta,
                lap_length_m=lap_len,
                message="Need at least two completed laps to validate road-distance semantics.",
                warnings=tuple(dict.fromkeys(warnings)),
                missing=tuple(dict.fromkeys(missing + ["second completed lap"])))

        # Reference length for relative comparisons: trusted lap length else mean delta.
        ref = lap_len if (lap_len is not None and lap_len > 0) else abs(mean_delta or 0.0)
        starts = [e.start_distance for e in laps]
        ends = [e.end_distance for e in laps]

        any_negative = any(d < 0 for d in deltas)

        # Delta consistency (spread relative to mean).
        consistent = False
        if mean_delta and abs(mean_delta) > 1e-9:
            spread = max(deltas) - min(deltas)
            consistent = spread <= _DELTA_CONSISTENCY_FRAC * abs(mean_delta)

        # Plausible vs trusted lap length.
        plausible = None
        if lap_len is not None and lap_len > 0:
            plausible = all(e.matches_lap_length for e in laps
                            if e.matches_lap_length is not None)

        # Cumulative signal: starts strictly increasing AND start(N+1) ≈ end(N).
        increasing = all(starts[i + 1] > starts[i] for i in range(len(starts) - 1))
        cont_tol = _CONTINUITY_TOL_FRAC * ref if ref > 0 else 1.0
        continuous = all(abs(starts[i + 1] - ends[i]) <= cont_tol
                         for i in range(len(starts) - 1))

        # Reset signal: every lap start near zero relative to the reference.
        near_zero_tol = _RESET_NEAR_ZERO_FRAC * ref if ref > 0 else 1.0
        resets = all(abs(s) <= near_zero_tol for s in starts)

        cumulative_ok = increasing and continuous and (plausible is not False) and not any_negative
        reset_ok = resets and consistent and (plausible is not False) and not any_negative

        if cumulative_ok and not reset_ok:
            status = RoadDistanceSemanticsStatus.CUMULATIVE_CONFIRMED
            appears_cumulative = True
            message = "road_distance behaves cumulatively (starts increase, continuous across laps)."
        elif reset_ok and not cumulative_ok:
            status = RoadDistanceSemanticsStatus.PER_LAP_RESET_CONFIRMED
            appears_cumulative = False
            message = "road_distance resets per lap (each lap starts near zero)."
        elif any_negative or (cumulative_ok and reset_ok):
            status = RoadDistanceSemanticsStatus.INCONSISTENT
            appears_cumulative = None
            message = "road_distance behaviour is inconsistent across the sampled laps."
            if not any_negative:
                warnings.append("cumulative and reset signals both matched — treat as inconsistent")
        else:
            status = RoadDistanceSemanticsStatus.INSUFFICIENT_EVIDENCE
            appears_cumulative = None
            message = "Not enough consistent evidence to confirm road-distance semantics."

        if lap_len is None:
            warnings.append("lap length unavailable — delta plausibility not checked")

        return RoadDistanceSemanticsResult(
            status=status, laps=tuple(laps), lap_count=len(laps),
            mean_delta=mean_delta, lap_length_m=lap_len,
            appears_cumulative=appears_cumulative, message=message,
            warnings=tuple(dict.fromkeys(warnings)), missing=tuple(dict.fromkeys(missing)))
    except Exception:
        return RoadDistanceSemanticsResult(
            status=RoadDistanceSemanticsStatus.UNKNOWN,
            message="Road-distance semantics could not be analysed.",
            warnings=("analysis error — treated as unknown",))


# ---------------------------------------------------------------------------
# Rendering (pure, driver-readable, honest, no command wording)
# ---------------------------------------------------------------------------

def format_road_distance_semantics(result: RoadDistanceSemanticsResult) -> dict:
    """Return {'found', 'warnings', 'missing'} lines summarising the semantics result."""
    found: List[str] = []
    warnings: List[str] = []
    missing: List[str] = []
    try:
        if result is None:
            return {"found": [], "warnings": [], "missing": ["road-distance semantics unavailable"]}
        status = result.status.value
        _labels = {
            "CUMULATIVE_CONFIRMED": "cumulative behaviour confirmed",
            "PER_LAP_RESET_CONFIRMED": "per-lap reset confirmed",
            "INCONSISTENT": "inconsistent (do not trust)",
            "INSUFFICIENT_EVIDENCE": "insufficient evidence",
            "UNKNOWN": "unknown",
        }
        found.append(f"road-distance semantics: {_labels.get(status, status.lower())}")
        if result.lap_count:
            found.append(f"laps sampled: {result.lap_count}")
        if result.mean_delta is not None:
            found.append(f"mean per-lap delta: {result.mean_delta:,.0f} m")
        if result.lap_length_m:
            found.append(f"trusted lap length: {result.lap_length_m:,.0f} m")
        else:
            missing.append("trusted lap length")
        for w in result.warnings:
            if w not in warnings:
                warnings.append(w)
        for m in result.missing:
            if m not in missing:
                missing.append(m)
        return {"found": found, "warnings": warnings, "missing": missing}
    except Exception:
        return {"found": [], "warnings": [], "missing": ["road-distance semantics unavailable"]}
