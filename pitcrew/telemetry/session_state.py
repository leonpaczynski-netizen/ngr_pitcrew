"""Session and lap state derived from the GT7 packet stream.

This replaces the old 1081-line `RaceStateTracker`.  Almost all of that class
existed to serve features that no longer exist (setup evidence, qualifying,
coaching).  What is kept here is the handful of detectors that were expensive
to get right:

* **Lap completion** fires on `last_lap_ms` changing to a new positive value,
  never on `laps_completed` — GT7's lap counter is unreliable and its indexing
  convention differs between race types.
* **Race start** requires `(the car was seen below 30 km/h) AND speed > 80`,
  or the lap counter increasing.  The low-speed gate stops a formation lap, or
  the app being started mid-session, from faking lights-out.  The lap-counter
  branch is deliberately left ungated so rolling starts still fire.
* **Race length** is taken from the maximum `laps_in_race` seen before the
  start, not from the packet at the moment of starting.  On circuits where the
  grid sits behind the start/finish line GT7 has already decremented the count
  by the time the car reaches 80 km/h.
* **Pit laps** are inferred, because GT7 broadcasts no pit flag in any packet
  format.  Two independent signals, either of which is enough: the tank rising
  across a two-second window at pit-lane speed, and all four tyre temperatures
  converging to one value in a single frame.  The second is the only evidence
  a **tyres-only stop** leaves behind.

The session kind is set by the app from what the driver chose to do, never
guessed from the game — GT7 classifies any multi-car lobby as a race.

Threading: `update()` is called on the UDP thread and returns events rather
than dispatching them, so the caller decides which thread acts on them.
"""
from __future__ import annotations

import enum
import time
from collections import deque
from dataclasses import dataclass, field

from pitcrew.analysis.refuel import MAX_PLAUSIBLE_LPS
from pitcrew.telemetry.packet import GT7Packet
from pitcrew.telemetry.recorder import SAMPLE_HZ

# Speed below which a fuel increase means the pit lane rather than a physics
# quirk.  GT7 pit limiters sit at 60-80 km/h; 120 leaves generous margin.
# This is the gate the car has to clear to be *leaving*; the fill itself is
# measured at a standstill -- see `_refuelling`.
PIT_MAX_SPEED_KMH = 120.0

# **Fuel has to be measured across a window, never between two frames.**
# GT7 fills at about 1 L/s and the stream runs at 60 Hz, so the tank rises by
# roughly 0.0167 L per frame.  The gate this replaced asked for 0.05 L between
# consecutive frames -- three times the signal -- and so never fired once in
# 132 recorded laps, including a stop that took 51 L over 63 s.  Every lap in
# the capture set carries `is_pit_lap = 0` as a result, and with it every
# out-lap, every stint boundary and every stop the export ever reported.
#
# 0.30 L over 2 s is six times the noise floor of a channel reported in litres
# and a fifth of what the slowest observed fill delivers in that time.
REFUEL_WINDOW_S = 2.0
REFUEL_WINDOW_L = 0.30

# **And a ceiling, because a tank can also be replaced rather than filled.**
# The floor above says "the level is rising"; nothing said how fast, so a
# single-frame garage reset satisfied it. Real: session 16 lap 1 steps
# 96.192 -> 100.000 between one packet and the next at 0.00 km/h, which is
# 228 L/s where GT7 fills at about one. The offline twin `pit_detect.find_stops`
# never fell for it because it measures the rise from inside a stationary
# window; this is the live half of the same rule, bounded by the figure
# `analysis/refuel.py` already uses to reject an implausible rate.
MAX_REFUEL_LPS = MAX_PLAUSIBLE_LPS

# **A tyre change is a step, not a cooling curve.**  GT7 does not let the
# rubber cool -- it replaces all four surface temperatures with one identical
# value in a single frame.  Measured on the only stop in the capture set:
# 73.8/67.6/82.9/79.8 C to 60.0/60.0/60.0/60.0 C between one packet and the
# next, three seconds before the fuel started going in.
#
# The signature is the *convergence*, not the value.  Sets are fitted anywhere
# from 60 to 70 C depending on the hour, so nothing can be gated on an
# absolute.  Run across all 132 recorded laps this fires exactly once, on the
# one real tyre change: no false positives anywhere in the capture set.
#
# This is the only detector for a **tyres-only stop**, which previously had no
# code path at all -- pit entry was reachable through refuelling alone.
TYRE_SWAP_DROP_C = 5.0
TYRE_SWAP_SPREAD_C = 0.5
# The change is observed with the car at a standstill in the box.  The gate is
# generous against that rather than tight, because the cost of missing a stop
# is a whole stint mis-attributed and the cost of a loose gate is nothing --
# four corners do not converge within half a degree while the car is driving.
TYRE_SWAP_MAX_SPEED_KPH = 10.0

# Race-start gates.  See the module docstring for why both exist.
RACE_START_SPEED_KMH = 80.0
GRID_LOW_SPEED_KMH = 30.0


class Phase(enum.Enum):
    IDLE = "idle"          # no car on track
    ON_TRACK = "on_track"  # car on track, race not running
    RACING = "racing"      # race started (race sessions only)
    IN_PIT = "in_pit"
    FINISHED = "finished"


class SessionKind(enum.Enum):
    PRACTICE = "practice"
    RACE = "race"


class EventKind(enum.Enum):
    LAP_COMPLETED = "lap_completed"
    RACE_STARTED = "race_started"
    RACE_FINISHED = "race_finished"
    PIT_ENTRY = "pit_entry"
    PIT_EXIT = "pit_exit"


@dataclass(frozen=True)
class SessionEvent:
    kind: EventKind
    data: dict


@dataclass
class Lap:
    """One completed lap.  `compound` is filled in later by the driver."""
    lap_num: int
    lap_time_ms: int
    best_lap_ms: int
    delta_ms: int
    fuel_start: float
    fuel_end: float
    fuel_used: float
    position: int
    is_pit_lap: bool
    is_out_lap: bool
    recorded_at: float = field(default_factory=time.time)
    compound: str | None = None
    # The ratios actually fitted, read off the packet rather than the sheet.
    # This is what catches "the sheet says one gearbox, the car has another",
    # which is otherwise invisible until a whole session has been run on it.
    gear_ratios: list[float] | None = None
    # Whether the set came off during a stop on this lap.  `None` when the lap
    # carried no stop at all -- the question was not asked, so it has no
    # answer.  `False` is a positive claim that the set stayed on, and it is
    # made only where a stop was seen and the temperatures did not step.
    tyres_changed: bool | None = None
    # Litres put in during a stop on this lap, `None` where there was no stop.
    fuel_added_l: float | None = None
    # How far the shift beep was dropped while this lap was driven, in rpm.
    # `None` means nobody recorded it; `0.0` means it was driven on the normal
    # threshold. A lap driven under the app's own fuel-saving instruction is
    # not evidence about the car - see the column comment in `store.schema`.
    short_shift_rpm: float | None = None


class SessionState:
    """Tracks phase, laps and fuel for one practice or race session."""

    def __init__(self, kind: SessionKind = SessionKind.PRACTICE) -> None:
        self.kind = kind
        self._phase = Phase.IDLE
        self._prev: GT7Packet | None = None

        self._laps: list[Lap] = []
        self._fuel_lap_start = 0.0
        self._lap_started_at = 0.0

        self._grid_low_speed_seen = False
        self._prev_laps_completed = 0
        self._laps_in_race = 0
        self._laps_in_race_pre_start_max = 0
        self._race_started_at: float | None = None

        self._pit_lap = False
        self._out_lap_pending = False
        self._fuel_at_pit_entry: float | None = None
        self._gear_ratios: list[float] | None = None
        # (timestamp, litres) over the last `REFUEL_WINDOW_S`.  A refuel is
        # only visible across a window; see the constant for why.
        self._fuel_window: deque[tuple[float, float]] = deque()
        self._tyres_changed_in_stop: bool | None = None
        self._fuel_added_in_stop: float | None = None

    # ------------------------------------------------------------------ state

    @property
    def phase(self) -> Phase:
        return self._phase

    @property
    def laps(self) -> list[Lap]:
        return list(self._laps)

    @property
    def lap_count(self) -> int:
        return len(self._laps)

    @property
    def current_lap_num(self) -> int:
        """1-based number of the lap being driven right now."""
        return len(self._laps) + 1

    @property
    def race_started(self) -> bool:
        return self._race_started_at is not None

    @property
    def laps_in_race(self) -> int:
        return self._laps_in_race

    @property
    def on_track(self) -> bool:
        return bool(self._prev and self._prev.car_on_track)

    @property
    def fuel_level(self) -> float:
        return self._prev.fuel_level if self._prev else 0.0

    @property
    def best_lap_ms(self) -> int:
        times = [lap.lap_time_ms for lap in self._laps if lap.lap_time_ms > 0]
        return min(times) if times else 0

    def laps_remaining(self) -> int | None:
        if self._laps_in_race <= 0:
            return None
        return max(0, self._laps_in_race - len(self._laps))

    def set_compound(self, lap_num: int, compound: str | None) -> None:
        for lap in self._laps:
            if lap.lap_num == lap_num:
                lap.compound = compound
                return

    # ------------------------------------------------------------------ update

    def update(self, packet: GT7Packet) -> list[SessionEvent]:
        """Feed one packet.  Returns the events it produced, oldest first."""
        if packet.paused or packet.loading:
            # **The fuel window cannot survive the gap.**  A pause or a load
            # screen is a hole in the stream of unbounded length, and a reading
            # from before it compared against the first one after it is not a
            # measurement of anything.  Reproduced: the first packet after a
            # paused race restart raised PIT_ENTRY with 40 litres, with the car
            # on track throughout.
            self._fuel_window.clear()
            self._prev = packet
            return []

        now = time.monotonic()
        events: list[SessionEvent] = []

        ratios = [r for r in packet.gear_ratios if r]
        if ratios:
            self._gear_ratios = ratios

        events.extend(self._update_phase(packet, now))
        events.extend(self._update_pit(packet, now))
        events.extend(self._check_lap(packet, now))

        self._prev = packet
        return events

    # --------------------------------------------------------------- internals

    def _update_phase(self, p: GT7Packet, now: float) -> list[SessionEvent]:
        if self._phase is Phase.IDLE:
            if not p.car_on_track:
                return []
            self._phase = Phase.ON_TRACK
            self._fuel_lap_start = p.fuel_level
            self._lap_started_at = now
            # GT7 sends -1 before any lap is complete; clamp so the "increased"
            # comparison below cannot be satisfied spuriously.
            self._prev_laps_completed = max(0, p.laps_completed)
            # A car already stationary when first seen is on the grid.
            self._grid_low_speed_seen = p.speed_kmh < GRID_LOW_SPEED_KMH
            return []

        if self._phase is Phase.ON_TRACK and self.kind is SessionKind.RACE:
            return self._check_race_start(p, now)

        return []

    def _check_race_start(self, p: GT7Packet, now: float) -> list[SessionEvent]:
        if p.laps_in_race > 0:
            self._laps_in_race_pre_start_max = max(
                self._laps_in_race_pre_start_max, p.laps_in_race)

        if p.speed_kmh < GRID_LOW_SPEED_KMH:
            self._grid_low_speed_seen = True

        crossed_line = (
            self._prev_laps_completed >= 0
            and p.laps_completed > self._prev_laps_completed
        )
        launched = self._grid_low_speed_seen and p.speed_kmh > RACE_START_SPEED_KMH
        if not (launched or crossed_line):
            return []

        self._phase = Phase.RACING
        self._race_started_at = now
        # Prefer the pre-start maximum: the live value may already be decremented.
        if self._laps_in_race_pre_start_max > 0:
            self._laps_in_race = self._laps_in_race_pre_start_max
        elif p.laps_in_race > 0:
            self._laps_in_race = p.laps_in_race

        return [SessionEvent(EventKind.RACE_STARTED, {
            "laps_in_race": self._laps_in_race,
            "remaining_time_ms": p.remaining_time_ms,
        })]

    def _refuelling(self, p: GT7Packet, now: float) -> bool:
        """Is the tank going up, at a rate a fuel rig can actually deliver?

        At 60 Hz a 1 L/s fill moves the gauge 0.0167 L between packets, which
        is why the frame-to-frame test this replaced could never see a stop.
        So the rise is measured across `REFUEL_WINDOW_S`, and three things have
        to hold at once:

        * **the car is stationary**, as it is in the box -- matching the
          offline twin `pit_detect.find_stops`, and not merely under the
          pit-lane speed, which the whole of a slow corner also satisfies;
        * **the rise clears `REFUEL_WINDOW_L`**, the floor that makes a real
          fill visible against a channel reported in litres;
        * **the rise is no faster than `MAX_REFUEL_LPS`**, which is what tells
          a fill from a tank being handed back full.

        The window is trimmed strictly by age.  It used to keep a minimum of
        two readings whatever their age, so one reading from before a pause or
        a load screen always survived and could be compared against the first
        one after it.  A stream that drops packets still delivers a hundred
        readings inside two seconds; a stream that stops delivers none, and the
        honest answer while it is rebuilding is "cannot tell".
        """
        self._fuel_window.append((now, p.fuel_level))
        while self._fuel_window and self._fuel_window[0][0] < now - REFUEL_WINDOW_S:
            self._fuel_window.popleft()
        if p.speed_kmh > TYRE_SWAP_MAX_SPEED_KPH or len(self._fuel_window) < 2:
            return False

        levels = [litres for _, litres in self._fuel_window]
        floor = min(levels)
        if p.fuel_level - floor < REFUEL_WINDOW_L:
            return False
        # Time the rise from the *last* reading at the floor, not the first.
        # A car that has been sitting there with a constant tank fills the
        # window with the floor value, and measuring from the oldest of them
        # would divide a one-frame jump by the whole two seconds and call
        # 228 L/s a plausible 1.9.
        started = len(levels) - 1 - levels[::-1].index(floor)
        span_s = (len(levels) - 1 - started) / SAMPLE_HZ
        if span_s <= 0:
            return False
        return (p.fuel_level - floor) / span_s <= MAX_REFUEL_LPS

    def _tyres_swapped(self, p: GT7Packet) -> bool:
        """Did all four corners step to one value in this single frame?

        GT7's tyre change is instantaneous and even.  Nothing a moving car
        does looks like it, and nothing in 132 recorded laps triggers it
        except the one real change.  See `TYRE_SWAP_DROP_C`.
        """
        if self._prev is None or p.speed_kmh > TYRE_SWAP_MAX_SPEED_KPH:
            return False
        before, after = self._prev.tyre_temps, p.tyre_temps
        if not all(b - a >= TYRE_SWAP_DROP_C for b, a in zip(before, after)):
            return False
        return max(after) - min(after) <= TYRE_SWAP_SPREAD_C

    def _update_pit(self, p: GT7Packet, now: float) -> list[SessionEvent]:
        """Infer pit entry and exit from the two signals a stop leaves.

        Either signal opens a stop on its own.  That is the point: a stop for
        tyres only puts nothing into the tank, and a splash of fuel changes no
        tyre, so requiring both would miss whichever kind of stop was made.

        **Neither signal means anything with the car off track.**  Returning to
        the garage refills the tank and refits the tyres, which is both
        signatures at once, and the stop that fabricates carries a measured
        litre figure and a tyre change into the lap row, the export's
        `fuelAddedL`, and -- in a race -- the coordinator's stint plan.  The
        offline twin `pit_detect` has required `on_track` from the start.
        """
        if not p.car_on_track:
            self._fuel_window.clear()
            return []

        if self._prev is None:
            self._fuel_window.append((now, p.fuel_level))
            return []

        refuelling = self._refuelling(p, now)
        swapped = self._tyres_swapped(p)

        if self._phase is not Phase.IN_PIT:
            if not (refuelling or swapped):
                return []
            self._phase = Phase.IN_PIT
            self._pit_lap = True
            # The window's floor, not the previous frame: by the time a fill
            # clears the threshold the tank has already taken 0.3 L, and the
            # oldest reading in the window is the closest thing to the level
            # before it started.
            self._fuel_at_pit_entry = min(litres for _, litres in self._fuel_window)
            # A stop has been seen, so "did the tyres come off" now has an
            # answer rather than being unasked.
            self._tyres_changed_in_stop = swapped
            return [SessionEvent(EventKind.PIT_ENTRY,
                                 {"fuel": self._fuel_at_pit_entry,
                                  "tyres_changed": swapped})]

        if swapped:
            self._tyres_changed_in_stop = True

        if not refuelling and p.speed_kmh > PIT_MAX_SPEED_KMH:
            fuel_added = 0.0
            if self._fuel_at_pit_entry is not None:
                fuel_added = max(0.0, p.fuel_level - self._fuel_at_pit_entry)
            self._fuel_at_pit_entry = None
            self._fuel_added_in_stop = round(fuel_added, 2)
            self._out_lap_pending = True
            self._phase = Phase.RACING if self.race_started else Phase.ON_TRACK
            return [SessionEvent(EventKind.PIT_EXIT, {
                "fuel_added": fuel_added,
                "tyres_changed": bool(self._tyres_changed_in_stop),
            })]

        return []

    def _check_lap(self, p: GT7Packet, now: float) -> list[SessionEvent]:
        if self._phase in (Phase.IDLE, Phase.FINISHED):
            return []

        prev_last_lap_ms = self._prev.last_lap_ms if self._prev else -1
        # The one reliable lap signal: a new positive last_lap_ms.
        if not (p.last_lap_ms > 0 and p.last_lap_ms != prev_last_lap_ms):
            return []
        if not p.car_on_track:
            return []

        lap_time_ms = p.last_lap_ms
        best_ms = p.best_lap_ms
        lap = Lap(
            lap_num=len(self._laps) + 1,
            lap_time_ms=lap_time_ms,
            best_lap_ms=best_ms,
            delta_ms=(lap_time_ms - best_ms) if best_ms > 0 else 0,
            fuel_start=self._fuel_lap_start,
            fuel_end=p.fuel_level,
            fuel_used=max(self._fuel_lap_start - p.fuel_level, 0.0),
            position=p.current_position,
            is_pit_lap=self._pit_lap,
            is_out_lap=self._out_lap_pending,
            gear_ratios=list(self._gear_ratios) if self._gear_ratios else None,
            tyres_changed=self._tyres_changed_in_stop if self._pit_lap else None,
            fuel_added_l=self._fuel_added_in_stop if self._pit_lap else None,
        )
        self._laps.append(lap)
        self._pit_lap = False
        self._out_lap_pending = False
        self._tyres_changed_in_stop = None
        self._fuel_added_in_stop = None

        self._fuel_lap_start = p.fuel_level
        self._lap_started_at = now
        self._prev_laps_completed = p.laps_completed

        events = [SessionEvent(EventKind.LAP_COMPLETED, {"lap": lap})]

        remaining = self.laps_remaining()
        if self.kind is SessionKind.RACE and remaining == 0:
            self._phase = Phase.FINISHED
            events.append(SessionEvent(EventKind.RACE_FINISHED, {
                "laps": len(self._laps),
                "position": p.current_position,
            }))
        return events
