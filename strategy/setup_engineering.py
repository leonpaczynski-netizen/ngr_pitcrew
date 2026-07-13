"""Engineering-reasoning layer for setup authoring (pure, Qt-free).

The audit (docs/AUDIT_setup_brain_engineer_evolution.md) found the Setup Brain
authored like a validator: the car was a name + ranges, the track collapsed into a
single aero knob, and every field was decided in isolation. This module makes the
authoring reason like a race engineer — from a VEHICLE MODEL, the RICH track
characteristics, the setup OBJECTIVE and the DRIVER — and it reasons in COUPLED
SYSTEMS (changing the rear prompts a look at rear toe / support).

It produces *directional intents* (field, direction, bounded magnitude, reason,
evidence, coupled fields), not fabricated precision. Those intents become a small
bias dict + a final-drive lean that flow through the SAME neutral-seed → clamp →
validate pipeline the baseline already uses — so nothing here authors a value the
range/legality validators would not, calls no AI, or auto-applies.

Design principles (a real engineer's first principles, direction-first):
  * Rear-engined (RR) cars are entry-understeer / power-oversteer prone and
    front-limited on the brakes -> author front bite + rear stability + brake bias
    forward.
  * Straight-heavy circuits want longer gearing (top speed) and less drag; corner-
    dense circuits want shorter gearing, more mechanical grip (softer ARB) and
    rotation.
  * Elevation change wants ride-height margin over compressions.
  * Qualifying maximises one-lap grip and ignores tyre wear; Race protects the
    tyre (especially the RR rear), stability and consistency over a stint.
  * Every intent lists what it COUPLES with, and a coupling pass emits the cascade
    a real engineer would follow (rear traction -> rear toe-in for stability).

Magnitudes are deliberately conservative single "engineering steps"; the existing
per-car range clamp bounds everything.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Optional


# ---------------------------------------------------------------------------
# Vehicle model — dynamics tendencies inferred from the specs that already exist
# ---------------------------------------------------------------------------
# Balance tendencies (what the car does before we tune it).
BAL_ENTRY_US_POWER_OS = "entry_understeer_power_oversteer"   # rear-engined (RR)
BAL_NEUTRAL_SHARP     = "neutral_sharp"                       # mid-engined (MR)
BAL_ENTRY_US          = "entry_understeer"                    # front-engined RWD (FR)
BAL_STRONG_US         = "strong_understeer"                   # front-drive (FF)
BAL_TRACTION_LIMITED  = "awd_traction_strong"                 # AWD

_ENGINE_LOCATION = {"rr": "rear", "mr": "mid", "fr": "front", "ff": "front",
                    "awd": "front", "4wd": "front"}
_BALANCE_BY_DRIVETRAIN = {
    "rr": BAL_ENTRY_US_POWER_OS, "mr": BAL_NEUTRAL_SHARP,
    "fr": BAL_ENTRY_US, "ff": BAL_STRONG_US, "awd": BAL_TRACTION_LIMITED,
}


@dataclass(frozen=True)
class VehicleModel:
    car: str
    drivetrain: str            # fr/ff/mr/rr/awd (lowercased)
    engine_location: str       # front/mid/rear
    weight_kg: Optional[float]
    power_hp: Optional[float]
    power_to_weight: Optional[float]   # hp per tonne
    category: str
    num_gears: int
    balance_tendency: str
    high_power_to_weight: bool
    rear_traction_priority: bool       # RR/MR/AWD put weight/drive over the rear

    def summary(self) -> str:
        pw = f"{self.power_to_weight:.0f} hp/t" if self.power_to_weight else "power/weight unknown"
        return (f"{self.category or 'car'}, {self.engine_location}-engined "
                f"{self.drivetrain.upper()}, {pw} — {self.balance_tendency.replace('_', ' ')}")


def build_vehicle_model(car: str, drivetrain: str, num_gears: int,
                        car_specs: Optional[dict] = None) -> VehicleModel:
    """Build a lightweight dynamics model from the specs that already exist.

    ``car_specs`` is the per-car dict from data/car_specs.json (power_hp, weight_kg,
    category, …). Missing specs degrade honestly to None — nothing is invented."""
    dt = (drivetrain or "").strip().lower()
    if dt in ("4wd", "4x4"):
        dt = "awd"
    specs = car_specs or {}
    weight = _num(specs.get("weight_kg"))
    power = _num(specs.get("power_hp"))
    ptw = round(power / (weight / 1000.0), 1) if (power and weight and weight > 0) else None
    balance = _BALANCE_BY_DRIVETRAIN.get(dt, BAL_NEUTRAL_SHARP if dt else BAL_ENTRY_US)
    return VehicleModel(
        car=car, drivetrain=dt or "",
        engine_location=_ENGINE_LOCATION.get(dt, "front"),
        weight_kg=weight, power_hp=power, power_to_weight=ptw,
        category=str(specs.get("category") or ""),
        num_gears=int(num_gears or 0),
        balance_tendency=balance,
        high_power_to_weight=bool(ptw and ptw >= 320.0),   # Gr.3 ~ 410; a road car ~ 150
        rear_traction_priority=dt in ("rr", "mr", "awd"),
    )


def _num(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f and f not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


# Thin read-only spec resolver (fallback when the caller does not pass car_specs).
# Cached so repeated authoring does not re-read the file. Never raises.
_CAR_SPECS_CACHE: "dict | None" = None


def resolve_car_specs(car: str) -> dict:
    """Return the per-car spec dict from data/car_specs.json, or {} if unavailable.

    Read-only, cached, never raises. Used only as a fallback so the vehicle model
    still works when a caller has not already resolved specs."""
    global _CAR_SPECS_CACHE
    if not car:
        return {}
    if _CAR_SPECS_CACHE is None:
        try:
            import json
            from pathlib import Path
            _p = Path(__file__).resolve().parent.parent / "data" / "car_specs.json"
            _CAR_SPECS_CACHE = json.loads(_p.read_text(encoding="utf-8"))
        except Exception:
            _CAR_SPECS_CACHE = {}
    entry = _CAR_SPECS_CACHE.get(car)
    return dict(entry) if isinstance(entry, dict) else {}


# ---------------------------------------------------------------------------
# Engineering intents
# ---------------------------------------------------------------------------
# One conservative "engineering step" per field (the clamp bounds the total).
_FIELD_STEP: dict[str, float] = {
    "arb_front": 1.0, "arb_rear": 1.0,
    "toe_rear": 0.05, "toe_front": 0.03,
    "ride_height_front": 3.0, "ride_height_rear": 3.0,
    "springs_front": 0.3, "springs_rear": 0.3,
    "brake_bias": 1.0,
    "aero_front": 25.0, "aero_rear": 25.0,
    "lsd_accel": 2.0, "lsd_decel": 2.0,
}
# Final drive is handled separately (not a per-car range field): a lean toward
# longer (numerically lower) or shorter (higher) gearing, in ratio units.
_FINAL_DRIVE_STEP = 0.12


@dataclass(frozen=True)
class EngineeringIntent:
    field: str
    direction: int             # -1 / +1
    strength: float            # multiplier on the field step (0.5 / 1.0 / 1.5)
    reason: str                # why an engineer makes this call
    evidence: str              # what it is grounded in (vehicle/track/objective/driver)
    couples_with: tuple = ()   # fields the engineer reviews alongside this one

    @property
    def delta(self) -> float:
        return self.direction * self.strength * _FIELD_STEP.get(self.field, 0.0)

    def as_json(self) -> dict:
        return {"field": self.field, "direction": self.direction,
                "strength": self.strength, "delta": round(self.delta, 3),
                "reason": self.reason, "evidence": self.evidence,
                "couples_with": list(self.couples_with)}


@dataclass(frozen=True)
class EngineeringPlan:
    vehicle: VehicleModel
    objective: str
    intents: list                    # list[EngineeringIntent]
    final_drive_lean: float          # ratio units: <0 longer (top speed), >0 shorter (accel)
    final_drive_reason: str
    notes: list = _dc_field(default_factory=list)

    def bias(self) -> dict:
        """field -> summed delta, ready to merge into build_baseline_setup's bias dict."""
        out: dict = {}
        for i in self.intents:
            out[i.field] = out.get(i.field, 0.0) + i.delta
        return out

    def as_json(self) -> dict:
        return {
            "vehicle": self.vehicle.summary(),
            "objective": self.objective,
            "intents": [i.as_json() for i in self.intents],
            "final_drive_lean": round(self.final_drive_lean, 3),
            "final_drive_reason": self.final_drive_reason,
            "notes": list(self.notes),
        }


# Objective constants mirror strategy.setup_authoring.SetupObjective values.
OBJ_BASE, OBJ_QUALI, OBJ_RACE = "base", "qualifying", "race"

# Track shaping thresholds (mirror track_tune_profile's).
_STRAIGHT_HEAVY = 0.22
_CORNER_DENSE = 6.0
_ELEVATION_SIGNIFICANT_M = 30.0


def derive_engineering_intents(
    vehicle: VehicleModel,
    track,                       # TrackTuneProfile (duck-typed) or None
    objective: str,
    driver=None,                 # DriverProfile (duck-typed) or None
) -> EngineeringPlan:
    """Reason like a race engineer over vehicle + track + objective + driver.

    Returns an EngineeringPlan of directional, coupled, bounded intents plus a
    final-drive lean. Direction-first: magnitudes are conservative single steps.
    """
    intents: list[EngineeringIntent] = []
    notes: list[str] = []
    obj = (objective or OBJ_BASE).strip().lower()

    trustworthy = bool(getattr(track, "trustworthy", False)) if track else False
    straight_fraction = getattr(track, "straight_fraction", None) if track else None
    corner_density = getattr(track, "corner_density_per_km", None) if track else None
    elevation = getattr(track, "elevation_change_m", None) if track else None

    # ---- VEHICLE: build the car to its nature -----------------------------
    if vehicle.balance_tendency == BAL_ENTRY_US_POWER_OS:
        # Rear-engined (Porsche): free the front on entry, plant the rear on power,
        # brake bias forward because the fronts do the stopping work.
        intents.append(EngineeringIntent(
            "arb_front", -1, 1.0,
            "rear-engined car understeers on entry — soften the front bar to free turn-in",
            "vehicle:rear_engine", ("aero_front", "toe_front")))
        intents.append(EngineeringIntent(
            "toe_rear", +1, 1.0,
            "rear weight bias makes the rear step out under power — add rear toe-in for "
            "straight-line and corner-exit stability",
            "vehicle:rear_engine", ("lsd_accel", "arb_rear", "aero_rear")))
        intents.append(EngineeringIntent(
            "brake_bias", -1, 1.0,
            "weight over the rear axle means the fronts are the braking limit — move bias "
            "forward for stable, repeatable braking",
            "vehicle:rear_engine", ()))
    elif vehicle.balance_tendency == BAL_STRONG_US:
        intents.append(EngineeringIntent(
            "arb_rear", +1, 1.0,
            "front-drive car understeers — stiffen the rear bar to rotate it",
            "vehicle:front_drive", ("aero_front",)))
    elif vehicle.balance_tendency == BAL_ENTRY_US:
        intents.append(EngineeringIntent(
            "arb_front", -1, 0.5,
            "front-engined RWD tends to push on entry — a touch softer front bar frees it",
            "vehicle:front_engine", ("aero_front",)))

    if vehicle.rear_traction_priority and vehicle.high_power_to_weight:
        intents.append(EngineeringIntent(
            "aero_rear", +1, 0.5,
            "high power over the driven rear axle — a little more rear downforce steadies "
            "traction out of medium/fast corners",
            "vehicle:high_power_rear_drive", ("toe_rear", "lsd_accel")))

    # ---- TRACK: gear and support to the circuit ---------------------------
    if trustworthy:
        if straight_fraction is not None and straight_fraction >= _STRAIGHT_HEAVY:
            fd_lean = -1.0   # longer gearing for top speed
            fd_reason = (f"longest straight is {straight_fraction * 100:.0f}% of the lap — "
                         "gear longer so the car is not on the limiter before the braking zone")
            intents.append(EngineeringIntent(
                "arb_rear", +1, 0.5,
                "fast, straight-heavy circuit — a slightly stiffer rear steadies the car at "
                "high speed through quick direction changes",
                "track:straight_heavy", ("aero_rear",)))
        elif corner_density is not None and corner_density >= _CORNER_DENSE:
            fd_lean = +1.0   # shorter gearing for acceleration out of slow corners
            fd_reason = (f"corner-dense ({corner_density:.1f}/km) — gear shorter for stronger "
                         "acceleration out of the many slow corners")
            intents.append(EngineeringIntent(
                "arb_front", -1, 0.5,
                "twisty circuit rewards mechanical grip and rotation — softer front bar",
                "track:corner_dense", ("springs_front",)))
            intents.append(EngineeringIntent(
                "springs_front", -1, 0.5,
                "low-speed mechanical grip matters more than high-speed platform here — "
                "soften the front spring a touch",
                "track:corner_dense", ("ride_height_front",)))
        else:
            fd_lean, fd_reason = 0.0, "balanced circuit — neutral gearing"

        if elevation is not None and elevation >= _ELEVATION_SIGNIFICANT_M:
            intents.append(EngineeringIntent(
                "ride_height_front", +1, 0.5,
                f"{elevation:.0f} m of elevation change — carry a little ride-height margin so "
                "the car does not bottom through compressions",
                "track:elevation", ("springs_front", "ride_height_rear")))
            intents.append(EngineeringIntent(
                "ride_height_rear", +1, 0.5,
                "match the rear ride-height margin to keep rake stable over the elevation",
                "track:elevation", ("ride_height_front",)))
    else:
        fd_lean, fd_reason = 0.0, "no trustworthy track model — neutral gearing (nothing invented)"
        notes.append("No trustworthy track model — track-specific gearing/support stays "
                     "conservative; only vehicle and objective reasoning applied.")

    # ---- OBJECTIVE: what are we optimising? -------------------------------
    if obj == OBJ_QUALI:
        # One flying lap on fresh tyres: peak grip and response, tyre life irrelevant.
        intents.append(EngineeringIntent(
            "arb_front", +1, 0.5,
            "qualifying wants immediate response — a firmer front sharpens turn-in for one lap",
            "objective:qualifying", ("aero_front",)))
        notes.append("Qualifying: peak one-lap grip and response; tyre-life and fuel ignored.")
    elif obj == OBJ_RACE:
        # Total race time: protect the tyre (RR rear especially), stability, consistency.
        if vehicle.balance_tendency == BAL_ENTRY_US_POWER_OS:
            intents.append(EngineeringIntent(
                "aero_rear", +1, 0.5,
                "race pace over a stint — a little more rear downforce protects the rear tyre "
                "and keeps the RR predictable as it wears",
                "objective:race+rear_engine", ("toe_rear",)))
        intents.append(EngineeringIntent(
            "arb_rear", -1, 0.5,
            "consistency over the stint — a slightly softer rear keeps mechanical grip and "
            "protects the tyre as the fuel load drops",
            "objective:race", ("aero_rear",)))
        notes.append("Race: minimise total race time — traction, tyre protection and "
                     "consistency over one-lap peak.")
    else:
        notes.append("Base: balanced platform to learn from; deliberately leaves headroom.")

    # DRIVER fit is handled by the dedicated evidence-scaled layer (strategy/driver_fit)
    # so the driver's preferences move each field in proportion to how far the current
    # value sits from their window — not a fixed nudge. It is composed alongside this
    # plan by the caller, keeping vehicle/track/objective reasoning separate and clean.

    return EngineeringPlan(
        vehicle=vehicle, objective=obj, intents=intents,
        final_drive_lean=fd_lean * _FINAL_DRIVE_STEP, final_drive_reason=fd_reason,
        notes=notes,
    )


def coupling_report(plan: EngineeringPlan) -> list:
    """Human-readable systems-coupling notes: for each authored lever, the related
    fields an engineer reviews alongside it. This is the 'reason in systems' surface."""
    out: list = []
    seen: set = set()
    for i in plan.intents:
        if not i.couples_with:
            continue
        key = (i.field, i.couples_with)
        if key in seen:
            continue
        seen.add(key)
        move = "raise" if i.direction > 0 else "lower"
        out.append(
            f"{move} {i.field.replace('_', ' ')} -> also review "
            + ", ".join(c.replace('_', ' ') for c in i.couples_with)
        )
    return out
