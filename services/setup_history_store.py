"""SetupHistoryStore — the persisted history of applied setup revisions (UAT-7).

The ``ActiveSetupAuthority`` mints a revision every time a setup is confirmed applied,
but it keeps only the CURRENT one — so the Garage's Lineage tab was blank and there was
no way to load a setup the driver had run before ("no way to load previous settings to
activate that's the settings I'm running in GT7").

This records each applied revision as it happens, per scope (car+track+layout) and
discipline, so the lineage can show rev1 → rev2 → … and any past revision can be loaded
back onto the sheet. It stores the TUNE snapshot the authority made active — not the
beep preference, which is not part of a setup's identity.

No Qt, no DB. Atomic writes; a corrupt file degrades to empty rather than taking the
app down (same contract as ``SetupSheetStore``).
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Dict, List, Mapping, Optional

from strategy.setup_sheet import normalise_discipline
from services.setup_store import scope_key  # re-exported for callers

SCHEMA = "ngr.setup_revisions.v1"


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


class SetupHistoryStore:
    """Applied-setup revisions per (scope, discipline), oldest first, persisted."""

    def __init__(self, path: Optional[str] = None):
        self._path = _norm(path)
        # scope -> discipline -> [revision dict]
        self._revs: Dict[str, Dict[str, List[dict]]] = {}
        self._loaded = False

    # ---- persistence ------------------------------------------------------
    def load(self) -> "SetupHistoryStore":
        self._loaded = True
        self._revs = {}
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
        for scope, per_disc in scopes.items():
            if not isinstance(per_disc, Mapping):
                continue
            bucket: Dict[str, List[dict]] = {}
            for disc, revs in per_disc.items():
                if isinstance(revs, list):
                    bucket[normalise_discipline(disc)] = [
                        dict(r) for r in revs if isinstance(r, Mapping)]
            if bucket:
                self._revs[_norm(scope)] = bucket
        return self

    def _save(self) -> bool:
        if not self._path:
            return False
        payload = {"schema": SCHEMA, "scopes": self._revs}
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

    # ---- write ------------------------------------------------------------
    def record(self, scope: str, discipline: str, *, revision: int, label: str,
               fields: Mapping, applied_at: str = "") -> bool:
        """Append a revision. Idempotent: re-recording the same revision number for a
        scope+discipline updates it in place rather than duplicating (re-confirming an
        unchanged setup must not grow the lineage)."""
        self._ensure_loaded()
        d = normalise_discipline(discipline)
        rev = int(revision or 0)
        if rev <= 0:
            return False
        entry = {"revision": rev, "label": _norm(label) or f"Setup rev {rev}",
                 "fields": dict(fields or {}), "applied_at": _norm(applied_at)}
        bucket = self._revs.setdefault(_norm(scope), {}).setdefault(d, [])
        for i, r in enumerate(bucket):
            if int(r.get("revision") or 0) == rev:
                bucket[i] = entry
                return self._save()
        bucket.append(entry)
        bucket.sort(key=lambda r: int(r.get("revision") or 0))
        return self._save()

    # ---- read -------------------------------------------------------------
    def revisions(self, scope: str, discipline: str = "race") -> List[dict]:
        """Every recorded revision for a scope+discipline, oldest first."""
        self._ensure_loaded()
        d = normalise_discipline(discipline)
        return list(self._revs.get(_norm(scope), {}).get(d, []))

    def snapshot(self, scope: str, discipline: str, revision: int) -> Optional[dict]:
        """The tune fields of one revision, or None if it isn't recorded."""
        rev = int(revision or 0)
        for r in self.revisions(scope, discipline):
            if int(r.get("revision") or 0) == rev:
                return dict(r.get("fields") or {})
        return None


def default_history_path(config_path: str = "") -> str:
    """Where the revisions live: beside the config, like the working sheets."""
    if not _norm(config_path):
        return ""
    return os.path.join(os.path.dirname(os.path.abspath(config_path)),
                        "setup_revisions.json")
