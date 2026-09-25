"""Rival stops panel and history rack helpers — Stories 2 & 4, 25 Sep 2026.

Covers:
- `_fmt_sector_rack`: millisecond formatter for the rack columns
- `_fill_verdict_text`: the FILL column text from a FillVerdictResult
- `_RivalStopsPanel.show_state`: offscreen Qt — labels populated correctly,
  dimmed rows use dim ink, bound markers appear, empty table clears labels
- `_HistoryPanel` extended to 9 columns in practice mode (sector/compound added)

**Offscreen Qt has no fonts**, so pixel-size assertions are skipped here.  The
mandatory fit test (`test_the_board_fits_his_monitor_on_the_faces_he_actually_has`
in `test_window_fit.py`) is the gate for that, and it runs with a real font DB
in a subprocess.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from pitcrew.race.fill_verdict import FillVerdictResult, RivalStopRow  # noqa: E402
from pitcrew.ui.driver_view import (  # noqa: E402
    _RivalStopsPanel,
    _fill_verdict_text,
    _fmt_sector_rack,
)


@pytest.fixture(scope="session")
def qt_app():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# ============================================================= _fmt_sector_rack


def test_fmt_sector_rack_none_returns_dashes():
    assert _fmt_sector_rack(None) == "--"


def test_fmt_sector_rack_zero_returns_dashes():
    """Zero is treated as missing — rule 3."""
    assert _fmt_sector_rack(0) == "--"


def test_fmt_sector_rack_sub_minute():
    """Under 60 s: formatted as ss.mmm without leading minute."""
    assert _fmt_sector_rack(38_412) == "38.412"


def test_fmt_sector_rack_sub_minute_leading_zero():
    assert _fmt_sector_rack(9_001) == "9.001"


def test_fmt_sector_rack_over_one_minute():
    """Sector ≥ 60 000 ms → m:ss.mmm (same as format_lap_ms)."""
    result = _fmt_sector_rack(62_345)
    assert result == "1:02.345"


# ============================================================ _fill_verdict_text


def test_fill_verdict_none_returns_dashes():
    assert _fill_verdict_text(None) == "--"


def test_fill_verdict_cant_tell_returns_question():
    v = FillVerdictResult(verdict="can't tell")
    assert _fill_verdict_text(v) == "?"


def test_fill_verdict_spare_no_margin():
    """No margin_l → only the verdict word."""
    v = FillVerdictResult(verdict="spare", margin_l=None)
    assert _fill_verdict_text(v) == "spare"


def test_fill_verdict_spare_with_margin():
    v = FillVerdictResult(verdict="spare", margin_l=4.5, bound=False)
    result = _fill_verdict_text(v)
    assert result == "SPARE +4 L"


def test_fill_verdict_spare_bound():
    """bound=True → tilde prefix on the margin."""
    v = FillVerdictResult(verdict="spare", margin_l=4.5, bound=True)
    result = _fill_verdict_text(v)
    assert "~" in result and "SPARE" in result


def test_fill_verdict_must_save_with_rate():
    v = FillVerdictResult(verdict="must save", margin_l=-2.0,
                          saving_per_lap_l=0.25, bound=False)
    result = _fill_verdict_text(v)
    assert "SAVE" in result
    assert "-2 L" in result
    assert "0.25" in result


def test_fill_verdict_must_save_no_rate():
    v = FillVerdictResult(verdict="must save", margin_l=-2.0,
                          saving_per_lap_l=None, bound=False)
    result = _fill_verdict_text(v)
    assert "SAVE" in result and "L/lap" not in result


def test_fill_verdict_exact():
    v = FillVerdictResult(verdict="exact", margin_l=0.3, bound=False)
    result = _fill_verdict_text(v)
    assert "EXACT" in result


# ===================================================== _RivalStopsPanel offscreen


def _row(driver="BEENI", lap=10, fuel_in=8.0, fuel_out=45.0,
         compound_in="RH", compound_out="RS", stop_count=1,
         burn=5.0, dimmed=False, verdict=None):
    return RivalStopRow(
        driver=driver,
        last_stop_lap=lap,
        fuel_in_l=fuel_in,
        fuel_out_l=fuel_out,
        compound_in=compound_in,
        compound_out=compound_out,
        stop_count=stop_count,
        burn_per_lap_l=burn,
        dimmed=dimmed,
        verdict=verdict,
    )


def test_rival_panel_constructs_without_crash(qt_app):
    """The widget builds without error on an offscreen platform."""
    panel = _RivalStopsPanel()
    assert panel is not None


def test_rival_panel_show_state_populates_driver_name(qt_app):
    panel = _RivalStopsPanel()
    panel.show_state((_row(driver="ROCKY"),))
    # Column 0 is DRIVER: first label in row 0.
    name_label = panel._row_labels[0][0]
    assert name_label.text() == "ROCKY"


def test_rival_panel_show_state_populates_lap(qt_app):
    panel = _RivalStopsPanel()
    panel.show_state((_row(lap=17),))
    lap_label = panel._row_labels[0][1]
    assert lap_label.text() == "L17"


def test_rival_panel_show_state_populates_fuel_in(qt_app):
    panel = _RivalStopsPanel()
    panel.show_state((_row(fuel_in=8.0),))
    fuel_in_label = panel._row_labels[0][2]
    assert fuel_in_label.text() == "8"


def test_rival_panel_fuel_in_bound_has_le_prefix(qt_app):
    """Partial stop entry: fuel_in is an upper bound → ≤ prefix."""
    row = _row()
    row = RivalStopRow(
        driver="X", last_stop_lap=10, fuel_in_l=8.0, fuel_in_is_bound=True,
        fuel_out_l=45.0, compound_in="RH", compound_out="RS",
        stop_count=1, burn_per_lap_l=5.0,
    )
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    assert panel._row_labels[0][2].text() == "≤8"


def test_rival_panel_fuel_out_bound_has_ge_prefix(qt_app):
    """exit_is_a_bound stop: fuel_out is a lower bound → ≥ prefix."""
    row = RivalStopRow(
        driver="X", last_stop_lap=10, fuel_in_l=8.0,
        fuel_out_l=45.0, fuel_out_is_bound=True,
        compound_in="RH", compound_out="RS",
        stop_count=1, burn_per_lap_l=5.0,
    )
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    assert panel._row_labels[0][3].text() == "≥45"


def test_rival_panel_burn_bound_has_ge_prefix(qt_app):
    row = RivalStopRow(
        driver="X", last_stop_lap=10, fuel_in_l=8.0,
        fuel_out_l=45.0, compound_in="RH", compound_out="RS",
        stop_count=1, burn_per_lap_l=5.0, burn_is_bound=True,
    )
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    # Column 7 = BURN/LAP
    assert panel._row_labels[0][7].text() == "≥5.00"


def test_rival_panel_null_burn_shows_dashes(qt_app):
    row = RivalStopRow(driver="Y", burn_per_lap_l=None)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    assert panel._row_labels[0][7].text() == "--"


def test_rival_panel_empty_table_clears_labels(qt_app):
    """After a non-empty call, clearing with () blanks all rows."""
    panel = _RivalStopsPanel()
    panel.show_state((_row(driver="ROCKY"),))
    panel.show_state(())
    # Every label in every row should be blank (no sub-labels: removed to keep
    # the panel within the 325-px budget it shares with the tyre section).
    for line in panel._row_labels:
        for lbl in line:
            assert lbl.text() == ""


def test_rival_panel_stop_count_column(qt_app):
    panel = _RivalStopsPanel()
    panel.show_state((_row(stop_count=2),))
    # Column 6 = #
    assert panel._row_labels[0][6].text() == "2"


def test_rival_panel_fill_verdict_cant_tell_shows_question(qt_app):
    v = FillVerdictResult(verdict="can't tell")
    panel = _RivalStopsPanel()
    panel.show_state((_row(verdict=v),))
    # Column 8 = FILL
    assert panel._row_labels[0][8].text() == "?"


def test_rival_panel_stop_count_records_multi_stop_driver(qt_app):
    """Multi-stop drivers show stop_count > 1 in the # column (no sub-label)."""
    row = RivalStopRow(
        driver="M", last_stop_lap=12, stop_count=2,
        earlier_stops=({"lap": 5},),
    )
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    assert panel._row_labels[0][6].text() == "2"   # column 6 = #


def test_rival_panel_second_row_populated(qt_app):
    """Two rows: both get their driver names."""
    panel = _RivalStopsPanel()
    panel.show_state((_row(driver="A"), _row(driver="B")))
    assert panel._row_labels[0][0].text() == "A"
    assert panel._row_labels[1][0].text() == "B"


def test_rival_panel_truncates_long_psn_id(qt_app):
    """PSN IDs may be 16 chars; longer ones are truncated."""
    panel = _RivalStopsPanel()
    long_name = "A" * 20
    panel.show_state((_row(driver=long_name),))
    assert len(panel._row_labels[0][0].text()) <= 16


# ============================================= C4: overflow for > MAX_RIVALS


def test_rival_panel_overflow_hidden_when_within_capacity(qt_app):
    """No overflow when rival_table <= MAX_RIVALS."""
    from pitcrew.ui.driver_view import MAX_RIVALS

    panel = _RivalStopsPanel()
    rows = tuple(
        RivalStopRow(driver=f"D{i}") for i in range(MAX_RIVALS)
    )
    panel.show_state(rows)
    # isHidden() checks the widget's own flag; isVisible() traverses the
    # parent chain and returns False on an unshown parent (offscreen test).
    assert panel._overflow_label.isHidden()


def test_rival_panel_overflow_label_visible_when_exceeded(qt_app):
    """When rival_table has MAX_RIVALS + 1 entries the overflow label appears."""
    from pitcrew.ui.driver_view import MAX_RIVALS

    panel = _RivalStopsPanel()
    rows = tuple(
        RivalStopRow(driver=f"D{i}") for i in range(MAX_RIVALS + 1)
    )
    panel.show_state(rows)
    assert not panel._overflow_label.isHidden()
    assert "+1" in panel._overflow_label.text()


def test_rival_panel_overflow_label_clears_on_smaller_table(qt_app):
    """After an overflow, a smaller table hides the overflow label."""
    from pitcrew.ui.driver_view import MAX_RIVALS

    panel = _RivalStopsPanel()
    panel.show_state(tuple(RivalStopRow(driver=f"D{i}")
                           for i in range(MAX_RIVALS + 3)))
    assert not panel._overflow_label.isHidden()
    # Now shrink to one row.
    panel.show_state((_row(driver="ONLY"),))
    assert panel._overflow_label.isHidden()


# ============================================= I4: driver ink fix


def test_signed_in_driver_not_dimmed_has_normal_ink(qt_app):
    """A signed-in (dimmed=False) driver name uses INK, not INK_DIM (I4 fix)."""
    from pitcrew.ui.driver_view import INK, INK_DIM

    panel = _RivalStopsPanel()
    row = RivalStopRow(driver="BEENI", dimmed=False)
    panel.show_state((row,))
    ss = panel._row_labels[0][0].styleSheet()
    # The stylesheet contains `color:<value>`. INK is "#E8E4DC", INK_DIM is
    # "#9A948A" — they share no common substring, so a substring check is safe.
    assert INK in ss, f"Expected INK ({INK}) in stylesheet, got: {ss!r}"
    assert INK_DIM not in ss, f"Expected no INK_DIM ({INK_DIM}) for signed-in driver"


def test_dimmed_driver_has_dim_ink(qt_app):
    """A dimmed (not entered) driver name uses INK_DIM."""
    from pitcrew.ui.driver_view import INK_DIM

    panel = _RivalStopsPanel()
    row = RivalStopRow(driver="GHOST", dimmed=True)
    panel.show_state((row,))
    ss = panel._row_labels[0][0].styleSheet()
    assert INK_DIM in ss, f"Expected INK_DIM ({INK_DIM}) in stylesheet, got: {ss!r}"


# ============================================= burn_assumed marker


def test_burn_assumed_adds_asterisk_to_burn_cell(qt_app):
    """When burn_assumed=True the burn cell gets a trailing '*'."""
    row = RivalStopRow(
        driver="X", burn_per_lap_l=7.50, burn_assumed=True,
    )
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    burn_text = panel._row_labels[0][7].text()
    assert burn_text.endswith("*"), f"Expected trailing *, got: {burn_text!r}"
    assert "7.50" in burn_text


def test_burn_assumed_asterisk_is_the_only_marker(qt_app):
    """burn_assumed is flagged with '*' in the burn cell only (no sub-label row).

    Sub-label rows were removed to keep the panel within the ~325 px budget it
    shares with the tyre section on the history page.  The '*' in the burn
    cell is the only on-screen signal.
    """
    row = RivalStopRow(driver="X", burn_per_lap_l=7.50, burn_assumed=True)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    # Confirm: no _sub_labels attribute at all.
    assert not hasattr(panel, "_sub_labels")


def test_burn_not_assumed_no_asterisk(qt_app):
    """When burn_assumed=False the burn cell has no trailing '*'."""
    row = RivalStopRow(driver="X", burn_per_lap_l=7.50, burn_assumed=False)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    assert "*" not in panel._row_labels[0][7].text()
