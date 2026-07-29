"""Curated proven-setup seed library (pure, offline, deterministic).

The from-scratch baseline recalls a vetted complete setup for a car+track and starts
from it instead of generic class defaults — the deterministic equivalent of recalling a
known-good setup, with no AI. Matching is by normalised car name (with aliases) + track
DISPLAY NAME + discipline (qualifying/race), so it is robust to the layout_id plumbing.
The only I/O is loading ``data/proven_setups.json`` once (cached). Never raises.

A matched entry's fields take precedence over the generic class seeds AND over the
driver's personal-history seeds for the fields it specifies — a vetted complete setup is
a better from-scratch start than either. The rule engine still refines it from telemetry.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_LIBRARY_PATH = Path(__file__).resolve().parent.parent / "data" / "proven_setups.json"

# Gearbox fields are authored by the gearbox builder, not the per-field seed loop, so
# they are split out and injected separately.
_GEARBOX_FIELDS = frozenset({
    "final_drive", "gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6",
    "transmission_max_speed_kmh",
})


def _norm(s) -> str:
    # Fold en/em dashes to a plain hyphen so "Watkins Glen International – Grand Prix"
    # matches "... - Grand Prix" regardless of which dash the event name uses.
    t = str(s or "").strip().lower().replace("–", "-").replace("—", "-")
    return " ".join(t.split())


def _discipline(session_type) -> str:
    """Map a session type to the library's discipline key ('' when neither)."""
    s = _norm(session_type)
    if s.startswith("qual"):
        return "qualifying"
    if s.startswith("race"):
        return "race"
    return ""  # practice / unknown → no discipline-specific proven setup


@lru_cache(maxsize=4)
def _load(path_str: str) -> tuple:
    try:
        raw = json.loads(Path(path_str).read_text(encoding="utf-8"))
        setups = raw.get("setups") if isinstance(raw, dict) else None
        return tuple(setups or ())
    except Exception:
        return ()


def load_proven_library(path=None) -> list:
    """All curated entries (list of dicts), or [] if the file is missing/unreadable."""
    return list(_load(str(path or _LIBRARY_PATH)))


def _car_matches(entry: dict, car_n: str) -> bool:
    names = [entry.get("car", "")] + list(entry.get("car_aliases") or [])
    return any(_norm(n) == car_n for n in names)


def _track_matches(entry: dict, track_n: str) -> bool:
    names = [entry.get("track", "")] + list(entry.get("track_aliases") or [])
    return any(_norm(n) == track_n for n in names)


def find_proven_setup(car, track, session_type, *, path=None) -> Optional[dict]:
    """Return a COPY of the matching proven setup's fields, or None.

    Matches normalised car (name or alias) + track (display name or alias) +
    discipline (qualifying/race). Pure; never raises.
    """
    car_n, track_n, disc = _norm(car), _norm(track), _discipline(session_type)
    if not car_n or not track_n or not disc:
        return None
    for entry in _load(str(path or _LIBRARY_PATH)):
        if _discipline(entry.get("discipline")) != disc:
            continue
        if not _track_matches(entry, track_n):
            continue
        if not _car_matches(entry, car_n):
            continue
        return {str(k): v for k, v in (entry.get("fields") or {}).items()}
    return None


def split_seed_and_gearbox(fields) -> tuple:
    """Split a proven fields dict into (non_gearbox_seed, gearbox) for the two
    baseline injection points. Either half may be empty."""
    fields = fields or {}
    seed = {k: v for k, v in fields.items() if k not in _GEARBOX_FIELDS}
    gearbox = {k: v for k, v in fields.items() if k in _GEARBOX_FIELDS}
    return seed, gearbox
