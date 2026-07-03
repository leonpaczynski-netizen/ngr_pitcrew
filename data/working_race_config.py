"""WorkingRaceConfig — the named read model of the race config being worked on.

Added by the **Working Race Config Read Model** sprint (2026-07-04) —
retirement-map item 3, first half (readers; the writers keep their flows).

Why this exists
---------------
Phase 6b's analysis identified that ``config["strategy"]`` carries a distinct
concept the other contexts deliberately do NOT model: the **working race
configuration** — the track/car/race-format the user is currently working
against. It *usually* mirrors the active event (and since Phase 4's re-sync can
never silently drift from it), but during a lap-bank restore
(``_load_session_config``) it deliberately holds a HISTORICAL session's race
config so the derived ``config_id`` (session match key) follows the restored
session. That dual semantics is why the match-key hash could not migrate to the
DB-first EventContext.

This module gives the concept a name and a type. Like every other context, its
builder reads the legacy dict as its **bridge input**; consumers read the model.
It also becomes the single owner of the **match-key algorithm**
(``compute_config_id``), which is frozen by golden vectors in
``tests/test_race_config_id_hash.py`` — a mismatch there means history
re-keying, and the code (not the vectors) must be fixed.

Ownership boundary
------------------
WorkingRaceConfig owns *only* the working race identity/format (track, car,
race type, lengths, the stored config_id). Event truth belongs to EventContext,
plan state to StrategyContext, live-session state to SessionContext.

Purity
------
No PyQt6, no DB, no I/O. ``from_strategy`` never raises.

Byte-identity notes
-------------------
``from_strategy`` reproduces the legacy reads verbatim, including the hash's
own absent-key defaults (``total_laps`` → 25, ``race_duration_minutes`` → 60 —
distinct from EventContext's 0 defaults) and the raw ``race_type`` token
semantics (anything other than exactly ``"timed"`` hashes as a lap race).
One intentional hardening: a non-numeric length value now coerces to the
field's default instead of propagating ``ValueError`` out of the hash (models
never raise; QSpinBox writers make garbage unreachable in practice).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


WORKING_RACE_CONFIG_SCHEMA = "working_race_config_v1"


def _as_str(v, default: str = "") -> str:
    if v is None:
        return default
    try:
        return str(v)
    except Exception:  # pragma: no cover - defensive
        return default


def _as_int(v, default: int) -> int:
    try:
        if v is None or v == "":
            return default
        return int(v)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class WorkingRaceConfig:
    """Immutable snapshot of the race configuration being worked on."""

    track: str = ""
    car: str = ""
    race_type: str = "lap"           # raw token; only exactly "timed" is timed
    total_laps: int = 25             # the hash's own absent-key default
    race_duration_minutes: int = 60  # the hash's own absent-key default
    config_id: str = ""              # the STORED match key (reads); the hash
                                     # recomputes it via compute_config_id()

    @classmethod
    def from_strategy(cls, strategy) -> "WorkingRaceConfig":
        """Build from the legacy ``config["strategy"]`` dict — verbatim reads."""
        strategy = strategy or {}
        return cls(
            track=_as_str(strategy.get("track", "")),
            car=_as_str(strategy.get("car", "")),
            race_type=_as_str(strategy.get("race_type", "lap")) or "lap",
            total_laps=_as_int(strategy.get("total_laps", 25), 25),
            race_duration_minutes=_as_int(strategy.get("race_duration_minutes", 60), 60),
            config_id=_as_str(strategy.get("config_id", "")),
        )

    # -- match-key algorithm (frozen by golden vectors) ---------------------- #
    @property
    def is_timed(self) -> bool:
        return self.race_type == "timed"

    @property
    def length_key(self) -> str:
        """The hash's length token: ``t<minutes>`` for timed, ``l<laps>`` else."""
        return f"t{int(self.race_duration_minutes)}" if self.is_timed \
            else f"l{int(self.total_laps)}"

    @property
    def hash_raw(self) -> str:
        """The exact raw string the match key is derived from."""
        return f"{self.track}|{self.car}|{self.length_key}"

    def compute_config_id(self) -> str:
        """Derive the 10-char session match key. FROZEN — golden vectors in
        tests/test_race_config_id_hash.py; changing this re-keys all history."""
        return hashlib.sha256(self.hash_raw.encode()).hexdigest()[:10]

    # -- display -------------------------------------------------------------- #
    def length_text(self) -> str:
        """The Strategy tab's length detail: ``"30 min"`` / ``"12 laps"``."""
        return f"{int(self.race_duration_minutes)} min" if self.is_timed \
            else f"{int(self.total_laps)} laps"

    def to_dict(self) -> dict:
        return {
            "schema": WORKING_RACE_CONFIG_SCHEMA,
            "track": self.track,
            "car": self.car,
            "race_type": self.race_type,
            "total_laps": self.total_laps,
            "race_duration_minutes": self.race_duration_minutes,
            "config_id": self.config_id,
        }
