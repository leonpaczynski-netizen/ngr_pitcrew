"""Drivetrain resolver — reads the curated ``car_drivetrains.json`` data file.

``car_specs.json`` carries no drivetrain, so this is the single place the rest of the
app resolves a car's drivetrain (FF/FR/MR/RR/4WD). The JSON is the correctable source
of truth (generated + hand-curated by data/car_drivetrain_inference.py). A car not in
the file resolves to "" — callers then fall back to their existing neutral behaviour,
never a wrong guess. Read-only, cached, never raises.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_PATH = Path(__file__).resolve().parent / "car_drivetrains.json"
_CACHE: Optional[dict] = None


def _load() -> dict:
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            _CACHE = {}
    return _CACHE


def resolve_drivetrain(car_name: str) -> str:
    """Drivetrain code (FF/FR/MR/RR/4WD) for ``car_name``, or "" if unknown."""
    if not car_name:
        return ""
    return str(_load().get(str(car_name), "") or "")
