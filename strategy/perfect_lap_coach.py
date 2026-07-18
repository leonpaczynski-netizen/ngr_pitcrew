"""Perfect-lap driving coach (pure, deterministic).

Holistic brain, Phase 2. Aggregates per-corner reference points
(``strategy.lap_corner_extraction.CornerReferencePoints``) across the driver's
clean laps into an IDEAL lap — **best executed value per corner** (theoretical
best, the basis the user chose) — plus a per-corner consistency band, then
coaches the gap between the driver's typical execution and their own best:

    "Turn 1: brake ~15 m later (you brake at 110 m, best 125 m); carry +6 km/h
     apex; get on throttle ~12 m earlier. Braking is inconsistent (±18 m)."

"Best" per metric uses the racing-correct direction:
  * apex speed  — higher is better (carry more speed)
  * braking pt  — later (higher road_distance) is more committed
  * throttle-on — earlier (lower road_distance) is better

Pure: no Qt, no DB. The caller extracts per-lap metrics (Phase 1) from the batch
telemetry reader (Phase 0) and passes them in with the clean-lap indices.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from strategy.lap_corner_extraction import CornerReferencePoints


# Gap thresholds below which a difference isn't worth coaching.
BRAKING_GAP_M = 6.0
APEX_SPEED_GAP_KMH = 2.0
THROTTLE_GAP_M = 6.0
# Spread above which a corner is flagged inconsistent.
BRAKING_SPREAD_M = 12.0
APEX_SPREAD_KMH = 4.0


@dataclass(frozen=True)
class IdealCorner:
    turn_number: Optional[int]
    corner_name: str
    clean_laps: int
    target_braking_m: Optional[float]
    target_min_speed_kmh: float
    target_throttle_on_m: Optional[float]
    entry_gear: int
    exit_gear: int
    braking_spread_m: float
    apex_spread_kmh: float

    def reference_line(self) -> str:
        loc = self.corner_name or (f"Turn {self.turn_number}" if self.turn_number else "corner")
        parts = [loc + ":"]
        if self.target_braking_m is not None:
            parts.append(f"brake ~{self.target_braking_m:.0f} m")
        parts.append(f"{self.entry_gear}→{self.exit_gear} gear")
        parts.append(f"apex {self.target_min_speed_kmh:.0f} km/h")
        if self.target_throttle_on_m is not None:
            parts.append(f"throttle ~{self.target_throttle_on_m:.0f} m")
        return " · ".join(parts)


@dataclass(frozen=True)
class CornerCoaching:
    turn_number: Optional[int]
    corner_name: str
    advice: Tuple[str, ...]
    braking_delta_m: Optional[float]     # ideal - typical (positive = brake later)
    apex_speed_delta_kmh: Optional[float]  # ideal - typical (positive = carry more)
    throttle_delta_m: Optional[float]    # typical - ideal (positive = get on earlier)
    consistent: bool


@dataclass(frozen=True)
class PerfectLapReport:
    clean_laps: int
    ideal_corners: Tuple[IdealCorner, ...]
    coaching: Tuple[CornerCoaching, ...]
    session_consistency: str

    @property
    def ideal_lap_lines(self) -> List[str]:
        return [c.reference_line() for c in self.ideal_corners]


def _corner_key(m: CornerReferencePoints) -> Tuple[Optional[int], str]:
    return (m.turn_number, m.corner_name)


def _median(vals: Sequence[float]) -> Optional[float]:
    vals = [v for v in vals if v is not None]
    return round(statistics.median(vals), 1) if vals else None


def _spread(vals: Sequence[float]) -> float:
    vals = [v for v in vals if v is not None]
    return round(max(vals) - min(vals), 1) if len(vals) >= 2 else 0.0


def _group_by_corner(
    per_lap_metrics: Sequence[Sequence[CornerReferencePoints]],
    clean_lap_indices: Optional[Sequence[int]] = None,
) -> Tuple[List[Tuple[Optional[int], str]], Dict[Tuple[Optional[int], str], List[CornerReferencePoints]]]:
    clean = set(clean_lap_indices) if clean_lap_indices is not None else None
    order: List[Tuple[Optional[int], str]] = []
    groups: Dict[Tuple[Optional[int], str], List[CornerReferencePoints]] = {}
    for lap_i, lap in enumerate(per_lap_metrics):
        if clean is not None and lap_i not in clean:
            continue
        for m in lap:
            k = _corner_key(m)
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].append(m)
    return order, groups


def build_ideal_lap(
    per_lap_metrics: Sequence[Sequence[CornerReferencePoints]],
    clean_lap_indices: Optional[Sequence[int]] = None,
) -> List[IdealCorner]:
    """Best-executed value per corner across clean laps (theoretical best)."""
    order, groups = _group_by_corner(per_lap_metrics, clean_lap_indices)
    ideals: List[IdealCorner] = []
    for k in order:
        ms = groups[k]
        apex_speeds = [m.min_speed_kmh for m in ms if m.min_speed_kmh]
        brakings = [m.braking_point_m for m in ms if m.braking_point_m is not None]
        throttles = [m.throttle_on_m for m in ms if m.throttle_on_m is not None]
        # Coherent gears: from the lap with the highest apex speed.
        best_m = max(ms, key=lambda m: m.min_speed_kmh) if ms else None
        ideals.append(IdealCorner(
            turn_number=k[0],
            corner_name=k[1],
            clean_laps=len(ms),
            target_braking_m=(max(brakings) if brakings else None),   # brake latest
            target_min_speed_kmh=(max(apex_speeds) if apex_speeds else 0.0),  # carry most
            target_throttle_on_m=(min(throttles) if throttles else None),  # earliest power
            entry_gear=best_m.entry_gear if best_m else 0,
            exit_gear=best_m.exit_gear if best_m else 0,
            braking_spread_m=_spread(brakings),
            apex_spread_kmh=_spread(apex_speeds),
        ))
    return ideals


def coach_against_ideal(
    per_lap_metrics: Sequence[Sequence[CornerReferencePoints]],
    ideal_corners: Sequence[IdealCorner],
    clean_lap_indices: Optional[Sequence[int]] = None,
) -> List[CornerCoaching]:
    """Coach the gap between the driver's TYPICAL (median) execution and their
    own best (ideal), per corner."""
    _order, groups = _group_by_corner(per_lap_metrics, clean_lap_indices)
    ideal_by_key = {(_c.turn_number, _c.corner_name): _c for _c in ideal_corners}
    out: List[CornerCoaching] = []
    for key, ideal in ideal_by_key.items():
        ms = groups.get(key, [])
        if not ms:
            continue
        med_brake = _median([m.braking_point_m for m in ms])
        med_apex = _median([m.min_speed_kmh for m in ms])
        med_throttle = _median([m.throttle_on_m for m in ms])
        loc = ideal.corner_name or (f"Turn {ideal.turn_number}"
                                    if ideal.turn_number else "corner")

        advice: List[str] = []
        brake_delta = apex_delta = throttle_delta = None

        if ideal.target_braking_m is not None and med_brake is not None:
            brake_delta = round(ideal.target_braking_m - med_brake, 1)
            if brake_delta >= BRAKING_GAP_M:
                advice.append(
                    f"brake ~{brake_delta:.0f} m later (you brake at "
                    f"{med_brake:.0f} m, best {ideal.target_braking_m:.0f} m)")

        if ideal.target_min_speed_kmh and med_apex is not None:
            apex_delta = round(ideal.target_min_speed_kmh - med_apex, 1)
            if apex_delta >= APEX_SPEED_GAP_KMH:
                advice.append(
                    f"carry +{apex_delta:.0f} km/h apex (you're {med_apex:.0f}, "
                    f"best {ideal.target_min_speed_kmh:.0f})")

        if ideal.target_throttle_on_m is not None and med_throttle is not None:
            throttle_delta = round(med_throttle - ideal.target_throttle_on_m, 1)
            if throttle_delta >= THROTTLE_GAP_M:
                advice.append(
                    f"get on throttle ~{throttle_delta:.0f} m earlier "
                    f"(you wait to {med_throttle:.0f} m, best "
                    f"{ideal.target_throttle_on_m:.0f} m)")

        consistent = (ideal.braking_spread_m <= BRAKING_SPREAD_M
                      and ideal.apex_spread_kmh <= APEX_SPREAD_KMH)
        if not consistent:
            bits = []
            if ideal.braking_spread_m > BRAKING_SPREAD_M:
                bits.append(f"braking ±{ideal.braking_spread_m:.0f} m")
            if ideal.apex_spread_kmh > APEX_SPREAD_KMH:
                bits.append(f"apex ±{ideal.apex_spread_kmh:.0f} km/h")
            advice.append("inconsistent here (" + ", ".join(bits) + ")")

        if not advice:
            advice.append("consistent and near your best — hold it.")

        out.append(CornerCoaching(
            turn_number=ideal.turn_number, corner_name=ideal.corner_name,
            advice=tuple(f"{loc}: {a}" for a in advice),
            braking_delta_m=brake_delta, apex_speed_delta_kmh=apex_delta,
            throttle_delta_m=throttle_delta, consistent=consistent))
    return out


def perfect_lap_report(
    per_lap_metrics: Sequence[Sequence[CornerReferencePoints]],
    clean_lap_indices: Optional[Sequence[int]] = None,
) -> PerfectLapReport:
    ideal = build_ideal_lap(per_lap_metrics, clean_lap_indices)
    coaching = coach_against_ideal(per_lap_metrics, ideal, clean_lap_indices)
    n_clean = (len(set(clean_lap_indices)) if clean_lap_indices is not None
               else len(per_lap_metrics))
    inconsistent = [c for c in coaching if not c.consistent]
    if not coaching:
        summary = "Not enough clean-lap corner data yet to coach a perfect lap."
    elif not inconsistent:
        summary = (f"Consistent across {n_clean} clean laps — chase the "
                   f"corner-by-corner targets to find time.")
    else:
        names = ", ".join(
            c.corner_name or f"T{c.turn_number}" for c in inconsistent[:3])
        summary = (f"{len(inconsistent)} corner(s) inconsistent ({names}) — "
                   "nail repeatability there first.")
    return PerfectLapReport(
        clean_laps=n_clean, ideal_corners=tuple(ideal),
        coaching=tuple(coaching), session_consistency=summary)
