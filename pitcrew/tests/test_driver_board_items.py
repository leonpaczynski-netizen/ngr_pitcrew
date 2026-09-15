"""Phase 1 row 1.8 - the six things the driver board could not say.

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
from pathlib import Path

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
    already ahead - and once the refill is counted the figure is comfortably
    positive. It is emphatically not -7.
    """
    state = _race()
    to_flag, why, rests_on = fuel_in_hand_to_flag(state)
    assert why is None
    assert to_flag is not None and to_flag > 0, to_flag
    # 84 L reaches the box with more than the fill wants, so the supply that
    # bound it is his own tank and the caption says so.
    assert rests_on == "on the fuel aboard"

    # **And a state where the two expressions genuinely differ**, because in
    # the surplus branch above they do not: it reduces algebraically to the
    # old `tank / burn - laps to the flag`, so this test used to pass on
    # `round(x, 1)` alone (2.0 against 2.048) and would have survived the
    # whole expression being replaced by the defect it is named for.
    #
    # 45 L is 10.7 laps against 18 remaining, so the old expression says
    # **-7.3** - the shape of the figure spoken at Daytona. The fill is what
    # makes the honest answer positive.
    short = _race(fuel_l=45.0)
    old = short.fuel_l / short.fuel_per_lap_l - short.laps_remaining()
    assert old == pytest.approx(-7.3, abs=0.1), old
    got, why, rests_on = fuel_in_hand_to_flag(short)
    assert why is None
    assert got == pytest.approx(1.0, abs=0.05), got
    assert rests_on == "on the plan\'s fill"
    # ⚠️ **And that 1.0 is `FUEL_MARGIN_LAPS` exactly**, because `_race()`
    # measures no burn scatter - so the leg above discriminates the
    # expressions but lands on the app's own switch. This is the one where
    # the figure actually moves: a measured scatter sizes the margin on it.
    measured, why, _ = fuel_in_hand_to_flag(_race(fuel_l=45.0,
                                                  fuel_sd_l=0.15))
    assert why is None
    assert measured == pytest.approx(0.3, abs=0.05), measured


def test_the_two_numbers_are_different_questions_and_say_so():
    """A stop nine laps away and a flag eighteen laps away are not one
    number. The stop figure is the tank he is carrying against the box; the
    flag figure is the supply he will leave the box with against the run
    home."""
    state = _race()
    to_stop, _ = fuel_in_hand_to_stop(state)
    to_flag, _, _ = fuel_in_hand_to_flag(state)
    # 84 / 4.19 = 20.0 laps aboard, 9 laps to the box.
    assert to_stop == pytest.approx(11.0, abs=0.1)
    # **The surplus regime, and it is the honest one.** 84 L is more than
    # this stop needs: he reaches the box with 46.3 L against a fill sized at
    # 41.9, and the pump cannot take fuel out, so he leaves with what he
    # arrived with and finishes 2.0 laps to the good.
    assert to_flag == pytest.approx(2.0, abs=0.1)


def test_the_flag_figure_is_still_while_the_plan_works_and_moves_when_not():
    """**Both critic passes hit this figure, from opposite sides.**

    Pass one: it read a flat 1.0 at 45, 60, 84 and 95 litres aboard, so it
    could not move with the tank - an instrument reading our own switch back
    to us. Pass two, after it was replaced with the tank against the run
    home: it read 14.9 where the plan will actually leave 1.0, fourteen laps
    of daylight beside a stop figure of 6.1, and it stepped 17.8 laps across
    one crossing.

    It is the plan's fill again, and its sub-line says so. Sitting still IS
    the answer while the plan is working: a stop refills, so what he carries
    before it does not decide the run home. It is not a constant - with a
    measured burn scatter the margin is sized on that scatter - and it moves
    with a stop that slips, with a tank that cannot hold the fill, and with
    an arrival that already carries more than the plan wants.
    """
    # No measured scatter: the plan's flat lap, the same at any tank that
    # still reaches the box. That is the plan working, not a dead needle.
    assert fuel_in_hand_to_flag(_race(fuel_l=45.0))[0] == \
        fuel_in_hand_to_flag(_race(fuel_l=60.0))[0] == \
        pytest.approx(1.0, abs=0.05)
    # A measured scatter sizes a smaller margin, and the figure follows it.
    assert fuel_in_hand_to_flag(_race(fuel_l=45.0, fuel_sd_l=0.15))[0] < \
        fuel_in_hand_to_flag(_race(fuel_l=45.0))[0]
    # And arriving with more than the plan wants is a real surplus: the pump
    # cannot take fuel out.
    assert fuel_in_hand_to_flag(_race(fuel_l=95.0, lap=9))[0] > 5.0
    # It is not the tank aboard divided by anything: a car that arrives with
    # LESS than the fill wants gets the fill, not its own tank.
    assert fuel_in_hand_to_flag(_race(fuel_l=45.0))[0] < \
        fuel_in_hand_to_flag(_race(fuel_l=95.0, lap=9))[0]


def test_the_flag_figure_keeps_the_timed_race_hedge():
    """A timed race's distance is an OUTPUT of the plan, and `fuel_margin_l`
    prices that: while the lap count is not firm it carries a whole lap.
    Computing the figure without going through it dropped the hedge silently,
    and he would stay out on a margin sized for a race whose length was still
    moving."""
    # 45 L aboard, so the fill binds rather than the tank he arrives with -
    # a surplus arrival carries its own fuel past any margin the plan sizes.
    firm = fuel_in_hand_to_flag(_race(
        fuel_l=45.0, race_minutes=50.0, fuel_sd_l=0.15,
        laps_estimate_firm=True))[0]
    loose = fuel_in_hand_to_flag(_race(
        fuel_l=45.0, race_minutes=50.0, fuel_sd_l=0.15,
        laps_estimate_firm=False))[0]
    assert loose > firm


def test_the_flag_figure_names_the_supply_that_actually_bound_it():
    """**Rule 12, and it was broken exactly where the number moves.** The
    supply is the biggest of what he arrives with and what the plan fills to,
    capped by the tank - so a figure of 2.0 that came from a 84 L arrival was
    captioned `on the plan's fill` when the plan's fill leaves 1.0. The block
    moved only where its caption lied and told the truth only where it could
    not move, which is worse than either on its own.
    """
    # The ordinary case: the fill binds.
    assert fuel_in_hand_to_flag(_race(fuel_l=45.0))[2] == "on the plan's fill"
    # He arrives carrying more than the fill wants: his own tank is the
    # supply, and the pump cannot take fuel out.
    assert fuel_in_hand_to_flag(_race(fuel_l=84.0))[2] == "on the fuel aboard"
    # The fill does not fit: he leaves with the tank full, and that is the
    # branch the negative comes from.
    got, why, rests_on = fuel_in_hand_to_flag(
        _race(fuel_capacity_l=30.0, fuel_l=25.0, lap=9, stint_ends_on_lap=10))
    assert why is None and got < 0
    assert rests_on == "on a full tank"


def test_no_tank_size_refuses_rather_than_becoming_an_infinite_tank():
    """**Rule 3, and it is the whole expression here rather than a term in
    it.** `fuel_capacity_l` is None until a packet sets it, and GT7 reports
    0 L for an electric car - a real value, not an error (CLAUDE.md 3.4).
    Skipping the cap on either turns "the plan does not reach" into a
    comfortable positive."""
    for capacity in (None, 0.0):
        got, why, _ = fuel_in_hand_to_flag(_race(fuel_capacity_l=capacity))
        assert got is None, capacity
        assert why == "no tank size read"


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
    assert fuel_in_hand_to_flag(state) == (spoken, None, "on the fuel aboard")
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
    assert why == "the stop is late"
    assert fuel_in_hand_to_flag(state)[0] == fuel_in_hand(state)[0]
    assert fuel_in_hand_to_flag(state)[2] == "on the fuel aboard"


def test_a_tank_that_does_not_reach_the_box_refuses_rather_than_clamps():
    """CLAUDE.md rule 9. A negative arrival is a reading whose reference is
    wrong, not a tank with nothing in it, and a flag figure computed from it
    would be a confident wrong answer about a race he never gets to."""
    state = _race(fuel_l=8.0)
    to_flag, why, _ = fuel_in_hand_to_flag(state)
    assert to_flag is None
    assert why == "tank short of the box"
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
    to_flag, why, _ = fuel_in_hand_to_flag(state)
    assert why is None
    # 30 L at 4.19 covers 7.2 laps; ten remain after the box, so the fill the
    # plan wants does not fit and the shortfall is the finding.
    assert to_flag is not None and to_flag < 0, to_flag


def test_another_stop_after_this_one_is_refused_not_guessed():
    """The laps after the NEXT stop ride on a fill nothing has sized, so a
    figure here would be a claim about a stop the app has not costed."""
    state = _race(further_stop_planned=True)
    assert fuel_in_hand_to_flag(state)[1] == "a stop after this one"
    # And unknown refuses for the same reason: `further_stop_planned` is None
    # where nobody said, and an unknown is not a no.
    assert fuel_in_hand_to_flag(_race(further_stop_planned=None))[1] == \
        "a stop after this one"


def test_a_missing_input_is_named_rather_than_pooled():
    """"No burn measured yet" said about a missing tank reading is a wrong
    answer wearing a right one's clothes."""
    assert fuel_in_hand_to_flag(_race(fuel_per_lap_l=None))[1] == \
        "no burn measured yet"
    assert fuel_in_hand_to_flag(_race(fuel_l=None))[1] == "no fuel reading"
    assert fuel_in_hand_to_flag(_race(laps_total=None))[1] == \
        "race length unknown"


def test_a_stop_on_the_last_lap_is_not_reported_as_past_the_flag():
    """**Two situations, and they were sharing one sentence.** `after_box`
    of zero is a stop scheduled for the LAST LAP, which is a real plan a
    driver has to execute; below zero is a stop past the flag, which is not.
    Telling him "past the flag" about the first reads as "the plan is
    broken" beside a live countdown still saying `plan: lap 21`, and he
    ignores a mandatory stop."""
    assert fuel_in_hand_to_flag(_race(stint_ends_on_lap=20))[1] == \
        "stop is the last lap"
    assert fuel_in_hand_to_flag(_race(stint_ends_on_lap=21))[1] == \
        "stop is past the flag"


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
        # One rear moving 0.2 degC a lap moves the AXLE gap 0.1 - real, and
        # well under RATE_WORTH_SAYING_C.
        creeping.note_lap(_lap(70.0, 70.0, 75.0 + 0.2 * lap, 75.0))
    rate, laps = creeping.axle_rate()
    assert rate is None and laps == 6

    running = SplitHistory()
    for lap in range(6):
        # One rear at 3.0 a lap is 1.5 on the axle gap, which clears it.
        running.note_lap(_lap(70.0, 70.0, 75.0 + 3.0 * lap, 75.0))
    rate, laps = running.axle_rate()
    assert rate == pytest.approx(1.5) and laps == 6


def test_a_trend_may_not_be_fitted_across_a_pit_stop():
    """**The window is eight laps and a stop lands in the middle of it.**

    Driven with the old set opening +6 to +20 degC and a fresh one restarting
    at +3 and opening at +1 a lap, the fit ran through both and drew
    *"settling 2.0/lap"* for six consecutive laps while the gap was in fact
    opening - with a sample count of "8 laps", half of which were a different
    tyre. §5.5's worked example makes that a brake-balance decision.

    `new_stint` is called at every PIT_EXIT, whether or not a set went on: the
    tyre detector is a tri-state and an unknown is not a no, and a stationary
    car cools whatever came off it.
    """
    history = SplitHistory()
    for lap in range(8):
        history.note_lap(_lap(70.0, 70.0, 76.0 + 2.0 * lap, 76.0 + 2.0 * lap))
    old_rate, _ = history.axle_rate()
    assert old_rate is not None and old_rate > 0

    history.new_stint()
    assert history.axle_split_now() is None
    assert history.axle_rate() == (None, 0)

    # The fresh set opens at 1.0 degC a lap - under the floor - and the board
    # claims no direction rather than the old set's 2.0 in the wrong one.
    for lap in range(4):
        history.note_lap(_lap(70.0, 70.0, 73.0 + lap, 73.0 + lap))
    rate, laps = history.axle_rate()
    assert rate is None and laps == 4


def test_a_lap_missing_a_corner_is_dropped_from_the_axle_series_too():
    """Three corners cannot make an axle mean, and a part-filled lap in the
    middle of a series is fitted straight through as though it were
    measured."""
    history = SplitHistory()
    history.note_lap(_lap(70.0, 70.0, 80.0, 80.0))
    history.note_lap({"fl": 70.0, "fr": None, "rl": 80.0, "rr": 80.0})
    assert len(history.laps) == 1


# ----------------------------------------------- the board, as it renders

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
    # `_sub_text`, the string the block was given: `plan: lap 11 · fuel
    # only` is 24 characters, which the middle rank holds on the rig at
    # 16 px a character and elides under the offscreen test font at 27.
    assert view.box_stat._sub_text == "plan: lap 11 · fuel only"
    # **The set going ON, not the set he is on**, and the two are given here
    # as the controller gives them: `compound` is what is bolted to the car,
    # `next_compound` is the plan's decision. Built with only `compound`,
    # this test could not see the board naming the wrong tyre on every
    # compound-changing stop - which is the only kind of stop this caption
    # earns its place on.
    view.update_state(DriverState(laps_to_box=4, box_on_lap=11,
                                  tyres_at_stop=True, compound="RM",
                                  next_compound="RS"))
    assert "fit RS" in view.box_stat.sub.text()
    assert "RM" not in view.box_stat.sub.text()
    # **A plan that did not say is silent.** "Fuel only" and "the plan is
    # quiet about it" are different answers and only one is a decision.
    view.update_state(DriverState(laps_to_box=4, box_on_lap=11,
                                  tyres_at_stop=None, compound="RS"))
    assert view.box_stat.sub.text() == "plan: lap 11"


def test_the_flag_block_names_the_supply_it_was_measured_on(qt_app):
    """**Rule 13, and the reason there is a caption at all.** Two blocks under
    near-identical headings, one that moves with the tank and one that cannot,
    is unreadable unless the second says what it rests on."""
    from pitcrew.ui.driver_view import DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(fuel_to_stop=6.1, laps_of_fuel=9.1,
                                  fuel_to_flag=14.9, burn_l=4.19,
                                  fuel_to_flag_on="on the plan's fill"))
    assert "9.1 laps aboard" in view.stop_stat.sub.text()
    # The reference leads, because it is the half that has to survive a cut.
    assert view.flag_stat.sub.text().startswith("on the plan's fill")
    # **The live litres are NOT here.** Both figures come off the tank as it
    # read at the last crossing; `packet.fuel_level` beside them put three
    # readings of one tank on the screen, none reconciling.
    view.update_state(DriverState(fuel_to_stop=6.1, fuel_to_flag=14.9,
                                  fuel_l=38.1, burn_l=4.19))
    assert "38.1" not in view.flag_stat.sub.text()
    assert "38.1" not in view.stop_stat.sub.text()


# The real overdue-box sentence `_box_now` builds, 126 characters of it.
OVERDUE_CALL = ("Box this lap. RM on. 3 laps overdue. You're 1.4 laps short "
                "of the flag on current burn - short-shift and lift if you "
                "stay out.")


def test_a_long_call_keeps_the_direction_and_still_ends_in_an_ellipsis(qt_app):
    """**Unbounded, the label asked for 3,744 px** and took the board's layout
    minimum to 4,117 - not a monitor he owns - and clipped flat with no
    ellipsis, so the half he lost was the reason.

    **Bounded to ONE line it was worse.** 1,560 px holds about 59 characters,
    which rendered *"You're 1.4 laps ..."* - and "1.4 laps" with the direction
    cut off reads as 1.4 laps IN HAND when what it said was 1.4 short. Two
    lines hold the whole of every call the engineer makes today, and anything
    longer still ends in an ellipsis rather than stopping dead.
    """
    from pitcrew.ui.driver_view import BoardCall, DriverState, DriverView

    view = DriverView()
    view.resize(2480, 1050)
    view.show()
    qt_app.processEvents()
    view.update_state(DriverState(last_call=BoardCall(
        text=OVERDUE_CALL, mark=MARK_INSTRUCTION, lap=14)))
    qt_app.processEvents()
    drawn = view.last_call.line.text()
    assert drawn.startswith("L14  Box this lap.")
    # The words that carry the direction survive.
    assert "short of the flag" in drawn
    # And a sentence three times longer than anything George says is cut,
    # visibly.
    view.update_state(DriverState(last_call=BoardCall(
        text=OVERDUE_CALL * 3, mark=MARK_INSTRUCTION, lap=14)))
    qt_app.processEvents()
    assert view.last_call.line.text().endswith("…")
    view.hide()


# **A growth ceiling in the HARNESS's font, not a claim about his monitor.**
# The offscreen face is 27 px a character where his is 16, so no absolute
# figure measured here is a fact about the panel - and forcing the board under
# 2560 offscreen means shortening strings for a font nobody has, which was
# done once on this branch and had to be undone. What this number is for is
# noticing growth: it is a little above where the board sits today, and the
# panel itself is held by
# `test_the_board_fits_his_monitor_on_the_faces_he_actually_has`.
# **Raised 3200 -> 3400 on 14 Sep 2026, and why.** Plan row 5.21 put the
# lap-time panel into the corners' row beside the three lights, which the
# offscreen stub font measures at 3,300 px. On the rig's faces the widest state
# it can be given measured 2,139 x 1,055 - inside his 2,560 x 1,080 panel, which
# `test_the_board_fits_his_monitor_on_the_faces_he_actually_has` holds. This
# ceiling is a growth tripwire on a pessimistic font, not the monitor.
OFFSCREEN_GROWTH_CEILING = 3400


def test_the_board_does_not_grow_in_the_widest_state_it_can_be_given(qt_app):
    """**Every state the board can be given, rendered and measured.**

    Qt answers a layout minimum bigger than the screen by growing the window
    off it rather than by dropping anything, so a board that does not fit
    loses its right-hand end - POSITION and the edge of the BEHIND gap - with
    nothing on the screen saying it has.

    **Three versions of this guard have now missed a way for the board to
    grow**, and each miss is why a line below is here:

    * the first compared a long call against a BLANK board, so it could not
      see a 46-character refusal reason widening a fuel block;
    * the second hard-coded `Boxhead` and `Rocky`, the two shortest names in
      the project's own reconstruction. The gap sentence carries a rival's
      name off the game and PSN ids run to sixteen characters; at fourteen
      the board already measured 2,490 px;
    * neither ever set `in_box`, and `QStackedLayout`'s minimum is the
      maximum over BOTH pages - so a stop whose next stint had no stated
      length set the window's minimum to 3,220 px and KEPT it for the rest of
      the race, because the page holds its text after he leaves the box.

    So this sweeps every refusal string both fuel figures can produce, a
    sixteen-character rival name on both neighbours, all five box states, and
    a call three times longer than any the engineer makes.

    ⚠️ **It runs offscreen, where the faces are not the rig's, and the two
    differ by a factor of 1.7.** Cascadia Mono at 27 px is 16 px a character
    natively and 27 px under the offscreen stub, so this measurement is
    pessimistic in width and optimistic in height - it cannot see a height
    regression at all (`GAP_PX = 210` puts the board at 1,090 px on the rig,
    over his panel, and 997 offscreen, with the whole suite green), and its
    widths are not his. So it asserts a GROWTH ceiling and the monitor is
    held by `test_the_board_fits_his_monitor_on_the_faces_he_actually_has`.

    No point figures are quoted in this docstring. Two rounds of them were
    wrong within a commit of being written, the last set by a change in the
    same commit.
    """
    from pitcrew.race import calls as C
    from pitcrew.ui.driver_view import (BoardCall, DriverState, DriverView,
                                        GapView)

    reasons = [C.NO_STOP_TO_COME, C.STOP_IS_LATE, C.NO_PLAN,
               C.FROM_THE_GREEN, C.NO_BURN_YET,
               C.NO_FUEL_READING, C.NO_RACE_LENGTH, C.NOT_REACHING_THE_BOX,
               C.STOP_ON_THE_LAST_LAP, C.STOP_PAST_THE_FLAG,
               C.ANOTHER_STOP_AFTER, C.NO_CAPACITY]
    rests = [C.ON_THE_PLANS_FILL, C.ON_THE_TANK_ABOARD, C.ON_A_FULL_TANK]
    long_name = "AVeryLongPSNid16"
    view = DriverView()
    view.resize(2480, 1050)
    view.show()
    qt_app.processEvents()
    widest = 0

    def measure(state, what):
        nonlocal widest
        view.update_state(state)
        qt_app.processEvents()
        # **`minimumSizeHint`, which is the size Qt actually enforces.**
        # `layout().minimumSize()` is not the same number and reported 1035
        # for a board whose window came out 1128 - the height that put the
        # first artefact over his panel.
        size = view.minimumSizeHint()
        widest = max(widest, size.width())

    for reason in reasons:
        for rests_on in rests:
            measure(DriverState(
                fuel_to_stop_why=reason, fuel_to_flag_why=reason,
                fuel_to_flag_on=rests_on,
                # The longest box caption there is, so the middle rank is
                # measured at its own worst as well as the fuel blocks at
                # theirs.
                laps_to_box=3, box_on_lap=12, tyres_at_stop=False,
                compound="RS", position=12, field_size=24, burn_l=4.19,
                # The lap panel at its widest: both references, a long
                # compound, and every light lit.
                lap_time_ms=599_999, delta_s=-12.345, session_best_ms=599_999,
                predicted_ms=599_999, delta_file_s=+12.345,
                file_best_ms=599_999, reference_compound="RMW",
                wet="mixed", abs_setting="Default", front_lock=True,
                tcs_active=True,
                ahead=GapView(
                    seconds=12.4,
                    note=f"he is catching 0.6 s a lap - {long_name}",
                    urgent=True),
                behind=GapView(
                    seconds=4.8,
                    note=f"pulling away 0.9 s a lap - {long_name}",
                    good=True),
                last_call=BoardCall(text=OVERDUE_CALL * 3,
                                    mark=MARK_UNCONFIRMED, lap=14)),
                reason)

    # **The box page, COMBINED rather than one shape at a time.** The first
    # version measured each of the five alone, which is how a fuel-only stop
    # with a measured rate, 31 L aboard and a rejoin behind a sixteen-
    # character name - all reachable together - came to measure 3,110 px with
    # every one of its parts inside the bound. Every shape is now built on
    # top of the widest common state, not instead of it.
    widest_box = dict(fuel_target_l=63.0, release_in_s=24.0, fuel_l=31.0,
                      fill_rate_note="declared", out_position=7,
                      out_behind=long_name)
    for box in (
            dict(has_plan=True, next_stint_laps=9, next_compound="RS",
                 tyres_at_stop=True),
            dict(has_plan=True),
            dict(has_plan=True, past_the_plan=True),
            dict(has_plan=True, runs_to_flag=True),
            dict(has_plan=True, tyres_at_stop=False),
            dict(has_plan=True, tyres_at_stop=True),
            {}):
        measure(DriverState(in_box=True, **{**widest_box, **box}), box)

    # **And the practice page**, where the lap panel leads at full size.
    for why in (None, "no best lap yet on this tyre", "compound not set"):
        measure(DriverState(session_kind="practice", lap_time_ms=599_999,
                            delta_s=None if why else -1.234, delta_why=why,
                            file_best_ms=599_999, delta_file_s=+1.234,
                            reference_compound="RS", wet="wet",
                            abs_setting="Weak", front_lock=True,
                            tcs_active=True), why)

    assert widest <= OFFSCREEN_GROWTH_CEILING, widest
    view.hide()


def test_a_short_call_is_not_elided(qt_app):
    from pitcrew.ui.driver_view import BoardCall, DriverState, DriverView

    view = DriverView()
    view.resize(2160, 1040)
    view.show()
    qt_app.processEvents()
    view.update_state(DriverState(last_call=BoardCall(
        text="Box this lap. Fuel to 63.", mark=MARK_INSTRUCTION, lap=11)))
    qt_app.processEvents()
    assert view.last_call.line.text() == "L11  Box this lap. Fuel to 63."
    view.hide()


def test_the_preview_sample_is_produced_by_the_code_it_pictures(qt_app):
    """**The acceptance artefact may not disagree with the app.** The first
    version of the sample hand-wrote an axle split of 12.15 beside four corner
    temperatures whose axle gap is 10.4, and a flag figure the fuel expression
    does not produce. A screenshot that contradicts the code proves the
    opposite of what it was taken for."""
    from pitcrew.race.tyre_split import SplitHistory
    from pitcrew.ui.preview import SAMPLE_TEMPS, sample_board

    board = sample_board()
    history = SplitHistory()
    for temps in SAMPLE_TEMPS:
        history.note_lap(temps)
    assert board.temps_c == SAMPLE_TEMPS[-1]
    # The per-corner trends are what `SplitHistory` makes of those laps.
    for corner, rate in (board.split_rates or {}).items():
        assert rate == pytest.approx(history.rate(corner)[0])
    # The predicted lap is the session best plus the live delta - the same
    # sum `BoardLive` makes for the real board.
    assert board.predicted_ms == board.session_best_ms + round(board.delta_s * 1000)
    # The countdown and the lap it names count the same way: the HUD lap he is
    # on plus the laps to the box, less the one in progress - it is the first
    # of them (14 Sep 2026).
    assert board.box_on_lap == 9 + int(board.laps_to_box) - 1


def test_the_board_fits_his_monitor_on_the_faces_he_actually_has():
    """**The guard above cannot see a height regression, and this can.**

    The offscreen font the suite runs on is 27 px a character where the rig's
    Cascadia Mono is 16 - so every offscreen width is pessimistic and every
    offscreen HEIGHT is optimistic. `GAP_PX = 210` measures 997 px offscreen
    and **1,090 on the rig**, over his 1080 panel, with the whole suite green.
    That is the regression round three found by hand and nothing has held it
    since.

    So this measures in a subprocess with no `QT_QPA_PLATFORM` forced. It
    skips where there is no real font database - a headless machine has
    nothing to measure and saying so is better than asserting the stub.
    """
    import json
    import subprocess
    import sys
    import textwrap

    probe = textwrap.dedent("""
        import json, sys
        from dataclasses import replace
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QFontDatabase
        app = QApplication([])
        from pitcrew.ui import theme
        theme.apply(app)
        if not QFontDatabase.families():
            print(json.dumps({"skip": "empty font database"})); sys.exit(0)
        from pitcrew.ui.driver_view import DriverState, DriverView, GapView
        from pitcrew.race import calls as C
        view = DriverView()
        # **Shown, like its offscreen sibling.** Without this the widget is
        # never laid out and its width hint comes back 784 px light - 1154
        # against 1938 - so the width leg could not fail however wide the
        # caps were set. The height leg was right either way.
        view.resize(2480, 1050)
        view.show()
        app.processEvents()
        name = "AVeryLongPSNid16"
        worst = (0, 0)
        states = []
        for reason in (C.NO_STOP_TO_COME, C.NOT_REACHING_THE_BOX,
                       C.STOP_PAST_THE_FLAG, C.ANOTHER_STOP_AFTER):
            states.append(DriverState(
                fuel_to_stop_why=reason, fuel_to_flag_why=reason,
                fuel_to_flag_on=C.ON_THE_PLANS_FILL, burn_l=4.19,
                laps_to_box=3, box_on_lap=12, tyres_at_stop=False,
                compound="RS", next_compound="RS", position=12, field_size=24,
                lap_time_ms=599_999, delta_s=-12.345, session_best_ms=599_999,
                predicted_ms=599_999, delta_file_s=12.345, file_best_ms=599_999,
                reference_compound="RS", wet="mixed", abs_setting="Default",
                front_lock=True, tcs_active=True,
                ahead=GapView(seconds=12.4,
                              note=f"he is catching 0.6 s a lap - {name}",
                              urgent=True),
                behind=GapView(seconds=4.8,
                               note=f"pulling away 0.9 s a lap - {name}",
                               good=True)))
        common = dict(in_box=True, fuel_target_l=63.0, release_in_s=24.0,
                      fuel_l=31.0, fill_rate_note="declared", out_position=7,
                      out_behind=name, has_plan=True)
        for extra in ({}, {"next_stint_laps": 9, "next_compound": "RS",
                           "tyres_at_stop": True}, {"runs_to_flag": True},
                      {"past_the_plan": True}, {"tyres_at_stop": False}):
            states.append(DriverState(**{**common, **extra}))
        # The practice page, whose lap panel leads at full size.
        states.append(DriverState(
            session_kind="practice", lap_time_ms=599_999, delta_s=-1.234,
            session_best_ms=599_999, predicted_ms=599_999, delta_file_s=1.234,
            file_best_ms=599_999, reference_compound="RS", wet="wet",
            abs_setting="Weak", front_lock=True, tcs_active=True,
            temps_c={"fl": 99.0, "fr": 99.0, "rl": 99.0, "rr": 99.0}))
        # **And the phone page** (15 Sep 2026): the fuel and position at the
        # lead size, the lap panel above, and the sector panel beside the
        # lights carrying its longest line - every page counts, because a
        # stack is as tall as its tallest page.
        from pitcrew.race.board_live import SectorsView
        states.append(replace(states[0], strip_live=True, sectors=SectorsView(
            times_ms=(599_999, 599_999, 599_999),
            best_ms=(599_998, 599_998, 599_998),
            set_best=(False, False, False),
            cut="thirds of the lap - not GT7's", compound="RS")))
        for state in states:
            view.update_state(state)
            app.processEvents()
            size = view.minimumSizeHint()
            # Per leg. `max` over (w, h) tuples is lexicographic: it kept
            # the widest state's height, so a taller, narrower state was
            # never held to the panel's height at all.
            worst = (max(worst[0], size.width()),
                     max(worst[1], size.height()))
        print(json.dumps({"w": worst[0], "h": worst[1]}))
    """)
    run = subprocess.run([sys.executable, "-c", probe],
                         capture_output=True, text=True,
                         cwd=str(Path(__file__).resolve().parents[2]),
                         env={k: v for k, v in os.environ.items()
                              if k != "QT_QPA_PLATFORM"})
    assert run.returncode == 0, run.stderr[-2000:]
    got = json.loads(run.stdout.strip().splitlines()[-1])
    if "skip" in got:
        pytest.skip(f"no real faces to measure: {got['skip']}")
    # 2560 x 1080, and the window is frameless with no resize handle.
    # **The height leg is the one that bites.** `GAP_PX = 210` and
    # `LINES = 3` both fail it, which is what it exists for. The width leg
    # cannot fail on anything reachable - the real-face board has some 600 px
    # of headroom - and that is worth asserting anyway and worth saying
    # plainly rather than dressing up as a test of the caps.
    assert got["h"] <= 1080, got
    assert got["w"] <= 2560, got


def test_the_burn_stays_on_the_flag_block(qt_app):
    """**It has been taken off once already, for a reason that was false.**

    The arithmetic said `on the plan's fill · 4.19 L/lap` wanted thirty-one
    characters against a twenty-one character bound; both figures came off the
    offscreen test font, and on the rig the string measures 496 px against 640
    and fits. The two tests that had pinned its ABSENCE were then rewritten to
    `.startswith("on the plan's fill")`, which is true either way - so it
    could have gone a third time in silence. The burn is what lets him check
    the figure; the reference is what says whether it is his to move; the
    order is what survives a cut.
    """
    from pitcrew.ui.driver_view import DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(fuel_to_flag=0.3, burn_l=4.19,
                                  fuel_to_flag_on="on the plan's fill"))
    # **The string the block was GIVEN**, because whether the tail survives
    # the elide is a property of the face: on the rig the whole thing fits in
    # 496 px of a 640 px bound, and under the offscreen test font it does
    # not. What is asserted here is what the board is asked to say.
    given = view.flag_stat._sub_text
    assert given.startswith("on the plan's fill")
    assert "4.19" in given, given
    # And the rendered form leads with the reference either way, because
    # `_resub` elides from the right.
    assert view.flag_stat.sub.text().startswith("on the plan's fill")


def test_a_dash_on_the_flag_block_carries_a_reason_and_not_a_burn(qt_app):
    """`--` captioned `4.19 L/lap` says what the figure would have rested on,
    which is not why there is not one. Every dash on this board says why."""
    from pitcrew.ui.driver_view import DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(fuel_to_flag=None, burn_l=4.19,
                                  fuel_to_flag_on="on the plan's fill"))
    assert view.flag_stat.value.text() == "--"
    # **The string the block was GIVEN.** Asserted on the rendered label this
    # passed with the defect reinstated: offscreen the sub elides at 640 px
    # to `on the plan's fill · 4…`, so the burn was cut by the harness's font
    # rather than by the code. On the rig the mutant renders the whole thing.
    assert "4.19" not in view.flag_stat._sub_text
    assert view.flag_stat._sub_text == "not measured"


def test_a_stop_that_sizes_to_zero_litres_is_not_a_stop_nobody_sized(qt_app):
    """**Rule 3, on the one number he holds the trigger against.**
    `fuel_target_l` is deliberately unclamped, so a real `0.0` was read as
    falsy and RELEASE IN said "nothing sized it" while FUEL TO one block
    along drew `0`. Two adjacent blocks contradicting each other about
    whether the stop had been sized."""
    from pitcrew.ui.driver_view import DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(in_box=True, fuel_target_l=0.0,
                                  release_in_s=None))
    assert view.box.fuel_stat.value.text() == "0"
    assert "nothing sized" not in view.box.release_stat.sub.text()


def test_the_box_names_the_set_going_on_even_when_the_plan_names_no_compound(
        qt_app):
    """**A dash where the opposite decision gets a word.**

    `handover.validate` permits a stint with `tyres` and no `compound`, so
    `tyres_at_stop=True, next_compound=None` is plan-reachable. The panel
    rendered it as `--`, on the one screen he reads with his hands on the
    MFD, while the same board had said "new set" on the straight and
    `_tyre_word` had said "Tyres on." in his ear. He takes a fuel-only stop
    the plan did not ask for.
    """
    from pitcrew.ui.driver_view import DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(in_box=True, has_plan=True,
                                  tyres_at_stop=True, next_compound=None))
    assert view.box.tyre_stat.value.text() == "NEW SET"
    assert "not named" in view.box.tyre_stat.sub.text()
    # And the opposite decision is still its own word.
    view.update_state(DriverState(in_box=True, has_plan=True,
                                  tyres_at_stop=False))
    assert view.box.tyre_stat.value.text() == "NO TYRES"


def test_the_box_tyre_block_names_the_set_going_on_not_the_one_coming_off(
        qt_app):
    """The blocker `_box_caption` was fixed for, one page over: this panel was
    still reading `compound`, and was right only because the controller
    overwrote that field on the in-box branch."""
    from pitcrew.ui.driver_view import DriverState, DriverView

    view = DriverView()
    view.update_state(DriverState(in_box=True, has_plan=True,
                                  tyres_at_stop=True, compound="RM",
                                  next_compound="RS"))
    assert view.box.tyre_stat.value.text() == "RS"
