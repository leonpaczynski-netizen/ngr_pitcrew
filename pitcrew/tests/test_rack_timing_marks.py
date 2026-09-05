"""Purple and blue on the rack, and the tail the rack follows.

The driver asked for the timing convention he reads everywhere else: **purple
fastest, then blue, then ordinary.** It was first built as a fill behind the
number, on the argument that purple ink was spoken for by the DERIVED
register — and that inverted the thing it was protecting. Every sector on the
rack is the app's own cut of the lap, so every sector was DERIVED, so every
sector was purple, and the driver reported the result exactly: *every sector
looks like it is the best sector*. The rank is the ink now; the claim that the
cut is ours moved to the column head. These tests are mostly about which
figures earn a mark and, more importantly, which must not.

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
    rank_ink,
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
    """`(lap mark, [three sector marks])` per drawn row."""
    return [(row.time_label._rank,
             [label._rank for label in row.sector_labels])
            for row in screen._row_widgets]


# ---------------------------------------------------------------- the ranking

def test_purple_outranks_green():
    """A lap that is the fastest ever here is also the fastest of its stint,
    and it is the larger claim that gets said."""
    assert rank_ink(100, 100, 100, counted=True) == theme.BEST_EVER


def test_green_where_it_leads_the_stint_but_not_the_archive():
    assert rank_ink(100, 100, 95, counted=True) == theme.BEST_STINT


def test_nothing_where_it_leads_neither():
    assert rank_ink(110, 100, 95, counted=True) is None


def test_an_uncounted_lap_can_never_hold_a_mark():
    """The out-lap case, and the reason the whole rule exists."""
    assert rank_ink(90, 100, 95, counted=False) is None


def test_a_missing_or_zero_figure_holds_no_mark():
    """A refused sector and a lap whose time was cleared as a phantom are
    both `None`/0 here, and neither is a fast lap."""
    assert rank_ink(None, 100, 95, counted=True) is None
    assert rank_ink(0, 100, 95, counted=True) is None


def test_nothing_to_beat_yet_holds_no_mark():
    assert rank_ink(100, None, None, counted=True) is None


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
    assert all(mark != theme.BEST_EVER for mark, _ in _fills(screen))

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


def test_an_ordinary_sector_is_neither_purple_nor_white(app):
    """**The defect the driver reported, asserted so it cannot come back.**

    Purple meant DERIVED, every sector is derived, so every sector was
    purple - and purple is what a timing screen uses for fastest, so the
    whole column read as best sectors. It may not be white either: a sector
    is the app's own cut of the lap and white is the ink for what came off
    the stream.
    """
    screen = PracticeScreen()
    screen.set_laps([_lap(1, 100_000), _lap(2, 99_000)])
    plain = screen._row_widgets[0].sector_labels[0]
    assert theme.BEST_EVER not in plain.styleSheet()
    assert theme.DERIVED not in plain.styleSheet()
    assert theme.STENCIL not in plain.styleSheet()
    assert theme.STENCIL_DIM in plain.styleSheet()


def test_the_column_head_carries_the_claim_the_value_gave_up(app):
    """Rule 5 did not stop applying - it moved to where a timing screen
    declares what a column is."""
    from pitcrew.ui.widgets import StencilLabel

    screen = PracticeScreen()
    # The one the screen actually built and parented, not a fresh throwaway:
    # an unparented head widget is collected out from under the assertion.
    derived = [w for w in screen.head_view.widget().findChildren(StencilLabel)
               if w.text() in ("S1", "S2", "S3")]
    assert len(derived) == 3, "the sector heads are not there to carry it"
    for head in derived:
        assert theme.DERIVED in head.styleSheet()


def test_a_mark_is_the_ink_and_it_survives_a_re_ink(app):
    """The rack re-inks a whole row whenever a mark changes. A raw
    `setStyleSheet` used to wipe the mark, so a lap held its purple until the
    first time anything on its row was touched."""
    screen = PracticeScreen()
    screen.set_laps([_lap(1, 100_000), _lap(2, 99_000)])
    marked = screen._row_widgets[1].time_label
    assert theme.BEST_STINT in marked.styleSheet()
    marked.set_ink(theme.STENCIL_DIM)
    assert theme.BEST_STINT in marked.styleSheet(), "the re-ink wiped the mark"


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
