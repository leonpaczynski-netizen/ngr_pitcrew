"""Session and lap state derived from the GT7 packet stream.

This replaces the old 1081-line `RaceStateTracker`.  Almost all of that class
existed to serve features that no longer exist (setup evidence, qualifying,
coaching).  What is kept here is the handful of detectors that were expensive
to get right:

* **Lap completion** fires on `last_lap_ms` changing to a new positive value,
  latched against the last value FILED and never against the previous frame.
  GT7's `laps_completed` is not the trigger — its indexing convention differs
  between race types — but it **is** checked against the app's own count at
  every crossing, and a disagreement is reported out loud. Those are two
  different questions and conflating them cost a lap: an indexing offset is a
  constant you can calibrate once, a dropped edge is not recoverable by
  anything, and trading the second away to avoid the first is what filed 19
  rows for a 20-lap race at Fuji.
* **Race start** requires `(the car was seen below 30 km/h) AND speed > 80`,
  or the lap counter increasing.  The low-speed gate stops a formation lap, or
  the app being started mid-session, from faking lights-out.  The lap-counter
  branch is deliberately left ungated so rolling starts still fire.  **The
  counter it compares against retires itself on a drop** - a `laps_completed`
  lower than the baseline cannot be this session's, and one carried over from
  the last session put the green 111.2 s late at Daytona and 112 s late at
  Monza.  See `_retire_a_foreign_lap_count`.
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
from types import SimpleNamespace

from pitcrew.analysis.refuel import MAX_PLAUSIBLE_LPS
from pitcrew.analysis.runs import out_lap_after_in_lap
from pitcrew.diagnostics import log
from pitcrew.telemetry.packet import GT7Packet
from pitcrew.telemetry.pit_detect import entered_the_pits, relocated
from pitcrew.telemetry.recorder import SAMPLE_HZ

# One `SessionState` holds one recording session, so the lap being filed is
# always in the same session as the one before it.
_THIS_SESSION = SimpleNamespace(session_id=None)

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

# **How big a single-frame fuel rise means the game just fuelled the car.**
# GT7 fills at about 1 L/s against a 60 Hz stream, so a real refuel moves the
# tank 0.0167 L between packets - three orders of magnitude below this. The
# grid fill is a step: session 88 stepped 49.88 -> 100.0 in one frame while
# stationary. See `_rebaseline_on_grid_fill`.
GRID_FILL_STEP_L = 1.0

# Race-start gates.  See the module docstring for why both exist.
RACE_START_SPEED_KMH = 80.0
GRID_LOW_SPEED_KMH = 30.0

# **The GT7 race clock no longer ends a race here, and nothing in race
# control reads it.**
#
# A `TIMED_RACE_EXPIRED_MAX_MS` gate used to sit at this point: a lap
# completing with `remaining_time_ms` at or just above zero finished the race.
# It rested on an unverified assumption - that GT7 clamps the field at zero
# after expiry rather than going negative - and it was logged once a lap
# precisely because nothing had certified that.
#
# It is gone because the assumption is not the problem. **The driver measured
# GT7's race clock as inaccurate**, so a finish gated on it is a finish gated
# on a number he does not trust. The race layer now runs its own monotonic
# timer started at the green (`race/clock.py`), corroborated against the sum
# of GT7's own exact per-lap times, and it decides the finish: a lap
# completing with the app timer expired is the final lap.
#
# `remaining_time_ms` still travels on LAP_COMPLETED for anything that merely
# wants to show it. Nothing may decide anything on it.


def _burn(started_with: float | None, ended_with: float | None,
          added: float | None = None) -> float:
    """Fuel used across a lap, counting anything put in during it.

    **A tank that ends fuller than it started has been filled, not un-burned.**
    Clamping that difference at zero is what filed `fuel_used = 0.0` against two
    Fuji laps that plainly used fuel: the pit lap, where refuelling put more in
    than the lap took out, and lap 1, whose reference was the 49.92 L lobby tank
    read 78 s before the game filled it to 100 L on the grid.

    Neither is a lap the app cannot measure - both are laps whose arithmetic was
    missing a term. The pit lap's term is the fill, which `_fuel_added_in_stop`
    already measures; lap 1's is the grid fill, which `update` now re-baselines
    against. So the answer is the true burn rather than a clamp *or* a null.

    **Not null, deliberately, and this is the constraint that decides it.**
    `laps.fuel_used` is `NOT NULL DEFAULT 0.0` and SQLite cannot relax that
    without rebuilding the table - which cascades into `lap_frames` and is
    forbidden. A None here reaches `if lap.fuel_used > 0` in the race
    coordinator and the practice screen, and an unhandled TypeError inside a Qt
    slot does not raise on Windows, it aborts the process. Every consumer
    already treats 0.0 as "no reading", so a residual zero is read as absent
    exactly as it should be; what changed is that it is now rare and honest
    rather than routine and wrong.
    """
    if started_with is None or ended_with is None:
        return 0.0
    used = started_with - ended_with + (added or 0.0)
    return used if used > 0.0 else 0.0


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
    # **GT7's own completed-lap count, as it read at this crossing.**
    #
    # This module counts laps from `last_lap_ms` changing and not from here,
    # on the stated grounds that "GT7's lap counter is unreliable and its
    # indexing convention differs between race types". That may well be true.
    # **It has never been checked, because nothing recorded the field** - so
    # the claim and its refutation are equally unavailable.
    #
    # It matters now. Every Monza race on file recorded 26 rows for 27 laps
    # driven: the crossing inside GT7's pit sequence never reaches the app, and
    # a count one light asks for one lap of fuel too much - about six litres,
    # six seconds standing still at 1 L/s. If this field survives the pit
    # sequence it is the answer; if it does not, that is worth knowing once
    # rather than assuming forever.
    #
    # Recorded, not yet trusted. One race settles it.
    laps_completed: int | None = None
    # **The race clock at this crossing, stamped on the way past.** Filled by
    # the coordinator, which owns the clock; None in practice and qualifying,
    # where there is no race clock to read. See `schema.py`'s note on why a
    # timed race's accuracy was never checkable without these.
    race_elapsed_s: float | None = None
    race_remaining_s: float | None = None
    laps_dropped: int | None = None
    # **Seconds of this lap actually spent RACING, on a pit lap only.**
    #
    # The time from the last crossing to the moment GT7 took the car into the
    # box, plus the time from release to this crossing - the stop itself
    # excluded. On an ordinary pit lap that is about one lap of driving.
    #
    # It exists because every Monza race on file recorded 26 rows for 27 laps:
    # the crossing inside GT7's pit sequence never reaches the app, so ONE row
    # holds nearly two laps of driving and the count comes out one light. A
    # count one light asks for a lap of fuel too much - about six litres, six
    # seconds standing still at the measured 1 L/s.
    #
    # **Measured here, judged in the race layer**, which is where the
    # representative pace to judge it against already lives. None on any lap
    # that was not a pit lap, and None where the entry frame was never seen.
    pit_racing_ms: int | None = None
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
    # Mean tyre surface temperature over the lap's frames, per axle, degC.
    # Computed live so the race engineer can speak about the one tyre channel
    # GT7 actually broadcasts - it used to exist only in the offline
    # aggregation, which is why a whole race was driven without a single
    # temperature call being possible. `None` where no frame carried temps.
    tyre_temp_front_c: float | None = None
    tyre_temp_rear_c: float | None = None


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
        # The lap time of the last lap actually FILED. See `_check_lap`: the
        # edge is latched against this and never against the previous frame,
        # so a frame the detector declines to act on cannot destroy it.
        self._last_lap_filed_ms = -1
        # GT7's counter less the app's own at the first lap filed. A constant
        # while nothing is dropped; a step in it is a crossing that went
        # missing, and `_check_lap` says so out loud.
        self._gt7_lap_offset: int | None = None
        self._laps_in_race = 0
        self._laps_in_race_pre_start_max = 0
        self._race_started_at: float | None = None

        self._pit_lap = False
        self._out_lap_pending = False
        self._fuel_at_pit_entry: float | None = None
        # When GT7 took the car (monotonic), and when it let it go again.
        # Both None outside a stop. See `Lap.pit_racing_ms`.
        self._pit_entry_at: float | None = None
        self._pit_exit_at: float | None = None
        self._gear_ratios: list[float] | None = None
        # (timestamp, litres) over the last `REFUEL_WINDOW_S`.  A refuel is
        # only visible across a window; see the constant for why.
        self._fuel_window: deque[tuple[float, float]] = deque()
        self._tyres_changed_in_stop: bool | None = None
        self._fuel_added_in_stop: float | None = None
        # **A stop that straddles the start/finish line is still one stop.**
        # GT7 puts the line INSIDE the pit lane at Daytona, Fuji and Monza, so
        # the crossing fires while the car is standing in the box: the ENTRY
        # lands on one lap and the FILL on the next. The close below used to
        # clear `_fuel_added_in_stop` and `_pit_lap` at every crossing, so the
        # fill - measured correctly, seconds later - was thrown away, the
        # out-lap's `start - end` went negative, and `_burn` clamped it to a
        # fabricated `fuel_used = 0.0`. Measured on session 127 lap 13:
        # 6.81 -> 62.96 L in the box and ~7 L burned finishing the lap, filed
        # as zero with `fuel_added_l` NULL. CLAUDE.md rule 9.
        self._stop_straddled = False
        # **And it may survive exactly one crossing.** A stop that spans two
        # whole laps is not a stop, it is a stuck flag - a missed PIT_EXIT
        # from packet loss, a retirement in the box, a stop that ends at the
        # flag. Left unbounded it filed `fuel_added_l = 0.0` and a definite
        # `tyres_changed = False` on ordinary green laps that were never near
        # the pit lane. CLAUDE.md rule 10: a guard that refuses a reading must
        # be able to retire its own reference.
        self._straddle_laps = 0
        # Per-lap axle temperature accumulators, reset at each lap boundary.
        # Sums rather than lists: at 60 Hz a lap is several thousand frames
        # and the only question ever asked is the mean.
        self._temp_sum_front = 0.0
        self._temp_sum_rear = 0.0
        self._temp_frames = 0
        # **No race-clock state is kept here any more.** A `_timed_clock_ran`
        # flag used to exist so that a timed race could be finished off
        # `remaining_time_ms`; the driver measured that clock as inaccurate,
        # and the finish moved to the race layer's own timer. Keeping a
        # shadow of it here would only invite the dependency back.

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

        if packet.car_on_track:
            # Accumulated before `_check_lap` so the frame that completes a
            # lap still belongs to it. Grid frames land in lap one, which is
            # what the offline aggregation does too - lap one's mean says
            # what the tyres were at the start, formation heat included.
            temps = packet.tyre_temps
            self._temp_sum_front += (temps[0] + temps[1]) / 2.0
            self._temp_sum_rear += (temps[2] + temps[3]) / 2.0
            self._temp_frames += 1
        self._rebaseline_on_grid_fill(packet)
        events.extend(self._update_phase(packet, now))
        events.extend(self._update_pit(packet, now))
        events.extend(self._check_lap(packet, now))

        self._prev = packet
        return events

    # --------------------------------------------------------------- internals

    def _rebaseline_on_grid_fill(self, p: GT7Packet) -> None:
        """Take lap one's fuel reference from the grid, not from the lobby.

        **The reference was being read up to a minute before the game fuelled
        the car.** `_update_phase` stamps `_fuel_lap_start` the moment the car
        is first seen on track, which in a race is the lobby: session 88's lap
        1 recorded `fuel_start = 49.92` and the frames show the tank stepping
        49.88 -> 100.0 at t = 77.78 s, stationary on the grid. The lap then
        "used" -44 litres, which the clamp turned into a positive claim of
        none.

        So a rise before the race has started re-stamps the reference. Bounded
        three ways, because "the tank went up" is also what a pit stop looks
        like: only before the green, only while the car is not moving, and only
        for a step far larger than any refuel delivers in one frame - GT7 fills
        at about 1 L/s against a 60 Hz stream, so a real fill moves 0.0167 L
        between packets and this needs a whole litre.
        """
        if self._phase is not Phase.ON_TRACK or self._prev is None:
            return
        if p.speed_kmh > GRID_LOW_SPEED_KMH:
            return
        if p.fuel_level - self._prev.fuel_level < GRID_FILL_STEP_L:
            return
        self._fuel_lap_start = p.fuel_level

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
            # **Seeded from the first packet, not left at -1.** The latch fires
            # on a CHANGE, so an unseeded one files a lap the moment the app
            # meets a stream that already carries a lap time - joining a
            # session in progress, or opening on a menu still holding the last
            # session's. That is what the `car_on_track` gate in `_check_lap`
            # was really protecting against, and seeding here protects against
            # it without also discarding the pit-lane crossing, which is the
            # one crossing that gate reliably threw away.
            self._last_lap_filed_ms = p.last_lap_ms
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

        self._retire_a_foreign_lap_count(p)

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

    def _retire_a_foreign_lap_count(self, p: GT7Packet) -> None:
        """Drop a `laps_completed` baseline that belongs to another session.

        **This is the whole of the Monza green-flag defect, and it cost the
        driver an entire opening lap twice.** `_update_phase` seeds
        `_prev_laps_completed` from the first packet it sees on track, and the
        first packet it sees on track can still be carrying the LAST session's
        payload. Measured, frame by frame, off session 127 (Daytona, 4 Sep
        2026, 20 laps, 7,034 frames in lap one):

        * frames 0-1 - `gt7_laps_completed` **5**, speed 278.7 km/h,
          `last_lap_ms` 103,795. That is the previous session's final lap, two
          frames of it, 33 ms;
        * frame 2 onward - `gt7_laps_completed` **0**, speed 80.0 km/h,
          `last_lap_ms` absent. This race, from the line;
        * frame 352 (t = 5.87 s) - **0 -> 1**, GT7 saying lap one is under way;
        * frame 7,033 (t = 117.2 s) - **1 -> 2**, the lap-one crossing.

        The baseline was seeded at **5** off frame 0, so `crossed_line` asked
        for a count above 5 and the lap-one crossing at 2 did not clear it.
        `_check_lap` then re-seeded the baseline to GT7's real 2 when it filed
        lap one, and the lap-TWO crossing at 3 finally cleared it: green at
        22:16:25, **4 min 21 s after the session opened and 111.2 s of racing
        late**, with lap one receiving no calls at all. The launch branch could
        not save it either - `_grid_low_speed_seen` was seeded False off the
        same 278.7 km/h frame and Daytona's minimum speed over the rest of the
        lap is 58.9 km/h, so nothing below 30 was ever seen again.

        **CLAUDE.md rule 10: a rule that refuses a reading must be able to
        refuse its own baseline.** A count that DROPS cannot be this session's
        history - GT7's counter only ever rises within a session - so the drop
        is the falsifier, and it retires the reference rather than being
        refused against it. Rule 11 is the other half: this is state that
        outlived a session and was read as if it belonged to this one.

        **And the accepts are logged, not only the refusals.** The ratchet was
        invisible for a whole race precisely because the number setting the bar
        never appeared in the log.
        """
        if p.laps_completed is None or p.laps_completed < 0:
            # GT7 sends -1 before any lap is complete. Not a drop - an absence.
            return
        if p.laps_completed >= self._prev_laps_completed:
            return
        log("session").info(
            "GT7's lap counter dropped %d -> %d, which cannot happen inside "
            "one session - the baseline came from the previous one. Retiring "
            "it: the green is now judged against %d, not %d.",
            self._prev_laps_completed, p.laps_completed,
            p.laps_completed, self._prev_laps_completed)
        self._prev_laps_completed = p.laps_completed

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
        # **The speed step, and it is the earliest of the three by seconds.**
        # GT7 takes the car over at pit entry and the speed drops from racing
        # to nothing BETWEEN TWO CONSECUTIVE FRAMES - measured at Monza as
        # 145.6 / 227.3 / 226.3 / 211.1 kph to zero, once per pit lap and never
        # outbound. Refuelling only becomes visible once the tank has actually
        # started to climb, which is several seconds after the car stopped
        # being driven, and a tyre swap later still.
        #
        # That lateness was the whole problem. `pit_racing_ms` below measures
        # the racing either side of the stop, and measured from a signal that
        # arrives late it would silently charge the stop's opening seconds to
        # the driving.
        #
        # **Only across genuinely adjacent frames.** The step is a one-frame
        # event, so it is only evidence if the two frames really are one frame
        # apart: a dropped datagram can put 200 km/h next to 0 km/h in the
        # received stream with an ordinary braking zone in between, and that
        # would read as a pit entry on a lap the driver never pitted. GT7's
        # own packet counter is what makes the test answerable.
        adjacent = (p.packet_id is not None
                    and self._prev.packet_id is not None
                    and p.packet_id - self._prev.packet_id == 1)
        # **And not a car the game moved.** A practice reset is the same
        # step - 265 km/h to 0 between two frames at session 158 lap 11 - but
        # the car lands 168 m away in the box in that same frame, where a
        # real entry freezes it in place. A reset is not a stop and makes no
        # in-lap (`pit_detect.Stop.reset`).
        taken = (adjacent
                 and entered_the_pits(self._prev.speed_kmh, p.speed_kmh)
                 and not relocated(self._prev, p))

        if self._phase is not Phase.IN_PIT:
            if not (refuelling or swapped or taken):
                return []
            self._phase = Phase.IN_PIT
            self._pit_lap = True
            self._pit_entry_at = now
            self._pit_exit_at = None
            # The window's floor, not the previous frame: by the time a fill
            # clears the threshold the tank has already taken 0.3 L, and the
            # oldest reading in the window is the closest thing to the level
            # before it started.
            self._fuel_at_pit_entry = min(litres for _, litres in self._fuel_window)
            # A stop has been seen. **The swap detector's silence is not "no
            # tyres".** It fires on all four corners stepping down in ONE
            # frame at walking pace, and at Deep Forest (6 Sep 2026, lap 13)
            # it did not fire on a stop that fitted a fresh set - the gauge
            # read 0.42 -> 0.00 across it. So a swap seen is True and a swap
            # not seen is None, never False: False is the positive claim
            # "fuel only", and the coordinator acts on it (rule 3).
            self._tyres_changed_in_stop = True if swapped else None
            return [SessionEvent(EventKind.PIT_ENTRY,
                                 {"fuel": self._fuel_at_pit_entry,
                                  # Tri-state here too: at entry the swap
                                  # has usually not happened yet, so "not
                                  # seen" is unknown, never "no".
                                  "tyres_changed": True if swapped else None,
                                  # Which signal found it. `speed-step` is the
                                  # frame-exact one; the others are seconds
                                  # late and say so by being named.
                                  "by": ("speed-step" if taken
                                         else "refuelling" if refuelling
                                         else "tyre-change")})]

        if swapped:
            self._tyres_changed_in_stop = True

        if not refuelling and p.speed_kmh > PIT_MAX_SPEED_KMH:
            fuel_added = 0.0
            if self._fuel_at_pit_entry is not None:
                fuel_added = max(0.0, p.fuel_level - self._fuel_at_pit_entry)
            self._fuel_at_pit_entry = None
            self._fuel_added_in_stop = round(fuel_added, 2)
            self._pit_exit_at = now
            self._out_lap_pending = True
            self._phase = Phase.RACING if self.race_started else Phase.ON_TRACK
            return [SessionEvent(EventKind.PIT_EXIT, {
                "fuel_added": fuel_added,
                # Tri-state, as held: True when the swap was seen, None when
                # it was not. `bool(None)` here used to emit False, and the
                # coordinator then kept the old set's wear history across a
                # fresh set and fitted a rate through the discontinuity.
                "tyres_changed": self._tyres_changed_in_stop,
            })]

        return []

    def _pit_racing_ms(self, now: float) -> int | None:
        """Milliseconds of this pit lap spent driving, stop excluded.

        `(entry - lap start) + (now - exit)`. **None unless both halves are
        known**: without the exit the car is still in the box and this
        crossing is not the end of a pit lap, and without the entry there is
        nothing to subtract the stop from. A partial figure here would be
        indistinguishable from a short lap, which is the opposite of the
        finding it exists to support.
        """
        if not self._pit_lap:
            return None
        if self._pit_entry_at is None or self._pit_exit_at is None:
            return None
        before = self._pit_entry_at - self._lap_started_at
        after = now - self._pit_exit_at
        if before < 0 or after < 0:
            return None
        return int(round((before + after) * 1000.0))

    def _say_if_a_crossing_went_missing(self, p: GT7Packet) -> None:
        """Compare the app's count with GT7's, and say so when they part.

        **The witness was already being written and read by nothing.** Every
        lap row carries `laps_completed`, GT7's own counter, and across
        session 88 it steps by one on every row except the pit row, where it
        steps 5 -> 7. That single difference is the whole diagnosis, and it
        sat in the archive unexamined while the race ran a lap short, the
        run-in counted down early, and the fuel at the stop was sized against
        a lap that had already gone by.

        Said at the crossing rather than at the flag, because a count that is
        wrong is wrong for every call made after it, and **silence from an
        adviser is indistinguishable from an adviser with nothing to say.**

        It does not fabricate a row. The lap GT7 timed cannot be reconstructed
        live - the app never saw its crossing and so never timed it - and a
        lap time invented here would be indistinguishable downstream from one
        the game reported. `tools/repair_dropped_laps.py` restores it
        afterwards from GT7's own lap list, which is a number that exists.
        """
        if p.laps_completed is None or p.laps_completed < 0:
            return
        offset = p.laps_completed - len(self._laps)
        if self._gt7_lap_offset is None:
            self._gt7_lap_offset = offset
            return
        if offset == self._gt7_lap_offset:
            return
        missed = offset - self._gt7_lap_offset
        self._gt7_lap_offset = offset
        if missed < 0:
            # The app counted a lap GT7 did not. Not a drop, and not
            # something this has ever seen - reported rather than corrected,
            # because a correction for a cause nobody has diagnosed is a guess.
            log("race").error(
                "the app has filed %d lap(s) MORE than GT7 counted by lap %d "
                "- this has no known cause and the lap count should not be "
                "trusted for the rest of this session", -missed, len(self._laps))
            return
        log("race").error(
            "GT7 counted %d crossing(s) the app did not, inside lap %d. Its "
            "counter reads %d against %d rows filed. This is what a stop at a "
            "circuit whose pit lane spans the start/finish line does; the lap "
            "count is short by that much from here until the race is "
            "re-derived", missed, len(self._laps), p.laps_completed,
            len(self._laps))

    def _check_lap(self, p: GT7Packet, now: float) -> list[SessionEvent]:
        if self._phase in (Phase.IDLE, Phase.FINISHED):
            return []

        # **Against the last time FILED, not the last frame seen.**
        #
        # This compared `p.last_lap_ms` with the previous frame's, so any
        # frame on which the event was discarded destroyed the edge for good:
        # the next frame's "previous" already carried the new time, the `!=`
        # was false from then on, and the lap was gone with nothing logged.
        # One skipped frame, one lap, silently.
        #
        # That is the same defect shape as the gauge ratchet - a baseline that
        # advances even when nothing was believed - and it is why session 88
        # filed 19 rows for a 20-lap race. Latched, a discarded frame costs a
        # delay rather than a lap.
        if not (p.last_lap_ms > 0 and p.last_lap_ms != self._last_lap_filed_ms):
            return []
        # **`car_on_track` is deliberately NOT a gate here.** GT7 takes the car
        # over at pit entry and clears the flag through the pit sequence -
        # which is exactly when the crossing this method exists to catch
        # happens, because at circuits whose pit lane spans the line the stop
        # straddles a lap. Being off track is a reason to doubt this lap's
        # fuel and tyre readings, not a reason to pretend the lap did not
        # happen; the flag travels on the row so the doubt travels with it.

        # **A stop that is still running when the line goes by is split here,
        # and each half is charged to the lap it happened on.**
        # `_fuel_at_pit_entry` is stamped when the car stops, so one
        # `fuel_added` would span the WHOLE fill; crediting all of it to the
        # out-lap overstates that lap's burn by exactly the litres that went in
        # before the crossing. So: the entry lap takes what has gone in so far,
        # and the baseline moves to the line so the exit measures only the
        # rest. Small at Daytona - the tank was at 6.81 L as the line went by -
        # and proportional to the pre-crossing fill anywhere the box sits
        # further back.
        if (self._phase is Phase.IN_PIT
                and self._fuel_at_pit_entry is not None
                and p.fuel_level is not None):
            self._fuel_added_in_stop = round(
                max(0.0, p.fuel_level - self._fuel_at_pit_entry), 2)
            self._fuel_at_pit_entry = p.fuel_level

        lap_time_ms = p.last_lap_ms
        best_ms = p.best_lap_ms
        temp_front = temp_rear = None
        if self._temp_frames:
            temp_front = round(self._temp_sum_front / self._temp_frames, 1)
            temp_rear = round(self._temp_sum_rear / self._temp_frames, 1)
        lap = Lap(
            lap_num=len(self._laps) + 1,
            lap_time_ms=lap_time_ms,
            best_lap_ms=best_ms,
            delta_ms=(lap_time_ms - best_ms) if best_ms > 0 else 0,
            fuel_start=self._fuel_lap_start,
            fuel_end=p.fuel_level,
            # The fill is part of the lap's arithmetic, not a reason to give
            # up on it - see `_burn`. On a pit lap this is what turns a
            # negative difference into the real burn.
            fuel_used=_burn(self._fuel_lap_start, p.fuel_level,
                            self._fuel_added_in_stop
                            if (self._pit_lap or self._stop_straddled)
                            else None),
            position=p.current_position,
            is_pit_lap=self._pit_lap,
            # **THE RULE, on the live side too** - the lap after an in-lap is
            # an out-lap, decided by the one function everything else calls.
            # The pit EXIT alone put the flag on the in-lap itself wherever
            # the exit came before the next crossing the app saw (the Monza
            # stops on file, sessions 52, 53, 58 and 78), and the lap after it
            # was counted: `is_pit_lap` followed by a lap that was not an
            # out-lap. **That flag on the in-lap is right, and it is what
            # satisfies the rule** (the driver, 15 Sep 2026): the row holds the
            # stop, the release and the drive back up to speed past the line,
            # so it IS the out-lap and the next row is a flying lap -
            # `runs.holds_its_own_out_lap`, which needs the lap before too.
            is_out_lap=(self._out_lap_pending
                        or out_lap_after_in_lap(
                            self._laps[-1] if self._laps else None,
                            _THIS_SESSION,
                            self._laps[-2] if len(self._laps) >= 2 else None)),
            gear_ratios=list(self._gear_ratios) if self._gear_ratios else None,
            # **`None` until the stop has actually closed.** The swap is read
            # at PIT_ENTRY, before it has happened, so a `False` filed on the
            # entry lap of a straddled stop is not "no tyres" - it is "not yet
            # asked", and s127 L12 filed exactly that against a set that WAS
            # changed. Rule 3. Resolved only once `_fuel_added_in_stop` exists,
            # which is the same instant the car is released.
            tyres_changed=(self._tyres_changed_in_stop
                           if ((self._pit_lap or self._stop_straddled)
                               and self._pit_exit_at is not None)
                           else None),
            fuel_added_l=(self._fuel_added_in_stop
                          if (self._pit_lap or self._stop_straddled)
                          else None),
            pit_racing_ms=self._pit_racing_ms(now),
            tyre_temp_front_c=temp_front,
            tyre_temp_rear_c=temp_rear,
            # Recorded beside the app's own count so the two can be compared
            # after a race instead of one being asserted over the other.
            laps_completed=(int(p.laps_completed)
                            if p.laps_completed is not None
                            and p.laps_completed >= 0 else None),
        )
        self._laps.append(lap)
        self._last_lap_filed_ms = lap_time_ms
        self._say_if_a_crossing_went_missing(p)
        self._pit_entry_at = None
        self._pit_exit_at = None
        self._pit_lap = False
        self._out_lap_pending = False
        # **Cleared only when the stop is actually over.** Still IN_PIT at the
        # crossing means the car is standing in the box and the fill has not
        # finished, so what is left of it belongs to the lap that has not
        # started yet.
        #
        # ⚠️ **And the baseline moves to the line, or the out-lap is paid
        # twice.** `_fuel_at_pit_entry` is stamped when the car stops, so a
        # single `fuel_added` spans the WHOLE fill. Crediting all of it to the
        # out-lap overstates that lap's burn by exactly the litres that went in
        # before the crossing - small at Daytona, where the tank was at 6.81 L
        # when the line went by, and proportional to the pre-crossing fill
        # anywhere the box sits further before it. Each half of the stop is
        # charged to the lap it happened on.
        if self._phase is Phase.IN_PIT and self._straddle_laps < 1:
            self._stop_straddled = True
            self._straddle_laps += 1
        else:
            if self._stop_straddled and self._phase is Phase.IN_PIT:
                log("race").warning(
                    "a pit stop has now spanned two laps without the car "
                    "leaving the box - the exit was missed, so the fill and "
                    "the tyre swap are recorded as unknown rather than as "
                    "zero. Laps from here are ordinary laps.")
            self._stop_straddled = False
            self._straddle_laps = 0
            self._tyres_changed_in_stop = None
            self._fuel_added_in_stop = None
        self._temp_sum_front = 0.0
        self._temp_sum_rear = 0.0
        self._temp_frames = 0

        self._fuel_lap_start = p.fuel_level
        self._lap_started_at = now
        self._prev_laps_completed = p.laps_completed

        # The clock travels with the lap so the race layer can tell "the
        # plan's estimated distance is done" from "the flag has fallen" -
        # a timed race that outruns its estimate by a lap is still a race.
        events = [SessionEvent(EventKind.LAP_COMPLETED, {
            "lap": lap,
            "remaining_time_ms": p.remaining_time_ms,
        })]

        remaining = self.laps_remaining()
        # **A lap race finishes here; a timed race does not.** The lap count
        # is a regulation and this class can see it. The clock is not - see
        # the note where `TIMED_RACE_EXPIRED_MAX_MS` used to be - so a timed
        # race's finish belongs to the race layer, which has an accurate timer
        # of its own and reconciles it against these very lap times.
        if self.kind is SessionKind.RACE and remaining == 0:
            self._phase = Phase.FINISHED
            events.append(SessionEvent(EventKind.RACE_FINISHED, {
                "laps": len(self._laps),
                "position": p.current_position,
            }))
        return events
