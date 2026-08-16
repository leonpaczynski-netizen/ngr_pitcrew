"""Running the race: arm, wait for green, follow the plan, adapt.

Two rules from the brief shape this:

* **Nothing fires until the race actually starts.** Start Race arms the
  coordinator; the plan does not begin until the car is on track and the
  start/finish line has been crossed. Arming is not starting.
* **The plan is refused if it was built for a different race.** A stint plan
  from another car, track or race length is worse than no plan, because the
  driver would act on it.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass

from pitcrew.race.calls import (
    BOX_IGNORED_LAPS,
    BOX_NOW,
    STAY_OUT,
    Call,
    RaceState,
    _crossing_the_line,
    clear_stint,
    next_call,
    stay_out_call,
)
from pitcrew.telemetry.session_state import EventKind, Phase


class RacePhase(enum.Enum):
    IDLE = "idle"          # not armed
    ARMED = "armed"        # waiting for the car to go green
    RUNNING = "running"
    FINISHED = "finished"


@dataclass(frozen=True)
class PlanContext:
    """What the approved plan was built for."""
    car: str
    track: str
    layout: str | None
    race_laps: int
    # Minutes when the race runs to the clock. **A timed race has no lap count
    # to be told**: `events.race_laps` holds the minutes for one (the spin box
    # is relabelled and saved there), so reading it as a distance raced a
    # 45-minute Monza as a 45-lap one. Kept separate so the two can never be
    # confused again, and so the plan match compares like with like.
    race_minutes: float | None = None

    @property
    def is_timed(self) -> bool:
        return bool(self.race_minutes)

    def matches(self, other: "PlanContext") -> tuple[bool, str]:
        if self.car != other.car:
            return False, f"plan was built for {self.car}, car is {other.car}"
        if self.track != other.track:
            return False, f"plan was built for {self.track}, track is {other.track}"
        if self.layout != other.layout:
            return False, (f"plan was built for the {self.layout} layout, "
                           f"this is {other.layout}")
        if self.is_timed != other.is_timed:
            kind = "a timed race" if self.is_timed else "a lap race"
            now = "a timed race" if other.is_timed else "a lap race"
            return False, f"plan was built for {kind}, this is {now}"
        if self.is_timed:
            if self.race_minutes != other.race_minutes:
                return False, (f"plan was built for {self.race_minutes:g} "
                               f"minutes, this race is {other.race_minutes:g}")
            return True, ""
        if self.race_laps != other.race_laps:
            return False, (f"plan was built for {self.race_laps} laps, "
                           f"this race is {other.race_laps}")
        return True, ""


class RaceCoordinator:
    """Turns telemetry events into engineer calls against an approved plan."""

    def __init__(self, plan: dict | None = None,
                 fuel_per_lap_l: float | None = None,
                 wear_per_lap: float | None = None,
                 fuel_capacity_l: float | None = None,
                 short_shift_l_per_1000rpm: float | None = None) -> None:
        self.phase = RacePhase.IDLE
        self.plan = plan or {}
        self.state = RaceState(
            fuel_per_lap_l=fuel_per_lap_l, wear_per_lap=wear_per_lap,
            fuel_capacity_l=fuel_capacity_l,
            # What a short-shift is worth on this car, measured from his own
            # laps. None where nobody has measured it, and the fuel call then
            # names the lever without a number - see `calls.short_shift_for`.
            short_shift_l_per_1000rpm=short_shift_l_per_1000rpm)
        self.refusal: str | None = None
        self.planned_fuel_per_lap_l = fuel_per_lap_l
        self._burns: list[float] = []
        # Lap times fit to judge pace against the plan - see
        # `representative_pace_ms` for what is kept out and why.
        self._pace_ms: list[int] = []
        self._stints = list(self.plan.get("stints") or ())
        self._apply_stint(0)

    # ------------------------------------------------------------------ arming

    def arm(self, planned: PlanContext | None,
            actual: PlanContext | None) -> bool:
        """Ready the race. Returns False, with a reason, if the plan does not fit."""
        self.refusal = None
        if planned is not None and actual is not None:
            ok, why = planned.matches(actual)
            if not ok:
                self.refusal = why
                return False
        if actual is not None:
            self.state.race_minutes = actual.race_minutes
            self.state.laps_total = self._laps_total_for(actual)
        self.phase = RacePhase.ARMED
        return True

    def _laps_total_for(self, actual: PlanContext) -> int | None:
        """The distance to count down from, or None when there is none.

        For a timed race that is **the approved plan's own distance**: the
        laps follow from the stops, so the plan is the only thing that has an
        opinion about how far this race goes. With no plan there is no
        estimate to give, and the calls say nothing about laps remaining
        rather than counting down a number of minutes.
        """
        if not actual.is_timed:
            return actual.race_laps
        return self._planned_distance()

    def _planned_distance(self) -> int | None:
        """The lap the approved plan expects to finish on.

        Taken from the last stint's own start and length rather than by
        summing, because `adopt` rewrites the tail of the plan from the
        current lap and the stints either side of that seam do not add up.
        """
        if not self._stints:
            return None
        last = self._stints[-1]
        end = int(last.get("start_lap") or 1) + int(last.get("laps") or 0) - 1
        return end or None

    def disarm(self) -> None:
        self.phase = RacePhase.IDLE

    @property
    def armed(self) -> bool:
        return self.phase is RacePhase.ARMED

    @property
    def running(self) -> bool:
        return self.phase is RacePhase.RUNNING

    # ------------------------------------------------------------------ laps

    def _apply_stint(self, index: int) -> None:
        self.state.stint_index = index
        if index >= len(self._stints):
            self.state.stint_ends_on_lap = None
            self.state.next_compound = None
            return
        stint = self._stints[index]
        start = stint.get("start_lap") or 1
        self.state.stint_ends_on_lap = start + stint.get("laps", 0) - 1
        following = self._stints[index + 1] if index + 1 < len(self._stints) else None
        self.state.next_compound = following.get("compound") if following else None
        # How long the stint after the next stop runs, so the fill at that
        # stop is for that stint and not for the whole rest of the race.
        self.state.next_stint_laps = (following.get("laps") if following
                                      else None)
        # Whether a stop comes after that stint too. When it does not, the
        # next stint runs to the flag, and the fill call clamps it against
        # the laps actually remaining - a stale plan's stint length must not
        # size a fill that has to reach the end of the race.
        self.state.further_stop_planned = index + 2 < len(self._stints)
        # The last stint runs to the flag; there is no stop at the end of it.
        if following is None:
            self.state.stint_ends_on_lap = None

    def handle(self, event, packet=None) -> Call | None:
        """Feed one telemetry event. Returns the call to make, if any."""
        if event.kind is EventKind.RACE_STARTED:
            return self._on_green(event)
        if self.phase is not RacePhase.RUNNING:
            return None
        if event.kind is EventKind.LAP_COMPLETED:
            return self._on_lap(event, packet)
        if event.kind is EventKind.PIT_ENTRY:
            self.state.in_pit = True
            return None
        if event.kind is EventKind.PIT_EXIT:
            self.state.in_pit = False
            # The stop carries whether the tyres came off. Discarding it made
            # every fuel-only stop a fresh set and silenced the end-of-window
            # call for the stint after it.
            clear_stint(self.state,
                        tyres_changed=event.data.get("tyres_changed"))
            self._apply_stint(self.state.stint_index + 1)
            return None
        if event.kind is EventKind.RACE_FINISHED:
            return self._on_finish(event)
        return None

    def _on_green(self, event) -> Call | None:
        if self.phase is not RacePhase.ARMED:
            # Arming is not starting, and a race that started without being
            # armed is not this app's race.
            return None
        self.phase = RacePhase.RUNNING
        # GT7 sends `laps_in_race = -1` for a timed race and session_state
        # clamps that to 0, so this guard never fired there anyway - but a
        # figure that did arrive would be a lap count for a race that has
        # none, and the plan's distance is the better estimate.
        if event.data.get("laps_in_race") and not self.state.race_minutes:
            self.state.laps_total = event.data["laps_in_race"]
        return self._emit()

    # Below this the race has not shown enough of its own burn to trust it
    # over the practice figure.
    BURN_LAPS_NEEDED = 3
    # And the same for pace: fewer representative laps than this and the
    # pace against the plan is unknown - not zero, and never lap one.
    PACE_LAPS_NEEDED = 3

    # A timed race's lap count is the plan's own estimate. When it runs out
    # while the packet clock still shows this much time, the estimate was a
    # lap short and the driver is genuinely going round again - the count is
    # extended rather than the engineer falling silent on a real racing lap.
    EXTRA_LAP_CLOCK_MS = 20_000

    def _on_lap(self, event, packet) -> Call | None:
        lap = event.data["lap"]
        self.state.lap = lap.lap_num
        self.state.laps_since_stop += 1
        self.state.fuel_l = lap.fuel_end
        if lap.position:
            self.state.position = lap.position

        # **The estimated distance yields to the clock.** For a timed race
        # `laps_total` is the plan's derived distance; if it undershoots by
        # a lap, `laps_remaining()` hits zero one lap early and every call
        # stands down on a lap he is actually racing. The session state now
        # sends the packet clock with each completed lap: meaningfully more
        # than zero left means the flag has not fallen, so the countdown is
        # stretched by one and the engineer keeps talking.
        remaining_ms = event.data.get("remaining_time_ms")
        if (self.state.race_minutes and self.state.laps_total is not None
                and self.state.laps_remaining() == 0
                and remaining_ms is not None
                and remaining_ms > self.EXTRA_LAP_CLOCK_MS):
            self.state.laps_total += 1

        # Fuel calls must use what this race is actually burning, not what
        # practice suggested. Told he could push while burning 35% more than
        # planned, the driver would run dry - and the number that produced
        # that advice would have looked perfectly reasonable.
        if lap.fuel_used > 0:
            self._burns.append(lap.fuel_used)
        if len(self._burns) >= self.BURN_LAPS_NEEDED:
            ordered = sorted(self._burns)
            self.state.fuel_per_lap_l = ordered[len(ordered) // 2]

        # **Lap one never enters the pace record.** It carries the grid and -
        # on race day - a standing start, and it once fed the pace-vs-plan
        # check on its own: "lapping 2% slower than planned" was voiced two
        # minutes into a race whose laps 2-3 promptly beat the reference.
        # Pit and out laps are excluded for the same reason they are excluded
        # offline; incidents cannot be flagged live, which is one more reason
        # the pace is a median and never a single lap.
        if (lap.lap_num > 1 and not lap.is_pit_lap and not lap.is_out_lap
                and lap.lap_time_ms > 0):
            self._pace_ms.append(lap.lap_time_ms)

        # The per-lap axle temperature means, where the session state
        # computed them. Both or neither: a one-axle reading would make the
        # asymmetry checks compare a measurement against a gap.
        front = getattr(lap, "tyre_temp_front_c", None)
        rear = getattr(lap, "tyre_temp_rear_c", None)
        if front is not None and rear is not None:
            self.state.note_temps(lap.lap_num, front, rear)

        folded = self._reconsider_ignored_box()
        if folded is not None:
            self.state.record(folded)
            return folded
        return self._emit()

    def _reconsider_ignored_box(self) -> Call | None:
        """A box call ignored twice is answered, not repeated.

        The stint pointer only advances on a PIT_EXIT, so a skipped stop used
        to leave the plan frozen and the box call re-firing verbatim every
        lap - nine times in one measured race, the last on the chequered-flag
        crossing, while the one call the driver needed (he was 0.4 laps short
        of a feasible zero-stop) was computed and outranked every lap.

        Two laps past the planned stop with the driver still out, the
        engineer re-reads the race: if the fuel aboard reaches the flag
        within the short-shift lever's range, the stay-out is said ONCE and
        the box call is retired - the plan folds to what he is actually
        doing. If the fuel genuinely cannot reach, the box call stands and
        escalates instead (`_box_now`).
        """
        state = self.state
        if (BOX_NOW not in state.said or STAY_OUT in state.said
                or state.in_pit or state.finished or not state.past_box_lap):
            return None
        if _crossing_the_line(state):
            # The distance is covered and the finish event is one packet
            # behind this one. A plan whose last stop sat two laps before
            # the end once put the fold exactly here - "Staying out? You
            # can make it." voiced on the chequered-flag crossing, recorded
            # as a driver decision about a race that was already over.
            return None
        overdue = state.lap - (state.stint_ends_on_lap or 0)
        if overdue < BOX_IGNORED_LAPS:
            return None
        call = stay_out_call(state)
        if call is None:
            return None
        # Internally adopt the zero-stop shape for the remainder: one stint
        # to the flag, no compound waiting, the fuel target becomes the flag.
        remaining = state.laps_remaining()
        if remaining:
            self.adopt((remaining,))
        else:
            state.stint_ends_on_lap = None
            state.next_stint_laps = None
            state.next_compound = None
        return call

    def observed_fuel_per_lap(self) -> float | None:
        if len(self._burns) < self.BURN_LAPS_NEEDED:
            return None
        ordered = sorted(self._burns)
        return ordered[len(ordered) // 2]

    # The pace window is wider than the minimum so that incident laps -
    # which cannot be flagged live - can be dropped and a median still
    # taken. A lap this far over the race's own best so far is an incident,
    # not noise: his measured lap-to-lap noise is about 0.8% of a two-minute
    # lap, while the measured incidents run 5-10% over. 4% splits the two
    # populations with margin on both sides.
    PACE_WINDOW_LAPS = 5
    PACE_OUTLIER_FRACTION = 0.04

    def representative_pace_ms(self) -> int | None:
        """The pace this race is showing, or None before it has shown one.

        A median over the last `PACE_WINDOW_LAPS` clean laps, never a single
        lap: the driver's measured lap-to-lap noise sits right at the
        re-plan threshold on a two-minute lap, so a single-lap trigger is a
        coin flip. And a median of only three is not enough either - the
        measured race had *adjacent* incident laps (crawl, then a spin
        recovery, +6% and +9%), and two of three carry the median with them.
        So laps more than `PACE_OUTLIER_FRACTION` over the race's own best
        are dropped as incidents first; fewer than `PACE_LAPS_NEEDED` clean
        laps in the window means the pace is unknown right now - None, not a
        number built out of trouble.
        """
        if len(self._pace_ms) < self.PACE_LAPS_NEEDED:
            return None
        cutoff = min(self._pace_ms) * (1.0 + self.PACE_OUTLIER_FRACTION)
        window = sorted(ms for ms in self._pace_ms[-self.PACE_WINDOW_LAPS:]
                        if ms <= cutoff)
        if len(window) < self.PACE_LAPS_NEEDED:
            return None
        return window[len(window) // 2]

    def _on_finish(self, event) -> Call | None:
        self.phase = RacePhase.FINISHED
        self.state.finished = True
        if event.data.get("position"):
            self.state.position = event.data["position"]
        return self._emit()

    def _emit(self) -> Call | None:
        call = next_call(self.state)
        if call is not None:
            self.state.record(call)
        return call

    def stops_planned(self) -> int:
        """Stops still in the plan from here, for the re-plan comparison."""
        return max(0, len(self._stints) - 1 - self.state.stint_index)

    def adopt(self, stint_laps) -> None:
        """Take on a re-plan the driver accepted.

        The stints already completed are left alone: what changes is the
        shape of the race from here, not a rewrite of what already happened.
        The stint currently running is replaced, not kept - keeping it would
        leave the stop at the end of it in the plan, which is exactly the stop
        the driver just cancelled.
        """
        done = self._stints[:self.state.stint_index]
        start = self.state.lap + 1
        fresh = []
        for laps in stint_laps:
            fresh.append({"laps": laps, "compound": None, "fuel_l": None,
                          "start_lap": start})
            start += laps
        self._stints = done + fresh
        self._apply_stint(self.state.stint_index)
        if self.state.race_minutes:
            # A timed race's distance is an output of the plan, so a new plan
            # is a new distance. Leaving it would count down to the old one.
            self.state.laps_total = self._planned_distance()

    # ---------------------------------------------------------------- answers

    def snapshot(self) -> dict:
        """What the pit wall shows, and what the PTT answers from."""
        return {
            "phase": self.phase.value,
            "lap": self.state.lap,
            "lapsTotal": self.state.laps_total,
            # Set for a timed race, where `lapsTotal` is the plan's expected
            # distance rather than a regulation, so nothing downstream reads
            # it as one.
            "raceMinutes": self.state.race_minutes,
            "lapsRemaining": self.state.laps_remaining(),
            "position": self.state.position,
            "fuelL": self.state.fuel_l,
            "lapsOfFuel": self.state.laps_of_fuel(),
            "lapsToStop": self.state.laps_to_stop(),
            "nextCompound": self.state.next_compound,
            "inPit": self.state.in_pit,
            # Whether there is an approved plan at all. `lapsToStop` is None
            # both for the last stint of a real plan and for a race armed with
            # no plan, and the two are different answers to "when do I box".
            "hasPlan": bool(self._stints),
        }


def context_from_event(event: dict, plan: dict | None = None) -> PlanContext:
    """The race as the event page declares it.

    **`events.race_laps` holds MINUTES when `race_type` is `time`.** The spin
    box is relabelled and saved to the same column; `race_minutes` is never
    written. The strategy path compensates on read (`evidence.py`); every
    other reader has to do it here or it races a 45-minute event as 45 laps.
    """
    declared = int(event.get("race_laps") or 0)
    timed = (event.get("race_type") or "laps") == "time"
    return PlanContext(
        car=event.get("car_name") or "",
        track=event.get("track") or "",
        layout=event.get("layout"),
        race_laps=0 if timed else declared,
        race_minutes=float(declared) if timed else None,
    )


def context_from_stored(stored: dict, event: dict) -> PlanContext:
    """A plan's saved context, read under the event's own race type.

    Contexts saved before a timed race had a `race_minutes` of its own carry
    the MINUTES in `race_laps` - the same confusion the column has. Read
    beside the event they still describe the race they were built for; read
    literally they would refuse every timed plan ever approved, on race day,
    which is the one moment a refusal cannot be worked around.
    """
    if "race_minutes" in stored:
        return PlanContext(**stored)
    length = context_from_event({"race_type": event.get("race_type"),
                                 "race_laps": stored.get("race_laps")})
    return PlanContext(
        car=stored.get("car") or "",
        track=stored.get("track") or "",
        layout=stored.get("layout"),
        race_laps=length.race_laps,
        race_minutes=length.race_minutes,
    )


def phase_from_session(phase: Phase) -> RacePhase:
    """Map the telemetry phase onto the engineer's, for display only."""
    if phase is Phase.RACING:
        return RacePhase.RUNNING
    if phase is Phase.FINISHED:
        return RacePhase.FINISHED
    return RacePhase.ARMED
