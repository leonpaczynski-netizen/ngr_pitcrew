"""What the driver tells the engineer, written down beside what the feed said.

**The radio only ever went one way.** Every intent in `engineer/intents.py` bar
one is a question - the driver asks, the engineer answers from the race state.
But `CLAUDE.md` §4.1 is the standing rule of the whole programme:

    The driver's report is primary evidence. Telemetry is corroboration.

and the app had no way to receive primary evidence at all. A handling
complaint made at racing speed, in the corner it happened in, is the single
most valuable thing said over a race weekend - it is what the export exists to
carry into a setup - and it was landing in the `radio` table as free text
tagged `unknown`, where nothing could find it again.

### The two disciplines, both inherited from `hud_calibration.py`

* **The driver reports the EVENT; the app supplies the NUMBERS.** He is not
  asked to read anything off a screen or to quantify a complaint. He says the
  front is pushing; the app writes down where he was, how fast, what lock was
  on, what the tyres were reading and which lap it was. His half is the
  observation and it is kept in his own words.
* **Acknowledged, never analysed out loud.** The engineer says "copy" and
  writes it down. Telling him what a report means would be inventing the
  meaning this file exists to collect the evidence for, and one observation is
  one observation. §5.5 allows one thing at a time and this is not the thing.

### Why a JSONL file and not a table

The same reason `hud_calibration.py` uses one: the schema of something nobody
has aggregated yet will change, and an append-only log survives that where a
migration does not. When the shape settles it can become a table, and the rows
will still be here to fill it.

### What is deliberately NOT recorded here

**Which corner it was.** Resolving that live needs the lap-distance integrator
and the stored corner model, which the race path does not carry yet - and a
corner id guessed from a world position would be a confident wrong label on
the one record that is supposed to be primary evidence. What is recorded is
the raw position and speed, from which the offline side can resolve the corner
exactly, whenever that work is done. Missing is missing.
"""
from __future__ import annotations

import datetime
import json
import math

from pitcrew.diagnostics import log
from pitcrew.paths import DATA_DIR

# One JSON object per line, appended.
REPORT_FILE = DATA_DIR / "driver_reports.jsonl"

# The kinds of report the vocabulary can produce. Kept here rather than in
# `intents.py` so that the record's vocabulary and the radio's vocabulary can
# move independently - a new phrase for an existing kind must not change what
# a season of rows means.
UNDERSTEER = "understeer"
OVERSTEER = "oversteer"
INCIDENT = "incident"
TRAFFIC = "traffic"
KINDS = (UNDERSTEER, OVERSTEER, INCIDENT, TRAFFIC)


def note_report(kind: str, heard: str, *, packet=None,
                car_id=None, compound: str | None = None,
                lap: int | None = None, event_id: int | None = None,
                session_id: int | None = None,
                path=None) -> dict | None:
    """Record one driver report against whatever the feed was reading.

    Returns the row written, or None for a kind nobody defined. **A report
    with no packet beside it is still written**, unlike a HUD calibration row:
    there the pairing IS the observation, here the driver's words are the
    observation and the telemetry is corroboration that may legitimately be
    absent. Losing "the rear stepped out at the exit of six" because the
    stream had a gap would be losing the primary evidence to keep the
    secondary.
    """
    if kind not in KINDS:
        return None
    row = {
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        # **His own words, verbatim.** The classified `kind` is ours and is a
        # lossy reading of what he said; the sentence is his and is the thing
        # §4.1 calls primary. A later reader must never be in doubt about
        # which half of this row is observation and which is inference.
        "heard": heard,
        "carId": car_id,
        "eventId": event_id,
        "sessionId": session_id,
        "compound": compound,
        "lap": lap,
    }
    row.update(_telemetry(packet))
    _append(row, path)
    log("race").info("driver report (%s) on lap %s: %r", kind, lap, heard)
    return row


def _telemetry(packet) -> dict:
    """What the feed was saying at that instant. All null where it was not.

    Every channel here is one a handling complaint is diagnosed against, and
    every one of them is `None` rather than `0` when absent - a steering angle
    of zero is a real value and means the wheel was straight.
    """
    if packet is None:
        return {"telemetry": None}
    temps = getattr(packet, "tyre_temps", None)
    steering = getattr(packet, "steering", None)
    throttle = getattr(packet, "throttle", None)
    brake = getattr(packet, "brake", None)
    return {"telemetry": {
        "speedKmh": _round(getattr(packet, "speed_kmh", None), 1),
        # Where on the circuit, in the game's own coordinates. The corner is
        # resolved from this offline; see the module docstring for why it is
        # not resolved here.
        "position": _position(packet),
        # Units converted here rather than carried raw, per CLAUDE.md 3.4:
        # the packet holds 0-1 pedals and radians, the record holds percent
        # and degrees, and nothing downstream should have to know which.
        "throttlePct": _round(None if throttle is None else throttle * 100.0, 1),
        "brakePct": _round(None if brake is None else brake * 100.0, 1),
        # **None on the 'A' packet format, which carries no steering at all.**
        # Zero would read as a straight wheel, which is exactly the wrong
        # thing to record beside "it would not turn in".
        "steeringDeg": _round(None if steering is None
                              else math.degrees(steering), 1),
        "gear": getattr(packet, "current_gear", None),
        "rpm": _round(getattr(packet, "engine_rpm", None), 0),
        "tyreTempC": ({"fl": _round(temps[0], 1), "fr": _round(temps[1], 1),
                       "rl": _round(temps[2], 1), "rr": _round(temps[3], 1)}
                      if temps and len(temps) == 4 else None),
    }}


def _position(packet) -> dict | None:
    x = getattr(packet, "pos_x", None)
    y = getattr(packet, "pos_y", None)
    z = getattr(packet, "pos_z", None)
    if x is None or z is None:
        return None
    return {"x": _round(x, 2), "y": _round(y, 2), "z": _round(z, 2)}


def _round(value, digits: int):
    if value is None:
        return None
    try:
        return round(float(value), digits) if digits else int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _append(row: dict, path=None) -> None:
    target = path or REPORT_FILE
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except OSError as exc:
        # **Never let note-taking reach a driver mid-race.** The exchange is
        # already in the `radio` table, which is where this can be recovered
        # from if the file could not be written.
        log("race").warning("could not write the driver report: %s", exc)


def read_reports(path=None) -> list[dict]:
    """Every report on file, oldest first. Bad lines are skipped, not raised.

    A log that a later bug half-wrote must still be readable: the rows before
    the damage are evidence and refusing all of them to protest one is the
    wrong trade.
    """
    target = path or REPORT_FILE
    if not target.exists():
        return []
    out = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            log("race").warning("skipping an unreadable driver-report row")
    return out
