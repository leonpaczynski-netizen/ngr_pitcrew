"""Phase 8 — setup ↔ race-time (aero/fuel) reasoning (pure, Qt-free).

Makes the setup brain aware that on a fuel-sensitive, drag-sensitive circuit the
aero/gearing choice affects total race time — WITHOUT fabricating a saving. When
the evidence points that way it recommends a controlled A/B comparison run and
surfaces the deterministic refuel-time arithmetic; it never invents a lap-time or
fuel-per-lap delta it cannot measure.

Reads only scalar evidence (fuel multiplier, refuel rate, a Phase-5 TrackTuneProfile,
the front-aero position) — a read-only bridge, no strategy-command capability. It
authors NO setup values and applies nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# A fuel multiplier at/above this makes fuel load a material total-race-time factor.
FUEL_SENSITIVE_MULTIPLIER = 2.0
# Front aero at/above this fraction of its range is "high" (drag worth questioning).
_AERO_HIGH_FRACTION = 0.70


@dataclass(frozen=True)
class AeroFuelAssessment:
    """Honest aero/fuel-vs-race-time assessment. When ``recommend_comparison_run``
    is True the driver should run the A/B test in ``comparison_run`` rather than be
    given a fabricated saving."""
    fuel_relevant_to_setup: bool
    recommend_comparison_run: bool
    reason: str
    comparison_run: str
    refuel_note: str

    def as_note(self) -> str:
        if not self.fuel_relevant_to_setup:
            return ""
        parts = [f"Fuel & race-time: {self.reason}."]
        if self.comparison_run:
            parts.append(self.comparison_run)
        if self.refuel_note:
            parts.append(self.refuel_note)
        return " ".join(parts)


def refuel_time_seconds(additional_fuel_l: float, refuel_rate_lps: float) -> Optional[float]:
    """Deterministic pit-time cost of ``additional_fuel_l`` at ``refuel_rate_lps``.

    additional_refuel_time_s = additional_fuel_l / rate (so 1 L = 1 s at 1 L/s).
    Returns None when the rate is unknown/non-positive (never invents a value)."""
    try:
        rate = float(refuel_rate_lps)
        if rate <= 0:
            return None
        return round(abs(float(additional_fuel_l)) / rate, 1)
    except (TypeError, ValueError):
        return None


def _aero_front_high(value, lo, hi) -> bool:
    try:
        v, lo, hi = float(value), float(lo), float(hi)
    except (TypeError, ValueError):
        return False
    if hi <= lo:
        return False
    return v >= lo + _AERO_HIGH_FRACTION * (hi - lo)


def assess_aero_fuel_tradeoff(
    *,
    fuel_multiplier: float = 1.0,
    refuel_rate_lps: float = 0.0,
    track_profile=None,
    aero_front_value=None,
    aero_front_lo=None,
    aero_front_hi=None,
    fuel_use_high: bool = False,
) -> AeroFuelAssessment:
    """Assess whether aero drag is materially affecting fuel / total race time.

    Positive only when ALL hold: the driver flagged high fuel use, the event runs a
    high fuel multiplier, the circuit is drag-sensitive (a straight-heavy track —
    Phase-5 aero_bias 'trim'), and the front aero is high. In that case recommend an
    A/B comparison run (never a fabricated saving) + expose the refuel arithmetic.
    """
    try:
        fmult = float(fuel_multiplier or 1.0)
    except (TypeError, ValueError):
        fmult = 1.0
    drag_sensitive = (getattr(track_profile, "aero_bias", "neutral") == "trim"
                      and bool(getattr(track_profile, "trustworthy", False)))
    high_fuel = fmult >= FUEL_SENSITIVE_MULTIPLIER
    aero_high = _aero_front_high(aero_front_value, aero_front_lo, aero_front_hi)

    if fuel_use_high and high_fuel and drag_sensitive and aero_high:
        sf = getattr(track_profile, "straight_fraction", None)
        straight_txt = (f"a long straight ({sf * 100:.0f}% of the lap)"
                        if isinstance(sf, (int, float)) else "a long straight")
        reason = (f"fuel ×{fmult:g} on {straight_txt} with high front aero — drag "
                  "raises fuel-per-lap and top-speed loss, so it affects total race time")
        comparison = ("Comparison run — Run A: current aero. Run B: front aero −25. "
                      "Compare lap time, fuel per lap, top speed and projected total "
                      "race time before committing.")
        rate = 0.0
        try:
            rate = float(refuel_rate_lps or 0.0)
        except (TypeError, ValueError):
            rate = 0.0
        if rate > 0:
            per_l = refuel_time_seconds(1.0, rate)
            refuel = (f"At {rate:g} L/s, every extra litre burned adds ~{per_l:g}s of "
                      "refuelling (1 L = 1 s at 1 L/s) on top of the lap-time cost.")
        else:
            refuel = ""
        return AeroFuelAssessment(True, True, reason, comparison, refuel)

    return AeroFuelAssessment(False, False, "", "", "")
