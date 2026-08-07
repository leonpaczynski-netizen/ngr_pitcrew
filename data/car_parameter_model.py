"""Per-car setup parameter model (pure, Qt-free) — UAT 2026-08-07 defects A5, A7.

The car data layer the engineering brain has never had. Before this module the
pipeline knew five facts about a car (category, PP, power, weight, aspiration) and
one hand-written global table of legal ranges, so every one of the 579 cars was
engineered as if it were the same car. This module resolves, per car and per field:

  * **legal range** — the outer safety clamp. Comes from a real GT7 capture when one
    exists, otherwise from ``setup_ranges.GENERIC_DEFAULTS``. Archetypes deliberately
    do NOT supply legal bounds: GT7's true slider limits are unknown for every car in
    the repository, and inventing them is the defect this module exists to correct.
  * **preference window** — the band a competent engineer works inside for this class.
    This is a DIFFERENT object from the legal range, and conflating the two is the root
    of several bad values (walking half of a 1-20 Hz legal spring range lands at 13 Hz;
    half of the Gr.3 preference band lands at 1 Hz).
  * **anchor** — the class-typical starting value. The engineering position that
    replaces "midpoint of the legal range", which is the absence of one.
  * **step** — the increment. No step model existed anywhere before this.

Every value carries a TIER saying where it came from: ``captured`` (real GT7 data the
driver entered) > ``archetype`` (class default) > ``generic`` (the global fallback
table). A car with no capture is resolvable and usable, and is visibly marked as
running on archetype defaults — it is never presented as engineered for that car.

Resolution is per FIELD, not per car: a partially-captured car uses its real data
where it has it and the archetype everywhere else.

Pure: no Qt, no DB, no network, no AI, no wall-clock, no randomness. Never raises.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field as _dc_field
from pathlib import Path
from typing import Optional

_DATA_DIR = Path(__file__).resolve().parent
_ARCHETYPE_PATH = _DATA_DIR / "car_archetypes.json"
_CAPTURE_PATH = _DATA_DIR / "car_gt7_ranges.json"

# Tier names, strongest first. Mirrors the per-field provenance tiers the Garage shows.
TIER_CAPTURED = "captured"
TIER_CURATED = "curated"          # a hand-entered per-car entry in car_setup_ranges.json
TIER_ARCHETYPE = "archetype"
TIER_GENERIC = "generic"
TIER_ASSUMED = "assumed"          # step sizes only — app precision, not GT7 truth

#: Tiers that describe THIS car rather than its class. The class archetype may widen a
#: generic bound but must never widen one of these — a per-car entry is more specific
#: than a class default even when it is only a preference window.
_CAR_SPECIFIC_TIERS = frozenset({TIER_CAPTURED, TIER_CURATED})

#: GT7 files its Gr.B rally cars under the Gr.4 category in car_specs.json, so the
#: category alone cannot identify them. They are detected by name instead.
_GRB_NAME = re.compile(r"\bGr\.?\s*B\b", re.IGNORECASE)

#: car_specs.json category -> archetype key.
_CATEGORY_TO_ARCHETYPE = {
    "gr.1": "gr1",
    "gr.2": "gr2",
    "gr.3": "gr3",
    "gr.4": "gr4",
    "gr.b": "grb",
    "road car": "road",
}

_DEFAULT_ARCHETYPE = "road"


# ---------------------------------------------------------------------------
# JSON loading — mtime-cached, degrades to empty on any failure.
# ---------------------------------------------------------------------------
_archetype_cache: Optional[dict] = None
_archetype_mtime: Optional[float] = None
_capture_cache: Optional[dict] = None
_capture_mtime: Optional[float] = None


def _load_json(path: Path, cache: Optional[dict], mtime: Optional[float]):
    """Return (data, mtime). Never raises; a missing or broken file reads as {}."""
    try:
        m = path.stat().st_mtime
    except OSError:
        return ({} if cache is None else cache), mtime
    if cache is not None and mtime == m:
        return cache, mtime
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            parsed = {}
    except Exception:
        parsed = {}
    return parsed, m


def _archetypes() -> dict:
    global _archetype_cache, _archetype_mtime
    _archetype_cache, _archetype_mtime = _load_json(
        _ARCHETYPE_PATH, _archetype_cache, _archetype_mtime)
    return _archetype_cache


def _captures() -> dict:
    global _capture_cache, _capture_mtime
    _capture_cache, _capture_mtime = _load_json(
        _CAPTURE_PATH, _capture_cache, _capture_mtime)
    return _capture_cache


def invalidate_cache() -> None:
    """Force the next resolve to re-read both JSON files (called after a capture save)."""
    global _archetype_cache, _archetype_mtime, _capture_cache, _capture_mtime
    _archetype_cache = _archetype_mtime = None
    _capture_cache = _capture_mtime = None


# ---------------------------------------------------------------------------
# Car-name matching — reuses the tolerant convention setup_ranges already uses so a
# capture keyed "Porsche 911 RSR (991) '17" still matches "Porsche 911 RSR '17".
# ---------------------------------------------------------------------------
def _normalise_car_key(name: str) -> str:
    if not name:
        return ""
    n = re.sub(r"\([^)]*\)", " ", str(name))      # drop "(991)" etc.
    return re.sub(r"\s+", " ", n).strip().lower()


def _match_car(store: dict, car_name: str):
    """Exact then normalised lookup into a {car_name: entry} map. None when absent."""
    if not isinstance(store, dict) or not car_name:
        return None
    entry = store.get(car_name)
    if isinstance(entry, dict):
        return entry
    target = _normalise_car_key(car_name)
    if not target:
        return None
    for key, val in store.items():
        if isinstance(val, dict) and _normalise_car_key(key) == target:
            return val
    return None


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


# ---------------------------------------------------------------------------
# Archetype resolution
# ---------------------------------------------------------------------------
def resolve_archetype(car_name: str, car_specs: Optional[dict] = None) -> str:
    """Return the archetype key for a car: gr1 / gr2 / gr3 / gr4 / grb / road.

    Gr.B is detected from the car NAME because GT7 files rally cars under the Gr.4
    category. Anything unrecognised falls back to ``road`` — the widest archetype, and
    the honest answer for a car we know nothing about.
    """
    name = str(car_name or "")
    if _GRB_NAME.search(name):
        return "grb"
    category = ""
    try:
        if car_specs is None:
            from strategy.setup_engineering import resolve_car_specs
            car_specs = resolve_car_specs(name)
        category = str((car_specs or {}).get("category", "") or "")
    except Exception:
        category = ""
    return _CATEGORY_TO_ARCHETYPE.get(category.strip().lower(), _DEFAULT_ARCHETYPE)


# ---------------------------------------------------------------------------
# The resolved model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ParameterSpec:
    """One field's resolved model. ``legal_*`` is the safety clamp; ``window_*`` is the
    engineering preference band; ``anchor`` is the starting position."""
    field: str
    legal_low: float
    legal_high: float
    legal_tier: str
    window_low: float
    window_high: float
    window_tier: str
    anchor: Optional[float]
    anchor_tier: str
    step: float
    step_tier: str
    source: str

    @property
    def legal_span(self) -> float:
        return max(0.0, self.legal_high - self.legal_low)

    @property
    def window_span(self) -> float:
        return max(0.0, self.window_high - self.window_low)

    def clamp_legal(self, v: float) -> float:
        return max(self.legal_low, min(self.legal_high, float(v)))

    def snap(self, v: float) -> float:
        """Round to the field's step, then clamp into the legal range.

        The step grid is anchored at ``legal_low`` so a snapped value is always one the
        slider can actually reach. Guards a zero/absent step by returning the clamped
        value untouched rather than dividing by zero.
        """
        val = self.clamp_legal(v)
        if not self.step or self.step <= 0:
            return val
        steps = round((val - self.legal_low) / self.step)
        snapped = self.legal_low + steps * self.step
        # Re-round to kill binary float dust (0.1 * 3 = 0.30000000000000004).
        decimals = max(0, len(str(self.step).split(".")[1]) if "." in str(self.step) else 0)
        return round(self.clamp_legal(snapped), decimals)

    def as_json(self) -> dict:
        return {
            "field": self.field,
            "legal": [self.legal_low, self.legal_high], "legal_tier": self.legal_tier,
            "window": [self.window_low, self.window_high], "window_tier": self.window_tier,
            "anchor": self.anchor, "anchor_tier": self.anchor_tier,
            "step": self.step, "step_tier": self.step_tier,
            "source": self.source,
        }


@dataclass(frozen=True)
class CarParameterModel:
    """Everything the setup pipeline knows about one car's adjustable parameters."""
    car: str
    archetype: str
    archetype_label: str
    archetype_confidence: str
    drivetrain: str
    num_gears: int                 # 0 = unknown (never invent a gearbox from this)
    redline_rpm: Optional[float]   # None = unknown
    captured_fields: tuple         # fields with real GT7 data
    parameters: dict               # field -> ParameterSpec
    #: Captured stock gear ratios, "gear_1".."gear_6" -> ratio. Empty until captured.
    #: The shape of a manufacturer's gearbox encodes more about the engine than
    #: anything the app can derive, so it is adjusted, never replaced (defect A4).
    stock_ratios: dict = _dc_field(default_factory=dict)

    @property
    def has_capture(self) -> bool:
        """True when ANY real GT7 data was captured for this car."""
        return bool(self.captured_fields) or self.num_gears > 0 or self.redline_rpm is not None

    @property
    def is_archetype_only(self) -> bool:
        """True when nothing about this car is real — the Garage must say so."""
        return not self.has_capture

    def spec(self, field: str) -> Optional[ParameterSpec]:
        return self.parameters.get(field)

    def legal_ranges(self) -> dict:
        """field -> (low, high). Shape-compatible with ``setup_ranges.resolve_ranges``."""
        return {f: (s.legal_low, s.legal_high) for f, s in self.parameters.items()}

    def windows(self) -> dict:
        """field -> (low, high) preference band."""
        return {f: (s.window_low, s.window_high) for f, s in self.parameters.items()}

    def anchors(self) -> dict:
        """field -> anchor value, omitting fields with no anchor."""
        return {f: s.anchor for f, s in self.parameters.items() if s.anchor is not None}

    def steps(self) -> dict:
        return {f: s.step for f, s in self.parameters.items()}

    def as_json(self) -> dict:
        return {
            "car": self.car,
            "archetype": self.archetype,
            "archetype_label": self.archetype_label,
            "archetype_confidence": self.archetype_confidence,
            "drivetrain": self.drivetrain,
            "num_gears": self.num_gears,
            "redline_rpm": self.redline_rpm,
            "has_capture": self.has_capture,
            "is_archetype_only": self.is_archetype_only,
            "captured_fields": list(self.captured_fields),
            "stock_ratios": dict(self.stock_ratios),
            "parameters": {f: s.as_json() for f, s in self.parameters.items()},
        }


def _archetype_entry(key: str) -> dict:
    data = _archetypes()
    entry = (data.get("archetypes") or {}).get(key)
    if not isinstance(entry, dict):
        entry = (data.get("archetypes") or {}).get(_DEFAULT_ARCHETYPE) or {}
    return entry if isinstance(entry, dict) else {}


def resolve_parameter_model(
    car_name: str,
    *,
    car_specs: Optional[dict] = None,
    drivetrain: str = "",
) -> CarParameterModel:
    """Resolve the full parameter model for a car. Never raises.

    Per field, in order of preference:
      * legal range  — captured GT7 min/max, else GENERIC_DEFAULTS (never the archetype)
      * window       — archetype preference band, intersected with the legal range
      * anchor       — captured stock value, else the archetype anchor
      * step         — captured step, else the archetype's assumed step

    An unknown car resolves cleanly to the ``road`` archetype with everything at
    ``archetype``/``generic`` tier, which is what ``is_archetype_only`` reports on.
    """
    car = (car_name or "").strip()

    # Legal ranges: the existing global table is the outer clamp. Note this deliberately
    # calls resolve_ranges, which still applies the four curated per-car entries — those
    # are preference windows wearing range semantics, and chunk 5 separates them.
    try:
        from strategy.setup_ranges import GENERIC_DEFAULTS, resolve_ranges
        legal = dict(resolve_ranges(car))
        generic = dict(GENERIC_DEFAULTS)
    except Exception:
        legal, generic = {}, {}

    arch_key = resolve_archetype(car, car_specs)
    arch = _archetype_entry(arch_key)
    arch_params = arch.get("parameters") or {}
    arch_steps = _archetypes().get("steps") or {}

    # Drivetrain: resolve from the curated data file when the caller did not supply one.
    # Defect A5 — this was consulted on only two of the setup paths, so the whole
    # engineering layer ran drivetrain-blind for an FF hatch and an RR 911 alike.
    dt = (drivetrain or "").strip().upper()
    if not dt:
        try:
            from data.car_drivetrain import resolve_drivetrain
            dt = (resolve_drivetrain(car) or "").strip().upper()
        except Exception:
            dt = ""

    cap = _match_car((_captures() or {}).get("cars") or {}, car) or {}
    cap_ranges = cap.get("ranges") if isinstance(cap.get("ranges"), dict) else {}
    cap_stock = cap.get("stock") if isinstance(cap.get("stock"), dict) else {}

    try:
        num_gears = int(cap.get("num_gears") or 0)
    except (TypeError, ValueError):
        num_gears = 0
    redline = _num(cap.get("redline_rpm"))

    # Captured stock gear ratios live alongside the other stock values but are not
    # range-managed fields, so they are collected separately.
    stock_ratios: dict = {}
    for _i in range(1, 7):
        _r = _num(cap_stock.get(f"gear_{_i}"))
        if _r is not None:
            stock_ratios[f"gear_{_i}"] = _r

    params: dict = {}
    captured: list = []
    for field, gen_bounds in (generic or {}).items():
        lo_gen, hi_gen = float(gen_bounds[0]), float(gen_bounds[1])
        cur = legal.get(field, (lo_gen, hi_gen))
        legal_low, legal_high = float(cur[0]), float(cur[1])
        # A bound that differs from the global table is a per-car entry someone curated
        # for THIS car in car_setup_ranges.json. It is a preference window wearing range
        # semantics (defect A7, unpicked in chunk 5) but it is still car-specific, so it
        # outranks the class archetype and must not be widened by it.
        legal_tier = (TIER_CURATED
                      if (legal_low, legal_high) != (lo_gen, hi_gen)
                      else TIER_GENERIC)
        sources: list = ["curated per-car range"] if legal_tier == TIER_CURATED else []

        # --- legal range: a capture is the only thing that can override the clamp ---
        cr = cap_ranges.get(field) if isinstance(cap_ranges.get(field), dict) else None
        if cr is not None:
            c_lo, c_hi = _num(cr.get("min")), _num(cr.get("max"))
            if c_lo is not None and c_hi is not None and c_hi >= c_lo:
                legal_low, legal_high = c_lo, c_hi
                legal_tier = TIER_CAPTURED
                sources.append("GT7 capture")
                captured.append(field)
        if legal_high < legal_low:
            legal_low, legal_high = legal_high, legal_low

        # --- preference window: the archetype's calibrated band ---
        ap = arch_params.get(field) if isinstance(arch_params.get(field), dict) else {}
        win = ap.get("window")
        window_tier = TIER_ARCHETYPE
        if isinstance(win, (list, tuple)) and len(win) == 2:
            w_lo, w_hi = _num(win[0]), _num(win[1])
        else:
            w_lo = w_hi = None
        if w_lo is None or w_hi is None:
            # No archetype opinion — the window IS the legal range, at generic tier.
            w_lo, w_hi = legal_low, legal_high
            window_tier = TIER_GENERIC
        else:
            sources.append(f"{arch_key} archetype")
        if w_hi < w_lo:
            w_lo, w_hi = w_hi, w_lo

        # --- clip the class window into the legal clamp ---
        # The archetype bands are authored to sit inside GENERIC_DEFAULTS (which was
        # itself corrected for defect A7 — its 60mm ride-height floor and ARB ceiling
        # of 7 were both narrower than values already run in GT7). Clipping here is a
        # guard, not a routine narrowing; it does real work only against a car-specific
        # legal range, which is MORE specific than the class and rightly wins.
        w_lo = max(legal_low, min(legal_high, w_lo))
        w_hi = max(legal_low, min(legal_high, w_hi))
        if w_hi < w_lo:
            w_lo = w_hi = legal_low

        # --- anchor: captured stock value beats the archetype position ---
        anchor = _num(cap_stock.get(field))
        anchor_tier = TIER_CAPTURED
        if anchor is None:
            anchor = _num(ap.get("anchor"))
            anchor_tier = TIER_ARCHETYPE if anchor is not None else TIER_GENERIC
        else:
            sources.append("GT7 stock value")
            if field not in captured:
                captured.append(field)
        if anchor is not None:
            anchor = max(legal_low, min(legal_high, anchor))

        # --- step ---
        step = _num(cr.get("step")) if cr is not None else None
        step_tier = TIER_CAPTURED
        if step is None or step <= 0:
            step = _num(arch_steps.get(field))
            step_tier = TIER_ASSUMED
        if step is None or step <= 0:
            step, step_tier = 0.0, TIER_GENERIC

        params[field] = ParameterSpec(
            field=field,
            legal_low=legal_low, legal_high=legal_high, legal_tier=legal_tier,
            window_low=w_lo, window_high=w_hi, window_tier=window_tier,
            anchor=anchor, anchor_tier=anchor_tier,
            step=float(step), step_tier=step_tier,
            source=", ".join(sources) if sources else "generic fallback table",
        )

    if num_gears <= 0:
        # The archetype's typical gear count is NOT used as num_gears: authoring a
        # gearbox from a class assumption is defect A4 in a different costume. It is
        # exposed separately so the capture screen can pre-fill the field.
        num_gears = 0

    return CarParameterModel(
        car=car,
        archetype=arch_key,
        archetype_label=str(arch.get("label", "") or arch_key),
        archetype_confidence=str(arch.get("confidence", "low") or "low"),
        drivetrain=dt,
        num_gears=num_gears,
        redline_rpm=redline,
        captured_fields=tuple(sorted(set(captured))),
        parameters=params,
        stock_ratios=stock_ratios,
    )


def typical_gears_for_car(car_name: str, car_specs: Optional[dict] = None) -> int:
    """The class-typical gear count — for PRE-FILLING the capture form only.

    Never feed this to the gearbox author: a class assumption is not evidence that
    this car has that many gears (UAT 2026-08-07 defect A4).
    """
    try:
        return int(_archetype_entry(resolve_archetype(car_name, car_specs))
                   .get("typical_gears") or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Capture store writes — used by the Garage car-data capture panel (chunk 9).
# ---------------------------------------------------------------------------
def save_car_capture(car_name: str, entry: dict) -> bool:
    """Merge one car's captured GT7 data into the store and write atomically.

    ``entry`` may carry any of ``num_gears``, ``redline_rpm``, ``stock`` and ``ranges``;
    each is merged field-by-field so a partial capture never erases earlier work.
    Returns True on success. Never raises.
    """
    car = (car_name or "").strip()
    if not car or not isinstance(entry, dict):
        return False
    try:
        store = dict(_captures() or {})
        cars = dict(store.get("cars") or {})
        existing = dict(cars.get(car) or {})

        for scalar in ("num_gears", "redline_rpm"):
            if entry.get(scalar) is not None:
                existing[scalar] = entry[scalar]
        for nested in ("stock", "ranges"):
            incoming = entry.get(nested)
            if isinstance(incoming, dict):
                merged = dict(existing.get(nested) or {})
                merged.update(incoming)
                existing[nested] = merged

        cars[car] = existing
        store["cars"] = cars
        tmp = _CAPTURE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_CAPTURE_PATH)
    except Exception:
        return False
    invalidate_cache()
    return True
