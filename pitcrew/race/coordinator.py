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

from pitcrew.diagnostics import log
from pitcrew.race.calls import (
    BOX_IGNORED_LAPS,
    BOX_NOW,
    HIGH,
    LOW,
    SAVING_RESPONSE,
    STAY_OUT,
    Call,
    RaceState,
    _crossing_the_line,
    clear_stint,
    next_call,
    stay_out_call,
)
from pitcrew.race.clock import RaceClock
from pitcrew.race.expectations import ExpectationTracker
from pitcrew.store.tyres import gap_association_for
from pitcrew.telemetry.session_state import EventKind, Phase

# **How much racing either side of the box means a crossing went missing.**
#
# An ordinary pit lap is about one lap of driving with a stop in the middle, so
# the racing measured either side of the box comes to roughly one lap. Two
# crossings' worth of driving in one row is the failure: every Monza race on
# file recorded 26 rows for 27 laps.
#
# 1.5 rather than something tighter because the out lap is genuinely slower
# than the reference - cold tyres and a pit-lane exit - and the pace this is
# measured against is a median of racing laps. Half a lap of slack absorbs
# that and is still nowhere near the whole extra lap the failure produces.
PIT_RACING_DROPPED_RATIO = 1.5


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
                 # **What the APPROVED plan was costed on**, which is not
                 # always what the evidence says today. At Watkins the plan
                 # was approved at 19:52 on 6.214 L/lap; a qualifying session
                 # ran before the 20:21 green, `build_inputs` re-weighted to
                 # about 6.70, and the engineer then told him he was "burning
                 # 8% under plan" on lap 7 - against a number the plan had
                 # never seen. Against the plan he was 1.6% under, which is
                 # on it. "Under plan" has to mean under THE PLAN, so the
                 # reference is the plan's own stored expectation and the
                 # fresh figure only seeds the working burn.
                 planned_fuel_per_lap_l: float | None = None,
                 fuel_sd_l: float | None = None,
                 wear_per_lap: float | None = None,
                 fuel_capacity_l: float | None = None,
                 short_shift_l_per_1000rpm: float | None = None,
                 lap_time_ms: int | None = None,
                 # Same separation as the burn above: the plan's own stored
                 # figure is the reference, the fresh one only seeds.
                 planned_lap_time_ms: int | None = None,
                 practice_lap_samples: int = 0,
                 practice_fuel_samples: int = 0,
                 # **The stop's own time loss, ex fuel - a TRACK constant**
                 # (CLAUDE.md 5.4), off `events.pit_loss_secs`. Only the fuel
                 # path reads it. None leaves every figure exactly as it was.
                 pit_loss_s: float | None = None,
                 now=None) -> None:
        self.phase = RacePhase.IDLE
        self.plan = plan or {}
        self.state = RaceState(
            fuel_per_lap_l=fuel_per_lap_l, wear_per_lap=wear_per_lap,
            # **Seeded from this event's own practice, then replaced by the
            # race.** Unlike `sigma_ms`, which may never be inherited, this
            # prior is the same car at the same circuit on the same estimator
            # - and without it the first stop of a short race would still be
            # sized on a flat lap, which is precisely the stop that cost six
            # seconds at Watkins.
            fuel_sd_l=fuel_sd_l,
            fuel_capacity_l=fuel_capacity_l,
            # What a short-shift is worth on this car, measured from his own
            # laps. None where nobody has measured it, and the fuel call then
            # names the lever without a number - see `calls.short_shift_for`.
            short_shift_l_per_1000rpm=short_shift_l_per_1000rpm)
        self.refusal: str | None = None
        self.planned_fuel_per_lap_l = (
            planned_fuel_per_lap_l if planned_fuel_per_lap_l is not None
            else fuel_per_lap_l)
        self.planned_lap_time_ms = (
            planned_lap_time_ms if planned_lap_time_ms is not None
            else lap_time_ms)
        self.pit_loss_s = pit_loss_s
        self._burns: list[float] = []
        # **Laps completed after arming but before the green was detected.**
        # `session_state` emits LAP_COMPLETED from `ON_TRACK` onward, so these
        # arrive here and used to be dropped on the floor by the RUNNING gate.
        # They are the racing the clock would otherwise never learn about -
        # see `_on_green` and `race/clock.start`.
        self._pre_green_laps: list = []
        # Lap times fit to judge pace against the plan - see
        # `representative_pace_ms` for what is kept out and why.
        self._pace_ms: list[int] = []
        # An incident seen during the lap in progress: None for no,
        # False for detected, True for driver-reported. Consumed at
        # the crossing - see `note_incident`.
        self._incident_pending: bool | None = None
        # The clock's dropped-lap count as it stood before the lap
        # being handled. See `_corroborate_pit_lap`.
        self._dropped_before_lap = 0
        self._stints = list(self.plan.get("stints") or ())
        # **The app's own race clock**, built at arming and started at the
        # green. GT7's clock is not accurate - the driver measured it - so
        # nothing in race control reads `remaining_time_ms` any more. See
        # `race/clock.py`. `now` is injectable so the tests can drive a race
        # in milliseconds instead of half an hour.
        self._now = now
        self.clock = RaceClock(None, **({"now": now} if now else {}))
        # What the plan expects to execute, and what it is executing. Built
        # from the practice figures the plan was costed with and refreshed by
        # every completed lap - the lap-to-lap reference the driver asked for.
        self.expect = ExpectationTracker(
            planned_lap_time_ms=self.planned_lap_time_ms,
            planned_fuel_per_lap_l=self.planned_fuel_per_lap_l,
            planned_wear_per_lap=wear_per_lap,
            practice_lap_samples=practice_lap_samples,
            practice_fuel_samples=practice_fuel_samples)
        self._apply_stint(0)

    # ------------------------------------------------------------------ arming

    def arm(self, planned: PlanContext | None,
            actual: PlanContext | None) -> bool:
        """Ready the race. Returns False, with a reason, if the plan does not fit."""
        self.refusal = None
        # A re-arm starts the count again: laps from a previous attempt are
        # not this race's.
        self._pre_green_laps = []
        if planned is not None and actual is not None:
            ok, why = planned.matches(actual)
            if not ok:
                self.refusal = why
                return False
        if actual is not None:
            self.state.race_minutes = actual.race_minutes
            self.state.laps_total = self._laps_total_for(actual)
            # **The race's own declared duration, from the event page.**
            # `events.race_laps` holds MINUTES for a timed race - the
            # documented column overload - and `context_from_event` has
            # already sorted that out, so this is the only conversion left.
            self.clock = RaceClock(
                actual.race_minutes * 60.0 if actual.is_timed else None,
                **({"now": self._now} if self._now else {}))
            # **The tyre-temperature association, only where it was measured.**
            # The front-to-rear gap predicts lap time on this driver's own
            # laps at one car and one circuit and is refuted at another, so it
            # is a scoped record rather than a rule - and where there is no
            # record for the car and circuit on track, the conserve call does
            # not exist at all. See `store/tyres.gap_association_for`.
            gap = gap_association_for(actual.car, actual.track, actual.layout)
            if gap is not None:
                self.state.temp_gap_conserve_c = gap.conserve_gap_c
                self.state.temp_gap_quiet_c = gap.quiet_gap_c
                self.state.temp_gap_front_floor_c = gap.front_floor_c
                self.state.temp_gap_s_per_c = gap.slope_s_per_c
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
        # The compound on the car now. Kept where the plan names one and left
        # alone where it does not - a re-plan adopted mid-race carries no
        # compound, and the rubber on the car has not changed because of it.
        if stint.get("compound"):
            self.state.tyre_compound = stint["compound"]
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
        if (event.kind is EventKind.LAP_COMPLETED
                and self.phase is RacePhase.ARMED):
            # **Armed but not green: keep the lap, make no call.** The race is
            # under way and the detector has not noticed yet, which is not a
            # state this app can call a race from - but the lap time is GT7's
            # own and exact, and at the green it is the difference between a
            # clock that counts from lap 1 and one that is a lap light for the
            # whole race. Nothing else here acts on it.
            lap = event.data.get("lap")
            if lap is not None and getattr(lap, "lap_time_ms", 0) > 0:
                self._pre_green_laps.append(lap)
            return None
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
        # **The green flag starts the app's own clock.** RACE_STARTED is
        # already gated on real green-flag conditions (the car seen slow, then
        # over 80 km/h, or the lap counter moving for a rolling start), so
        # this is the moment the race actually began. Everything about time
        # remaining derives from here and from the laps, never from GT7's own
        # clock, which the driver measured as inaccurate.
        # **Started from lap 1, not from here.** The detector is gated on the
        # car being seen slow and then fast, or on the lap counter moving, and
        # it can fire long after the car has actually launched: at Monza on
        # 19 Aug 2026 it fired at the lap-2 crossing, 112 s into the race. A
        # clock started there is short by every lap already run, and so is its
        # lap sum, so the two agree with each other and the reconciliation
        # sees nothing wrong. That race then ran 117 s light to the flag and
        # the stop was fuelled for 17 laps against 13 - 16 L parked.
        #
        # These are GT7's own exact figures for those laps, so the back-dating
        # is a measurement rather than the estimate `note_lap` falls back to.
        # **A caveat worth knowing:** any lap run in this session after arming
        # counts, so arming before a warm-up lap would back-date too far. The
        # clock logs what it did and the snapshot carries `lapsBeforeClock`,
        # because a reconstructed zero point is not an observed one.
        before_ms = sum(int(lap.lap_time_ms) for lap in self._pre_green_laps)
        self.clock.start(before_ms, laps_before=len(self._pre_green_laps))
        # GT7 sends `laps_in_race = -1` for a timed race and session_state
        # clamps that to 0, so this guard never fired there anyway - but a
        # figure that did arrive would be a lap count for a race that has
        # none, and the plan's distance is the better estimate.
        if event.data.get("laps_in_race") and not self.state.race_minutes:
            self.state.laps_total = event.data["laps_in_race"]
        return self._emit()

    # **Green race laps before the race's own burn is used for the fuel call.**
    # Raised from three on measurement: the running median converges inside 2%
    # after ONE lap, so this is not a convergence figure but a precision one.
    # The zero-versus-one-stop decision at the measured race turned on 1.80%,
    # and a three-lap mean resolves to +/-2.18% where five resolves to
    # +/-1.69%. The burn population is filtered the same way the pace
    # population is: a trailing window that admitted his two fuel-saving laps
    # read 12% under the real rate and would have planned the rest of the race
    # on a burn he was only achieving by lifting.
    BURN_LAPS_NEEDED = 5
    # And the same for pace: fewer representative laps than this and the
    # pace against the plan is unknown - not zero, and never lap one.
    PACE_LAPS_NEEDED = 3

    def _on_lap(self, event, packet) -> Call | None:
        lap = event.data["lap"]
        self.state.lap = lap.lap_num
        self.state.laps_since_stop += 1
        self.state.fuel_l = lap.fuel_end
        if lap.position:
            self.state.position = lap.position

        # **The two measures of elapsed race time, reconciled.** The app timer
        # is one; the sum of GT7's own exact lap figures is the other. They
        # should stay a constant distance apart - the standing start - and a
        # gap that grows means the app timer ran through something the laps
        # did not. `RaceClock` prefers the lap sum when they disagree and says
        # so once. See `race/clock.py`.
        #
        # **`event.data["remaining_time_ms"]` is deliberately not read here.**
        # It still travels on the event for anything that wants to display it,
        # but no race-control decision may rest on it: the driver measured
        # GT7's race clock as inaccurate, and an app timer started at the
        # green is the reference.
        # `lap_num` is the clock's backstop for a green detected late - it can
        # see that its first crossing was lap 4 and back-date itself even when
        # nothing was captured before the green. See `race/clock.note_lap`.
        # Sampled before the clock is told about this lap, so that "did the
        # clock count a drop on THIS crossing" is answerable afterwards.
        self._dropped_before_lap = self.clock.laps_dropped
        self.clock.note_lap(lap.lap_time_ms, is_pit_lap=bool(lap.is_pit_lap),
                            lap_num=lap.lap_num)
        self.expect.note_lap(lap)
        self._corroborate_pit_lap(lap)

        # Fuel calls must use what this race is actually burning, not what
        # practice suggested. Told he could push while burning 35% more than
        # planned, the driver would run dry - and the number that produced
        # that advice would have looked perfectly reasonable.
        # Filtered by the expectation tracker, which drops lap one, pit and
        # out laps, incident laps and any lap driven under the app's own
        # short-shift instruction. Kept as a list here too so
        # `observed_fuel_per_lap` keeps its own shape for callers that built
        # the coordinator by hand.
        if lap.fuel_used > 0:
            self._burns.append(lap.fuel_used)
        green = self.expect.race_fuel_per_lap_l()
        if green is not None and self.expect.green_laps() >= self.BURN_LAPS_NEEDED:
            self.state.fuel_per_lap_l = green
        # **And the scatter beside it, because the scatter sizes the fill.**
        # Installed on the same terms as the rate: this race's own laps, or
        # nothing. Where it is None the fill falls back to CLAUDE.md's flat
        # lap, which is the right answer for a burn nobody has measured the
        # spread of - it is only the wrong answer once the spread is known.
        measured_sd = self.expect.race_fuel_sd_l()
        if measured_sd is not None:
            self.state.fuel_sd_l = measured_sd

        # **The lap the car stopped on, before anything reads the pace.** It
        # has to be settled here because the cost is measured against the pace
        # record and this lap must not be in it - and because the same flag
        # decides whether the lap enters the record at all.
        incident = self._incident_pending
        self._incident_pending = None
        if incident is not None:
            self._note_incident(lap, reported=incident)

        # **Lap one never enters the pace record.** It carries the grid and -
        # on race day - a standing start, and it once fed the pace-vs-plan
        # check on its own: "lapping 2% slower than planned" was voiced two
        # minutes into a race whose laps 2-3 promptly beat the reference.
        # Pit and out laps are excluded for the same reason they are excluded
        # offline.
        #
        # **And now incidents too.** The comment here used to end "incidents
        # cannot be flagged live, which is one more reason the pace is a
        # median and never a single lap" - `race/incident_watch.py` is the
        # half that changed. The median still stands, because the watcher
        # catches a car that stopped and not a spin that kept moving; this
        # just stops the ones it does catch from having to be absorbed as
        # outliers by a statistic that was never meant to carry them.
        if (lap.lap_num > 1 and not lap.is_pit_lap and not lap.is_out_lap
                and lap.lap_time_ms > 0 and incident is None):
            self._pace_ms.append(lap.lap_time_ms)

        # The per-lap axle temperature means, where the session state
        # computed them. Both or neither: a one-axle reading would make the
        # asymmetry checks compare a measurement against a gap.
        front = getattr(lap, "tyre_temp_front_c", None)
        rear = getattr(lap, "tyre_temp_rear_c", None)
        if front is not None and rear is not None:
            self.state.note_temps(lap.lap_num, front, rear)

        # **A lap race gets the countdown too, and there it is exact.** The
        # two-to-go and last-lap calls were reachable only on a timed race
        # because only the clock path set the estimate - on a lap race the
        # figure is a regulation the game reports and the call is free.
        if not self.state.race_minutes:
            remaining = self.state.laps_remaining()
            self.state.laps_to_go_estimate = remaining
            self.state.laps_estimate_firm = remaining is not None

        finish = self._update_clock_distance()
        if finish is not None:
            return finish

        folded = self._reconsider_ignored_box()
        if folded is not None:
            self.state.record(folded)
            return folded
        return self._emit()

    def note_incident(self, *, reported: bool = False) -> None:
        """The car stopped mid-lap, or the driver said it did.

        Held until the crossing that ends the lap, because that is when the
        lap has a time to be costed and a number to be named by. `reported`
        travels so the engineer does not announce something the driver told
        it thirty seconds ago and was already answered about.
        """
        if self._incident_pending is None or reported:
            # **Reported wins over detected**, whichever arrived first: being
            # told is being told, and the acknowledgement he already heard is
            # the one that stands.
            self._incident_pending = bool(reported)

    def _note_incident(self, lap, *, reported: bool) -> None:
        """Cost the lap and reset what it made stale."""
        pace = self.representative_pace_ms()
        cost = (int(lap.lap_time_ms - pace)
                if pace is not None and lap.lap_time_ms else None)
        self.state.incident_lap = lap.lap_num
        self.state.incident_cost_ms = cost if cost and cost > 0 else None
        self.state.incident_reported = reported

        # **The stint's temperature occasions speak again.** This is the
        # "reset" half: a trip through the grass or a spell stationary in the
        # gravel leaves the set at a temperature the stint's earlier calls
        # were not about, and "up to temperature" said four laps ago is now a
        # claim about a set that has since stopped. The HISTORY is kept - it
        # is the same rubber, and its own trend is the evidence - but every
        # occasion is armed again so the engineer may speak about it.
        self.state.temp_said = set()
        self.state.temp_conserve_lap = None
        log("race").info(
            "incident on lap %s: %s, cost %s",
            lap.lap_num, "driver-reported" if reported else "detected",
            f"{cost} ms" if cost else "not costed - no pace reference")

    def _corroborate_pit_lap(self, lap) -> None:
        """A second, independent opinion on whether a crossing went missing.

        **`race/clock.py` already finds dropped laps** and finds them on pit
        laps specifically - the guard that used to exclude them hid the event
        it was most needed for. Its test is the app timer's span against GT7's
        own lap time, `> 1.6x`, and at Monza on 18 Aug that read 1.74 where a
        clean pit lap would have read 1.16.

        **But that margin depends on how long the stop was.** A long stop eats
        into the ratio: the stationary time sits inside GT7's lap figure, so a
        splash-and-dash leaves a wider gap for a missed crossing to hide in
        than a full service does.

        `Lap.pit_racing_ms` does not have that weakness. It is the driving
        either side of the box, measured from the frame GT7 took the car -
        which is why the speed-step detector had to be wired first - with the
        stop excluded by construction. Roughly one lap on an ordinary pit lap,
        whatever the stop cost.

        **Nothing here changes `laps_dropped`.** The clock owns that count and
        two detectors incrementing one counter is how a single missed crossing
        becomes two. This corroborates, and where the two disagree it says so:
        CLAUDE.md §4.1's rule is that a disagreement between two measures is
        the finding, and is worth more than either statement alone.
        """
        racing_ms = getattr(lap, "pit_racing_ms", None)
        if not lap.is_pit_lap or not racing_ms:
            return
        pace = self.representative_pace_ms()
        if not pace:
            # No reference yet. Silence rather than a ratio against a guess.
            return
        ratio = racing_ms / pace
        by_racing = ratio >= PIT_RACING_DROPPED_RATIO
        by_clock = self.clock.laps_dropped > self._dropped_before_lap
        if by_racing and by_clock:
            log("race").warning(
                "lap %s: both measures agree a crossing was missed - %.0f s "
                "of racing either side of the box against a %.0f s lap "
                "(ratio %.2f)", lap.lap_num, racing_ms / 1000.0,
                pace / 1000.0, ratio)
        elif by_racing:
            log("race").warning(
                "lap %s: the racing either side of the box came to %.0f s "
                "against a %.0f s lap (ratio %.2f), which is a missed "
                "crossing - but the clock did not see one. Two measures "
                "disagree; the lap count may be one light",
                lap.lap_num, racing_ms / 1000.0, pace / 1000.0, ratio)
        elif by_clock:
            log("race").warning(
                "lap %s: the clock counted a dropped lap, but the racing "
                "either side of the box was only %.0f s against a %.0f s lap "
                "(ratio %.2f) - which is one lap of driving, not two. Two "
                "measures disagree; this may have been a pause",
                lap.lap_num, racing_ms / 1000.0, pace / 1000.0, ratio)

    def _laps_after_stops(self, lap_ms: int | None,
                          left: int | None) -> int | None:
        """`laps_left` again, with the stops still to come out of the clock.

        Pending stops are the stints still ahead of the one being run. During
        the stop itself `stint_index` has not advanced yet - `_apply_stint`
        moves it on PIT_EXIT - so the stop in progress still counts, which is
        right: the clock has not absorbed its time at a crossing yet, and the
        in-box refuel call is made squarely inside that window.
        """
        pending = max(0, len(self._stints) - 1 - self.state.stint_index)
        if not pending or not self.pit_loss_s:
            return left
        return self.clock.laps_left(lap_ms, less_s=pending * self.pit_loss_s)

    def _update_clock_distance(self) -> Call | None:
        """A timed race's distance, from the app clock and the median lap.

        **This is the whole point of owning the clock.** The distance used to
        be the approved plan's own estimate, frozen at arming, patched by a
        packet field the driver does not trust when the estimate ran out a lap
        early. Now it is recomputed at every crossing: the time left divided
        by the lap this race is actually running, ceiling'd because GT7 drops
        the flag at the first crossing after the clock expires.

        Returns the chequered-flag call when the clock has run out - a lap
        completing with the app timer expired IS the final lap - and None
        otherwise. A lap race is untouched: its distance is a regulation, not
        an estimate.
        """
        if not self.state.race_minutes or not self.clock.running:
            return None
        # **The ACHIEVED median - every completed lap, incidents included -
        # and not the clean pace.** Measured on the 30-minute race: the
        # achieved median of 121.51 s predicts fifteen laps, which is what
        # happened, while the clean-pace median of 119.62 s and the practice
        # median both predict sixteen. An incident lap does not make the car
        # slower but it does consume the clock, and the clock is the question.
        lap_ms = self.expect.achieved_lap_time_ms() or self.planned_lap_time_ms
        left = self.clock.laps_left(lap_ms)
        self.state.clock_corroborated = self.clock.corroborated
        # Carried onto the state so the lap-count calls can say which fault
        # they are living with - see `calls._laps_to_go`.
        self.state.laps_dropped = self.clock.laps_dropped
        # **How wrong the median may be before the answer changes.** Measured
        # on that race, the first four crossings had 0.12-0.66 s of margin
        # against a lap-time spread of 2.04 s - the prediction there is not
        # merely uncertain, it is unresolvable, and the honest output is not a
        # number. From lap five the margin runs 0.9 s and upward.
        margin = self.clock.laps_left_margin_s(lap_ms)
        sigma = self.expect.sigma_ms()
        self.state.laps_estimate_firm = bool(
            margin is not None and sigma is not None
            and margin >= sigma / 1000.0)
        if left is None:
            # No lap time to divide by. The plan's frozen distance is all
            # there is, and it stands rather than being replaced by a guess.
            return None
        self.state.laps_total = self.state.lap + left
        # **What the fuel path counts, which is not what the flag counts.**
        # A stop is a minute of clock that covers no ground. `laps_total`
        # ceilings over the whole window including it, so before a stop is
        # taken the distance reads one lap long and the fill at that stop is
        # sized for a lap that will never be driven - 6 L at Monza, and one
        # litre is one second stationary at the measured 1.002 L/s.
        #
        # Only the *ex-fuel* loss is taken off, and deliberately: the discount
        # cuts the fill, so an overstated one runs him dry. The refuel time is
        # the larger half and it is left in, which errs toward a litre spare.
        self.state.laps_after_stops = self._laps_after_stops(lap_ms, left)
        # The two-to-go and last-lap calls read this. They are safe from two
        # laps out - measured margins of 13.3 s and 31.2 s at the end of laps
        # 13 and 14 - which is well clear of anything the median can be wrong
        # by, and it is why those two are the only lap-count facts spoken.
        self.state.laps_to_go_estimate = left
        if left > 0:
            return None
        # **The flag.** The app timer has expired and a lap has just been
        # completed, so this crossing is the finish. GT7 emits nothing the
        # app can trust here - a timed race never raised RACE_FINISHED at all
        # before the clock did it, and one measured 30-minute race ended with
        # the engineer mid-box-call and no chequered flag.
        self.phase = RacePhase.FINISHED
        self.state.finished = True
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
        """The race's own burn, or None before enough green laps exist.

        Green laps only. Measured: burn on a green lap has a CV of 2.0% and
        burn on any lap at all has a CV of 10.4%, the whole spread coming from
        incident laps and laps he was deliberately saving on.
        """
        green = self.expect.race_fuel_per_lap_l()
        if green is None or self.expect.green_laps() < self.BURN_LAPS_NEEDED:
            return None
        return green

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

    # Laps to wait after asking for a saving before judging it. Two, because
    # one lap is a lap and not a trend - and because the shortfall the
    # instruction was meant to cover is still there while nobody has said.
    SAVING_RESPONSE_AFTER = 2

    def _emit(self) -> Call | None:
        call = next_call(self.state)
        if call is not None:
            self.state.record(call)
            if call.short_shift_drop_rpm:
                # The loop opens here. It has never closed.
                self._saving_asked_lap = self.state.lap
                self._saving_answered = False
            return call

        # **Nothing else won the lap, so close the loop if one is open.**
        # Ranked below every real call and above the colour tier: it is not an
        # instruction, but it is the answer to one the engineer gave.
        answer = self._saving_response()
        if answer is not None:
            self.state.record(answer)
        return answer

    def _saving_response(self) -> Call | None:
        asked = getattr(self, "_saving_asked_lap", None)
        if asked is None or getattr(self, "_saving_answered", False):
            return None
        if self.state.lap - asked < self.SAVING_RESPONSE_AFTER:
            return None
        response = self.expect.saving_response(asked)
        if response is None:
            return None
        # Said once per instruction. Asking again gets a fresh answer; this
        # one is closed whatever it found, including "cannot resolve" - which
        # is an answer, and repeating it every lap would be chatter.
        self._saving_answered = True
        return Call(SAVING_RESPONSE, self.state.lap, response.call(),
                    "", confidence=HIGH if response.measurable else LOW)

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
            # **The lap he is ON, not the last one he finished.** `lap` counts
            # crossings, so during the thirteenth lap it reads 12 - and a
            # driver report is always about the lap in progress. Told "lap 12
            # is out" while driving 13, he would correct a mistake the app had
            # not made and the right lap would stay in.
            "lapInProgress": self.state.lap + 1,
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
            # The app's own clock, and the lap-time sum that corroborates it.
            **self.clock.as_snapshot(),
            # What the plan expects to execute against what it is executing -
            # the lap-to-lap reference the driver asked for, so the screen and
            # the PTT can both answer "are we on the plan".
            **self.expect.as_snapshot(),
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
