"""Every circuit's straights model, kept current from the laps he drives.

**The driver, 15 Sep 2026: "Map all known and future circuits."** Until then a
model existed only where someone ran `tools/derive_straights.py --apply` for
one circuit. This is the part that decides, from the database alone, whether a
circuit's model should be derived, re-derived or left alone - for the tool's
`--all` and for the app when a session closes (`refresh_after_session`).

**Nothing here is held between calls** (rule 11). Every decision is read off
the stored laps and the stored model at the moment it is made, so a session
closing at Suzuka cannot be judged against anything left over from the last
one at Monza.

### When a model is derived - `plan`

1. **No model, and at least `MIN_LAPS` clean laps on file.** With fewer - a
   circuit selected for the first time, or one practice lap - it says so in
   the log and derives nothing.
2. **A model, and the clean laps recorded since it was derived reach `GROWTH`
   of the laps it pooled.** "Since" is the clean laps on file now minus
   `laps_available`, the count on file when the model was derived; a model
   written before that field existed counts from its own pooled laps.
3. **A model, and the circuit's latest clean laps no longer integrate to its
   axis** - see "Axis" below.

**Why 25%, and why of the laps pooled.** The pool is capped at `MAX_LAPS`
(the most recent 80), so on Monza's 218 clean laps "25% more laps on file"
would wait for 55 new ones - two thirds of the pool replaced before the model
noticed - and "25% more than the 80 pooled" would fire at every close forever.
Counted as new laps against the pool, a refresh waits for 3 new laps on a
10-lap model, 10 on 40 and 20 on a full 80: a quarter of the evidence
replaced. Refreshing sooner buys nothing measurable on the model's accuracy -
from 10 laps up no gated model stored an end past the full pool's by more than
the live fit margin, and the phantom-window rate is flat from 15 laps to 25
(`analysis/straights.MIN_LAPS`). What a refresh buys is recency: at 25% the
stored model never lags the latest laps by more than a quarter of its own
pool, for one derivation every one or two sessions at a circuit he is
practising - each 1-17 s of a background thread on the thirteen circuits on
file, timed twice on 15 Sep 2026 (Monza's 80 laps the slowest).

### Never a worse model - `compare`

A derived model replaces the stored one unless it:

* **pools fewer laps**, or
* **loses a stored window** - one the stored model holds, with nothing
  overlapping it in the new model, because it failed today's gates or is no
  longer on most laps.

**Rule 10: each refusal can retire its own baseline.** The stored model is no
baseline, and any model that passes the gates replaces it, when:

* it fails today's gates itself (written before them, or by hand);
* the axis moved (it no longer describes the road the ruler measures);
* none of its sessions is in the new pool - the evidence is entirely new;
* for a lost window only: the new model pools at least `RETIRE_RATIO` times
  its laps - twice the evidence says that straight is not a place.

`tools/derive_straights.py --replace` is the driver's override. Accepts are
logged as well as refusals, with the counts that decided them.

### Axis

**Before 15 Sep 2026 nothing invalidated a straights model.** The corner model
has one guard (`resolve.resolve_corner_model` supersedes a model whose lap
length is off by more than 50 m). The straights model had only the live one:
`race/straight.StraightsModel.remaining_s` returns None - the unmodelled
fallback - when the ruler's last lap is more than 2% off the model's axis. That
stops a stale model being used; it never replaced it.

Now: the median integrated length of the circuit's latest
`RECENT_AXIS_LAPS` clean laps is compared with the model's `lap_length_m` at
every session close, and more than `derivation.LAP_LENGTH_TOLERANCE` (2%, the
same tolerance the live lookup refuses at and the derivation pools by) is an
axis change: the model is re-derived from the laps on the new axis only, and
until `MIN_LAPS` of them exist the stored model stays - refused live by the
same 2% - and the log says how many there are. A change inside 2% needs
nothing: every lap is scaled onto the axis by its own length, live and in the
derivation. **A move of the start line with the length unchanged is not
detectable by length and is not handled.**
"""
from __future__ import annotations

import datetime
import json
import math
import sqlite3
import statistics
import threading
import time
from dataclasses import dataclass
from typing import Callable

from pitcrew.analysis import straights as derivation
from pitcrew.analysis.distance import teleports
from pitcrew.analysis.resolve import circuit_key
from pitcrew.diagnostics import log

# The most recent laps a model pools. Recent is what matters - the car and the
# physics version he races now - and it bounds memory: 80 Monza laps are about
# 540,000 frames.
MAX_LAPS = 80
# Rows read to find them: the selection refuses 0-27% of a circuit's clean laps
# (teleports, wrong lengths, slow laps), so twice the pool is enough.
LOAD_LIMIT = 2 * MAX_LAPS
MIN_LAPS = derivation.MIN_LAPS
GROWTH = 0.25
RETIRE_RATIO = 2.0
# A median over ten laps resists four broken ones, and ten is one session.
RECENT_AXIS_LAPS = 10
MIN_AXIS_LAPS = 5

Query = Callable[[str, tuple], list]

_LOG = "straights"

_CLEAN = (
    "FROM laps l JOIN lap_frames f ON f.lap_id = l.id "
    "JOIN sessions s ON s.id = l.session_id "
    "WHERE s.event_id IN ({marks}) AND l.excluded = 0 "
    "  AND l.is_pit_lap = 0 AND l.is_out_lap = 0 AND l.lap_time_ms > 0 "
    "  AND NOT (s.kind = 'race' AND l.lap_num = 1)")

# The five channels a derivation reads. Position is read at load to find
# teleports and then dropped.
_KEEP = ("throttle_pct", "brake_pct", "lat_g", "speed_kph", "lap_distance_m")
_INDEX = {name: index for index, name in enumerate(_KEEP)}


class Frame(tuple):
    """One stored frame as a tuple of `_KEEP`, read like the dict it replaces.

    **A dict per frame held 267 MB for Monza's 80 laps** (tracemalloc, 15 Sep
    2026) - too much for a thread running inside the app at a session close.
    """
    __slots__ = ()

    def get(self, key, default=None):
        index = _INDEX.get(key)
        return default if index is None else tuple.__getitem__(self, index)

    def __getitem__(self, key):
        if isinstance(key, str):
            return tuple.__getitem__(self, _INDEX[key])
        return tuple.__getitem__(self, key)


# ------------------------------------------------------------------ reading

def read_only_query(conn: sqlite3.Connection) -> Query:
    return lambda sql, params=(): conn.execute(sql, params).fetchall()


def circuits(query: Query) -> dict[str, list[int]]:
    """Every circuit with an event on file, and the events at it."""
    out: dict[str, list[int]] = {}
    for event_id, track, layout in query(
            "SELECT id, track, layout FROM events WHERE track IS NOT NULL", ()):
        if track:
            out.setdefault(circuit_key(track, layout), []).append(event_id)
    return out


def _clean(event_ids, exclude_sessions) -> tuple[str, list]:
    params = list(event_ids)
    sql = _CLEAN.format(marks=",".join("?" * len(event_ids)))
    if exclude_sessions:
        sql += " AND l.session_id NOT IN (%s)" % ",".join(
            "?" * len(exclude_sessions))
        params += list(exclude_sessions)
    return sql, params


def clean_lap_count(query: Query, event_ids: list[int], *,
                    exclude_sessions=()) -> int:
    """Clean laps on file with frames - not struck, not pit or out laps, not
    a race's first lap, which starts on the grid rather than the line."""
    if not event_ids:
        return 0
    sql, params = _clean(event_ids, exclude_sessions)
    return int(query("SELECT COUNT(*) " + sql, tuple(params))[0][0])


def _recent_rows(query: Query, event_ids, limit: int, exclude_sessions=()):
    if not event_ids:
        return []
    sql, params = _clean(event_ids, exclude_sessions)
    return query(
        "SELECT l.id, l.session_id, l.lap_num, l.lap_time_ms, "
        "(SELECT car_name FROM events WHERE id = s.event_id) "
        + sql + " ORDER BY l.id DESC LIMIT ?", tuple(params) + (limit,))


def _frames(query: Query, lap_id: int):
    from pitcrew.telemetry.recorder import decode_frames

    got = query("SELECT blob, sample_hz FROM lap_frames WHERE lap_id = ?",
                (lap_id,))
    if not got or got[0][0] is None:
        return None, None
    return decode_frames(got[0][0]), got[0][1]


def load_laps(query: Query, event_ids: list[int], *,
              limit: int = LOAD_LIMIT,
              exclude_sessions=()) -> list[derivation.LapInput]:
    """The most recent clean laps, in the order driven, one blob at a time.

    One query per lap rather than one for all of them, so the store's lock is
    never held across a whole circuit's blobs.
    """
    laps = []
    for lap_id, session_id, lap_num, lap_ms, car in _recent_rows(
            query, event_ids, limit, exclude_sessions):
        frames, hz = _frames(query, lap_id)
        if frames is None:
            continue
        laps.append(derivation.LapInput(
            session_id, lap_num, lap_ms,
            [Frame(tuple(frame.get(name) for name in _KEEP))
             for frame in frames],
            hz or derivation.SAMPLE_HZ, car,
            teleported=teleports(frames).happened))
    laps.reverse()
    return laps


def recent_length_m(query: Query, event_ids: list[int], *,
                    laps: int = RECENT_AXIS_LAPS) -> float | None:
    """The median integrated length of the latest clean laps, or None with
    fewer than `MIN_AXIS_LAPS` that measured the road (no teleport)."""
    lengths = []
    for lap_id, *_ in _recent_rows(query, event_ids, laps):
        frames, _hz = _frames(query, lap_id)
        if not frames or teleports(frames).happened:
            continue
        values = [f.get("lap_distance_m") for f in frames
                  if f.get("lap_distance_m") is not None]
        if values:
            lengths.append(max(values))
    return statistics.median(lengths) if len(lengths) >= MIN_AXIS_LAPS else None


def stored_model(query: Query, key: str) -> dict | None:
    try:
        rows = query("SELECT model_json FROM straight_models "
                     "WHERE circuit_key = ?", (key,))
    except sqlite3.OperationalError:
        return None                     # a file from before v20
    return json.loads(rows[0][0]) if rows else None


# ----------------------------------------------------------------- deciding

@dataclass(frozen=True)
class Plan:
    derive: bool
    reason: str
    available: int
    reference_length_m: float | None = None
    axis_changed: bool = False


def plan(stored: dict | None, available: int,
         recent_m: float | None) -> Plan:
    """Whether to derive, and why - from the stored model and the counts."""
    if stored is None:
        if available < MIN_LAPS:
            return Plan(False, f"no model; {available} clean laps on file, "
                               f"{MIN_LAPS} needed", available)
        return Plan(True, f"no model; {available} clean laps on file",
                    available)
    axis = stored.get("lap_length_m")
    if (recent_m is not None and axis
            and abs(recent_m - axis) > derivation.LAP_LENGTH_TOLERANCE * axis):
        return Plan(True, f"the lap-distance axis moved: the latest laps "
                          f"integrate to {recent_m:.0f} m against the model's "
                          f"{axis:.0f} m", available,
                    reference_length_m=recent_m, axis_changed=True)
    pooled = int(stored.get("laps") or 0)
    then = stored.get("laps_available")
    then = pooled if then is None else int(then)
    new = available - then
    need = max(1, math.ceil(GROWTH * pooled))
    if new >= need:
        return Plan(True, f"{new} clean laps since the model was derived "
                          f"from {pooled} ({need} needed)", available)
    return Plan(False, f"{max(new, 0)} clean laps since the model was derived "
                       f"from {pooled}; {need} needed", available)


def gate_failures(stored: dict) -> list[str]:
    """Where a stored model fails today's gates - a model written before
    them, or by hand, is no baseline to protect."""
    failures = []
    if int(stored.get("laps") or 0) < MIN_LAPS:
        failures.append(f"{stored.get('laps')} laps pooled")
    for window in stored.get("windows") or ():
        reason = derivation.gate({
            "laps": int(window.get("laps") or 0),
            "end_spread_m": (math.inf if window.get("end_spread_m") is None
                             else float(window["end_spread_m"]))})
        if reason:
            failures.append(f"{window.get('id')} {reason}")
    return failures


def _overlaps(a: dict, b: dict, axis: float) -> bool:
    return derivation._overlap(float(a["start_m"]), float(a["end_m"]),
                               float(b["start_m"]), float(b["end_m"]),
                               axis) > 0


def compare(stored: dict | None, candidate: derivation.Derived, *,
            axis_changed: bool = False) -> str | None:
    """Why `candidate` may not replace `stored`, or None if it may."""
    if candidate.model is None:
        return f"nothing derived - {candidate.reason}"
    if stored is None or axis_changed or gate_failures(stored):
        return None
    new = candidate.model
    old_laps = int(stored.get("laps") or 0)
    if not set(stored.get("session_ids") or ()) & set(new["session_ids"]):
        return None                     # entirely new evidence
    if new["laps"] < old_laps:
        return (f"it pools {new['laps']} laps against the stored model's "
                f"{old_laps}")
    if new["laps"] >= RETIRE_RATIO * old_laps:
        return None
    axis = float(stored.get("lap_length_m") or new["lap_length_m"])
    lost = []
    for window in stored.get("windows") or ():
        if any(_overlaps(window, w, axis) for w in new["windows"]):
            continue
        why = next((d["reason"] for d in candidate.dropped
                    if _overlaps(window, d, axis)), "no longer on most laps")
        lost.append(f"{window.get('id')} {float(window['start_m']):.0f}-"
                    f"{float(window['end_m']):.0f} m ({why})")
    if lost:
        return "it would lose " + "; ".join(lost)
    return None


@dataclass
class Outcome:
    circuit_key: str
    action: str                 # stored | would-store | refused | unchanged
    reason: str
    derived: derivation.Derived | None = None
    available: int = 0
    seconds: float | None = None        # loading and deriving, when it did


def _summary(model: dict) -> str:
    return (f"{len(model['windows'])} straights, {model['laps']} laps pooled "
            f"of {model.get('laps_available')} clean, sessions "
            f"{model['session_ids'][0]}-{model['session_ids'][-1]}, axis "
            f"{model['lap_length_m']:.0f} m [DERIVED]")


def refresh(query: Query, key: str, event_ids: list[int], *,
            save: Callable[[str, dict], None] | None = None,
            always: bool = False, replace: bool = False,
            today: str | None = None,
            exclude_sessions=()) -> Outcome:
    """Derive `key` if `plan` says so (or `always`), and store it through
    `save` if `compare` lets it. `save=None` is a dry run.

    Logs every outcome, accepts included (rule 10).
    """
    logger = log(_LOG)
    stored = stored_model(query, key)
    available = clean_lap_count(query, event_ids,
                                exclude_sessions=exclude_sessions)
    recent = (recent_length_m(query, event_ids)
              if stored is not None else None)
    decided = plan(stored, available, recent)
    if not decided.derive and not always:
        logger.info("straights %s: unchanged - %s", key, decided.reason)
        return Outcome(key, "unchanged", decided.reason, None, available)

    started = time.monotonic()
    laps = load_laps(query, event_ids, exclude_sessions=exclude_sessions)
    derived = derivation.derive(
        key, laps, derived_on=today or datetime.date.today().isoformat(),
        max_laps=MAX_LAPS, reference_length_m=decided.reference_length_m)
    del laps
    took = time.monotonic() - started
    if derived.model is not None:
        derived.model["laps_available"] = available
    for window in derived.dropped:
        logger.info("straights %s: window left out, not stored - %s",
                    key, derivation.describe_dropped(window))
    refusal = (None if replace and derived.model is not None
               else compare(stored, derived,
                            axis_changed=decided.axis_changed))
    if refusal is not None:
        kept = ("the stored model stays" if stored is not None
                else "no model")
        logger.info("straights %s: refused (%s) - %s; %s [%.1f s]", key,
                    decided.reason, refusal, kept, took)
        return Outcome(key, "refused", refusal, derived, available, took)
    if save is None:
        return Outcome(key, "would-store", decided.reason, derived, available,
                       took)
    save(key, derived.model)
    logger.info("straights %s: stored (%s) - %s%s [%.1f s]", key,
                decided.reason, _summary(derived.model),
                "; replacing on the driver's --replace" if replace else "",
                took)
    return Outcome(key, "stored", decided.reason, derived, available, took)


# ----------------------------------------------------- the session close

# Serialises refreshes, so two sessions closed in quick succession at one
# circuit are judged one after the other against what the first stored. A
# lock, not a cache: it holds no state about any session.
_REFRESHING = threading.Lock()


def refresh_after_session(store, session_id: int) -> Outcome | None:
    """Re-derive the closed session's circuit if it needs it. Reads through
    the store's own lock one query at a time; writes through
    `Store.save_straight_model`."""
    query = store._query
    with _REFRESHING:
        rows = query("SELECT e.track, e.layout FROM sessions s "
                     "JOIN events e ON e.id = s.event_id WHERE s.id = ?",
                     (session_id,))
        if not rows or not rows[0][0]:
            log(_LOG).info("straights: session %s has no circuit on its "
                           "event - nothing to derive", session_id)
            return None
        key = circuit_key(rows[0][0], rows[0][1])
        return refresh(query, key, circuits(query).get(key, []),
                       save=store.save_straight_model)


def refresh_in_background(store, session_id: int | None) -> threading.Thread | None:
    """`refresh_after_session` on a daemon thread; never raises into the
    caller, and a failure is a logged warning."""
    if session_id is None:
        return None

    def work() -> None:
        try:
            refresh_after_session(store, session_id)
        except Exception:                                # noqa: BLE001
            log(_LOG).warning(
                "straights: could not refresh the model after session %s - "
                "the stored model, if any, is unchanged", session_id,
                exc_info=True)

    thread = threading.Thread(target=work, name="straights", daemon=True)
    thread.start()
    return thread
