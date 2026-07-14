"""Discipline intelligence (pure, Qt-free) — Engineering-Brain Phase 4.

Makes the Base / Qualifying / Race objectives first-class and independent, per the
plan's Layer 6: each discipline is a different engineering PRODUCT, not one setup with a
label. This module adds the discipline decisions that are not just field biases:

  * **Soft-tyre qualifying enforcement** — qualifying runs the softest legal compound
    (peak one-lap grip; tyre life is irrelevant over one lap).
  * **Objective RPM / shift targets** — qualifying uses the full power band and short
    gearing over one lap; race leaves headroom and short-shifts to protect traction and
    fuel.
  * **Objective scoring priorities** — the readable factor weighting each discipline
    optimises (feeds the Phase-3 synthesis scorer and the driver-facing brief).

It authors no setup values and calls no AI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Dry-compound softness (lower = softer = faster over one lap). Racing < Sports <
# Comfort in outright grip; within a family, Soft < Medium < Hard.
_SOFTNESS: dict = {
    "RSS": 0, "RS": 1, "RM": 2, "RH": 3,
    "SS": 4, "SM": 5, "SH": 6,
    "CS": 7, "CM": 8, "CH": 9,
}
_WET = {"RI", "RW", "IM", "W", "INT", "WET"}

_COMPOUND_NAME = {
    "RSS": "Racing Super Soft", "RS": "Racing Soft", "RM": "Racing Medium",
    "RH": "Racing Hard", "SS": "Sports Soft", "SM": "Sports Medium", "SH": "Sports Hard",
    "CS": "Comfort Soft", "CM": "Comfort Medium", "CH": "Comfort Hard",
}


def _norm_compound(c) -> str:
    return str(c or "").strip().upper()


def softest_dry_compound(available: list) -> Optional[str]:
    """The softest (fastest over one lap) dry compound in ``available``, or None."""
    dry = [c for c in ({_norm_compound(x) for x in (available or [])})
           if c in _SOFTNESS]
    if not dry:
        return None
    return min(dry, key=lambda c: _SOFTNESS[c])


@dataclass(frozen=True)
class TyrePlan:
    compound: str
    name: str
    reason: str


def qualifying_tyre_plan(available: list, required: list = None) -> TyrePlan:
    """Choose the qualifying compound: the softest legal dry option. Qualifying has no
    stint to protect, so tyre life never outranks one-lap grip. If a required-compound
    rule constrains the choice, pick the softest that satisfies it."""
    avail = [_norm_compound(x) for x in (available or [])]
    req = [_norm_compound(x) for x in (required or [])]
    # If required compounds are specified AND present, choose the softest required one;
    # else the softest available dry compound.
    pool = [c for c in avail if c in req] if req else avail
    softest = softest_dry_compound(pool) or softest_dry_compound(avail)
    if not softest:
        return TyrePlan("", "", "no dry compound available — cannot enforce soft qualifying tyre")
    return TyrePlan(
        softest, _COMPOUND_NAME.get(softest, softest),
        f"softest legal compound ({_COMPOUND_NAME.get(softest, softest)}) — qualifying is "
        "one flying lap, so peak grip beats tyre life")


@dataclass(frozen=True)
class RpmShiftTarget:
    objective: str
    shift_style: str            # "rev_out" / "short_shift" / "balanced"
    note: str


def objective_rpm_target(objective: str) -> RpmShiftTarget:
    obj = str(objective or "base").lower()
    if obj == "qualifying":
        return RpmShiftTarget(
            obj, "rev_out",
            "Qualifying: gear to use the full power band over one lap — rev each gear out "
            "toward the limiter before the braking zone; short enough gearing that the car "
            "is pulling hard everywhere, not bogged.")
    if obj == "race":
        return RpmShiftTarget(
            obj, "short_shift",
            "Race: leave a little RPM headroom and short-shift out of slow corners to reduce "
            "wheelspin and fuel burn; longer gearing lowers RPM and stress over the stint.")
    return RpmShiftTarget(
        obj, "balanced",
        "Base: balanced gearing that reaches the power band without bogging — a neutral "
        "platform to learn the car's RPM behaviour.")


# The readable factors each discipline optimises (plan Layer 6). Weight > 1 = emphasise,
# < 1 = de-emphasise. Consumed by the Phase-3 scorer's objective weighting + the brief.
_OBJECTIVE_PRIORITIES: dict = {
    "qualifying": {
        "one_lap_pace": 1.5, "rotation": 1.4, "peak_grip": 1.4, "braking_performance": 1.3,
        "acceleration": 1.2, "driver_confidence_at_max_attack": 1.1,
        "tyre_life": 0.2, "fuel_efficiency": 0.2, "stint_stability": 0.3,
    },
    "race": {
        "average_stint_pace": 1.4, "lap_time_variance": 1.4, "tyre_degradation": 1.4,
        "wheelspin_loss": 1.2, "fuel_efficiency": 1.2, "refuel_time": 1.0,
        "braking_stability": 1.2, "balance_on_worn_tyres": 1.2, "mistake_probability": 1.1,
        "peak_grip": 0.7,
    },
    "base": {
        "balanced_behaviour": 1.2, "diagnostic_usefulness": 1.2, "driver_confidence": 1.1,
        "representative_tyre_behaviour": 1.0, "track_suitability": 1.0,
        "capacity_for_refinement": 1.1,
    },
}


def objective_priorities(objective: str) -> dict:
    return dict(_OBJECTIVE_PRIORITIES.get(str(objective or "base").lower(),
                                          _OBJECTIVE_PRIORITIES["base"]))


def discipline_objective_summary(
    objective: str, *, available_tyres: list = None, required_tyres: list = None,
) -> dict:
    """One readable summary of what THIS discipline is engineering for — the tyre choice,
    the RPM/shift intent, and the scoring priorities."""
    obj = str(objective or "base").lower()
    out: dict = {
        "objective": obj,
        "rpm": {"shift_style": objective_rpm_target(obj).shift_style,
                "note": objective_rpm_target(obj).note},
        "priorities": objective_priorities(obj),
    }
    if obj == "qualifying":
        tp = qualifying_tyre_plan(available_tyres, required_tyres)
        out["tyre"] = {"compound": tp.compound, "name": tp.name, "reason": tp.reason,
                       "enforced": bool(tp.compound)}
    return out
