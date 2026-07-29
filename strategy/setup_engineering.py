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


def effective_car_specs(car: str, setup: Optional[dict] = None) -> dict:
    """Per-car specs to reason with — the JSON defaults, OVERRIDDEN by any regulated
    weight/power the driver entered on the setup.

    Weight and power default from ``data/car_specs.json``, but a series can mandate a
    specific minimum weight or maximum power (e.g. Supercars: 1335 kg / 606 bhp) that the
    stock figures don't reflect — a car lightened with parts and ballasted back up to a
    minimum can't be derived from stock weight + ballast. So a ``weight_kg`` / ``power_hp``
    set on the setup (>0) wins; otherwise the JSON default stands. Pure; never raises."""
    specs = dict(resolve_car_specs(car) or {})
    s = setup or {}
    w = _num(s.get("weight_kg"))
    if w is not None and w > 0:
        specs["weight_kg"] = w
    p = _num(s.get("power_hp"))
    if p is not None and p > 0:
        specs["power_hp"] = p
    return specs


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


# ---------------------------------------------------------------------------
# Chassis seeds (dampers / camber / toe) — car- and objective-specific starting
# values for the fields the DIRECTIONAL-intent layer above does not shape. Without
# this they come out at a single flat neutral constant for EVERY car — identical
# compression/expansion and toe on a light GT3 and a heavy road car, and identical
# between race and qualifying — which is exactly what a driver notices as "weird".
# Derived ONLY from mass + drivetrain + objective (all already known); when mass is
# unknown the mass factor is neutral so nothing is invented. Everything is clamped to
# the car's real range downstream in build_baseline_setup.
_DAMPER_REF_MASS_KG = 1300.0
_DAMPER_BASE = {"dampers_front_comp": 30.0, "dampers_front_ext": 40.0,
                "dampers_rear_comp": 25.0, "dampers_rear_ext": 35.0}


def derive_chassis_seeds(vehicle: VehicleModel, objective: str) -> "dict":
    """Car/objective-specific seeds for dampers, camber and toe. Pure; never raises."""
    obj = (objective or OBJ_BASE).strip().lower()
    dt = (vehicle.drivetrain or "").lower()
    seeds: dict = {}

    # Dampers scale with sprung MASS (more mass → more damping to control it) and with
    # OBJECTIVE (qualifying firmer for response; race softer for compliance over a
    # stint). A stiff, high-downforce car (high power/weight) also runs firmer damping.
    mass = vehicle.weight_kg
    mass_f = max(0.75, min(1.30, mass / _DAMPER_REF_MASS_KG)) if mass else 1.0
    stiff_f = 1.12 if vehicle.high_power_to_weight else 1.0
    obj_damp = {OBJ_QUALI: 1.10, OBJ_RACE: 0.95}.get(obj, 1.0)
    for f, base in _DAMPER_BASE.items():
        seeds[f] = float(round(base * mass_f * stiff_f * obj_damp))

    # Camber (negative, for grip). Calibrated against reference tunes, which agree on
    # what a good baseline looks like: FRONT > REAR on EVERY car regardless of drivetrain
    # (~2.5 / 1.9), scaling UP with downforce / car class (race + high power-to-weight run
    # more camber) and DOWN a touch for a race stint vs a one-lap qualifying setup. Only a
    # small front-drive nudge (more front camber to fight understeer). Values clamp to the
    # car's range downstream, so a road car with a tight camber range never over-cambers.
    cat = (getattr(vehicle, "category", "") or "").lower()
    if cat.startswith("gr.") or getattr(vehicle, "high_power_to_weight", False):
        df = 1.10          # GT3/GT4/prototypes and high power/weight → more camber
    elif "road" in cat:
        df = 0.85          # softer road cars → less
    else:
        df = 1.0
    obj_c = {OBJ_QUALI: 0.15, OBJ_RACE: -0.2}.get(obj, 0.0)
    front_nudge = 0.2 if dt == "ff" else 0.0
    seeds["camber_front"] = round(2.4 * df + obj_c + front_nudge, 1)
    seeds["camber_rear"] = round(1.9 * df + obj_c, 1)

    # Toe: a slight front toe-OUT for turn-in, a SUBSTANTIAL rear toe-IN for stability
    # (references run ~-0.05 front / ~+0.14 rear, not the tiny values before). Rear-drive
    # carries more rear toe-in for traction; a race stint adds rear toe-in for stability,
    # a qualifying lap trims it (less scrub) and sharpens front turn-in.
    rear_dt = {"rr": 0.03, "fr": 0.02, "mr": 0.02, "awd": 0.0}.get(dt, 0.0)
    obj_ft = {OBJ_RACE: -0.02}.get(obj, 0.0)
    obj_rt = {OBJ_QUALI: -0.03, OBJ_RACE: 0.03}.get(obj, 0.0)
    seeds["toe_front"] = round(-0.05 + obj_ft, 2)
    seeds["toe_rear"] = round(0.14 + rear_dt + obj_rt, 2)

    return seeds


# Track shaping thresholds (mirror track_tune_profile's).
_STRAIGHT_HEAVY = 0.22
_CORNER_DENSE = 6.0
_ELEVATION_SIGNIFICANT_M = 30.0


# ---------------------------------------------------------------------------
# Physics-based spring natural frequency targets — Group 77 / spring-baseline
# ---------------------------------------------------------------------------
# Named band constants (all Hz).  None may come from any external tuning
# document — each traces to car-class band / physics / discipline / track.
_SPRING_BAND_ROAD  = (1.5, 3.0)   # Road cars: compliance and ride quality
_SPRING_BAND_SPORT = (2.5, 5.0)   # Sport/GT4/touring: balanced platform
_SPRING_BAND_RACE  = (4.0, 8.0)   # Gr.3/Gr.4/Prototype + high power-to-weight

# Qualifying squeezes one extra flying lap out of the platform (×10% stiffer).
_QUALI_STIFFNESS_FACTOR = 1.10

# Track-character modifiers applied to the band midpoint before the split.
# Straight-heavy → stiffer (higher Hz) for high-speed stability.
# Corner-dense   → softer  (lower Hz) for mechanical grip and rotation.
_TRACK_STRAIGHT_HZ_STEP = +0.30
_TRACK_CORNER_HZ_STEP   = -0.20

# Drivetrain-keyed front-axle weight fraction prior (0.0–1.0).
# Keys match the lowercased VehicleModel.drivetrain strings (rr/mr/fr/ff/awd).
# "4wd" maps to "awd" in build_vehicle_model; this dict uses the final key.
_WEIGHT_DIST_PRIOR: dict = {
    "rr":  0.38,   # rear-engined: weight well over the back axle
    "mr":  0.42,   # mid-engined: still rear-biased, slightly less so
    "fr":  0.48,   # front-engined RWD: near-neutral, slight front bias
    "ff":  0.60,   # front-wheel drive: engine + driven axle both at the front
    "awd": 0.50,   # all-wheel drive: by design near 50:50
}

# Total Hz span applied as a bounded delta between the front and rear axles
# based on the front-weight deviation from 50:50.  Kept modest so both axles
# stay inside the selected class band after the split clamp.
_SPLIT_HZ_SPAN = 2.0

# Ballast-aware effective weight distribution constants.
_BALLAST_POS_FULL  = 50.0   # GT7 ballast_position slider extreme (|pos| that means fully front/rear)
_BALLAST_AUTHORITY = 1.0    # scale on the position->fraction mapping; named knob, calibratable later
_BALLAST_FRAC_LO   = 0.30   # effective front-fraction safety clamp lower bound
_BALLAST_FRAC_HI   = 0.70   # effective front-fraction safety clamp upper bound


@dataclass(frozen=True)
class SpringFrequencies:
    """Physics-derived spring natural frequency target for both axles.

    Produced by ``derive_spring_frequencies``; consumed by the baseline engine
    as ``chassis_seed_overrides["springs_front/rear"]``.  Immutable.
    """
    front_hz: float
    rear_hz: float
    front_reason: str
    rear_reason: str


def derive_spring_frequencies(
    vehicle: VehicleModel,
    objective: str,
    track=None,
    front_weight_dist: Optional[float] = None,
    ballast_kg: float = 0.0,
    ballast_position: float = 0.0,
) -> SpringFrequencies:
    """Physics-based spring natural frequency target for both axles.

    Ordering of operations (important for predictability and in-band behaviour):
      1. Band selection    — car class / power-to-weight → Road / Sport / Race band.
         Insufficient data (weight, category or drivetrain missing) → FALLBACK to
         NEUTRAL_SEEDS springs immediately; no further computation.
      2. Base Hz           — band midpoint.
      3. Track adjustment  — trustworthy track only: straight-heavy circuit adds
         ``_TRACK_STRAIGHT_HZ_STEP``; corner-dense circuit adds
         ``_TRACK_CORNER_HZ_STEP``.  At most one adjustment is applied (first match).
      4. Front/rear split  — resolve the front-axle weight fraction
         (``front_weight_dist`` arg → ``data.car_weight_distribution`` file →
         ``_WEIGHT_DIST_PRIOR[drivetrain]``), then compute a bounded delta so that
         the front axle is stiffer when the car is front-heavy and the rear axle is
         stiffer when the car is rear-heavy.  Both values are clamped to the selected
         band [lo, hi] so the split cannot push either axle outside its class band.
      5. Discipline factor — qualifying objective applies ``_QUALI_STIFFNESS_FACTOR``
         (×1.10) AFTER the band clamp, so qualifying is allowed to slightly exceed
         the band ceiling (by ≤10%).  Unknown/wet objectives use factor 1.0.
      6. GT7 slider clamp  — both values clamped to [1.00, 20.00].

    Net invariants:
      * RR/MR → rear_hz >= front_hz  (rear-heavy → rear stiffer)
      * FF     → front_hz >= rear_hz  (front-heavy → front stiffer)
      * Both within [1.00, 20.00]
      * Qualifying both_hz >= race both_hz for the same car + track

    Parameters
    ----------
    vehicle:
        VehicleModel from ``build_vehicle_model()``.
    objective:
        Objective string: ``"base"`` | ``"qualifying"`` | ``"race"``.
        Unknown strings default to factor 1.0 (no crash).
    track:
        Duck-typed ``TrackTuneProfile`` or None.  Only consulted when
        ``track.trustworthy`` is True.
    front_weight_dist:
        Front-axle weight fraction in (0.0, 1.0), or None.  When None the
        per-car data file and then ``_WEIGHT_DIST_PRIOR`` are tried in order.

    Returns
    -------
    SpringFrequencies with front_hz, rear_hz and human-readable reason strings.
    Pure; never raises.
    """
    # Function-local import to avoid a module-level cycle
    # (setup_baseline imports driving_advisor function-locally which imports
    # setup_engineering function-locally; no module-level cycle exists here
    # because setup_baseline's only module-level import is setup_ranges).
    try:
        from strategy.setup_baseline import NEUTRAL_SEEDS as _NS
    except Exception:
        # Should never happen in practice; keep an inline fallback so tests that
        # import setup_engineering in isolation don't break.
        _NS = {"springs_front": 3.50, "springs_rear": 3.00}

    _neutral_front = float(_NS.get("springs_front", 3.50))
    _neutral_rear  = float(_NS.get("springs_rear",  3.00))

    obj = (objective or OBJ_BASE).strip().lower()
    w_kg = vehicle.weight_kg
    cat  = (vehicle.category or "").strip()
    dt   = (vehicle.drivetrain or "").strip().lower()

    # ── Step 1: band selection (first match wins) ────────────────────────────
    if (w_kg is None or w_kg <= 0) or cat == "" or dt == "":
        return SpringFrequencies(
            front_hz=_neutral_front,
            rear_hz=_neutral_rear,
            front_reason="insufficient data (weight/category/drivetrain missing) → neutral fallback",
            rear_reason="insufficient data (weight/category/drivetrain missing) → neutral fallback",
        )

    cat_lower = cat.lower()
    if cat_lower.startswith("gr."):
        lo, hi = _SPRING_BAND_RACE
        band_name = f"{cat} race band"
    elif vehicle.high_power_to_weight:
        lo, hi = _SPRING_BAND_RACE
        band_name = "race band (high power-to-weight ≥ 320 hp/t)"
    elif "road" in cat_lower:
        lo, hi = _SPRING_BAND_ROAD
        band_name = "road band"
    else:
        lo, hi = _SPRING_BAND_SPORT
        band_name = "sport band"

    # ── Step 2: base Hz = band midpoint ──────────────────────────────────────
    base_hz = (lo + hi) / 2.0

    # ── Step 3: track adjustment (trustworthy track only; first match) ───────
    track_note = ""
    trustworthy = bool(getattr(track, "trustworthy", False)) if track else False
    if trustworthy:
        _sf  = getattr(track, "straight_fraction",      None)
        _cd  = getattr(track, "corner_density_per_km",  None)
        if _sf is not None and _sf >= _STRAIGHT_HEAVY:
            base_hz += _TRACK_STRAIGHT_HZ_STEP
            track_note = "straight-heavy track stiffened"
        elif _cd is not None and _cd >= _CORNER_DENSE:
            base_hz += _TRACK_CORNER_HZ_STEP
            track_note = "technical track softened"

    # ── Step 4: front/rear split ─────────────────────────────────────────────
    # Resolution order: arg → car file → drivetrain prior
    if front_weight_dist is not None:
        frac = float(front_weight_dist)
        frac_label = "override"
    else:
        try:
            from data.car_weight_distribution import resolve_front_weight_dist as _rwd
            _file_frac = _rwd(vehicle.car)
        except Exception:
            _file_frac = None
        if _file_frac is not None:
            frac = float(_file_frac)
            frac_label = "car data file"
        else:
            _prior = _WEIGHT_DIST_PRIOR.get(dt)
            if _prior is None:
                # Unrecognised drivetrain, no explicit override, no car-data entry.
                # AC5: no fraction source available → neutral fallback, no guessing.
                return SpringFrequencies(
                    front_hz=_neutral_front,
                    rear_hz=_neutral_rear,
                    front_reason="unknown drivetrain, no weight-dist data → neutral fallback",
                    rear_reason="unknown drivetrain, no weight-dist data → neutral fallback",
                )
            frac = float(_prior)
            # NB: the reason string below already prepends {dt.upper()}, so the
            # label must not repeat it (avoids "RR RR drivetrain prior ...").
            frac_label = "drivetrain prior"

    # ── Step 4b: ballast adjustment (mass-weighted; exact no-op when ballast_kg<=0) ──
    # Positive ballast_position = rearward, negative = forward (GT7 convention).
    # Sign invariant: positive position → lower _bpos_frac → lowers effective front fraction.
    ballast_note = ""
    _bkg = float(ballast_kg or 0.0)
    if _bkg > 0.0 and (w_kg is not None and w_kg > 0.0):
        _bpos_frac = 0.5 - 0.5 * _BALLAST_AUTHORITY * (float(ballast_position or 0.0) / _BALLAST_POS_FULL)
        _eff = (frac * w_kg + _bpos_frac * _bkg) / (w_kg + _bkg)
        _eff = max(_BALLAST_FRAC_LO, min(_BALLAST_FRAC_HI, _eff))
        if abs(_eff - frac) >= 0.005:
            _dir = "rear" if _eff < frac else "front"
            ballast_note = f"effective front {_eff:.0%} (base {frac:.0%}, {_dir} ballast)"
            frac = _eff

    # Bounded delta: positive → front stiffer (front-heavy); negative → rear stiffer.
    delta = (frac - 0.50) * _SPLIT_HZ_SPAN
    front_hz = max(lo, min(hi, base_hz + delta))
    rear_hz  = max(lo, min(hi, base_hz - delta))

    # ── Step 5: discipline factor (applied after band clamp) ─────────────────
    disc_note = ""
    if obj == OBJ_QUALI:
        front_hz *= _QUALI_STIFFNESS_FACTOR
        rear_hz  *= _QUALI_STIFFNESS_FACTOR
        disc_note = "qualifying stiffened"

    # ── Step 6: GT7 slider clamp ─────────────────────────────────────────────
    front_hz = max(1.00, min(20.00, front_hz))
    rear_hz  = max(1.00, min(20.00, rear_hz))

    # ── Reason strings ────────────────────────────────────────────────────────
    if frac > 0.50:
        bias_desc = f"{dt.upper()} {frac_label} front-heavy bias (front stiffer)"
    elif frac < 0.50:
        bias_desc = f"{dt.upper()} {frac_label} rear-traction bias (rear stiffer)"
    else:
        bias_desc = f"{dt.upper()} balanced weight distribution"

    _parts = [band_name, bias_desc]
    if ballast_note:
        _parts.append(ballast_note)
    if track_note:
        _parts.append(track_note)
    if disc_note:
        _parts.append(disc_note)
    reason = ", ".join(_parts)

    return SpringFrequencies(
        front_hz=round(front_hz, 2),
        rear_hz=round(rear_hz, 2),
        front_reason=reason,
        rear_reason=reason,
    )


def derive_engineering_intents(
    vehicle: VehicleModel,
    track,                       # TrackTuneProfile (duck-typed) or None
    objective: str,
    driver=None,                 # DriverProfile (duck-typed) or None
    corner_profile=None,         # CornerProfile (duck-typed) or None
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
            # The higher-resolution per-corner profile (when available) owns the
            # mechanical-grip reasoning; only fall back to the coarse density heuristic
            # when no reviewed per-corner segments exist.
            _have_corner_profile = bool(getattr(corner_profile, "available", False))
            if not _have_corner_profile:
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

    # ---- PER-CORNER: shape to the actual corner character -----------------
    # Higher-resolution than corner density: tight-vs-open mix, traction-limited exits,
    # kerb load — from the track's reviewed segments (a geometric proxy, so conservative).
    if getattr(corner_profile, "available", False):
        try:
            from strategy.corner_profile import corner_profile_intents
            for _ci in corner_profile_intents(corner_profile, obj):
                intents.append(EngineeringIntent(
                    _ci["field"], int(_ci["direction"]), float(_ci.get("strength", 0.5)),
                    _ci.get("reason", ""), _ci.get("evidence", "corners"),
                    tuple(_ci.get("couples_with", ()))))
            notes.append("Per-corner: " + corner_profile.summary())
        except Exception:
            pass

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
