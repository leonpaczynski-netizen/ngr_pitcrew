"""Phase 1 row 1.8 - the five things the driver board could not say.

**Every test here is written against a state the board could mislead him
with**, not against a happy path: two fuel numbers that could be the same
number twice, a split whose sign he would have to decode at 200 km/h, a call
whose register the screen and the voice could disagree about, a lap number his
HUD would never show him, and a position of zero.

The fuel arithmetic is exercised on a real `RaceState` rather than on a stub.
`race/calls.py` is where it lives and where it has already been wrong once, in
the way `fuel_in_hand_to_flag`'s docstring records: **"-7.1 laps of fuel in
hand to the flag" spoken with 84.0 L aboard and the stop nine laps away.**
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pitcrew.race.calls import (  # noqa: E402
    HIGH,
    LOW,
    MARK_INSTRUCTION,
    MARK_SUGGESTION,
    MARK_UNCONFIRMED,
    STAY_OUT,
    TO_THE_FLAG,
    TO_THE_STOP,
    BOX_NOW,
    Call,
    RaceState,
    fuel_frame,
    fuel_in_hand,
    fuel_in_hand_to_flag,
    fuel_in_hand_to_stop,
)
from pitcrew.race.tyre_split import SplitHistory  # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    """One QApplication for the file, torn down with the session.

    **Built here rather than on demand inside each test.** A QApplication
    created and abandoned inside a test function is what produced the
    0xC0000409 in PyQt teardown while this file was being written - the same
    class of fault CLAUDE.md 7 records against the module-scope wheel guard,
    and it is a product of the harness rather than of the code under test.
    """
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _race(**kwargs) -> RaceState:
    """A 20-lap race with one stop on lap 11, at the Daytona event's numbers.

    Deliberately the shape of the race that produced the -7.1: 20 laps, one
    mandatory stop, a plan whose box lap is nine laps ahead of the crossing
    the figure was spoken on.
    """
    state = RaceState()
    state.laps_total = 20
    state.lap = 2
    state.fuel_l = 84.0
    state.fuel_per_lap_l = 4.19
    state.fuel_capacity_l = 100.0
    state.stint_ends_on_lap = 11
    state.further_stop_planned = False
    state.mandatory_stops_left = 1
    for key, value in kwargs.items():
        setattr(state, key, value)
    return state


# ------------------------------------------------- fuel, as TWO numbers

def test_the_flag_figure_no_longer_forgets_the_litres_the_stop_adds():
    """**The defect this whole item exists for.** Session 127, Daytona, lap 2:
    *"-7.1 laps of fuel in hand to the flag"* with 84 L aboard and the box
    nine laps away. The old expression divided the tank by the burn and
    subtracted the laps to the FLAG, with no term for the fill.

    84 L at 4.19 is 20.0 laps against 18 remaining, so the tank alone is
    already ahead - and once the stop's fill is counted the figure is the
    plan's own margin, comfortably positive. It is emphatically not -7.
    """
    state = _race()
    to_flag, why = fuel_in_hand_to_flag(state)
    assert why is None
    assert to_flag is not None and to_flag > 0, to_flag
    # And the old arithmetic, reproduced here, is what it is NOT.
    old = state.fuel_l / state.fuel_per_lap_l - state.laps_remaining()
    assert to_flag != pytest.approx(old)


def test_the_two_numbers_are_different_questions_and_say_so():
    """A stop nine laps away and a flag eighteen laps away are not one
    number. The stop figure is the tank against the box; the flag figure
    counts the fill."""
    state = _race()
    to_stop, _ = fuel_in_hand_to_stop(state)
    to_flag, _ = fuel_in_hand_to_flag(state)
    # 84 / 4.19 = 20.0 laps aboard, 9 laps to the box.
    assert to_stop == pytest.approx(11.0, abs=0.1)
    assert to_flag != to_stop


def test_the_stop_figure_is_the_expression_the_voice_speaks():
    """Rule 13, and it is enforced by identity rather than by agreement: the
    board's stop number IS `fuel_in_hand`, which is what the driver hears as
    "N laps of fuel in hand to the stop"."""
    state = _race()
    spoken, reference = fuel_in_hand(state)
    assert reference == TO_THE_STOP
    assert fuel_in_hand_to_stop(state)[0] == spoken


def test_with_no_stop_left_the_flag_figure_is_the_one_the_voice_speaks():
    """Once the stop is gone there is no fill to count, and the board must
    not invent one. Same expression as the voice, which is now saying "to the
    flag" about the same tank."""
    state = _race(stint_ends_on_lap=None)
    spoken, reference = fuel_in_hand(state)
    assert reference == TO_THE_FLAG
    assert fuel_in_hand_to_flag(state) == (spoken, None)
    assert fuel_in_hand_to_stop(state) == (None, "no stop still to come")


def test_past_the_box_lap_the_flag_figure_is_the_tank_alone():
    """**And the two must not disagree about which frame they are in.**
    `fuel_frame` says the flag once the box lap has gone by - he is running
    on this fuel until he actually stops - so the board counts no fill
    either, and its stop figure says which of the reasons it is a dash."""
    state = _race(lap=13)
    assert fuel_frame(state)[1] == TO_THE_FLAG
    to_stop, why = fuel_in_hand_to_stop(state)
    assert to_stop is None
    assert why == "past the box lap - the tank is the whole supply"
    assert fuel_in_hand_to_flag(state)[0] == fuel_in_hand(state)[0]


def test_a_tank_that_does_not_reach_the_box_refuses_rather_than_clamps():
    """CLAUDE.md rule 9. A negative arrival is a reading whose reference is
    wrong, not a tank with nothing in it, and a flag figure computed from it
    would be a confident wrong answer about a race he never gets to."""
    state = _race(fuel_l=8.0)
    to_flag, why = fuel_in_hand_to_flag(state)
    assert to_flag is None
    assert why == "this tank does not reach the box"
    # The stop figure still answers, and its answer is the bad news: nine
    # laps to the box on 1.9 laps of fuel.
    to_stop, _ = fuel_in_hand_to_stop(state)
    assert to_stop is not None and to_stop < 0


def test_a_fill_the_tank_cannot_hold_makes_the_figure_negative():
    """**The finding, and it is the whole reason the flag number exists.** A
    one-stop plan whose second stint needs more than the tank holds does not
    reach, and the board says so in laps rather than silently sizing a fill
    nobody can take."""
    state = _race(fuel_capacity_l=30.0, fuel_l=25.0, lap=9,
                  stint_ends_on_lap=10)
    to_flag, why = fuel_in_hand_to_flag(state)
    assert why is None
    assert to_flag is not None and to_flag < 0, to_flag


def test_another_stop_after_this_one_is_refused_not_guessed():
    """The laps after the NEXT stop ride on a fill nothing has sized, so a
    figure here would be a claim about a stop the app has not costed."""
    state = _race(further_stop_planned=True)
    assert fuel_in_hand_to_flag(state) == (None, "another stop after this one")
    # And unknown refuses for the same reason: `further_stop_planned` is None
    # where nobody said, and an unknown is not a no.
    assert fuel_in_hand_to_flag(_race(further_stop_planned=None))[1] == \
        "another stop after this one"


def test_a_missing_input_is_named_rather_than_pooled():
    """"No burn measured yet" said about a missing tank reading is a wrong
    answer wearing a right one's clothes."""
    assert fuel_in_hand_to_flag(_race(fuel_per_lap_l=None))[1] == \
        "no burn measured yet"
    assert fuel_in_hand_to_flag(_race(fuel_l=None))[1] == "no fuel reading"
    assert fuel_in_hand_to_flag(_race(laps_total=None))[1] == \
        "the race length is not known"


def test_a_stop_at_or_past_the_flag_is_refused():
    """A plan whose box lap is the last lap leaves no laps for the fill to
    cover, and dividing by that produces a figure about nothing."""
    state = _race(stint_ends_on_lap=20)
    assert fuel_in_hand_to_flag(state)[1] == \
        "the plan's stop is at or past the flag"


# --------------------------------------------- the mark, spoken and printed

def test_the_printed_mark_and_the_spoken_suffix_are_one_decision():
    """Rule 12. The suffix `spoken()` appends is built from `mark()`, so a
    call cannot be an instruction in his ear and a suggestion on the screen.
    """
    ordered = Call(BOX_NOW, 4, "Box this lap.", "Fuel to 63.")
    assert ordered.mark() == MARK_INSTRUCTION
    assert not ordered.spoken().endswith("Suggestion.")
    assert not ordered.spoken().endswith("Unconfirmed.")

    offered = Call(STAY_OUT, 4, "Stay out.", "")
    assert offered.mark() == MARK_SUGGESTION
    assert offered.spoken().endswith("Suggestion.")

    unsure = Call(BOX_NOW, 4, "Box this lap.", "", confidence=LOW)
    assert unsure.mark() == MARK_UNCONFIRMED
    assert unsure.spoken().endswith("Unconfirmed.")


def test_unconfirmed_outranks_suggestion_on_the_screen_as_in_the_ear():
    """"I am not sure this is true" outranks "I am not telling you to do it",
    and the two outputs must rank them the same way."""
    call = Call(STAY_OUT, 4, "Stay out.", "", confidence=LOW)
    assert call.mark() == MARK_UNCONFIRMED
    assert call.spoken().endswith("Unconfirmed.")
    assert "Suggestion." not in call.spoken()


def test_a_high_confidence_call_is_marked_and_carries_no_suffix():
    """An instruction is the default and says nothing extra in the ear (§5.5,
    one thing at a time) - but the board names it, because a driver who
    cannot tell an order from an offer treats every line as one or the
    other."""
    call = Call(BOX_NOW, 6, "Box this lap.", "", confidence=HIGH)
    assert call.mark() == MARK_INSTRUCTION
    assert call.spoken() == "Box this lap."


# ------------------------------------------------------------- the splits

def _lap(fl, fr, rl, rr):
    return {"fl": fl, "fr": fr, "rl": rl, "rr": rr}


def test_the_axle_split_is_signed_because_both_directions_are_findings():
    """Rears hotter is a rear-limited car and fronts hotter is a front-limited
    one - CLAUDE.md 5.5's own example call is the second of those. The
    left-right split is positive-only for the opposite reason: those two
    tyres are interchangeable."""
    history = SplitHistory()
    history.note_lap(_lap(62.5, 65.6, 73.2, 75.7))
    assert history.axle_split_now() == pytest.approx(10.4)

    fronts = SplitHistory()
    fronts.note_lap(_lap(90.0, 90.0, 80.0, 80.0))
    assert fronts.axle_split_now() == pytest.approx(-10.0)


def test_the_axle_split_is_none_before_a_lap_and_never_a_zero():
    assert SplitHistory().axle_split_now() is None
    assert SplitHistory().axle_rate() == (None, 0)


def test_the_axle_trend_needs_five_laps_and_has_to_clear_the_floor():
    """Three points is a slope through noise. And a movement inside the
    derived floor is `None` - not a rate of zero, which the board would draw
    as "settling"."""
    creeping = SplitHistory()
    for lap in range(6):
        # 0.2 degC a lap: real, and under RATE_WORTH_SAYING_C.
        creeping.note_lap(_lap(70.0, 70.0, 75.0 + 0.2 * lap, 75.0))
    rate, laps = creeping.axle_rate()
    assert rate is None and laps == 6

    running = SplitHistory()
    for lap in range(6):
        running.note_lap(_lap(70.0, 70.0, 75.0 + 3.0 * lap, 75.0))
    rate, laps = running.axle_rate()
    assert rate is not None and rate > 0 and laps == 6


def test_a_lap_missing_a_corner_is_dropped_from_the_axle_series_too():
    """Three corners cannot make an axle mean, and a part-filled lap in the
    middle of a series is fitted straight through as though it were
    measured."""
    history = SplitHistory()
    history.note_lap(_lap(70.0, 70.0, 80.0, 80.0))
    history.note_lap({"fl": 70.0, "fr": None, "rl": 80.0, "rr": 80.0})
    assert len(history.laps) == 1


# ----------------------------------------------- the board, as it renders

def test_the_board_words_the_axle_direction_and_never_shows_a_sign(qt_app):
    from pitcrew.ui.driver_view import DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(axle_split_c=12.15, axle_split_rate=1.42,
                                  split_laps=8))
    assert view.axle_stat.value.text() == "12.2"
    assert view.axle_stat.caption.text() == "REAR OVER FRONT"
    assert "widening" in view.axle_stat.sub.text()
    assert "8 laps" in view.axle_stat.sub.text()

    # The other way round: the same magnitude, the opposite diagnosis, and
    # still no minus sign on the screen.
    view.update_state(DriverState(axle_split_c=-12.15, axle_split_rate=-1.42,
                                  split_laps=8))
    assert view.axle_stat.value.text() == "12.2"
    assert view.axle_stat.caption.text() == "FRONT OVER REAR"
    # **Widening, not settling.** The rate is the slope of rear-minus-front,
    # so a front gap running away has a NEGATIVE rate - reading the raw sign
    # would have said "settling" at the moment it was going.
    assert "widening" in view.axle_stat.sub.text()


def test_a_split_with_no_trend_claims_none_and_still_says_how_many_laps(qt_app):
    from pitcrew.ui.driver_view import DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(axle_split_c=4.0, axle_split_rate=None,
                                  rear_pair_hotter="rl",
                                  rear_pair_split_c=1.5, split_laps=3))
    assert view.axle_stat.sub.text() == "3 laps"
    assert "settling" not in view.axle_stat.sub.text()
    assert "widening" not in view.axle_stat.sub.text()
    assert view.rear_pair_stat.caption.text() == "RL OVER RR"


def test_the_split_caption_says_the_floor_is_derived(qt_app):
    """CLAUDE.md rule 5: nothing derived is presented as measured, and
    `RATE_WORTH_SAYING_C` is derived from an instrument-noise argument rather
    than measured."""
    from pitcrew.ui.driver_view import DriverView

    # **The view is held.** `DriverView().split_caption` drops the parent on
    # the same line, Qt deletes the C++ object under the label, and the read
    # raises "wrapped C/C++ object has been deleted" - the same shape of
    # fault CLAUDE.md 7 records against the module-scope wheel guard.
    view = DriverView()
    caption = view.split_caption.text().lower()
    assert "derived" in caption
    assert "1.25" in caption


def test_the_last_call_line_prints_the_sentence_the_mark_and_the_lap(qt_app):
    from pitcrew.ui.driver_view import BoardCall, DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(last_call=BoardCall(
        text="Box this lap. Fuel to 63.", mark=MARK_INSTRUCTION, lap=11)))
    assert "Box this lap." in view.last_call.line.text()
    assert view.last_call.line.text().startswith("L11")
    assert view.last_call.mark.text() == "INSTRUCTION"

    # Nothing said yet is blank rather than a dash: it is the ordinary state
    # of the first laps of every race and needs no explaining.
    view.update_state(DriverState())
    assert view.last_call.line.text() == ""
    assert view.last_call.mark.text() == ""


def test_an_unconfirmed_call_is_the_only_mark_with_an_ink_of_its_own(qt_app):
    from pitcrew.ui.driver_view import BoardCall, DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(last_call=BoardCall(
        text="Possible penalty served.", mark=MARK_UNCONFIRMED, lap=4)))
    warned = view.last_call.mark.styleSheet()
    view.update_state(DriverState(last_call=BoardCall(
        text="Stay out.", mark=MARK_SUGGESTION, lap=4)))
    assert view.last_call.mark.styleSheet() != warned


def test_a_call_with_no_lap_prints_no_lap_rather_than_lap_zero(qt_app):
    """Rule 3. Lap 0 is not a lap he drove, and a board row filed under it is
    exactly the defect critic pass 8 found in the call ledger."""
    from pitcrew.ui.driver_view import BoardCall, DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(last_call=BoardCall(
        text="Green.", mark=MARK_INSTRUCTION, lap=None)))
    assert view.last_call.line.text() == "Green."


def test_the_tyre_decision_reaches_him_before_he_is_stationary(qt_app):
    """`state.next_tyres` was rendered only inside the box panel, so he read
    the plan's tyre decision once he was already stopped and executing it."""
    from pitcrew.ui.driver_view import DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(laps_to_box=4, box_on_lap=11,
                                  tyres_at_stop=False, compound="RS"))
    assert "no tyres" in view.box_stat.sub.text()
    view.update_state(DriverState(laps_to_box=4, box_on_lap=11,
                                  tyres_at_stop=True, compound="RS"))
    assert "RS on" in view.box_stat.sub.text()
    # **A plan that did not say is silent.** "Fuel only" and "the plan is
    # quiet about it" are different answers and only one is a decision.
    view.update_state(DriverState(laps_to_box=4, box_on_lap=11,
                                  tyres_at_stop=None, compound="RS"))
    assert view.box_stat.sub.text() == "plan: lap 11"
