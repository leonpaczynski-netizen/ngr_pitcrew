"""The monitor as history - the third screen of his split (17 Sep 2026).

"Monitor - history data viewed least." With his car on the phone and the
field on the tablet, the ultrawide carries the race behind him: every lap as
it was judged, and the burns per beep column. These hold the two ways a rack
like this lies - a lap quietly dropped, and two columns averaged into one.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from pitcrew.ui.driver_view import (  # noqa: E402
    HISTORY_ROWS, DriverState, DriverView, history_rows, history_summary)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _lap(lap, **over):
    row = {"lap": lap, "lap_ms": 101_400, "target_ms": 101_100,
           "lap_delta_s": 0.3, "burn_l": 5.37, "burn_delta_l": 0.02,
           "saving": True, "why": None, "pit": False, "out": False,
           "compound": "RM"}
    row.update(over)
    return row


def test_a_lap_with_no_verdict_keeps_its_row_and_says_why():
    """Dropping them leaves a rack whose lap numbers skip, and the gaps are
    where most of a race's time goes."""
    rows = history_rows([_lap(9), _lap(10, pit=True, lap_delta_s=None,
                                       burn_delta_l=None, why="a pit lap"),
                         _lap(11, out=True, lap_delta_s=None,
                              burn_delta_l=None, why="an out lap")])
    assert [row.lap for row in rows] == ["9", "10", "11"]
    assert [row.note for row in rows] == ["save", "pit lap", "out lap"]
    assert rows[1].delta == "" and rows[1].burn == "5.37"


def test_the_rack_tones_each_half_on_its_own_target():
    rows = history_rows([_lap(4, lap_delta_s=-0.4, burn_delta_l=0.3)])
    assert rows[0].delta == "-0.400" and rows[0].delta_tone == "good"
    assert rows[0].burn == "5.37  +0.30" and rows[0].burn_tone == "urgent"


def test_the_rack_draws_the_last_laps_and_no_more():
    rows = history_rows([_lap(n) for n in range(1, 40)])
    assert len(rows) == HISTORY_ROWS and rows[-1].lap == "39"


def test_the_summary_keeps_the_two_columns_apart():
    """5.37 saving and 7.04 full pooled is ~5.6 - the practice figure, and
    the bug that put six litres in the car at Sardegna."""
    laps = ([_lap(n, saving=False, burn_l=7.04) for n in range(1, 4)]
            + [_lap(n) for n in range(4, 10)])
    summary = history_summary(laps)
    assert "save 5.37 L/lap over 6" in summary
    assert "full 7.04 L/lap over 3" in summary
    assert "9 laps" in summary and "best 1:41.400" in summary


def test_the_monitor_turns_to_history_only_with_both_screens_up(app):
    view = DriverView()
    racing = DriverState(session_kind="race", history=(_lap(3), _lap(4)))
    view.update_state(racing)
    assert view.states.currentWidget() is view.running
    view.update_state(DriverState(session_kind="race", show_history=True,
                                  history=(_lap(3), _lap(4))))
    assert view.states.currentWidget() is view.history
    assert view.history.cells[0][0].text() == "3"
    # A stop is happening: the box wins whatever is on the other screens.
    view.update_state(DriverState(session_kind="race", show_history=True,
                                  in_box=True))
    assert view.states.currentWidget() is view.box
    view.close()


def test_the_corners_are_on_the_history_page_because_they_are_on_no_other(app):
    """His call, 18 Sep 2026. With the phone on his car and the tablet on the
    field, this page replaces the live board - and the four temperatures, the
    one reading GT7 does not show him, went with it."""
    view = DriverView()
    view.update_state(DriverState(
        session_kind="race", show_history=True, history=(_lap(3),),
        compound="RH", temps_c={"fl": 88.0, "fr": 91.0, "rl": 85.0,
                                "rr": 87.0}))
    assert view.states.currentWidget() is view.history
    drawn = {corner: widget.value.text()
             for corner, widget in view.history.tyres.items()}
    assert drawn == {"fl": "88", "fr": "91", "rl": "85", "rr": "87"}
    assert view.history.tyre_caption.text().endswith("RH")
    # The same expression the running board uses, so one set of temperatures
    # cannot be two claims: both pages ink 91 on an RH the same way.
    assert (view.history.tyres["fr"].value.styleSheet()
            == view.tyres["fr"].value.styleSheet())
    # And with no compound the caption refuses the wear line, as it does above.
    view.update_state(DriverState(session_kind="race", show_history=True,
                                  history=(_lap(3),),
                                  temps_c={"fl": 88.0}))
    assert "NO WEAR LINE" in view.history.tyre_caption.text()
    view.close()


def test_his_fuel_in_hand_is_on_the_page_he_is_actually_looking_at(app):
    """**It was on no screen at all for a whole race** (20 Sep, Bathurst).

    `DriverState` carries `fuel_l`, `laps_of_fuel` and `burn_l` on every
    250 ms tick. But with the phone and the tablet both polling, the monitor
    swaps to this page, `_show_fuel` writes into hidden widgets, the tablet's
    own row is blank and the strip draws litres only inside the box. Captured
    four times a second from lap 1 to the flag, rendered nowhere.

    **Both distances are named, on the same line** - rule 13. "Laps in hand"
    was spoken twice in two minutes meaning laps-to-the-stop and
    laps-to-the-flag, figures ten laps apart, neither naming its reference.
    """
    from pitcrew.ui.driver_view import fuel_in_hand_parts

    view = DriverView()
    state = DriverState(session_kind="race", show_history=True,
                        history=(_lap(3), _lap(4)),
                        fuel_to_stop=2.4, fuel_to_flag=-1.2,
                        laps_of_fuel=8.1, burn_l=5.37)
    view.update_state(state)
    assert view.states.currentWidget() is view.history
    drawn = view.history.fuel.text()
    assert "2.4 TO THE STOP" in drawn and "-1.2 TO THE FLAG" in drawn
    assert "8.1 ABOARD" in drawn
    # **The shortfall is inked as one and the healthy figure is not**, which
    # is why the line is built in parts: one ink for the whole of it would
    # have to lie about one of the two.
    parts = dict((words, ink) for words, ink in fuel_in_hand_parts(state))
    assert parts["2.4 TO THE STOP"] != parts["-1.2 TO THE FLAG"]
    view.close()


def test_a_fuel_figure_the_page_has_not_got_says_why_it_has_not(app):
    """Every dash on this board says why, and a dash is not a figure - so it
    does not take a figure's ink either (rule 3)."""
    from pitcrew.race import calls as C
    from pitcrew.ui.driver_view import INK_DIM, fuel_in_hand_parts

    state = DriverState(session_kind="race", show_history=True,
                        history=(_lap(3),),
                        fuel_to_stop_why=C.NO_STOP_TO_COME,
                        fuel_to_flag_why=C.NO_STOP_TO_COME)
    parts = fuel_in_hand_parts(state)
    words = [text for text, _ in parts]
    assert any(C.NO_STOP_TO_COME in text and "TO THE STOP" in text
               for text in words), words
    assert all(ink == INK_DIM for text, ink in parts if text.startswith("--"))
    # Nothing aboard was measured, so nothing aboard is claimed.
    assert not any("ABOARD" in text for text in words), words


def test_the_fuel_line_says_the_same_thing_the_running_board_says(app):
    """One tank, one claim, whichever page is up (rules 12 and 13). Both
    figures come from `fuel_stop_block` / `fuel_flag_block` unchanged - not
    from a second expression written for this page."""
    from pitcrew.ui.driver_view import (fuel_flag_block, fuel_in_hand_parts,
                                        fuel_stop_block)

    state = DriverState(session_kind="race", show_history=True,
                        history=(_lap(3),), fuel_to_stop=2.4,
                        fuel_to_flag=6.8, laps_of_fuel=8.1, burn_l=5.37)
    words = [text for text, _ in fuel_in_hand_parts(state)]
    assert f"{fuel_stop_block(state).value} TO THE STOP" in words
    assert f"{fuel_flag_block(state).value} TO THE FLAG" in words


def test_the_flag_keeps_the_race_on_the_history_page():
    """At the flag the board builds its own state, and it carried no history:
    the monitor turned to twelve empty rows and "0 laps" at the one moment
    the page is read."""
    from pitcrew.controller import PitCrewController
    from pitcrew.race import calls as C

    ctl = PitCrewController.__new__(PitCrewController)
    race = type("Race", (), {"running": False, "armed": True})()
    race.state = C.RaceState(lap=20, laps_total=20, finished=True,
                             position=3, field_size=20)
    race.state.lap_history = [_lap(19), _lap(20)]
    ctl.race = race
    ctl._board_temps = lambda *a, **k: {}
    ctl._split_rates = lambda: {}
    ctl._board_live_fields = lambda: {}
    ctl._board_call = None
    state = ctl._driver_board_state()
    assert state.finished is True
    assert [lap["lap"] for lap in state.history] == [19, 20]
    assert history_rows(state.history)[-1].lap == "20"


def test_the_flag_is_built_from_the_real_live_fields_not_an_empty_stub():
    """**The stub above is why a crash at every chequered flag shipped
    green.**

    `_board_live_fields()` ALWAYS carries `lap_number`
    (`board_live.board_fields`), and the finished branch passed
    `lap_number=` as a keyword beside the `**` splat of it. Every test of
    that branch stubbed the splat to `{}`, so the one collision the branch
    could have was the one thing no test could reach:

        TypeError: DriverState() got multiple values for keyword argument
        'lap_number'

    raised four times a second from 21:17:25 on 20 Sep, which took the
    phone strip to NO DATA and the monitor board down for the rest of the
    session (`logs/pitcrew.log:11358-11383`). This test builds the branch
    from a REAL `BoardLive.board_fields()` dict, so any key the two sides
    ever both claim fails here rather than at a flag.
    """
    from pitcrew.controller import PitCrewController
    from pitcrew.race import calls as C
    from pitcrew.race.board_live import BoardLive

    live_fields = dict(BoardLive().board_fields())
    assert "lap_number" in live_fields, (
        "the collision this test guards needs board_fields to carry it")

    ctl = PitCrewController.__new__(PitCrewController)
    race = type("Race", (), {"running": False, "armed": True})()
    race.state = C.RaceState(lap=20, laps_total=20, finished=True,
                             position=3, field_size=20)
    race.state.lap_history = [_lap(19), _lap(20)]
    ctl.race = race
    ctl._board_temps = lambda *a, **k: {}
    ctl._split_rates = lambda: {}
    ctl._board_live_fields = lambda: dict(live_fields)
    ctl._board_call = None

    state = ctl._driver_board_state()
    assert state.finished is True
    # **And the lap on it is HIS lap, not the live panel's.** `lap_number`
    # off `board_fields` is the packet's `laps_completed`, which drifts from
    # `lap_on_screen()` after a crossing lost in the pit lane - so the
    # winner of the collision had to be the one the box lap is counted in.
    assert state.lap_number == race.state.lap_on_screen()
    assert [lap["lap"] for lap in state.history] == [19, 20]


def test_the_monitor_does_not_turn_to_an_empty_rack_in_practice():
    """Both pages poll in practice too. Without a race behind him the rack is
    twelve blank rows under "0 laps", in place of the live board."""
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.driver_view import DriverState as DS

    class Server:
        def live(self, page="strip"):
            return True

        def last_client_of(self, page="strip"):
            return "10.0.0.9"

        def publish(self, body, page="strip"):
            pass

    ctl = PitCrewController.__new__(PitCrewController)
    ctl.race = None
    # `_tablet_controls` reads which session is OPEN, and it reads
    # `session_kind` directly - a default there would hide one that
    # went missing - so a controller built by hand sets it by hand.
    ctl.session_kind = None
    ctl._strip_composer = type("C", (), {"compose": lambda _s, state: {}})()
    ctl._strip_was_live = True
    ctl._strip_failures = 0
    ctl.strip = Server()
    ctl._driver_board_state = lambda: DS(session_kind="practice")
    state = ctl._publish_strip()
    assert state.show_history is False
    ctl._driver_board_state = lambda: DS(session_kind="race",
                                         history=(_lap(3),))
    assert ctl._publish_strip().show_history is True


# ----------------------------------------------------------------- practice
# **The lap rack on the monitor** - his ask, 20 Sep 2026: *"in practice board
# on monitor should move to tablet as it has nothing on it and the lap rack on
# the practice page can be visible on the monitor."* Nothing is re-parented:
# `_HistoryPanel` already IS that rack, and all that was missing was something
# to fill `DriverState.history` with outside a race.


def _practice_lap(num, ms=105_400, fuel=4.12, **over):
    """One `practice_screen.LapRow`, the real class - the converter reads its
    `counted` property and the rack's own out-lap and strike marks, and a stub
    that agreed with itself would prove nothing about either."""
    from pitcrew.ui.practice_screen import LapRow

    return LapRow(lap_id=num, lap_num=num, lap_time_ms=ms, fuel_used=fuel,
                  **over)


def _practising(rows, intent="practice"):
    """A controller far enough built to answer `_driver_board_state()`."""
    from pitcrew.controller import PitCrewController

    ctl = PitCrewController.__new__(PitCrewController)
    ctl.race = None
    ctl.session_kind = "practice"
    ctl.bridge = type("B", (), {"last_packet": None})()
    ctl.practice = type("P", (), {
        "rows": lambda _s: list(rows),
        "practice_intent": lambda _s: intent})()
    ctl._board_temps = lambda *a, **k: {}
    ctl._split_rates = lambda: {}
    ctl._board_live_fields = lambda: {}
    ctl._board_call = None
    return ctl


def test_the_practice_laps_reach_the_monitors_rack():
    """The half of his ask that is nearly free. `_HistoryPanel` is already
    this rack; the practice branch of `_driver_board_state` simply never put
    anything in `history`, so the page had nothing to be reachable WITH."""
    ctl = _practising([_practice_lap(1, ms=95_000, is_out_lap=True),
                       _practice_lap(2, ms=105_400),
                       _practice_lap(3, ms=104_900)])
    state = ctl._driver_board_state()
    assert state.session_kind == "practice"
    assert [lap["lap"] for lap in state.history] == [1, 2, 3]
    assert history_rows(state.history, kind="practice")[-1].lap == "3"


def test_the_practice_rack_is_reachable_the_moment_there_are_laps_to_draw():
    """**And not one lap before it.** The guard that kept an empty rack off
    the live practice board is `bool(board.history)`, not the session kind -
    so filling the practice branch needed nothing done to it."""
    from pitcrew.controller import PitCrewController

    class Server:
        def live(self, page="strip"):
            return True

        def last_client_of(self, page="strip"):
            return "10.0.0.9"

        def publish(self, body, page="strip"):
            pass

    def publisher(rows):
        ctl = PitCrewController.__new__(PitCrewController)
        ctl.race = None
        ctl._strip_composer = type("C", (), {"compose": lambda _s, s: {}})()
        ctl._strip_was_live = True
        ctl._strip_failures = 0
        ctl.strip = Server()
        practising = _practising(rows)
        ctl._driver_board_state = practising._driver_board_state
        ctl._publish_tablet = lambda _strip, board=None: True
        return ctl._publish_strip()

    assert publisher([]).show_history is False
    assert publisher([_practice_lap(1)]).show_history is True


def test_a_practice_rack_that_cannot_be_read_costs_a_page_not_the_board():
    """`_driver_board_state` runs inside the board's own failure counter, and
    twelve raises take the board off the monitor for the session. Reaching
    into another screen's widget tree is the one thing on the practice board
    that can raise, so it is guarded to an empty rack - which the line above
    then declines to show."""
    ctl = _practising([])
    ctl.practice = type("P", (), {
        "rows": lambda _s: (_ for _ in ()).throw(RuntimeError("mid-rebuild")),
        "practice_intent": lambda _s: "practice"})()
    assert ctl._driver_board_state().history == ()


def test_a_practice_delta_is_against_the_rack_and_carries_no_verdict_ink():
    """**Plain, not red.** A practice delta is the lap against the best of the
    laps beside it, so it cannot be negative - and the race's tone rule would
    paint every row but one urgent, which says the session went wrong when all
    it says is that one lap was the quickest."""
    from pitcrew.ui.driver_view import practice_history

    history = practice_history([_practice_lap(1, ms=105_400),
                                _practice_lap(2, ms=104_900),
                                _practice_lap(3, ms=106_200)])
    rows = history_rows(history, kind="practice")
    assert [row.delta for row in rows] == ["+0.500", "+0.000", "+1.300"]
    assert {row.delta_tone for row in rows} == {"plain"}
    # And a race is untouched: its delta is against a plan, and late is bad
    # news in a colour.
    assert history_rows([_lap(4, lap_delta_s=0.9)])[0].delta_tone == "urgent"


def test_a_practice_lap_that_did_not_count_keeps_its_row_and_sets_no_best():
    """The same set `PracticeScreen._best_ms` takes the best from. A lobby
    out-lap is short by twelve seconds at Daytona: counted, it is the best on
    the rack and every delta under it is wrong."""
    from pitcrew.ui.driver_view import practice_history

    history = practice_history([
        _practice_lap(1, ms=93_100, is_out_lap=True),
        _practice_lap(2, ms=105_400),
        _practice_lap(3, ms=104_900, excluded=True,
                      exclusion_reason="fuel implausible")])
    assert [lap["lap_delta_s"] for lap in history] == [None, 0.0, None]
    rows = history_rows(history, kind="practice")
    assert [row.lap for row in rows] == ["1", "2", "3"]
    assert [row.note for row in rows] == ["out lap", "", "fuel implausible"]


def test_a_burn_the_practice_rack_never_read_is_not_drawn_as_zero():
    """Rule 3, on the one figure tomorrow's fuel plan is built from.
    `LapRow.fuel_used` is a plain float and a lap whose fuel was never read
    arrives as 0.0 - drawn, that is a measurement nobody made."""
    from pitcrew.ui.driver_view import practice_history

    history = practice_history([_practice_lap(1, fuel=0.0),
                                _practice_lap(2, fuel=4.12)])
    assert [lap["burn_l"] for lap in history] == [None, 4.12]
    assert [row.burn for row in history_rows(history, kind="practice")] \
        == ["", "4.12"]


def test_the_practice_summary_carries_the_reference_burn_with_its_count():
    """Practice has one burn column, not two - no plan, so no beep column -
    and that one figure is why the rack is worth a screen the night before a
    race. Over the counted laps only, and with its count (rule 4)."""
    from pitcrew.ui.driver_view import practice_history

    history = practice_history([
        _practice_lap(1, ms=93_100, fuel=1.90, is_out_lap=True),
        _practice_lap(2, ms=105_400, fuel=4.12),
        _practice_lap(3, ms=104_900, fuel=4.08)])
    summary = history_summary(history, kind="practice")
    assert "3 laps" in summary and "best 1:44.900" in summary
    # The out-lap's 1.90 is not a reference burn, and it is not in the mean.
    assert "burn 4.10 L/lap over 2" in summary
    # A race still splits its two beep columns and never pools them.
    assert "save" in history_summary([_lap(3)])


def test_the_summary_and_the_delta_column_name_one_best(app):
    """**Rule 13 across two lines of one page.** The rack draws twelve laps
    and the summary reads the whole session, so a best set on lap 1 of twenty
    is off the bottom of the rack - referenced by every delta above it and
    named only in the summary. Sliced to twelve before either saw it, the
    summary would have named a slower lap as "best" while the deltas went on
    being measured against the quicker one."""
    from pitcrew.ui.driver_view import format_lap_ms, practice_history

    history = practice_history(
        [_practice_lap(1, ms=100_000)]
        + [_practice_lap(n, ms=105_000 + n) for n in range(2, 21)])
    assert len(history) == 20
    rows = history_rows(history, kind="practice")
    assert len(rows) == HISTORY_ROWS and rows[0].lap == "9"
    assert f"best {format_lap_ms(100_000)}" in history_summary(
        history, kind="practice")
    # And the deltas on the drawn rows are against that same lap.
    assert rows[-1].delta == "+5.020"


def test_the_rack_is_worded_for_the_session_it_is_describing(app):
    """**Rule 13, on the head of a column.** "VS TARGET" over a lap judged
    against his own best would be the same three words meaning two things on
    two nights - and "THE RACE SO FAR" over a practice rack names the wrong
    session outright."""
    from pitcrew.ui.driver_view import practice_history

    view = DriverView()
    view.update_state(DriverState(session_kind="race", show_history=True,
                                  history=(_lap(3), _lap(4))))
    assert view.history.caption.text() == "THE RACE SO FAR"
    assert "VS TARGET" in view.history.heads[2].text()

    view.update_state(DriverState(
        session_kind="practice", show_history=True,
        history=practice_history([_practice_lap(1), _practice_lap(2)])))
    assert view.states.currentWidget() is view.history
    assert view.history.caption.text() == "THE SESSION SO FAR"
    # **Not a bare "VS BEST".** The phone says that in practice already, and
    # there it is the best lap EVER recorded on this tyre.
    assert "VS BEST ON RACK" in view.history.heads[2].text()
    # No plan, so no burn target - the head drops the half it has not got
    # rather than dashing it.
    assert "VS TARGET" not in view.history.heads[3].text()
    assert "BURN" in view.history.heads[3].text()
    # And back again, in one app run: he practises, then races.
    view.update_state(DriverState(session_kind="race", show_history=True,
                                  history=(_lap(3),)))
    assert "VS TARGET" in view.history.heads[2].text()
    assert view.history.caption.text() == "THE RACE SO FAR"
    view.close()


def test_the_practice_rack_claims_no_laps_in_hand(app):
    """There is no stop and no flag in practice, so both figures would be
    permanent refusals dragging their reasons along - two things to read that
    can never change, which is why the running board HIDES its race-only rows
    in practice rather than dashing them."""
    from pitcrew.ui.driver_view import practice_history

    view = DriverView()
    view.update_state(DriverState(
        session_kind="practice", show_history=True,
        history=practice_history([_practice_lap(1)])))
    assert view.history.fuel.text() == ""
    # The race page is untouched: it was put there because both figures were
    # on no screen at all for a whole race.
    view.update_state(DriverState(session_kind="race", show_history=True,
                                  history=(_lap(3),), fuel_to_stop=2.4,
                                  fuel_to_flag=6.8, laps_of_fuel=8.1))
    assert "2.4 TO THE STOP" in view.history.fuel.text()
    view.close()


def test_every_lap_is_filed_as_it_was_judged():
    from pitcrew.tests.test_field import _coordinator

    race = _coordinator()
    lap = type("Lap", (), {"lap_num": 3, "lap_time_ms": 101_400,
                           "fuel_used": 5.4, "is_pit_lap": False,
                           "is_out_lap": False, "short_shift_rpm": None})()
    race._judge_against_target(lap, incident=False)
    filed = race.state.lap_history[-1]
    assert filed["lap"] == 3 and filed["lap_ms"] == 101_400
    assert filed["burn_l"] == 5.4
    # No plan targets on this race: the reason is filed, never a zero.
    assert filed["lap_delta_s"] is None and filed["why"]


# ---- rule 13: one burn column, two references, and it says where it moved

def test_the_rack_marks_the_lap_the_burn_reference_changed():
    """Bathurst Rd 8. The burn deltas read `-2.32 -2.48 -2.18 -2.13 -2.12
    +0.16 0.00 -0.24` down one column in one ink: laps 2-6 against the plan's
    10.625 and laps 7+ against this race's own 8.47. Nothing he did changed
    on lap 7 - the app changed what it was subtracting."""
    from pitcrew.strategy.targets import BURN_BASIS_PLAN, BURN_BASIS_RACE

    laps = ([_lap(n, saving=False, burn_delta_l=-2.3,
                  burn_source=BURN_BASIS_PLAN) for n in (5, 6)]
            + [_lap(n, saving=False, burn_delta_l=0.1,
                    burn_source=BURN_BASIS_RACE) for n in (7, 8, 9)])
    notes = [row.note for row in history_rows(laps)]
    # The first judged row in the window, so it is never wholly unlabelled,
    # and the row where it moved. Not every row: twelve repetitions of one
    # word is a column he reads once and then stops seeing.
    assert notes == ["full · vs plan", "full", "full · vs race",
                     "full", "full"]


def test_a_rack_whose_laps_carry_no_reference_is_drawn_as_it_always_was():
    """Rule 3 - and the practice rack, which has no plan to be against."""
    assert [row.note for row in history_rows([_lap(4), _lap(5)])] == \
        ["save", "save"]
    assert [row.note for row in
            history_rows([_lap(4)], kind="practice")] == ["save"]


def test_a_lap_with_no_burn_verdict_is_not_a_change_of_reference():
    """A pit lap carries no delta, so it cannot be evidence that anything
    moved - and it keeps its own word."""
    from pitcrew.strategy.targets import BURN_BASIS_RACE

    rows = history_rows([
        _lap(9, saving=False, burn_delta_l=0.1, burn_source=BURN_BASIS_RACE),
        _lap(10, pit=True, lap_delta_s=None, burn_delta_l=None,
             burn_source=None, why="a pit lap"),
        _lap(11, saving=False, burn_delta_l=0.1, burn_source=BURN_BASIS_RACE),
    ])
    assert [row.note for row in rows] == ["full · vs race", "pit lap", "full"]
