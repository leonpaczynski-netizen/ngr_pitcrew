"""CarWeightDistStore — user-saved front weight-distribution overlay (garage save).

The curated seed (``data/car_weight_distribution.json``) is git-tracked and never
written by the user.  When the driver saves a front-weight-distribution % in the
Garage, it lands in a WRITABLE OVERLAY beside ``config.json``.  The resolver
(``data/car_weight_distribution``) merges OVERLAY-ON-TOP-OF-SEED so the user's
value takes effect immediately — no restart required.

No Qt, no DB.  Atomic writes; a corrupt or missing file degrades to an empty
overlay rather than taking the app down (same contract as every other store in
services/).
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Dict, Optional


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


class CarWeightDistStore:
    """Persisted user overlay of car front weight-distribution fractions.

    Values are fractions in the OPEN interval (0, 1) — same convention as the
    seed file ``data/car_weight_distribution.json``.  The flat JSON format is::

        {
         "Porsche 911 RSR (991) '17": 0.38,
         "Toyota AE86 Levin D-Tuned": 0.55
        }
    """

    def __init__(self, path: str = ""):
        self._path = _norm(path)
        self._data: Dict[str, float] = {}
        self._loaded = False

    # ---- persistence -------------------------------------------------------

    def load(self) -> "CarWeightDistStore":
        """Read the overlay file.  Missing or corrupt file → empty dict, never raises."""
        self._loaded = True
        self._data = {}
        if not self._path or not os.path.isfile(self._path):
            return self
        try:
            with open(self._path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            return self
        if not isinstance(raw, dict):
            return self
        for k, v in raw.items():
            try:
                f = float(v)
                if 0.0 < f < 1.0:
                    self._data[str(k)] = f
            except (TypeError, ValueError):
                pass
        return self

    def _save(self) -> bool:
        if not self._path:
            return False
        try:
            directory = os.path.dirname(os.path.abspath(self._path)) or "."
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(self._data, fh, indent=1, sort_keys=True)
                os.replace(tmp, self._path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except Exception:
            return False
        return True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ---- write -------------------------------------------------------------

    def set(self, car_name: str, frac: float) -> bool:
        """Store a front-weight fraction for a car.

        ``frac`` must be in the open interval (0, 1) — boundary values are
        physically meaningless and rejected (returns False).  An empty path
        keeps the value in memory and returns True without writing anything.
        """
        self._ensure_loaded()
        try:
            f = float(frac)
        except (TypeError, ValueError):
            return False
        if not (0.0 < f < 1.0):
            return False
        self._data[str(car_name)] = f
        if not self._path:
            return True  # in-memory only; no file to write
        return self._save()

    def remove(self, car_name: str) -> bool:
        """Delete a car's override.  Returns True if the entry existed and was removed."""
        self._ensure_loaded()
        key = str(car_name)
        if key not in self._data:
            return False
        del self._data[key]
        if not self._path:
            return True
        return self._save()

    # ---- read --------------------------------------------------------------

    def overlay(self) -> Dict[str, float]:
        """A copy of the current ``{car_name: fraction}`` map."""
        self._ensure_loaded()
        return dict(self._data)


def default_car_weight_dist_path(config_path: str = "") -> str:
    """Where the user overlay lives: beside config.json, never in the repo.

    Returns ``""`` when ``config_path`` is empty/blank — the store then operates
    in-memory only and persists nothing.  Mirror of ``default_history_path`` and
    ``default_store_path`` in the services layer.
    """
    if not _norm(config_path):
        return ""
    return os.path.join(
        os.path.dirname(os.path.abspath(config_path)),
        "car_weight_distribution.user.json",
    )
