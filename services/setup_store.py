"""SetupSheetStore — who owns the setup values (single-system stage 2).

Right now the answer is "a QDoubleSpinBox". This makes it a file.

The store holds one :class:`SetupSheet` per discipline per scope (car + track +
layout), so switching event never shows another event's numbers, and persists them as
JSON next to the config. It is the last piece of setup state that lived in the classic
form, and moving it is what lets the setup operations become headless.

Deliberately NOT a new source of truth for *applied* setups — ``ActiveSetupAuthority``
already owns what is on the car, and duplicating that would create two answers to the
same question. This store owns the WORKING sheet: what the driver is currently building.

No Qt, no DB. Atomic writes, and a corrupt file degrades to empty sheets rather than
taking the app down.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Dict, Iterable, Mapping, Optional, Tuple

from strategy.setup_sheet import (
    DISCIPLINES, SetupSheet, empty_sheet, normalise_discipline, sheet_from_dict,
)

SCHEMA = "ngr.setup_sheets.v1"


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


def scope_key(car: str = "", track: str = "", layout: str = "") -> str:
    """The scope a sheet belongs to. Case/whitespace-insensitive.

    Layout is part of the key: the same car at the same circuit on a different layout is
    a different setup problem, and silently sharing a sheet across layouts would hand
    the driver numbers built for a different track.
    """
    return "|".join(_norm(p).lower() for p in (car, track, layout))


class SetupSheetStore:
    """The working Race and Qualifying sheets, per scope, persisted."""

    def __init__(self, path: Optional[str] = None):
        self._path = _norm(path)
        self._sheets: Dict[str, Dict[str, SetupSheet]] = {}
        self._loaded = False

    # ---- persistence ------------------------------------------------------
    def load(self) -> "SetupSheetStore":
        """Read the file if there is one. A missing or corrupt file is simply empty."""
        self._loaded = True
        self._sheets = {}
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
        for key, per_discipline in scopes.items():
            if not isinstance(per_discipline, Mapping):
                continue
            bucket: Dict[str, SetupSheet] = {}
            for discipline, values in per_discipline.items():
                d = normalise_discipline(discipline)
                if isinstance(values, Mapping):
                    bucket[d] = sheet_from_dict(values)
            if bucket:
                self._sheets[_norm(key)] = bucket
        return self

    def save(self) -> bool:
        """Write atomically. Returns False rather than raising when it cannot."""
        if not self._path:
            return False
        payload = {
            "schema": SCHEMA,
            "scopes": {
                key: {d: sheet.as_dict() for d, sheet in per.items()}
                for key, per in self._sheets.items() if per
            },
        }
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

    # ---- read -------------------------------------------------------------
    def get(self, scope: str, discipline: str = "race") -> SetupSheet:
        """The working sheet for a scope+discipline. Never None."""
        self._ensure_loaded()
        return self._sheets.get(_norm(scope), {}).get(
            normalise_discipline(discipline), empty_sheet())

    def has_setup(self, scope: str, discipline: str = "race") -> bool:
        """Whether a REAL setup has been authored here (not just defaults)."""
        return self.get(scope, discipline).is_authored

    def scopes(self) -> Tuple[str, ...]:
        self._ensure_loaded()
        return tuple(sorted(self._sheets))

    # ---- write ------------------------------------------------------------
    def set(self, scope: str, discipline: str, sheet, *, persist: bool = True) -> SetupSheet:
        """Replace a sheet. Accepts a SetupSheet or a plain dict."""
        self._ensure_loaded()
        s = sheet if isinstance(sheet, SetupSheet) else sheet_from_dict(sheet)
        self._sheets.setdefault(_norm(scope), {})[normalise_discipline(discipline)] = s
        if persist:
            self.save()
        return s

    def merge(self, scope: str, discipline: str, changes: Optional[Mapping],
              *, persist: bool = True) -> SetupSheet:
        """Apply field changes over the current sheet and store the result."""
        merged = self.get(scope, discipline).merge(changes)
        return self.set(scope, discipline, merged, persist=persist)

    def set_many(self, scope: str, sheets: Mapping, *, persist: bool = True) -> None:
        """Write several disciplines at once — one persist, not one per sheet.

        The initial-setup build authors both sheets together; saving twice would leave a
        window where the file holds a Race sheet from this build and a Qualifying sheet
        from the last one.
        """
        for discipline, sheet in (sheets or {}).items():
            self.set(scope, discipline, sheet, persist=False)
        if persist:
            self.save()

    def clear(self, scope: str = "", *, persist: bool = True) -> None:
        """Forget one scope, or everything when no scope is given."""
        self._ensure_loaded()
        if _norm(scope):
            self._sheets.pop(_norm(scope), None)
        else:
            self._sheets = {}
        if persist:
            self.save()


def default_store_path(config_path: str = "") -> str:
    """Where the sheets live: beside the config, like the active-setup state."""
    if not _norm(config_path):
        return ""
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), "setup_sheets.json")


def disciplines() -> Iterable[str]:
    return DISCIPLINES
