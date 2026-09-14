"""The box call is made on the IN-LAP, not the lap after it.

Bathurst, 14 Sep 2026 (session 176, race run 21, strategy 31): the plan put
the stop on lap 11 (`pit_laps` [11], stint 1 laps 1-11). `laps_to_stop()`
counts the laps still to drive INCLUDING the in-lap, so with ten laps done it
is 1 - and `_box_now` fired only at 0, so "Box this lap" went out with eleven
laps done, named lap 12, and he pitted at the end of lap 12. The driver board
said "plan: lap 12". The verdict read "acted". Race runs 3, 4, 9, 14, 17 and
21 all stopped one lap after the plan's lap; on the plan's 91 L load a car
that does that runs dry.

One definition now, named in `RaceState.laps_to_stop` and rendered by
`calls.box_when`: N is the laps still to drive to the box. 1 is "Box this
lap.", 2 is "Box next lap.", N is "Box in N laps." - and the countdown's
"N laps to the stop." is the same N.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.engineer.intents import BOX_WHEN, PLAN, answer
from pitcrew.race.call_outcome import ACTED, NOT_ACTED, outcome_for
from pitcrew.race.calls import (BOX_NOW, BOX_SOON, RaceState, box_when,
                                next_call, _box_now, _laps_after_this_stop)

IN_LAP = 11                    # Bathurst's plan: pit_laps [11]


def bathurst(lap: int, **kw) -> RaceState:
    fields = dict(lap=lap, laps_total=20, stint_ends_on_lap=IN_LAP,
                  next_compound="RS", next_tyres=True,
                  mandatory_stops_left=None)
    fields.update(kw)
    return RaceState(**fields)


@dataclass
class _Lap:
    lap_num: int
    is_pit_lap: bool = False


def _race(pit_on: int, count: int = 20):
    return [_Lap(n, is_pit_lap=(n == pit_on)) for n in range(1, count + 1)]


# ------------------------------------------------------------ the ladder

def test_the_ladder_is_one_count():
    assert box_when(0) == "Box this lap."          # overdue
    assert box_when(1) == "Box this lap."
    assert box_when(2) == "Box next lap."
    assert box_when(3) == "Box in 3 laps."
    assert box_when(7) == "Box in 7 laps."


def test_box_this_lap_is_said_with_ten_laps_done_for_a_plan_stop_on_11():
    """The exact sequence a plan in-lap of 11 speaks, crossing by crossing.
    `lap` is laps COMPLETED, so lap 10 done is the crossing that starts lap
    11 - the in-lap."""
    heard = {}
    state = bathurst(0)
    for done in range(6, 13):
        state.lap = done
        call = next_call(state)
        if call is not None and call.kind in (BOX_NOW, BOX_SOON):
            heard[done] = call.call
            state.record(call)
    assert heard == {
        8: "Box in 3 laps.",
        9: "Box next lap.",
        10: "Box this lap. RS on.",
        # He drove past it: the in-lap is done and he is still out.
        11: "Box this lap. RS on.",
        12: "Box this lap. RS on.",
    }
    state.lap = 11
    assert _box_now(state).reason.startswith("1 lap overdue.")


def test_the_countdown_and_the_ladder_say_the_same_number():
    """Rule 13: "3 laps to the stop." and "Box in 3 laps." on one crossing
    are one claim. They were a lap apart."""
    state = bathurst(8)
    assert state.laps_to_stop() == 3
    assert box_when(state.laps_to_stop()) == "Box in 3 laps."


def test_on_the_in_lap_the_stop_is_due_and_not_late():
    state = bathurst(10)
    assert state.laps_to_stop() == 1
    assert state.laps_overdue() == 0
    assert state.past_box_lap is False
    state.lap = 11
    assert state.laps_to_stop() == 0
    assert state.laps_overdue() == 1
    assert state.past_box_lap is True
    assert bathurst(9).laps_overdue() is None


# ------------------------------------------------------------- the board

def test_the_board_names_the_plans_lap_not_the_lap_after_it():
    for done in (3, 8, 10):
        assert bathurst(done).box_lap_on_screen() == IN_LAP
    # Late, it stays the plan's lap rather than walking with the race.
    assert bathurst(12).box_lap_on_screen() == IN_LAP


def test_a_missed_crossing_moves_the_board_lap_with_the_hud():
    """The app's count is one light after a crossing lost in the lane; the
    stop the app calls lands one real lap later, and the HUD shows that."""
    state = bathurst(9, laps_dropped_seen=1)
    assert state.lap_on_screen() == 11
    assert state.box_lap_on_screen() == 12


# ------------------------------------------------------------ push-to-talk

def test_push_to_talk_says_the_ladder_the_voice_says():
    for done, said in ((8, "Box in 3 laps."), (9, "Box next lap."),
                       (10, "Box this lap."), (11, "Box this lap.")):
        snapshot = {"hasPlan": True,
                    "lapsToStop": bathurst(done).laps_to_stop()}
        assert answer(BOX_WHEN, snapshot).text == said, done
    assert answer(PLAN, {"hasPlan": True, "lapsToStop": 2}).text.startswith(
        "Box next lap")


# ---------------------------------------------------------------- verdicts

def _the_box_call():
    call = _box_now(bathurst(10))
    assert call is not None
    assert (call.box_lap, call.plan_box_lap) == (IN_LAP, IN_LAP)
    return call


def test_stopping_at_the_end_of_lap_11_is_on_plan():
    outcome = outcome_for(_the_box_call(), _race(pit_on=11))
    assert outcome.verdict == ACTED
    assert outcome.laps_late == 0
    assert "on the plan's lap" in outcome.detail


def test_stopping_at_the_end_of_lap_12_is_one_lap_late():
    outcome = outcome_for(_the_box_call(), _race(pit_on=12))
    assert outcome.verdict == ACTED
    assert outcome.laps_late == 1
    assert "one lap late against the plan's lap 11" in outcome.detail


def test_the_lap_the_call_was_said_on_cannot_answer_it():
    """Said on the crossing that closed lap 10, so lap 10 was already driven.
    The window judged from it, and a pit lap there read as compliance."""
    outcome = outcome_for(_the_box_call(), _race(pit_on=10))
    assert outcome.verdict == NOT_ACTED
    assert "11-12" in outcome.detail


def test_a_box_in_3_is_judged_against_the_lap_it_named():
    call = next_call(bathurst(8))
    assert call.call == "Box in 3 laps." and call.box_lap == IN_LAP
    on_time = outcome_for(call, _race(pit_on=11))
    assert on_time.verdict == ACTED and on_time.laps_late == 0
    assert outcome_for(call, _race(pit_on=13)).verdict == NOT_ACTED


# ------------------------------------------- where the line sits in the lane

def test_crossing_in_the_box_makes_no_box_call_and_sizes_the_out_lap():
    """Daytona and Spa cross the line in the lane before the box: the
    crossing that closes the in-lap arrives with the car in the pit, where
    nothing about boxing is said, and the lap in progress is the out-lap -
    covered in full."""
    state = bathurst(IN_LAP, in_pit=True, crossed_in_box=True)
    assert _box_now(state) is None
    assert _laps_after_this_stop(state) == 20 - IN_LAP


def test_line_after_the_box_takes_the_in_lap_off_the_fill():
    """Deep Forest and Monza: in the box the in-lap has not been closed, it is
    mostly behind the car, and the fill covers the laps after it - the same
    count the box call named on the crossing that started the in-lap."""
    in_box = bathurst(IN_LAP - 1, in_pit=True)
    at_the_call = bathurst(IN_LAP - 1)
    assert _laps_after_this_stop(in_box) == 20 - IN_LAP
    assert _laps_after_this_stop(at_the_call) == 20 - IN_LAP


def test_the_plan_of_the_night_arms_its_in_lap_as_the_stop():
    """Strategy 31 as stored: stint 1 laps 1-11, stint 2 from lap 12,
    `pit_laps` [11]. The in-lap the coordinator arms is the plan's pit lap."""
    from pitcrew.race.coordinator import RaceCoordinator

    plan = {"pit_laps": [11], "stints": [
        {"laps": 11, "compound": "RS", "fuel_l": 91.08, "start_lap": 1},
        {"laps": 9, "compound": "RS", "fuel_l": 74.14, "start_lap": 12,
         "tyres": True}]}
    race = RaceCoordinator(plan)
    assert race.state.stint_ends_on_lap == plan["pit_laps"][0]
    race.state.lap = 10
    assert race.state.laps_to_stop() == 1
    assert race.state.box_lap_on_screen() == 11
