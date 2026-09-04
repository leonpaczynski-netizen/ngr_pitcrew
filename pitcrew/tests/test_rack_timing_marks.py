"""Purple and green on the rack, and the tail the rack follows.

The driver asked for the timing convention he reads everywhere else: purple
for a personal best, green for the best of the stint. It could not be done
with ink — purple text already means DERIVED and `CRAYON` green already means
DECLARED — so the rank is painted behind the number and the register is left
alone. These tests are mostly about which cells earn a fill and, more
importantly, which must not.

The one that matters is the out-lap. A pit-exit-to-line fragment is SHORT:
`min(lap_time_ms)` over the Daytona event once returned 93.100 s as the best
lap of the day, and a purple cell would have made that look like an
achievement rather than a defect.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from pitcrew.ui import theme  # noqa: E402
from pitcrew.ui.practice_screen import (  # noqa: E402
    ROW_HEIGHT,
    Bests,
    LapRow,
    PracticeScreen,
    rank_fill,
)

STAMP = "somewhere-full-course:landmark:2000/4000"
OTHER = "somewhere-full-course:thirds:1900/3800"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _lap(num, ms, sectors=(40_000, 36_000, 30_000), *, out=False,
         stamp=STAMP, session=1, fuel_start=None):
    """One rack row, with a tank that **falls** across the run.

    The fuel matters more than it looks. `auto_out_laps` calls any lap whose
    tank is fuller than the last one's end the start of a new run, and a
    fixture that gave every lap a full tank made every lap an out-lap - so
    nothing was counted, nothing could hold a mark, and the tests failed
    against perfectly good code. A fake of the wrong shape tests the fake.
    """
    if fuel_start is None:
        fuel_start = 90.0 - 3.0 * (num - 1)
    return LapRow(lap_id=num, lap_num=num, lap_time_ms=ms, fuel_used=3.0,
                  fuel_start=fuel_start, fuel_end=fuel_start - 3.0,
                  compound="RH", is_out_lap=out, session_id=session,
                  lap_num_in_session=num, sector1_ms=sectors[0],
                  sector2_ms=sectors[1], sector3_ms=sectors[2],
                  sector_source=stamp)


def _fills(screen):
    """`(lap fill, [three sector fills])` per drawn row."""
    return [(row.time_label._fill,
             [label._fill for label in row.sector_labels])
            for row in screen._row_widgets]


# ---------------------------------------------------------------- the ranking

def test_purple_outranks_green():
    """A lap that is the fastest ever here is also the fastest of its stint,
    and it is the larger claim that gets said."""
    assert rank_fill(100, 100, 100, counted=True) == theme.BEST_EVER


def test_green_where_it_leads_the_stint_but_not_the_archive():
    assert rank_fill(100, 100, 95, counted=True) == theme.BEST_STINT


def test_nothing_where_it_leads_neither():
    assert rank_fill(110, 100, 95, counted=True) is None


def test_an_uncounted_lap_can_never_hold_a_mark():
    """The out-lap case, and the reason the whole rule exists."""
    assert rank_fill(90, 100, 95, counted=False) is None


def test_a_missing_or_zero_figure_holds_no_mark():
    """A refused sector and a lap whose time was cleared as a phantom are
    both `None`/0 here, and neither is a fast lap."""
    assert rank_fill(None, 100, 95, counted=True) is None
    assert rank_fill(0, 100, 95, counted=True) is None


def test_nothing_to_beat_yet_holds_no_mark():
    assert rank_fill(100, None, None, counted=True) is None


# ------------------------------------------------------------------ on a rack

def test_the_out_lap_holds_no_mark_even_when_it_is_the_shortest(app):
    """**The defect this guards.** A pit-exit-to-line fragment is shorter than
    every real lap, so a naive minimum crowns it."""
    screen = PracticeScreen()
    screen.set_laps([
        _lap(1, 60_000, out=True),          # a fragment, quicker than anything
        _lap(2, 100_000),
        _lap(3, 99_000),
    ])
    laps, sectors = zip(*_fills(screen))
    assert laps[0] is None                  # the fragment holds nothing
    assert laps[2] == theme.BEST_STINT      # the real quickest does


def test_green_is_per_stint_not_per_rack(app):
    """Two stints, and each keeps its own green - which is the whole point of
    the colour. A refuel between them is what splits the run."""
    screen = PracticeScreen()
    screen.set_laps([
        _lap(1, 100_000, fuel_start=90.0),
        _lap(2, 99_000, fuel_start=87.0),
        # A tank fuller than the last lap's end is a refuel, and a refuel
        # starts a new run - which is what a stint is.
        _lap(3, 101_000, fuel_start=90.0),
        _lap(4, 100_500, fuel_start=87.0),
    ])
    laps = [fill for fill, _ in _fills(screen)]
    assert laps[1] == theme.BEST_STINT      # quickest of the first stint
    assert laps[3] == theme.BEST_STINT      # and of the second, though slower
    assert laps[2] is None


def test_purple_comes_from_the_archive_and_not_from_the_rack(app):
    """Nothing on the rack can be purple on its own - "ever" is a claim about
    every practice session, which only the store can answer."""
    screen = PracticeScreen()
    rows = [_lap(1, 100_000), _lap(2, 99_000)]
    screen.set_laps(rows)
    assert all(fill != theme.BEST_EVER for fill, _ in _fills(screen))

    screen.set_personal_bests({STAMP: {"lap_ms": 99_000,
                                       "sectors": (None, None, None)}})
    assert _fills(screen)[1][0] == theme.BEST_EVER


def test_a_sector_is_marked_against_its_own_lines(app):
    """A rack can hold two sets of lines - a catalogue entry added between one
    session and the next - and a sector cut at 1,900 m is not comparable with
    one cut at 2,000. Each half is marked against its own."""
    screen = PracticeScreen()
    # **Every session opens with an out-lap** by the rack's own rule, and an
    # out-lap holds no mark - so each half needs a second lap to carry one.
    screen.set_laps([
        _lap(1, 105_000, (44_000, 40_000, 33_000), stamp=STAMP),
        _lap(2, 100_000, (40_000, 36_000, 30_000), stamp=STAMP),
        _lap(3, 105_000, (44_000, 40_000, 33_000), stamp=OTHER, session=2),
        _lap(4, 100_000, (39_000, 36_000, 30_000), stamp=OTHER, session=2),
    ])
    screen.set_personal_bests({
        STAMP: {"lap_ms": None, "sectors": (40_000, None, None)},
        OTHER: {"lap_ms": None, "sectors": (38_000, None, None)},
    })
    fills = _fills(screen)
    assert fills[1][1][0] == theme.BEST_EVER    # 40.000 is the best on ITS lines
    assert fills[3][1][0] != theme.BEST_EVER    # 39.000 is not, on the other's


def test_a_sector_the_model_refused_is_never_marked(app):
    screen = PracticeScreen()
    screen.set_laps([_lap(1, 100_000, (None, None, None))])
    assert _fills(screen)[0][1] == [None, None, None]


def test_the_ink_register_survives_a_mark(app):
    """A filled cell switches to `STENCIL` so it reads on the dark ground -
    but an unfilled sector is still DERIVED purple text, because it is still
    a figure the app worked out."""
    screen = PracticeScreen()
    screen.set_laps([_lap(1, 100_000), _lap(2, 99_000)])
    plain = screen._row_widgets[0].sector_labels[0]
    assert theme.DERIVED in plain.styleSheet()
    marked = screen._row_widgets[1].time_label
    assert theme.BEST_STINT in marked.styleSheet()
    assert theme.STENCIL in marked.styleSheet()


# ------------------------------------------------------------- following the tail

def test_a_lap_landing_while_he_watches_the_bottom_scrolls_to_it(app):
    screen = PracticeScreen()
    screen.resize(900, 300)
    screen.set_laps([_lap(n, 100_000 + n) for n in range(1, 12)])
    bar = screen.scroller.verticalScrollBar()
    bar.setValue(bar.maximum())
    screen.add_lap(_lap(12, 99_000))
    assert screen._follow_tail is True


def test_a_lap_landing_while_he_is_marking_up_lap_three_does_not_move_him(app):
    """The same concern the whole of `add_lap` exists for: a lap arriving
    while he is tagging a compound must not take the row out from under the
    cursor."""
    screen = PracticeScreen()
    screen.resize(900, 300)
    screen.show()          # the scroll area has no range until it is laid out
    QApplication.instance().processEvents()
    screen.set_laps([_lap(n, 100_000 + n) for n in range(1, 30)])
    QApplication.instance().processEvents()
    bar = screen.scroller.verticalScrollBar()
    assert bar.maximum() > ROW_HEIGHT * 2, "need a rack taller than the view"
    bar.setValue(0)
    screen.add_lap(_lap(30, 99_000))
    assert screen._follow_tail is False
