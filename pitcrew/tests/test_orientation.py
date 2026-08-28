"""Where he is, when the screen no longer says.

The driver turned GT7's race-information HUD off on 28 Aug 2026 - lap number,
position and time remaining all came off the display, leaving car information
only. Those three now exist nowhere except in this call, which changes what it
is: not reassurance duplicating a dashboard, but the instrument.

*"Laps remaining must be 100% accurate even in a timed race... George can work
out my average lap time and time left divided by it rounded up to the next
whole lap. George can notify time at the start but from the half way point I
want time and laps remaining."*

The arithmetic he describes is `clock.laps_left` and was already there. What
was missing was that nothing said it, and that two things had to be right
first: the lap count, and the clock.
"""
from __future__ import annotations

from pitcrew.race.calls import (
    LAPS_FROM_FRACTION,
    RaceState,
    minutes_left,
    orientation,
)


def timed(**overrides) -> RaceState:
    fields = dict(lap=13, laps_total=22, race_minutes=30.0, position=3,
                  fuel_l=60.0, fuel_per_lap_l=6.0, last_said_lap=12,
                  status_every_laps=1)
    state = RaceState(**{**fields, **overrides})
    state.race_remaining_s = overrides.pop("_left", 660.0)
    return state


# ------------------------------------------------------------- the lap number

def test_the_lap_number_is_gt7s_count_not_the_app_s():
    """**Road Atlanta is on file.** GT7's `laps_completed` sat +1 above the
    app's on lap 1 and +2 by lap 20 - the crossing inside the pit sequence
    never reached the app - so its table holds 21 laps of a race he drove 22
    of. `laps_remaining()` has always applied that correction; the lap NUMBER
    never did, because nothing spoke it."""
    state = timed(lap=13)
    state.laps_dropped_seen = 1
    assert state.lap_now() == 14


def test_a_corrected_crossing_is_said_flat_not_as_a_pair():
    """**A pair that excludes the truth is worse than either number.**

    This said "Lap N or M" and at Road Atlanta's measured drop of two that
    renders "Lap 20 or 22" - a disjunction with the right answer missing from
    it. And the same breath says "9 laps to go", which comes from
    `laps_remaining()` and treats the same correction as certain: one quantity
    cannot be uncertain in one clause and certain in the next.

    It is certain enough to say flat. The correction comes from GT7's own
    `laps_completed`, which is the authority here and the whole reason the
    count is taken from it rather than from the app's own crossings.
    """
    state = timed(lap=13)
    state.laps_dropped_seen = 2
    assert state.lap_now() == 15
    said = orientation(state)
    assert said.startswith("Lap 15."), said
    assert " or " not in said.split(".")[0]


def test_a_clean_count_says_one_number():
    assert orientation(timed(lap=13)).startswith("Lap 13")


# ------------------------------------------------------------------ the clock

def test_minutes_are_the_measurement():
    """The app timer runs from the green and is reconciled against GT7's own
    exact lap figures. The lap count divides it by a median and inherits that
    median's error - so the clock is said whenever it exists, and the laps
    only when they resolve."""
    state = timed()
    state.race_remaining_s = 660.0
    assert minutes_left(state) == "11 minutes left."


def test_the_last_minute_is_counted_in_seconds():
    state = timed()
    state.race_remaining_s = 45.0
    assert minutes_left(state) == "45 seconds left."


def test_a_clock_it_does_not_have_is_said_rather_than_dropped():
    """With the HUD off, a race with no clause about its own length is
    indistinguishable from a race with no end - and from a dead app."""
    state = timed()
    state.race_remaining_s = None
    assert "I don't have the clock" in orientation(state)


# ------------------------------------------------- time first, then time+laps

def test_the_first_half_is_the_clock_only():
    """His call, and it matches the measurement: `ceil(time/lap)` is
    unresolvable early - on a real 30-minute race the first four crossings
    would have flipped on a median error of 0.12-0.66 s against a 2.04 s
    spread - and firms up as the remaining time shrinks."""
    state = timed(lap=3, laps_total=22)
    state.race_remaining_s = 30.0 * 60 * (1.0 - LAPS_FROM_FRACTION) + 60
    said = orientation(state)
    assert "minutes left" in said
    assert "to go" not in said


def test_from_halfway_it_is_both():
    state = timed(lap=13, laps_total=22)
    state.race_remaining_s = 660.0
    state.laps_estimate_firm = True
    assert orientation(state) == "Lap 13. 11 minutes left. 9 laps to go."


def test_an_unresolved_count_names_both_candidates():
    """`ceil` flips when the time left is near a whole number of laps. There
    the answer is not unknown - it is one of two, and naming them beats
    picking one and beats the silence this used to fall to.

    **The pair runs downward.** Every known error in this count is in the same
    direction - it reads long: the stop discount uses an ex-fuel pit loss and
    is therefore too small, and the achieved median is dragged down by
    fresh-tyre laps. `N or N+1` asserts the truth may be HIGHER than the
    estimate, which is the one thing it cannot be.
    """
    state = timed(lap=13, laps_total=22)
    state.race_remaining_s = 660.0
    state.laps_count_hedged = True
    assert orientation(state) == "Lap 13. 11 minutes left. 8 or 9 laps to go."


# -------------------------------------------------------------- the lap race

def test_a_lap_race_says_the_lap_and_what_is_left_of_it():
    """**One number per sentence.** The pack plays a call by peeling known
    sentences and splitting what is left on its single number, so "Lap 7 of
    24." carries two and falls whole to live synthesis - a pause on every
    crossing at the cadence he asked for. Two sentences cost one clip each and
    say more: the count he is on and the count still to run."""
    state = RaceState(lap=7, laps_total=24, position=4)
    assert orientation(state) == "Lap 7. 17 laps to go."


def test_a_lap_race_with_no_distance_still_says_the_lap():
    state = RaceState(lap=7, position=4)
    assert orientation(state) == "Lap 7."


def test_nothing_is_said_before_the_first_crossing():
    assert orientation(RaceState(lap=0, laps_total=24)) == ""




def test_the_clock_actually_reaches_the_lap_row(store, event_id):
    """**A write-only column is worse than no column.**

    The stamp lived in the coordinator's `_on_lap`, and the INSERT lives in
    the controller's lap-completed slot. Both are queued to the Qt thread and
    Qt runs them in order, so the row was written first and all three columns
    were NULL on every lap of every race - while the schema comment promised
    they were the record that would settle whether the lap estimate had ever
    been right.
    """
    from pitcrew.race.coordinator import RaceCoordinator
    from pitcrew.race.clock import RaceClock
    from pitcrew.telemetry.session_state import Lap

    race = RaceCoordinator({"stints": [{"laps": 20, "start_lap": 1}]})
    race.clock = RaceClock(1800.0, now=lambda: 600.0)
    race.clock.start()
    lap = Lap(lap_num=5, lap_time_ms=94_000, best_lap_ms=94_000, delta_ms=0,
              fuel_start=40.0, fuel_end=36.6, fuel_used=3.4, position=3,
              is_pit_lap=False, is_out_lap=False)
    race.stamp_clock(lap)

    session_id = store.start_session(event_id, "race")
    lap_id = store.add_lap(session_id, lap)
    row = store._query("SELECT race_elapsed_s, race_remaining_s, laps_dropped "
                       "FROM laps WHERE id = ?", (lap_id,))[0]
    assert row["race_elapsed_s"] is not None, "the clock never reached the row"
    assert row["race_remaining_s"] is not None
    assert row["laps_dropped"] is not None


# ------------------------------------------------ the stop that spends clock

def crossings_truth(remaining_s: float, lap_s: float, stop_s: float,
                    stop_on: int = 1) -> int:
    """How many crossings there will be, simulated rather than derived.

    The flag falls at the first crossing after the clock expires, so this
    walks the laps and counts them - which is the ground truth the estimate is
    supposed to predict.
    """
    elapsed, laps = 0.0, 0
    while elapsed < remaining_s:
        elapsed += lap_s + (stop_s if laps == stop_on else 0.0)
        laps += 1
    return laps


def test_a_pending_stop_prices_the_stop_rather_than_hedging_it():
    """**He may simply not stop, and he often does not.**

    The count used to have the stop DISCOUNTED out of it, which assumes he
    takes it. He skipped one in two recorded races and was right both times,
    and the discounted count was then a lap short - "3 or 4 laps to go" for an
    answer of 5, a pair with the truth outside it.

    So the number is what he gets if he stays out, and the stop is named as
    what it would cost. That is not an error bar: it is a decision he is about
    to make, and it says which way and what decides it.
    """
    state = timed(lap=13, laps_total=22)
    state.race_remaining_s = 660.0
    state.stop_pending = True
    state.stop_costs_laps = 1
    said = orientation(state)
    assert said == "Lap 13. 11 minutes left. 9 laps to go, one less if you stop."
    assert " or " not in said


def test_the_priced_stop_stands_down_on_the_last_lap():
    """"1 lap to go, one less if you stop." claims zero laps, and it has no
    clip either."""
    state = timed(lap=21, laps_total=22)
    state.race_remaining_s = 95.0
    state.stop_pending = True
    state.stop_costs_laps = 1
    assert orientation(state) == "Lap 21. 95 seconds left. 1 lap to go."


# --------------------------------------- the last crossings, on the real thing

def a_timed_race(pit_loss_s=25.0, stints=2, minutes=30.0):
    """A coordinator with a real clock, driven by a clock the test moves."""
    from pitcrew.race.clock import RaceClock
    from pitcrew.race.coordinator import RaceCoordinator

    plan = {"stints": [{"laps": 10, "compound": "RS", "fuel_l": 60.0,
                        "start_lap": 1 + 10 * n} for n in range(stints)],
            "binding_constraint": "fuel"}
    race = RaceCoordinator(plan, pit_loss_s=pit_loss_s)
    race.state.race_minutes = minutes
    elapsed = {"s": 0.0}
    race.clock = RaceClock(minutes * 60.0, now=lambda: elapsed["s"])
    race.clock.start()
    race.elapsed = elapsed
    return race


def test_the_spoken_count_never_moves_the_fuel_distance():
    """**The defect this test exists for, and it was shipped.**

    Putting the stop discount into `laps_total` moved the race distance under
    every fuel calculation - `fuel_frame`, `fuel_reaches_flag`,
    `fuel_target_l` and `stay_out_call` all measure against
    `laps_remaining()`. On the real coordinator at four crossings from the
    flag with a stop pending that turned "box, you cannot make it" into
    "Staying out? You can make it." at about five litres short.

    The two figures are different questions and stay apart: `laps_remaining()`
    is the distance the tank has to cover, `laps_to_flag` is how many
    crossings there will be.
    """
    race = a_timed_race()
    race.state.lap = 12
    race.state.laps_total = 16
    race.state.race_remaining_s = 400.0
    race.state.stop_pending = True
    race.state.stop_costs_laps = 1
    assert race.state.laps_remaining() == 4, "the fuel distance is untouched"
    # **The same four, spoken.** There is one count now. A second, discounted
    # one was the defect: inside `laps_total` it moved the distance under
    # every fuel calculation, and once isolated it disagreed with what
    # push-to-talk and the colour line answer to the same question in the
    # same words.
    assert "4 laps to go, one less if you stop" in orientation(race.state)


def test_the_count_stops_being_discounted_once_the_stop_is_off():
    """`_stops_off` says "no more stops on fuel" and nothing retired the stop
    from the plan, so the discount outlived its own cancellation - and in the
    stay-out it outlived it permanently, because `stay_out_call` returns None
    exactly when the fuel cannot reach."""
    race = a_timed_race()
    race.state.lap = 12
    race.state.laps_total = 20
    race.state.stint_ends_on_lap = 14
    race.state.fuel_per_lap_l = 6.0
    race.state.fuel_l = 20.0
    race.state.plan_binding_constraint = "fuel"
    race.state.mandatory_stops_left = 0
    assert race._pending_stops() == 1, "a stop the fuel still needs"

    race.state.fuel_l = 90.0            # now it reaches the flag
    assert race._pending_stops() == 0, \
        "the discount survived the stop being declared off"


def test_under_one_lap_the_count_stands_down_for_the_run_in():
    """"0 or 1 laps to go." is not a thing to say, and it is not in the pack
    either - `UNCERTAIN_LAPS` starts at one. The run-in owns this ground."""
    state = timed(lap=22, laps_total=22)
    state.race_remaining_s = 20.0
    said = orientation(state)
    assert "to go" not in said, said
    assert "20 seconds left" in said


# ------------------------------------------- what "firm" is allowed to mean

def test_a_stint_that_has_run_long_is_not_called_firm():
    """**The margin test was blind to the largest error in the count.**

    The predictor is a median over laps already driven and the laps still to
    come are slower than it. Against CLAUDE.md 5.1's phase-2 band at a 100 s
    base lap: eighteen laps in, the remaining laps take 4.8 s/lap more than
    the median at the bottom of the band and 14.2 s more at the top, against a
    measured lap-to-lap sigma of 2.04 s. One lap long across the whole band,
    two at the top of it over ten laps.

    `laps_left_margin_s` is headroom before the ceiling flips, compared with
    RANDOM noise. This is a SYSTEMATIC bias, so a test of resolvability was
    being read as a test of correctness.
    """
    race = a_timed_race(stints=1)
    race.state.laps_since_stop = 18
    headroom = race._degradation_headroom_s()
    assert headroom > 2.04, (
        f"{headroom:.1f}s of bias must outweigh the 2.04s of noise the test "
        f"used to compare against on its own")


def test_a_fresh_stint_carries_almost_no_degradation_headroom():
    """It has to shrink to nothing, or the count is never flat and the hedge
    stops carrying information."""
    race = a_timed_race(stints=1)
    race.state.laps_since_stop = 0
    assert race._degradation_headroom_s() == 0.0


def test_a_priced_stop_beats_a_pair_that_cannot_say_which_way():
    """**A stop he may or may not take is not "one of two".** A pair says the
    truth is one of two values and cannot say which; this says exactly which
    way and what decides it - and it is a decision he is about to make rather
    than an error bar."""
    state = timed(lap=13, laps_total=22)
    state.race_remaining_s = 660.0
    state.stop_pending = True
    state.stop_costs_laps = 1
    said = orientation(state)
    assert "one less if you stop" in said, said
    assert " or " not in said


def test_the_unmeasured_pit_loss_wording_can_be_played_from_the_pack():
    """It lands at every crossing of the second half of a race at a circuit
    whose pit loss nobody has measured - which is most of them - so a miss
    here is a live synthesis on every lap."""
    from pitcrew.engineer import phrase_manifest as manifest

    state = timed(lap=13, laps_total=22)
    state.race_remaining_s = 660.0
    state.stop_pending = True
    state.stop_costs_laps = 1
    line = orientation(state)
    clips = set(manifest.clips())
    missing = [c for c in (manifest.segments_for(line) or ()) if c not in clips]
    assert not missing, (line, missing)


def test_the_clock_is_rounded_down_so_it_never_flatters():
    """At 91 s, rounding to nearest says "2 minutes left" - 29 s more race
    than there is, at the point where 29 s is a third of a lap. The green
    detection already runs the countdown long by an unmeasured amount in the
    same direction, and two overstatements compounding is how he plans a lap
    he does not have."""
    state = timed()
    for seconds, expected in ((91.0, "91 seconds left."),
                              (99.0, "99 seconds left."),
                              (119.0, "1 minute left."),
                              (150.0, "2 minutes left."),
                              (179.0, "2 minutes left."),
                              (180.0, "3 minutes left.")):
        state.race_remaining_s = seconds
        assert minutes_left(state) == expected, seconds


# ------------------------------- tests that bite on behaviour, not on presence


# ------------------------- guards driven through the real coordinator, not by
# ------------------------- hand-setting the state the coordinator computes

def a_clocked_race(*, pit_loss_s=20.0, stints=2, minutes=30.0, elapsed=0.0):
    from pitcrew.race.clock import RaceClock
    from pitcrew.race.coordinator import RaceCoordinator

    plan = {"stints": [{"laps": 10, "compound": "RS", "fuel_l": 60.0,
                        "start_lap": 1 + 10 * n} for n in range(stints)],
            "binding_constraint": "fuel"}
    race = RaceCoordinator(plan, pit_loss_s=pit_loss_s)
    race.state.race_minutes = minutes
    clock = {"s": elapsed}
    race.clock = RaceClock(minutes * 60.0, now=lambda: clock["s"])
    race.clock.start()
    race.clock_at = clock
    return race


def drive(race, *, lap, lap_ms, elapsed):
    """Put the coordinator at a crossing and let it compute the distance."""
    race.clock_at["s"] = elapsed
    race.state.lap = lap
    race.expect.achieved_lap_time_ms = lambda: lap_ms
    race._update_clock_distance()
    return race.state


def test_the_race_distance_is_never_the_discounted_one():
    """**The regression the whole line of work exists to prevent, guarded at
    the level it actually happens.**

    Two earlier tests claimed this and could not fail: both hand-assigned
    `laps_total` and so never exercised `_update_clock_distance`, which is the
    only place the defect can be reintroduced. Re-adding the discount there
    left the whole suite green.

    The distance must equal the RAW clock count, because `fuel_frame`,
    `fuel_reaches_flag`, `fuel_target_l` and `stay_out_call` all measure
    against it - and a lap taken out of it is the under-fuelling direction.
    """
    race = a_clocked_race()
    state = drive(race, lap=12, lap_ms=100_000, elapsed=1390.0)
    raw = race.clock.laps_left(100_000)
    assert state.laps_total == state.lap + state.laps_missed() + raw, (
        "laps_total is not the raw count - the fuel path has been moved")
    assert race._pending_stops() > 0, "with no pending stop this proves nothing"
    discounted = race.clock.laps_left(100_000, less_s=20.0)
    assert discounted < raw, "and the discount would have differed here"


def test_a_pending_stop_still_buys_a_full_lap_of_fuel_margin():
    """`laps_estimate_firm` sizes fills - `fuel_margin_l` returns a WHOLE LAP
    when it is False. The pending-stop term was dropped from it by accident
    while splitting the voice's hedge out, narrowing the fill by 4.8 L at Road
    Atlanta and 2.2 L at Yas: the running-dry direction, changed silently."""
    from pitcrew.strategy.model import fuel_margin_l

    race = a_clocked_race()
    # **A margin that comfortably clears the noise**, so `firm` is decided by
    # the pending stop and nothing else - without this the flag is False for
    # want of a sigma and the test passes whatever the code does.
    race.expect.sigma_ms = lambda: 500.0
    state = drive(race, lap=12, lap_ms=100_000, elapsed=1350.0)
    margin = race.clock.laps_left_margin_s(100_000)
    assert margin is not None and margin > 0.5, margin
    assert race._pending_stops() > 0
    assert state.laps_estimate_firm is False, (
        "a pending stop has to keep the count off firm for the FILL")
    whole, _why = fuel_margin_l(5, 6.3, sd_l=0.225, timed=True,
                                lap_count_firm=state.laps_estimate_firm)
    scatter, _why = fuel_margin_l(5, 6.3, sd_l=0.225, timed=True,
                                  lap_count_firm=True)
    assert whole > scatter, "the fill lost its lap of margin"


def test_the_stop_is_priced_from_the_clock_and_is_usually_silent():
    """**A flat "one less if you stop" was wrong on 15 of 18 crossings** of
    the two timed races on file: at 20 s of pit loss against an 82-120 s lap
    the stop usually costs no lap at all. Saying otherwise told him there was
    less race than there is."""
    race = a_clocked_race()
    # 850 s left on a 100 s lap, past halfway so the count is spoken: nine
    # laps fit, and nine still fit with the stop's twenty seconds gone.
    state = drive(race, lap=5, lap_ms=100_000, elapsed=950.0)
    assert state.stop_costs_laps == 0
    state.race_remaining_s = race.clock.remaining_s
    state.position = 3
    assert "if you stop" not in orientation(state), orientation(state)

    # 810 s left: nine fit without the stop, eight with it.
    state = drive(race, lap=5, lap_ms=100_000, elapsed=990.0)
    assert state.stop_costs_laps == 1
    state.race_remaining_s = race.clock.remaining_s
    state.position = 3
    assert "one less if you stop" in orientation(state), orientation(state)


def test_an_unmeasured_stop_cost_is_not_spoken_as_one():
    """`pit_loss_secs` is `declared` on every event on file and Watkins
    measured 15.7 s ex-fuel against a typed-in 20. Rules 3 and 5: a cost
    nobody has measured is not a cost to state."""
    race = a_clocked_race(pit_loss_s=None)
    state = drive(race, lap=5, lap_ms=100_000, elapsed=990.0)
    assert state.stop_costs_laps is None
    state.race_remaining_s = race.clock.remaining_s
    state.position = 3
    assert "if you stop" not in orientation(state), orientation(state)


def test_the_stop_question_is_answered_against_this_crossing_s_distance():
    """`_pending_stops` asks `stop_still_needed`, which reads
    `laps_remaining()`, which reads `laps_total` - so asking it BEFORE the
    distance was written measured this crossing against the previous one's,
    and answered the stop question wrongly whenever the two differed."""
    import inspect

    from pitcrew.race.coordinator import RaceCoordinator

    body = inspect.getsource(RaceCoordinator._update_clock_distance)
    assert body.index("self.state.laps_total = ") < body.index(
        "self.state.stop_pending = "), (
        "the stop question is being asked against a stale distance")

