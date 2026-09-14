"""Which laps are in-laps, read off the stored frames - and so which are out-laps.

    python tools/repair_in_out_laps.py            # report, change nothing
    python tools/repair_in_out_laps.py --apply --db PATH

**The in-lap is defined by what happened, not by a flag.** It is the lap on
which the car was driven into the pit lane and stopped there to be serviced.
The frames say so three ways, all of them read by `telemetry.pit_detect` - the
same detector the live path uses, never a second one:

* **(A) a pit stop in this lap, after racing.** `find_stops` finds a serviced
  stationary window (fuel rising at a rig's rate, or all four tyres assigned
  one temperature), and the car was above pit-lane speed earlier in the lap.
  Monza, Deep Forest: the box is before the line.
* **(B) the NEXT lap opens on a pit stop.** Its first pit stop comes before
  any frame above pit-lane speed: the car crossed the line inside the pit
  lane, BEFORE the box (Daytona, Spa - "Crossing in the Box"). The in-lap is
  the lap before; the lap holding the stop is its out-lap.
* **(C) a pit-lane placement with no stop to see.** GT7 hands a driven car to
  the lane rolling at the limiter (`pit_detect.placed_in_pit_lane`). Only
  ever used to KEEP a stored flag - a session that ended in the pits has an
  in-lap and nothing after it.

**A practice reset is not a stop** (`pit_detect.reset_at`). The game puts the
car back in the box: moved there in one frame, landing stationary, the tank
and the tyres replaced in the same frame. Nothing was driven into the pit
lane, so it makes no in-lap and no out-lap - but the lap itself is struck,
reason `reset` (the driver, 15 Sep 2026: "Strike the reset lap."), because its
time was clocked from the box, not round the circuit. It still ends the tank:
`runs.starts_run` sees the fill in the lap's fuel readings.

**The out-lap is then THE RULE** (`runs.out_lap_after_in_lap`, the driver,
15 Sep 2026): *"A lap in the same session after an in lap has to be an out
lap."* No exceptions within a session; a session change creates none. **A row
that holds both the in-lap and its out-lap satisfies it**
(`LapReading.holds_out_lap`): that row is the out-lap, and the next row is a
flying lap that counts.

The unit is the lap, and the session is the scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from pitcrew.analysis.runs import REASON_RESET, out_lap_after_in_lap
from pitcrew.telemetry.pit_detect import (
    RACING_KPH,
    Sample,
    Stop,
    find_stops,
    placed_in_pit_lane,
    reset_at,
)

CORNERS = ("fl", "fr", "rl", "rr")

# Above this the car is racing, not rolling down a pit lane.
PIT_LANE_MAX_KPH = RACING_KPH

# A lap's frames have to span this much of its lap time before the frames'
# SILENCE about a stop is believed. Less, and a stop may sit in the part the
# recorder never saw - session 72 lap 5 carries 45 s of frames for an 80.7 s
# lap - so "no stop in the frames" is "cannot tell", never "no stop".
COVERED_FRACTION = 0.9

IN_LAP_STOP = "stop"            # (A)
IN_LAP_CROSSED = "crossed"      # (B)
IN_LAP_PLACED = "placed"        # (C)


@dataclass(frozen=True)
class LapReading:
    """What one lap's frames say about the pits. Nothing here is a verdict."""
    lap_id: int
    session_id: int | None
    lap_num: int
    has_frames: bool
    covered: bool
    # Serviced stops the car was driven to, in order (`Stop.pit_stop`).
    stops: tuple[Stop, ...] = ()
    # The first of them comes before any racing frame of this lap.
    opens_on_stop: bool = False
    placed_s: float | None = None
    # **This row holds its in-lap AND its out-lap** (the driver, 15 Sep 2026:
    # "A row that contains both the in-lap and the out-lap satisfies the
    # rule; the next row is a flying lap and counts"): a pit stop after racing
    # in this lap, and the car back above racing speed after that stop ended -
    # released and driven back up to speed before the line closed the row.
    holds_out_lap: bool = False
    # When a practice reset happened in this lap (`pit_detect.reset_at`).
    reset_s: float | None = None


@dataclass(frozen=True)
class LapFinding:
    """What re-reading one lap's frames turned up, as the flags it implies."""
    lap_id: int
    session_id: int
    lap_num: int
    is_pit_lap: bool = False
    is_out_lap: bool = False
    tyres_changed: bool | None = None
    fuel_added_l: float | None = None
    stop_s: float | None = None
    note: str = ""

    @property
    def changes(self) -> dict:
        """The columns this finding would write, and only those.

        `tyres_changed` and `fuel_added_l` only on the lap whose own frames
        hold the stop - "the set stayed on" is a real answer there, and the
        question was never asked anywhere else.
        """
        out: dict = {"is_pit_lap": int(self.is_pit_lap),
                     "is_out_lap": int(self.is_out_lap)}
        if self.stop_s is not None:
            out["tyres_changed"] = (None if self.tyres_changed is None
                                    else int(self.tyres_changed))
            out["fuel_added_l"] = self.fuel_added_l
        return out

    def describe(self) -> str:
        where = f"s{self.session_id} lap {self.lap_num}: "
        if not self.is_pit_lap:
            text = where + "out-lap"
        else:
            # A lap can be both: he came out of one stop and back into the next.
            text = where + ("out-lap and pit lap" if self.is_out_lap
                            else "pit lap")
        if self.stop_s is not None:
            what = []
            if self.fuel_added_l:
                what.append(f"+{self.fuel_added_l:.1f} L")
            if self.tyres_changed:
                what.append("tyres")
            text += (f", {self.stop_s:.0f} s stationary"
                     + (f" ({', '.join(what)})" if what else ""))
        return text


def samples_from(frames: list[dict], sample_hz: float) -> list[Sample]:
    """Stored frames as the stop detector's input.

    The frame clock is the row index at the known sample rate, not `t_ms`:
    laps recorded before 12 Aug carry GT7's in-game clock there, which runs at
    the event's time multiplier and is useless as a duration.

    `on_track` is True throughout. A lap that was recorded at all was recorded
    on track — the recorder drops frames where the car is not — so the field
    carries no information here and pretending otherwise would end stationary
    windows at random.
    """
    rate = sample_hz or 60.0
    out = []
    for index, frame in enumerate(frames):
        temps = tuple(frame.get(f"temp_{corner}") for corner in CORNERS)
        out.append(Sample(
            t_s=index / rate,
            speed_kph=frame.get("speed_kph") or 0.0,
            fuel_l=frame.get("fuel_l") if frame.get("fuel_l") is not None else 0.0,
            on_track=True,
            lap=index,
            temps=None if None in temps else temps,
            x_m=frame.get("pos_x"),
            z_m=frame.get("pos_z"),
        ))
    return out


def read_lap(lap: dict, frames: list[dict] | None) -> LapReading:
    """One lap's frames through the stop detector."""
    base = dict(lap_id=lap["id"], session_id=lap.get("session_id"),
                lap_num=lap["lap_num"])
    if not frames:
        return LapReading(**base, has_frames=False, covered=False)
    rate = lap.get("sample_hz") or 60.0
    samples = samples_from(frames, rate)
    windows = find_stops(samples)
    stops = tuple(stop for stop in windows if stop.pit_stop)
    opens = False
    holds_out = False
    if stops:
        first = stops[0]
        opens = not any(sample.speed_kph > PIT_LANE_MAX_KPH
                        for sample in samples if sample.t_s < first.start_s)
        driven_into = [stop for index, stop in enumerate(stops)
                       if index or not opens]
        if driven_into:
            holds_out = back_up_to_speed_s(samples, driven_into[-1]) is not None
    lap_time_ms = lap.get("lap_time_ms")
    covered = (bool(lap_time_ms) and lap_time_ms > 0
               and len(frames) / rate >= COVERED_FRACTION * lap_time_ms / 1000.0)
    return LapReading(**base, has_frames=True, covered=covered, stops=stops,
                      opens_on_stop=opens,
                      placed_s=placed_in_pit_lane(samples, windows),
                      holds_out_lap=holds_out, reset_s=reset_at(samples))


def back_up_to_speed_s(samples, stop: Stop) -> float | None:
    """Seconds from the car first being back above racing speed after `stop`
    to the end of these samples - or None where it never was.

    The out-lap half of a merged row: released from the box and driven back
    above `RACING_KPH` before the line closed the row. A box before the line
    whose exit comes AFTER it (session 136 lap 6: the stop ends 2 s before
    the row does, and the car leaves at 80 km/h) never gets there, and its
    out-lap is the next row.
    """
    after = [sample for sample in samples
             if sample.t_s > stop.end_s and sample.speed_kph > RACING_KPH]
    if not after:
        return None
    return samples[-1].t_s - after[0].t_s


def lap_reset_s(frames: list[dict] | None, sample_hz: float) -> float | None:
    """When a practice reset happened in these frames - the live recorder's
    question, asked of the one detector."""
    if not frames:
        return None
    return reset_at(samples_from(frames, sample_hz))


def _same_session(a: LapReading, b: LapReading) -> bool:
    return not (a.session_id is not None and b.session_id is not None
                and a.session_id != b.session_id)


def in_lap_evidence(readings: list[LapReading]) -> dict[int, str]:
    """{lap_id: evidence} for every lap the frames show was an in-lap.

    `readings` in lap order. (A) and (B) only - the ones that SET a flag.
    (C) is read separately by the repair, which only uses it to keep one.
    """
    found: dict[int, str] = {}
    for index, reading in enumerate(readings):
        if not reading.stops:
            continue
        if not reading.opens_on_stop:
            found[reading.lap_id] = IN_LAP_STOP
            continue
        # The lap opens in the pit lane: the line came before the box, so the
        # in-lap is the one before - if there is one in this session. A
        # session's first lap opening on a stop is the grid fill or the lobby
        # box, and no lap was driven in.
        before = readings[index - 1] if index else None
        if before is not None and _same_session(before, reading):
            found[before.lap_id] = IN_LAP_CROSSED
        # A lap opening on one stop can still be driven into another later.
        if len(reading.stops) > 1:
            found[reading.lap_id] = IN_LAP_STOP
    return found


def _flags(reading: LapReading, is_pit: bool, is_out: bool):
    """A reading as the duck type `out_lap_after_in_lap` asks of."""
    return SimpleNamespace(is_pit_lap=is_pit, is_out_lap=is_out,
                           session_id=reading.session_id)


def outs_by_rule(readings: list[LapReading], pit: dict[int, bool],
                 stored_out: dict[int, bool]) -> dict[int, tuple[bool, str]]:
    """{lap_id: (is_out_lap, why)} across one session, given its in-laps.

    **One walk, for `read_session` and the repair alike.** A lap is an out-lap
    where it already was one, where it is an in-lap whose own frames hold its
    out-lap, or where THE RULE makes it one - asked of
    `runs.out_lap_after_in_lap` with the flags as they will stand, so the row
    after a merged in-lap is judged against that row's own out-lap flag.
    """
    out: dict[int, tuple[bool, str]] = {}
    shown: list = []
    for index, reading in enumerate(readings):
        is_pit = pit.get(reading.lap_id, False)
        is_out, why = stored_out.get(reading.lap_id, False), ""
        if not is_out and is_pit and reading.holds_out_lap:
            is_out, why = True, ("this row holds its out-lap too: after the "
                                 "stop the car is back above racing speed "
                                 "before the line")
        previous = shown[index - 1] if index else None
        before = shown[index - 2] if index >= 2 else None
        if (not is_out and previous is not None
                and out_lap_after_in_lap(
                    previous, _flags(reading, is_pit, False), before)):
            is_out = True
            why = f"the lap after in-lap {readings[index - 1].lap_num}"
        out[reading.lap_id] = (is_out, why)
        shown.append(_flags(reading, is_pit, is_out))
    return out


def read_session(laps: list[dict], frames_for) -> list[LapFinding]:
    """Every in-lap in one session's stored laps, and the out-laps THE RULE makes.

    `laps` are rows in lap order; `frames_for(lap_id)` returns the decoded
    frames or None. A lap with no frames is never an in-lap here and makes no
    out-lap: it was not measured, which is not the same as having no stop in
    it.
    """
    readings = [read_lap(lap, frames_for(lap["id"])) for lap in laps]
    in_laps = in_lap_evidence(readings)
    outs = outs_by_rule(readings, {lap_id: True for lap_id in in_laps}, {})

    findings: list[LapFinding] = []
    for reading in readings:
        is_in = reading.lap_id in in_laps
        is_out, why = outs[reading.lap_id]
        if not (is_in or is_out):
            continue
        stop = reading.stops
        findings.append(LapFinding(
            lap_id=reading.lap_id,
            session_id=reading.session_id,
            lap_num=reading.lap_num,
            is_pit_lap=is_in,
            is_out_lap=is_out,
            # **One finding per lap, never two.** A lap can be the out-lap of
            # one stop and the in-lap of the next.
            tyres_changed=(any(s.changed_tyres for s in stop)
                           if stop else None),
            fuel_added_l=(round(sum(s.fuel_added_l for s in stop), 2)
                          if stop else None),
            stop_s=sum(s.duration_s for s in stop) if stop else None,
            note="; ".join(part for part in (
                _EVIDENCE.get(in_laps.get(reading.lap_id), ""), why) if part)))
    return findings


@dataclass(frozen=True)
class FlagChange:
    """One stored column the repair would move, and why."""
    lap_id: int
    session_id: int | None
    lap_num: int
    column: str             # `is_pit_lap`, `is_out_lap` or `exclusion_reason`
    stored: object
    target: object
    reason: str

    def describe(self) -> str:
        return (f"s{self.session_id} lap {self.lap_num}: {self.column} "
                f"{self.stored} -> {self.target} ({self.reason})")


def plan_session(laps: list[dict], frames_for) -> list[FlagChange]:
    """What the stored flags of one session should become, and nothing else.

    `laps` are stored rows in lap order, carrying `is_pit_lap`, `is_out_lap`,
    `excluded`, `exclusion_reason`, `lap_time_ms` and `sample_hz`. The rules,
    in order of how much they are allowed to do:

    * **`is_pit_lap` is SET** where the frames show an in-lap - (A) or (B).
    * **`is_pit_lap` is CLEARED** only where the frames cover the lap and show
      no in-lap by any of (A), (B) or (C): a practice reset, a crash, the
      out-lap of a stop whose line came before the box. A lap without frames,
      or with frames that do not span its lap time, keeps what it has -
      silence from a recording that missed part of the lap is not evidence.
    * **`is_out_lap` is SET** on an in-lap whose own frames hold its out-lap,
      and by THE RULE on the lap after every other in-lap. **Never cleared.**
    * **A lap with a practice reset in it is STRUCK**, `excluded = 1` with
      reason `reset` - only where nothing had struck it, so a reason he gave
      is never overwritten.

    No lap is deleted and no time is rewritten.
    """
    readings = [read_lap(lap, frames_for(lap["id"])) for lap in laps]
    evidence = in_lap_evidence(readings)
    changes: list[FlagChange] = []
    target_pit: dict[int, bool] = {}
    for lap, reading in zip(laps, readings):
        stored = bool(lap.get("is_pit_lap"))
        if reading.lap_id in evidence:
            target = True
            why = _EVIDENCE[evidence[reading.lap_id]]
        elif not stored:
            target, why = False, ""
        elif not reading.has_frames:
            target, why = True, ""
        elif not reading.covered:
            target, why = True, ""
        elif reading.placed_s is not None:
            target, why = True, ""
        else:
            target = False
            if reading.stops and reading.opens_on_stop:
                what = ("its stop opens the lap, so the line came before the "
                        "box and this is the out-lap")
            elif reading.reset_s is not None:
                what = "a practice reset: the car was moved to the box"
            else:
                what = "no pit stop and no pit-lane placement"
            why = f"the frames cover the lap - {what}"
        target_pit[reading.lap_id] = target
        if target != stored:
            changes.append(FlagChange(reading.lap_id, reading.session_id,
                                      reading.lap_num, "is_pit_lap",
                                      int(stored), int(target), why))

    stored_out = {lap["id"]: bool(lap.get("is_out_lap")) for lap in laps}
    outs = outs_by_rule(readings, target_pit, stored_out)
    for reading in readings:
        is_out, why = outs[reading.lap_id]
        if is_out and not stored_out[reading.lap_id]:
            changes.append(FlagChange(reading.lap_id, reading.session_id,
                                      reading.lap_num, "is_out_lap", 0, 1, why))

    for lap, reading in zip(laps, readings):
        if reading.reset_s is not None and not lap.get("excluded"):
            changes.append(FlagChange(
                reading.lap_id, reading.session_id, reading.lap_num,
                "exclusion_reason", lap.get("exclusion_reason"), REASON_RESET,
                f"a practice reset {reading.reset_s:.1f} s into the frames: "
                f"the time is clocked from the box, not round the circuit"))
    return changes


_EVIDENCE = {
    IN_LAP_STOP: "a pit stop in this lap's frames, after racing",
    IN_LAP_CROSSED: ("the next lap opens on its pit stop: the line was "
                     "crossed in the pit lane, before the box"),
}


def rule_violations(laps: list[dict]) -> list[tuple]:
    """(session_id, in-lap, next lap) wherever THE RULE is broken.

    `laps` in session and lap order, as stored rows or anything with the same
    keys. Asked of `runs.out_lap_after_in_lap` itself, so an in-lap row that
    holds its own out-lap is not a break, and an in-lap that ends its session
    has no lap after it to break the rule with.
    """
    rows = [SimpleNamespace(is_pit_lap=bool(lap.get("is_pit_lap")),
                            is_out_lap=bool(lap.get("is_out_lap")),
                            session_id=lap.get("session_id"))
            for lap in laps]
    out = []
    for index in range(1, len(rows)):
        previous, row = rows[index - 1], rows[index]
        if previous.session_id != row.session_id or row.is_out_lap:
            continue
        before = rows[index - 2] if index >= 2 else None
        if out_lap_after_in_lap(previous, row, before):
            out.append((row.session_id, laps[index - 1]["lap_num"],
                        laps[index]["lap_num"]))
    return out
