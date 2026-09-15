"""Rd 9, 15 Sep 2026 - the first race run with the phone strip.

Three faults he reported from one night, and the redesign that followed:

* **Leading, the board and the phone showed a car ahead** - "Car #124, 0.1,
  catching 10.6 s a lap" - for eight laps, and the voice said it every other
  lap. An unread interval box is no reading, so the trend kept its last one.
* **The ultrawide board was wider than the monitor** (2716 px on a 2560
  panel). The phone dropping swapped the race pages, and for one call both
  lap panels stood in one row.
* **The strip's bottom row overlapped** - captions ran under the lamps.

And his pick for the redesign, "motion as signal": a block that changes slot
moves there, and only an instruction floods.
"""
from __future__ import annotations

import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from pitcrew.race import calls as C  # noqa: E402
from pitcrew.race.gaps import GapTrend  # noqa: E402
from pitcrew.ui.driver_view import (  # noqa: E402
    GROUND, NEAR, NOBODY_AHEAD, DriverState, DriverView, GapView, _Stat,
    fit_on_screen, gap_block)
from pitcrew.ui.strip import (  # noqa: E402
    CENTRE_BOX, SUBJECT_AHEAD, SUBJECT_FUEL_TO_STOP, SUBJECT_LAPS_TO_STOP,
    StripComposer)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _trend(side: str, *reads) -> GapTrend:
    trend = GapTrend(side=side)
    for lap, gap in reads:
        trend.note(lap, gap, subject="Car #124")
    return trend


# ----------------------------------------------------------- nobody there

def test_the_leader_has_no_car_ahead_whatever_the_trend_last_read():
    """The exact night: 0.1 read on the lap the two cars ahead boxed."""
    state = C.RaceState(position=3, field_size=20)
    state.gap_ahead = _trend("ahead", (15, 2.3), (16, 0.1))
    state.gap_ahead_name = "Car #124"
    assert state.gap_ahead.latest() == 0.1
    state.position = 1
    assert state.gap_ahead is None
    assert state.gap_ahead_name is None
    assert state.nobody_on("ahead")


def test_the_chase_call_is_silent_while_leading():
    """George said "Car 124 0.1 ahead, 7 or 8 laps to go" three times."""
    state = C.RaceState(position=1, field_size=20, lap=20, laps_total=28)
    state.gap_ahead = _trend("ahead", (19, 0.1), (20, 0.1))
    assert C._chase(state) is None


def test_dropping_back_shows_nothing_until_the_board_is_read_again():
    """The pre-lead reading is about a car that may be anywhere now."""
    trend = _trend("ahead", (16, 0.1))
    state = C.RaceState(position=1, field_size=20)
    state.gap_ahead = trend
    assert state.gap_ahead is None
    state.position = 2
    assert state.gap_ahead is None             # still the old reading
    trend.note(18, 1.4, subject="Car #7")
    assert state.gap_ahead is trend and state.gap_ahead.latest() == 1.4


def test_the_last_car_has_nobody_behind_and_the_middle_has_both():
    state = C.RaceState(position=20, field_size=20)
    behind = _trend("behind", (3, 0.9))
    state.gap_behind = behind
    state.gap_ahead = _trend("ahead", (3, 1.1))
    assert state.gap_behind is None and state.gap_ahead is not None
    state.position = 12
    assert state.gap_behind is None             # nothing read since
    behind.note(4, 0.8)
    assert state.gap_behind is behind


def test_no_position_yet_hides_nothing():
    state = C.RaceState(gap_ahead=_trend("ahead", (1, 2.0)))
    assert state.position is None
    assert state.gap_ahead is not None


def test_an_empty_side_says_why_rather_than_no_gap_read():
    assert gap_block(GapView(note=NOBODY_AHEAD)).sub == NOBODY_AHEAD
    assert gap_block(None).sub == "no gap read"
    assert gap_block(GapView()).sub == "no gap read"


# ----------------------------------------------------------- the strip

def racing(**kw) -> DriverState:
    base = dict(has_plan=True, laps_to_box=4.0, box_on_lap=14,
                fuel_to_stop=0.3, laps_of_fuel=4.3,
                ahead=GapView(seconds=3.4, note="steady"),
                behind=GapView(seconds=2.6, note="steady"))
    base.update(kw)
    return DriverState(**base)


def test_a_block_keeps_its_subject_as_it_changes_slot():
    """What lets the page fly laps-to-the-stop out to the flank a car took."""
    composer = StripComposer()
    quiet = composer.compose(racing())
    assert quiet["centre"]["subject"] == SUBJECT_LAPS_TO_STOP
    assert quiet["left"]["subject"] == SUBJECT_AHEAD
    close = composer.compose(racing(ahead=GapView(seconds=0.6)))
    assert close["centre"]["subject"] == SUBJECT_AHEAD
    assert close["left"]["subject"] == SUBJECT_LAPS_TO_STOP
    short = composer.compose(racing(fuel_to_stop=-0.2))
    assert short["centre"]["subject"] == SUBJECT_FUEL_TO_STOP
    assert short["extra"] is None


@pytest.mark.parametrize("payload", [
    racing(), racing(ahead=GapView(seconds=0.5)), racing(fuel_to_stop=-0.3),
    racing(in_box=True, release_in_s=4.0, fuel_target_l=40.0, fuel_l=10.0),
    DriverState(session_kind="practice")])
def test_no_two_blocks_on_one_payload_share_a_subject(payload):
    """A duplicate transition name makes the browser skip the morph."""
    got = StripComposer().compose(payload)
    subjects = [got[k]["subject"] for k in ("left", "centre", "right", "extra")
                if got.get(k)]
    assert len(subjects) == len(set(subjects))


def test_only_an_instruction_floods_not_a_number_to_watch():
    composer = StripComposer()
    assert composer.compose(racing(laps_to_box=2.0))["centre"]["tone"] == "urgent"
    assert composer.compose(racing(laps_to_box=2.0))["centre"]["act"] is False
    now = composer.compose(racing(laps_to_box=0.0, laps_past_box=0))
    assert now["centre"]["id"] == CENTRE_BOX and now["centre"]["act"] is True
    assert composer.compose(racing(fuel_to_stop=-0.1))["centre"]["act"] is True
    assert composer.compose(racing(ahead=GapView(seconds=0.4, urgent=True))
                            )["centre"]["act"] is False


def test_the_page_draws_both_rows_on_one_grid():
    """The two readings take the width, the lamps a thin band under them.

    16 Sep 2026, the driver: the lamps "only need to be very small and
    different coloured for visibility", and the room they had goes to fuel in
    hand and the lap against the plan's target. So the readings are row 2
    across all three columns and the lamps are row 3.
    """
    from pitcrew.ui.strip_server import PAGE

    page = PAGE.read_text(encoding="utf-8")
    assert "#extras { grid-area: 2 / 1 / 3 / 4;" in page
    assert "#lights { grid-area: 3 / 1 / 4 / 4;" in page
    # The lamp keeps its colour and loses its reason line and its height.
    assert ".light .lsub { display: none; }" in page
    assert 'id="extra2"' in page and "item(\"extra2\", d.extra2" in page
    assert "startViewTransition" in page and "data.act === true" in page


# ----------------------------------------------------------- the ultrawide

def test_a_window_is_never_bigger_than_its_screen_and_stays_where_he_put_it():
    """The first version also pulled it wholly on screen, every tick - and
    parked partly off the edge is how he reaches the app behind it. It could
    not be moved at all, and he had to quit the app (15 Sep 2026)."""
    screen = (1920, 0, 2560, 1080)
    assert fit_on_screen((1682, 237, 2716, 1055), screen) == (1682, 237, 2560, 1055)
    assert fit_on_screen((2000, 10, 2480, 1050), screen) == (2000, 10, 2480, 1050)
    assert fit_on_screen((4400, -40, 800, 400), screen) == (4400, -40, 800, 400)


def test_a_board_he_dragged_part_off_the_edge_is_not_pulled_back(app):
    from pitcrew.ui.driver_view import DriverWindow

    window = DriverWindow()
    screen = QApplication.instance().primaryScreen().geometry()
    window.show()
    app.processEvents()
    window.move(screen.x() + 40, screen.y() + screen.height() - 120)
    app.processEvents()
    before = window.pos()
    for _ in range(4):                      # the board's 250 ms tick
        window.update_state(racing(session_kind="race"))
        app.processEvents()
    assert window.pos() == before
    window.close()


def test_a_reason_nobody_wrote_short_does_not_widen_the_board(app):
    """Sardegna practice: the analysis's own diagnostic under S1/S2/S3 took
    the board to 2,702 px, twice in one evening."""
    from pitcrew.race.board_live import SectorsView

    reason = ("the car jumped 167 m in one frame (2x) - a reset or a garage "
              "return, so every distance after it is against a different axis "
              "than the lines were drawn on")
    view = DriverView()
    view.update_state(DriverState(session_kind="practice"))
    plain = view.sector_panel.minimumSizeHint().width()
    view.update_state(DriverState(session_kind="practice", sectors=SectorsView(
        why=reason, cut="thirds of the lap - not GT7's")))
    note = view.sector_panel.note
    assert reason in note.full_text() and reason in note.toolTip()
    assert note.width() <= note.MAX_W
    assert view.sector_panel.minimumSizeHint().width() <= max(plain, note.MAX_W)


def test_the_phone_dropping_does_not_grow_the_board(app):
    """Shown first, the lap panel stood beside the sectors for one call and
    the window grew to fit both - and was never shrunk back."""
    # **Measured as the window's width against its widest page**, because a
    # window keeps whatever it was grown to: with the panels shown before
    # hidden, this view came out 4,574 px wide against pages of 3,068 and
    # 3,300 offscreen - the page minimum plus the second panel plus the gap.
    view = DriverView()
    phone = racing(strip_live=True, session_kind="race")
    gap = replace(phone, strip_live=False)
    view.show()
    widest = 0
    for state in (phone, gap, phone, gap):
        view.update_state(state)
        app.processEvents()
        widest = max(widest, view.minimumSizeHint().width())
    assert view.width() <= widest
    view.close()


def test_an_instruction_floods_its_block_and_a_trend_does_not(app):
    stat = _Stat("in hand to the stop")
    stat.set_flood()
    stat.show_value("-0.4", "3.2 laps aboard", urgent=True)
    assert stat.fill_showing() == NEAR and GROUND in stat.value.styleSheet()
    stat.show_value("2", "plan: lap 12", urgent=True, act=False)
    assert stat.fill_showing() is None and NEAR in stat.value.styleSheet()
    gap = _Stat("behind")
    gap.show_value("0.7", "he is catching", urgent=True)
    assert gap.fill_showing() is None
