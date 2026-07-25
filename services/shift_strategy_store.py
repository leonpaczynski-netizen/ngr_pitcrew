"""ShiftStrategyStore — persisted per-scope shift strategy results (Phase 1).

Mirrors SetupHistoryStore exactly: JSON side-file beside the config, lazy
load, atomic tempfile→os.replace save, keyed by scope_key(car, track, layout).

Stores the configuration fingerprint, a computed_at string PASSED IN by the
caller (the store never generates a timestamp), manual_engine_data, the two
profile JSON blobs, and the required_fuel_saving_pct.

No Qt, no DB.  A corrupt file degrades to an empty store rather than crashing.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Mapping, Optional

from services.setup_store import scope_key  # re-exported for callers

SCHEMA = "ngr.shift_strategy.v1"


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


class ShiftStrategyStore:
    """Per-scope shift-strategy data, persisted beside the config."""

    def __init__(self, path: Optional[str] = None):
        self._path = _norm(path)
        self._data: dict = {}       # scope -> dict
        self._loaded = False

    # ---- persistence ---------------------------------------------------------

    def load(self) -> "ShiftStrategyStore":
        """Read the file.  A missing or corrupt file is simply empty."""
        self._loaded = True
        self._data = {}
        if not self._path or not os.path.isfile(self._path):
            return self
        try:
            with open(self._path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            return self
        scopes = (raw or {}).get("scopes") if isinstance(raw, Mapping) else None
        if not isinstance(scopes, Mapping):
            return self
        for scope, entry in scopes.items():
            if isinstance(entry, Mapping):
                self._data[_norm(scope)] = dict(entry)
        return self

    def _save(self) -> bool:
        if not self._path:
            return False
        payload = {"schema": SCHEMA, "scopes": self._data}
        try:
            directory = os.path.dirname(os.path.abspath(self._path)) or "."
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=1, sort_keys=True)
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

    # ---- read ----------------------------------------------------------------

    def get(self, scope: str) -> Optional[dict]:
        """Stored data for a scope, or None if absent."""
        self._ensure_loaded()
        entry = self._data.get(_norm(scope))
        return dict(entry) if isinstance(entry, Mapping) else None

    # ---- write ---------------------------------------------------------------

    def save(self, scope: str, data: dict) -> bool:
        """Persist data for a scope.  Returns False on I/O failure — never raises.

        Expected keys in ``data``:
          fingerprint          — str: ShiftStrategyInputs fingerprint
          computed_at          — str: ISO-8601 timestamp (CALLER must supply this;
                                 the store never generates a timestamp)
          manual_engine_data   — dict: peak_power_rpm / peak_torque_rpm / redline
          qualifying_profile_json — dict: ShiftProfile.to_dict()
          race_profile_json    — dict: ShiftProfile.to_dict()
          required_fuel_saving_pct — float
        """
        self._ensure_loaded()
        self._data[_norm(scope)] = dict(data)
        return self._save()

    def clear(self, scope: str) -> bool:
        """Remove stored data for a scope.  Returns False on I/O failure."""
        self._ensure_loaded()
        self._data.pop(_norm(scope), None)
        return self._save()


def default_shift_strategy_path(config_path: str = "") -> str:
    """Where the shift strategy data lives: beside the config.

    Returns "" when no config_path is provided (no-op path for the store).
    """
    if not _norm(config_path):
        return ""
    return os.path.join(
        os.path.dirname(os.path.abspath(config_path)),
        "shift_strategy.json",
    )
