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
* **Pit laps** are inferred from fuel increasing at pit-lane speed, because
  GT7 does not broadcast a pit flag.

The session kind is set by the app from what the driver chose to do, never
guessed from the game — GT7 classifies any multi-car lobby as a race.

Threading: `update()` is called on the UDP thread and returns events rather
than dispatching them, so the caller decides which thread acts on them.
"""
from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field

from pitcrew.telemetry.packet import GT7Packet

# Speed below which a fuel increase means the pit lane rather than a physics
# quirk.  GT7 pit limiters sit at 60-80 km/h; 120 leaves generous margin.
PIT_MAX_SPEED_KMH = 120.0

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
            self._prev = packet
            return []

        now = time.monotonic()
        events: list[SessionEvent] = []

        ratios = [r for r in packet.gear_ratios if r]
        if ratios:
            self._gear_ratios = ratios

        events.extend(self._update_phase(packet, now))
        events.extend(self._update_pit(packet))
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

    def _update_pit(self, p: GT7Packet) -> list[SessionEvent]:
        """Infer pit entry/exit from refuelling at pit-lane speed."""
        if self._prev is None:
            return []

        refuelling = (
            p.fuel_level > self._prev.fuel_level + 0.05
            and p.speed_kmh < PIT_MAX_SPEED_KMH
        )

        if refuelling and self._phase is not Phase.IN_PIT:
            self._phase = Phase.IN_PIT
            self._pit_lap = True
            self._fuel_at_pit_entry = self._prev.fuel_level
            return [SessionEvent(EventKind.PIT_ENTRY, {"fuel": self._prev.fuel_level})]

        if self._phase is Phase.IN_PIT and not refuelling and p.speed_kmh > PIT_MAX_SPEED_KMH:
            fuel_added = 0.0
            if self._fuel_at_pit_entry is not None:
                fuel_added = max(0.0, p.fuel_level - self._fuel_at_pit_entry)
            self._fuel_at_pit_entry = None
            self._out_lap_pending = True
            self._phase = Phase.RACING if self.race_started else Phase.ON_TRACK
            return [SessionEvent(EventKind.PIT_EXIT, {"fuel_added": fuel_added})]

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
        )
        self._laps.append(lap)
        self._pit_lap = False
        self._out_lap_pending = False

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
