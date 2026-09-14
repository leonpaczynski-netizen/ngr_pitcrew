"""The cancelled stop, held (carried from row 1.10, plan §9a).

"The retirement of a cancelled stop has no latch, so a burn median that
moves back across the margin makes the countdown vanish and return - rule
10's shape."

**Redesigned after critic 4 on batch 4.** The first version latched the
retirement when he was told and needed two laps to bring the stop back - but
only one to take it off again, so a burn going short, short, long cycled the
two calls aloud; and it latched `laps_to_stop()` alone, so four other
surfaces read the unlatched arithmetic. Now the fuel's answer about the stop
is HELD in `_stop_needed_on_fuel`, which every consumer asks, and it moves
only after `STOP_FLIP_LAPS` consecutive laps of contrary arithmetic, in
either direction. Each change is said, and makes the opposite call sayable
again.

**And it starts from the plan's answer** (critic 4 on the redesign): a stop
the plan put there is held until the full run retires it, so taking it off
costs `STOP_FLIP_LAPS` at the green, after a stop and after a re-plan too.

Unreachable on every plan on file today (none grants `drop_stop`).
"""
from __future__ import annotations

from pitcrew.race import calls as C
from pitcrew.race.calls import (STOP_BACK, STOP_FLIP_LAPS, STOPS_OFF,
                                RaceState, next_call, stop_still_needed)


def _fuelled(**over) -> RaceState:
    """A fuel-bound one-stop, drop granted, carrying enough to the flag."""
    fields = dict(lap=8, laps_total=20, stint_ends_on_lap=10, fuel_l=60.0,
                  fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
                  plan_binding_constraint="fuel", mandatory_stops_left=0,
                  drop_stop_granted=True)
    fields.update(over)
    return RaceState(**fields)


def _judge(state, laps=1):
    for _ in range(laps):
        state.note_stop_need()


def _retired(**over) -> RaceState:
    state = _fuelled(**over)
    _judge(state, STOP_FLIP_LAPS)
    assert state.stop_needed_held is False
    return state


def test_before_any_lap_is_judged_the_plans_stop_stands():
    """The tank already reaches, but nothing has been judged: every surface
    reads the plan's stop, not the arithmetic of this instant."""
    state = _fuelled()
    assert stop_still_needed(state) is True
    assert state.laps_to_stop() == 2


def test_the_first_judged_lap_does_not_retire_the_plans_stop():
    """Critic 4 on the redesign, MAJOR: the hold started empty, so the first
    judged lap set it outright and retiring cost one lap - at the green,
    after a stop, after a re-plan - where bringing it back cost two."""
    state = _fuelled()
    _judge(state)
    assert state.stop_needed_held is True, "one lap does not take it off"
    assert state.laps_to_stop() == 2
    call = next_call(state)
    assert call is None or call.kind != STOPS_OFF
    _judge(state, STOP_FLIP_LAPS - 1)
    assert state.stop_needed_held is False
    assert state.laps_to_stop() is None
    call = next_call(state)
    assert call is not None and call.kind == STOPS_OFF


def test_one_contrary_lap_moves_nothing():
    state = _retired()
    state.fuel_per_lap_l = 6.0
    _judge(state)
    assert state.stop_needed_held is False
    assert state.laps_to_stop() is None, "one contrary lap is not a reversal"


def test_a_sustained_reversal_brings_the_stop_back_and_says_so():
    state = _retired()
    state.record(next_call(state))                  # "You're fuelled..."
    state.fuel_per_lap_l = 6.0
    _judge(state, STOP_FLIP_LAPS)
    assert state.laps_to_stop() == 2
    call = next_call(state)
    assert call is not None and call.kind == STOP_BACK
    # Two laps to drive to the box is "Box next lap." - `box_when`'s ladder.
    assert call.call == "The stop is back on. Box next lap."
    assert call.reason == "Fuel won't reach the flag."
    state.record(call)
    again = next_call(state)
    assert again is None or again.kind != STOP_BACK


def test_each_reversal_is_said_every_time_it_happens():
    """Pins the four guards that survived critic 4's mutation sweep: a
    reinstatement makes "fuelled to the flag" sayable again (`stops_off_said`
    and `said`), and a retirement makes "the stop is back on" sayable again.
    Off, on, off, on - each told, none twice in a row."""
    state = _retired()
    kinds = []
    for rate in (6.0, 3.0, 6.0):
        call = next_call(state)
        assert call is not None
        kinds.append(call.kind)
        state.record(call)
        state.fuel_per_lap_l = rate
        _judge(state, STOP_FLIP_LAPS)
    call = next_call(state)
    assert call is not None
    kinds.append(call.kind)
    assert kinds == [STOPS_OFF, STOP_BACK, STOPS_OFF, STOP_BACK]


def test_a_stop_retired_again_before_he_was_told_it_was_back_is_not_said_back():
    """The other surviving mutant: `stop_back_due` left set by a retirement
    would say "The stop is back on." about a stop that is off again."""
    state = _retired()
    state.record(next_call(state))                  # "You're fuelled..."
    state.fuel_per_lap_l = 6.0
    _judge(state, STOP_FLIP_LAPS)
    assert state.stop_back_due is True
    state.fuel_per_lap_l = 3.0
    _judge(state, STOP_FLIP_LAPS)
    assert state.stop_back_due is False
    call = next_call(state)
    assert call is None or call.kind != STOP_BACK


def test_retiring_again_needs_the_same_run_it_took_to_come_back():
    """The BLOCKER: one lap to take the stop off, two to put it back, and the
    calls cycled. Symmetric now."""
    state = _retired()
    state.fuel_per_lap_l = 6.0
    _judge(state, STOP_FLIP_LAPS)
    state.record(next_call(state))                  # "The stop is back on."
    state.fuel_per_lap_l = 3.0
    _judge(state)
    assert state.stop_needed_held is True, "one lap does not take it off"
    _judge(state)
    assert state.stop_needed_held is False
    call = next_call(state)
    assert call is not None and call.kind == STOPS_OFF, (
        "told it was back on, he must be told again when it is off")


def test_a_reversal_that_does_not_last_resets_the_count():
    state = _retired()
    for rate in (6.0, 3.0, 6.0):
        state.fuel_per_lap_l = rate
        _judge(state)
    assert state.laps_to_stop() is None, "the run has to be consecutive"


def test_every_consumer_reads_the_held_answer():
    """Critic 4, MAJOR: four surfaces read the arithmetic directly. The hold
    is in `_stop_needed_on_fuel`, so `stop_still_needed` - which the colour
    tier, the board and the rival calls read - agrees with the countdown
    through a contrary lap."""
    state = _retired()
    state.fuel_per_lap_l = 6.0
    _judge(state)                                  # one contrary lap
    assert stop_still_needed(state) is False
    assert state.laps_to_stop() is None


def test_the_box_call_gives_the_reason_of_the_answer_that_boxed_him():
    """Critic 4 on the redesign, MAJOR (rule 12): the hold kept the stop and
    the reason came from the arithmetic, so on the box lap he heard "Box this
    lap." because "Fuel is fine - the tank covers the next stint.". A held
    stop the tank no longer needs is the plan's stop."""
    state = _fuelled(lap=9)                        # the in-lap
    _judge(state)                                  # held, not yet retired
    assert C._why_the_stop_stands(state) is None, "the tank reaches"
    call = C._box_now(state)
    assert call is not None and call.call.startswith("Box this lap.")
    assert call.reason.startswith("On the plan."), call.reason
    soon = C._box_soon(_fuelled(lap=8))
    assert soon is not None and soon.reason == "Stop 1, on the plan."


def test_a_retired_stop_is_not_argued_against():
    """Critic 4's minor: the stay-out argument read the raw box lap, so a
    stop the fuel had retired was still "in question"."""
    from pitcrew.race.rival_calls import _a_stop_is_in_question

    state = _fuelled(lap=9)
    assert _a_stop_is_in_question(state) is True
    _judge(state, STOP_FLIP_LAPS)
    assert _a_stop_is_in_question(state) is False


def test_a_stop_back_on_its_box_lap_is_a_box_call():
    """Critic 4, MAJOR: reinstated on the box lap it said "The stop is back
    on." and the lap went by with no instruction to box."""
    state = _retired(lap=9)                        # the in-lap
    state.fuel_per_lap_l = 6.0
    _judge(state, STOP_FLIP_LAPS)
    call = next_call(state)
    assert call is not None and call.kind == STOP_BACK
    assert call.call.startswith("The stop is back on. Box this lap.")


def test_a_stop_back_after_its_box_lap_is_due_now_not_overdue():
    """"Overdue" counts from when he was told, not from the lap he was told
    the stop was off."""
    state = _retired(lap=13)
    # 9 L a lap: seven laps left need 63 L and more against 60 aboard. At 6
    # the tank still reached, and nothing came back to test.
    state.fuel_per_lap_l = 9.0
    _judge(state, STOP_FLIP_LAPS)
    # The lap in progress - 13 done - becomes the in-lap.
    assert state.stint_ends_on_lap == 14
    call = next_call(state)
    assert call.call.startswith("The stop is back on. Box this lap.")


def test_a_stop_the_desk_did_not_let_him_drop_stands():
    """The rail withholds `drop_stop`: he hears the report form, and the stop
    stands - `stop_still_needed` is True whatever the fuel says."""
    state = _fuelled(drop_stop_granted=False)
    _judge(state, STOP_FLIP_LAPS)
    assert state.laps_to_stop() == 2


def test_a_stop_taken_clears_everything_for_the_next_one():
    """The hold belongs to the stop it judged. Batch 4 cleared the latch and
    left `stops_off_said`, so the next stop flickered and nothing about it
    could be said (critic 4, MAJOR). Cleared to the plan's answer: the next
    stop stands until the full run retires it."""
    from pitcrew.race.coordinator import RaceCoordinator

    plan = {"stints": [{"laps": 7, "start_lap": 1},
                       {"laps": 7, "start_lap": 8},
                       {"laps": 6, "start_lap": 15}],
            "binding_constraint": "fuel"}
    race = RaceCoordinator(plan, fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
                           planned_fuel_per_lap_l=3.0,
                           planned_lap_time_ms=90_000, mandatory_stops=0)
    state = race.state
    state.stop_needed_held = False
    state.stop_flip_laps = 1
    state.stop_back_due = True
    state.stops_off_said = True
    state.said.extend([STOPS_OFF, STOP_BACK])
    race._apply_stint(1, over_a_stop=True)
    assert state.stop_needed_held is None
    assert stop_still_needed(state) is True, "the next stop is the plan's"
    assert state.stop_flip_laps == 0
    assert state.stop_back_due is False
    assert state.stops_off_said is False
    assert STOPS_OFF not in state.said and STOP_BACK not in state.said
    assert state.stint_ends_on_lap == 14
