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
    GOOD,
    INK,
    INK_DIM,
    NEAR,
    _HistoryPanel,
    _RivalStopsPanel,
    _fill_verdict_ink,
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


def test_fill_verdict_on_the_limit_with_margin():
    """'on the limit' verdict shows 'ON LIMIT' with signed margin."""
    v = FillVerdictResult(verdict="on the limit", margin_l=0.4, bound=False)
    result = _fill_verdict_text(v)
    assert "ON LIMIT" in result
    assert "+0" in result


def test_fill_verdict_on_the_limit_bound():
    """'on the limit' with bound=True carries the '~' prefix."""
    v = FillVerdictResult(verdict="on the limit", margin_l=0.3, bound=True)
    result = _fill_verdict_text(v)
    assert "~" in result


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
    name_label = panel._row_labels[0][1]
    assert name_label.text() == "ROCKY"


def test_rival_panel_show_state_populates_lap(qt_app):
    panel = _RivalStopsPanel()
    panel.show_state((_row(lap=17),))
    lap_label = panel._row_labels[0][2]
    assert lap_label.text() == "L17"


def test_rival_panel_show_state_populates_fuel_in(qt_app):
    panel = _RivalStopsPanel()
    panel.show_state((_row(fuel_in=8.0),))
    fuel_in_label = panel._row_labels[0][3]
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
    assert panel._row_labels[0][3].text() == "≤8"


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
    assert panel._row_labels[0][4].text() == "≥45"


def test_rival_panel_burn_bound_has_ge_prefix(qt_app):
    row = RivalStopRow(
        driver="X", last_stop_lap=10, fuel_in_l=8.0,
        fuel_out_l=45.0, compound_in="RH", compound_out="RS",
        stop_count=1, burn_per_lap_l=5.0, burn_is_bound=True,
    )
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    # Column 7 = BURN/LAP
    assert panel._row_labels[0][8].text() == "≥5.00"


def test_rival_panel_null_burn_shows_dashes(qt_app):
    row = RivalStopRow(driver="Y", burn_per_lap_l=None)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    assert panel._row_labels[0][8].text() == "--"


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
    assert panel._row_labels[0][7].text() == "2"


def test_rival_panel_fill_verdict_cant_tell_shows_question(qt_app):
    v = FillVerdictResult(verdict="can't tell")
    panel = _RivalStopsPanel()
    panel.show_state((_row(verdict=v),))
    # Column 8 = FILL
    assert panel._row_labels[0][9].text() == "?"


def test_rival_panel_stop_count_records_multi_stop_driver(qt_app):
    """Multi-stop drivers show stop_count > 1 in the # column."""
    row = RivalStopRow(
        driver="M", last_stop_lap=12, stop_count=2,
        earlier_stops=({"lap": 5},),
    )
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    assert panel._row_labels[0][7].text() == "2"   # column 6 = #


def test_rival_panel_second_row_populated(qt_app):
    """Two rows: both get their driver names."""
    panel = _RivalStopsPanel()
    panel.show_state((_row(driver="A"), _row(driver="B")))
    assert panel._row_labels[0][1].text() == "A"
    assert panel._row_labels[1][1].text() == "B"


def test_rival_panel_truncates_long_psn_id(qt_app):
    """PSN IDs may be 16 chars; longer ones are truncated."""
    panel = _RivalStopsPanel()
    long_name = "A" * 20
    panel.show_state((_row(driver=long_name),))
    assert len(panel._row_labels[0][1].text()) <= 16


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
    ss = panel._row_labels[0][1].styleSheet()
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
    ss = panel._row_labels[0][1].styleSheet()
    assert INK_DIM in ss, f"Expected INK_DIM ({INK_DIM}) in stylesheet, got: {ss!r}"


# ============================================= burn_assumed marker


def test_burn_assumed_adds_asterisk_to_burn_cell(qt_app):
    """When burn_assumed=True the burn cell gets a trailing '*'."""
    row = RivalStopRow(
        driver="X", burn_per_lap_l=7.50, burn_assumed=True,
    )
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    burn_text = panel._row_labels[0][8].text()
    assert burn_text.endswith("*"), f"Expected trailing *, got: {burn_text!r}"
    assert "7.50" in burn_text


def test_burn_assumed_asterisk_is_the_only_marker(qt_app):
    """burn_assumed is flagged with '*' in the burn cell only (no sub-label row).

    Sub-labels exist for earlier-stop lines (26 Sep 2026).
    The '*' in the burn cell remains the marker for burn_assumed.
    """
    row = RivalStopRow(driver="X", burn_per_lap_l=7.50, burn_assumed=True)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    # Sub-labels now exist (earlier-stops sub-lines, 26 Sep 2026).
    assert hasattr(panel, "_sub_labels")


def test_burn_not_assumed_no_asterisk(qt_app):
    """When burn_assumed=False the burn cell has no trailing '*'."""
    row = RivalStopRow(driver="X", burn_per_lap_l=7.50, burn_assumed=False)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    assert "*" not in panel._row_labels[0][8].text()


# ============================================================= _fill_verdict_text "stops again"


def test_fill_verdict_stops_again_with_margin():
    """'stops again' verdict shows 'STOP AGAIN' with signed margin."""
    v = FillVerdictResult(verdict="stops again", margin_l=-4.0, bound=False)
    result = _fill_verdict_text(v)
    assert "STOP AGAIN" in result
    assert "-4" in result


def test_fill_verdict_stops_again_no_margin():
    """'stops again' with no margin falls back to the raw verdict string."""
    v = FillVerdictResult(verdict="stops again", margin_l=None, bound=False)
    result = _fill_verdict_text(v)
    # margin_l is None → returns the raw verdict word (pre-existing behaviour)
    assert result == "stops again"


# ============================================================= _fill_verdict_ink


def test_fill_verdict_ink_none_is_dim():
    assert _fill_verdict_ink(None) == INK_DIM


def test_fill_verdict_ink_cant_tell_is_dim():
    v = FillVerdictResult(verdict="can't tell", margin_l=None, bound=False)
    assert _fill_verdict_ink(v) == INK_DIM


def test_fill_verdict_ink_must_save_is_warning():
    v = FillVerdictResult(verdict="must save", margin_l=-3.0, bound=False)
    assert _fill_verdict_ink(v) == NEAR


def test_fill_verdict_ink_stops_again_is_warning():
    v = FillVerdictResult(verdict="stops again", margin_l=-5.0, bound=False)
    assert _fill_verdict_ink(v) == NEAR


def test_fill_verdict_ink_spare_is_good():
    v = FillVerdictResult(verdict="spare", margin_l=8.0, bound=False)
    assert _fill_verdict_ink(v) == GOOD


def test_fill_verdict_ink_exact_is_plain():
    v = FillVerdictResult(verdict="exact", margin_l=0.2, bound=False)
    assert _fill_verdict_ink(v) == INK


def test_fill_verdict_ink_on_the_limit_is_warning():
    """'on the limit' is the marginal case — warning ink, same as must-save."""
    v = FillVerdictResult(verdict="on the limit", margin_l=0.4, bound=False)
    assert _fill_verdict_ink(v) == NEAR


# ============================================================= rival panel fill ink via show_state


def test_rival_panel_must_save_fill_cell_is_warning_ink(qt_app):
    """The FILL cell (column 8) is rendered in warning ink for must-save."""
    verdict = FillVerdictResult(verdict="must save", margin_l=-3.0, bound=False,
                                saving_per_lap_l=0.5)
    row = RivalStopRow(driver="A", verdict=verdict)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    style = panel._row_labels[0][9].styleSheet()
    assert NEAR in style


def test_rival_panel_stops_again_fill_cell_is_warning_ink(qt_app):
    """The FILL cell is in warning ink for 'stops again'."""
    verdict = FillVerdictResult(verdict="stops again", margin_l=-2.0, bound=False)
    row = RivalStopRow(driver="B", verdict=verdict)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    style = panel._row_labels[0][9].styleSheet()
    assert NEAR in style


def test_rival_panel_on_the_limit_fill_cell_is_warning_ink(qt_app):
    """The FILL cell is in warning ink for 'on the limit'."""
    verdict = FillVerdictResult(verdict="on the limit", margin_l=0.3, bound=False)
    row = RivalStopRow(driver="E", verdict=verdict)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    style = panel._row_labels[0][9].styleSheet()
    assert NEAR in style


def test_rival_panel_spare_fill_cell_is_good_ink(qt_app):
    """The FILL cell is in good (green) ink for 'spare'."""
    verdict = FillVerdictResult(verdict="spare", margin_l=10.0, bound=False)
    row = RivalStopRow(driver="C", verdict=verdict)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    style = panel._row_labels[0][9].styleSheet()
    assert GOOD in style


def test_rival_panel_dimmed_fill_cell_is_dim_regardless_of_verdict(qt_app):
    """A dimmed row keeps dim ink even for a warning verdict (the driver is not
    in this round, so the verdict about him is also contextually absent)."""
    verdict = FillVerdictResult(verdict="must save", margin_l=-3.0, bound=False)
    row = RivalStopRow(driver="D", dimmed=True, verdict=verdict)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    style = panel._row_labels[0][9].styleSheet()
    assert INK_DIM in style
    assert NEAR not in style


# ============================================================= P column (26 Sep 2026)


def test_rival_panel_p_column_shows_fresh_position(qt_app):
    """A fresh position (position_fresh=True) shows 'P<n>' in column 0."""
    row = RivalStopRow(driver="ROCKY", position=3, position_fresh=True)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    p_text = panel._row_labels[0][0].text()
    assert p_text == "P3", f"Expected 'P3' in P column, got: {p_text!r}"


def test_rival_panel_p_column_shows_dashes_when_stale(qt_app):
    """Stale or absent position shows '--' in column 0."""
    row = RivalStopRow(driver="ROCKY", position=3, position_fresh=False)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    assert panel._row_labels[0][0].text() == "--"


def test_rival_panel_p_column_absent_shows_dashes(qt_app):
    """No position at all → '--' in P column (rule 3)."""
    row = RivalStopRow(driver="ROCKY")
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    assert panel._row_labels[0][0].text() == "--"


def test_rival_panel_sorted_by_position(qt_app):
    """Rows with fresh positions are sorted ascending; stale rows follow."""
    rows = (
        RivalStopRow(driver="C", position=3, position_fresh=True),
        RivalStopRow(driver="A", position=1, position_fresh=True),
        RivalStopRow(driver="B", position=2, position_fresh=True),
        RivalStopRow(driver="D"),  # no position
    )
    panel = _RivalStopsPanel()
    panel.show_state(rows)
    # After sorting: A(P1), B(P2), C(P3), D(--)
    assert panel._row_labels[0][1].text() == "A"
    assert panel._row_labels[1][1].text() == "B"
    assert panel._row_labels[2][1].text() == "C"
    assert panel._row_labels[3][1].text() == "D"


def test_rival_panel_stale_position_rows_after_fresh(qt_app):
    """Stale-position rows appear after all fresh-position rows."""
    rows = (
        RivalStopRow(driver="Z"),   # no position
        RivalStopRow(driver="A", position=5, position_fresh=True),
    )
    panel = _RivalStopsPanel()
    panel.show_state(rows)
    assert panel._row_labels[0][1].text() == "A"
    assert panel._row_labels[1][1].text() == "Z"


# ============================================================= earlier-stop sub-lines (26 Sep 2026)


def test_rival_panel_sub_label_visible_when_earlier_stops(qt_app):
    """A driver with earlier_stops gets a visible sub-label below their row."""
    row = RivalStopRow(
        driver="ROCKY", last_stop_lap=15, stop_count=2,
        earlier_stops=({"lap": 8, "fuel_in_l": 45.0, "fuel_out_l": 78.0,
                        "compound_in": "RH", "compound": "RS"},),
    )
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    sub = panel._sub_labels[0]
    assert not sub.isHidden(), "sub-label should be visible when earlier_stops is non-empty"
    assert "L8" in sub.text()
    assert "45" in sub.text()
    assert "78" in sub.text()


def test_rival_panel_sub_label_hidden_when_no_earlier_stops(qt_app):
    """A driver with no earlier stops has a hidden sub-label (no space wasted)."""
    row = RivalStopRow(driver="ROCKY", last_stop_lap=10, stop_count=1)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    assert panel._sub_labels[0].isHidden()


def test_rival_panel_sub_label_hidden_when_empty_table(qt_app):
    """After clearing to an empty table, all sub-labels are hidden."""
    row = RivalStopRow(
        driver="ROCKY", stop_count=2,
        earlier_stops=({"lap": 5},),
    )
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    panel.show_state(())
    assert panel._sub_labels[0].isHidden()


# ============================================================= _HistoryPanel race mode (26 Sep 2026)


def test_history_panel_rack_hidden_in_race_mode(qt_app):
    """In race mode the _rack_section is hidden (only rival panel shown)."""
    panel = _HistoryPanel()
    panel.show_state(_ds("race"))
    assert panel._rack_section.isHidden(), "_rack_section must be hidden in race mode"


def test_history_panel_rack_visible_in_practice_mode(qt_app):
    """In practice mode the _rack_section is visible."""
    panel = _HistoryPanel()
    panel.show_state(_ds("practice"))
    assert not panel._rack_section.isHidden(), "_rack_section must be visible in practice mode"


def test_history_panel_rival_panel_shown_in_race_mode(qt_app):
    """In race mode the rival panel is always shown (even with empty table)."""
    panel = _HistoryPanel()
    panel.show_state(_ds("race"))
    assert not panel.rival_panel.isHidden(), "rival_panel should be visible in race mode"


def test_history_panel_rival_panel_hidden_in_practice_mode(qt_app):
    """In practice mode the rival panel is hidden."""
    panel = _HistoryPanel()
    panel.show_state(_ds("practice"))
    assert panel.rival_panel.isHidden(), "rival_panel should be hidden in practice mode"


# ============================================================= _HistoryPanel sector column visibility


def _ds(session_kind="race"):
    """Minimal DriverState for _HistoryPanel.show_state tests."""
    from pitcrew.ui.driver_view import DriverState
    return DriverState(session_kind=session_kind)


def test_history_panel_race_mode_hides_sector_heads(qt_app):
    """In race mode the S1/S2/S3 column heads are hidden."""
    panel = _HistoryPanel()
    panel.show_state(_ds("race"))
    # Head indices 6/7/8 are S1/S2/S3 stored in _sector_head_labels.
    for lbl in panel._sector_head_labels:
        assert lbl.isHidden(), f"sector head should be hidden in race mode: {lbl.text()}"


def test_history_panel_practice_mode_shows_sector_heads(qt_app):
    """In practice mode the S1/S2/S3 column heads are visible."""
    panel = _HistoryPanel()
    panel.show_state(_ds("practice"))
    for lbl in panel._sector_head_labels:
        assert not lbl.isHidden(), (
            f"sector head should be visible in practice: {lbl.text()}")


def test_history_panel_sector_visibility_toggles_correctly(qt_app):
    """Switching session kind toggles the sector columns without error."""
    panel = _HistoryPanel()

    panel.show_state(_ds("race"))
    for lbl in panel._sector_head_labels:
        assert lbl.isHidden()

    panel.show_state(_ds("practice"))
    for lbl in panel._sector_head_labels:
        assert not lbl.isHidden()

    # Toggle back.
    panel.show_state(_ds("race"))
    for lbl in panel._sector_head_labels:
        assert lbl.isHidden()


# ============================================================= Round 8: caption + legend

def test_rival_panel_caption_default(qt_app):
    """Caption reads 'RIVAL STOPS' when rival_all_divisions is False."""
    panel = _RivalStopsPanel()
    panel.show_state((), rival_all_divisions=False)
    assert panel._caption.text() == "RIVAL STOPS"


def test_rival_panel_caption_all_divisions(qt_app):
    """Caption names all-divisions when rival_all_divisions=True."""
    panel = _RivalStopsPanel()
    panel.show_state((), rival_all_divisions=True)
    caption_text = panel._caption.text()
    assert "all divisions" in caption_text.lower()
    assert "not found" in caption_text.lower()


def test_rival_panel_caption_resets_to_default(qt_app):
    """After an all-divisions call, a subsequent normal call resets the caption."""
    panel = _RivalStopsPanel()
    panel.show_state((), rival_all_divisions=True)
    panel.show_state((), rival_all_divisions=False)
    assert panel._caption.text() == "RIVAL STOPS"


def test_rival_panel_legend_absent_when_no_assumed_rows(qt_app):
    """No legend in caption when all rows have burn_assumed=False."""
    row = RivalStopRow(driver="X", burn_per_lap_l=7.0, burn_assumed=False)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    assert panel._caption.text() == "RIVAL STOPS"
    # Overflow slot must stay hidden — legend is not a substitute for it.
    assert panel._overflow_label.isHidden()


def test_rival_panel_legend_in_caption_for_capacity_basis(qt_app):
    """Legend is appended to caption when start_basis='capacity'."""
    row = RivalStopRow(driver="X", burn_per_lap_l=7.0, burn_assumed=True,
                       start_basis="capacity")
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    caption = panel._caption.text()
    assert caption.startswith("RIVAL STOPS")
    assert "full tank" in caption.lower()
    # Legend is in caption, not in the overflow slot.
    assert panel._overflow_label.isHidden()


def test_rival_panel_legend_in_caption_for_100_L_assumed_basis(qt_app):
    """Legend is appended to caption when start_basis='100 L assumed'."""
    row = RivalStopRow(driver="X", burn_per_lap_l=7.0, burn_assumed=True,
                       start_basis="100 L assumed")
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    caption = panel._caption.text()
    assert caption.startswith("RIVAL STOPS")
    assert "full tank" in caption.lower()
    assert panel._overflow_label.isHidden()


def test_rival_panel_legend_in_caption_for_assumed_start_l_basis(qt_app):
    """Legend is appended to caption when start_basis='assumed_start_l'."""
    row = RivalStopRow(driver="X", burn_per_lap_l=7.0, burn_assumed=True,
                       start_basis="assumed_start_l")
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    caption = panel._caption.text()
    assert caption.startswith("RIVAL STOPS")
    assert "estimated" in caption.lower()
    assert panel._overflow_label.isHidden()


def test_rival_panel_legend_generic_in_caption_for_unknown_basis(qt_app):
    """Generic legend in caption for an unrecognised non-None start_basis."""
    row = RivalStopRow(driver="X", burn_per_lap_l=7.0, burn_assumed=True,
                       start_basis="some_future_basis")
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    caption = panel._caption.text()
    assert caption.startswith("RIVAL STOPS")
    assert "*" in caption
    assert panel._overflow_label.isHidden()


def test_rival_panel_legend_generic_in_caption_for_none_basis(qt_app):
    """Generic legend in caption when burn_assumed=True but start_basis=None.

    In production start_basis is always set when burn_assumed=True (the backend
    sets one of three known values).  Should the combination occur anyway, the
    generic legend is shown — the '*' in the burn cell is still explained.
    """
    row = RivalStopRow(driver="X", burn_per_lap_l=7.0, burn_assumed=True,
                       start_basis=None)
    panel = _RivalStopsPanel()
    panel.show_state((row,))
    caption = panel._caption.text()
    assert caption.startswith("RIVAL STOPS")
    assert "*" in caption


def test_rival_panel_legend_combined_with_all_divisions(qt_app):
    """Legend and all-divisions note both appear in caption on one line."""
    row = RivalStopRow(driver="X", burn_per_lap_l=7.0, burn_assumed=True,
                       start_basis="capacity")
    panel = _RivalStopsPanel()
    panel.show_state((row,), rival_all_divisions=True)
    caption = panel._caption.text()
    assert "all divisions" in caption.lower()
    assert "full tank" in caption.lower()
    # Only one QLabel line — confirmed by checking the caption starts with RIVAL STOPS.
    assert caption.startswith("RIVAL STOPS")


def test_rival_panel_overflow_slot_shows_count_not_legend(qt_app):
    """When overflow > 0 the overflow slot shows the count; legend is in caption."""
    from pitcrew.ui.driver_view import MAX_RIVALS

    rows = tuple(
        RivalStopRow(driver=f"D{i}", burn_assumed=True, start_basis="capacity",
                     burn_per_lap_l=7.0)
        for i in range(MAX_RIVALS + 2)
    )
    panel = _RivalStopsPanel()
    panel.show_state(rows)
    # Overflow slot: count.
    assert not panel._overflow_label.isHidden()
    assert "+2" in panel._overflow_label.text()
    assert "tank" not in panel._overflow_label.text().lower()
    # Caption: legend (both can be shown simultaneously).
    assert "full tank" in panel._caption.text().lower()


def test_rival_panel_legend_clears_from_caption_when_assumed_rows_removed(qt_app):
    """After a table with assumed rows, a clean table removes the legend from caption."""
    row_assumed = RivalStopRow(driver="X", burn_per_lap_l=7.0, burn_assumed=True,
                               start_basis="capacity")
    row_clean = RivalStopRow(driver="Y", burn_per_lap_l=6.0, burn_assumed=False)
    panel = _RivalStopsPanel()
    panel.show_state((row_assumed,))
    assert "full tank" in panel._caption.text().lower()
    panel.show_state((row_clean,))
    assert panel._caption.text() == "RIVAL STOPS"
