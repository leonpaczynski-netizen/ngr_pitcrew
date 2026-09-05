"""The optimal lap: three best sectors added up, and what it may not include.

**Nobody drove it**, which is the whole reason it is worth stating and the
whole reason it has to be derived ink. It says: this is available, and you
have already driven every part of it.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture(scope="module")
def qt_app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def a_lap(num, total, s1, s2, **kw):
    """A counted lap, mid-session.

    `lap_num_in_session` starts at 2 deliberately: the opening lap of a
    session IS an out-lap, so a fixture numbering from 1 gets its first lap
    struck by the rack and then tests the wrong thing. Which is the behaviour
    `test_an_out_lap_cannot_donate_a_sector` asserts on purpose, below.
    """
    from pitcrew.ui.practice_screen import LapRow
    kw.setdefault("lap_num_in_session", num + 1)
    return LapRow(lap_id=num, lap_num=num, lap_time_ms=total, fuel_used=7.8,
                  sector1_ms=s1, sector2_ms=s2, sector3_ms=total - s1 - s2,
                  sector_source="daytona:thirds:1/2", compound="RS", **kw)


# Slow enough in every sector that it can never win one, so it is only ever
# the out-lap and never a donor. `test_an_out_lap_cannot_donate_a_sector`
# supplies a FAST one instead, which is the case that matters.
SLOW_OPENER = (140_000, 50_000, 48_000)


def a_screen(rows, *, opener=True):
    """The rack, with a real out-lap in front of the laps under test.

    **`auto_out_laps` always claims the rack's opening lap**, and it is right
    to: a lobby session's first lap is driven out of the box and is short -
    93.100 s against 105-112 s for the rest of the Daytona session it was
    found on. A fixture that numbers from 1 therefore gets its first lap
    struck, and then quietly tests one lap fewer than it thinks. Rather than
    work around the rule, these fixtures carry the out-lap the rule exists
    for.
    """
    from pitcrew.ui.practice_screen import PracticeScreen
    if opener:
        rows = [a_lap(0, *SLOW_OPENER, lap_num_in_session=1)] + list(rows)
    screen = PracticeScreen()
    screen.set_laps(rows)
    return screen


def test_it_is_the_best_of_each_sector_not_the_best_lap(qt_app):
    """Three sectors from three different laps. If it only ever returned the
    best lap's own splits it would be a rename, not a finding."""
    screen = a_screen([
        a_lap(1, 103_500, 37_400, 36_000),      # best S3 (30_100)
        a_lap(2, 104_100, 37_200, 36_400),      # best S1
        a_lap(3, 103_900, 37_600, 35_800),      # best S2
    ])
    total, parts = screen.optimal_lap()
    assert parts == (37_200, 35_800, 30_100)
    assert total == 103_100
    # Ahead of every lap actually driven, which is the point.
    assert total < min(row.lap_time_ms for row in screen.rows())


def test_an_out_lap_cannot_donate_a_sector(qt_app):
    """A pit-exit-to-line fragment is SHORT. Letting its S1 into the sum
    produces a target nothing could ever match, and it would look exactly
    like a real one."""
    fast_but_uncounted = a_lap(1, 60_000, 8_000, 26_000, lap_num_in_session=1)
    screen = a_screen([
        fast_but_uncounted,
        a_lap(2, 103_900, 37_600, 35_800),
        a_lap(3, 104_100, 37_200, 36_400),
    ], opener=False)
    assert screen.rows()[0].is_out_lap, "the rack did not claim the out-lap"
    total, parts = screen.optimal_lap()
    assert parts[0] == 37_200, "the out-lap's 8.000 s S1 was counted"
    assert total > 100_000


def test_a_struck_lap_cannot_donate_a_sector(qt_app):
    """Same rule as the timing marks: only a counted lap holds a mark."""
    screen = a_screen([
        a_lap(1, 100_000, 30_000, 35_000, excluded=True),
        a_lap(2, 103_900, 37_600, 35_800),
    ])
    total, _ = screen.optimal_lap()
    assert total == 103_900, "a struck lap donated a sector"


def test_a_missing_sector_refuses_the_whole_lap(qt_app):
    """Sectors are refused on about one lap in six. A sum over two of three
    is not a lap time - it is a smaller number that looks like one."""
    from pitcrew.ui.practice_screen import LapRow
    screen = a_screen([
        LapRow(lap_id=1, lap_num=1, lap_time_ms=103_900, fuel_used=7.8,
               lap_num_in_session=2, sector1_ms=37_600, sector2_ms=None,
               sector3_ms=30_100),
    ], opener=False)
    assert screen.optimal_lap() is None


def test_no_laps_at_all_is_none_not_zero(qt_app):
    """Rule 3, at the one place a sum would happily produce a 0."""
    assert a_screen([], opener=False).optimal_lap() is None


def test_it_reaches_the_spec_line_as_derived(qt_app):
    """Purple, because no car set this time. Green would say he typed it and
    white would say it came off the stream; both are false."""
    from pitcrew.ui import theme
    from pitcrew.ui.widgets import Derived

    screen = a_screen([
        a_lap(1, 103_500, 37_400, 36_000),
        a_lap(2, 104_100, 37_200, 36_400),
        a_lap(3, 103_900, 37_600, 35_800),
    ])
    labels = {entry[0].text(): entry[1] for entry in screen.spec._entries}
    assert "Optimal" in labels, "the optimal lap never reached the spec line"
    assert isinstance(labels["Optimal"], Derived)
    assert theme.DERIVED.lower() in labels["Optimal"].styleSheet().lower()
    # And the gap, which is the figure he can actually act on.
    assert "Available" in labels


def test_no_gap_is_shown_when_the_best_lap_already_is_the_optimal(qt_app):
    """Printing "+0.000 s" sends him looking for a tenth that is not there."""
    screen = a_screen([a_lap(1, 103_900, 37_600, 35_800),
                       a_lap(2, 104_500, 37_900, 36_100)])
    total, _ = screen.optimal_lap()
    assert total == 103_900
    labels = [entry[0].text() for entry in screen.spec._entries]
    assert "Optimal" in labels
    assert "Available" not in labels
