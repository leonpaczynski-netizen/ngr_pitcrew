"""Car-specific setup parameter ranges for the GT7 AI setup builder.

Provides:
  - GENERIC_DEFAULTS: canonical (min, max) for every in-scope parameter.
  - resolve_ranges(car_name): returns a copy of defaults with per-car overrides.
  - save_car_ranges(car_name, overrides): writes per-car overrides atomically.

The JSON store is at data/car_setup_ranges.json.
Keys are exact-case trimmed car names (matching car_specs.json).
Values are partial dicts of param -> {"min": N, "max": N}.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Canonical (min, max) for every in-scope parameter.
# Gearbox params (final_drive, gear_ratios, transmission_max_speed_kmh,
# shift_rpm) are intentionally excluded — they are not range-managed.
# ---------------------------------------------------------------------------
GENERIC_DEFAULTS: dict[str, tuple] = {
    "ride_height_front":      (60,   200),
    "ride_height_rear":       (60,   200),
    "springs_front":          (1.00, 20.00),
    "springs_rear":           (1.00, 20.00),
    "dampers_front_comp":     (1,    100),
    "dampers_front_ext":      (1,    100),
    "dampers_rear_comp":      (1,    100),
    "dampers_rear_ext":       (1,    100),
    "arb_front":              (1,    7),
    "arb_rear":               (1,    7),
    "camber_front":           (-5.0, 0.0),
    "camber_rear":            (-5.0, 0.0),
    "toe_front":              (-2.00, 2.00),
    "toe_rear":               (-2.00, 2.00),
    "aero_front":             (0,    1000),
    "aero_rear":              (0,    1000),
    "lsd_initial":            (0,    60),
    "lsd_accel":              (0,    60),
    "lsd_decel":              (0,    60),
    "lsd_front_initial":      (0,    60),
    "lsd_front_accel":        (0,    60),
    "lsd_front_decel":        (0,    60),
    "brake_bias":             (-5,   5),
    "ballast_kg":             (0,    60),
    "ballast_position":       (-50,  50),
    "power_restrictor":       (0,    100),
}

# ---------------------------------------------------------------------------
# JSON file path
# ---------------------------------------------------------------------------
_JSON_PATH = Path(__file__).parent.parent / "data" / "car_setup_ranges.json"

# ---------------------------------------------------------------------------
# Module-level mtime cache
# ---------------------------------------------------------------------------
_cache_data: dict[str, Any] = {}          # {car_name: {param: {"min": N, "max": N}}}
_cache_mtime: float | None = None


def _load_ranges_json() -> dict:
    """Return the parsed car_setup_ranges.json; returns {} on missing / parse error.

    Uses a module-level cache keyed by file mtime so reads are cheap after
    the first load, and fresh data is seen immediately after save_car_ranges()
    invalidates the cache.
    """
    global _cache_data, _cache_mtime
    try:
        mtime = _JSON_PATH.stat().st_mtime
    except FileNotFoundError:
        # No file yet — treat as empty, leave cache alone if it holds data
        if not _cache_data:
            _cache_data = {}
        return _cache_data

    if _cache_mtime is not None and mtime == _cache_mtime and _cache_data is not None:
        return _cache_data

    try:
        raw = _JSON_PATH.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            parsed = {}
    except Exception:
        parsed = {}

    _cache_data = parsed
    _cache_mtime = mtime
    return _cache_data


def _invalidate_cache() -> None:
    """Force the next _load_ranges_json() call to re-read the file."""
    global _cache_data, _cache_mtime
    _cache_data = {}
    _cache_mtime = None


def resolve_ranges(car_name: str) -> dict[str, tuple]:
    """Return a COPY of GENERIC_DEFAULTS with per-car overrides applied.

    car_name is stripped of whitespace before lookup.
    Empty or unknown car returns pure defaults.
    Never mutates GENERIC_DEFAULTS.
    """
    car_name = car_name.strip() if car_name else ""
    result = dict(GENERIC_DEFAULTS)   # shallow copy; tuples are immutable

    if not car_name:
        return result

    all_ranges = _load_ranges_json()
    car_overrides = all_ranges.get(car_name)
    if not isinstance(car_overrides, dict):
        return result

    for param, bounds in car_overrides.items():
        if not isinstance(bounds, dict):
            continue
        try:
            lo = bounds["min"]
            hi = bounds["max"]
        except (KeyError, TypeError):
            continue
        if param in result:
            result[param] = (lo, hi)

    return result


def save_car_ranges(car_name: str, overrides: dict[str, dict]) -> None:
    """Merge per-car overrides into the JSON store and write atomically.

    Parameters
    ----------
    car_name:
        Exact-case trimmed car name (matching car_specs.json). Will be
        stripped of leading/trailing whitespace.
    overrides:
        {param: {"min": N, "max": N}}. Every entry is validated (min <= max).

    Raises
    ------
    ValueError
        If any override has min > max.
    """
    car_name = car_name.strip() if car_name else ""
    if not car_name:
        raise ValueError("car_name must not be empty")

    # Validate all entries first
    for param, bounds in overrides.items():
        lo = bounds.get("min")
        hi = bounds.get("max")
        if lo is None or hi is None:
            raise ValueError(f"Override for '{param}' is missing 'min' or 'max'")
        if lo > hi:
            raise ValueError(
                f"Override for '{param}': min ({lo}) > max ({hi})"
            )

    # Load current data (may be empty)
    current = _load_ranges_json()
    merged = dict(current)   # shallow copy

    car_entry = dict(merged.get(car_name, {}))
    for param, bounds in overrides.items():
        car_entry[param] = {"min": bounds["min"], "max": bounds["max"]}
    merged[car_name] = car_entry

    # Atomic write: write .tmp then replace
    tmp_path = _JSON_PATH.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        tmp_path.replace(_JSON_PATH)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise

    _invalidate_cache()
