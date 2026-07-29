"""Front weight-distribution resolver — reads the curated ``car_weight_distribution.json`` data file.

Per-car front-axle weight fraction (0.0–1.0). A car not in the file resolves to None —
callers then fall back to the drivetrain-keyed ``_WEIGHT_DIST_PRIOR`` in
``strategy/setup_engineering.py``, which covers all 579 cars via a per-drivetrain prior.

Overlay support: a user-saved overlay (``car_weight_distribution.user.json`` beside
``config.json``) is merged ON TOP of the seed at load time so user-saved values win.
The overlay path is injected once at startup via ``set_overlay_path()``.  Call
``invalidate()`` to force a re-read (e.g. after ``CarWeightDistStore.set()``).

Read-only from callers' perspective, cached, never raises.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_PATH = Path(__file__).resolve().parent / "car_weight_distribution.json"
_CACHE: Optional[dict] = None
_OVERLAY_PATH: Optional[str] = None


def set_overlay_path(path: str) -> None:
    """Register the user-overlay file path and invalidate the cache.

    Call once at startup (bridge ``__init__``) so subsequent resolves merge the
    overlay on top of the seed.  An empty string disables overlay reads.
    """
    global _OVERLAY_PATH
    _OVERLAY_PATH = str(path).strip() if path else ""
    invalidate()


def invalidate() -> None:
    """Clear the merged cache so the next resolve re-reads seed + overlay."""
    global _CACHE
    _CACHE = None


def _load() -> dict:
    global _CACHE
    if _CACHE is None:
        # 1. Load the git-tracked seed
        try:
            seed: dict = json.loads(_PATH.read_text(encoding="utf-8"))
            if not isinstance(seed, dict):
                seed = {}
        except Exception:
            seed = {}

        # 2. Merge user overlay on top (overlay wins).
        #    Missing or corrupt overlay → ignore silently; never raise.
        overlay: dict = {}
        if _OVERLAY_PATH:
            try:
                raw = Path(_OVERLAY_PATH).read_text(encoding="utf-8")
                candidate = json.loads(raw)
                if isinstance(candidate, dict):
                    overlay = candidate
            except Exception:
                pass

        _CACHE = {**seed, **overlay}
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
