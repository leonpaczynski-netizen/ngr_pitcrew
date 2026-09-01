"""The live rack has to name out-laps by the same rule the rebuild does.

`controller._rows_for_event` applies `auto_out_laps` when it builds the rack
from stored laps. `PracticeScreen.add_lap` did not: it appended whatever
`is_out_lap` the lap carried out of the database, and that column is zero on
every lap ever recorded. So the rack was right when the event was selected
and wrong for every lap that landed live afterwards - which is the shape the
driver reported, "counting outlap as fastest lap in second stint, got it
right in first ever practice stint".

The numbers below are session 114 at Daytona, 1 Sep 2026, unrounded.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture(scope="session")
def qt_app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# (lap_time_ms, fuel_start, fuel_end) - the opening lap is driven out of the
# pit box and is SHORT, which is why an unstruck out-lap does not merely join
# the count, it wins by twelve seconds.
DAYTONA_114 = [
    (93100, 99.97, 92.72),
    (108484, 92.72, 85.27),
    (106319, 85.27, 77.91),
    (106115, 77.91, 70.39),
    (112467, 70.39, 62.84),
    (107999, 62.84, 55.20),
    (105661, 55.20, 47.67),
    (105977, 47.67, 40.27),
]


def _row(index, lap, mode="lobby", session_id=114):
    from pitcrew.ui.practice_screen import LapRow

    time_ms, start, end = lap
    return LapRow(
        lap_id=1000 + index,
        lap_num=index,
        lap_time_ms=time_ms,
        fuel_used=round(start - end, 2),
        fuel_start=start,
        fuel_end=end,
        # As the database has it on every lap ever recorded.
        is_out_lap=False,
        session_id=session_id,
        practice_mode=mode,
        lap_num_in_session=index,
    )


def test_a_lap_arriving_live_does_not_make_the_out_lap_the_session_best(qt_app):
    from pitcrew.ui.practice_screen import PracticeScreen

    screen = PracticeScreen()
    for index, lap in enumerate(DAYTONA_114, 1):
        screen.add_lap(_row(index, lap))

    rows = screen.rows()
    assert rows[0].is_out_lap, "the opening lap of a lobby session is an out-lap"
    assert not rows[0].counted

    counted = [row for row in rows if row.counted]
    best = min(row.lap_time_ms for row in counted)
    assert best == 105661, "the best counted lap, not the 93.100 s out-lap"
    assert len(counted) == 7


def test_the_live_rack_and_the_rebuild_reach_the_same_answer(qt_app):
    """The two paths must agree or the screen quotes a session the payload
    does not describe."""
    from pitcrew.analysis.runs import auto_out_laps
    from pitcrew.ui.practice_screen import PracticeScreen

    screen = PracticeScreen()
    for index, lap in enumerate(DAYTONA_114, 1):
        screen.add_lap(_row(index, lap))

    live = {row.lap_num for row in screen.rows() if row.is_out_lap}
    rebuilt = auto_out_laps([_row(i, lap) for i, lap in enumerate(DAYTONA_114, 1)])
    assert live == rebuilt


def test_a_refuel_mid_session_opens_a_run_and_strikes_its_first_lap(qt_app):
    """The new lap is what opens the run, so the rule cannot be applied to
    the row in isolation - it is recomputed across the whole rack."""
    from pitcrew.ui.practice_screen import PracticeScreen

    laps = [
        (95000, 100.0, 92.0),
        (105000, 92.0, 84.0),
        (105000, 84.0, 76.0),
        # Boxed: the tank goes back up, so this lap starts a new run.
        (118000, 99.0, 91.0),
        (104500, 91.0, 83.0),
    ]
    screen = PracticeScreen()
    for index, lap in enumerate(laps, 1):
        screen.add_lap(_row(index, lap))

    rows = screen.rows()
    assert rows[0].is_out_lap
    assert rows[3].is_out_lap, "the lap after the stop is an out-lap"
    assert not rows[4].is_out_lap
    counted = [row.lap_time_ms for row in rows if row.counted]
    assert min(counted) == 104500


def test_a_time_trials_opening_lap_is_not_struck(qt_app):
    """The one exception, and the live path could not see it before: the car
    starts on track in a time trial and that lap is the session best in six
    of the eight time trials on file."""
    from pitcrew.ui.practice_screen import PracticeScreen

    screen = PracticeScreen()
    for index, lap in enumerate(DAYTONA_114[:4], 1):
        screen.add_lap(_row(index, lap, mode="time-trial"))

    rows = screen.rows()
    assert not rows[0].is_out_lap
    assert min(row.lap_time_ms for row in rows if row.counted) == 93100


# ---------------------------------------------------------- fuel-implausible

def _burning(burns, times=None, *, tank=100.0, mode="lobby"):
    """Rows whose tank actually chains, so no lap looks like a refuel.

    Getting this wrong makes every lap a run start and therefore an out-lap,
    which is a fixture bug that reads exactly like a product one.
    """
    from pitcrew.ui.practice_screen import LapRow

    rows = []
    for index, burn in enumerate(burns, 1):
        start, tank = tank, tank - burn
        rows.append(LapRow(
            lap_id=2000 + index,
            lap_num=index,
            lap_time_ms=(times[index - 1] if times else 107_000),
            fuel_used=burn,
            fuel_start=start,
            fuel_end=tank,
            session_id=200,
            practice_mode=mode,
            lap_num_in_session=index,
        ))
    return rows


def test_a_garage_transition_lap_does_not_become_the_live_best(qt_app):
    """The 11 Aug Monza shape: a lap boundary inside a garage transition
    burns a twentieth of a lap's fuel and, being short, is promoted to best.
    The rebuild struck it; the live path did not."""
    from pitcrew.ui.practice_screen import PracticeScreen

    screen = PracticeScreen()
    screen.set_fuel_capacity(100.0)
    # The fifth boundary landed in the garage: 0.16 L, and 90 s.
    for row in _burning([6.5, 6.4, 6.6, 6.5, 0.16, 6.5],
                        [109_000, 107_500, 107_800, 108_100, 90_200, 107_200]):
        screen.add_lap(row)

    rows = screen.rows()
    assert rows[4].excluded
    assert rows[4].exclusion_reason == "fuel-implausible"
    counted = [row.lap_time_ms for row in rows if row.counted]
    assert min(counted) == 107_200, "not the 90.200 s garage lap"


def test_the_rule_withdraws_a_mark_the_settling_median_no_longer_supports(qt_app):
    """CLAUDE.md rule 10. The floor is half the MEDIAN burn, so it moves as
    laps arrive - a mark that could only be set would latch an early estimate
    for the rest of the session with nothing able to retire it."""
    from pitcrew.ui.practice_screen import PracticeScreen

    screen = PracticeScreen()
    screen.set_fuel_capacity(100.0)
    # Two heavy laps first, so the early median is high and the third lap -
    # an ordinary one - falls under half of it. Then more ordinary laps
    # arrive and the median settles onto them.
    rows = _burning([9.0, 9.0, 4.0, 4.1, 4.0, 3.9, 4.0])
    for row in rows[:3]:
        screen.add_lap(row)
    assert screen.rows()[2].excluded, "struck against the two-lap median"

    for row in rows[3:]:
        screen.add_lap(row)

    assert not screen.rows()[2].excluded, "the mark has to be withdrawable"
    assert screen.rows()[2].exclusion_reason is None
    assert screen.rows()[2].counted


def test_a_hand_strike_is_never_withdrawn_by_the_fuel_rule(qt_app):
    """Only exclusions this rule wrote are its to take back."""
    from pitcrew.ui.practice_screen import PracticeScreen

    screen = PracticeScreen()
    screen.set_fuel_capacity(100.0)
    rows = _burning([6.5, 6.5, 6.5, 6.5])
    rows[0].excluded = True
    rows[0].exclusion_reason = "struck by hand"
    for row in rows:
        screen.add_lap(row)

    assert screen.rows()[0].excluded
    assert screen.rows()[0].exclusion_reason == "struck by hand"


def test_an_electric_car_does_not_have_its_whole_session_struck(qt_app):
    """A capacity of 0 is a real value and every lap burns nothing."""
    from pitcrew.ui.practice_screen import PracticeScreen

    screen = PracticeScreen()
    screen.set_fuel_capacity(0.0)
    for row in _burning([0.0, 0.0, 0.0, 0.0], tank=0.0):
        screen.add_lap(row)

    assert not any(row.excluded for row in screen.rows())
