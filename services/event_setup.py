"""Creating and activating an event, headless (single-system stage 3).

The classic Event Planner does this by reading eighteen widgets and calling six mixin
methods. This is the same job as a service: take a described event, validate it, save
it, and make it the one being prepared — with no Qt anywhere.

Deliberately NOT a port of the planner. The rules the driver actually has to state are
few; everything else has a sane default and only matters for some events, so this API
takes an ``EventDraft`` where the regulations are optional and pre-filled.

The write sequence mirrors the classic activation path exactly, because that path is
correct — an event that is saved but whose preparation cycle was never created is an
event the Command Centre cannot see:

  1. save the event                       (SessionDB.upsert_event)
  2. fan out the working-config core      (track / format / event_id / car)
  3. ensure ONE preparation cycle for it  (idempotent by a stable cycle id)
  4. mark it the active event + cycle
  5. persist

Never raises: every entry point returns a result object carrying what happened.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from data.ids import new_id

#: Race formats the app understands. Stored as these exact codes.
RACE_TYPES: Tuple[Tuple[str, str], ...] = (
    ("lap", "A set number of laps"),
    ("timed", "A fixed length of time"),
)

WEATHER_CHOICES: Tuple[str, ...] = (
    "Fixed Dry", "Fixed Wet", "Random Weather", "Light Rain", "Heavy Rain")
DAMAGE_CHOICES: Tuple[str, ...] = ("None", "Light", "Heavy")

#: The regulation defaults. An event that states nothing unusual gets these, and the
#: driver is never asked about them.
DEFAULT_RULES: Dict[str, Any] = {
    "tyre_wear": 1.0,
    "fuel_mult": 1.0,
    "refuel_rate_lps": 10.0,
    "mandatory_stops": 0,
    "bop": False,
    "tuning": True,
    "abs": True,
    "weather": "Fixed Dry",
    "damage": "None",
    "avail_tyres": [],
    "req_tyres": [],
    "allowed_tuning_categories": [],
}


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


def _cycle_id_for(event_name: str) -> str:
    """A stable cycle id per event, so activating twice never makes two cycles."""
    slug = re.sub(r"[^a-z0-9]+", "-", _norm(event_name).lower()).strip("-")
    return f"cycle-{slug}" if slug else ""


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


@dataclass(frozen=True)
class EventDraft:
    """What the driver described. Only the first four fields are ever required."""

    name: str = ""
    car: str = ""
    track: str = ""
    race_type: str = "lap"

    laps: int = 25
    duration_mins: int = 60

    rules: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_RULES))
    notes: str = ""

    def with_(self, **changes) -> "EventDraft":
        known = {k: v for k, v in changes.items() if k in EventDraft.__dataclass_fields__}
        return replace(self, **known) if known else self

    def with_rule(self, key: str, value) -> "EventDraft":
        rules = dict(self.rules)
        rules[_norm(key)] = value
        return replace(self, rules=rules)

    def rule(self, key: str, default=None):
        return self.rules.get(_norm(key), DEFAULT_RULES.get(_norm(key), default))

    @property
    def is_timed(self) -> bool:
        return _norm(self.race_type).lower() == "timed"

    @property
    def has_custom_rules(self) -> bool:
        """Whether anything differs from the standard regulations."""
        for key, default in DEFAULT_RULES.items():
            if self.rules.get(key, default) != default:
                return True
        return False

    def as_event_row(self) -> Dict[str, Any]:
        """The dict ``SessionDB.upsert_event`` expects."""
        row = {
            "name": _norm(self.name), "track": _norm(self.track),
            "race_type": "timed" if self.is_timed else "lap",
            "laps": int(self.laps or 0), "duration_mins": int(self.duration_mins or 0),
            "notes": _norm(self.notes),
        }
        for key, default in DEFAULT_RULES.items():
            row[key] = self.rules.get(key, default)
        return row

    def summary(self) -> str:
        """The event in one plain sentence — the "did I get this right?" check the
        eighteen-field form never gave."""
        length = (f"{int(self.duration_mins)}-minute race" if self.is_timed
                  else f"{int(self.laps)}-lap race")
        who = " ".join(p for p in (_norm(self.car),) if p)
        where = _norm(self.track)
        parts = [f"A {length}"]
        if where:
            parts.append(f"at {where}")
        if who:
            parts.append(f"in the {who}")
        sentence = " ".join(parts) + "."
        extras = self.rule_sentences()
        return sentence + ("  " + "  ".join(extras) if extras else "")

    def rule_sentences(self) -> List[str]:
        """Only the regulations that DIFFER from standard, in plain English."""
        out: List[str] = []
        wear, fuel = self.rule("tyre_wear"), self.rule("fuel_mult")
        if wear and float(wear) != 1.0:
            out.append(f"Tyres wear at {_num(wear)}x.")
        if fuel and float(fuel) != 1.0:
            out.append(f"Fuel burns at {_num(fuel)}x.")
        stops = int(self.rule("mandatory_stops") or 0)
        if stops:
            out.append(f"{stops} mandatory pit stop{'s' if stops != 1 else ''}.")
        if self.rule("bop"):
            out.append("Balance of Performance is on.")
        if not self.rule("tuning"):
            out.append("Tuning is not allowed.")
        if not self.rule("abs"):
            out.append("ABS is not allowed.")
        weather = _norm(self.rule("weather"))
        if weather and weather != DEFAULT_RULES["weather"]:
            out.append(f"Weather: {weather}.")
        damage = _norm(self.rule("damage"))
        if damage and damage != DEFAULT_RULES["damage"]:
            out.append(f"Damage: {damage}.")
        tyres = list(self.rule("avail_tyres") or ())
        if tyres:
            out.append(f"Allowed compounds: {', '.join(str(t) for t in tyres)}.")
        return out


def _num(v) -> str:
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else f"{f:g}"
    except (TypeError, ValueError):
        return str(v)


@dataclass(frozen=True)
class DraftIssue:
    field_name: str
    message: str


def validate(draft: EventDraft) -> Tuple[DraftIssue, ...]:
    """Everything wrong with the draft, each naming its field and how to fix it."""
    issues: List[DraftIssue] = []
    if not _norm(draft.name):
        issues.append(DraftIssue("name", "Give the event a name so you can find it again."))
    if not _norm(draft.car):
        issues.append(DraftIssue("car", "Choose the car you are racing — the setup and "
                                        "strategy are built for it."))
    if not _norm(draft.track):
        issues.append(DraftIssue("track", "Choose the track."))
    if draft.is_timed:
        if int(draft.duration_mins or 0) <= 0:
            issues.append(DraftIssue("duration_mins", "How long is the race, in minutes?"))
    elif int(draft.laps or 0) <= 0:
        issues.append(DraftIssue("laps", "How many laps is the race?"))
    return tuple(issues)


def draft_from_event(evt: Optional[dict], car: str = "") -> EventDraft:
    """Rebuild a draft from a saved event row, for editing."""
    e = dict(evt or {})
    rules = dict(DEFAULT_RULES)
    for key in DEFAULT_RULES:
        if e.get(key) is not None:
            rules[key] = e[key]
    return EventDraft(
        # The EVENT's own car wins; the passed car is only a fallback for an event that
        # has none. The old order (car or e.get("car")) let the current working car
        # override the event's, so switching events kept the current car — the setup,
        # runs and telemetry all stayed tagged to the wrong car.
        name=_norm(e.get("name")), car=_norm(e.get("car") or car),
        track=_norm(e.get("track")),
        race_type="timed" if _norm(e.get("race_type")).lower().startswith("t") else "lap",
        laps=int(e.get("laps") or 25),
        duration_mins=int(e.get("duration_mins", e.get("duration")) or 60),
        rules=rules, notes=_norm(e.get("notes")))


@dataclass(frozen=True)
class SaveResult:
    ok: bool = False
    message: str = ""
    issues: Tuple[DraftIssue, ...] = field(default_factory=tuple)
    event_name: str = ""
    event_id: int = 0
    cycle_id: str = ""


class EventSetupService:
    """Saves and activates events. Owns no widgets."""

    def __init__(self, db=None, config: Optional[dict] = None, persist=None):
        self._db = db
        self._config = config if isinstance(config, dict) else {}
        self._persist = persist          # optional callable to write config to disk

    # ---- reads ------------------------------------------------------------
    def known_events(self) -> List[dict]:
        try:
            return list(self._db.get_all_events() or []) if self._db is not None else []
        except Exception:
            return []

    def active_event_name(self) -> str:
        return _norm(self._config.get("active_event_id"))

    def draft_for(self, event_name: str) -> EventDraft:
        """A draft for an existing event, or a blank one carrying the current car.

        The event's car is stored on its preparation CYCLE (the events table has no car
        column), so we read it from there. Only when the target event has no car of its
        own do we fall back to the current working car — otherwise switching to another
        event kept the current car, tagging its setup/runs/telemetry to the wrong car."""
        name = _norm(event_name)
        strat = self._config.get("strategy") or {}
        if not name:
            return EventDraft(car=_norm(strat.get("car")))
        try:
            row = self._db.get_event(name) if self._db is not None else None
        except Exception:
            row = None
        event_car = ""
        try:
            if self._db is not None and hasattr(self._db, "get_cycle_by_event"):
                eid = int((row or {}).get("id") or (row or {}).get("event_id") or 0)
                cyc = self._db.get_cycle_by_event(eid, name) or {}
                event_car = _norm(cyc.get("car"))
        except Exception:
            event_car = ""
        car = event_car or _norm(strat.get("car"))
        if not row:
            return EventDraft(name=name, car=car)
        return draft_from_event(row, car=car)

    # ---- write ------------------------------------------------------------
    def save_and_activate(self, draft: EventDraft) -> SaveResult:
        """Save the event and make it the one being prepared. Never raises."""
        issues = validate(draft)
        if issues:
            return SaveResult(message="Some details are still needed.", issues=issues)
        if self._db is None or not hasattr(self._db, "upsert_event"):
            return SaveResult(message="No event database available.")

        name = _norm(draft.name)
        try:
            event_id = int(self._db.upsert_event(draft.as_event_row()) or 0)
        except Exception as exc:
            return SaveResult(message=f"Could not save the event: {exc}")

        self._fanout(draft, event_id)
        cycle_id = self._ensure_cycle(draft, event_id)
        self._config["active_event_id"] = name
        if cycle_id:
            self._config["active_cycle_id"] = cycle_id
        self._persist_config()
        return SaveResult(
            ok=True, event_name=name, event_id=event_id, cycle_id=cycle_id,
            message=f"{name} is now the event you are preparing.")

    def complete_active_event(self) -> SaveResult:
        """Finish the active event: mark its cycle complete and clear the active slot.

        The programme ends at the debrief; until now there was no way to close an event
        out, so the last one stayed "active" forever. Completing writes ``explicit_state
        = "complete"`` through the sole sanctioned writer (``upsert_preparation_cycle``),
        which the active-cycle resolver reads as a terminal state and reports NO ACTIVE
        EVENT — so the app cleanly returns to "no event loaded" and the finished cycle is
        never silently reopened.
        """
        name = _norm(self._config.get("active_event_id"))
        cycle_id = _norm(self._config.get("active_cycle_id"))
        if not cycle_id:
            return SaveResult(message="No active event to finish.")
        if self._db is None or not hasattr(self._db, "upsert_preparation_cycle"):
            return SaveResult(message="No event database available.")
        try:
            existing = self._db.get_preparation_cycle(cycle_id) or {}
        except Exception:
            existing = {}
        now = _now_iso()
        try:
            row = dict(existing)
            row.update({
                "cycle_id": cycle_id,
                "explicit_state": "complete",
                "created_at": _norm(existing.get("created_at")) or now,
                "updated_at": now,
            })
            self._db.upsert_preparation_cycle(row)
        except Exception as exc:
            return SaveResult(message=f"Could not finish the event: {exc}")
        # Clear the active slot so the Command Centre shows "no event loaded".
        self._config.pop("active_event_id", None)
        self._config.pop("active_cycle_id", None)
        self._persist_config()
        return SaveResult(
            ok=True, event_name=name, cycle_id=cycle_id,
            message=f"{name} is finished." if name else "Event finished.")

    # ---- internals --------------------------------------------------------
    def _fanout(self, draft: EventDraft, event_id: int) -> None:
        """Write the working-config core: track, format and the car.

        Rules are deliberately NOT duplicated here — every consumer reads them DB-first
        through the canonical contexts, and a second copy is a second thing to go stale.
        """
        try:
            strat = self._config.setdefault("strategy", {})
            strat["track"] = _norm(draft.track)
            strat["car"] = _norm(draft.car)
            strat["race_type"] = "timed" if draft.is_timed else "lap"
            strat["laps"] = int(draft.laps or 0)
            strat["total_laps"] = int(draft.laps or 0)
            strat["race_duration_minutes"] = int(draft.duration_mins or 0)
            strat["event_id"] = int(event_id or 0)
            # Re-derive the canonical track ids from the (new) track name and write them
            # UNCONDITIONALLY. These are the ONLY per-event writer of the ids besides the
            # Track Modelling tab; without this they stayed frozen at whatever that tab
            # last set, so every event's setup build + save inherited a stale layout_id —
            # which mis-directed track shaping AND blocked personal-history recall.
            try:
                from data.track_intelligence import resolve_ids_for_track_name
                loc_id, lay_id = resolve_ids_for_track_name(strat["track"])
                strat["track_location_id"] = loc_id
                strat["layout_id"] = lay_id
            except Exception:
                pass
        except Exception:  # pragma: no cover - defensive
            pass

    def _ensure_cycle(self, draft: EventDraft, event_id: int) -> str:
        """One preparation cycle per event, idempotent.

        An event saved without a cycle is invisible to the Command Centre. A cycle the
        driver explicitly completed or abandoned is NEVER silently reopened.
        """
        if self._db is None or not hasattr(self._db, "upsert_preparation_cycle"):
            return ""
        # Reuse the event's existing cycle if there is one, else mint a fresh UUID.
        # v33 replaced the derivable cycle_id slug with an opaque UUID, so "one cycle
        # per event" is now guaranteed by looking the cycle up by stable event_id
        # (get_cycle_by_event) rather than re-deriving the id from the name.
        existing = {}
        if hasattr(self._db, "get_cycle_by_event"):
            try:
                existing = self._db.get_cycle_by_event(int(event_id or 0), _norm(draft.name)) or {}
            except Exception:
                existing = {}
        cycle_id = _norm(existing.get("cycle_id")) or new_id()
        now = _now_iso()
        # Activating an event is a DELIBERATE choice to prepare it, so a previously
        # completed/abandoned cycle is REOPENED here. This is an explicit user action
        # (save_and_activate is only ever called from the event picker / "Switch to this
        # event"), not the silent/passive reopen the doctrine guards against. Without it,
        # re-selecting a finished event left it "active in config but complete", and its
        # recorded runs stopped registering as evidence (the exact UAT blocker).
        _prev_state = _norm(existing.get("explicit_state"))
        _explicit_state = "" if _prev_state in ("complete", "abandoned") else _prev_state
        try:
            self._db.upsert_preparation_cycle({
                "cycle_id": cycle_id,
                "event_id": int(event_id or 0),
                "event_name": _norm(draft.name),
                "series": _norm(existing.get("series")),
                "round_label": _norm(existing.get("round_label")),
                "car": _norm(draft.car) or _norm(existing.get("car")),
                "track": _norm(draft.track),
                "layout": _norm(existing.get("layout")),
                "official_race_date": _norm(existing.get("official_race_date")),
                "explicit_state": _explicit_state,
                "created_at": _norm(existing.get("created_at")) or now,
                "updated_at": now,
            })
        except Exception:
            return ""
        return cycle_id

    def _persist_config(self) -> None:
        try:
            if callable(self._persist):
                self._persist()
        except Exception:  # pragma: no cover - defensive
            pass
