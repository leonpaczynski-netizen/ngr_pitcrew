"""Suzuka, 13 Sep 2026: a 30-minute timed race, session 166, run with no plan.

He finished on 2.73 L with no stop, lifting on the last two laps. George said
"Recommend 1 stop" four times, never gave a fuel-save figure, told him "the
stop has moved 3 laps" about a stop that had moved 0 or 2, and ran the
laps-to-go a lap long from lap 7 to the flag - "Two to go." on the last lap.

Per lap: (lap, time s, fuel at end L, race_remaining_s at end).
"""
from __future__ import annotations

from pitcrew.race.calls import (
    FUEL_REACHES,
    FUEL_SHORT,
    LAPS_TO_GO,
    RaceState,
    _chase,
    _fuel_standing,
    _laps_to_go,
    next_call,
)
from pitcrew.race.clock import RaceClock
from pitcrew.race.coordinator import RaceCoordinator
from pitcrew.race.replan import (
    NONE,
    URGENT,
    PlanRegister,
    Replan,
    assess,
)
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent

LAPS = [
    (1, 134.2, 91.45, 1669.7), (2, 133.9, 83.31, 1535.8),
    (3, 125.4, 75.49, 1410.4), (4, 125.5, 68.27, 1284.9),
    (5, 132.3, 60.93, 1152.5), (6, 125.0, 53.54, 1027.5),
    (7, 126.7, 46.41, 900.8), (8, 126.2, 39.21, 774.6),
    (9, 126.3, 32.03, 648.3), (10, 133.8, 25.15, 514.5),
    (11, 126.7, 17.97, 387.9), (12, 126.6, 11.40, 261.2),
    (13, 132.9, 7.43, 128.4), (14, 134.0, 2.73, -5.6),
]
PRACTICE_BURN = 9.116      # the quali-pace practice figure the race seeded on
RACE_BURN = 7.19           # green median of laps 3-12


def lap_12(**overrides) -> RaceState:
    """After lap 12, with the TRUE distance: two laps left."""
    fields = dict(lap=12, laps_total=14, race_minutes=30.0, fuel_l=11.40,
                  fuel_per_lap_l=RACE_BURN, fuel_capacity_l=100.0, position=5,
                  laps_to_go_estimate=2)
    fields.update(overrides)
    state = RaceState(**fields)
    state.race_remaining_s = 261.2
    state.last_said_lap = 11
    return state


# ------------------------------------------- 1. a save target, not a stop

def test_a_shortfall_a_save_covers_is_a_save_target():
    """0.4 laps short with two to go is three litres - a lift, not a stop."""
    call = next_call(lap_12())
    assert call.kind == FUEL_SHORT
    assert call.call == "Save 1.5 litres a lap to make the flag."
    assert "stop" not in call.spoken().lower()


def test_the_heartbeat_does_not_call_three_litres_short_fuel_good():
    """The half-lap tolerance is burn noise over a stint, not over two laps."""
    assert _fuel_standing(lap_12()) == "0.4 short to the flag on current burn."


def test_a_shortfall_no_save_covers_is_still_a_stop():
    call = next_call(lap_12(fuel_l=5.0))                     # 1.3 laps short
    assert call.call == "Fuel needs a stop."


def test_the_replanner_does_not_recommend_a_stop_a_save_covers():
    verdict = assess(laps_done=12, laps_total=14, fuel_l=11.40,
                     planned_fuel_per_lap=PRACTICE_BURN,
                     observed_fuel_per_lap_l=RACE_BURN, lap_time_ms=None,
                     planned_lap_time_ms=None, current_stops=0)
    assert verdict.offered is False
    assert "Recommend" not in verdict.call()
    # And beyond what a save covers it is still arithmetic, and urgent.
    short = assess(laps_done=11, laps_total=14, fuel_l=11.40,
                   planned_fuel_per_lap=PRACTICE_BURN,
                   observed_fuel_per_lap_l=RACE_BURN, lap_time_ms=None,
                   planned_lap_time_ms=None, current_stops=0)
    assert short.verdict == URGENT


def test_a_stop_withdrawn_for_a_save_is_not_announced_as_fuel_reaching():
    """The register's "Fuel reaches the flag now" would be false here."""
    register = PlanRegister()
    register.consider(Replan(URGENT, "1.4 laps short of the flag on current "
                             "burn", stops=1, next_stop_lap=13,
                             laps_to_next_stop=1), lap=11)
    covered = assess(laps_done=12, laps_total=14, fuel_l=11.40,
                     planned_fuel_per_lap=PRACTICE_BURN,
                     observed_fuel_per_lap_l=RACE_BURN, lap_time_ms=None,
                     planned_lap_time_ms=None, current_stops=0)
    outcome = register.consider(covered, lap=12)
    assert not (outcome.spoken and "reaches" in outcome.verdict.call())
    # Only when the tank truly reaches is that said.
    reaches = assess(laps_done=13, laps_total=14, fuel_l=7.43,
                     planned_fuel_per_lap=PRACTICE_BURN,
                     observed_fuel_per_lap_l=RACE_BURN, lap_time_ms=None,
                     planned_lap_time_ms=None, current_stops=0)
    assert reaches.verdict == NONE


def test_the_burn_coming_back_under_the_flag_is_said_once():
    state = lap_12()
    state.record(next_call(state))
    state.lap, state.fuel_l, state.laps_to_go_estimate = 13, 7.43, None
    call = next_call(state)
    assert call.kind == FUEL_REACHES
    assert call.call == "Fuel reaches the flag now."
    state.record(call)
    assert all(c is None or c.kind != FUEL_REACHES
               for c in (next_call(state),))


def test_a_plan_that_needs_a_save_says_how_much():
    """Tomorrow's shape: a one-stop plan, and a zero-stop that fits only if
    he saves. The lever and its size are what he hears, not a clause the
    spoken reason cuts off."""
    from pitcrew.tests.test_ptt_and_replan import an_inputs

    verdict = assess(laps_done=5, laps_total=20, fuel_l=50.0,
                     planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=3.42,
                     lap_time_ms=94_100, planned_lap_time_ms=94_000,
                     current_stops=1, inputs=an_inputs())
    assert verdict.offered and verdict.stops == 0
    assert verdict.spoken_reason().startswith("Save ")
    assert "litres a lap" in verdict.spoken_reason()


# ------------------------------------------------ 2. timed-race laps to go

def test_a_hedged_two_to_go_is_said_as_the_pair():
    state = RaceState(lap=13, laps_total=15, race_minutes=30.0,
                      laps_to_go_estimate=2, laps_count_hedged=True)
    call = _laps_to_go(state)
    assert call.call != "Two to go."
    assert call.call == "One or two to go."


def test_the_chase_count_carries_the_hedge():
    class Gap:
        seen = {11: 6.2}

    state = RaceState(lap=12, laps_total=15, race_minutes=30.0,
                      laps_count_hedged=True, gap_ahead=Gap(),
                      gap_ahead_name="Boxhead")
    call = _chase(state)
    assert "2 or 3 laps to go." in call.call


def replayed(upto: int):
    """Race 166 through the real coordinator, to the end of lap `upto`."""
    clock = {"s": 0.0}
    race = RaceCoordinator(None, fuel_per_lap_l=PRACTICE_BURN,
                           planned_fuel_per_lap_l=PRACTICE_BURN,
                           fuel_capacity_l=100.0, now=lambda: clock["s"])
    assert race.arm(None, None)
    race.state.race_minutes = 30.0
    race.clock = RaceClock(1800.0, now=lambda: clock["s"])
    race.handle(SessionEvent(EventKind.RACE_STARTED, {}))
    race.test_clock = clock
    calls = [drive_one(race, row) for row in LAPS[:upto]]
    return race, calls


def drive_one(race, row):
    num, secs, fuel_end, remaining = row
    fuel = LAPS[num - 2][2] if num > 1 else 100.0
    race.test_clock["s"] = 1800.0 - remaining
    lap = Lap(lap_num=num, lap_time_ms=int(secs * 1000),
              best_lap_ms=int(secs * 1000), delta_ms=0, fuel_start=fuel,
              fuel_end=fuel_end, fuel_used=round(fuel - fuel_end, 2),
              position=5, is_pit_lap=False, is_out_lap=False)
    return race.handle(SessionEvent(EventKind.LAP_COMPLETED, {"lap": lap}))


def test_the_last_lap_of_the_race_is_not_called_two_to_go():
    race, calls = replayed(13)
    said = [c.call for c in calls if c is not None and c.kind == LAPS_TO_GO]
    assert "Two to go." not in said[-1:]
    call = _laps_to_go(race.state)
    assert call is None or call.call != "Two to go."


def test_a_lap_driven_under_a_save_counts_in_the_projection():
    """Asked to save on lap 12, he lifts: lap 13 is 132.9 against a 126.7
    median, and 128.4 s left is ONE lap at that pace, not two."""
    race, _ = replayed(12)
    # The save is asked on lap 12's crossing, whatever the count said then.
    race.note_save_asked(12)
    drive_one(race, LAPS[12])
    assert race.state.laps_remaining() == 1
    call = _laps_to_go(race.state)
    assert call is not None and call.call == "Last lap."


def test_an_off_with_no_save_asked_does_not_shorten_the_race():
    """Lap 10 was an off, not a lift. The median stands."""
    race, _ = replayed(10)
    race._save_asked_lap = None
    assert race.projected_lap_ms() == race.expect.achieved_lap_time_ms()
    race.note_save_asked(8)
    assert race.projected_lap_ms() > race.expect.achieved_lap_time_ms()


# --------------------------------------------------- 3. why it was spoken

def urgent(lap: int, next_stop: int) -> Replan:
    return Replan(URGENT, "short of the flag", stops=1,
                  next_stop_lap=next_stop, laps_to_next_stop=next_stop - lap)


def test_a_stop_that_has_not_moved_is_not_announced_as_moved():
    """Laps 1, 4, 9, 12: the stop sat on 11, 11, 13, 13."""
    register = PlanRegister()
    assert register.consider(urgent(1, 11), lap=1).spoken
    for lap, stop in ((4, 11), (9, 13), (12, 13)):
        outcome = register.consider(urgent(lap, stop), lap=lap)
        assert outcome.spoken is False, (lap, outcome.why)


def test_a_stop_that_has_moved_says_by_how_much():
    register = PlanRegister()
    register.consider(urgent(1, 11), lap=1)
    outcome = register.consider(urgent(2, 16), lap=2)
    assert outcome.spoken
    assert outcome.why == "the stop has moved 5 laps later"
