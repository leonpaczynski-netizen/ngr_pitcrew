"""Anchor resolution (pure, Qt-free) — UAT 2026-08-07 defect A1.

The neutral reference for every field must be a physical baseline, not the midpoint
of a legal range. The midpoint of a (0, 1000) downforce slider is not an engineering
position; it is the absence of one, and walking away from it is how a Gr.3 baseline
came out at 108mm ride height with 13.4Hz springs and more camber on the rear than
the front.

``resolve_anchor`` answers one question per field: *where should this car, at this
track, for this objective, START?* — in strict order of evidence:

  1. ``PROVEN``      — a vetted setup for this exact car + track + discipline.
  2. ``TRANSFERRED`` — the same car proven somewhere else (or a same-class result).
  3. ``STOCK``       — the car's real GT7 stock value, if it has been captured.
  4. ``ARCHETYPE``   — the class-typical position (Gr.1/2/3/4/B, road).
  5. ``GENERIC``     — the legal midpoint. Last resort, and labelled as the absence
                       of a position rather than dressed up as a decision.

Each anchor carries a preference WINDOW as well as a value: the band the field should
be worked inside. A proven anchor gets a tight band around what worked; an archetype
anchor gets the class band; only a GENERIC anchor gets the full legal range. This is
the second half of the A1 fix and it matters as much as the first — half of a generic
1-20Hz spring range is 9.5Hz, which is what produced 13.4Hz springs, while half of the
Gr.3 band is 1.0Hz.

**Deliberately NOT done here: drivetrain shaping.** An RR 911 and an FF hatch do need
different camber, ARB and diff settings, but that reasoning already has an owner —
``setup_engineering.derive_engineering_intents``, which emits it as engineering bias
layered on top of the seed. Applying it here as well would double-count it, which is
the same class of bug as stacking driver-profile bias onto an already-proven value.
The anchor is the CLASS position; the drivetrain moves it, elsewhere, once.

Pure: no Qt, no DB, no network, no AI, no wall-clock, no randomness. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Provenance tiers, strongest first. These are the same tier names the Garage shows
# per field; ENGINEERED sits between TRANSFERRED and ARCHETYPE but is assigned by the
# authoring layer (a physics model with real car data), not by anchor resolution.
TIER_PROVEN = "PROVEN"
TIER_TRANSFERRED = "TRANSFERRED"
TIER_STOCK = "STOCK"
TIER_ARCHETYPE = "ARCHETYPE"
TIER_GENERIC = "GENERIC"

#: Tiers at or above which a field may carry the label "engineered for car + track +
#: objective". ARCHETYPE and GENERIC may not — they are class defaults and fallbacks.
ENGINEERED_OR_BETTER = frozenset({TIER_PROVEN, TIER_TRANSFERRED, TIER_STOCK})

#: Half-width of the band around a PROVEN/TRANSFERRED anchor, as a fraction of the
#: legal span. Mirrors setup_engineering_context._WINDOW_HALF_FRAC so a proven value
#: gets the same treatment whichever path builds the window.
_PROVEN_HALF_FRAC = 0.14

#: A TRANSFERRED value is the right car but the wrong track, so it earns a wider band
#: than a directly proven one — the direction is trustworthy, the exact number is not.
_TRANSFERRED_HALF_FRAC = 0.22

#: Tier ceilings from setup_history_intelligence: <= 2 is same car + same/similar
#: track (proven), <= 3 is same car elsewhere (transferred).
_HIST_TIER_STRONG = 2
_HIST_TIER_SAME_CAR = 3


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


@dataclass(frozen=True)
class FieldAnchor:
    """Where one field starts, why, and the band it should be worked inside."""
    field: str
    value: float
    tier: str
    source: str
    window_low: float
    window_high: float
    legal_low: float
    legal_high: float

    @property
    def window_span(self) -> float:
        return max(0.0, self.window_high - self.window_low)

    @property
    def is_engineering_position(self) -> bool:
        """False for GENERIC — a legal midpoint is not a decision and must never be
        presented as one."""
        return self.tier != TIER_GENERIC

    def as_json(self) -> dict:
        return {"field": self.field, "value": self.value, "tier": self.tier,
                "source": self.source, "window": [self.window_low, self.window_high],
                "legal": [self.legal_low, self.legal_high]}


@dataclass(frozen=True)
class AnchorSet:
    """Every field's starting position for one car + track + objective."""
    car: str
    track: str
    discipline: str
    archetype: str
    archetype_confidence: str
    is_archetype_only: bool
    anchors: dict                  # field -> FieldAnchor

    def get(self, field: str) -> Optional[FieldAnchor]:
        return self.anchors.get(field)

    def value(self, field: str) -> Optional[float]:
        a = self.anchors.get(field)
        return a.value if a is not None else None

    def tier(self, field: str) -> str:
        a = self.anchors.get(field)
        return a.tier if a is not None else TIER_GENERIC

    def window(self, field: str) -> Optional[tuple]:
        a = self.anchors.get(field)
        return (a.window_low, a.window_high) if a is not None else None

    def tier_counts(self) -> dict:
        out: dict = {}
        for a in self.anchors.values():
            out[a.tier] = out.get(a.tier, 0) + 1
        return out

    def headline(self) -> str:
        """One sentence the Garage can show at the top of the sheet, so a setup that
        is mostly class defaults says so instead of presenting as engineered."""
        counts = self.tier_counts()
        total = sum(counts.values()) or 1
        weak = counts.get(TIER_ARCHETYPE, 0) + counts.get(TIER_GENERIC, 0)
        if counts.get(TIER_PROVEN, 0) >= total * 0.5:
            return "Started from your proven setup for this car at this track."
        if weak >= total * 0.8:
            return (f"Started from {self.archetype} class defaults — no captured GT7 "
                    f"data and no proven history for this car. Treat as a starting "
                    f"point to test, not a setup engineered for this car.")
        if weak >= total * 0.4:
            return (f"Mixed: some fields from your history, the rest from "
                    f"{self.archetype} class defaults.")
        return "Started from real data for this car."

    def as_json(self) -> dict:
        return {"car": self.car, "track": self.track, "discipline": self.discipline,
                "archetype": self.archetype,
                "archetype_confidence": self.archetype_confidence,
                "is_archetype_only": self.is_archetype_only,
                "tier_counts": self.tier_counts(), "headline": self.headline(),
                "anchors": {f: a.as_json() for f, a in self.anchors.items()}}


def _proven_window(value: float, lo: float, hi: float, frac: float) -> tuple:
    """Band around a proven value, clipped into the legal range."""
    half = max((hi - lo) * frac, 0.0)
    return (max(lo, value - half), min(hi, value + half))


def resolve_anchor(
    car: str,
    track: str,
    discipline: str,
    *,
    ranges: Optional[dict] = None,
    history_prior: Optional[dict] = None,
    proven_fields: Optional[dict] = None,
    car_specs: Optional[dict] = None,
    drivetrain: str = "",
    parameter_model=None,
) -> AnchorSet:
    """Resolve every field's starting position. Never raises.

    ``proven_fields`` is the vetted complete setup for this exact car + track +
    discipline (``proven_setup_library.find_proven_setup``). When omitted, it is
    looked up. ``history_prior`` is the per-field proven-history map from
    ``setup_history_intelligence.build_historical_prior``.

    ``ranges`` overrides the legal clamp when a caller already resolved one; otherwise
    the parameter model's own legal ranges are used.
    """
    car = (car or "").strip()
    discipline = str(discipline or "base").strip().lower()

    if parameter_model is None:
        try:
            from data.car_parameter_model import resolve_parameter_model
            parameter_model = resolve_parameter_model(
                car, car_specs=car_specs, drivetrain=drivetrain)
        except Exception:
            parameter_model = None

    if proven_fields is None:
        try:
            from strategy.proven_setup_library import find_proven_setup
            proven_fields = find_proven_setup(car, track, discipline) or {}
        except Exception:
            proven_fields = {}
    proven_fields = proven_fields or {}
    history_prior = history_prior or {}

    specs = getattr(parameter_model, "parameters", {}) or {}
    legal = dict(ranges or {})
    if not legal and parameter_model is not None:
        try:
            legal = parameter_model.legal_ranges()
        except Exception:
            legal = {}

    anchors: dict = {}
    for field in sorted(set(specs) | set(legal)):
        spec = specs.get(field)
        bounds = legal.get(field)
        c_lo = c_hi = None
        if bounds is not None and len(bounds) == 2:
            c_lo, c_hi = float(bounds[0]), float(bounds[1])

        if spec is None:
            if c_lo is None:
                continue
            lo, hi = c_lo, c_hi
        elif getattr(spec, "legal_tier", "") in ("captured", "curated"):
            # Car-specific data is authoritative — a caller-supplied generic range must
            # not widen a clamp the driver measured off the actual slider, nor one
            # someone curated for this car.
            lo, hi = spec.legal_low, spec.legal_high
        elif c_lo is None:
            lo, hi = spec.legal_low, spec.legal_high
        else:
            # Neither side is measured: the caller's `ranges` is the same hand-written
            # global table, and the parameter model has already widened it to admit the
            # class band. Take the union so the caller's narrower generic bound cannot
            # veto the class position — GENERIC_DEFAULTS floors ride height at 60mm
            # while the vetted Gr.3 setups run 55, and clamping to it would put the
            # anchor back on a boundary (UAT 2026-08-07 defect A7).
            lo = min(c_lo, spec.legal_low)
            hi = max(c_hi, spec.legal_high)
        if hi < lo:
            lo, hi = hi, lo

        value = tier = source = None
        w_lo = w_hi = None

        # 1. PROVEN — a vetted setup for this exact car + track + discipline.
        pv = _num(proven_fields.get(field))
        if pv is not None:
            value, tier = max(lo, min(hi, pv)), TIER_PROVEN
            source = f"vetted {discipline} setup for this car at {track or 'this track'}"
            w_lo, w_hi = _proven_window(value, lo, hi, _PROVEN_HALF_FRAC)

        # 2. TRANSFERRED — the same car proven elsewhere.
        if value is None:
            hp = history_prior.get(field)
            if isinstance(hp, dict):
                hv = _num(hp.get("value"))
                try:
                    htier = int(hp.get("tier"))
                except (TypeError, ValueError):
                    htier = None
                if hv is not None and htier is not None and htier <= _HIST_TIER_SAME_CAR:
                    value = max(lo, min(hi, hv))
                    strong = htier <= _HIST_TIER_STRONG
                    tier = TIER_PROVEN if strong else TIER_TRANSFERRED
                    source = ("your proven value for this car at this track" if strong
                              else "your proven value for this car at another track")
                    w_lo, w_hi = _proven_window(
                        value, lo, hi,
                        _PROVEN_HALF_FRAC if strong else _TRANSFERRED_HALF_FRAC)

        # 3/4. STOCK or ARCHETYPE — whichever the parameter model resolved.
        if value is None and spec is not None and spec.anchor is not None:
            value = max(lo, min(hi, spec.anchor))
            if spec.anchor_tier == "captured":
                tier = TIER_STOCK
                source = "this car's GT7 stock value"
            else:
                tier = TIER_ARCHETYPE
                source = f"{getattr(parameter_model, 'archetype', 'class')} class default"
            w_lo, w_hi = spec.window_low, spec.window_high

        # 5. GENERIC — the legal midpoint. Not a position; say so.
        if value is None:
            value, tier = (lo + hi) / 2.0, TIER_GENERIC
            source = "midpoint of the legal range — no data for this field"
            w_lo, w_hi = lo, hi

        if w_lo is None or w_hi is None or w_hi < w_lo:
            w_lo, w_hi = lo, hi
        # A degenerate band gives the walk nothing to work with; fall back to legal.
        if w_hi <= w_lo and hi > lo:
            w_lo, w_hi = lo, hi

        anchors[field] = FieldAnchor(
            field=field, value=value, tier=tier, source=source,
            window_low=w_lo, window_high=w_hi, legal_low=lo, legal_high=hi)

    return AnchorSet(
        car=car, track=str(track or ""), discipline=discipline,
        archetype=str(getattr(parameter_model, "archetype", "") or ""),
        archetype_confidence=str(getattr(parameter_model, "archetype_confidence", "") or ""),
        is_archetype_only=bool(getattr(parameter_model, "is_archetype_only", True)),
        anchors=anchors)
