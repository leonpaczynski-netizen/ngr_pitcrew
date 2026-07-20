"""Manual UAT evidence store (Program 2, Phase 71).

A thin persistence wrapper over the pure ``ManualUatLedger``: it loads the append-only evidence ledger from
a JSON file and writes it back ATOMICALLY (shared ``atomic_write_json``) on an EXPLICIT user action only.
It re-implements no ledger logic — precedence/supersession live in the pure domain. It never writes setup
history, never touches config, and never auto-creates a PASS. Defensive: a missing/corrupt file yields an
empty ledger; a write failure is reported to the caller, never silently swallowing evidence loss.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from data.atomic_write import atomic_write_json
from strategy.manual_uat_evidence import ManualUatLedger, ManualUatObservation


class ManualUatStore:
    """Loads / persists a ``ManualUatLedger`` at ``path``. Writes only on ``record`` (explicit user action)."""

    def __init__(self, path):
        self._path = Path(path)
        self._ledger = self._load()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def ledger(self) -> ManualUatLedger:
        return self._ledger

    def _load(self) -> ManualUatLedger:
        try:
            if self._path.exists():
                with open(self._path, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
                return ManualUatLedger.from_payload(payload)
        except Exception:
            # a corrupt file must not crash the app; start from an empty ledger (the file is not deleted).
            pass
        return ManualUatLedger()

    def record(self, observation: ManualUatObservation) -> bool:
        """Append ONE user-entered observation and persist atomically. Returns True on a successful write.
        Explicit user action only; never called from a unit/bench test path."""
        try:
            self._ledger = self._ledger.append(observation)
            atomic_write_json(self._path, self._ledger.to_payload())
            return True
        except Exception:
            return False

    def reload(self) -> ManualUatLedger:
        self._ledger = self._load()
        return self._ledger
