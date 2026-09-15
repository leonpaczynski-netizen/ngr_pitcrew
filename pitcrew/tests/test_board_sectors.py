"""Last lap S1 / S2 / S3 on the ultrawide, against this session's bests.

Asked for on 15 Sep 2026 when the phone strip freed room on the board. GT7
sends no sectors, so every figure here is `analysis/lap_sectors.py`'s cut and
the panel has to hold the same two locks every best on this board carries -
**the same tyre and the same sector lines** - and never let a lap that does not
count become the best it is measured against.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from pitcrew.analysis.lap_sectors import cut_words  # noqa: E402
from pitcrew.race.board_live import (  # noqa: E402
    NO_LAP_YET, NO_SECTOR_TIMES, BoardLive, SectorsView)
from pitcrew.ui.driver_view import (  # noqa: E402
    DriverState, DriverView, sector_blocks)

LINES = "monza:landmark:2097/3978"
OTHER_LINES = "monza:thirds:1930/3860"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def noted(live, lap_id, times, *, stamp=LINES, compound="RM", counted=True,
          refused=None):
    live.note_sectors(lap_id=lap_id, times_ms=times, stamp=stamp,
                      compound=compound, counted=counted, refused=refused)


# ------------------------------------------------------------ the reader

def test_before_any_lap_it_says_so():
    view = BoardLive().sectors_view(cut_words)
    assert view.times_ms is None and view.why == NO_LAP_YET


def test_the_last_lap_is_set_against_the_best_of_each_sector():
    live = BoardLive()
    noted(live, 1, (38_500, 36_300, 30_700))
    noted(live, 2, (38_200, 36_400, 30_800))
    view = live.sectors_view(cut_words)
    assert view.times_ms == (38_200, 36_400, 30_800)
    assert view.best_ms == (38_200, 36_300, 30_700)
    assert view.set_best == (True, False, False)
    assert view.cut == "at the circuit's landmarks"


def test_an_out_lap_never_becomes_the_best_it_is_measured_against():
    live = BoardLive()
    noted(live, 1, (38_500, 36_300, 30_700))
    noted(live, 2, (37_000, 36_000, 30_000), counted=False)
    view = live.sectors_view(cut_words)
    assert view.best_ms == (38_500, 36_300, 30_700)
    assert view.set_best == (False, False, False)


def test_a_best_on_another_tyre_or_other_lines_is_not_this_ones():
    live = BoardLive()
    noted(live, 1, (37_000, 35_000, 29_000), compound="RS")
    noted(live, 2, (37_500, 35_500, 29_500), stamp=OTHER_LINES)
    noted(live, 3, (38_000, 36_000, 30_000))
    view = live.sectors_view(cut_words)
    assert view.best_ms == (38_000, 36_000, 30_000)
    assert view.set_best == (True, True, True)


def test_a_struck_lap_stops_being_a_best_and_the_next_one_stands():
    live = BoardLive()
    noted(live, 1, (38_000, 36_000, 30_000))
    noted(live, 2, (38_400, 36_200, 30_100))
    live.drop_lap(1)
    view = live.sectors_view(cut_words)
    assert view.best_ms == (38_400, 36_200, 30_100)


def test_a_lap_without_all_three_is_dashes_with_the_cutters_reason():
    live = BoardLive()
    noted(live, 1, (38_000, 36_000, 30_000))
    noted(live, 2, (None, None, None), refused="the lap clock and the distance "
                                               "axis disagree")
    view = live.sectors_view(cut_words)
    assert view.times_ms is None
    assert view.why == "the lap clock and the distance axis disagree"
    noted(live, 3, None)
    assert live.sectors_view(cut_words).why == NO_SECTOR_TIMES


def test_a_new_session_forgets_every_sector():
    live = BoardLive()
    noted(live, 1, (38_000, 36_000, 30_000))
    live.new_session()
    assert live.sectors_view(cut_words).why == NO_LAP_YET


# ------------------------------------------------------------ the words

def test_slower_is_amber_a_best_is_green_and_the_line_names_its_references():
    state = DriverState(sectors=SectorsView(
        times_ms=(38_412, 36_050, 30_719), best_ms=(38_198, 36_050, 30_632),
        set_best=(False, True, False), cut="at the circuit's landmarks",
        compound="RM"))
    (s1, s2, s3), note = sector_blocks(state)
    assert (s1.value, s1.sub, s1.tone) == ("38.412", "+0.214", "urgent")
    assert (s2.value, s2.sub, s2.tone) == ("36.050", "best", "good")
    assert s3.sub == "+0.087"
    assert note == "last lap  ·  vs RM session bests  ·  sectors at the circuit's landmarks"


def test_a_sector_past_a_minute_reads_as_a_clock():
    state = DriverState(sectors=SectorsView(times_ms=(62_345, 70_000, 71_000)))
    (s1, _, _), _ = sector_blocks(state)
    assert s1.value == "1:02.345"


def test_dashes_carry_the_reason_on_the_line_not_under_one_sector():
    state = DriverState(sectors=SectorsView(why="no lap completed yet"))
    blocks, note = sector_blocks(state)
    assert all(block.value == "--.---" and block.sub == "" for block in blocks)
    assert note == "no lap completed yet"


# ------------------------------------------------------------ the board

def test_the_sectors_show_in_practice_and_on_the_phone_page_not_the_fallback(app):
    view = DriverView()
    view.update_state(DriverState(session_kind="practice"))
    assert not view.sector_panel.isHidden()
    view.update_state(DriverState(strip_live=True))
    assert not view.sector_panel.isHidden()
    assert view.lap_panel_top.isHidden()
    # The gap-led page is today's board exactly.
    view.update_state(DriverState(strip_live=False))
    assert view.sector_panel.isHidden()
    assert not view.lap_panel_top.isHidden()


def test_a_page_that_comes_back_is_measured_again_not_drawn_clipped():
    """15 Sep 2026: after the phone page, the fallback's lap panel came back
    at 199 px against a 272 px lap time and drew `:11.41`. The same happened
    going from practice to a race - a label's text changed while its page was
    hidden, and Qt kept the old size.

    **Measured on the real faces, in a subprocess**, for the reason
    `test_the_board_fits_his_monitor_on_the_faces_he_actually_has` gives: the
    offscreen test face is 27 px a character, the row is squeezed at 2560
    either way, and the defect cannot be seen there at all (checked - the
    offscreen version passed with the fix removed). Compared against a board
    that opened on the fallback, so the claim is only that arriving at a page
    lays it out as opening on it does.
    """
    import json
    import subprocess
    import sys
    import textwrap
    from pathlib import Path

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
        from pitcrew.ui.driver_view import DriverView
        from pitcrew.ui.preview import sample_board

        def widths(view):
            view.resize(2560, 1080)
            app.processEvents()
            view.grab()
            return [getattr(view.lap_panel_top, n).value.width()
                    for n in ("lap", "diff", "pred")]

        fallback = replace(sample_board(), strip_live=False)
        fresh = DriverView()
        fresh.update_state(fallback)
        out = {"fresh": widths(fresh)}
        for name, first in (("phone", replace(sample_board(), strip_live=True)),
                            ("practice", sample_board(session_kind="practice"))):
            view = DriverView()
            view.update_state(first)
            widths(view)
            view.update_state(fallback)
            out[name] = widths(view)
        print(json.dumps(out))
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
    assert got["phone"] == got["fresh"], got
    assert got["practice"] == got["fresh"], got


def test_the_panel_draws_what_the_words_say(app):
    view = DriverView()
    view.update_state(DriverState(session_kind="practice", sectors=SectorsView(
        times_ms=(38_412, 36_050, 30_719), best_ms=(38_198, 36_050, 30_632),
        set_best=(False, True, False), compound="RM")))
    assert [box.value.text() for box in view.sector_panel.boxes] == \
        ["38.412", "36.050", "30.719"]
    assert [sub.text() for sub in view.sector_panel.subs] == \
        ["+0.214", "best", "+0.087"]
