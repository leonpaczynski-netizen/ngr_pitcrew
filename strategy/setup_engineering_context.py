"""Canonical Setup Engineering Context (pure, Qt-free) — Engineering-Brain Phase 2.

The plan's Layer 1: ONE immutable context that every authoring and diagnostic layer
reasons from, so no component builds its own partial interpretation of the facts. It
bundles the Driver, the Car (vehicle model), the Track (tune profile + per-corner
character), the Event objective/parameters, and the current evidence (setup, diagnosis,
proven history) — built ONCE — and derives two things the plan calls for:

  * **Working windows** — every adjustable field gets a WINDOW (a range with evidence
    provenance and a preferred value), assembled through the documented evidence
    precedence, instead of one forced value. A lower-confidence source never overrides
    a higher one; proven driver history narrows the window toward what worked.
  * **Confidence separated by capability** — the track model's usefulness is reported
    per use (setup shaping vs per-corner detail), not as a single flag.

It authors no setup values and calls no AI — it is the shared, evidence-honest picture
the deterministic authoring (and the Phase-3 solver) select from.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Optional


# Evidence precedence (higher wins) — the canonical ordering used to build windows.
EVIDENCE_PRECEDENCE: tuple = (
    "1. Safety and legal range",
    "2. Event restrictions (tuning permissions)",
    "3. Proven same-driver+car+track history",
    "4. Proven same-car history from another track (reduced confidence)",
    "5. Car-characteristic range",
    "6. Track-derived range",
    "7. Driver-style range",
    "8. Generic conservative fallback",
)

# Tier → confidence for a proven historical value (mirrors setup_history_intelligence).
_TIER_STRONG = 2          # <= this = strong scope (same car, same/similar track)
_TIER_SAME_CAR = 3        # <= this = same car (other track) — a valid starting window


@dataclass(frozen=True)
class WorkingWindow:
    """A field's working range with evidence — not a single forced value.

    ``low``/``high`` are the LEGAL range (the safety clamp). ``pref_low``/``pref_high``
    are the engineering PREFERENCE band, which is normally much narrower — UAT
    2026-08-07 defect A1/A7: the two used to be the same object, so anything that
    walked "half the window" walked half of a generic slider and landed at 13.4Hz
    springs. ``anchor`` is where the field starts when there is no proven value; see
    ``strategy.setup_anchor``.
    """
    field: str
    low: float
    high: float
    preferred: Optional[float]     # proven value for this field, or None
    sources: tuple                 # evidence provenance, precedence-ordered
    confidence: str                # high / medium / low / none
    locked: bool = False           # event forbids tuning this field
    anchor: Optional[float] = None       # starting position (proven > stock > class)
    anchor_tier: str = ""                # PROVEN / TRANSFERRED / STOCK / ARCHETYPE / GENERIC
    window_low: Optional[float] = None   # preference band; None = fall back to legal
    window_high: Optional[float] = None

    @property
    def pref_low(self) -> float:
        return self.low if self.window_low is None else self.window_low

    @property
    def pref_high(self) -> float:
        return self.high if self.window_high is None else self.window_high

    @property
    def centre(self) -> float:
        """The reference point every candidate moves away from.

        Proven value first, then the resolved anchor, and only as a last resort the
        legal midpoint — which is the absence of an engineering position, not one.
        """
        if self.preferred is not None:
            return float(self.preferred)
        if self.anchor is not None:
            return float(self.anchor)
        return (self.low + self.high) / 2.0

    def contains(self, v: float) -> bool:
        try:
            return self.low <= float(v) <= self.high
        except (TypeError, ValueError):
            return False

    def as_json(self) -> dict:
        return {"field": self.field, "low": self.low, "high": self.high,
                "preferred": self.preferred, "sources": list(self.sources),
                "confidence": self.confidence, "locked": self.locked,
                "anchor": self.anchor, "anchor_tier": self.anchor_tier,
                "window": [self.pref_low, self.pref_high]}


# Fraction of a field's legal span used as the half-width of a proven-value window.
_WINDOW_HALF_FRAC = 0.14


def _num(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f and f not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def build_working_window(
    field: str,
    ranges: dict,
    history_prior: dict,
    *,
    locked: bool = False,
    current_value: Optional[float] = None,
    anchor=None,
) -> Optional[WorkingWindow]:
    """Assemble one field's working window through evidence precedence.

    Legal range is the outer bound (safety). If the event locks the field, the window
    collapses to the current value (EVENT_CONSTRAINT). A strong proven value narrows the
    window toward what worked; otherwise the window is the full legal range at low
    confidence. Returns None when the field has no legal range (not adjustable)."""
    rng = (ranges or {}).get(field)
    if not rng or len(rng) != 2:
        return None
    lo, hi = float(rng[0]), float(rng[1])
    if hi < lo:
        lo, hi = hi, lo
    span = hi - lo

    if locked:
        cv = current_value if current_value is not None else lo
        return WorkingWindow(field, cv, cv, cv, ("2. event restriction — locked",),
                             "n/a", locked=True)

    # UAT 2026-08-07 defect A1 — the anchor (strategy.setup_anchor) supplies the
    # starting position and the preference band for every field. Without it the window
    # was the whole legal range at low confidence and the centre was its midpoint.
    a_val = getattr(anchor, "value", None)
    a_tier = str(getattr(anchor, "tier", "") or "")
    a_lo = getattr(anchor, "window_low", None)
    a_hi = getattr(anchor, "window_high", None)
    if a_lo is None or a_hi is None:
        a_lo, a_hi = lo, hi
    # The anchor resolved the legal clamp already (caller ranges unioned with the class
    # band, with a real GT7 capture taking precedence over both). Adopt it, or the
    # generic 60mm ride-height floor clamps the Gr.3 anchor of 55 straight back up.
    _al, _ah = getattr(anchor, "legal_low", None), getattr(anchor, "legal_high", None)
    if _al is not None and _ah is not None and _ah > _al:
        lo, hi = float(_al), float(_ah)
        span = hi - lo

    pd = (history_prior or {}).get(field)
    proven = None
    tier = None
    source = ""
    if isinstance(pd, dict):
        proven = _num(pd.get("value"))
        try:
            tier = int(pd.get("tier"))
        except (TypeError, ValueError):
            tier = None
        source = str(pd.get("source", ""))

    if proven is not None and tier is not None and tier <= _TIER_SAME_CAR and span > 0:
        half = max(span * _WINDOW_HALF_FRAC, 0.0)
        w_lo = max(lo, proven - half)
        w_hi = min(hi, proven + half)
        conf = "high" if tier <= _TIER_STRONG else "medium"
        prov_label = ("3. proven same-car same/similar-track" if tier <= _TIER_STRONG
                      else "4. proven same-car (other track)")
        # A proven value narrows the legal clamp itself — it always did, and that is
        # correct: the strongest evidence there is should bound the search.
        return WorkingWindow(
            field, round(w_lo, 3), round(w_hi, 3), round(proven, 3),
            ("1. legal range", f"{prov_label}: {proven:g}" + (f" ({source})" if source else ""),
             "narrowed toward your proven value"),
            conf,
            anchor=round(proven, 3), anchor_tier=a_tier or "PROVEN",
            window_low=round(w_lo, 3), window_high=round(w_hi, 3))

    # No proven value → the legal range stays the clamp, but the PREFERENCE band and
    # the starting position come from the anchor. Confidence tracks the anchor's tier:
    # a class default is honest evidence of a starting point, a legal midpoint is not.
    conf = "low"
    sources = ("1. legal range", "8. generic conservative fallback")
    if a_val is not None and a_tier:
        conf = "medium" if a_tier in ("STOCK", "TRANSFERRED") else "low"
        sources = ("1. legal range",
                   f"anchor ({a_tier.lower()}): {a_val:g}"
                   + (f" — {getattr(anchor, 'source', '')}"
                      if getattr(anchor, "source", "") else ""))
    return WorkingWindow(field, round(lo, 3), round(hi, 3), None, sources, conf,
                         anchor=(round(a_val, 3) if a_val is not None else None),
                         anchor_tier=a_tier,
                         window_low=round(float(a_lo), 3),
                         window_high=round(float(a_hi), 3))


def build_working_windows(
    ranges: dict, history_prior: dict, *,
    locked_fields=None, current_setup=None, anchor_set=None,
) -> dict:
    """field -> WorkingWindow for every field with a legal range.

    ``anchor_set`` is a ``strategy.setup_anchor.AnchorSet``; when absent every window
    falls back to the legal range and its midpoint, which is the pre-A1 behaviour.
    """
    locked = {f for f in (locked_fields or ())}
    setup = current_setup or {}
    out: dict = {}
    for field in (ranges or {}):
        w = build_working_window(
            field, ranges, history_prior,
            locked=field in locked, current_value=_num(setup.get(field)),
            anchor=(anchor_set.get(field) if anchor_set is not None else None))
        if w is not None:
            out[field] = w
    return out


def track_confidence_by_capability(track_profile, corner_profile) -> dict:
    """Report the track model's usefulness PER capability, not as one flag."""
    trustworthy = bool(getattr(track_profile, "trustworthy", False)) if track_profile else False
    measured = bool(getattr(track_profile, "measured", False)) if track_profile else False
    cp_available = bool(getattr(corner_profile, "available", False)) if corner_profile else False
    cp_conf = str(getattr(corner_profile, "confidence", "none")) if corner_profile else "none"
    return {
        # Enough geometry (lap length + corners) to shape aero/gearing/support.
        # UAT 2026-08-07 defect A2: this returned "medium" — which passes the
        # synthesis-primary gate — for a track SEED (a hand-entered length and an
        # expected corner count). A seed is enough to nudge aero; it is nowhere near
        # enough to authorise replacing the engineered baseline. "high" now requires a
        # measured, accepted model; a seed is "low" and shapes advisories only.
        "setup_shaping": "high" if measured else ("low" if trustworthy else "none"),
        # Reviewed per-corner segments to shape corner-specific demands.
        "corner_detail": (cp_conf if cp_available else "none"),
        # Whether a trustworthy geometry model exists at all.
        "geometry": "high" if trustworthy else "none",
    }


def feedback_state(diagnosis: dict, history_prior: dict) -> dict:
    """Distinguish what the driver reports NOW from their proven historical preferences
    (plan §Phase 2: 'current versus historical feedback state')."""
    d = diagnosis or {}
    flags = d.get("driver_feel_flags", {}) or {}
    current = sorted(f for f, v in flags.items()
                     if v and f not in ("entry_balance_good",))
    return {
        "has_current_feedback": bool(current),
        "current_problems": current,
        "has_proven_history": bool(history_prior),
        "proven_fields": sorted(history_prior.keys()) if history_prior else [],
    }


@dataclass(frozen=True)
class SetupEngineeringContext:
    """The ONE canonical context every authoring/diagnostic layer reasons from."""
    car: str
    objective: str                 # base / qualifying / race
    vehicle: object                # VehicleModel
    track_profile: object          # TrackTuneProfile or None
    corner_profile: object         # CornerProfile or None
    driver: object                 # DriverProfile
    ranges: dict
    allowed_tuning: Optional[list]
    tuning_locked: bool
    # event
    duration_mins: float
    tyre_wear_multiplier: Optional[float]
    fuel_multiplier: Optional[float]
    refuel_rate: Optional[float]
    required_compounds: tuple
    car_class: str
    # evidence
    current_setup: Optional[dict]
    diagnosis: Optional[dict]
    history_prior: dict
    # derived (built once)
    working_windows: dict          # field -> WorkingWindow
    track_confidence: dict         # per-capability
    feedback: dict                 # current vs historical
    missing_evidence: tuple
    anchor_set: object = None      # strategy.setup_anchor.AnchorSet (or None)

    def window(self, field: str) -> Optional[WorkingWindow]:
        return self.working_windows.get(field)

    def as_json(self) -> dict:
        return {
            "car": self.car,
            "objective": self.objective,
            "vehicle": (self.vehicle.summary() if hasattr(self.vehicle, "summary") else str(self.vehicle)),
            "track": (self.track_profile.summary() if hasattr(self.track_profile, "summary")
                      else None),
            "corner": (self.corner_profile.summary() if hasattr(self.corner_profile, "summary")
                       else None),
            "track_confidence": dict(self.track_confidence),
            "feedback": dict(self.feedback),
            "working_windows": {f: w.as_json() for f, w in self.working_windows.items()},
            "missing_evidence": list(self.missing_evidence),
            "evidence_precedence": list(EVIDENCE_PRECEDENCE),
            "anchors": (self.anchor_set.as_json()
                        if hasattr(self.anchor_set, "as_json") else None),
        }


def build_setup_engineering_context(
    *,
    car: str,
    objective: str,
    ranges: dict,
    drivetrain: str = "",
    num_gears: int = 6,
    profile=None,
    allowed_tuning=None,
    tuning_locked: bool = False,
    track_profile=None,
    corner_profile=None,
    history_prior: Optional[dict] = None,
    current_setup: Optional[dict] = None,
    diagnosis: Optional[dict] = None,
    duration_mins: float = 0.0,
    tyre_wear_multiplier: Optional[float] = None,
    fuel_multiplier: Optional[float] = None,
    refuel_rate: Optional[float] = None,
    required_compounds: tuple = (),
    car_class: str = "",
    car_specs: Optional[dict] = None,
    track_name: str = "",
    proven_fields: Optional[dict] = None,
) -> SetupEngineeringContext:
    """Build the canonical context ONCE from the shared builders. Degrades honestly on
    any missing input (never raises)."""
    history_prior = history_prior or {}

    # Vehicle model — from the real specs, with any series-regulated weight/power the
    # driver entered on the setup taking precedence over the stock JSON figures.
    try:
        from strategy.setup_engineering import (
            build_vehicle_model, resolve_car_specs, effective_car_specs)
        base = car_specs if car_specs is not None else resolve_car_specs(car)
        specs = effective_car_specs(car, current_setup)
        # Preserve any extra keys an explicitly-passed car_specs carried.
        if car_specs is not None:
            merged = dict(base)
            merged.update({k: v for k, v in specs.items() if k in ("weight_kg", "power_hp")})
            specs = merged
        vehicle = build_vehicle_model(car, drivetrain, num_gears, specs)
    except Exception:
        vehicle = None

    # Locked fields for the working windows.
    locked_fields: set = set()
    if allowed_tuning:
        try:
            from strategy.driving_advisor import _derive_locked_fields
            locked_fields = _derive_locked_fields(allowed_tuning)
        except Exception:
            locked_fields = set()

    # UAT 2026-08-07 defects A1 + A3 — resolve every field's starting position before
    # building the windows. `proven_fields` is the vetted complete setup for this exact
    # car + track + discipline; it used to be seeded into the baseline and then never
    # reach the context, so `WorkingWindow.preferred` stayed None and the guard in
    # reconcile_synthesis_primary that is supposed to protect a proven value could
    # never fire. Passing it here is what makes that guard real.
    anchor_set = None
    try:
        from strategy.setup_anchor import resolve_anchor
        anchor_set = resolve_anchor(
            car, track_name or getattr(track_profile, "track_name", "") or "",
            str(objective), ranges=ranges, history_prior=history_prior,
            proven_fields=proven_fields, car_specs=car_specs, drivetrain=drivetrain)
    except Exception:
        anchor_set = None

    # A proven field enters the history prior at the strongest tier so the window
    # narrows around it and synthesis treats it as the primary author.
    if proven_fields:
        merged_prior = dict(history_prior)
        for _f, _v in (proven_fields or {}).items():
            if _num(_v) is None:
                continue
            merged_prior[_f] = {"value": float(_v), "tier": 1,
                                "source": "proven-setup library"}
        history_prior = merged_prior

    windows = build_working_windows(
        ranges, history_prior, locked_fields=locked_fields,
        current_setup=current_setup, anchor_set=anchor_set)
    track_conf = track_confidence_by_capability(track_profile, corner_profile)
    fb = feedback_state(diagnosis, history_prior)

    missing: list = []
    if not getattr(vehicle, "power_to_weight", None):
        missing.append("car power/weight (vehicle model uses drivetrain only)")
    if not (track_profile and getattr(track_profile, "trustworthy", False)):
        missing.append("trustworthy track model")
    if not (corner_profile and getattr(corner_profile, "available", False)):
        missing.append("reviewed per-corner segments")
    if not history_prior:
        missing.append("proven same-car history")

    return SetupEngineeringContext(
        car=car, objective=str(objective), vehicle=vehicle, track_profile=track_profile,
        corner_profile=corner_profile, driver=profile, ranges=ranges,
        allowed_tuning=allowed_tuning, tuning_locked=tuning_locked,
        duration_mins=duration_mins, tyre_wear_multiplier=tyre_wear_multiplier,
        fuel_multiplier=fuel_multiplier, refuel_rate=refuel_rate,
        required_compounds=tuple(required_compounds or ()), car_class=car_class,
        current_setup=current_setup, diagnosis=diagnosis, history_prior=history_prior,
        working_windows=windows, track_confidence=track_conf, feedback=fb,
        missing_evidence=tuple(missing), anchor_set=anchor_set,
    )
