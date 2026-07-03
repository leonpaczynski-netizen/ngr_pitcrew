"""EventContext — canonical read model for active event / race configuration.

Added by the **State Consolidation 1 — EventContext** sprint (2026-07-03) as the
first concrete step of the target architecture proposed in
`docs/PRODUCT_CONSOLIDATION_AUDIT.md`.

Why this exists
---------------
The worst single-source-of-truth violation in the app is that "Set as Active"
fans the selected event into ``config["strategy"]`` — a god-object snapshot that
can drift from the durable DB event record. The two representations even use
different field names:

    concept              DB event record        config["strategy"]
    -------------------  ---------------------  ----------------------
    tyre wear multiplier tyre_wear              tyre_wear_multiplier
    race duration (min)  duration_mins          race_duration_minutes
    refuel rate          refuel_rate_lps        refuel_speed_lps
    required tyres       req_tyres              required_tyres
    car                  (not stored)           car
    track ids            (not stored)           track_location_id, layout_id

``EventContext`` normalises **both** shapes into one immutable, validated read
model with stable field names, so downstream consumers stop reaching into
``config["strategy"]`` directly.

Ownership boundary
------------------
EventContext owns *only* event/race configuration truth. It must **not** own
telemetry, lap validity, reference paths / station maps, setup diagnosis,
strategy calculations, AI logs, or learning history (see the audit §7).

Purity
------
No PyQt6, no DB, no I/O — builders take plain dicts (a DB event record and/or the
legacy strategy dict). This keeps the module unit-testable without a QApplication
(the project's test convention) and free of import cycles. ``config["strategy"]``
is intentionally *not* deleted this sprint; it remains as legacy compatibility.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional, Tuple


EVENT_CONTEXT_SCHEMA = "event_context_v1"


class EventContextSource(str, Enum):
    """Where an EventContext was resolved from."""
    EMPTY = "empty"                    # no active event at all
    DB_EVENT = "db_event"              # only a DB event record was available
    LEGACY_STRATEGY = "legacy_strategy"  # only config["strategy"] was available
    MERGED = "merged"                  # DB event record + strategy overlay


# --------------------------------------------------------------------------- #
# Safe coercion helpers (never raise)
# --------------------------------------------------------------------------- #
def _as_str(v, default: str = "") -> str:
    if v is None:
        return default
    try:
        return str(v)
    except Exception:  # pragma: no cover - defensive
        return default


def _as_int(v, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def _as_float(v, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _as_bool(v, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    try:
        return bool(v)
    except Exception:  # pragma: no cover - defensive
        return default


def _as_str_tuple(v) -> Tuple[str, ...]:
    if v is None:
        return ()
    if isinstance(v, (list, tuple)):
        return tuple(_as_str(x) for x in v if _as_str(x))
    if isinstance(v, str):
        # Comma-separated fallback (e.g. mandatory_compounds strings).
        return tuple(p.strip() for p in v.split(",") if p.strip())
    return ()


def _norm_race_type(v) -> str:
    """Normalise any race-type token to exactly 'lap' or 'timed'."""
    s = _as_str(v).strip().lower()
    return "timed" if "timed" in s else "lap"


def _present(*dicts_and_keys) -> bool:
    """True if any (dict, key) pair has a non-None value for key."""
    for d, k in dicts_and_keys:
        if d and d.get(k) is not None:
            return True
    return False


# --------------------------------------------------------------------------- #
# The read model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EventContext:
    """Immutable, normalised snapshot of the active event / race configuration."""

    # Identity
    event_id: Optional[int]
    event_name: str

    # Selections
    car: str
    track: str
    track_location_id: str
    layout_id: str

    # Race format
    race_type: str                # 'lap' | 'timed'
    laps: int
    race_duration_minutes: int

    # Multipliers / pit
    tyre_wear_multiplier: float
    fuel_multiplier: float
    refuel_rate_lps: float
    mandatory_stops: int

    # Rules / legality
    bop_enabled: bool
    tuning_allowed: bool
    allowed_tuning_categories: Tuple[str, ...]

    # Tyres
    available_tyres: Tuple[str, ...]
    required_tyres: Tuple[str, ...]

    # Conditions
    weather: str
    damage: str

    # Provenance / change marker
    source: EventContextSource = EventContextSource.EMPTY
    change_hash: str = ""

    # -- convenience ------------------------------------------------------- #
    @property
    def is_timed(self) -> bool:
        return self.race_type == "timed"

    @property
    def is_lap_race(self) -> bool:
        return self.race_type == "lap"

    @property
    def has_active_event(self) -> bool:
        return self.source != EventContextSource.EMPTY

    @property
    def tuning_locked(self) -> bool:
        return not self.tuning_allowed

    def race_length_text(self) -> str:
        if self.is_timed:
            return f"{self.race_duration_minutes} minutes, Timed Race"
        lap_word = "lap" if self.laps == 1 else "laps"
        return f"{self.laps} {lap_word}, Lap Race"

    def summary_line(self) -> str:
        """One-line human summary for a status label."""
        car = self.car or "—"
        track = self.track or "—"
        name = self.event_name or "(no event)"
        return (
            f"Event: {name}  |  Track: {track}  |  Car: {car}  |  "
            f"{self.race_length_text()}  |  Wear: {self.tyre_wear_multiplier:g}×  |  "
            f"Fuel: {self.fuel_multiplier:g}×  |  "
            f"BoP: {'ON' if self.bop_enabled else 'OFF'}  |  "
            f"Tuning: {'Allowed' if self.tuning_allowed else 'Locked'}"
        )

    def to_summary_lines(self) -> list:
        """Multi-line summary suitable for a small overview panel."""
        lines = [
            f"Event: {self.event_name or '(none)'}",
            f"Car: {self.car or '—'}",
            f"Track: {self.track or '—'}",
            f"Race: {self.race_length_text()}",
            f"Tyre wear: {self.tyre_wear_multiplier:g}×   Fuel: {self.fuel_multiplier:g}×",
            f"BoP: {'ON' if self.bop_enabled else 'OFF'}   "
            f"Tuning: {'Allowed' if self.tuning_allowed else 'Locked'}",
        ]
        if self.required_tyres:
            lines.append(f"Required tyres: {', '.join(self.required_tyres)}")
        return lines

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source"] = self.source.value
        d["allowed_tuning_categories"] = list(self.allowed_tuning_categories)
        d["available_tyres"] = list(self.available_tyres)
        d["required_tyres"] = list(self.required_tyres)
        d["schema"] = EVENT_CONTEXT_SCHEMA
        return d


@dataclass(frozen=True)
class EventContextValidationResult:
    ok: bool
    warnings: Tuple[str, ...] = ()
    missing_fields: Tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# Builder / adapter
# --------------------------------------------------------------------------- #
def _canonical_change_fields(**kw) -> dict:
    """The subset of fields that define whether the event 'changed'. Excludes
    provenance (source) and the hash itself."""
    return {
        "event_id": kw["event_id"],
        "event_name": kw["event_name"],
        "car": kw["car"],
        "track": kw["track"],
        "track_location_id": kw["track_location_id"],
        "layout_id": kw["layout_id"],
        "race_type": kw["race_type"],
        "laps": kw["laps"],
        "race_duration_minutes": kw["race_duration_minutes"],
        "tyre_wear_multiplier": kw["tyre_wear_multiplier"],
        "fuel_multiplier": kw["fuel_multiplier"],
        "refuel_rate_lps": kw["refuel_rate_lps"],
        "mandatory_stops": kw["mandatory_stops"],
        "bop_enabled": kw["bop_enabled"],
        "tuning_allowed": kw["tuning_allowed"],
        "allowed_tuning_categories": list(kw["allowed_tuning_categories"]),
        "available_tyres": list(kw["available_tyres"]),
        "required_tyres": list(kw["required_tyres"]),
        "weather": kw["weather"],
        "damage": kw["damage"],
    }


def compute_change_hash(fields: dict) -> str:
    """Stable 12-char hash over the canonical event fields — a change marker so
    consumers can cheaply detect that the event configuration changed and
    invalidate any derived snapshot. Deterministic (no time / randomness)."""
    blob = json.dumps(fields, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def build_event_context(
    *,
    event: Optional[dict] = None,
    strategy: Optional[dict] = None,
    active_event_id=None,
) -> EventContext:
    """Build the canonical EventContext from the current app state.

    Parameters
    ----------
    event : dict | None
        A DB event record (as returned by ``SessionDB.get_event``). This is the
        durable, editable truth for race rules; preferred when present so that
        editing the event and rebuilding EventContext never returns stale values.
    strategy : dict | None
        The legacy ``config["strategy"]`` dict. Supplies fields the events table
        does not store (car, track_location_id, layout_id) and acts as a fallback
        when no DB event record is available.
    active_event_id
        ``config["active_event_id"]`` — used only to fill the event name when the
        DB record is absent.

    Never raises. Returns an EMPTY-source context when nothing is available.
    """
    event = event or {}
    strategy = strategy or {}

    has_event = bool(event)
    has_strategy = bool(strategy)

    if has_event and has_strategy:
        source = EventContextSource.MERGED
    elif has_event:
        source = EventContextSource.DB_EVENT
    elif has_strategy:
        source = EventContextSource.LEGACY_STRATEGY
    else:
        source = EventContextSource.EMPTY

    # Resolution rule: prefer the durable DB event record for race-rule fields
    # (so edits are never masked by a stale strategy snapshot); take car + track
    # ids from the strategy dict (the events table does not store them); fall
    # back to strategy when the DB record is absent.
    def pick(evt_key, strat_key, default, cast):
        # cast(value, default) so malformed values coerce to the sensible field
        # default (e.g. a non-numeric tyre_wear falls back to 1.0, not 0.0).
        if has_event and event.get(evt_key) is not None:
            return cast(event.get(evt_key), default)
        if has_strategy and strategy.get(strat_key) is not None:
            return cast(strategy.get(strat_key), default)
        return default

    event_id_raw = event.get("id") if has_event else strategy.get("event_id")
    event_id = _as_int(event_id_raw) if event_id_raw not in (None, "") else None

    event_name = _as_str(event.get("name")) or _as_str(active_event_id)

    # car / track ids live only in the strategy snapshot today
    car = _as_str(strategy.get("car")) or _as_str(event.get("car"))
    track_location_id = _as_str(strategy.get("track_location_id")) or _as_str(event.get("track_location_id"))
    layout_id = _as_str(strategy.get("layout_id")) or _as_str(event.get("layout_id"))

    track = pick("track", "track", "", _as_str)
    race_type = _norm_race_type(
        event.get("race_type") if has_event and event.get("race_type") is not None
        else strategy.get("race_type")
    )
    laps = pick("laps", "total_laps", 0, _as_int)
    if laps == 0:
        laps = _as_int(strategy.get("laps"), 0)
    race_duration_minutes = pick("duration_mins", "race_duration_minutes", 0, _as_int)
    tyre_wear_multiplier = pick("tyre_wear", "tyre_wear_multiplier", 1.0, _as_float)
    fuel_multiplier = pick("fuel_mult", "fuel_mult", 1.0, _as_float)
    refuel_rate_lps = pick("refuel_rate_lps", "refuel_speed_lps", 0.0, _as_float)
    mandatory_stops = pick("mandatory_stops", "mandatory_stops", 0, _as_int)

    bop_enabled = (
        _as_bool(event.get("bop")) if (has_event and _present((event, "bop")))
        else _as_bool(strategy.get("bop"))
    )
    tuning_allowed = (
        _as_bool(event.get("tuning"), True) if (has_event and _present((event, "tuning")))
        else _as_bool(strategy.get("tuning"), True)
    )
    allowed_tuning_categories = _as_str_tuple(
        event.get("allowed_tuning_categories") if has_event and event.get("allowed_tuning_categories") is not None
        else strategy.get("allowed_tuning_categories")
    )
    available_tyres = _as_str_tuple(
        event.get("avail_tyres") if has_event and event.get("avail_tyres") is not None
        else strategy.get("avail_tyres")
    )
    required_tyres = _as_str_tuple(
        event.get("req_tyres") if has_event and event.get("req_tyres") is not None
        else strategy.get("required_tyres")
    )
    weather = pick("weather", "weather", "", _as_str)
    damage = pick("damage", "damage", "", _as_str)

    canonical = _canonical_change_fields(
        event_id=event_id, event_name=event_name, car=car, track=track,
        track_location_id=track_location_id, layout_id=layout_id,
        race_type=race_type, laps=laps, race_duration_minutes=race_duration_minutes,
        tyre_wear_multiplier=tyre_wear_multiplier, fuel_multiplier=fuel_multiplier,
        refuel_rate_lps=refuel_rate_lps, mandatory_stops=mandatory_stops,
        bop_enabled=bop_enabled, tuning_allowed=tuning_allowed,
        allowed_tuning_categories=allowed_tuning_categories,
        available_tyres=available_tyres, required_tyres=required_tyres,
        weather=weather, damage=damage,
    )
    change_hash = "" if source == EventContextSource.EMPTY else compute_change_hash(canonical)

    return EventContext(
        event_id=event_id,
        event_name=event_name,
        car=car,
        track=track,
        track_location_id=track_location_id,
        layout_id=layout_id,
        race_type=race_type,
        laps=laps,
        race_duration_minutes=race_duration_minutes,
        tyre_wear_multiplier=tyre_wear_multiplier,
        fuel_multiplier=fuel_multiplier,
        refuel_rate_lps=refuel_rate_lps,
        mandatory_stops=mandatory_stops,
        bop_enabled=bop_enabled,
        tuning_allowed=tuning_allowed,
        allowed_tuning_categories=allowed_tuning_categories,
        available_tyres=available_tyres,
        required_tyres=required_tyres,
        weather=weather,
        damage=damage,
        source=source,
        change_hash=change_hash,
    )


def empty_event_context() -> EventContext:
    """A well-formed EMPTY context (no active event)."""
    return build_event_context()


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate_event_context(ctx: EventContext) -> EventContextValidationResult:
    """Return non-crashing validation warnings for optional/missing fields.

    Missing optional fields produce warnings, never exceptions — callers decide
    whether to block. An EMPTY context is reported as "no active event".
    """
    warnings = []
    missing = []

    if ctx.source == EventContextSource.EMPTY:
        return EventContextValidationResult(
            ok=False, warnings=("No active event — set one in Event Planner.",),
            missing_fields=("event",),
        )

    if not ctx.car:
        warnings.append("No car selected — select one in the Garage.")
        missing.append("car")
    if not ctx.track:
        warnings.append("No track selected — set one in Event Planner.")
        missing.append("track")
    if ctx.is_timed and ctx.race_duration_minutes <= 0:
        warnings.append("Timed race has no duration set.")
        missing.append("race_duration_minutes")
    if ctx.is_lap_race and ctx.laps <= 0:
        warnings.append("Lap race has no lap count set.")
        missing.append("laps")
    if ctx.tuning_locked and ctx.allowed_tuning_categories:
        warnings.append(
            "Tuning is locked but allowed setup categories are listed — "
            "the lock takes precedence."
        )
    if not ctx.available_tyres:
        warnings.append("No available tyre compounds set for this event.")
        missing.append("available_tyres")

    return EventContextValidationResult(
        ok=not warnings,
        warnings=tuple(warnings),
        missing_fields=tuple(missing),
    )


# --------------------------------------------------------------------------- #
# Bridge to ui/product_flow.py (home / next-action surface)
# --------------------------------------------------------------------------- #
def flow_flags(ctx: EventContext) -> dict:
    """Derive the boolean flags ``ui.product_flow.build_flow_state_summary``
    expects from an EventContext. Lets a future home/overview panel drive the
    'suggested next action' from real event state.

    Returns only the event-derived flags; the caller merges in the
    telemetry/setup/strategy flags it owns.
    """
    return {
        "has_event": ctx.has_active_event,
        "has_car": bool(ctx.car),
        "has_track": bool(ctx.track),
        "tuning_confirmed": ctx.has_active_event,
    }
