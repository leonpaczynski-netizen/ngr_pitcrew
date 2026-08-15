"""Find the stops in sessions that were recorded before the app could see them.

    python tools/reaggregate.py              # report, change nothing
    python tools/reaggregate.py --apply      # write the flags back

Every lap ever recorded carries `is_pit_lap = 0` and `is_out_lap = 0`, because
the live detector asked for the tank to rise 0.05 L between two consecutive
frames and GT7 fills at 0.0167 L per frame. The gate could not fire. That is
fixed for sessions recorded from now on; this is for the 132 laps already on
disk, and it works because the raw frames were kept — re-reading a stored
session after fixing a detector is exactly the case `CLAUDE.md` §6 kept them
for.

**It only ever sets flags.** No lap is deleted, no time is rewritten, no
aggregate is recomputed here. A lap the detector cannot explain is left
exactly as it is rather than being given a guess, and a flag the driver set by
hand is never overwritten by one the app worked out.

The unit is the lap, not the session: a stop lives inside one lap's frames,
and the lap after it is the out-lap.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.telemetry.pit_detect import Sample, find_stops

CORNERS = ("fl", "fr", "rl", "rr")


@dataclass(frozen=True)
class LapFinding:
    """What re-reading one lap's frames turned up."""
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

        `tyres_changed` is included even when False — on a lap where a stop
        was found, "the set stayed on" is a real answer. It is omitted
        entirely on a lap with no stop, where the question was never asked.
        """
        out: dict = {"is_pit_lap": int(self.is_pit_lap),
                     "is_out_lap": int(self.is_out_lap)}
        if self.is_pit_lap:
            out["tyres_changed"] = (None if self.tyres_changed is None
                                    else int(self.tyres_changed))
            out["fuel_added_l"] = self.fuel_added_l
        return out

    def describe(self) -> str:
        where = f"s{self.session_id} lap {self.lap_num}: "
        if not self.is_pit_lap:
            return where + "out-lap"
        what = []
        if self.fuel_added_l:
            what.append(f"+{self.fuel_added_l:.1f} L")
        if self.tyres_changed:
            what.append("tyres")
        # A lap can be both: he came out of one stop and back into the next.
        return (where + ("out-lap and pit lap, " if self.is_out_lap
                         else "pit lap, ")
                + f"{self.stop_s:.0f} s stationary"
                + (f" ({', '.join(what)})" if what else ""))


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
        ))
    return out


def read_session(laps: list[dict], frames_for) -> list[LapFinding]:
    """Every stop in one session's stored laps, and the out-laps they imply.

    `laps` are rows in lap order; `frames_for(lap_id)` returns the decoded
    frames or None. A lap with no frames is skipped rather than assumed clean:
    it was not measured, which is not the same as having no stop in it.
    """
    findings: list[LapFinding] = []
    pit_before = False

    for lap in laps:
        frames = frames_for(lap["id"])
        if frames is None:
            pit_before = False
            continue

        serviced = [stop for stop
                    in find_stops(samples_from(frames, lap.get("sample_hz", 60.0)))
                    if stop.serviced]

        # **One finding per lap, never two.** A lap can be the out-lap of one
        # stop and the in-lap of the next, and two findings for it write two
        # sets of flags: `changes` always carries both columns, so applying
        # them in order put `is_out_lap = 0` back over the out-lap finding
        # that had just set it.
        if serviced:
            # More than one serviced stop inside a single lap is not a thing a
            # driver does; if it ever happens the fuel is summed and the tyre
            # answer is "yes if any of them changed it", which is the honest
            # reading of the evidence rather than a choice between them.
            findings.append(LapFinding(
                lap_id=lap["id"], session_id=lap["session_id"],
                lap_num=lap["lap_num"], is_pit_lap=True,
                is_out_lap=pit_before,
                tyres_changed=any(s.changed_tyres for s in serviced),
                fuel_added_l=round(sum(s.fuel_added_l for s in serviced), 2),
                stop_s=sum(s.duration_s for s in serviced),
                note=("a stop found in this lap's frames, and it follows a "
                      "stop" if pit_before
                      else "stop found in this lap's frames")))
        elif pit_before:
            findings.append(LapFinding(
                lap_id=lap["id"], session_id=lap["session_id"],
                lap_num=lap["lap_num"], is_out_lap=True,
                note="the lap after a stop"))
        pit_before = bool(serviced)

    return findings
