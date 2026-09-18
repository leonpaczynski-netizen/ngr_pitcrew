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
