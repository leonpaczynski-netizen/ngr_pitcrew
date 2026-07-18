"""Persistence store for the canonical active applied setup (UAT Finding 1).

Backs ``data.setup_state_authority.ActiveSetupAuthority`` so the last confirmed
active setup restores after a restart. Deliberately a small, atomic JSON file
(matching the project's other JSON stores) rather than a new DB schema
migration — additive and low-risk.

The path is injectable so tests write to a temp file and never pollute the repo.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import List


_DEFAULT_PATH = Path(__file__).resolve().parent / "active_setup_state.json"


class JsonActiveSetupStore:
    """Load/save the list of active-setup records to a JSON file, atomically."""

    def __init__(self, path: str | os.PathLike | None = None):
        self._path = Path(path) if path is not None else _DEFAULT_PATH

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> List[dict]:
        try:
            if not self._path.exists():
                return []
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if isinstance(data, dict):
            data = data.get("active_setups", [])
        if not isinstance(data, list):
            return []
        return [r for r in data if isinstance(r, dict)]

    def save(self, records: List[dict]) -> None:
        payload = {"version": 1, "active_setups": list(records or [])}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write: temp file in the same dir + os.replace.
            fd, tmp = tempfile.mkstemp(
                dir=str(self._path.parent), prefix=".active_setup_", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, sort_keys=True)
                os.replace(tmp, self._path)
            finally:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
        except Exception:
            # Persistence failure must never break the UI action that triggered it.
            pass


class InMemoryActiveSetupStore:
    """A store that keeps records in memory — used by tests."""

    def __init__(self, records: List[dict] | None = None):
        self._records: List[dict] = list(records or [])

    def load(self) -> List[dict]:
        return [dict(r) for r in self._records]

    def save(self, records: List[dict]) -> None:
        self._records = [dict(r) for r in (records or [])]
