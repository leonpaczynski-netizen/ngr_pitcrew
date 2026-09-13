"""The 16 Aug race, replayed against the engineer that failed it.

Session 44, Yas Marina, a 30-minute race the plan expected to take 15 laps and
a 2-stop shape the race left behind: the driver ran a feasible zero-stop,
never pitted, and finished with 1.79 litres. The engineer of that night said
"Box this lap. RS. Fuel to 27 litres." verbatim on every lap from 7 to 15 -
the ninth voiced on his chequered-flag crossing - while the one unanswered
re-plan offer from minute two gagged every later assessment.

**This file now drives the redesign the driver asked for**, which is a
different engineer: an app race clock started at the green (GT7's own clock is
not accurate and nothing in race control reads it), the whole strategy problem
re-solved at every crossing, and a register that speaks only when the answer
has materially changed. Recalculating every lap makes announcing every lap
trivially easy to do by accident, so most of what is asserted here is silence.

The replay drives RaceCoordinator, PlanRegister and assess through the exact
shape of that night - the same plan, burns, lap times, positions and (but for
lap one, taken from the measured stone-cold session 43 start so the cold
branch is exercised; the real lap one was grid-warmed) the same temperatures -
and asserts the race the engineer should have called. The unit tests below it
pin each mechanism on its own.
"""
from __future__ import annotations

import pytest

from pitcrew.controller import PitCrewController
from pitcrew.race.calls import (
    BOX_NOW,
    BOX_SOON,
    CHEQUER,
    FUEL_LONG,
    HIGH,
    LAPS_TO_GO,
    MEDIUM,
    STATUS,
    STAY_OUT,
    TYRE_TEMP,
    RaceState,
    _fuel_instruction,
    _laps_to_go,
    fuel_target_l,
    next_call,
    stay_out_call,
)
from pitcrew.race.clock import STREAM_HZ, RaceClock
from pitcrew.race.coordinator import (
    PlanContext,
    RaceCoordinator,
    context_from_event,
)
from pitcrew.race.expectations import (
    PRACTICE,
    RACE,
    ExpectationTracker,
    detectable_delta_ms,
)
from pitcrew.race.replan import (
    BAND_ON,
    BAND_UNDER,
    NONE,
    RECOMMENDED,
    RESOLVED_ACCEPTED,
    RESOLVED_KEPT,
    URGENT,
    PlanRegister,
    Replan,
    assess,
    burn_band,
    materially_different,
)
from pitcrew.race.temps import lap_axle_means, window_from_samples
from pitcrew.strategy.model import CompoundProfile, RaceInputs
from pitcrew.telemetry.session_state import (
    EventKind,
    Lap,
    SessionEvent,
    SessionKind,
    SessionState,
)

from .conftest import make_packet


# ------------------------------------------------------------- tonight's race

# The approved plan: strategy 3, "2 stops", stints 7/3/5, all RS, assumed
# 7.563 L/lap, reference 118.940 s, for a timed 30-minute race.
PLAN = {"stints": [
    {"laps": 7, "compound": "RS", "fuel_l": 52.9, "start_lap": 1},
    {"laps": 3, "compound": "RS", "fuel_l": 27.0, "start_lap": 8},
    {"laps": 5, "compound": "RS", "fuel_l": 41.6, "start_lap": 11},
]}
PLANNED_BURN = 7.563
PLANNED_LAP_MS = 118_940
RACE_SECONDS = 30 * 60

# **The standing start, measured.** `standing_start_ms` on race lap 1 was
# 44,283: the time between the green - where the app clock starts - and the
# first line crossing, which is where the lap-time sum starts. It is the
# offset the two measures of elapsed time are reconciled against, and it is a
# measurement rather than an error.
STANDING_START_S = 44.283

# lap: (time_ms, position, fuel_end, fuel_used, front_mean, rear_mean).
# Lap 1's temps are session 43's measured stone-cold start (59.3/61.5);
# everything else is session 44 as recorded.
LAPS = {
    1: (121_511, 4, 92.84, 0.00, 59.3, 61.5),
    2: (117_724, 4, 86.09, 6.75, 73.0, 78.3),
    3: (117_318, 4, 79.32, 6.77, 74.9, 79.9),
    4: (126_254, 4, 72.50, 6.82, 74.4, 82.3),
    5: (129_989, 7, 65.61, 6.89, 76.3, 86.0),
    6: (120_073, 6, 58.88, 6.73, 72.0, 81.4),
    7: (119_170, 6, 51.95, 6.93, 72.9, 81.7),
    8: (119_557, 6, 45.10, 6.85, 73.5, 81.6),
    9: (121_826, 5, 38.10, 7.00, 74.0, 83.2),
    10: (124_059, 4, 31.35, 6.75, 73.8, 84.7),
    11: (119_624, 4, 24.68, 6.67, 73.5, 82.9),
    12: (119_729, 4, 18.11, 6.57, 73.5, 82.4),
    13: (130_443, 4, 12.18, 5.93, 74.0, 81.8),
    14: (124_332, 4, 7.74, 4.44, 70.5, 78.8),
    15: (129_675, 5, 1.79, 5.95, 72.4, 79.1),
}

# The measured running range for this car at this track: practice sessions
# 41-43 ran F 70-77 / R 77-88 steady, up to temperature in about two laps.
# **A description of where he has been, not a window** - see `race/temps.py`.
WINDOW_FRONT = (70.0, 77.0)
WINDOW_REAR = (77.0, 88.0)


class FakeMonotonic:
    """A clock the test drives, so a 30-minute race runs in milliseconds."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def lap_event(lap_num: int) -> SessionEvent:
    time_ms, position, fuel_end, fuel_used, front, rear = LAPS[lap_num]
    lap = Lap(
        lap_num=lap_num, lap_time_ms=time_ms, best_lap_ms=117_318,
        delta_ms=time_ms - 117_318,
        fuel_start=fuel_end + fuel_used, fuel_end=fuel_end,
        fuel_used=fuel_used, position=position,
        is_pit_lap=False, is_out_lap=False,
        tyre_temp_front_c=front, tyre_temp_rear_c=rear,
    )
    # The GT7 clock still travels on the event, because the screen may want to
    # show it. **Nothing in race control reads it** - the driver measured it as
    # inaccurate - and this replay proves it by sending a figure that is
    # nonsense: if any decision moved with it, these tests would say so.
    return SessionEvent(EventKind.LAP_COMPLETED,
                        {"lap": lap, "remaining_time_ms": -1})


# **The event row as the app actually stores it.** Every fixture below is
# driven through `context_from_event` from this, and nothing invents a tidier
# name: the tyre-temperature association is keyed on `circuit/car` composed
# from these exact strings, it was written once against an invented
# `track="Yas Marina", layout=None`, and the consequence was a scope that
# matched nothing - the conserve call could not fire for a whole race while
# every test covering it passed.
EVENT_ROW = {
    "car_name": "Ford Shelby GT350R '16",
    "track": "Yas Marina Circuit",
    "layout": "Full Course",
    "race_type": "time",
    "race_laps": 30,
}


def a_timed_context() -> PlanContext:
    return context_from_event(EVENT_ROW)


def tonight_inputs() -> RaceInputs:
    """The rest of the race as the strategy model sees it, from practice."""
    return RaceInputs(
        race_laps=15, race_minutes=30.0, lap_time_ms=PLANNED_LAP_MS,
        fuel_per_lap_l=PLANNED_BURN, fuel_capacity_l=100.0,
        refuel_rate_lps=2.0, pit_loss_s=20.0, wear_per_lap=0.03161,
        available_compounds=("RS",), evidence_compound="RS",
        compound_profiles={"RS": CompoundProfile(
            "RS", 0.0, 0.03161, "measured", laps_measured=13,
            stints_measured=2, longest_stint_laps=7)})


def tonight(now: FakeMonotonic | None = None) -> RaceCoordinator:
    race = RaceCoordinator(
        PLAN,
        fuel_per_lap_l=PLANNED_BURN,
        wear_per_lap=0.03161,
        fuel_capacity_l=100.0,
        # No measured short-shift trade for the Shelby - the fold call must
        # name the lever without inventing a number.
        short_shift_l_per_1000rpm=None,
        lap_time_ms=PLANNED_LAP_MS,
        practice_lap_samples=8, practice_fuel_samples=8,
        now=now)
    assert race.arm(a_timed_context(), a_timed_context()) is True
    race.state.temp_window_front = WINDOW_FRONT
    race.state.temp_window_rear = WINDOW_REAR
    race.state.temp_laps_to_window = 2
    return race


def replay():
    """Drive the race and the re-plan loop the way the controller wires them.

    Returns (race, calls, spoken, clock). `spoken` is every recomputation the
    register decided to voice - the whole point being how few there are. The
    driver never answers a recommendation out loud: he is under a helmet,
    which is why nothing waits for him any more.
    """
    now = FakeMonotonic()
    race = tonight(now)
    register = PlanRegister()
    inputs = tonight_inputs()
    calls, spoken = [], []

    green = race.handle(SessionEvent(EventKind.RACE_STARTED,
                                     {"laps_in_race": 0}))
    if green:
        calls.append(green)
    # Between the green and the first crossing: the grid, the launch, and the
    # standing start. The app clock is running through all of it.
    now.advance(STANDING_START_S)

    for lap_num in range(1, 16):
        now.advance(LAPS[lap_num][0] / 1000.0)
        call = race.handle(lap_event(lap_num))
        if call:
            calls.append(call)
            if call.kind == STAY_OUT:
                register.note_driver_shape(race.stops_planned(), lap=call.lap)
        verdict = assess(
            laps_done=race.state.lap,
            laps_total=race.state.laps_total,
            fuel_l=race.state.fuel_l,
            planned_fuel_per_lap=race.planned_fuel_per_lap_l,
            observed_fuel_per_lap_l=race.observed_fuel_per_lap(),
            lap_time_ms=race.representative_pace_ms(),
            planned_lap_time_ms=PLANNED_LAP_MS,
            current_stops=race.stops_planned(),
            inputs=inputs,
            fuel_capacity_l=100.0,
        )
        outcome = register.consider(
            verdict, lap=race.state.lap,
            burn_drift=race.expect.burn_vs_plan(),
            race_evidence=race.observed_fuel_per_lap() is not None,
            # **The same arbitration the controller does.** Without it this
            # harness certifies a race the app would never run: on lap 8 both
            # producers spoke, and the driver heard "Recommend running to the
            # flag" followed by "Box this lap, one lap overdue".
            may_speak=lambda candidate: PitCrewController._replan_outranks(
                candidate, call))
        if outcome.spoken:
            spoken.append(outcome)
    return race, calls, spoken, race.clock


@pytest.fixture(scope="module")
def raced():
    return replay()


def test_nothing_is_offered_before_the_race_has_shown_anything(raced):
    """The lap-1 offer of the real night - "lapping 2% slower than planned",
    voiced two minutes in - must not exist in any form.

    Nor may its successor. The model prefers a 1-stop over the approved 2-stop
    from the very first crossing, on practice numbers alone, because the
    approved plan is the driver's choice among ranked options and not always
    the model's favourite. Re-offering the model's favourite two minutes after
    the green is not re-planning; it is arguing about a decision he has
    already made."""
    _, _, spoken, _ = raced
    assert all(item.lap >= 8 for item in spoken)


def test_one_thing_is_said_per_crossing_across_both_producers(raced):
    """**The defect this asserts against is in the certifying replay itself.**
    The coordinator and the re-planner used to be voiced independently, in
    whatever order the code ran them, and on lap 8 the driver heard "Recommend
    running to the flag." followed by "Box this lap. RS. 1 lap overdue." -
    two opposite instructions two hundred milliseconds apart, in the exact
    race this engineer was rebuilt for. §5.5 allows one."""
    _, calls, spoken, _ = raced
    per_lap = {}
    for call in calls:
        per_lap.setdefault(call.lap, []).append(call.kind)
    for item in spoken:
        per_lap.setdefault(item.lap, []).append("replan")
    crowded = {lap: kinds for lap, kinds in per_lap.items() if len(kinds) > 1}
    assert crowded == {}


def test_the_engineer_speaks_the_whole_race_in_twelve_calls(raced):
    """Recalculating every lap did not become announcing every lap. The model
    is re-solved at all fifteen crossings; he hears twelve things across the
    race, none of them twice."""
    _, calls, spoken, _ = raced
    said = [c.spoken() for c in calls] + [
        item.verdict.call() for item in spoken]
    assert len(said) <= 13
    assert len(set(said)) == len(said)


def test_a_held_recommendation_is_not_lost(raced):
    """Losing the lap is not the same as losing the finding. The burn crossed
    10% under plan on lap 8 and every lap from there had something more urgent
    on it until lap 11, where it was said - once."""
    _, _, spoken, _ = raced
    notes = [item for item in spoken if not item.verdict.offered]
    assert len(notes) == 1
    assert notes[0].lap == 11
    assert "10% under plan" in notes[0].verdict.call()


def test_lap_time_alone_never_moves_the_stop_count():
    """His measured spread at this car and circuit is 2.04 s, wider than the
    whole degradation band a stint plan is trying to see. A pace deviation of
    four seconds a lap - twice anything a real race produces - changes
    nothing, because pace does not enter the verdict at all."""
    inputs = tonight_inputs()
    steady = assess(
        laps_done=6, laps_total=15, fuel_l=58.88,
        planned_fuel_per_lap=PLANNED_BURN, observed_fuel_per_lap_l=None,
        lap_time_ms=PLANNED_LAP_MS, planned_lap_time_ms=PLANNED_LAP_MS,
        current_stops=2, inputs=inputs, fuel_capacity_l=100.0)
    slow = assess(
        laps_done=6, laps_total=15, fuel_l=58.88,
        planned_fuel_per_lap=PLANNED_BURN, observed_fuel_per_lap_l=None,
        lap_time_ms=PLANNED_LAP_MS + 4_000,
        planned_lap_time_ms=PLANNED_LAP_MS,
        current_stops=2, inputs=inputs, fuel_capacity_l=100.0)
    assert steady.stops == slow.stops
    assert steady.reason == slow.reason
    assert "slower" not in slow.reason and "lapping" not in slow.reason


def test_fuel_that_will_not_reach_is_urgent_from_the_first_laps():
    """**The gate and its own exemption used to be the same predicate.** The
    urgent branch needed a converged race burn, which needs five GREEN laps,
    which is exactly what `race_evidence` waits for - so a genuinely short
    tank on laps 2, 3 and 4 produced a verdict that was computed and then
    silenced. On the replayed race, where laps 4 and 5 were incidents and did
    not count as green, that muted the strategy layer for seven of fifteen
    laps; in a ten-lap sprint with two incidents it would be eight of ten.

    Reaching the flag is arithmetic on the fuel aboard. It does not need the
    burn to have converged - only to exist - and the confidence says which
    figure it used."""
    inputs = tonight_inputs()
    register = PlanRegister()
    verdict = assess(
        laps_done=2, laps_total=15, fuel_l=30.0,
        planned_fuel_per_lap=PLANNED_BURN,
        observed_fuel_per_lap_l=None,          # no converged burn on lap 2
        lap_time_ms=None, planned_lap_time_ms=PLANNED_LAP_MS,
        current_stops=0, inputs=inputs, fuel_capacity_l=100.0)
    assert verdict.verdict == URGENT
    assert "short of the flag on the planned burn" in verdict.reason
    assert verdict.confidence == "medium"      # a projection, not a reading
    # And it is not silenced by the evidence gate it used to share.
    assert register.consider(verdict, lap=2, race_evidence=False).spoken


def test_a_converged_burn_makes_the_same_call_a_reading():
    inputs = tonight_inputs()
    verdict = assess(
        laps_done=8, laps_total=15, fuel_l=30.0,
        planned_fuel_per_lap=PLANNED_BURN, observed_fuel_per_lap_l=6.77,
        lap_time_ms=None, planned_lap_time_ms=PLANNED_LAP_MS,
        current_stops=0, inputs=inputs, fuel_capacity_l=100.0)
    assert verdict.verdict == URGENT
    assert "on current burn" in verdict.reason
    assert verdict.confidence == "high"


def test_the_spoken_reason_is_one_clause():
    """§5.5: instruction first, reason second and SHORT. The full reason
    carries every fact for the record; the unabridged form was 145 characters
    of three semicolon-joined clauses beginning in lower case."""
    verdict = Replan(
        RECOMMENDED,
        "burning 10% less fuel than planned; 68 seconds in it; you'd be "
        "0.3 laps short at this burn - short-shift and lift",
        stops=0)
    spoken = f"{verdict.call()} {verdict.spoken_reason()}"
    assert spoken == ("Recommend running to the flag. "
                      "Burning 10% less fuel than planned.")
    assert len(spoken) < 80


def test_a_verdict_with_no_stop_count_is_not_read_out_as_none():
    assert Replan(RECOMMENDED, "something changed", stops=None).call() == (
        "The plan needs a look.")


def test_box_now_is_said_at_most_twice_before_the_fold(raced):
    _, calls, _, _ = raced
    box_laps = [c.lap for c in calls if c.kind == BOX_NOW]
    assert box_laps == [7, 8]


def test_the_repeated_box_call_is_never_verbatim(raced):
    _, calls, _, _ = raced
    box = [c.spoken() for c in calls if c.kind == BOX_NOW]
    assert len(set(box)) == len(box)
    assert "overdue" in box[1]


def test_the_engineer_folds_to_the_stay_out_with_the_short_shift_lever(raced):
    race, calls, _, _ = raced
    fold = next(c for c in calls if c.kind == STAY_OUT)
    assert fold.lap == 9
    assert "Staying out" in fold.call
    assert "Short-shift" in fold.reason
    # No measured slope for the Shelby: the lever carries no rpm number and
    # the confidence drops instead of a figure being invented.
    assert fold.confidence == MEDIUM
    assert "0.4" in fold.reason
    # The fold adopted the zero-stop shape: no stop left, target is the flag.
    assert race.stops_planned() == 0
    assert race.state.stint_ends_on_lap is None


def test_nothing_after_the_fold_asks_him_to_box(raced):
    _, calls, spoken, _ = raced
    assert not any(c.kind in (BOX_NOW, BOX_SOON) and c.lap > 9 for c in calls)
    # And the re-planner composes with the fold rather than fighting it: from
    # lap 9 the model does keep finding stop shapes it likes, and the driver's
    # own vote outranks every one of them. What he hears after the fold is a
    # note about the burn, which asks nothing of him.
    assert not any(item.verdict.offered and item.lap > 9 for item in spoken)


def test_fuel_to_27_litres_is_never_said(raced):
    """The physically vacuous fill of the real night - "Fuel to 27 litres"
    with 51.9 aboard - must not survive in any call."""
    _, calls, spoken, _ = raced
    everything = ([c.spoken() for c in calls]
                  + [item.verdict.reason for item in spoken])
    assert not any("Fuel to 27" in text for text in everything)
    assert not any("27 litres" in text for text in everything)


# ------------------------------------------------------------- the app clock

def test_the_app_clock_finishes_the_race_and_gt7s_does_not(raced):
    """A timed race never emitted RACE_FINISHED at all before the clock did
    it, and the version that did rested on GT7's own `remaining_time_ms` -
    which the driver measured as inaccurate. This replay sends -1 on every
    lap, so if anything still read it the race could not end at all."""
    race, calls, _, _ = raced
    assert calls[-1].kind == CHEQUER
    assert calls[-1].lap == 15
    assert race.state.finished is True


def test_the_chequered_flag_is_called_with_position_and_a_closing_fact(raced):
    _, calls, _, _ = raced
    assert "P5" in calls[-1].reason
    assert "1.8 litres" in calls[-1].reason
    assert "zero-stop" in calls[-1].reason


def test_two_to_go_and_last_lap_are_said_at_the_right_crossings(raced):
    """**What an accurate clock unlocks.** Measured on this race the call is
    safe from two laps out - 13.3 s of margin at the end of lap 13 and 31.2 s
    at the end of lap 14 - and the last-lap call is made at the crossing that
    BEGINS the final lap, not after it."""
    _, calls, _, _ = raced
    to_go = [(c.lap, c.call) for c in calls if c.kind == LAPS_TO_GO]
    assert to_go == [(13, "Two to go."), (14, "Last lap.")]


def test_the_distance_estimate_lands_on_fifteen_laps(raced):
    """Predicted from the ACHIEVED median - every lap as run, incidents
    included - and not from the clean pace. Measured: the achieved median of
    121.51 s predicts fifteen, which is what happened; the clean-pace median
    of 119.62 s and the practice median both predict sixteen."""
    race, _, _, _ = raced
    assert race.state.laps_total == 15


def test_the_two_measures_of_elapsed_time_agree_all_race(raced):
    """The app timer and the sum of GT7's own exact lap times, reconciled
    against the standing start measured at the first crossing."""
    _, _, _, clock = raced
    assert clock.corroborated is True
    assert clock.elapsed_laps_s == pytest.approx(1841.28, abs=0.05)
    assert clock.elapsed_app_s == pytest.approx(1841.28 + STANDING_START_S,
                                                abs=0.05)


def test_no_box_or_fuel_call_fires_on_the_final_crossing(raced):
    """The ninth box call of the real night was voiced on the chequered-flag
    crossing - LAP_COMPLETED for the last lap arrives before RACE_FINISHED."""
    _, calls, _, _ = raced
    on_lap_15 = [c for c in calls if c.lap == 15]
    assert all(c.kind == CHEQUER for c in on_lap_15)


# ------------------------------------------------------ the plan's own numbers

def test_the_plan_carries_what_it_expected_and_what_it_ran(raced):
    race, _, _, _ = raced
    snapshot = race.snapshot()
    assert snapshot["plannedFuelPerLapL"] == PLANNED_BURN
    assert snapshot["plannedLapMs"] == PLANNED_LAP_MS
    # The race replaced the practice burn outright once five green laps
    # existed. Measured: practice was 10.7% high, and that error alone turned
    # a zero-stop race into a two-stop plan.
    assert snapshot["expectedFuelSource"] == RACE
    assert snapshot["actualFuelPerLapL"] == pytest.approx(6.76, abs=0.06)
    assert snapshot["burnVsPlanPct"] == pytest.approx(-10.6, abs=1.0)


def test_the_pace_comparison_never_claims_more_than_it_can_see(raced):
    """Lap time confirms and never triggers, and it is reported with the
    noise floor it has to clear. At this car's measured spread a fifteen-lap
    race cannot honestly show a one-second-a-lap drift."""
    race, _, _, _ = raced
    snapshot = race.snapshot()
    assert snapshot["lapTimeSigmaMs"] > 900          # measured here, not 918
    assert snapshot["paceDetectableMs"] is not None
    assert snapshot["paceIsReal"] is False
    line = race.expect.audit_line()
    assert "not a finding" in line
    assert "assumption" in line                      # wear, always


def test_the_tyre_temperature_conserve_call_fires_once(raced):
    """Once per stint, on the front-to-rear gap - his own measured
    association - with the hysteresis holding it down for the rest of the race
    even though the gap never comes back under the quiet threshold.

    It lands on lap 10 rather than earlier because **one call per lap is a
    hard rule and a box call outranks a temperature**: the gap first clears
    the threshold on lap 5, which is a "Box in 2", and every lap from there to
    the fold belongs to the stop conversation. Lap 10 is the first one free.
    """
    _, calls, _, _ = raced
    conserve = [c for c in calls if c.kind == TYRE_TEMP and c.tag == "conserve"]
    assert len(conserve) == 1
    assert conserve[0].lap == 10
    # The scope resolved for this car at this circuit, off the real event row.
    assert raced[0].state.temp_gap_conserve_c == 8.0
    assert "Ease the" in conserve[0].call
    assert "over the fronts" in conserve[0].reason


def test_no_call_ever_claims_an_optimal_tyre_window(raced):
    """Nobody has published one for GT7, so the app may not imply one. The
    push call the brief asked for is deliberately absent for this reason."""
    _, calls, _, _ = raced
    said = " ".join(c.spoken() for c in calls).lower()
    assert "optimal" not in said
    assert "in window" not in said
    assert "you can push" not in said or "fuel" in said


def test_the_cold_tyre_call_still_opens_the_race(raced):
    _, calls, _, _ = raced
    temps = [c for c in calls if c.kind == TYRE_TEMP]
    assert temps[0].lap == 1
    assert "Tyres cold" in temps[0].call
    assert "2 laps to come up" in temps[0].reason


def test_the_normal_rear_hot_offset_never_raises_a_trend_call(raced):
    """Rears 8-11 degC hotter than fronts all race is this car's normal
    thermal balance, not a finding."""
    _, calls, _, _ = raced
    assert not any("heating" in c.call for c in calls)


def test_the_push_call_of_the_night_still_exists(raced):
    """Lap 4's "You can push" - a FUEL call, about fuel in hand, and nothing
    to do with tyre temperature - is not this pass's target."""
    _, calls, _, _ = raced
    assert any(c.kind == FUEL_LONG and c.lap == 4 for c in calls)


def test_no_lap_is_wasted_on_a_repeated_box_call(raced):
    """The real night said the same box call nine times, and every lap it
    spent doing that was a lap something else could have used. Laps 9 and 10
    are the proof: the fold, and then the temperature call the box repeats
    used to bury."""
    _, calls, _, _ = raced
    assert {c.kind for c in calls if c.lap in (9, 10)} == {STAY_OUT, TYRE_TEMP}


def test_the_status_call_still_reports_when_it_has_the_lap_free():
    """It is crowded out of tonight's race by louder things, which is one
    call per lap working. On a quiet lap it still comes round."""
    state = RaceState(lap=10, laps_total=15, race_minutes=30.0, position=4,
                      laps_estimate_firm=True)
    # The heartbeat measures silence: nothing has been said for ten laps.
    state.last_said_lap = 0
    # **The clock has to be on the state now.** He turned GT7's race HUD off
    # on 28 Aug 2026, so minutes are a figure only this call carries - and a
    # state without one says so out loud rather than dropping the clause,
    # because silence there is indistinguishable from a race with no end.
    state.race_remaining_s = 9 * 60.0
    call = next_call(state)
    assert call.kind == STATUS
    assert "P4" in call.call
    # **`Lap 11`, not `Lap 10`.** `state.lap` is the count behind him and
    # GT7's HUD names the lap he is driving; the engineer spoke the count
    # for a whole race at Daytona on 4 Sep 2026 and he reported it. The
    # laps-to-go clause is untouched. See `RaceState.lap_on_screen`.
    assert "Lap 11" in call.call
    assert "9 minutes left" in call.call
    assert "5 laps to go" in call.call


# ------------------------------------------------------------ the register

def an_offer(**overrides) -> Replan:
    fields = dict(verdict=RECOMMENDED, reason="burning 10% less",
                  stops=1, stint_laps=(8,), gain_s=12.0,
                  next_stop_lap=12, laps_to_next_stop=8)
    fields.update(overrides)
    return Replan(**fields)


def test_the_first_assessment_is_spoken():
    register = PlanRegister()
    outcome = register.consider(an_offer(), lap=4)
    assert outcome.spoken is True
    assert outcome.why == "first assessment of the race"


def test_the_same_answer_again_is_silence():
    """**There is no expiry and there is no repeat.** The old desk lapsed an
    unanswered offer after two laps and could then re-voice it; the driver's
    instruction was that an offer should not expire, because the engineer is
    reassessing anyway. What he must never hear is the same answer twice."""
    register = PlanRegister()
    register.consider(an_offer(), lap=4)
    for lap in range(5, 15):
        assert register.consider(an_offer(), lap=lap).spoken is False


def test_a_changed_stop_count_is_material():
    register = PlanRegister()
    register.consider(an_offer(stops=1), lap=4)
    outcome = register.consider(an_offer(stops=0, next_stop_lap=None), lap=5)
    assert outcome.spoken is True
    assert outcome.why == "the stop count has changed"


def test_a_stop_that_slides_a_lap_or_two_is_not_worth_a_word():
    # The absolute lap moves with the relative one here: lap 12, then 15,
    # then 17. (It used to stay on 12 while "moving", which is the Suzuka
    # defect - see `test_suzuka_race_166`.)
    register = PlanRegister()
    register.consider(an_offer(laps_to_next_stop=8, next_stop_lap=12), lap=4)
    assert register.consider(
        an_offer(laps_to_next_stop=10, next_stop_lap=15), lap=5).spoken is False
    outcome = register.consider(
        an_offer(laps_to_next_stop=11, next_stop_lap=17), lap=6)
    assert outcome.spoken is True
    assert outcome.why == "the stop has moved 5 laps later"


def test_a_stop_that_stays_put_is_never_announced_by_the_calendar():
    """**The comparison is laps from now, not the lap number.** Re-planning
    the remainder restarts the first stint at the current lap every time, so a
    tyre-limited stint of a fixed length marches the ABSOLUTE stop lap forward
    one lap per lap while the answer has not moved at all. Compared
    absolutely it tripped the threshold every third lap: nine announcements in
    28 laps on a probe, the same instruction three times running."""
    register = PlanRegister()
    register.consider(an_offer(laps_to_next_stop=17, next_stop_lap=18), lap=1)
    for lap in range(2, 29):
        # The stint is tyre-limited at 17 laps, so the stop is always 17 laps
        # away and the absolute lap climbs with the race.
        outcome = register.consider(
            an_offer(laps_to_next_stop=17, next_stop_lap=lap + 17), lap=lap)
        assert outcome.spoken is False, lap


def test_an_oscillating_verdict_does_not_swap_the_answer_every_lap():
    """A race sitting on a stop-count boundary flips the model's answer lap to
    lap, and the measured race sat inside 1.80% of exactly that boundary. The
    first swap is information; swapping straight back is the model dithering
    out loud.

    `OfferDesk` had this guard and the class that replaced it did not, so a
    probe of six consecutive laps produced six contradictory instructions -
    "Recommend 1 stop" / "running to the flag" / "1 stop" / "running to the
    flag". Restored here against the new class."""
    register = PlanRegister()
    assert register.consider(an_offer(stops=1), lap=4).spoken is True
    assert register.consider(
        an_offer(stops=0, laps_to_next_stop=None), lap=5).spoken is True
    for lap in range(6, 12):
        stops = 1 if lap % 2 == 0 else 0
        outcome = register.consider(
            an_offer(stops=stops,
                     laps_to_next_stop=8 if stops else None), lap=lap)
        assert outcome.spoken is False, (lap, stops)


def test_an_urgent_escalation_cuts_through_the_swap_back_guard():
    """Not a preference between plans - arithmetic about reaching the end."""
    register = PlanRegister()
    register.consider(an_offer(stops=1), lap=4)
    register.consider(an_offer(stops=0, laps_to_next_stop=None), lap=5)
    urgent = an_offer(stops=1, verdict=URGENT, confidence="high")
    assert register.consider(urgent, lap=6).spoken is True


def test_running_out_of_fuel_escalates_through_everything():
    register = PlanRegister()
    register.consider(an_offer(), lap=4)
    outcome = register.consider(
        an_offer(verdict=URGENT, confidence="high"), lap=5)
    assert outcome.spoken is True
    assert outcome.why == "the fuel no longer reaches the flag"


def test_the_fuel_picture_clearing_is_worth_a_word_too():
    """He is saving fuel he may no longer need to save."""
    register = PlanRegister()
    register.consider(an_offer(verdict=URGENT, confidence="high"), lap=4)
    outcome = register.consider(Replan(NONE, "on the plan"), lap=6)
    assert outcome.spoken is True
    assert outcome.why == "the fuel picture has cleared"


def test_a_plan_that_says_nothing_new_is_not_a_revision():
    """A row a lap would bury the ones that matter."""
    register = PlanRegister()
    outcome = register.consider(Replan(NONE, "on the plan"), lap=4)
    assert outcome.spoken is False


def test_the_drivers_own_shape_outranks_the_model():
    """He voted with the car by running past his stop. From there the
    engineer confirms or revises THAT race - it does not keep re-proposing
    the stop he spent two laps declining."""
    register = PlanRegister()
    register.note_driver_shape(0, lap=9)
    assert register.consider(an_offer(stops=1), lap=10).spoken is False
    assert register.consider(an_offer(stops=2), lap=11).spoken is False
    # Arithmetic still cuts through a preference.
    urgent = an_offer(stops=1, verdict=URGENT, confidence="high")
    assert register.consider(urgent, lap=12).spoken is True


def test_nothing_is_offered_until_the_race_has_evidence():
    register = PlanRegister()
    assert register.consider(an_offer(), lap=2,
                             race_evidence=False).spoken is False
    urgent = an_offer(verdict=URGENT, confidence="high")
    assert register.consider(urgent, lap=3,
                             race_evidence=False).spoken is True


def test_accepting_records_the_shape_and_keeping_records_the_refusal():
    register = PlanRegister()
    register.consider(an_offer(stops=0), lap=4)
    resolution = register.answered(accepted=True, lap=5)
    assert resolution.reason == RESOLVED_ACCEPTED
    assert register.driver_shape_stops == 0

    register = PlanRegister()
    register.consider(an_offer(stops=0), lap=4)
    resolution = register.answered(accepted=False, lap=5)
    assert resolution.reason == RESOLVED_KEPT


def test_an_answer_with_nothing_told_is_none():
    assert PlanRegister().answered(accepted=True, lap=5) is None


def test_materially_different_needs_something_to_compare_against():
    say, why = materially_different(an_offer(), None)
    assert say is True and why


# --------------------------------------------------- the burn against the plan

def test_the_burn_band_needs_five_percent_to_enter_and_three_to_leave():
    """Hysteresis, so a burn sitting on the threshold cannot announce itself
    every other lap."""
    assert burn_band(-0.04, BAND_ON) == BAND_ON
    assert burn_band(-0.06, BAND_ON) == BAND_UNDER
    assert burn_band(-0.04, BAND_UNDER) == BAND_UNDER      # still out
    assert burn_band(-0.02, BAND_UNDER) == BAND_ON
    assert burn_band(None, BAND_UNDER) == BAND_UNDER       # unknown changes nothing


def test_a_band_crossing_is_said_once_and_is_not_a_question():
    register = PlanRegister()
    quiet = Replan(NONE, "on the plan")
    assert register.consider(quiet, lap=4, burn_drift=-0.01).spoken is False
    outcome = register.consider(quiet, lap=5, burn_drift=-0.10)
    assert outcome.spoken is True
    assert "10% under plan" in outcome.verdict.call()
    # Not a question: nothing to accept or keep.
    assert outcome.verdict.offered is False
    assert register.consider(quiet, lap=6, burn_drift=-0.11).spoken is False


# ------------------------------------------------------------- the race clock

def a_clock(duration_s: float = 600.0):
    now = FakeMonotonic()
    clock = RaceClock(duration_s, now=now)
    clock.start()
    return clock, now


def test_the_clock_measures_from_the_green():
    clock, now = a_clock()
    now.advance(120.0)
    assert clock.elapsed_s == pytest.approx(120.0)
    assert clock.remaining_s == pytest.approx(480.0)
    assert clock.expired is False


def test_a_pause_does_not_run_the_clock():
    """GT7 pauses mid-race in a single-player lobby, and `SessionState.update`
    returns early on one - so nothing but the frame watcher can see it. A
    clock that ran through a pause would call the last lap early."""
    clock, now = a_clock()
    now.advance(60.0)
    clock.note_frame(now(), paused=True)
    now.advance(300.0)
    # Mid-pause the clock is already holding, not catching up afterwards.
    assert clock.elapsed_s == pytest.approx(60.0)
    clock.note_frame(now(), paused=False)
    now.advance(30.0)
    assert clock.elapsed_s == pytest.approx(90.0)


def test_the_flag_falls_on_the_first_crossing_after_the_clock():
    clock, now = a_clock(duration_s=240.0)
    assert clock.laps_left(120_000) == 2
    now.advance(130.0)
    assert clock.laps_left(120_000) == 1        # 110 s left: one more lap
    now.advance(120.0)
    assert clock.expired is True
    assert clock.laps_left(120_000) == 0


def test_no_lap_time_means_no_estimate_rather_than_a_guess():
    clock, _ = a_clock()
    assert clock.laps_left(None) is None
    assert clock.laps_left(0) is None
    assert RaceClock(None).laps_left(120_000) is None


def test_the_margin_says_when_the_estimate_cannot_be_resolved():
    """Measured on the real race: at the first four crossings the median only
    had to be wrong by 0.12-0.66 s to change the answer, against a lap-to-lap
    spread of 2.04 s."""
    clock, now = a_clock(duration_s=1800.0)
    now.advance(121.5)
    tight = clock.laps_left_margin_s(119_624)
    assert tight is not None and tight < 1.0
    now.advance(1590.0)                          # end of lap 14, 88 s left
    assert clock.laps_left_margin_s(121_511) > 10.0


def test_the_lap_times_corroborate_the_app_timer():
    clock, now = a_clock(duration_s=1800.0)
    now.advance(44.283)                          # the standing start
    for lap_ms in (121_511, 117_724, 117_318):
        now.advance(lap_ms / 1000.0)
        clock.note_lap(lap_ms)
    assert clock.corroborated is True
    assert clock.elapsed_s == pytest.approx(clock.elapsed_app_s)


def test_a_pause_the_frame_watcher_missed_hands_the_clock_to_the_laps():
    """The app timer running through something the laps did not. The lap-time
    sum wins, because it is built from GT7's own exact figures."""
    clock, now = a_clock(duration_s=1800.0)
    now.advance(44.283)
    now.advance(120.0)
    clock.note_lap(120_000)
    now.advance(120.0 + 90.0)                    # 90 s nobody accounted for
    clock.note_lap(120_000)
    assert clock.corroborated is False
    # 44.3 s of standing start plus 240 s of laps, and not the 330 the app
    # timer thinks it saw.
    assert clock.elapsed_s == pytest.approx(44.283 + 240.0, abs=0.1)


def test_the_discrepancy_is_logged_once_and_not_per_lap(caplog):
    clock, now = a_clock(duration_s=1800.0)
    now.advance(44.283)
    now.advance(120.0)
    clock.note_lap(120_000)
    with caplog.at_level("WARNING"):
        for _ in range(4):
            now.advance(120.0 + 90.0)
            clock.note_lap(120_000)
    said = [r for r in caplog.records if "clock disagreement" in r.message]
    assert len(said) == 1


def stream(clock, now, seconds: float) -> None:
    """Advance the clock with telemetry arriving under it, as a race does.

    The frame count is what separates a dropped lap from a pause nobody saw -
    both look identical in the wall clock alone - so a test that asserts one
    or the other has to say which it is driving.
    """
    frames = int(seconds * STREAM_HZ)
    for _ in range(frames):
        now.advance(seconds / frames)
        clock.note_frame(now(), paused=False)


def test_a_dropped_lap_event_is_caught():
    """A lap-time sum that jumps by one lap while the wall clock jumps by two,
    **with telemetry arriving throughout**, is a LAP_COMPLETED that never
    arrived - and every distance estimate downstream counts laps."""
    clock, now = a_clock(duration_s=1800.0)
    now.advance(44.283)
    stream(clock, now, 120.0)
    clock.note_lap(120_000)
    stream(clock, now, 120.0)
    assert clock.note_lap(120_000).dropped_lap is False
    stream(clock, now, 240.0)                    # two laps, one event
    assert clock.note_lap(120_000).dropped_lap is True


def test_a_dropped_lap_keeps_the_app_timer_as_the_reference():
    """**The lap-time sum is the one measure that is definitely wrong** - it
    is short by exactly the lap nobody recorded. Preferring it is what told
    the Monza engineer of 18 Aug 2026 it had 136 s more race than it did.
    """
    clock, now = a_clock(duration_s=1800.0)
    now.advance(44.283)
    stream(clock, now, 120.0)
    clock.note_lap(120_000)
    stream(clock, now, 240.0)                    # two laps, one event
    result = clock.note_lap(120_000)
    assert result.dropped_lap is True
    assert clock.laps_dropped == 1
    # The missing lap is folded into the offset, so the two measures agree
    # again and the app timer - which was right all along - still governs.
    assert clock.corroborated is True
    assert clock.elapsed_s == pytest.approx(clock.elapsed_app_s)
    assert clock.elapsed_s == pytest.approx(44.283 + 360.0, abs=0.1)


def test_the_monza_pit_lap_is_a_dropped_lap_and_not_a_clock_disagreement():
    """Session 52, 18 Aug 2026, the only stop of the race.

    319.0 s of wall clock between the lap-15 and lap-16 crossings against
    GT7's 183.094 s for lap 16, with 19117 frames under it - the car streaming
    continuously the whole time. The tank was filled to 73.82 L and read
    68.31 L at the next crossing, 5.50 L gone against a 5.553 L lap: the
    out-lap was never counted. The app used to call this a clock disagreement
    and hand the reference to the lap-time sum.
    """
    clock, now = a_clock(duration_s=3000.0)
    now.advance(31.317)                          # standing_start_ms, lap 1
    for lap_ms in (118_779, 109_437, 110_450, 109_661, 109_303):
        stream(clock, now, lap_ms / 1000.0)
        assert clock.note_lap(lap_ms).dropped_lap is False
    assert clock.corroborated is True

    stream(clock, now, 319.0)                    # the stop, and the out-lap
    result = clock.note_lap(183_094, is_pit_lap=True)
    assert result.dropped_lap is True
    assert clock.corroborated is True
    # 135.9 s of racing the lap-time sum will never contain.
    assert clock.elapsed_s == pytest.approx(clock.elapsed_app_s)


def test_a_pause_is_not_reported_as_a_dropped_lap():
    """The counterpart, and the reason the frame count exists: the same span
    with no telemetry under it is time the car did not race, and there the
    lap-time sum really is the better measure."""
    clock, now = a_clock(duration_s=1800.0)
    now.advance(44.283)
    stream(clock, now, 120.0)
    clock.note_lap(120_000)
    stream(clock, now, 120.0)
    now.advance(90.0)                            # 90 s nobody accounted for
    result = clock.note_lap(120_000)
    assert result.dropped_lap is False
    assert clock.laps_dropped == 0
    assert clock.corroborated is False


def test_a_lap_race_is_not_reconciled():
    """The reconciliation protects one thing - how much racing time is left -
    and a race run to a lap count has none."""
    clock = RaceClock(None, now=FakeMonotonic())
    clock.start()
    clock.note_lap(120_000)
    clock.note_lap(120_000)
    assert clock.corroborated is None


# ---------------------------------------------------- the plan's expectations

def a_race_lap(lap_num: int, time_ms: int, used: float, **overrides) -> Lap:
    fields = dict(lap_num=lap_num, lap_time_ms=time_ms, best_lap_ms=time_ms,
                  delta_ms=0, fuel_start=90.0, fuel_end=90.0 - used,
                  fuel_used=used, position=3, is_pit_lap=False,
                  is_out_lap=False)
    fields.update(overrides)
    return Lap(**fields)


def a_tracker() -> ExpectationTracker:
    return ExpectationTracker(
        planned_lap_time_ms=PLANNED_LAP_MS,
        planned_fuel_per_lap_l=PLANNED_BURN, planned_wear_per_lap=0.03161,
        practice_lap_samples=8, practice_fuel_samples=8)


def test_the_plan_starts_on_practice_and_says_so():
    tracker = a_tracker()
    expectation = tracker.current()
    assert expectation.fuel_per_lap_l == PLANNED_BURN
    assert expectation.fuel_source == PRACTICE
    assert expectation.fuel_samples == 8
    assert tracker.burn_vs_plan() is None


def test_the_race_burn_replaces_practice_after_five_green_laps():
    """Five and not three: the running median is inside 2% after one lap, but
    the zero-versus-one-stop decision at the measured race turned on 1.80%,
    which three laps cannot resolve at 95%."""
    tracker = a_tracker()
    for lap_num in range(1, 6):                  # lap one never counts
        tracker.note_lap(a_race_lap(lap_num, 119_000, 6.75))
    assert tracker.current().fuel_source != RACE
    tracker.note_lap(a_race_lap(6, 119_000, 6.75))
    expectation = tracker.current()
    assert expectation.fuel_source == RACE
    assert expectation.fuel_per_lap_l == pytest.approx(6.75)
    assert expectation.fuel_samples == 5
    assert tracker.burn_vs_plan() == pytest.approx(-0.107, abs=0.005)


def test_a_lap_he_was_saving_on_is_not_evidence_about_the_burn():
    """Measured: a trailing window admitting his two fuel-saving laps read
    12.17% under the real rate, and would have planned the rest of the race on
    a burn he was only achieving by lifting."""
    tracker = a_tracker()
    for lap_num in range(2, 7):
        tracker.note_lap(a_race_lap(lap_num, 119_000, 6.75))
    for lap_num in (7, 8):
        tracker.note_lap(a_race_lap(lap_num, 124_000, 4.44,
                                    short_shift_rpm=500.0))
    assert tracker.race_fuel_per_lap_l() == pytest.approx(6.75)


def test_an_incident_lap_is_not_evidence_about_the_burn_either():
    tracker = a_tracker()
    for lap_num in range(2, 7):
        tracker.note_lap(a_race_lap(lap_num, 119_000, 6.75))
    tracker.note_lap(a_race_lap(7, 140_000, 2.10))     # a crawl, 18% over
    assert tracker.race_fuel_per_lap_l() == pytest.approx(6.75)


def test_the_achieved_median_includes_everything_the_clock_saw():
    """An incident lap does not make the car slower, but it does consume the
    clock - and the clock is what a timed race's distance is predicted from."""
    tracker = a_tracker()
    for lap_num in range(1, 6):
        tracker.note_lap(a_race_lap(lap_num, 119_000, 6.75))
    tracker.note_lap(a_race_lap(6, 140_000, 2.10))
    assert tracker.race_lap_time_ms() == 119_000
    assert tracker.achieved_lap_time_ms() == 119_000
    for lap_num in (7, 8, 9, 10):
        tracker.note_lap(a_race_lap(lap_num, 140_000, 2.10))
    assert tracker.race_lap_time_ms() == 119_000        # the car's pace
    assert tracker.achieved_lap_time_ms() > 119_000     # what the clock saw


def test_the_noise_floor_is_measured_here_and_never_inherited():
    """The 0.918 s on record is a Monza/Porsche figure over a population that
    still contained incident laps. This car at this circuit measures 2.04 s -
    2.7 times Monza - and a builder who inherited the recorded number would
    over-claim detectability by about a factor of two."""
    tracker = a_tracker()
    assert tracker.sigma_ms() is None                # nothing to measure yet
    for lap_num, ms in enumerate(
            (117_724, 117_318, 120_073, 119_170, 119_557), start=2):
        tracker.note_lap(a_race_lap(lap_num, ms, 6.75))
    sigma = tracker.sigma_ms()
    assert sigma is not None and 900 < sigma < 1600


def test_no_sigma_means_no_pace_claim_at_all():
    tracker = a_tracker()
    tracker.note_lap(a_race_lap(2, 125_000, 6.75))
    tracker.note_lap(a_race_lap(3, 125_100, 6.75))
    tracker.note_lap(a_race_lap(4, 125_200, 6.75))
    assert tracker.pace_vs_plan_ms() is not None      # the number exists
    assert tracker.pace_detectable_ms() is None       # but it means nothing
    assert tracker.pace_is_real() is False
    snapshot = tracker.as_snapshot()
    assert snapshot["paceVsPlanMs"] is None
    assert snapshot["paceVsPlanNote"] == "not yet measurable"


def test_the_detection_floor_matches_the_measured_pairs():
    """Two useful pairs at this car's spread: 2.0 s/lap over 4 laps, and
    1.0 s/lap over 16."""
    assert detectable_delta_ms(4, 2037.0) == pytest.approx(2000, abs=30)
    assert detectable_delta_ms(16, 2037.0) == pytest.approx(1000, abs=20)
    assert detectable_delta_ms(1, 2037.0) is None
    assert detectable_delta_ms(10, None) is None


def test_wear_never_stops_being_the_plans_assumption():
    """Confirmed on the measured race: zero gauge readings across all fifteen
    laps. And the evidence contradicts itself - the three readings on file
    have the FRONTS wearing faster while the temperature gap points at the
    rear. The contradiction is surfaced, never averaged."""
    tracker = a_tracker()
    for lap_num in range(2, 12):
        tracker.note_lap(a_race_lap(lap_num, 119_000, 6.75))
    expectation = tracker.current()
    assert expectation.wear_per_lap == 0.03161
    assert "assumption" in expectation.wear_source
    line = tracker.audit_line()
    assert "no gauge reading was entered during the race" in line
    assert "FRONTS wearing faster" in line


# ------------------------------------------------------- representative pace

def pace_race() -> RaceCoordinator:
    race = RaceCoordinator(None, fuel_per_lap_l=3.4)
    race.arm(None, PlanContext(car="c", track="t", layout=None, race_laps=20))
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    return race


def a_lap(lap_num: int, time_ms: int, **overrides) -> SessionEvent:
    fields = dict(lap_num=lap_num, lap_time_ms=time_ms, best_lap_ms=time_ms,
                  delta_ms=0, fuel_start=40.0, fuel_end=36.6, fuel_used=3.4,
                  position=3, is_pit_lap=False, is_out_lap=False)
    fields.update(overrides)
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": Lap(**fields)})


def test_lap_one_never_enters_the_pace_record():
    race = pace_race()
    race.handle(a_lap(1, 121_511))
    race.handle(a_lap(2, 117_724))
    race.handle(a_lap(3, 117_318))
    assert race.representative_pace_ms() is None     # only two count
    race.handle(a_lap(4, 117_500))
    assert race.representative_pace_ms() == 117_500  # median of 2,3,4


def test_one_incident_lap_does_not_move_the_pace():
    """His lap-to-lap noise sits right at the 2% threshold on a two-minute
    lap - one slow lap must not read as a pace change. A +6.8% lap is an
    incident, dropped before the median; with only two clean laps left the
    honest answer is that the pace is unknown, and it returns once a third
    clean lap lands."""
    race = pace_race()
    for lap_num, ms in ((1, 121_511), (2, 118_000), (3, 118_100),
                        (4, 126_000)):
        race.handle(a_lap(lap_num, ms))
    assert race.representative_pace_ms() is None
    race.handle(a_lap(5, 118_300))
    assert race.representative_pace_ms() == 118_100


def test_adjacent_incident_laps_cannot_carry_the_median():
    """Tonight's real laps 4-5 (+6.1% and +9.3%: a crawl, then the spin
    recovery) once made the three-lap median 126,254 - a +6% pace verdict
    that went unvoiced only because an earlier offer was gagging the loop.
    Incident laps are 5-10% outliers, not noise; they are dropped against
    the race's own best before any median is taken."""
    race = pace_race()
    for lap_num, ms in ((1, 121_511), (2, 117_724), (3, 117_318),
                        (4, 126_254), (5, 129_989)):
        race.handle(a_lap(lap_num, ms))
    assert race.representative_pace_ms() is None    # two clean laps only
    race.handle(a_lap(6, 120_073))
    assert race.representative_pace_ms() == 117_724


def test_pit_and_out_laps_stay_out_of_the_pace():
    race = pace_race()
    race.handle(a_lap(1, 118_000))
    race.handle(a_lap(2, 118_000))
    race.handle(a_lap(3, 140_000, is_pit_lap=True))
    race.handle(a_lap(4, 139_000, is_out_lap=True))
    race.handle(a_lap(5, 118_200))
    race.handle(a_lap(6, 118_400))
    assert race.representative_pace_ms() == 118_200


def test_no_pace_means_no_pace_verdict():
    verdict = assess(laps_done=1, laps_total=20, fuel_l=90.0,
                     planned_fuel_per_lap=7.563, observed_fuel_per_lap_l=None,
                     lap_time_ms=None, planned_lap_time_ms=118_940,
                     current_stops=2, inputs=None)
    assert verdict.offered is False


# ---------------------------------------------------------------- stay out

def a_state(**overrides) -> RaceState:
    fields = dict(lap=9, laps_total=15, fuel_l=38.1, fuel_per_lap_l=6.77,
                  position=5, stint_ends_on_lap=7, laps_since_stop=9,
                  fuel_capacity_l=100.0)
    fields.update(overrides)
    return RaceState(**fields)


def test_the_stay_out_needs_the_fuel_to_nearly_reach():
    """Without a measured short-shift slope the claim stops at half a lap."""
    assert stay_out_call(a_state(fuel_l=38.1)) is not None   # 0.37 short
    assert stay_out_call(a_state(fuel_l=36.0)) is None       # 0.68 short


def test_a_measured_slope_extends_the_stay_out_reach():
    state = a_state(fuel_l=34.0, short_shift_l_per_1000rpm=1.762)
    call = stay_out_call(state)                              # 0.98 short
    assert call is not None
    # "Should", not "can": the claim rests on him executing the saving
    # every remaining lap, and MEDIUM is never voiced - the hedge has to
    # live in the words.
    assert call.call == "Staying out? You should make it."
    assert call.reason.startswith("Short-shift ")
    drop = int(call.reason.split()[1].rstrip(","))
    assert drop % 50 == 0
    assert call.confidence == HIGH


def test_a_lever_that_cannot_close_the_gap_refuses_the_fold():
    """`stay_out_call` used to read only the rpm drop off `short_shift_for`
    and throw away the laps the CAPPED drop still cannot cover - so with a
    measured slope and a 3-lap hole it said "you can make it" and retired a
    stop the driver needed. The fold's gate is the lever's own arithmetic:
    a residue past the epsilon means the box call stands."""
    state = a_state(fuel_l=20.0, short_shift_l_per_1000rpm=1.762)
    assert stay_out_call(state) is None                      # 3.0 laps short


def test_fuel_already_good_says_so_without_a_lever():
    call = stay_out_call(a_state(fuel_l=45.0))
    # The one unhedged form: no saving is being asked of him.
    assert call.call == "Staying out? You can make it."
    assert "good to the flag" in call.reason
    assert "Short-shift" not in call.reason


def test_a_box_call_that_cannot_make_the_flag_escalates_instead():
    """Fold refused, so the repeat carries the new fact - never verbatim,
    and never the old "You will not make the flag": the measured driver
    closed 0.7 laps with lift-and-coast alone, so the escalation states the
    gap in its frame and names his lever, hedged."""
    state = a_state(fuel_l=20.0)                             # 3 laps short
    state.record(next_call(state))                           # overdue 2
    state.lap = 10                                           # overdue 3
    call = next_call(state)
    assert call.kind == BOX_NOW
    assert "3 laps overdue" in call.reason
    assert "short of the flag on current burn" in call.reason
    assert "short-shift and lift" in call.reason
    assert call.confidence == MEDIUM
    assert "will not make" not in call.reason


# ---------------------------------------------------------- the stale fill

def test_a_stale_plan_does_not_size_a_fill_below_the_race():
    """Next stint 3 laps, no stop after it, 8 laps left of which lap 8 is
    the in-lap: the fill must reach the flag - 7 laps after the box - not
    the plan's stale stint length."""
    state = RaceState(lap=7, laps_total=15, fuel_l=5.0, fuel_per_lap_l=6.79,
                      stint_ends_on_lap=7, next_stint_laps=3,
                      further_stop_planned=False, fuel_capacity_l=100.0)
    said = _fuel_instruction(state)
    assert said == "Fuel to 55 litres - 7 laps after the box."  # (7+1) x 6.79, rounded up; sized by the flag, and it says so


def test_a_hand_built_state_keeps_the_stints_own_figure():
    """`further_stop_planned` is None where nobody said - missing is not
    False, and the old behaviour stands."""
    state = RaceState(lap=7, laps_total=15, fuel_l=5.0, fuel_per_lap_l=6.79,
                      stint_ends_on_lap=7, next_stint_laps=3,
                      fuel_capacity_l=100.0)
    assert said_litres(_fuel_instruction(state)) == 28   # (3+1) x 6.79, up


def said_litres(said: str) -> int:
    return int(said.split("Fuel to ")[1].split(" litres")[0])


# ------------------------------------------------------------- the chequer

def test_the_chequer_outranks_a_stale_box_call():
    state = a_state(lap=15, finished=True, position=5, fuel_l=1.79)
    call = next_call(state)
    assert call.kind == CHEQUER
    assert "P5" in call.reason


def test_the_final_crossing_gap_is_silence_not_a_box_call():
    """LAP_COMPLETED for the last lap lands before RACE_FINISHED. In that
    gap the distance is covered and nothing about a stop is actionable."""
    state = a_state(lap=15, finished=False)
    assert next_call(state) is None


def test_the_fold_never_fires_on_the_chequered_crossing():
    """A plan whose last stop sits two laps before the end puts the fold's
    overdue trigger exactly on the final lap - and the fold used to run there,
    voicing "Staying out? You can make it." 200 ms before the chequer and
    recording an accepted stay-out about a race already over."""
    plan = {"stints": [
        {"laps": 13, "compound": "RS", "start_lap": 1},
        {"laps": 2, "compound": "RS", "start_lap": 14},
    ]}
    now = FakeMonotonic()
    race = RaceCoordinator(plan, fuel_per_lap_l=PLANNED_BURN,
                           wear_per_lap=0.03161, fuel_capacity_l=100.0,
                           lap_time_ms=PLANNED_LAP_MS, now=now)
    assert race.arm(a_timed_context(), a_timed_context()) is True
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 0}))
    now.advance(STANDING_START_S)
    calls = []
    for lap_num in range(1, 16):
        now.advance(LAPS[lap_num][0] / 1000.0)
        call = race.handle(lap_event(lap_num))
        if call:
            calls.append(call)
    assert calls[-1].kind == CHEQUER
    assert calls[-1].lap == 15
    assert not any(c.kind == STAY_OUT for c in calls)


def test_the_clock_and_not_the_plan_decides_how_far_a_timed_race_goes():
    """**The whole reason the app owns a clock.** The distance used to be the
    approved plan's own estimate, frozen at arming, patched by GT7's packet
    clock when it ran out a lap early. Here the plan expects thirteen laps and
    the race has time for fifteen: the countdown follows the clock and the
    pace, and the engineer is still talking on laps 14 and 15."""
    plan = {"stints": [{"laps": 13, "compound": "RS", "start_lap": 1}]}
    now = FakeMonotonic()
    race = RaceCoordinator(plan, fuel_per_lap_l=PLANNED_BURN,
                           wear_per_lap=0.03161, fuel_capacity_l=100.0,
                           lap_time_ms=PLANNED_LAP_MS, now=now)
    race.arm(a_timed_context(), a_timed_context())
    assert race.state.laps_total == 13          # the plan's own estimate
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 0}))
    now.advance(STANDING_START_S)
    for lap_num in range(1, 14):
        now.advance(LAPS[lap_num][0] / 1000.0)
        race.handle(lap_event(lap_num))
    assert race.state.laps_total == 15          # the clock's answer
    assert race.state.finished is False


def test_gt7s_own_race_clock_decides_nothing():
    """The driver measured it as inaccurate. Every lap in this replay carries
    a nonsense figure in `remaining_time_ms` and the race is unaffected - the
    field still travels because a screen may want to show it, and nothing in
    race control may read it."""
    now = FakeMonotonic()
    race = tonight(now)
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 0}))
    now.advance(STANDING_START_S)
    for lap_num in range(1, 15):
        now.advance(LAPS[lap_num][0] / 1000.0)
        event = lap_event(lap_num)
        # Wildly wrong, in both directions, on alternate laps.
        event.data["remaining_time_ms"] = 0 if lap_num % 2 else 9_000_000
        race.handle(event)
    assert race.state.finished is False
    assert race.state.laps_total == 15


# ------------------------------------------------------------- tyre temps

def temp_state(**overrides) -> RaceState:
    fields = dict(lap=1, laps_total=15, position=4,
                  temp_window_front=(70.0, 77.0),
                  temp_window_rear=(77.0, 88.0),
                  temp_laps_to_window=2, tyre_compound="RS",
                  # The measured association for THIS car at THIS circuit.
                  # None everywhere else, and None means no conserve call.
                  temp_gap_conserve_c=8.0, temp_gap_quiet_c=6.7,
                  temp_gap_front_floor_c=72.0, temp_gap_s_per_c=0.89)
    fields.update(overrides)
    return RaceState(**fields)


def test_cold_at_the_green_needs_a_real_margin_below_the_range():
    cold = temp_state()
    cold.note_temps(1, 59.3, 61.5)
    call = next_call(cold)
    assert call.kind == TYRE_TEMP and "Tyres cold" in call.call
    assert "2 laps to come up" in call.reason

    warm = temp_state()
    warm.note_temps(1, 68.1, 71.3)      # the real grid-warmed lap one
    assert next_call(warm) is None


def test_there_is_no_push_call_because_there_is_no_window():
    """The driver asked to be told when the tyres are in their optimal window
    so he can push. **No such window has ever been published for GT7** - the
    question was put to GTPlanet in April 2025 and answered "I didn't test the
    lower range", PD's manual documents the HUD frame as simply redder with
    heat, and inventing a lower edge is exactly how 85-110 degC got into this
    codebase. A set sitting squarely inside the measured running range must
    therefore produce no licence to push."""
    state = temp_state(lap=2)
    state.note_temps(1, 73.0, 78.3)
    state.lap = 2
    state.note_temps(2, 73.2, 78.5)
    call = next_call(state)
    assert call is None or "push" not in call.spoken().lower()


def test_the_warm_up_plateau_is_announced_instead():
    """What CAN be measured is the warm-up curve flattening. It is a statement
    about a curve, not a claim about grip, and it says nothing about pushing."""
    state = temp_state(lap=0)
    for lap_num, front, rear in ((1, 62.0, 65.0), (2, 70.0, 76.0),
                                 (3, 73.0, 79.0), (4, 73.4, 79.3),
                                 (5, 73.6, 79.5)):
        state.lap = lap_num
        state.note_temps(lap_num, front, rear)
        call = next_call(state)
        if call is not None:
            state.record(call)
    assert "up-to-temp" in state.temp_said
    said = next(c for c in (call,) if c is not None)
    assert said.call == "Tyres are up to temperature."
    assert "settled" in said.reason
    assert "window" not in said.spoken().lower()


def test_the_conserve_call_fires_on_the_measured_gap():
    """`rear - front` correlates with lap time at +0.89 s per degree across 17
    of his own laps, sign-stable between practice and race. Absolute
    temperature does not: the front is r = -0.13 within session."""
    state = temp_state(lap=6)
    state.note_temps(6, 76.3, 86.0)     # gap 9.7, front well up to temperature
    call = next_call(state)
    assert call.kind == TYRE_TEMP and call.tag == "conserve"
    assert "Ease" in call.call
    assert "over the fronts" in call.reason
    # An association measured on his own laps - never a physical optimum.
    assert "optimal" not in call.spoken().lower()
    assert "window" not in call.spoken().lower()


def test_a_cold_front_cannot_fake_a_hot_rear():
    """The gap conflates two mechanisms: one practice lap reads 8.3 degC
    because the FRONT was at 67, not because the rear was hot. Without the
    front gate the call fires on an out lap and asks him to back off a set
    that is still warming up."""
    state = temp_state(lap=2)
    state.note_temps(2, 67.0, 75.3)     # gap 8.3, front nowhere near ready
    call = next_call(state)
    assert call is None or call.tag != "conserve"


def test_nothing_speaks_on_the_external_wear_threshold():
    """Racing Soft 88 degC is stored, sourced and labelled - and untestable on
    his own data: 0 of 318 Monza corner observations reach it at all, and
    there are 15 gauge readings across 175 laps with none in either race. It
    is a cross-check the export names beside the measured temperature, and no
    live call rests on it."""
    state = temp_state(lap=6, temp_gap_conserve_c=None,
                       temp_gap_quiet_c=None, temp_gap_front_floor_c=None)
    state.note_temps(6, 82.0, 92.0)     # well past the RS threshold
    call = next_call(state)
    assert call is None or call.tag != "conserve"


def test_the_conserve_call_does_not_exist_where_the_gap_was_refuted():
    """**The association is not a law.** Fitted on 17 of his own laps at Yas
    Marina it is +0.87 s/degC at t = 3.52; tested across 95 clean laps at
    three cars and three circuits it does not hold - Monza comes back
    +0.011 +/- 0.077, z = -11.4 against the prior, on a WIDER gap range. So
    the thresholds live in a scoped record and the call simply does not exist
    where that record does not."""
    from pitcrew.store.tyres import gap_association_for, scope_key

    # **Resolved from the event row as the app stores it**, through the same
    # `context_from_event` the controller uses. Asserting against a hand-typed
    # "Yas Marina" is what let a scope that matched nothing pass for a whole
    # build.
    here = context_from_event(EVENT_ROW)
    assert scope_key(here.car, here.track, here.layout) == (
        "yas-marina-circuit-full-course/ford-shelby-gt350r-16")
    assert gap_association_for(here.car, here.track, here.layout) is not None

    monza = context_from_event({
        "car_name": "Porsche 911 RSR (991) '17",
        "track": "Autodromo Nazionale Monza", "layout": None,
        "race_type": "time", "race_laps": 50})
    assert gap_association_for(monza.car, monza.track, monza.layout) is None
    assert gap_association_for(None, "Yas Marina Circuit") is None
    assert gap_association_for("Ford Shelby GT350R '16", None) is None

    unscoped = temp_state(lap=6, temp_gap_conserve_c=None,
                          temp_gap_quiet_c=None, temp_gap_front_floor_c=None)
    unscoped.note_temps(6, 76.3, 90.0)  # a gap of 14 degrees, and silence
    call = next_call(unscoped)
    assert call is None or call.tag != "conserve"


def test_the_refuted_prior_carries_its_own_falsification():
    """"Refuted at Monza" is a fact the app carries, not one somebody
    remembers."""
    from pitcrew.store.tyres import GAP_PRIOR, WEAR_ONSET_PRIOR

    assert GAP_PRIOR.status == "REFUTED-OUT-OF-SCOPE"
    assert any("REFUTED" in line for line in GAP_PRIOR.evidence)
    assert len(GAP_PRIOR.speakable_scopes) == 1
    # And the external threshold may be spoken nowhere at all.
    assert WEAR_ONSET_PRIOR.speakable_scopes == ()


def test_a_gap_under_the_measured_threshold_says_nothing():
    state = temp_state(lap=6)
    state.note_temps(6, 82.0, 88.5)     # gap 6.5 - under the conserve edge
    assert next_call(state) is None


def test_conserve_is_said_once_and_re_arms_only_on_both_conditions():
    """1.3 degC of hysteresis between the trigger and the quiet threshold,
    plus two laps. Measured, backing off cools the rear about eight times
    faster than pushing heats it, so two laps is a real change."""
    state = temp_state(lap=6)
    state.note_temps(6, 76.3, 86.0)
    state.record(next_call(state))
    assert state.temp_conserve_lap == 6

    state.lap = 7                       # still hot, and too soon anyway
    state.note_temps(7, 76.0, 85.5)
    assert next_call(state) is None or next_call(state).tag != "conserve"

    state.lap = 8                       # two laps on, but the gap is still 8+
    state.note_temps(8, 75.0, 83.5)
    assert "conserve" in state.temp_said

    state.lap = 9                       # cooled back under the quiet edge
    state.note_temps(9, 74.0, 80.0)
    next_call(state)
    assert "conserve" not in state.temp_said

    state.lap = 10                      # and it may be said again
    state.note_temps(10, 76.0, 85.0)
    again = next_call(state)
    assert again is not None and again.tag == "conserve"


def test_the_baseline_offset_between_axles_is_never_a_finding():
    """Rears 8-11 degC hotter than fronts, every lap, is this car's normal -
    but only where the gap stays under the measured conserve threshold."""
    state = temp_state(lap=0, temp_window_front=None, temp_window_rear=None,
                       temp_laps_to_window=None, temp_gap_conserve_c=None,
                       temp_gap_quiet_c=None,
                       temp_gap_front_floor_c=None)
    for lap_num, (front, rear) in enumerate(
            [(73.0, 79.0), (74.0, 80.0), (73.5, 79.5), (73.8, 80.3),
             (73.2, 79.8), (73.6, 80.0)], start=1):
        state.lap = lap_num
        state.note_temps(lap_num, front, rear)
        call = next_call(state)
        if call is not None:
            state.record(call)
        # The warm-up plateau is allowed - it is a statement about a curve,
        # and so is the routine status call. What must never fire is anything
        # about the balance between the axles.
        assert (call is None or call.kind != TYRE_TEMP
                or call.tag == "up-to-temp"), (lap_num, call)


def test_a_rear_running_away_is_the_conserve_call_where_it_is_measured():
    """**"Rears heating" has been retired.** It compared the rear against its
    own baseline and needed several steady laps to establish one; where the
    gap association has been measured it says the same thing sooner and in a
    form he can act on, and it needs no measured temperature range to do it.
    Where the association has NOT been measured, nothing is said either way -
    which is the honest replacement for a baseline call that would have fired
    on a relationship the data refutes."""
    state = temp_state(lap=0, temp_window_front=None, temp_window_rear=None,
                       temp_laps_to_window=None)
    # A settled gap of six degrees - this car's normal, and under the measured
    # conserve threshold, so nothing is said about it.
    steady = [(73.0, 79.0), (73.5, 79.5), (73.2, 79.2), (73.4, 79.4),
              (73.1, 79.3)]
    for lap_num, (front, rear) in enumerate(steady, start=1):
        state.lap = lap_num
        state.note_temps(lap_num, front, rear)
        call = next_call(state)
        if call is not None:
            state.record(call)
        assert call is None or call.tag != "conserve"
    state.lap = 6
    state.note_temps(6, 73.3, 87.0)            # the rear runs away: gap 13.7
    call = next_call(state)
    assert call.kind == TYRE_TEMP and call.tag == "conserve"
    assert "heating" not in call.call
    state.record(call)
    state.lap = 7
    state.note_temps(7, 73.3, 88.0)
    following = next_call(state)
    assert following is None or following.tag != "conserve"


def test_fronts_going_first_may_move_brake_balance_rearward_only():
    state = temp_state(lap=0, temp_window_front=None, temp_window_rear=None,
                       temp_laps_to_window=None, temp_gap_conserve_c=None,
                       temp_gap_quiet_c=None,
                       temp_gap_front_floor_c=None)
    steady = [(73.0, 81.0), (73.5, 81.5), (73.2, 81.2), (73.4, 81.4),
              (73.1, 81.3)]
    for lap_num, (front, rear) in enumerate(steady, start=1):
        state.lap = lap_num
        state.note_temps(lap_num, front, rear)
        next_call(state)
    for lap_num, front in ((6, 79.0), (7, 80.0)):
        state.lap = lap_num
        state.note_temps(lap_num, front, 81.3)
        call = next_call(state)
    assert "Fronts heating" in call.call
    assert "rearward" in call.reason
    assert "forward" not in call.spoken()


def test_a_fresh_sets_warm_up_is_not_its_own_baseline():
    """`clear_stint` empties the temp history on a tyre change, and the trend
    baseline used to filter on the ABSOLUTE race lap - so after a lap-10 stop
    every entry qualified, the fresh set's cold laps entered its own baseline,
    and its normal steady temperature read as "heating" in every race with a
    tyre stop."""
    from pitcrew.race.calls import clear_stint
    state = temp_state(lap=0, laps_total=25, temp_window_front=None,
                       temp_window_rear=None, temp_laps_to_window=None,
                       temp_gap_conserve_c=None,
                       temp_gap_quiet_c=None,
                       temp_gap_front_floor_c=None)
    for lap_num in range(1, 11):
        state.lap = lap_num
        state.note_temps(lap_num, 73.0, 81.0)
        next_call(state)
    clear_stint(state, tyres_changed=True)
    fresh_set = [(11, 60.5, 64.0), (12, 67.0, 72.0),        # warm-up
                 (13, 73.0, 81.0), (14, 73.2, 81.2), (15, 73.1, 81.1),
                 (16, 73.3, 81.3), (17, 73.2, 81.4)]        # its normal
    for lap_num, front, rear in fresh_set:
        state.lap = lap_num
        state.note_temps(lap_num, front, rear)
        call = next_call(state)
        if call is not None:
            state.record(call)
        assert call is None or "heating" not in call.call, (lap_num, call)


def test_no_range_means_no_absolute_temperature_claim():
    """Missing is null: without a measured range the only allowed form is
    relative - both axles still climbing - at reduced confidence."""
    state = temp_state(temp_window_front=None, temp_window_rear=None,
                       temp_laps_to_window=None, temp_gap_conserve_c=None,
                       temp_gap_quiet_c=None,
                       temp_gap_front_floor_c=None)
    state.note_temps(1, 59.3, 61.5)
    assert next_call(state) is None     # one lap proves nothing
    state.lap = 2
    state.note_temps(2, 66.0, 68.0)
    call = next_call(state)
    assert call.kind == TYRE_TEMP
    assert "Tyres cold" in call.call
    assert call.confidence == MEDIUM
    assert "window" not in call.reason  # no measured figure to quote


# --------------------------------------------------------- measured window

def test_the_window_is_measured_from_steady_practice_laps():
    samples = ([(41, 59.3, 61.5), (41, 66.0, 70.0)]      # warm-up, dropped
               + [(41, 72.0, 78.0), (41, 74.0, 82.0), (41, 76.0, 86.0)]
               + [(42, 60.0, 62.0), (42, 68.0, 72.0)]    # warm-up, dropped
               + [(42, 71.0, 77.5), (42, 75.0, 84.0)])
    window = window_from_samples(samples)
    assert window is not None
    assert window.laps_sampled == 5
    assert 71.0 <= window.front[0] < window.front[1] <= 76.0
    assert 77.5 <= window.rear[0] < window.rear[1] <= 86.0
    assert window.laps_to_window == 2


def test_too_few_steady_laps_is_no_window_not_a_thin_one():
    samples = [(41, 59.3, 61.5), (41, 66.0, 70.0), (41, 72.0, 78.0)]
    assert window_from_samples(samples) is None
    assert window_from_samples([]) is None


def test_lap_axle_means_needs_temps_on_the_frames():
    frames = [{"temp_fl": 72.0, "temp_fr": 74.0,
               "temp_rl": 80.0, "temp_rr": 82.0},
              {"temp_fl": 73.0, "temp_fr": 75.0,
               "temp_rl": 81.0, "temp_rr": 83.0}]
    assert lap_axle_means(frames) == (73.5, 81.5)
    assert lap_axle_means([{"temp_fl": None, "temp_fr": None,
                            "temp_rl": None, "temp_rr": None}]) is None


# ----------------------------------------------- the live feed's new facts

def test_a_completed_lap_carries_its_axle_temperature_means():
    state = SessionState(SessionKind.PRACTICE)
    state.update(make_packet(tyre_temp_fl=70.0, tyre_temp_fr=72.0,
                             tyre_temp_rl=80.0, tyre_temp_rr=82.0))
    state.update(make_packet(tyre_temp_fl=72.0, tyre_temp_fr=74.0,
                             tyre_temp_rl=82.0, tyre_temp_rr=84.0))
    events = state.update(make_packet(
        tyre_temp_fl=72.0, tyre_temp_fr=74.0,
        tyre_temp_rl=82.0, tyre_temp_rr=84.0, last_lap_ms=94_000))
    lap = events[0].data["lap"]
    assert lap.tyre_temp_front_c == pytest.approx(72.0, abs=0.5)
    assert lap.tyre_temp_rear_c == pytest.approx(82.0, abs=0.5)


def test_the_session_state_no_longer_finishes_a_timed_race():
    """It used to, off `remaining_time_ms` - a field the driver measured as
    inaccurate, gated on an unverified assumption about what GT7 does with it
    after expiry, and logged once a lap precisely because nothing had
    certified that. **The finish moved to the race layer**, which owns a
    monotonic timer started at the green and reconciles it against these very
    lap times. This class sees a lap count and nothing else, and a timed race
    has none."""
    state = SessionState(SessionKind.RACE)
    state.update(make_packet(speed_ms=0.0, remaining_time_ms=1_800_000))
    events = state.update(make_packet(speed_ms=40.0,
                                      remaining_time_ms=1_800_000))
    assert any(e.kind is EventKind.RACE_STARTED for e in events)
    events = state.update(make_packet(speed_ms=40.0, last_lap_ms=121_511,
                                      remaining_time_ms=1_000_000))
    assert [e.kind for e in events] == [EventKind.LAP_COMPLETED]
    # The clock reading zero decides nothing here any more.
    events = state.update(make_packet(speed_ms=40.0, last_lap_ms=119_170,
                                      remaining_time_ms=0))
    assert [e.kind for e in events] == [EventKind.LAP_COMPLETED]
    # And it still travels, for anything that only wants to show it.
    assert events[0].data["remaining_time_ms"] == 0


def test_a_lap_race_never_takes_the_timed_finish_branch():
    """GT7 reports -1 for a lap race's clock; it must not read as expired."""
    state = SessionState(SessionKind.RACE)
    state.update(make_packet(speed_ms=0.0, laps_in_race=3,
                             remaining_time_ms=-1))
    state.update(make_packet(speed_ms=40.0, laps_in_race=3,
                             remaining_time_ms=-1))
    events = state.update(make_packet(speed_ms=40.0, laps_in_race=3,
                                      last_lap_ms=94_000,
                                      remaining_time_ms=-1))
    assert [e.kind for e in events] == [EventKind.LAP_COMPLETED]


# ------------------------------------------------------------- the outcome

def test_the_outcome_names_the_fold():
    from pitcrew.analysis.session import LapInput
    from pitcrew.race.outcome import race_outcome
    laps = [LapInput(lap_num=n, lap_time_ms=120_000, fuel_start=90.0,
                     fuel_end=83.0) for n in range(1, 16)]
    text = race_outcome(laps, planned_stops=2, final_position=5,
                        declined_calls=11, stay_out_lap=9)
    assert "No stops" in text
    assert "plan called for 2 stops" in text
    assert "folded to the driver's stay-out on lap 9" in text
    assert "11 calls offered and not taken" in text


# ------------------------------------------------- one rule for one identity

def test_an_accented_car_name_folds_rather_than_fracturing():
    """**The third identity bug of the same family, 17 Aug 2026.**

    `str.isalnum()` returns True for "a-acute", so a rule written as "keep the
    alphanumerics" kept it and wrote `lamborghini-hurac<a>n-gt3-15`, while a
    rule written as a regex over `[a-z0-9]` treated it as a separator and
    produced `lamborghini-hurac-n-gt3-15`. Two rules, one identity, and a
    lookup for the Huracan could never reach its own 300 grip observations or
    its 8 fitted models. Both sides were internally consistent, which is why
    nothing failed loudly.

    `slugify` is now the one rule and it folds to ASCII."""
    from pitcrew.store.tyres import scope_key, slugify

    assert slugify("Lamborghini Huracán GT3 '15") == (
        "lamborghini-huracan-gt3-15")
    assert slugify("Nürburgring") == "nurburgring"
    assert slugify("Citroën") == "citroen"
    # The composed scope, from the event row as the app stores it.
    assert scope_key("Lamborghini Huracán GT3 '15",
                     "Watkins Glen International", "Long Course") == (
        "watkins-glen-international-long-course/lamborghini-huracan-gt3-15")


def test_a_name_with_nothing_latin_in_it_still_gets_its_own_identity():
    """Every such name collapsing to "" would be the same bug wearing a
    different hat, so the fallback is a digest of the original."""
    from pitcrew.store.tyres import slugify

    suzuka, fuji = "鈴鹿", "富士"
    assert slugify(suzuka) == slugify(suzuka)      # stable
    assert slugify(suzuka) != slugify(fuji)        # and distinct
    assert slugify(suzuka)


def test_the_layout_is_part_of_the_circuit_identity():
    """Joined before slugging, so "Yas Marina Circuit" plus "Full Course" is
    one key. The ordering is part of the identity and not a formatting
    choice."""
    from pitcrew.store.tyres import scope_key

    full = scope_key("car", "Yas Marina Circuit", "Full Course")
    south = scope_key("car", "Yas Marina Circuit", "South Course")
    bare = scope_key("car", "Yas Marina Circuit")
    assert full != south != bare
    assert full.startswith("yas-marina-circuit-full-course/")



# ------------------------------------- the green that arrived after the race
#
# Monza, 19 Aug 2026, session 53 - the final rehearsal. The launch detector
# fired at the **lap-2 crossing**, 112 s after the car had actually launched,
# so the clock started with a lap and a half of racing already behind it. Both
# of its measures were short by the same racing, which is why the
# reconciliation could not see it: it compares them against each other.
#
# What followed: drift read -110.7 s, the reference went to the lap sum (the
# measure missing lap 1), elapsed race time ran ~117 s light to the flag, and
# the in-box refuel call asked for **94 L against a stint that needed 78**.
# The driver ignored it and finished on 1.15 L.

REHEARSAL_LAPS_MS = [116947, 110958, 114024, 111458, 109411, 110818, 111276,
                     110235, 111421, 110116, 109294, 109554, 110418]
REHEARSAL_DURATION_S = 50 * 60.0


def a_late_green(laps_before_green: int = 1):
    """The rehearsal's own opening, driven on a fake monotonic clock.

    `session_state` emits RACE_STARTED before LAP_COMPLETED for the same
    packet, so a green detected ON a crossing does not capture that lap before
    the green - only the ones fully completed ahead of it. One is the measured
    case: lap 1 captured, lap 2 the first crossing the clock ever sees.
    """
    now = FakeMonotonic()
    clock = RaceClock(REHEARSAL_DURATION_S, now=now)
    captured = REHEARSAL_LAPS_MS[:laps_before_green]
    # The green fires where the racing had already reached.
    now.advance(sum(captured) / 1000.0)
    clock.start(sum(captured), laps_before=len(captured))
    return clock, now


def test_a_green_detected_late_still_counts_elapsed_from_lap_one():
    clock, now = a_late_green()
    # Lap 2 completes on the same packet as the green, so it is the first
    # crossing the clock sees rather than something it was handed.
    clock.note_lap(REHEARSAL_LAPS_MS[1], lap_num=2)
    two_laps_s = sum(REHEARSAL_LAPS_MS[:2]) / 1000.0
    assert clock.elapsed_s == pytest.approx(two_laps_s, abs=0.01)
    assert clock.laps_before_clock == 1
    # No standing start is measurable on a green this late, and the app timer
    # must not be left carrying one it did not observe.
    #
    # **`None`, and it used to be `0.0`.** The zero came out of a
    # `max(0.0, ...)` and said the wrong thing in the loudest possible way:
    # the log line it feeds exists to report how late the launch detector
    # fired, and session 127 printed `0.00 s` off a green 111.2 s late.
    # Not measurable is not zero - CLAUDE.md rule 9. The lights-out case
    # below still measures its 6.0 s, so the refusal is not a blanket one.
    assert clock.as_snapshot()["greenToFirstCrossingS"] is None


def test_the_two_measures_agree_for_the_rest_of_a_late_started_race():
    """The whole failure was that both measures were short by the same racing,
    so they corroborated each other all the way to the flag."""
    clock, now = a_late_green()
    clock.note_lap(REHEARSAL_LAPS_MS[1], lap_num=2)
    for index, lap_ms in enumerate(REHEARSAL_LAPS_MS[2:], start=3):
        now.advance(lap_ms / 1000.0)
        rec = clock.note_lap(lap_ms, lap_num=index)
    assert rec.corroborated is True
    assert abs(rec.drift_s) < 1.0
    # Thirteen laps of the real race, counted from lap 1 rather than from the
    # green. The broken clock read 1329.0 s here - a whole lap light.
    assert clock.elapsed_s == pytest.approx(
        sum(REHEARSAL_LAPS_MS) / 1000.0, abs=0.01)


def test_the_late_green_no_longer_buys_an_extra_lap_of_fuel():
    """The number the driver actually heard, and the one he should have."""
    clock, now = a_late_green()
    clock.note_lap(REHEARSAL_LAPS_MS[1], lap_num=2)
    for index, lap_ms in enumerate(REHEARSAL_LAPS_MS[2:], start=3):
        now.advance(lap_ms / 1000.0)
        clock.note_lap(lap_ms, lap_num=index)

    burn = 5.529
    state = RaceState(
        lap=13, in_pit=True, fuel_per_lap_l=burn, race_minutes=50,
        next_stint_laps=13, further_stop_planned=False,
        laps_estimate_firm=False,
        laps_total=13 + clock.laps_left(REHEARSAL_LAPS_MS[-1]))
    target = fuel_target_l(state)
    # 94 L was the call. Anything at or above it is the bug reappearing.
    assert target is not None and target < 90.0
    # And it still covers the stint the plan asked for, with the timed race's
    # deliberate lap of margin on top - never less than the plan's own 13.
    assert target >= 14 * burn


def test_the_backstop_back_dates_from_the_lap_number_alone():
    """When nothing was captured before the green - the coordinator was armed
    mid-lap, or an older caller passed no figures - GT7's own lap number still
    says racing happened. Estimated at this lap's pace, and flagged as an
    estimate rather than passed off as a reading."""
    now = FakeMonotonic()
    clock = RaceClock(REHEARSAL_DURATION_S, now=now)
    clock.start()
    clock.note_lap(110958, lap_num=3)
    assert clock.laps_before_clock == 2
    assert clock.start_estimated is True
    assert clock.as_snapshot()["startEstimated"] is True
    # Three laps of racing, the two missing ones estimated at this lap's pace.
    assert clock.elapsed_s == pytest.approx(3 * 110.958, abs=0.01)


def test_a_normal_green_measures_its_standing_start_untouched():
    """The repair must not fire on the race it was not written for."""
    now = FakeMonotonic()
    clock = RaceClock(REHEARSAL_DURATION_S, now=now)
    clock.start()
    now.advance(6.0 + 116.947)                   # grid period, then lap one
    clock.note_lap(116947, lap_num=1)
    assert clock.laps_before_clock == 0
    assert clock.start_estimated is False
    # The standing start is still measured, and still the whole of the offset.
    assert clock.as_snapshot()["greenToFirstCrossingS"] == pytest.approx(6.0)


def test_a_negative_drift_never_hands_the_reference_to_the_lap_sum():
    """The handover defends against the app timer running LONG - a pause it
    did not see. A lap sum that is AHEAD of the timer is the opposite fault
    and the sum is the measure at fault, so preferring it rewards the wrong
    one. This is the guard for a late start the back-dating did not catch."""
    now = FakeMonotonic()
    clock = RaceClock(REHEARSAL_DURATION_S, now=now)
    clock.start()
    now.advance(110.0)
    clock.note_lap(110_000, lap_num=1)           # offset 0, both agree
    # A lap arrives carrying far more time than the timer ran through.
    now.advance(110.0)
    rec = clock.note_lap(220_000, lap_num=2)
    assert rec.corroborated is False and rec.drift_s < 0
    # The timer, not the sum: 220 s of clock, not 330 s of lap times.
    assert clock.elapsed_s == pytest.approx(220.0, abs=0.01)


# ------------------------------------- the stop that is clock but not distance


def test_the_stop_comes_off_the_clock_before_the_ceiling_not_after():
    """Subtracting whole laps from an already-rounded answer throws away the
    fraction the rounding was about. 14.07 laps minus a 19 s stop is 13.89,
    and both ceiling to 14 - but 15 minus a rounded stop is 14 only by luck."""
    clock, now = a_late_green()
    clock.note_lap(REHEARSAL_LAPS_MS[1], lap_num=2)
    for index, lap_ms in enumerate(REHEARSAL_LAPS_MS[2:], start=3):
        now.advance(lap_ms / 1000.0)
        clock.note_lap(lap_ms, lap_num=index)
    lap_ms = REHEARSAL_LAPS_MS[-1]
    assert clock.laps_left(lap_ms) == 15
    assert clock.laps_left(lap_ms, less_s=19.0) == 14


def test_the_flag_still_counts_crossings():
    """A crossing still happens on the lap the stop is taken, so the flag,
    'two to go' and the last lap must not see the discount."""
    clock, now = a_clock(duration_s=240.0)
    assert clock.laps_left(120_000) == 2
    assert clock.laps_left(120_000, less_s=0.0) == 2


def test_the_fill_is_sized_on_laps_that_are_actually_driven():
    """Monza, 19 Aug 2026. He was told 94 L for a stint that needed 78."""
    burn = 5.529
    common = dict(lap=13, in_pit=True, fuel_per_lap_l=burn, race_minutes=50,
                  next_stint_laps=13, further_stop_planned=False,
                  laps_estimate_firm=False, laps_total=28)
    # The flag's own count, with the stop still inside it.
    assert fuel_target_l(RaceState(**common)) == pytest.approx(82.9, abs=0.1)
    # The fuel path's count, with the stop taken out of the clock.
    sized = fuel_target_l(RaceState(laps_after_stops=14, **common))
    assert sized == pytest.approx(77.4, abs=0.1)
    # Still covers the stint the plan asked for, plus the timed race's lap.
    assert sized >= 13 * burn


def test_no_pending_stop_means_no_discount():
    """The last stint runs to the flag. Nothing is coming off the CLOCK - no
    pending stop is priced - and the fill falls through to `laps_remaining`;
    the in-lap (lap 21) still comes off, because the fill is for the laps
    after the box whichever way the count was reached."""
    burn = 5.529
    state = RaceState(lap=20, fuel_per_lap_l=burn, race_minutes=50,
                      next_stint_laps=None, further_stop_planned=False,
                      laps_estimate_firm=False, laps_total=28,
                      laps_after_stops=None)
    assert fuel_target_l(state) == pytest.approx(7 * burn + burn, abs=0.1)


def test_a_dropped_lap_names_the_pit_lane_rather_than_the_two_measures():
    """The clock folds a missed crossing into its offset and stays on the app
    timer, so "on lap times" would name the measure it is NOT using. Both
    races so far missed the crossing in the pit lane.

    This branch also had no `confidence` bound at all - an UnboundLocalError
    on the two calls made at the very end of a race, which no test covered
    and which a replay of the rehearsal found."""
    state = RaceState(lap=25, laps_to_go_estimate=1, laps_dropped=1,
                      clock_corroborated=False)
    call = _laps_to_go(state)
    assert call is not None
    assert call.call == "Last lap."
    assert "crossing was missed" in call.reason
    assert call.confidence == MEDIUM


def test_a_drift_with_no_dropped_lap_still_names_the_lap_times():
    state = RaceState(lap=25, laps_to_go_estimate=2, laps_dropped=0,
                      clock_corroborated=False)
    call = _laps_to_go(state)
    assert "lap times" in call.reason and call.confidence == MEDIUM


def test_a_clock_that_agrees_says_so_plainly():
    state = RaceState(lap=25, laps_to_go_estimate=1, laps_dropped=0,
                      clock_corroborated=True)
    call = _laps_to_go(state)
    assert call.reason == "On the clock." and call.confidence == HIGH


def test_the_fill_never_asks_for_more_than_the_tank_holds():
    """"Fuel to 510 litres" was voiced once. An instruction the car cannot
    execute is worse than none: he acts on it, finds the fill stops short and
    has to work the shortfall out himself at pit-exit speed."""
    state = RaceState(lap=1, fuel_per_lap_l=5.5, fuel_capacity_l=100.0,
                      fuel_l=10.0, laps_total=60, race_minutes=50,
                      laps_estimate_firm=False)
    said = _fuel_instruction(state)
    assert "510" not in said
    numbers = [float(n) for n in __import__("re").findall(r"\d+\.?\d*", said)]
    assert all(n <= 100.0 for n in numbers), said
