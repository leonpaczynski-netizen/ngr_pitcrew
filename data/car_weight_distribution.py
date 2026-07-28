"""Front weight-distribution resolver — reads the curated ``car_weight_distribution.json`` data file.

Per-car front-axle weight fraction (0.0–1.0). A car not in the file resolves to None —
callers then fall back to the drivetrain-keyed ``_WEIGHT_DIST_PRIOR`` in
``strategy/setup_engineering.py``, which covers all 579 cars via a per-drivetrain prior.
Read-only, cached, never raises.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_PATH = Path(__file__).resolve().parent / "car_weight_distribution.json"
_CACHE: Optional[dict] = None


def _load() -> dict:
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            _CACHE = {}
    return _CACHE


def resolve_front_weight_dist(car_name: str) -> Optional[float]:
    """Front-axle weight fraction (0.0–1.0) for ``car_name``, or None if unknown.

    Returns None for unknown/empty names, missing files, or values outside (0, 1).
    Read-only, cached, never raises.
    """
    if not car_name:
        return None
    val = _load().get(str(car_name))
    if val is None:
        return None
    try:
        f = float(val)
        return f if 0.0 < f < 1.0 else None
    except (TypeError, ValueError):
        return None
