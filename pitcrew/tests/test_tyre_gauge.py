"""The four-corner tyre gauge, and where it is allowed to appear.

GT7 exposes no tyre wear channel, so the driver's reading of the in-game gauge
is the only figure anchored to the game's own model. That makes this widget
the highest-value input on the Practice screen, and makes two of its
behaviours load-bearing rather than cosmetic:

* **Empty means unread, not zero.** A zero is a fresh tyre and would be
  believed all the way into a stint length.
* **A tied maximum names no corner.** Nominating one of a tied pair invents
  an asymmetry the driver never saw.
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from pitcrew.ui.practice_screen import LapRow, RackRow, stint_end_ids
from pitcrew.ui.widgets import TyreGauge, TyreGaugeSet, wear_colour, wear_phase

from .test_controller import qt_app  # noqa: F401


def drag_to(gauge: TyreGauge, fraction: float) -> None:
    """Press at the depth that corresponds to `fraction`, as the driver would."""
    y = gauge.height() * fraction
    point = QPointF(gauge.width() / 2, y)
    gauge.mousePressEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, point, Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))


def a_lap(lap_id: int, **overrides) -> LapRow:
    fields = dict(lap_id=lap_id, lap_num=lap_id, lap_time_ms=94_000,
                  fuel_used=3.4)
    fields.update(overrides)
    return LapRow(**fields)


# ----------------------------------------------------------------- the gauge

def test_a_gauge_starts_unread_rather_than_at_zero(qt_app):  # noqa: F811
    """Zero is a fresh tyre. Not-read is not a value at all."""
    assert TyreGauge("fl").fraction() is None


def test_dragging_down_fills_the_gauge(qt_app):  # noqa: F811
    gauge = TyreGauge("fl")
    drag_to(gauge, 0.75)
    assert gauge.fraction() == 0.75


def test_a_drag_cannot_leave_the_box(qt_app):  # noqa: F811
    """Past the bottom is 100% consumed, not 130%."""
    gauge = TyreGauge("fl")
    drag_to(gauge, 1.4)
    assert gauge.fraction() == 1.0
    drag_to(gauge, -0.3)
    assert gauge.fraction() == 0.0


def test_the_gauge_is_reachable_without_a_mouse(qt_app):  # noqa: F811
    """A precise drag is not the only way in."""
    gauge = TyreGauge("fl")
    assert gauge.focusPolicy() == Qt.FocusPolicy.StrongFocus
    gauge.setFraction(0.50)
    gauge.keyPressEvent(_key(Qt.Key.Key_Up))
    assert gauge.fraction() == 0.55
    gauge.keyPressEvent(_key(Qt.Key.Key_PageDown))
    assert gauge.fraction() == 0.30


def test_a_gauge_can_be_cleared_back_to_unread(qt_app):  # noqa: F811
    """Clearing is its own action - dragging to the bottom means 100% worn."""
    gauge = TyreGauge("fl")
    gauge.setFraction(0.6)
    gauge.keyPressEvent(_key(Qt.Key.Key_Delete))
    assert gauge.fraction() is None


def test_the_fill_follows_the_models_own_phases(qt_app):  # noqa: F811
    """The bands are 0.85/w's bands, not decoration."""
    assert wear_phase(0.30) == "flat"
    assert wear_phase(0.70) == "linear"
    assert wear_phase(0.95) == "cliff"
    assert wear_colour(0.30) != wear_colour(0.70) != wear_colour(0.95)


# ------------------------------------------------------------------- the set

def test_the_set_reports_every_corner_separately(qt_app):  # noqa: F811
    gauges = TyreGaugeSet()
    gauges.setValues({"fl": 0.8, "fr": 0.4, "rl": 0.3, "rr": None})
    assert gauges.values() == {"fl": 0.8, "fr": 0.4, "rl": 0.3, "rr": None}


def test_the_worst_corner_is_marked(qt_app):  # noqa: F811
    gauges = TyreGaugeSet()
    gauges.setValues({"fl": 0.8, "fr": 0.4, "rl": 0.3, "rr": 0.3})
    assert gauges._gauges["fl"]._limiting is True
    assert gauges._gauges["fr"]._limiting is False


def test_four_equal_corners_mark_none_of_them(qt_app):  # noqa: F811
    """With nothing to choose between, pointing at one is a fabrication."""
    gauges = TyreGaugeSet()
    gauges.setValues({"fl": 0.5, "fr": 0.5, "rl": 0.5, "rr": 0.5})
    assert not any(g._limiting for g in gauges._gauges.values())


def test_loading_values_does_not_fire_a_save(qt_app):  # noqa: F811
    """Rebuilding the rack must not look like the driver made an edit."""
    gauges = TyreGaugeSet()
    seen = []
    gauges.changed.connect(lambda: seen.append(1))
    gauges.setValues({"fl": 0.8, "fr": 0.4, "rl": 0.3, "rr": 0.3})
    assert seen == []


# ------------------------------------------------- where the gauge belongs

def test_the_last_lap_of_the_run_ends_a_stint():
    rows = [a_lap(1), a_lap(2), a_lap(3)]
    assert stint_end_ids(rows) == {3}


def test_an_in_lap_ends_a_stint():
    rows = [a_lap(1), a_lap(2, is_pit_lap=True), a_lap(3)]
    assert stint_end_ids(rows) == {2, 3}


def test_a_compound_change_ends_the_stint_before_it():
    """The set came off between these two laps, so lap 2 is where it ended."""
    rows = [a_lap(1, compound="RS"), a_lap(2, compound="RS"),
            a_lap(3, compound="RM"), a_lap(4, compound="RM")]
    assert stint_end_ids(rows) == {2, 4}


def test_striking_the_final_lap_moves_the_gauge_back_not_away():
    """The reading still belongs somewhere - to the last lap that counts."""
    rows = [a_lap(1), a_lap(2), a_lap(3, excluded=True)]
    assert stint_end_ids(rows) == {2}


def test_a_lap_that_already_has_a_reading_keeps_its_gauge():
    """Hiding the control would hide data that is still stored."""
    rows = [a_lap(1, wear_fl=0.4), a_lap(2), a_lap(3)]
    assert stint_end_ids(rows) == {1, 3}


def test_only_a_stint_end_row_is_given_a_gauge(qt_app):  # noqa: F811
    plain = RackRow(a_lap(1), 94_000, stint_end=False)
    ending = RackRow(a_lap(2), 94_000, stint_end=True)
    assert plain.gauges is None
    assert ending.gauges is not None


def test_a_gauge_edit_reaches_the_row(qt_app):  # noqa: F811
    """What the driver drags is what gets persisted.

    **Through the popup now**, not off the row. The four gauges left the row
    on 5 Sep 2026 - laid out as the car they are 140px deep, and they put
    three laps in a 950px window on the screen built for comparing laps. The
    gauges themselves are unchanged and still dragged; what changed is that
    the row shows the corner that ends the stint and opens the four on click.
    So the path this asserts is the whole path: drag a gauge, and the row
    behind the rack has the number.
    """
    row = a_lap(1)
    widget = RackRow(row, 94_000, stint_end=True)
    seen = []
    widget.changed.connect(seen.append)

    widget.gauges._open()
    try:
        widget.gauges._popup.gauges._gauges["fl"].setFraction(0.62)
        assert row.wear_fl == 0.62
        assert row.worst_wear == 0.62
        assert seen == [1]
        # And the cell says which corner is the one that ends the stint,
        # which is the figure the wear model runs on.
        assert widget.gauges.worst() == ("fl", 0.62)
        assert "FL" in widget.gauges.text()
    finally:
        widget.gauges._popup.close()


def test_a_cell_with_nothing_read_is_struck_not_a_zero(qt_app):  # noqa: F811
    """Rule 3 at the wear column: no reading is not a wear of zero, and a
    fresh set is exactly what a zero would claim."""
    from pitcrew.ui import theme

    widget = RackRow(a_lap(1), 94_000, stint_end=True)
    assert widget.gauges.worst() is None
    assert widget.gauges.text() == "—"
    assert theme.STRUCK.lower() in widget.gauges.styleSheet().lower()


def _key(key: Qt.Key) -> object:
    from PyQt6.QtGui import QKeyEvent
    return QKeyEvent(QKeyEvent.Type.KeyPress, key,
                     Qt.KeyboardModifier.NoModifier)
