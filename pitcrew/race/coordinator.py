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
    STATUS,
    stop_still_needed,
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
# The most crossings the live counter will accept as "missed" inside one lap.
# A pit stop loses one. More than two means the counter is not describing this
# race - a restart, a session change, a bad read - and a fuel call must not be
# sized from it. See `RaceCoordinator.note_packet`.
MAX_LIVE_MISSED_LAPS = 2
# How long a counter discrepancy must persist before it is believed, in
# packets at 60 Hz - about two seconds. Every ordinary crossing shows one for
# a handful of frames, because GT7's counter moves before the app's own
# LAP_COMPLETED lands. A missed crossing shows one for the rest of the lap.
LAP_COUNTER_HOLD_FRAMES = 120


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
                 mandatory_stops: int = 0,
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
        # **Why the plan's stops exist**, in the plan's own word for it. Only
        # a fuel-bound stop can be cancelled by a tankful, and a plan that
        # does not say keeps every stop it named - see `calls.stop_still_needed`
        # for the Fuji race this is on file from.
        self.state.plan_binding_constraint = self.plan.get("binding_constraint")
        self._mandatory_stops = int(mandatory_stops or 0)
        self._note_mandatory_stops()
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
        # **GT7's own lap counter at the last crossing the app recorded.**
        # None until the first crossing under green. See `note_packet`.
        # **GT7's counter minus the app's, learned at the first crossing
        # under green.** None until then. Learned at a crossing and not at the
        # green because only at a crossing is the relationship exact - mid-lap
        # the game is already counting the lap in progress, and an offset one
        # too high silently disables the detector. See `note_packet`.
        self._gt7_offset: int | None = None
        # Consecutive packets the current discrepancy has survived, and the
        # value it has been surviving as. Both, because the hold has to re-arm
        # when the discrepancy CHANGES - see `note_packet`.
        self._gt7_pending = 0
        self._gt7_pending_value = 0

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

    def _note_mandatory_stops(self) -> None:
        """How many required stops are still owed.

        **Known, not unknown.** `events.mandatory_stops` is a real column with
        a real default, so this is a count and never a `None` standing in for
        one - and that matters because the first draft of `stop_still_needed`
        treated it as unknown, kept every stop on that basis, and could
        therefore never fire at all. A rule that cannot fire is the thing this
        codebase keeps building by accident.

        Stops taken is the stint index: the car is in stint N having made N
        stops, and `_apply_stint` advances it across each one.
        """
        self.state.mandatory_stops_left = max(
            0, self._mandatory_stops - self.state.stint_index)

    def _apply_stint(self, index: int, *, over_a_stop: bool = False) -> None:
        """Move to stint `index`.

        `over_a_stop` says a set of tyres has just been fitted, which is the
        one time an unnamed compound must not be read as "unchanged".
        """
        self.state.stint_index = index
        if index >= len(self._stints):
            self.state.stint_ends_on_lap = None
            self.state.next_compound = None
            return
        self._note_mandatory_stops()
        stint = self._stints[index]
        # The compound on the car now. Named by the plan, or - when the plan
        # does not name one - unchanged, because a re-plan adopted mid-race
        # carries no compound and the rubber has not changed because of it.
        #
        # **Except across a stop, where "unchanged" is false and stale.**
        # Fresh rubber went on and the plan cannot say which, so the honest
        # value is `None` and not the last stint's compound (CLAUDE.md §4.3).
        # `_tag_lap_compound` writes this onto every lap of the stint, and its
        # own docstring is the argument: a wear rate attributed to the wrong
        # tyre is not a gap in the model, it is a corruption of it.
        if stint.get("compound"):
            self.state.tyre_compound = stint["compound"]
        elif over_a_stop:
            self.state.tyre_compound = None
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
            self._apply_stint(self.state.stint_index + 1,
                              over_a_stop=True)
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
        # **The offset between the two lap counters, learned once, here.**
        # At a crossing the relationship is exact; mid-lap GT7 is already
        # counting the lap in progress and the offset would come out one high,
        # which disables the detector silently. See `note_packet`.
        #
        # **Read off the Lap, not off `packet`.** The only production caller
        # is the controller's race-event slot, which calls `handle(event)`
        # with no packet at all - so a version of this that read the argument
        # learned nothing, ever, and the detector was dead in the race while
        # passing every test. `Lap.laps_completed` carries the same GT7 field
        # and travels on the event.
        counted = getattr(lap, "laps_completed", None)
        if counted is None and packet is not None:
            counted = getattr(packet, "laps_completed", None)
        if (self._gt7_offset is None and counted is not None
                and counted >= 0 and lap.lap_num > 0):
            self._gt7_offset = counted - lap.lap_num
        # A crossing resets the pending discrepancy: whatever it was, the app
        # has just counted a lap and the two are being compared afresh.
        self._gt7_pending = 0
        self._gt7_pending_value = 0
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
            # **The flag, for a lap race, and nothing was declaring it.**
            #
            # `SessionState` raises RACE_FINISHED when `laps_in_race` minus the
            # number of lap ROWS it filed reaches zero - and a crossing inside
            # GT7's pit sequence never reaches the app, so at Fuji it filed 19
            # rows for 20 laps and the count stopped one short. The race never
            # ended: `race_runs.finished_at` stayed null, no chequered flag was
            # called, no export was ever generated, and the session closed on
            # shutdown 16 minutes 48 seconds after the last crossing. Job 3 did
            # not run at all.
            #
            # The dropped crossing and the missing finish are the same defect,
            # and the correction already exists one layer up: `laps_remaining`
            # here counts `lap + laps_missed()`, which at Fuji is 19 + 1 = 20.
            # It was computed every crossing and nothing read it as a finish.
            #
            # Same rule as the timed race two hundred lines below - a lap
            # completing with nothing left to run IS the final lap - and it
            # cannot fire early: `laps_missed` only ever grows the count by a
            # crossing the game itself counted and the app did not.
            if remaining == 0 and self.phase is RacePhase.RUNNING:
                self.phase = RacePhase.FINISHED
                self.state.finished = True
                if lap.position:
                    self.state.position = lap.position
                return self._emit()

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

    def note_packet(self, packet) -> None:
        """Compare GT7's own lap counter against the app's, every packet.

        **This is the only detector that can see a missed crossing while the
        car is still in the box.** The clock's check runs when a lap completes
        and is therefore always one lap late; measured at Road Atlanta on
        23 Aug 2026 that lateness was two minutes and one second, and the
        in-box fuel call went out in the gap asking for twelve laps of fuel
        against nine to run. Thirteen litres crossed the line unburnt, which
        at that league's 2.00 L/s is six and a half seconds parked.

        GT7 increments `laps_completed` at the crossing itself, including the
        one inside the pit sequence that never reaches the app as a
        LAP_COMPLETED. So while the app still believes it is on lap N, a
        counter reading past the app's own crossings is a crossing the app
        missed, and it says so within a packet.

        **The field is marked unreliable for the race finish and that caution
        stands.** It is not read as a count here, only as a delta against the
        app's own crossings - which on the twenty-two laps of that race moved
        by exactly one on every lap but the pit lap, where it moved by two.

        **Three guards, all of which fail toward over-fuelling.** A false
        positive takes fuel off the call, and a driver who runs dry has lost
        the race where one lap too many costs him three seconds in the box:

        1. The offset is learned at a *crossing*, where the relationship
           between the two counters is exact, and never mid-lap.
        2. A discrepancy must persist `LAP_COUNTER_HOLD_FRAMES` before it is
           believed. GT7's counter moves a few frames before the app's own
           LAP_COMPLETED lands, so every ordinary crossing shows this
           discrepancy briefly; a real missed crossing shows it for the rest
           of the lap.
        3. More than `MAX_LIVE_MISSED_LAPS` is not a pit stop - it is a
           restart or a bad read - and is ignored rather than acted on.
        """
        if self.phase is not RacePhase.RUNNING or packet is None:
            return
        if getattr(packet, "paused", False) or getattr(packet, "loading",
                                                       False):
            # **A paused or loading frame is not evidence.** `SessionState`
            # returns early on both and emits no events, so the app lap count
            # is frozen by construction while GT7 counter is whatever it was -
            # and on a load frame the fields are stale from another context
            # entirely. Two seconds of them would manufacture a crossing that
            # never happened.
            self._gt7_pending = 0
            self._gt7_pending_value = 0
            return
        counted = getattr(packet, "laps_completed", None)
        if counted is None or counted < 0 or self._gt7_offset is None:
            # A sentinel or a missing field is a gap in the evidence, not
            # agreement, so the pending count starts again rather than
            # carrying across it.
            self._gt7_pending = 0
            self._gt7_pending_value = 0
            return
        if self.state.lap < 1:
            # Before the first crossing there is nothing to be out of step
            # with. The offset is learned at that crossing, so in a real race
            # this is already unreachable - it is here because a detector that
            # can fire on lap zero can fire during the formation lap.
            return
        missed = counted - self._gt7_offset - self.state.lap
        if not 0 < missed <= MAX_LIVE_MISSED_LAPS:
            # Back in agreement, or so far out it is not this race.
            self._gt7_pending = 0
            self._gt7_pending_value = 0
            self.state.laps_dropped_seen = 0
            return
        # **The hold has to re-arm on the VALUE, not just on disagreement.**
        # `_gt7_pending` counted frames where the two counters differed at all,
        # so once a real dropped lap had parked `missed` at 1 the counter sat
        # saturated for the rest of the race - and the moment an ordinary
        # crossing pushed it briefly to 2, that 2 was believed on the very next
        # frame. The hold existed precisely to swallow that transient and could
        # never fire again after the first genuine correction.
        #
        # Fuji is the whole shape of it. 31 warnings between the stop and the
        # flag, alternating "2 crossings ... app still on lap N" at the
        # crossing instant and "1 crossing ... app still on lap N+1" about two
        # seconds later, never converging. The permanent +1 was right; the +2
        # was the Qt thread not having reached LAP_COMPLETED yet. **The calls
        # are composed during exactly that window**, so the run-in went out a
        # lap early all the way to the flag: "Two to go" with three to go,
        # "Last lap" with two, and nothing at all on the actual last lap.
        #
        # Each distinct value now serves its own hold before it is believed.
        if missed != self._gt7_pending_value:
            self._gt7_pending_value = missed
            self._gt7_pending = 1
            return
        self._gt7_pending += 1
        if self._gt7_pending < LAP_COUNTER_HOLD_FRAMES:
            return
        # **Assigned, not ratcheted, so the claim can be WITHDRAWN.**
        # `note_packet` runs on the telemetry thread and `_on_lap` on the Qt
        # thread behind a queued signal, so at every ordinary crossing the two
        # counters are briefly out of step - for as long as the Qt thread takes
        # to reach the event, which on a crossing also encodes a lap of frames
        # and writes them. A hold that a slow crossing outlasts would otherwise
        # latch a lap of fuel out of every remaining fill, permanently, because
        # nothing ever lowered it again. Now the next agreeing frame clears it.
        if missed != self.state.laps_dropped_seen:
            log("race").warning(
                "GT7 has counted %s crossing(s) the app did not, while the "
                "app is still on lap %s - most likely in the box. Correcting "
                "the lap count now rather than at the next crossing, because "
                "the fuel call is made in between.", missed, self.state.lap)
        self.state.laps_dropped_seen = missed

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

    def _pending_stops(self) -> int:
        """Stops still ahead of the stint being run, that will actually happen.

        During the stop itself `stint_index` has not advanced - `_apply_stint`
        moves it on PIT_EXIT - so the stop in progress still counts.

        **A stop that has been declared off does not count.** `_stops_off`
        says "no more stops on fuel" and `stop_still_needed` is what decided
        it, but neither touches `_stints` - so the discount went on
        subtracting a stop the engineer had just cancelled, for the rest of
        the race. Worse in the stay-out: `stay_out_call` returns None exactly
        when the fuel cannot reach, so in the case where the stop is real the
        cancellation never happens and in the case where it is not the
        discount is permanent.
        """
        pending = max(0, len(self._stints) - 1 - self.state.stint_index)
        if pending and not stop_still_needed(self.state):
            return 0
        return pending

    def _laps_to_flag(self, lap_ms: int | None,
                      left: int | None) -> int | None:
        """How many crossings there will actually be, stops taken out.

        The same arithmetic as `_laps_after_stops` and a different question,
        which is why it is a second method rather than a shared one. That one
        sizes a FILL and deliberately under-discounts so an overstated
        discount cannot run him dry; this one is the distance the driver is
        told, where under and over are both simply wrong.
        """
        pending = self._pending_stops()
        if not pending or not self.pit_loss_s:
            return left
        return self.clock.laps_left(lap_ms, less_s=pending * self.pit_loss_s)

    def _stop_discount_is_short(self) -> bool:
        """Whether the laps-to-flag discount is known to be incomplete.

        `pit_loss_s` is the track constant and is measured ex-fuel - CLAUDE.md
        §5.4 puts the fuel-dependent part at 0.5-1.0 s per 10% of tank on top.
        So with a stop still to come the discount is short by the fill, by an
        amount nobody here has measured, and the count can be a lap long
        because of it. That is a reason to offer two numbers, not to guess a
        third.
        """
        return self._pending_stops() > 0

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

    def stamp_clock(self, lap) -> None:
        """Write the race clock onto the lap, on the way past.

        **So that next time the answer can be checked.** A timed race's
        distance is `ceil(time left / lap)`, and whether that has ever been
        right is unanswerable from what is on disk: nothing recorded the clock
        per lap, so an audit can only re-derive elapsed time by summing lap
        times - which omits everything before lap 1. At Monza that omission is
        67.9 s, over half a lap, and it is exactly the size of the error being
        investigated. Three timed races on file and in none of them can "the
        estimate was wrong" be told from "the reconstruction was wrong".

        Stored beside `laps_completed`, GT7's own answer to the neighbouring
        question, so one query settles both.

        **Called from the controller's lap-completed slot, not from `_on_lap`
        here.** Those are two queued slots on the same thread and Qt runs them
        in order: the INSERT went first, so a stamp written here landed after
        the row and never reached the database at all.
        """
        if self.clock is None or not self.clock.running:
            return
        try:
            lap.race_elapsed_s = round(self.clock.elapsed_s, 2)
            remaining = self.clock.remaining_s
            lap.race_remaining_s = (round(remaining, 2)
                                    if remaining is not None else None)
            # **Both detectors, not just the clock's.** `laps_dropped_seen`
            # is GT7's own counter disagreeing, and that is the one that
            # caught Road Atlanta - recording only the clock's would omit the
            # evidence the column exists to hold.
            lap.laps_dropped = self.state.laps_missed()
        except Exception:                                    # noqa: BLE001
            # A lap that will not take the stamp is still a lap. The audit is
            # worth having and is worth nothing at the cost of the race.
            log("race").warning("could not stamp the clock onto lap %s",
                                getattr(lap, "lap_num", "?"), exc_info=True)

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
        # **The clock onto the state, so the engineer can say it.** With
        # GT7's race HUD off this is the driver's only source for how much
        # race is left, and minutes are a measurement where the lap count is
        # an inference over a median.
        self.state.race_remaining_s = self.clock.remaining_s
        lap_ms = self.expect.achieved_lap_time_ms() or self.planned_lap_time_ms
        # **Two counts, and they are different questions.**
        #
        # `left` is the raw clock: how many laps fit if every one of them is a
        # green lap. It is what decides the FLAG, because it is recomputed at
        # every crossing off the time actually remaining and therefore
        # self-corrects as the stop is taken.
        #
        # `to_flag` is how many crossings there will actually BE, which is
        # fewer when a stop is still to come: the stop spends clock and covers
        # no ground. `laps_left`'s own docstring argued the other way - "a
        # crossing still happens on the lap the stop is taken" - and that is
        # true and is not the point. Simulated against ground truth at
        # remaining 600/610/650/700/720 s on a 100 s lap with a 30 s stop, the
        # undiscounted count is wrong at 610 and 720 and the discounted one is
        # right at all five. This is the figure the driver is told, and he
        # asked for it to be right.
        left = self.clock.laps_left(lap_ms)
        to_flag = self._laps_to_flag(lap_ms, left)
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
        # **"Firm" has to mean firm against everything that can move it, not
        # just against lap-to-lap noise.** It compared the margin to sigma
        # alone, which is silent on the two systematic offsets that can each
        # shift the answer by a whole lap - so it could read True while the
        # count was one out for a reason it had never looked at.
        #
        # The pending stop is now IN the estimate rather than being an error
        # in it, but only to the extent of `pit_loss_s`, which is the track
        # constant and excludes the fill. With a stop still to come and no
        # measured fill time, the discount is known to be short by an
        # unquantified amount - so the count is offered as one of two rather
        # than flat. Inventing a coefficient for the fill would be the thing
        # this project refuses everywhere else.
        self.state.laps_estimate_firm = bool(
            margin is not None and sigma is not None
            and margin >= sigma / 1000.0
            and not self._stop_discount_is_short())
        if left is None:
            # No lap time to divide by. The plan's frozen distance is all
            # there is, and it stands rather than being replaced by a guess.
            return None
        # **`laps_missed()` is in the completed count here too.** A timed
        # race distance is recomputed from the clock at every crossing, and
        # `left` is time-based and therefore already right whatever the lap
        # count has done. Adding only `lap` would leave `laps_remaining()`
        # subtracting the correction a second time - `left - missed` - taking
        # a lap of fuel out of the fill. That is the under-fuelling direction,
        # and running dry loses the race where a lap too many costs three
        # seconds in the box.
        # **`left`, not `to_flag`.** Putting the discounted count here moved
        # the race distance under NINE readers, four of which decide fuel:
        # `fuel_frame`, `fuel_reaches_flag`, `fuel_target_l` and
        # `stay_out_call` all measure against `laps_remaining()`. Measured on
        # the real coordinator at lap 12 with 19.0 L aboard and four crossings
        # left, the discounted distance turned a correct "box, you cannot make
        # it" into **"Staying out? You can make it."** at 0.83 laps short -
        # about five litres - by subtracting a stop he was in the act of
        # refusing. The comment three lines above says exactly why: that is
        # the under-fuelling direction, and running dry loses the race where a
        # lap too many costs three seconds in the box.
        #
        # The spoken count reads `laps_to_flag` instead, which is kept apart
        # for the same reason `laps_after_stops` is kept apart for the fill.
        self.state.laps_total = (self.state.lap + self.state.laps_missed()
                                 + left)
        self.state.laps_to_flag = to_flag
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
        """The one thing said this lap, or nothing.

        **The heartbeat reports; it never occupies the lap.** At the driver's
        every-lap setting it wins almost every crossing, and three things in
        this app key off "nothing was said" - the saving answer below, the
        colour calls in the controller, and the short-shift beep, which is
        cleared by any call that does not ask for one. Left ranked purely by
        urgency, a heartbeat would have closed the saving loop forever and
        withdrawn a short-shift instruction the lap after it was given, both
        without a word. So it is taken out of the running here and put back
        only once the things that key off silence have had the lap.
        """
        call = next_call(self.state)
        heartbeat = call if call is not None and call.kind == STATUS else None
        if call is not None and heartbeat is None:
            self.state.record(call)
            if call.short_shift_drop_rpm:
                # The loop opens here. It has never closed.
                self._saving_asked_lap = self.state.lap
                self._saving_answered = False
            return call

        # **Nothing else won the lap, so close the loop if one is open.**
        # Ranked below every real call and above the heartbeat: it is not an
        # instruction, but it is the answer to one the engineer gave, and an
        # unclosed loop leaves the driver believing a shortfall was covered
        # when it was not.
        answer = self._saving_response()
        if answer is not None:
            self.state.record(answer)
            return answer
        if heartbeat is not None:
            self.state.record(heartbeat)
        return heartbeat

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

    def adopt(self, stint_laps, *, compounds=None, fuel_l=None) -> None:
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
        planned = list(self._stints[self.state.stint_index:])
        for offset, laps in enumerate(stint_laps):
            # **What the re-planner did not decide is carried, not nulled.**
            # A re-plan changes the SHAPE of the race - how many laps each
            # stint runs - and it says nothing about what rubber goes on or
            # how much fuel goes in. Writing `None` over the plan's answers
            # threw both away on the first adaptation: "Box this lap" lost the
            # compound it was going to name, and "how much fuel do I take"
            # lost its answer, on a plan that had said RM and 48 litres.
            #
            # Carried positionally off the plan of record, and only where the
            # re-planner supplied nothing of its own. Where the shapes no
            # longer line up there is no answer to carry, and `None` there is
            # the truth rather than a discard.
            was = planned[offset] if offset < len(planned) else {}
            compound = (compounds[offset]
                        if compounds is not None and offset < len(compounds)
                        else was.get("compound"))
            litres = (fuel_l[offset]
                      if fuel_l is not None and offset < len(fuel_l)
                      else None)
            fresh.append({"laps": laps, "compound": compound,
                          "fuel_l": litres, "start_lap": start})
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

    **Read key by key, never splatted.** `PlanContext(**stored)` raises
    `TypeError` on any key the dataclass does not declare, and the caller is
    `start_race`, on the grid, with no guard around it - so one extra field in
    a plan written outside the app would take the race down at the moment a
    refusal cannot be worked around. A context is data from a file now, not
    only something this app wrote.
    """
    if "race_minutes" in stored:
        length = PlanContext(car="", track="", layout=None,
                             race_laps=int(stored.get("race_laps") or 0),
                             race_minutes=stored.get("race_minutes"))
    else:
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
