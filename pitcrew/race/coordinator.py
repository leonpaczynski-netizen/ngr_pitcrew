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
from dataclasses import dataclass, replace

from pitcrew.diagnostics import log
from pitcrew.race.rivals import Stop
from pitcrew.race.calls import (
    STATUS,
    stop_still_needed,
    BOX_IGNORED_LAPS,
    BOX_NOW,
    FUEL_REACHES,
    FUEL_SAVE,
    FUEL_SHORT,
    HIGH,
    LOW,
    SAVING_RESPONSE,
    STAY_OUT,
    STOP_BACK,
    STOPS_OFF,
    Call,
    RaceState,
    fuel_in_hand,
    _crossing_the_line,
    clear_stint,
    next_call,
    stay_out_call,
)
from pitcrew.race.clock import RaceClock
from pitcrew.race.composure import Composure
from pitcrew.race.expectations import ExpectationTracker
from pitcrew.race.news import RaceNews
from pitcrew.store.tyres import gap_association_for
from pitcrew.strategy.model import PIT_LOSS_MEASURED_EX_FUEL
from pitcrew.telemetry.recorder import SAMPLE_HZ
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
    # The tyre-wear multiplier the race runs at, as the event declares it
    # ("2x"). Not part of `matches`: a plan is not refused over it, but a
    # briefed wear rate measured at another multiplier is.
    tyre_wear_mult: str | None = None
    # How the race starts, as the event declares it ("Rolling", "Standing",
    # "Grid - no track limit"). Not part of `matches`: it decides whether lap
    # one is evidence, not whether the plan fits.
    start_type: str | None = None

    @property
    def is_timed(self) -> bool:
        return bool(self.race_minutes)

    def matches(self, other: "PlanContext") -> tuple[bool, str]:
        if self.car != other.car:
            return False, f"plan was built for {self.car}, car is {other.car}"
        if self.track != other.track:
            return False, f"plan was built for {self.track}, track is {other.track}"
        if self.layout != other.layout:
            # **An unrecorded layout is not a different one** (rule 3, critic
            # 2 on the storage row): "built for the None layout" was on the
            # Strategy page for two old Monza plans written before the layout
            # was stored. Still refused - nothing says it is this layout -
            # but it says which side does not know.
            if self.layout is None:
                return False, ("plan does not record which layout it was "
                               f"built for; this is {other.layout}")
            if other.layout is None:
                return False, (f"plan was built for the {self.layout} layout "
                               f"and this event does not record one")
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


def _tri(value) -> bool | None:
    """A plan field to a tri-state: absent or null stays None.

    **A bool, 0 or 1, or nothing.** `bool("false")` is True, so a plan written
    with the word in quotes would have said "RS on" for a stop meant to be
    fuel only - the opposite instruction. Anything else is None here (the
    plan did not say) and is refused by `Handover.validate` at the door.
    """
    from pitcrew.strategy.handover import tyres_decision

    decided = tyres_decision(value)
    if decided is not None or value is None:
        return decided
    log("race").warning("a stint's tyres field reads %r - not a bool, so it "
                        "is treated as unsaid", value)
    return None


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
                 # Litres a second at the pump, off `events.refuel_rate_lps`.
                 refuel_rate_lps: float | None = None,
                 mandatory_stops: int = 0,
                 pit_loss_measured: bool = False,
                 # **Ludo's briefing for this circuit**, or None where nobody
                 # wrote one. It is the only route by which anything George
                 # cannot derive gets into a race: no model runs in the live
                 # loop, so everything clever is precomputed. See
                 # `race/knowledge.py`. Absent is announced at the green, not
                 # papered over.
                 knowledge=None,
                 now=None) -> None:
        self.phase = RacePhase.IDLE
        self.plan = plan or {}
        self.knowledge = knowledge
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
        # **The briefing's measured stop beats the event's declared one.**
        # Watkins: 15.7 s measured against 20 s declared, and nothing carried
        # the measurement into the next race. Only where the briefing actually
        # names one - `None` there leaves every figure exactly as it was - and
        # it is not marked `pit_loss_measured`, because a figure typed at the
        # desk is declared however carefully it was arrived at.
        if knowledge is not None and knowledge.pit_loss_s:
            pit_loss_s = knowledge.pit_loss_s
        # **And the rate, for the same reason and with the same caveat.** The
        # briefing beat the event page on the pit loss and not on the pump,
        # so the driver board (which reads the briefing) and `rejoin_call`
        # (which reads the state) priced the same stop from different numbers
        # with neither saying which - rule 12. One figure now, merged here
        # where the pit loss is already merged, so every consumer downstream
        # sees the same one. Still declared, however carefully arrived at.
        if knowledge is not None and knowledge.refuel_l_per_s:
            refuel_rate_lps = knowledge.refuel_l_per_s
        self.pit_loss_s = pit_loss_s
        self._burns: list[float] = []
        # **The wall's `lap_now()` key -> the lap it was actually driving.**
        # Filled at each crossing by `_on_lap`, read by `_weigh_the_tow`, and
        # by nothing else. See the note there: the offset is not a constant,
        # so it is recorded rather than assumed. The coordinator is built once
        # per race (`controller._start_race`) and emptied again on every
        # `arm`, which is CLAUDE.md rule 11 for it: a key left from a previous
        # attempt would pair this race's gap with a lap that is not in it.
        self._lap_of_read_key: dict[int, int] = {}
        # **Laps completed after arming but before the green was detected.**
        # `session_state` emits LAP_COMPLETED from `ON_TRACK` onward, so these
        # arrive here and used to be dropped on the floor by the RUNNING gate.
        # They are the racing the clock would otherwise never learn about -
        # see `_on_green` and `race/clock.start`.
        self._pre_green_laps: list = []
        # Lap times fit to judge pace against the plan - see
        # `representative_pace_ms` for what is kept out and why.
        self._pace_ms: list[int] = []
        # (lap, ms) of every lap that was driving, and the crossing a fuel
        # save was first asked for on - see `projected_lap_ms`.
        self._racing_laps: list[tuple[int, int]] = []
        self._save_asked_lap: int | None = None
        # An incident seen during the lap in progress: None for no,
        # False for detected, True for driver-reported. Consumed at
        # the crossing - see `note_incident`.
        self._incident_pending: bool | None = None
        # The clock's dropped-lap count as it stood before the lap
        # being handled. See `_corroborate_pit_lap`.
        self._dropped_before_lap = 0
        self._stints = list(self.plan.get("stints") or ())
        # **The bounds the engineer at the desk set on the engineer in the
        # car.** Empty for a plan the app wrote itself, and empty is not the
        # same as absent: see `_may`.
        from pitcrew.strategy.handover import playbook_of

        self._playbook = {entry.trigger: entry
                          for entry in playbook_of(self.plan)}
        # Whether a fuel-long may drop a stop - `_may` reads the playbook,
        # and with none it refuses, which is the one place absence is no.
        self.state.drop_stop_granted = self._may("fuel_long", "drop_stop")
        # **Why the plan's stops exist**, in the plan's own word for it. Only
        # a fuel-bound stop can be cancelled by a tankful, and a plan that
        # does not say keeps every stop it named - see `calls.stop_still_needed`
        # for the Fuji race this is on file from.
        self.state.plan_binding_constraint = self.plan.get("binding_constraint")
        self.pit_loss_measured = bool(pit_loss_measured)
        # **The two figures the pit-lane calls price a stop with**, put on the
        # state because that is what `calls.next_call` reads. `pit_loss_s` is a
        # TRACK constant (CLAUDE.md 5.4); the refuel rate comes off the event
        # and is `None` until somebody measures it, which is not a rate.
        self.state.pit_loss_s = pit_loss_s
        # **The vocabulary `stop_costs_s` actually compares against.** This
        # wrote the bare string "measured" while `strategy.model` - the module
        # that defines the term, and the one `gaps.stop_costs_s` and
        # `StrategyInputs.stop_overhead_s` both import it from - spells it
        # `measured-this-track`. The comparison therefore never matched, so
        # `PIT_DEAD_TIME_S` was never added to a measured pit loss by ANY
        # pit-lane call: 7.5 s missing from every rejoin verdict against a
        # `REJOIN_MARGIN_S` of 3 s. Two words for one concept is rule 13 with
        # the sign hidden - the mismatch fails silently, and in the direction
        # that makes a stop look cheap.
        #
        # The events column keeps its own storage vocabulary ("declared" /
        # "measured"); it is translated here, once, at the boundary.
        #
        # **And translated to what the measurement IS** (14 Sep 2026). The
        # only writer of "measured" is `race/pit_loss.py` via
        # `Store.record_measured_pit_loss`, and its figure is the whole stop
        # less the refuelling - dead time included. Translated to the
        # lane-only `PIT_LOSS_MEASURED`, `stop_costs_s` added the 7.5 s dead
        # time a second time: Bathurst's 23.13 s was priced as 30.6 s.
        self.state.pit_loss_source = (PIT_LOSS_MEASURED_EX_FUEL
                                      if pit_loss_measured else None)
        self.state.refuel_rate_lps = refuel_rate_lps
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
        # **Built here and reset with the race, not at app start.** State that
        # outlives a session is read as belonging to it (CLAUDE.md rule 11) -
        # and a coordinator carrying a stale recovery would open a race with
        # the engineer already holding its tongue.
        self.composure = Composure()
        self.composure.reset()
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
        # **The race around him, volunteered** - gaps, the stop cycle, the
        # championship and pace (D7, 14 Sep 2026). See `race/news.py`.
        self.news = RaceNews()
        self._reset_mid_lap()

    # ------------------------------------------------------------------ arming

    def arm(self, planned: PlanContext | None,
            actual: PlanContext | None) -> bool:
        """Ready the race. Returns False, with a reason, if the plan does not fit."""
        self.refusal = None
        # A re-arm starts the count again: laps from a previous attempt are
        # not this race's - and neither are the keys the wall filed its gaps
        # under while they were being driven.
        self._pre_green_laps = []
        self._lap_of_read_key = {}
        self._racing_laps = []
        self._save_asked_lap = None
        # **And the rival stops, and the mid-lap slot's clock** (rule 11): a
        # stop seen before a re-arm is not this race's news.
        self.state.lane.new_session()
        self.news.new_session()
        self._reset_mid_lap()
        if planned is not None and actual is not None:
            ok, why = planned.matches(actual)
            if not ok:
                self.refusal = why
                return False
        if actual is not None:
            self.state.race_minutes = actual.race_minutes
            self.state.tyre_wear_mult = getattr(actual, "tyre_wear_mult", None)
            # Lap one is evidence after a rolling start and not after a
            # standing one - see `ExpectationTracker.rolling_start`.
            self.expect.rolling_start = (
                (getattr(actual, "start_type", None) or "") == "Rolling")
            # The first stint was briefed at construction, before the race's
            # multiplier was known; brief it again now that it is.
            self._brief_the_wear_rate()
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
        # **The latch belongs to the stop it retired.** This is where
        # `stint_ends_on_lap` is recomputed - across a stop taken, at a
        # re-plan adopted, at construction - and a retirement of the old stop
        # says nothing about the next one (CLAUDE.md rule 11's shape: state
        # that outlives its subject is read as though it were about this one).
        # **All of it, and logged** (critic 4, MAJOR): batch 4 cleared the
        # latch and left `stops_off_said`, so after a re-plan or a stop the
        # new stop's countdown flickered and nothing about it could be said.
        had = self.state.stop_needed_held
        self.state.stop_needed_held = None
        self.state.stop_flip_laps = 0
        self.state.stop_back_due = False
        self.state.stops_off_said = False
        self.state.forget_said(STOPS_OFF)
        self.state.forget_said(STOP_BACK)
        if had is not None:
            log("race").info("stint %d: the held stop answer (%s) is cleared "
                             "for the stop this stint ends on", index,
                             "needed" if had else "not needed")
        # **What the NEXT stint starts on** - not the fill. The litres through
        # the hose are this minus whatever is aboard when we arrive, and
        # `_fill_at_the_stop` does that subtraction. `None` on the last stint:
        # there is no next stop, and a rejoin call about one would be about a
        # stop that is not happening.
        following = index + 1
        self.state.next_stint_load_l = (
            self._stints[following].get("fuel_l")
            if following < len(self._stints) else None)
        if index >= len(self._stints):
            self.state.stint_ends_on_lap = None
            self.state.next_compound = None
            self.state.next_tyres = None
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
        self._brief_the_wear_rate()
        start = stint.get("start_lap") or 1
        # **The IN-LAP**: the last lap of the stint, whose end is the pit
        # lane - the plan's `pit_laps` entry. "Box this lap." is said on the
        # crossing that STARTS it, `laps_to_stop() == 1` (14 Sep 2026).
        self.state.stint_ends_on_lap = start + stint.get("laps", 0) - 1
        following = self._stints[index + 1] if index + 1 < len(self._stints) else None
        self.state.next_compound = following.get("compound") if following else None
        # **The plan's tyre decision for the coming stop, tri-state.** A
        # stint written before the field existed has no `tyres` key and reads
        # None - "the plan did not say" - never False, because False is the
        # positive claim "fuel only" and the box call acts on it.
        self.state.next_tyres = (_tri(following.get("tyres"))
                                 if following else None)
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

    def note_tyres_word(self, changed: bool) -> None:
        """The driver said "new tyres" or "no tyres" on the radio.

        **Held while he is still in the lane.** PIT_EXIT needs 120 km/h, and
        a word said leaving the box would otherwise find the stop not yet
        marked and be applied to the previous one, or dropped.
        """
        if self.state.in_pit:
            self._pending_tyres_word = changed
            return
        self.state.note_tyres_word(changed, lap=self.state.lap)

    def note_penalty(self, lap_num: int, lost_s: float | None, *,
                     speak: bool = True) -> None:
        """A track-limit penalty served on this lap, from the controller.

        The lap leaves the pace and burn populations, and the crossing says
        so with the derived cost. Guarded like its siblings.

        **`speak=False` strikes the lap and says nothing** (critic pass 7).
        `analysis/penalties.py` can tell that a brake is not evidence of pace
        - which is true whatever caused it - without being able to say it was
        a penalty, and at a place the driver brakes at most laps that is
        exactly where it stands. Also the shape of a partial withdrawal: the
        cost of the readings that still stand is corrected here, and a call
        already made about that lap is tagged and will not be remade.
        """
        if not self.running:
            return
        self.expect.note_penalty(lap_num)
        if speak:
            self.state.penalty_note = (int(lap_num), lost_s)
        elif (self.state.penalty_note is not None
                and self.state.penalty_note[0] == int(lap_num)):
            # An unspoken note about this lap is corrected rather than left
            # carrying a cost that has since been withdrawn.
            self.state.penalty_note = (int(lap_num), lost_s)

    def forget_penalty(self, lap_num: int) -> None:
        """Withdraw a penalty read: the place turned out to be the road.

        The controller calls this when a place has been braked on nearly
        every lap of the session, which a corner missing from the model is
        and a served penalty is not - see `analysis/penalties.py`. **Only
        where NOTHING is left standing on the lap:** a lap can carry a
        penalty at one place and a missing corner at another, and a lap that
        still carries one is still out of the pace.

        The lap goes back into the pace and burn populations and an unspoken
        note about it is dropped. A call already made cannot be unmade, which
        is why it went out at LOW with "Unconfirmed." on the end.
        """
        if not self.running:
            return
        self.expect.forget_penalty(lap_num)
        note = self.state.penalty_note
        if note is not None and note[0] == int(lap_num):
            self.state.penalty_note = None

    def note_driving(self, lap_num: int, read) -> None:
        """One lap's driving read off its frames, from the controller.

        Kept per stint - a stop resets it, because the saving that stopped
        at the stop is the stop's own news and the next stint starts clean.
        The step is looked for here, the sentence is composed here, and
        `_saving_change` says it at the next crossing.
        """
        from pitcrew.analysis.driving import saving_change

        history = getattr(self, "_driving", None)
        if history is None:
            history = self._driving = []
        history.append((int(lap_num), read))
        change = saving_change(history)
        if change is None or change.lap == getattr(self, "_saving_change_lap", None):
            return
        self._saving_change_lap = change.lap
        burn = self.state.fuel_per_lap_l
        tail = (f" Burn is {burn:.1f} litres a lap now." if burn else "")
        if change.what == "lift-and-coast":
            note = (f"You've stopped lift-and-coasting since lap {change.lap} - "
                    f"{change.before:.0f} percent of the lap off the pedals "
                    f"before, {change.after:.0f} now.{tail}")
        else:
            note = (f"You've stopped short-shifting since lap {change.lap} - "
                    f"upshifts at {change.before:.0f} before, "
                    f"{change.after:.0f} now.{tail}")
        self.state.saving_change_note = note
        self.state.saving_change_lap = change.lap

    def _brief_the_wear_rate(self) -> None:
        """The measured rate for the compound now on the car, or nothing.

        **Re-read at every stint**, because the rate belongs to a compound and
        the compound changes at a stop. A briefed rate that survived a change
        from RS to RH would be the app's own standing rule 11 all over again:
        state that outlives the thing it describes gets read as if it belongs
        to what came after.

        **Cleared where the compound is unknown**, which is what a stop with
        no compound in the plan leaves behind. A rate attributed to the wrong
        tyre is not a gap in the model, it is a corruption of it.
        """
        self.state.briefed_wear_per_lap = None
        self.state.briefed_wear_samples = 0
        if self.knowledge is None or not self.state.tyre_compound:
            return
        rate, samples = self.knowledge.wear_per_lap(
            self.state.tyre_compound, multiplier=self.state.tyre_wear_mult)
        if rate:
            self.state.briefed_wear_per_lap = rate
            self.state.briefed_wear_samples = samples

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
            if self.state.in_pit:
                # The line is inside the lane here (Daytona, Spa): the lap
                # counter has moved before the fill, so the lap in progress
                # is the out-lap and the fill covers it whole.
                self.state.crossed_in_box = True
            return self._on_lap(event, packet)
        if event.kind is EventKind.PIT_ENTRY:
            self.state.in_pit = True
            self.state.crossed_in_box = False
            # **What we arrived with, so a rival's fill has ours to beat.**
            # `rival_boxed` says "he stands N seconds longer than you did", and
            # without our own stop it can only say his standing time in
            # isolation - which is the number the driver cannot act on, since
            # what matters is the swing.
            self._our_entry_fuel_l = self.state.fuel_l
            return None
        if event.kind is EventKind.PIT_EXIT:
            self.state.in_pit = False
            self.state.crossed_in_box = False
            # A new stint: the driving history and any pending note restart.
            self._driving = []
            # A save asked for on the old tank is not asked for on this one.
            self._save_asked_lap = None
            self.state.saving_change_note = None
            self.state.saving_change_lap = None
            entry = getattr(self, "_our_entry_fuel_l", None)
            if entry is not None and self.state.fuel_l is not None:
                self.state.our_stop = Stop(
                    lap=self.state.lap, fuel_in_l=entry,
                    fuel_out_l=self.state.fuel_l,
                    tyres_changed=event.data.get("tyres_changed"))
            self._our_entry_fuel_l = None
            # The stop carries whether the tyres came off. Discarding it made
            # every fuel-only stop a fresh set and silenced the end-of-window
            # call for the stint after it.
            clear_stint(self.state,
                        tyres_changed=event.data.get("tyres_changed"))
            pending = getattr(self, "_pending_tyres_word", None)
            if pending is not None:
                self._pending_tyres_word = None
                self.state.note_tyres_word(pending, lap=self.state.lap)
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
        # **Which lap the wall's gap readings belong to, settled here and
        # nowhere else** (critic pass 6). The pit wall files every gap under
        # `lap_now()` - laps COMPLETED - so a gap read while lap N was being
        # driven carries the key N-1, while `laps_by_number()` keys lap N's
        # own time and burn under N. Paired naively the tow trade compared
        # this lap's gap with the PREVIOUS lap's laptime and litres, which is
        # the one pairing the whole calculation is about.
        #
        # A constant offset of one would be wrong too: `lap_now()` carries
        # `laps_missed()`, so a crossing lost in the pit lane shifts the keys
        # for the rest of the race and a fixed shift drifts from there on.
        # Read here, before `state.lap` moves, it is not an offset at all -
        # it is the counter's actual value while the lap was being driven.
        #
        # **Key 0 covers everything before the first crossing**, formation lap
        # included, because `_on_lap` does not run before the green and
        # `state.lap` stays 0 through it. `GapTrend.note` keeps only the last
        # reading per key, so the figure filed under 0 is the newest one -
        # which after a rolling start is a lap-one read and not a formation
        # gap, unless the board went unreadable for the whole of lap one.
        read_key = int(self.state.lap_now())
        self._lap_of_read_key[read_key] = int(lap.lap_num)
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
        # **The same field, now also spoken.** GT7 increments at the crossing,
        # so at this instant `counted` IS the lap he is about to drive and the
        # number his HUD has just changed to. `state.lap` remains the count
        # behind him and remains what every piece of arithmetic here uses;
        # `screen_lap` is the one that may be said as "Lap N". They were one
        # apart on all 20 rows of session 127 and the engineer said the wrong
        # one every lap of it - see `RaceState.lap_on_screen`.
        #
        # Set every crossing rather than derived once from `_gt7_offset`,
        # because the offset is not constant: a crossing GT7 counts and the
        # app misses widens it mid-race, and a cached offset would then speak
        # a lap number that drifts further from the screen with every drop.
        if counted is not None and counted > 0:
            self.state.screen_lap = counted
        elif self.state.screen_lap is not None:
            # GT7 stopped answering. Keep counting rather than freezing on the
            # last number it gave - a stale lap number is worse than an
            # arithmetic one, because it does not move at all.
            self.state.screen_lap = None
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
        if (lap.lap_time_ms > 0 and not lap.is_pit_lap
                and not lap.is_out_lap):
            # Driving, not the box: what `projected_lap_ms` may average.
            self._racing_laps.append((int(lap.lap_num), int(lap.lap_time_ms)))
        self._corroborate_pit_lap(lap)
        self._weigh_the_tow()
        self._note_crossing_for_mid_lap()

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
        # **This stint's burn once it has three clean laps, the race's until
        # then.** The whole-race median said "6% under plan" with the hose
        # in at Deep Forest, from a first stint driven lift-and-coasting,
        # while the stint about to be run burned 8% more. The fill and every
        # "vs plan" sentence size the laps AHEAD, and those are this stint's.
        green, burn_laps, basis = self.expect.current_fuel_basis()
        if green is not None and self.expect.green_laps() >= self.BURN_LAPS_NEEDED:
            if (green != self.state.fuel_per_lap_l
                    or basis != self.state.fuel_burn_basis):
                # **Logged on accept** (rule 10): the burn every fuel call
                # rests on, how many laps stand behind it, and whose laps.
                log("race").info("burn installed on lap %s: %.3f L/lap over "
                                 "%d laps of %s", lap.lap_num, green,
                                 burn_laps, basis)
            self.state.fuel_per_lap_l = green
            # How many laps the band in `calls.fuel_verdict` is a projection
            # off, and whether they are this stint's yet.
            self.state.fuel_burn_laps = burn_laps
            self.state.fuel_burn_basis = basis
            # **And the load it was measured at, or the burn is unanchored.**
            # A median taken over the heavy first half of a stint over-states
            # what the light second half will use; without this the fill at the
            # stop is sized on laps the car is no longer running. Installed on
            # the same terms as the rate - this race's own laps, or nothing.
            self.state.fuel_reference_load_l = (
                self.expect.current_fuel_reference_load_l())
        # **And the scatter beside it, because the scatter sizes the fill.**
        # Installed on the same terms as the rate: this race's own laps, or
        # nothing. Where it is None the fill falls back to CLAUDE.md's flat
        # lap, which is the right answer for a burn nobody has measured the
        # spread of - it is only the wrong answer once the spread is known.
        # **The stint's own scatter once it can speak, the race's until
        # then** - the same terms as the rate. A whole-race sd across a stint
        # boundary contains the STEP between stints (7.32 -> 7.8-8.1 at Deep
        # Forest), which this codebase's own rule says is not scatter; a
        # margin sized on it buys fuel against a fault that does not exist.
        # The lap-to-lap spread, for the chase call to state its noise.
        sigma_ms = self.expect.sigma_ms()
        self.state.lap_sigma_s = (sigma_ms / 1000.0) if sigma_ms else None
        measured_sd = (self.expect.stint_fuel_sd_l()
                       if self.expect.stint_fuel_per_lap_l() is not None
                       else self.expect.race_fuel_sd_l())
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
        # **The lap into the pace record of the cars either side**, with the
        # reason where it is not a lap of anybody's pace (rule: exclude the
        # excursions before correlating). Keyed on the wall's own read key.
        dirty = ("our pit lap" if lap.is_pit_lap else
                 "our out lap" if lap.is_out_lap else
                 "our incident lap" if incident is not None else
                 "lap one" if lap.lap_num <= 1 else None)
        try:
            self.news.note_lap(read_key, int(lap.lap_num),
                               (lap.lap_time_ms / 1000.0
                                if lap.lap_time_ms and lap.lap_time_ms > 0
                                else None),
                               dirty, lane=self.state.lane)
        except Exception:
            log("race").exception("news: the lap could not be filed")

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

        # **Once a lap, after this lap's burn is installed**, because
        # `stop_still_needed` reads it: whether a stop he was told was off
        # has been needed long enough to come back. See `note_stop_need`.
        self.state.note_stop_need()
        folded = self._reconsider_ignored_box()
        if folded is not None:
            self.state.record(folded)
            if folded.severity is not None:
                # A fold short of the flag asks him to save.
                self.note_save_asked(self.state.lap)
            return folded
        return self._emit()

    def note_rival_stop(self, seen, burn_per_lap_l=None,
                        burn_stops: int = 0) -> None:
        """File a rival's finished stop so the calls can reason about it.

        **Qt thread only.** The pit wall sees a stop on the sampler's worker
        thread; the controller hands it here through a queued signal, because
        `RaceState` is read on the crossing and a dict written from two threads
        is the same defect the roster had.

        A partial stop is kept: the exit fuel is what every call downstream
        needs, and a stop whose ENTRY figure was never read still carries it.
        """
        # **Every gate says which one it was.** This method had five silent
        # returns and no log line at all - and the history of this feature is a
        # whole race of unexplained silence. CLAUDE.md rule 10: log the
        # accepts, not only the refusals.
        why = None
        if seen is None:
            why = "nothing was sent"
        elif not self.running:
            why = f"the race is {self.phase.name.lower()}, not running"
        elif not getattr(seen, "driver", None):
            why = "the stop carries no driver name"
        elif getattr(seen, "stop", None) is None:
            why = "the stop carries no fuel record"
        if why is not None:
            log("race").info("rival stop not filed: %s", why)
            return
        from pitcrew.race.rival_calls import Rival

        name = seen.driver
        # **He is out of the lane.** From here his stop is news for one more
        # crossing and then history (`race/lane.py`), and a place gained on
        # him while he stood there can come back without being a pass.
        if self.state.lane.left(name, lap=self.state.lap) is not None:
            log("race").info("rival out of the lane: %s, after our lap %s",
                             name, self.state.lap)
        self.state.rivals[name] = Rival(
            name=name, stop=seen.stop, pitted=True,
            burn_per_lap_l=burn_per_lap_l, burn_stops=burn_stops,
            exit_is_a_bound=getattr(seen, "exit_is_a_bound", False),
            position=self.state.rival_positions.get(name))
        log("race").info(
            "rival stop filed: %s out on %s L on lap %s, burn %s L/lap from "
            "%d stop%s%s", name, seen.stop.fuel_out_l, seen.stop.lap,
            f"{burn_per_lap_l:.2f}" if burn_per_lap_l else "ours",
            burn_stops, "" if burn_stops == 1 else "s",
            " (exit figure is a lower bound)"
            if getattr(seen, "exit_is_a_bound", False) else "")

    def note_rival_entered(self, entered) -> None:
        """A car is standing in its box right now.

        **Its own event, because "he has boxed" is news for one lap.** The
        finished stop arrives when he LEAVES, which for a call whose whole
        content is what his fill is about to cost him is a minute too late.
        """
        if not self.running or entered is None:
            return
        if not getattr(entered, "driver", None):
            log("race").info("rival entry not taken: no driver name")
            return
        # **Recorded, not queued.** Two cars can be in the lane in one frame,
        # and a queue drained at every crossing lost every stop a box call
        # outranked - eight of ten at Bathurst. See `race/lane.py`.
        if self.state.lane.enter(entered, lap=self.state.lap) is None:
            log("race").info("rival entry already on file: %s, lap %s",
                             entered.driver, entered.lap)
            return
        log("race").info("rival entered the lane: %s on %s L, lap %s, %s us",
                         entered.driver, entered.fuel_in_l, entered.lap,
                         {True: "was ahead of", False: "was behind",
                          None: "unplaced against"}[
                              getattr(entered, "ahead_at_entry", None)])

    def _weigh_the_tow(self) -> None:
        """Remake the tow trade from this race's laps and the wall's gaps.

        Every crossing, so the verdict the driver hears is the one the laps
        just driven support. None where fewer than three laps were held up,
        or nothing can stand as the clear-air reference.

        **The two sides are keyed differently and are re-keyed here** (critic
        pass 6). The trend holds `lap_now()` - laps COMPLETED at the instant
        the board was read - and `laps_by_number()` holds the lap's own
        number, so a gap read on lap 7 was being compared with lap 6's time
        and litres. `_lap_of_read_key` is written at each crossing from the
        counter's real value, so this is a lookup and not an assumed offset;
        a read whose lap never completed simply has no entry and drops out,
        which is rule 3 rather than a guess.
        """
        from pitcrew.race import tow

        trend = self.state.gap_ahead
        seen = dict(getattr(trend, "seen", None) or {})
        if not seen:
            self.state.tow_trade = None
            return
        by_lap = {}
        for key, gap in seen.items():
            lap = self._lap_of_read_key.get(int(key))
            if lap is not None:
                by_lap[lap] = gap
        if not by_lap:
            self.state.tow_trade = None
            return
        try:
            self.state.tow_trade = tow.trade(
                by_lap, self.expect.laps_by_number(),
                refuel_rate_lps=self.state.refuel_rate_lps,
                planned_fuel_per_lap_l=self.planned_fuel_per_lap_l,
                planned_lap_time_ms=self.planned_lap_time_ms)
        except Exception:
            log("race").exception("the tow trade could not be made")
            self.state.tow_trade = None

    def note_circuit(self, length_m: float | None,
                     sector_cuts_m=None) -> None:
        """The circuit's length and sector lines, for binning the gap.

        Without the length no lap can be judged against the circuit and the
        sector map is never built; without the cuts the map cannot speak in
        the sectors on his rack. Both come from the store, through the
        controller, once per race.
        """
        from pitcrew.race.sectors import SectorMap

        if not length_m:
            return
        self.state.sector_map = SectorMap(circuit_length_m=float(length_m))
        self.state.sector_cuts_m = (tuple(float(c) for c in sector_cuts_m)
                                    if sector_cuts_m else None)

    def note_gaps(self, ahead=None, behind=None,
                  ahead_name=None, behind_name=None,
                  ahead_samples=None) -> None:
        """The two gap trends the board reader keeps, and whose they are.

        Guarded like its two siblings: a gap noted before the green or after
        the flag describes a race that is not being run.

        `ahead_samples` are the lap just driven's `(track_m, gap_s)` readings
        of the car ahead, in order, folded into the sector map - which drops
        a lap whole when its span does not look like the circuit.
        """
        if not self.running:
            return
        self.state.gap_ahead = ahead
        self.state.gap_behind = behind
        self.state.gap_ahead_name = ahead_name
        self.state.gap_behind_name = behind_name
        sector_map = self.state.sector_map
        if sector_map is not None and ahead_samples:
            subject = getattr(ahead, "subject", None)
            try:
                sector_map.note_lap(list(ahead_samples), subject=subject)
            except Exception:
                log("race").exception("the sector map could not take the lap")

    def note_gap_read(self, side: str, gap_s: float | None, subject=None,
                      name: str | None = None) -> None:
        """One interval box, read now, with whose it is. Worker thread.

        **As it is read, not at the crossing.** `note_gaps` hands over the
        wall's trends once a lap, which is right for a closing rate and a lap
        late for "PUNISHED ahead, 2.1" - the gap George volunteers mid-lap
        has to be the gap now (D7, 14 Sep 2026). Stamped with the frame
        count the mid-lap slot keeps time in, and the wall's own read key.
        """
        if not self.running:
            return
        try:
            self.news.note_gap(side, gap_s, subject, name,
                               packet=self._packets,
                               lap_key=int(self.state.lap_now()))
        except Exception:
            log("race").exception("news: a gap reading could not be taken")

    def note_board(self, rows, own_row: int | None) -> None:
        """One frame of the board's rows, `(row, name)`. Worker thread.

        Turned into places against our own place off the packet at this
        moment - see `news.board_places` for the shape it has to fit.
        """
        if not self.running:
            return
        try:
            self.news.note_board(rows, own_row, packet=self._packets,
                                 our_position=self.state.position)
        except Exception:
            log("race").exception("news: a board read could not be taken")

    def note_rival_positions(self, positions: dict) -> None:
        """Where the other cars are, refreshed each lap from the board.

        Kept beside the rivals rather than on them because a stop's position
        is read while the car is STANDING, which is the one moment it does not
        describe where he is racing.
        """
        if not positions:
            return
        self.state.rival_positions.update(positions)
        for name, rival in self.state.rivals.items():
            where = positions.get(name)
            if where is not None and where != rival.position:
                self.state.rivals[name] = replace(rival, position=where)

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

    def note_packet(self, packet) -> "Call | None":
        """Everything that has to be read on a FRAME rather than a crossing.

        Two jobs, and they are independent on purpose - a packet that cannot
        serve one still serves the other:

        * **the lap counter**, in `_note_lap_counter`, which is the only
          detector that can see a missed crossing while the car is still in
          the box;
        * **race position**, which is read here and returned as a call.

        **The position half returns a call and the counter half does not**,
        because they answer to different clocks. A missed crossing changes the
        fuel arithmetic and is acted on silently; a place changed is news and
        has to be said while it is still what just happened.

        The caller speaks whatever comes back. `None` is the ordinary answer.

        **It is also the mid-lap slot for a rival's stop** (14 Sep 2026), and
        whatever it returns has been decided on: see `_mid_lap`.
        """
        call = None
        if packet is not None and self.phase is RacePhase.RUNNING \
                and not getattr(packet, "paused", False) \
                and not getattr(packet, "loading", False):
            self._packets += 1
            self._note_composure(packet)
            self._expire_in_flight()
            call = self._mid_lap(packet)
        self._note_lap_counter(packet)
        return call

    # **Seconds between two volunteered mid-lap calls OF ONE KIND.** Bathurst,
    # 14 Sep 2026: "P9", "P8", "P7" in 41 s. A held place is not lost by the
    # wait - it is re-read when the slot opens, so what is said is where he
    # has SETTLED. Once a kind, not once for everything: the same night the
    # driver asked for MORE radio about the race, with no cap on how much,
    # and one 30 s slot shared by places, stops, gaps, pace and the
    # championship would have been the cap he declined.
    MID_LAP_SPACING_S = 30.0
    # **Seconds between any two volunteered lines.** Two lines back to back
    # on one straight are a table, which §5.5 forbids: one thing, then a
    # corner, then the next. The longest NEWS line is ~5 s from the pack, so
    # this leaves at least seven seconds of silence after it - about one
    # braking zone at racing speed. Not a limit on how many a lap: a 2:02
    # Bathurst lap has room for eight at this spacing and the voice's gate,
    # not this, decides which of them find a straight.
    NEWS_SPACING_S = 12.0
    # Frames between two looks at the four race-news calls when the slot is
    # open. They read snapshots under a lock; ten times a second is plenty
    # for facts that are held for seconds before they are said.
    NEWS_EVERY_PACKETS = 6
    # **Seconds either side of a crossing the slot stays shut.** The crossing
    # speaks its own call - a box call among them - and the voice drops the
    # oldest of a queue three deep and anything eight seconds stale, so a
    # rival's name landing on the line can cost the instruction or itself.
    CROSSING_QUIET_S = 10.0

    def _reset_mid_lap(self) -> None:
        self._packets = 0
        self._last_mid_lap_packet: int | None = None
        self._crossed_at_packet: int | None = None
        self._lap_packets: int | None = None
        self._holding_logged: str | None = None
        self._was_in_pit = False
        self._left_pit_packet: int | None = None
        # Keys of cars that stood in the lane, ahead of us when they went in,
        # at any frame since the last place he was told - see `_through_the_lane`.
        self._lane_while_moving: dict[str, object] = {}
        # Calls handed to the voice and not yet heard, by `id` - see
        # `_hand_out`. Rule 11: a new race hears nothing about the last one's.
        self._in_flight: dict[int, tuple] = {}
        # A place call's lane explanation, applied when it is heard.
        self._lane_use: dict[int, tuple] = {}
        # The frame each mid-lap kind was last handed out on - see
        # `MID_LAP_SPACING_S`.
        self._last_kind_packet: dict[str, int] = {}

    def _note_crossing_for_mid_lap(self) -> None:
        """Qt thread, at the crossing: where the lap began, and how long it is
        likely to be, in packets. Two assignments the telemetry thread reads."""
        lap_ms = self.projected_lap_ms()
        self._lap_packets = (int(lap_ms * SAMPLE_HZ / 1000.0)
                             if lap_ms else None)
        self._crossed_at_packet = self._packets

    def _slot_is_open(self) -> str | None:
        """Why the mid-lap slot is shut, or `None` when it is open."""
        quiet = int(self.CROSSING_QUIET_S * SAMPLE_HZ)
        if self.state.in_pit:
            # Our own stop: the fill and the release are called in the box.
            return "in our own pit box"
        if (self._left_pit_packet is not None
                and self._packets - self._left_pit_packet < quiet):
            return "just out of the box"
        crossed = self._crossed_at_packet
        if crossed is not None:
            into = self._packets - crossed
            if into < quiet:
                return "just after the line"
            if self._lap_packets and into > self._lap_packets - quiet:
                return "coming up to the line"
        last = self._last_mid_lap_packet
        if last is not None and (self._packets - last
                                 < int(self.NEWS_SPACING_S * SAMPLE_HZ)):
            return "spacing"
        return None

    def _rested(self, kind: str) -> bool:
        """Whether a call of this kind may be handed out again yet."""
        last = self._last_kind_packet.get(kind)
        return last is None or (self._packets - last
                                >= int(self.MID_LAP_SPACING_S * SAMPLE_HZ))

    def _spoke_mid_lap(self, kind: str | None = None) -> None:
        self._last_mid_lap_packet = self._packets
        if kind is not None:
            self._last_kind_packet[kind] = self._packets
        self._holding_logged = None

    def _hold(self, what: str, why: str) -> None:
        """Log a held call once per reason, not sixty times a second."""
        key = f"{what}:{why}"
        if self._holding_logged != key:
            self._holding_logged = key
            log("race").info("held a %s call: %s", what, why)

    def _mid_lap(self, packet) -> "Call | None":
        """The one thing, if any, said between two crossings, off a frame.

        Three things may be said here first, in this order, each at most once
        per `MID_LAP_SPACING_S` and any two `NEWS_SPACING_S` apart:

        1. **"You're back on it."** - the word owed on the way back from an
           off (see `_compose`). It is not spaced: it is the end of a silence.
        2. **A rival's stop** not yet said. Perishable - he is in the box now
           and out in a minute - so it goes before a place, which keeps.
        3. **A place gained or lost**, once it has held, measured against the
           last place he was TOLD, and said through the lane where the lane
           made it.

        None of it on or near a crossing (`CROSSING_QUIET_S`), which belongs
        to the crossing's own call. A held call is never booked as said, so
        it is still true, and still said, when the slot opens.

        ### And the race around him (D7, 14 Sep 2026)

        After those three, **the four volunteered race calls** in
        `race/news.py`, in the driver's order of worth: what the stops mean
        for us, pace against a neighbour, a championship rival, the gaps.
        Any two volunteered lines are `NEWS_SPACING_S` apart and two of one
        kind `MID_LAP_SPACING_S`; there is no count per lap.

        **A place the pit lane made carries the stop picture, not "Not
        passes".** "P6 of 13. Not passes - 2 cars ahead boxed." and "P6 on
        the road. Effectively P8 after the stops." are the same event, and
        one call says it: where the lane explains a gain and the picture has
        an after-the-stops place to give, the picture IS the place call.
        """
        from pitcrew.race.calls import FACT, POSITION, RIVAL_BOXED

        proposal = self._note_position(packet)
        in_pit = bool(self.state.in_pit)
        if self._was_in_pit and not in_pit:
            self._left_pit_packet = self._packets
        self._was_in_pit = in_pit
        self._watch_the_lane_while_moving()
        shut = self._slot_is_open()
        if shut is not None and shut != "spacing":
            if proposal is not None:
                self._hold("position", shut)
            return None
        owed = self._compose(None)
        if owed is not None:
            self._spoke_mid_lap()
            return owed
        if shut is not None:
            if proposal is not None:
                self._hold("position", shut)
            return None
        rival = (self._rival_stop_mid_lap() if self._rested(RIVAL_BOXED)
                 else None)
        if rival is not None:
            self._spoke_mid_lap(RIVAL_BOXED)
            log("race").info("mid-lap: %s", rival.spoken())
            self._hand_out(rival)
            return rival
        if proposal is not None and self._rested(POSITION):
            if not self.composure.may_volunteer(FACT):
                self._hold("position", "off the road or still regathering")
                return None
            if self._place_waiting_on_the_voice(proposal):
                # **The same place, already handed over and not yet heard.**
                # The voice holds it for a straight; handing it over again
                # would queue it twice. A DIFFERENT place goes through, and
                # the voice replaces the queued line with it.
                self._hold("position", "that place is waiting on the voice")
                return None
            call = self._through_the_lane(proposal)
            call = self._place_with_the_picture(call)
            self._spoke_mid_lap(POSITION)
            log("race").info("mid-lap: %s", call.spoken())
            self._hand_out(call)
            return call
        return self._race_news()

    # ------------------------------------------------- the race around him

    def _required_stops(self) -> tuple[int | None, str | None, int]:
        """`(stops each rival is assumed to make, where that comes from, stops
        our plan makes)`.

        **The regulation minimum, and only that** (D7): nothing on the board
        says how often a rival will stop, so each is taken to stop as often
        as the rules make him, and every sentence built on it says so. Where
        the event states no requirement, our own plan's count stands in and
        the call is unconfirmed - it is an assumption about him drawn from us.
        """
        planned = max(0, len(self._stints) - 1)
        if self._mandatory_stops > 0:
            return self._mandatory_stops, "the regulations", planned
        if planned > 0:
            return planned, "our plan", planned
        return None, None, planned

    def _place_with_the_picture(self, call):
        """The place call, or the stop picture that says what it means."""
        use = self._lane_use.get(id(call))
        if use is None or not use[1]:
            return call                       # not a gain the lane made
        required, source, planned = self._required_stops()
        # The cars this place is about to explain are not explained yet -
        # that is booked when it is heard - so they are counted here.
        waiting = [key for key in use[2]
                   if not self.state.lane.explained(key)]
        picture = self.news.picture_call(
            self.state, self._packets, required=required,
            required_source=source, planned=planned,
            extra_dropped=len(waiting), position_called=call.position_called,
            hold=False)
        if picture is None:
            return call
        if not picture.reason.startswith("Effectively"):
            self.news.release(picture)
            return call
        self._lane_use.pop(id(call), None)
        self._lane_use[id(picture)] = (picture, use[1], use[2])
        log("race").info("the place is the stop picture: %s",
                         picture.spoken())
        return picture

    def _news_in_flight(self) -> bool:
        kinds = self._news_kinds()
        return any(call.kind in kinds
                   for call, _ in list(self._in_flight.values()))

    @staticmethod
    def _news_kinds() -> frozenset:
        from pitcrew.race.calls import GAPS, PACE, STOPS_PICTURE, WATCHED

        return frozenset({STOPS_PICTURE, PACE, WATCHED, GAPS})

    def _race_news(self) -> "Call | None":
        """The four volunteered race calls, best first, one at a time.

        **Never a second while one is waiting on the voice.** A line held for
        a straight is still the line he will hear; queueing the next behind
        it is how a queue fills with facts that go stale together. Where
        nothing answers for the voice (a replay), the spacing alone paces them.
        """
        from pitcrew.race.calls import (FACT, GAPS, PACE, STOPS_PICTURE,
                                        WATCHED, _crossing_the_line)

        if self._packets % self.NEWS_EVERY_PACKETS:
            return None
        state = self.state
        if (state.in_pit or state.finished or state.lap < 1
                or _crossing_the_line(state)
                or not self.composure.composed
                or not self.composure.may_volunteer(FACT)):
            return None
        if self.acknowledged_delivery and self._news_in_flight():
            self._hold("race news", "a line is waiting on the voice")
            return None
        now = self._packets
        required, source, planned = self._required_stops()
        builders = (
            (STOPS_PICTURE, lambda: self.news.picture_call(
                state, now, required=required, required_source=source,
                planned=planned)),
            (PACE, lambda: self.news.pace_call(state, now, lane=state.lane)),
            (WATCHED, lambda: self.news.watched_call(state, now)),
            (GAPS, lambda: self.news.gaps_call(state, now)),
        )
        for kind, build in builders:
            if not self._rested(kind):
                continue
            try:
                call = build()
            except Exception:
                log("race").exception("news: the %s call could not be made",
                                      kind)
                continue
            if call is None:
                continue
            self._spoke_mid_lap(kind)
            log("race").info("mid-lap: %s [%s]", call.spoken(),
                             call.why_spoken)
            self._hand_out(call)
            return call
        return None

    # ------------------------------------------------- said means heard
    #
    # **A volunteered fact is retired when the voice says it was HEARD, not
    # when it is handed over** (14 Sep 2026, after the voice fix). NEWS waits
    # for a straight and can go stale, be replaced by a newer place, or be
    # dropped for an instruction; a rival stop retired at hand-over was lost
    # every time that happened, which is the Bathurst defect - eight of ten
    # stops never said - one layer further down.
    #
    # So a rival stop, a place, and the tagged rival facts (committed, short,
    # closing) are IN FLIGHT from `_hand_out` until `delivered` is told what
    # happened: heard, and they are booked exactly as they used to be at
    # hand-over; not heard, and they are offered again, still subject to
    # their own staleness.
    #
    # **Only where something will answer.** `acknowledged_delivery` is set
    # by the controller, which routes the voice's answer back here; a
    # coordinator driven by a replay or a test has nobody to answer, and
    # books at hand-over as before rather than holding facts forever.
    #
    # **And a hand-over nobody answers is released** after `ACK_TIMEOUT_S`
    # (rule 10: a reference that nothing can retire is a latch). The voice's
    # slowest line goes stale at 30 s, so an answer later than that is one
    # that is never coming.

    acknowledged_delivery = False
    ACK_TIMEOUT_S = 45.0

    @staticmethod
    def _heard_matters(call) -> bool:
        from pitcrew.race.calls import (
            CLOSING, POSITION, RIVAL_BOXED, RIVAL_COMMITTED, RIVAL_SHORT)

        if call is None:
            return False
        if call.kind == POSITION:
            return call.position_called is not None
        # The race news books a band, a place or a figure as what he was
        # told - so only when he was told it (`race/news.py`).
        return call.kind in (RIVAL_BOXED, RIVAL_COMMITTED, RIVAL_SHORT,
                             CLOSING, *RaceCoordinator._news_kinds())

    def _hand_out(self, call) -> None:
        """`call` is being given to the voice: in flight, or booked now."""
        from pitcrew.race.calls import RIVAL_BOXED

        if not self._heard_matters(call):
            return
        if call.kind == RIVAL_BOXED:
            self.state.lane.offer(
                self.state.lane.keys_in_tag(RIVAL_BOXED, call.tag))
        if not self.acknowledged_delivery:
            self._book(call)
            return
        self._in_flight[id(call)] = (call, self._packets)

    def awaits_delivery(self, call) -> bool:
        """Whether `call` is in flight and wants to hear back from the voice."""
        entry = self._in_flight.get(id(call))
        return entry is not None and entry[0] is call

    def delivered(self, call, played: bool) -> None:
        """The voice's answer about a handed-over call. Qt thread.

        Heard: booked - the stop retired, the place the new baseline. Not
        heard: offered again. An answer about a call that is not in flight
        (a new race since, or already released) changes nothing.
        """
        if not self.awaits_delivery(call):
            return
        if self._in_flight.pop(id(call), None) is None:
            return                          # the timeout took it first
        if played:
            log("race").info("heard, so retired: %s", call.spoken())
            self._book(call)
        else:
            log("race").info("not heard, so offered again: %s",
                             call.spoken())
            self._release(call)

    def _book(self, call) -> None:
        from pitcrew.race.calls import POSITION, RIVAL_BOXED, position_spoken

        lane = self.state.lane
        if call.kind == RIVAL_BOXED:
            lane.tell(lane.keys_in_tag(RIVAL_BOXED, call.tag))
        elif call.kind in self._news_kinds():
            self.news.book(call)
        if call.kind == POSITION or (call.kind in self._news_kinds()
                                     and call.position_called is not None):
            # A stop picture that stood in for a place books the place too.
            position_spoken(self.state, call)
            use = self._lane_use.pop(id(call), None)
            if use is not None and use[0] is call:
                _, gained, keys = use
                (lane.explain if gained else lane.returned)(keys)

    def _release(self, call) -> None:
        from pitcrew.race.calls import RIVAL_BOXED

        lane = self.state.lane
        if call.kind == RIVAL_BOXED:
            lane.release(lane.keys_in_tag(RIVAL_BOXED, call.tag))
        if call.kind in self._news_kinds():
            self.news.release(call)
        if call.tag:
            # A crossing's tagged rival fact is "said" by its tag
            # (`_worth_saying_again`); unheard, it is sayable again.
            self.state.said_tags.discard(call.tag)
        self._lane_use.pop(id(call), None)

    def _place_waiting_on_the_voice(self, proposal) -> bool:
        from pitcrew.race.calls import POSITION

        # Any kind carrying the place: a stop picture can stand in for one.
        return any((call.kind == POSITION or call.position_called is not None)
                   and call.position_called == proposal.position_called
                   for call, _ in list(self._in_flight.values()))

    def _expire_in_flight(self) -> None:
        """Release what the voice never answered about. Telemetry thread."""
        if not self._in_flight:
            return
        limit = int(self.ACK_TIMEOUT_S * SAMPLE_HZ)
        for key, (call, at) in list(self._in_flight.items()):
            if self._packets - at <= limit:
                continue
            if self._in_flight.pop(key, None) is None:
                continue
            log("race").warning(
                "no word from the voice %.0f s after handing it %r - "
                "released and offered again", self.ACK_TIMEOUT_S,
                call.spoken())
            self._release(call)

    def _rival_stop_mid_lap(self) -> "Call | None":
        """The untold rival stops, if this is a moment to say them.

        Not from our own pit box - the fill is being called there - nor on
        the lap that is the flag, and not while he is regathering: it is not
        an instruction and it keeps until he is settled (race/lane.py says
        how long).
        """
        from pitcrew.race.calls import _crossing_the_line
        from pitcrew.race.rival_calls import boxed_call

        state = self.state
        if state.in_pit or state.finished or state.lap < 1:
            return None
        if _crossing_the_line(state) or not self.composure.composed:
            return None
        return boxed_call(state)

    def _watch_the_lane_while_moving(self) -> None:
        """Remember every car standing in the lane while the byte is away from
        the last place he was told.

        **Asked at the moment of speaking, the lane had already emptied.** A
        place gained on a car in its box is SAID up to half a minute later -
        the spacing, the crossing - and by then he may be back out: replayed
        at Bathurst, Car #31 left at 20:44:38, nine seconds before the call
        his stop had made. So the cars are collected while the place is
        moving and read when it is said.
        """
        state = self.state
        if state.position_said is None or state.position == state.position_said:
            if self._lane_while_moving:
                self._lane_while_moving = {}
            return
        for stop in state.lane.passed_in_the_lane():
            if stop.key not in self._lane_while_moving:
                self._lane_while_moving[stop.key] = stop

    def _through_the_lane(self, call) -> "Call":
        """The position call, with its reason taken from the pit lane where
        cars in the lane - not passes - moved the byte."""
        from pitcrew.race.calls import places_through_the_lane

        was, now = self.state.position_said, call.position_called
        if was is None or now is None or self.state.position_through_stop:
            return call
        lane = self.state.lane
        places = was - now
        if places > 0:
            cars = [stop for stop in self._lane_while_moving.values()
                    if not lane.explained(stop.key)]
        elif places < 0:
            cars = lane.back_out(self.state.lap)
        else:
            cars = []
        reason = places_through_the_lane(places, len(cars))
        if reason is None:
            return call
        used = [stop.key for stop in cars[:abs(places)]]
        call = replace(call, reason=reason)
        # **Marked explained when the place is HEARD** (`_book`), not here:
        # a line the voice drops has explained nothing to the driver, and the
        # same cars have to be able to explain the place when it is said.
        self._lane_use[id(call)] = (call, places > 0, used)
        log("race").info("position through the lane: %s (%s)",
                         reason, ", ".join(stop.driver
                                           for stop in cars[:abs(places)]))
        return call

    def _note_composure(self, packet) -> None:
        """Watch the surface, so the engineer knows when to stop volunteering.

        Reported from the seat: *"I came off track and was frustrated, and then
        George kept telling me every time someone passed me, which made me more
        angry."* See `race/composure.py`. The register that goes quiet is FACT
        only, and a decision is never withheld.
        """
        self.composure.update(getattr(packet, "surface_types", None),
                              1.0 / SAMPLE_HZ)

    def _compose(self, call):
        """Hold a volunteered fact while he is off the road or regathering.

        **Silence is only half of what he asked for.** The other half is a word
        on the way back, and it is deliberately a FACT rather than
        encouragement - what the moment actually cost. An engineer who tells a
        driver he is fine right after the driver lost four seconds is an
        engineer that driver stops believing.
        """
        from pitcrew.race.calls import POSITION, Call, register_of

        owed = self.composure.owed()
        if owed is not None:
            # Ahead of any held position call: the first thing he hears on the
            # way back is the account of the moment, not the places it cost.
            # **"That cost you N seconds" is the INCIDENT call's phrase
            # for lap time lost** (row 1.10), and this is seconds with a
            # wheel off the road - a smaller number, on a different clock,
            # landing first. One spin trips both.
            return Call(POSITION, self.state.lap, "You're back on it.",
                        f"About {owed:.0f} seconds off the road.")
        if call is None:
            return None
        if self.composure.may_volunteer(register_of(call.kind)):
            return call
        # **Held, not booked.** Nothing here marks the call said: a position
        # held while he is off the road is measured against what he last
        # heard when it is finally said (`calls.position_spoken`).
        log("race").info("held a %s call: off the road or still regathering",
                         call.kind)
        return None

    def _note_position(self, packet) -> "Call | None":
        """Where he is in the field, off the packet, at 60 Hz.

        **The field has been decoded correctly all along and read by
        nothing.** `packet.current_position` and `cars_in_race` reach
        `session_state.py` and stop there; no module in this package has ever
        looked at either, so every race the engineer has run was run as though
        the driver were alone on the circuit. Verified against the archive
        before wiring it: `laps.position` reads P3 to P1 across session 49 -
        the Watkins race won from P3 - and P10 to P5 at Fuji.

        Guarded rather than trusted. `current_position` already returns 0 for
        anything outside 1..100, and 0 is "no reading" here, never a position.
        """
        from pitcrew.race.calls import position_change

        position = getattr(packet, "current_position", None)
        if position:
            self.state.position = position
        field = getattr(packet, "cars_in_race", None)
        if field:
            self.state.field_size = field
        return position_change(self.state)

    def _note_lap_counter(self, packet) -> None:
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

    def _may(self, trigger: str, action: str) -> bool:
        """Whether George may do this on his own.

        **The bound is the ACTION, not the playbook.** Four actions change
        the plan's shape - `handover.STRUCTURAL_ACTIONS` - and George may take
        one only where the desk wrote it down. Everything else is free, and
        free means free: it does not consult the playbook, it does not care
        whether one exists, and an author who forgot an entry cannot silence
        a lever the driver is expecting.

        **This replaces two failure modes of one mechanism.** The gate used to
        permit whatever a playbook happened to name, and to permit everything
        when there was no playbook - so a plan the app wrote itself left
        George unbounded, while a handover that omitted `short_shift` took the
        shift beep away from a driver who had been promised it. Neither was a
        decision anybody took. The driver's, 29 Aug 2026: the rail gates the
        structural four and nothing else.

        A structural action with no playbook at all is REFUSED, which is the
        one place absence now means no rather than yes. That is the safe
        direction: George cannot put him in the pit lane on the strength of a
        file nobody wrote.
        """
        # **`handover.grants` is the expression**, not a second copy of it
        # here. The standing orders on the Race page tell the driver what
        # George may do without asking, and they were computed from "is there
        # an entry" while this was computed from the action - so the screen
        # said "George falls back to his own" about the two decisions this
        # refuses him (row 1.7, critic pass 1).
        from pitcrew.strategy.handover import grants

        return grants(self._playbook, trigger, action)

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

    # **The top of CLAUDE.md 5.1's phase-2 degradation band**, in seconds per
    # lap of cumulative loss. `[DOCTRINE]`, and it is used for one thing only:
    # to make the engineer LESS certain. Using an assumed figure to widen a
    # hedge is legitimate where using it to assert would not be - it can only
    # move the answer from a flat number to one of two, never the other way,
    # so no claim rests on it being right.
    DEGRADATION_S_PER_LAP = 1.5

    def _degradation_headroom_s(self) -> float:
        """How far the divisor may be optimistic because the tyre has gone off.

        **The predictor is a median over laps already driven, and the laps
        still to come are slower than it.** Computed against 5.1's band at a
        base lap of 100 s: eighteen laps into a stint the remaining laps take
        4.8 s/lap more than the median at the bottom of the band and 14.2 s
        more at the top, against a measured lap-to-lap sigma of 2.04 s. The
        count is one lap long across the whole band and two at the top of it
        over ten laps.

        `laps_left_margin_s` cannot see any of that: it is the headroom before
        the ceiling flips, compared against RANDOM noise, and this is a
        SYSTEMATIC bias. A test of resolvability was being read as a test of
        correctness.

        **The predictor itself is not changed, deliberately.** Lap-time
        degradation is below this driver's own detection floor - sigma 0.918 s
        puts it at 1.74 s/lap against a 0.5-1.5 band - so no trend can be
        fitted from his laps, and swapping the median for a recent window
        scored WORSE on the three timed races on file, 30% against 58%.

        Halved because the bias grows through the stint and this is its
        average over the laps that made the median.

        **`laps_since_stop` is an imperfect proxy** and is named as one: the
        predictor is a whole-race median, not a stint one, so a tyre change
        snaps this to zero at the crossing where the median is most
        contaminated by the worn laps before it. It errs toward saying the
        count is firm just after a stop, which is where the margin is widest
        anyway. Fixing it properly means a stint-scoped predictor.
        """
        stint_laps = max(0, self.state.laps_since_stop)
        return self.DEGRADATION_S_PER_LAP * stint_laps / 2.0

    def _stop_costs_laps(self, lap_ms: int | None,
                         left: int | None) -> int | None:
        """How many laps a remaining stop actually costs, or None.

        The difference between the crossings that fit with the stop's clock
        spent and the crossings that fit without it. Usually zero: a 20 s stop
        on a 100 s lap only removes a lap when the remaining time happens to
        sit inside 20 s of a whole number of them.

        **`None` unless `events.pit_loss_source` says `measured`**, and that
        is the whole of the check. The column is `REAL NOT NULL DEFAULT 20.0`,
        so `pit_loss_s` is never falsy and a test on the VALUE is unreachable
        - the first draft of this had one, called it a safeguard, and shipped
        the app's own untouched default as a measured cost. `schema.py` says
        it in as many words: no reader may treat the value as declared without
        the source saying so.

        It is not academic. Road Atlanta's real ex-fuel loss works out at
        about 23.7 s from the archive - the pit lap less the green median,
        less the fuel taken at the declared rate - against the typed 20, and
        that difference is the one crossing of that race where the stop truly
        cost a lap and this said nothing.
        """
        pending = self._pending_stops()
        if not pending or not self.pit_loss_s or not self.pit_loss_measured:
            return None
        with_stop = self.clock.laps_left(
            lap_ms, less_s=pending * self.pit_loss_s)
        if with_stop is None:
            return None
        return max(0, left - with_stop)

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

    # Laps driven under a save that the projection averages: one lap is a
    # lap, and a save that is working shows on the next as well.
    SAVE_PACE_LAPS = 2

    def note_save_asked(self, lap: int) -> None:
        """A fuel save was asked for at this crossing. The first ask stands."""
        if self._save_asked_lap is None:
            self._save_asked_lap = int(lap)

    def projected_lap_ms(self) -> int | None:
        """The lap a timed race's remaining distance is divided by.

        **The achieved median, unless he has been asked to save and is.**
        Suzuka, 13 Sep 2026: 128.4 s left, a 126.7 s median, and a lap of
        132.9 driven lifting - "Two to go." on the last lap. Under a save the
        laps still to come are the saving laps, so the recent ones since the
        ask count when they are slower. Without an ask a slow lap is an off
        (lap 10 there) and the median stands, as it always has.

        One figure for every reader: the distance, the hedge's margin, the
        stop's price, and the re-planner's unit (rule 13).
        """
        achieved = (self.expect.achieved_lap_time_ms()
                    or self.planned_lap_time_ms)
        asked = self._save_asked_lap
        if not achieved or asked is None:
            return achieved
        saving = [ms for num, ms in self._racing_laps
                  if num > asked][-self.SAVE_PACE_LAPS:]
        if not saving:
            return achieved
        return max(achieved, int(sum(saving) / len(saving)))

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
        lap_ms = self.projected_lap_ms()
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
        # **What the margin has to clear, and what it deliberately does not.**
        #
        # `laps_left_margin_s` is the headroom before the ceiling flips,
        # compared against lap-to-lap NOISE. It is silent on the two
        # systematic offsets - a pending stop's clock, and the degradation
        # bias in a median taken over younger tyres - and both can move the
        # answer by a whole lap.
        #
        # Those belong to the VOICE, not to this flag: `laps_count_hedged`
        # below carries them and turns a flat number into a pair. This one
        # sizes fills - `fuel_margin_l` answers False with a WHOLE LAP - and
        # widening it put a spare lap in every timed-race tank, 2.2-4.7 L at
        # Yas and 3.4-5.6 L at Road Atlanta, four seconds parked. The driver,
        # 29 Aug 2026: *"I will only need to stop again if I need fuel and you
        # can work that out."*
        #
        # So: the noise test, and only the noise test, which is also what it
        # was before any of this work. Three stacked comment blocks here said
        # the opposite - two of them that a pending-stop term was "restored,
        # deliberately" - describing an expression that has not carried one
        # since `6d15652`. In a codebase whose method is that the comment is
        # the argument, a comment asserting conservatism the code does not
        # have is the most dangerous thing in the file.
        _firm_noise = bool(margin is not None and sigma is not None
                           and margin >= sigma / 1000.0)
        # What the VOICE needs, which is a different question: is the number
        # good enough to say flat? Noise, plus the bias the noise test cannot
        # see. Nothing sizes a fill off this.
        self.state.laps_count_hedged = bool(
            margin is None or sigma is None
            or margin < (sigma / 1000.0) + self._degradation_headroom_s())

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
        # **The raw clock, never a discounted count.** Putting a
        # stop-discounted distance here moved
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
        self.state.laps_total = (self.state.lap + self.state.laps_missed()
                                 + left)
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
        # **He may simply not stop, and he often does not.** A count with the
        # stop taken out of it is wrong by a lap when the stop is not taken -
        # he skipped one in two recorded races and was right both times. So
        # the count is the undiscounted one, right if he stays out, and the
        # stop is priced beside it.
        #
        # **Priced from the model, never asserted.** "one less if you stop"
        # as a constant is wrong on 15 of the 18 second-half crossings of the
        # two timed races on file: at 20 s of pit loss against a 82-120 s lap
        # the stop usually costs no lap at all, and saying otherwise told him
        # there was less race than there is - the same direction as the clock
        # rounding this file just fixed. `None` where no pit loss has been
        # measured, because a cost nobody has measured may not be spoken as
        # one (rules 3 and 5).
        #
        # Computed AFTER `laps_total` is written: `_pending_stops` asks
        # `stop_still_needed`, which reads `laps_remaining()`, which reads
        # `laps_total` - so computing it above the write measured this
        # crossing against the previous crossing's distance and answered the
        # stop question wrongly whenever the two differed.
        self.state.stop_pending = self._pending_stops() > 0
        self.state.stop_costs_laps = self._stop_costs_laps(lap_ms, left)
        # **Below the `laps_total` write, and this is why.** `_pending_stops`
        # asks `stop_still_needed`, which reads `laps_remaining()`, which
        # reads `laps_total` - so asked above the write it measures this
        # crossing against the previous crossing's distance. `stop_pending`
        # was moved for exactly that reason and this branch was left behind,
        # which is worse: it sizes the FILL. Measured at the crossing where a
        # stop stops being needed, it asked for 6.00 L of margin where 1.20 L
        # is right - 4.8 L, about 4.8 s stationary at the measured rate, in
        # the direction he has refused.
        self.state.laps_estimate_firm = _firm_noise
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
        # **In-laps gone by, not laps past the box call.** "Box this lap." is
        # said on the in-lap (overdue 0), so an overdue count of two is two
        # box calls he drove past - the same two it was before the ladder
        # moved a lap earlier (14 Sep 2026).
        overdue = state.laps_overdue() or 0
        if overdue < BOX_IGNORED_LAPS:
            return None
        call = stay_out_call(state)
        if call is None:
            return None
        # Internally adopt the zero-stop shape for the remainder: one stint
        # to the flag, no compound waiting, the fuel target becomes the flag.
        remaining = state.laps_remaining()
        # **The fold is free, and it is free because it is not George's
        # decision.** It reads like `drop_stop` - the plan goes from one stop
        # to none - and it is the opposite: the driver has already declined
        # the stop with his hands, two laps ago, by driving past the box.
        # George is recognising that, not taking it.
        #
        # Refusing to recognise it is not caution, it is the nine-box-calls
        # defect: the plan of record still holds a stop that will never
        # happen, so the box call fires on the next lap, and the next, all
        # the way to the flag. `_reconsider_ignored_box` exists to stop
        # exactly that, and gating it gave the fault back.
        #
        # George deciding a *planned and still-reachable* stop is unnecessary
        # is `drop_stop`, it is structural, and it is gated. This is not it.
        if remaining:
            self.adopt((remaining,))
        else:
            state.stint_ends_on_lap = None
            state.next_stint_laps = None
            state.next_compound = None
            state.next_tyres = None
        return call

    def observed_fuel_per_lap(self) -> float | None:
        """The race's own burn, or None before enough green laps exist.

        Green laps only. Measured: burn on a green lap has a CV of 2.0% and
        burn on any lap at all has a CV of 10.4%, the whole spread coming from
        incident laps and laps he was deliberately saving on.
        """
        # The burn the race is being run on - this stint's once it can speak
        # (0.9), so the re-planner and the fill read one number, not two.
        green = self.expect.current_fuel_per_lap_l()
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
        # **The briefing first, then the playbook.** They cut different
        # things: the briefing can drop a whole call Ludo does not want made
        # here, the playbook strips a structural instruction off one that is
        # still said. Running the briefing first means the playbook is never
        # asked about a call nobody is going to hear.
        call = self._within_the_briefing(call)
        call = self._within_the_playbook(call)
        heartbeat = call if call is not None and call.kind == STATUS else None
        if call is not None and heartbeat is None:
            self.state.record(call)
            self._hand_out(call)
            if call.kind == FUEL_SHORT and call.tag == FUEL_SAVE:
                self.note_save_asked(self.state.lap)
            elif call.kind == FUEL_REACHES:
                self._save_asked_lap = None
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

    def _within_the_briefing(self, call: Call | None) -> Call | None:
        """The call, unless Ludo said not to make this one here.

        **The rail expressed as knowledge rather than as a veto.** The playbook
        gates four structural actions and nothing else; this is the other half
        of the same idea, and it is the half that carries a reason: *"don't
        call short-shift here, the straights are too short to pay."* Ludo
        teaching George, not muzzling him.

        **A DECISION may be silenced; an EVENT may not.** The green, the flag,
        an incident and the run-in are true exactly once and cannot be asked
        for afterwards, so turning one off does not quiet the engineer, it
        deletes the only chance the driver had to hear it. A record trying to
        is refused at `Knowledge.validate` time for a kind that does not exist,
        and here for one that does but must not be silenced.

        Logged with the reason, because a call that does not happen is
        indistinguishable from an engineer with nothing to say - which is the
        silence this app keeps having to explain afterwards.
        """
        from pitcrew.race.calls import DECISION, register_of

        if call is None or self.knowledge is None:
            return call
        why = self.knowledge.silences(call.kind)
        if not why:
            return call
        if register_of(call.kind) is not DECISION:
            log("race").warning(
                "the briefing asks for %r to be off, and it is not a decision "
                "- it is true once and cannot be asked for afterwards, so it "
                "is being said anyway. Reason on file: %s", call.kind, why)
            return call
        log("race").info("%r withheld: the briefing says %s", call.kind, why)
        return None

    def _within_the_playbook(self, call: Call | None) -> Call | None:
        """The call as made, with any structural instruction the desk withheld.

        **The words always stay; only a structural instruction can go.** A
        fuel call that names the shortfall is a report and he keeps it
        whatever the playbook says.

        **`short_shift` no longer passes through here, and that is the
        change.** It used to be stripped whenever the playbook omitted it -
        so a handover that forgot one entry took the shift beep away from a
        driver who had been told to short-shift, silently. Short-shifting
        changes how a lap is driven, not what the plan is; it costs a lap, it
        is reversible on the next one, and the driver's levers are his own.
        The rail is for the four that are not reversible - see
        `handover.STRUCTURAL_ACTIONS`.

        **Two calls ride one, as of 7 Sep 2026.** `STOPS_OFF` is a
        `drop_stop` under `fuel_long`; the wear cliff's "Box this lap" is an
        `add_stop` under `tyre_short` when no stop was planned. Withheld,
        each falls back to its `report_form` - the reading, the litres - so
        the driver hears what was seen and decides the shape himself. That
        is the Daytona handover's `fuel_long: report_only`, executed.

        **The trigger is the call's own**, not its kind: no kind is a
        trigger, so the old lookup refused everything the desk had granted.
        """
        if call is None or not call.structural_action:
            return call
        trigger = call.trigger or call.kind.replace("-", "_")
        if self._may(trigger, call.structural_action):
            return call
        log("race").info(
            "structural instruction %r withheld on a %r call: the playbook "
            "does not grant it under %r. The call still says what it saw.",
            call.structural_action, call.kind, trigger)
        return replace(call, structural_action=None,
                       call=call.report_form or call.call)

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

    def adopt(self, stint_laps, *, compounds=None, fuel_l=None,
              tyres=None) -> None:
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
            # **The tyres decision travels with the stint** (the critic on
            # row 2.6): rebuilt without it, "No tyres." became a bare "RS."
            # the moment he accepted a re-plan. A changed compound is a set
            # going on, whatever the old stint said.
            #
            # **Where the re-planner priced a decision, its decision wins**
            # (pass 2, MAJOR). Carried by position alone, a re-plan that
            # added a stop moved "No tyres." - made for a lap-14 stop with six
            # to go - onto a new lap-8 stop with twelve, and left the added
            # stop with no decision at all. `recommend` priced every one of
            # those stops as a fresh set; the old decision contradicts it.
            previous = fresh[-1] if fresh else (done[-1] if done else None)
            before = previous.get("compound") if isinstance(previous, dict) else None
            priced = (tyres[offset]
                      if tyres is not None and offset < len(tyres) else None)
            # **And the desk's decision stands where the shape keeps its stop
            # count** (pass 3, the merge of the two critics). Pass 2: carried
            # by position across a CHANGED count, "No tyres." landed on a stop
            # it was never made for. Pass 3: replacing it everywhere turned a
            # fuel-only plan into "RS on." on an offer that never mentioned
            # tyres. Same count, same stops: the desk's answer. A changed
            # count describes stops the desk never decided, and the priced
            # decision is the only answer there is.
            desk = was.get("tyres")
            reshaped = len(stint_laps) != len(planned)
            decided = (priced if priced is not None
                       and (reshaped or desk is None) else desk)
            if compound and before and compound != before:
                decided = True
            fresh.append({"laps": laps, "compound": compound,
                          "fuel_l": litres, "start_lap": start,
                          "tyres": decided})
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
            # **What GT7 is showing him**, which is the same lap counted by
            # the other party. Beside `lapInProgress` rather than replacing
            # it, because the two disagree exactly when a crossing has gone
            # missing and that disagreement is a finding, not a nuisance:
            # `lapInProgress` is the app's arithmetic, this is the game's own
            # answer, and only this one may be spoken. See
            # `RaceState.lap_on_screen`.
            "screenLap": self.state.lap_on_screen(),
            "lapsTotal": self.state.laps_total,
            # Set for a timed race, where `lapsTotal` is the plan's expected
            # distance rather than a regulation, so nothing downstream reads
            # it as one.
            "raceMinutes": self.state.race_minutes,
            "lapsRemaining": self.state.laps_remaining(),
            "position": self.state.position,
            # **How many cars he is a position OUT OF.** "P8" and "P8 of 9"
            # are different pieces of news and only the second one is
            # actionable. Decoded from the packet since the parser was
            # written and read by nothing until 29 Aug 2026.
            "fieldSize": self.state.field_size,
            # Whether the remaining-lap figure of a timed race is worth
            # quoting as a count. It divides a measured clock by a noisy
            # median, so early in a race it is unresolvable - and the PTT
            # answers "how long left" from it.
            "lapsEstimateFirm": self.state.laps_estimate_firm,
            # Whether the heartbeat says that count as a pair. The PTT answer
            # to "laps left" must hedge it the same way (rule 13).
            "lapsCountHedged": self.state.laps_count_hedged,
            "fuelL": self.state.fuel_l,
            # **Absolute: tank divided by burn.** Not a margin, and the PTT
            # answer used to say "8.2 laps of fuel" off it while the
            # volunteered call said "1.9 laps of fuel in hand to the stop"
            # off `_fuel_gap` - one phrase, two quantities, and the failure
            # direction that kills a race is hearing the absolute as the
            # margin (row 1.10, rule 13).
            "lapsOfFuel": self.state.laps_of_fuel(),
            # The margin and the distance it is a margin TO, from the one
            # expression that produces both.
            **dict(zip(("fuelInHand", "fuelReference"),
                       fuel_in_hand(self.state))),
            "lapsToStop": self.state.laps_to_stop(),
            # **The sign `laps_to_stop()` throws away when it clamps at
            # zero.** The Race screen has an OVERDUE branch keyed on a
            # negative that could never arrive, so a driver three laps past
            # his box lap read "BOX IN 0" - which its own comment calls a
            # different instruction from "you are three laps late", and rule
            # 9 on the highest-consequence number the app emits. The driver
            # board recovered the sign through `past_box_lap`; the desk
            # screen had no equivalent (the critic on row 1.10).
            # **Off `laps_to_stop`'s own retirement, not off the raw
            # field** (the critic on row 1.10). Read raw, this became the
            # FIFTH surface counting a stop the engineer had cancelled - and
            # the loudest: the desk screen showed OVERDUE / "3 LATE" in
            # warning ink on the lap "You're fuelled to the flag. No more
            # stops on fuel." went out, and again in the box and after the
            # flag, where every voice call is silent by design.
            # **`laps_overdue()`, the box call's own count**: 0 on the
            # in-lap, where the box call says "Box this lap." and nothing is
            # late, N once N in-laps have gone by (14 Sep 2026).
            "lapsPastBox": (
                self.state.laps_overdue()
                if self.state.past_box_lap
                and not self.state.in_pit and not self.state.finished
                else None),
            # **Only while there IS a next stop** (the critic on row 2.6, pass
            # 3). After the fuel retired the stop the call said "No more stops
            # on fuel." and "what tyres?" still answered "Tyres on." - the
            # stop's decision outliving the stop. `lapsToStop` is the same
            # expression BOX_WHEN answers "No stop planned" from.
            "nextCompound": (self.state.next_compound
                             if self.state.laps_to_stop() is not None
                             else None),
            # The plan's tyre decision for that stop, tri-state, so the
            # radio answers "what tyres" in the box call's own words
            # (the critic on row 2.6).
            "nextTyres": (self.state.next_tyres
                          if self.state.laps_to_stop() is not None else None),
            "inPit": self.state.in_pit,
            # **The flag, because the box reading has to know about it.**
            # Post-flag with a stop never taken the Race screen read "BOX IN
            # 0" - which the whole `lapsPastBox` exercise established means
            # "box now" - about a race that is over. `driver_view` has
            # checked its own `finished` since it was written.
            "finished": self.state.finished,
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
        tyre_wear_mult=event.get("tyre_wear_mult"),
        start_type=event.get("start_type"),
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
