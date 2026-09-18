"""Plan row 5.21 - the board's lap-time panel, its three lights, the practice
page, and the controller that feeds them outside a race."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from pitcrew.controller import PitCrewController  # noqa: E402
from pitcrew.ui import theme  # noqa: E402
from pitcrew.ui.driver_view import (  # noqa: E402
    DriverState,
    DriverView,
    abs_light,
    format_delta,
    format_lap_ms,
    tcs_light,
    wet_light,
)


@pytest.fixture(scope="session")
def qt_app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------ words and inks

def test_times_and_deltas_are_drawn_as_a_timing_screen_draws_them():
    assert format_lap_ms(92_418) == "1:32.418"
    assert format_lap_ms(None) == "-:--.---"
    assert format_delta(-0.2141) == "-0.214"
    assert format_delta(0.3) == "+0.300"
    assert format_delta(None) == "--.---"


def test_wet_lights_only_on_a_reading_and_never_says_dry_without_one():
    assert wet_light("wet")[2] == theme.WET_LIGHT
    assert wet_light("mixed")[2] is not None
    word, sub, ink = wet_light("dry")
    assert word == "dry" and ink is None
    word, sub, ink = wet_light(None)
    assert word == "wet" and sub == "cannot see" and ink is None


def test_abs_names_the_setting_and_lights_lock_as_derived():
    word, sub, ink = abs_light("Weak", False)
    assert word == "abs Weak" and ink is None
    word, sub, ink = abs_light("Weak", True)
    assert word == "lock" and ink is not None and "derived" in sub
    assert "unknown" in abs_light(None, True)[1]


def test_tcs_with_no_packet_is_no_signal_not_off():
    assert tcs_light(None)[1] == "no signal"
    assert tcs_light(True)[2] is not None
    assert tcs_light(False)[2] is None


# ------------------------------------------------------------ the view

def test_the_diff_is_green_ahead_and_amber_behind_and_names_its_tyre(qt_app):
    from pitcrew.ui.driver_view import GOOD, NEAR

    view = DriverView()
    view.update_state(DriverState(lap_time_ms=61_000, delta_s=-0.5,
                                  session_best_ms=90_000, predicted_ms=89_500,
                                  reference_compound="RS", file_best_ms=89_000,
                                  delta_file_s=0.5))
    panel = view.lap_panel_top
    assert panel.diff.value.text() == "-0.500"
    assert GOOD in panel.diff.value.styleSheet()
    # **The line the panel was GIVEN**: it is elided to a width now, and the
    # offscreen face is 27 px a character where the rig's is 16.
    assert "RS session best 1:30.000" in panel.note.full_text()
    assert "RS on file 1:29.000 (+0.500)" in panel.note.full_text()
    view.update_state(DriverState(delta_s=0.25, reference_compound="RS"))
    assert NEAR in panel.diff.value.styleSheet()
    view.update_state(DriverState(delta_why="compound not set"))
    assert panel.diff.value.text() == "--.---"
    assert "compound not set" in panel.note.full_text()


def test_practice_swaps_the_race_rows_for_the_lead_lap_panel(qt_app):
    view = DriverView()
    view.resize(2480, 1050)
    view.show()
    qt_app.processEvents()
    view.update_state(DriverState(session_kind="practice"))
    qt_app.processEvents()
    assert view.lower.currentWidget() is view.leading_lap
    assert not view.lap_panel_top.isVisible()
    view.update_state(DriverState(session_kind="race"))
    qt_app.processEvents()
    assert view.lower.currentWidget() is not view.leading_lap
    assert view.lap_panel_top.isVisible()
    view.hide()


def test_a_lit_lamp_paints_its_fill(qt_app):
    """The first render drew a lit TCS lamp's dark word on an unpainted
    background - invisible. **Asserted against rendered pixels**, not against
    the mechanism: the fill was a styled background then and is painted by
    `_Face` now (the wipe, 15 Sep 2026), and a test of the attribute would
    have passed on a lamp that painted nothing either way."""
    from PyQt6.QtGui import QColor

    from pitcrew.ui.driver_view import NEAR

    view = DriverView()
    view.update_state(DriverState(tcs_active=True))
    assert view.tcs_light.lit
    lamp = view.tcs_light
    lamp.resize(300, 90)
    image = lamp.grab().toImage()
    middle = image.pixelColor(image.width() // 8, image.height() // 2)
    assert middle.name() == QColor(NEAR).name()


# ------------------------------------------------------------ the controller

class _Practice:
    def __init__(self, intent="race", compound=None):
        self._intent, self._compound = intent, compound

    def practice_intent(self):
        return self._intent

    def starting_compound(self):
        return self._compound

    def rows(self):
        return []


class _Stub:
    _driver_board_state = PitCrewController._driver_board_state
    # The top line is the last call, or `Voice.health`'s reason he did
    # not hear it. Bound off the real class; no `voice` here takes the
    # guarded branch and the last call stands.
    _board_call_now = PitCrewController._board_call_now
    _board_temps = PitCrewController._board_temps
    _split_rates = PitCrewController._split_rates
    _board_live_fields = PitCrewController._board_live_fields
    _tag_practice_compound = PitCrewController._tag_practice_compound
    _fitted_compound = PitCrewController._fitted_compound
    _started_compound = None

    def __init__(self, *, intent="race", live=None):
        from pitcrew.race.tyre_split import SplitHistory

        self.race = None
        self.session_kind = "practice"
        self.practice = _Practice(intent)
        self.bridge = SimpleNamespace(board_live=live, last_packet=None,
                                      _abs_setting="Weak",
                                      recent_corner_means=lambda *a, **k: None)
        self.hud = SimpleNamespace(wet_now=lambda: "wet", compound_now=lambda: None)
        self._board_call = None
        self._splits = SplitHistory()
        self.tagged = []
        self.store = SimpleNamespace(
            set_lap_compound=lambda lap_id, c: self.tagged.append((lap_id, c)))

    def _event_record(self):
        return None


def test_a_practice_board_carries_the_lap_panel_and_lights_and_nothing_race():
    from pitcrew.race.board_live import BoardLive
    from pitcrew.analysis.runs import FOR_QUALIFYING

    live = BoardLive()
    live.set_compound("RM")
    got = _Stub(live=live)._driver_board_state()
    assert got.session_kind == "practice"
    assert got.wet == "wet" and got.abs_setting == "Weak"
    assert got.reference_compound == "RM" and got.compound == "RM"
    assert got.laps_to_box is None and got.ahead is None and got.position is None
    assert _Stub(intent=FOR_QUALIFYING, live=live)._driver_board_state() \
        .session_kind == "qualifying"


def test_no_session_is_a_blank_board():
    stub = _Stub()
    stub.session_kind = None
    assert stub._driver_board_state() == DriverState()


def test_the_start_compound_tags_laps_until_the_first_pit_lap():
    stub = _Stub()
    stub._started_compound = "RS"
    first = SimpleNamespace(compound=None, is_pit_lap=False, lap_num_in_session=1)
    stub._tag_practice_compound(1, first)
    assert first.compound == "RS"
    pit = SimpleNamespace(compound=None, is_pit_lap=True, lap_num_in_session=2)
    stub._tag_practice_compound(2, pit)
    # The in-lap is still on the set he started on; after it, the declaration
    # is no evidence about the tyre on the car.
    assert pit.compound == "RS"
    after = SimpleNamespace(compound=None, is_pit_lap=False, lap_num_in_session=3)
    stub._tag_practice_compound(3, after)
    assert after.compound is None


def test_a_settled_hud_label_tags_the_lap_before_any_declaration():
    stub = _Stub()
    stub._started_compound = "RS"
    stub.hud = SimpleNamespace(wet_now=lambda: None, compound_now=lambda: "RM")
    row = SimpleNamespace(compound=None, is_pit_lap=False, lap_num_in_session=1)
    stub._tag_practice_compound(1, row)
    assert row.compound == "RM" and stub.tagged == [(1, "RM")]


def test_a_pit_lap_is_never_tagged_off_the_label():
    """The set can change inside the lap, so the label at the line may be the
    new tyre on a lap mostly driven on the old one."""
    stub = _Stub()
    stub._started_compound = "RS"
    stub.hud = SimpleNamespace(wet_now=lambda: None, compound_now=lambda: "RM")
    row = SimpleNamespace(compound=None, is_pit_lap=True, lap_num_in_session=4)
    stub._tag_practice_compound(4, row)
    assert row.compound == "RS"


def test_the_board_references_follow_the_label_on_the_car():
    from pitcrew.race.board_live import BoardLive

    live = BoardLive()
    live.set_compound("RS")
    stub = _Stub(live=live)
    stub.hud = SimpleNamespace(wet_now=lambda: None, compound_now=lambda: "RM")
    assert stub._driver_board_state().reference_compound == "RM"
