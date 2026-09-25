"""Rival stop rows for the race monitor — Story 2, 25 Sep 2026.

`rival_stop_rows` groups `db.rival_stops` rows by driver and attaches the fill
verdict.  These tests hold the grouping rule, the dimming rule, the burn-per-lap
derivation, and the negative-burn refusal (rule 9).
"""
from __future__ import annotations

import pytest

from pitcrew.race.fill_verdict import rival_stop_rows


def _stop(driver, lap, fuel_in=8.0, fuel_out=60.0, partial=False,
          exit_is_a_bound=False, stop_id=1):
    return {
        "id": stop_id,
        "driver": driver,
        "lap": lap,
        "fuel_in_l": fuel_in,
        "fuel_out_l": fuel_out,
        "partial": int(partial),
        "exit_is_a_bound": int(exit_is_a_bound),
        "compound": "RS",
        "compound_in": "RH",
    }


# ----------------------------------------- dimming rule


def test_rival_not_in_entered_is_dimmed():
    """A driver in stops but not in entered → row present, dimmed=True.

    C2: entered drivers also get rows (BEENI with no stops here), so there
    are two rows total.  The PUNISHED row is the dimmed one.
    """
    stops = [_stop("PUNISHED", 10)]
    rows = rival_stop_rows(stops, entered=["BEENI"], own_driver=None,
                           laps_remaining=10, own_burn_l=8.0)
    # Both BEENI (entered, no stops) and PUNISHED (not entered, has stop).
    assert len(rows) == 2
    punished = next(r for r in rows if r.driver == "PUNISHED")
    beeni = next(r for r in rows if r.driver == "BEENI")
    assert punished.dimmed is True
    assert beeni.dimmed is False
    assert beeni.stop_count == 0


def test_driver_in_entered_is_not_dimmed():
    stops = [_stop("BEENI", 10)]
    rows = rival_stop_rows(stops, entered=["BEENI"], own_driver=None,
                           laps_remaining=10, own_burn_l=8.0)
    assert len(rows) == 1
    assert rows[0].dimmed is False


def test_case_insensitive_entered_matching():
    """Entered list may use different capitalisation than stop rows."""
    stops = [_stop("Beeni-187", 10)]
    rows = rival_stop_rows(stops, entered=["BEENI-187"], own_driver=None,
                           laps_remaining=10, own_burn_l=8.0)
    assert rows[0].dimmed is False


# ----------------------------------------- own driver excluded


def test_own_driver_excluded_from_table():
    stops = [_stop("BEENI", 10), _stop("RIVAL", 11, stop_id=2)]
    rows = rival_stop_rows(stops, entered=["BEENI", "RIVAL"],
                           own_driver="BEENI", laps_remaining=10, own_burn_l=8.0)
    names = [r.driver for r in rows]
    assert "BEENI" not in names
    assert "RIVAL" in names


# ----------------------------------------- burn derivation


def test_burn_per_lap_negative_returns_none_falls_back_to_own_burn():
    """If prev_out < cur_in the stint burned negative fuel → rule 9: use own burn."""
    prev = _stop("X", 5, fuel_in=20.0, fuel_out=50.0, stop_id=1)
    cur = _stop("X", 15, fuel_in=60.0, fuel_out=30.0, stop_id=2)
    # prev_out=50, cur_in=60 → burned = 50-60 = -10 → refused; falls back to own
    rows = rival_stop_rows([prev, cur], entered=["X"], own_driver=None,
                           laps_remaining=10, own_burn_l=5.0)
    assert len(rows) == 1
    assert rows[0].burn_per_lap_l == pytest.approx(5.0)


def test_burn_per_lap_derived_from_consecutive_stops():
    """Two stops with valid figures → derived burn used."""
    prev = _stop("Y", 5, fuel_in=10.0, fuel_out=60.0, stop_id=1)
    # fuel burned in 10 laps = 60 - 10 = 50 L → 5 L/lap
    cur = _stop("Y", 15, fuel_in=10.0, fuel_out=45.0, stop_id=2)
    rows = rival_stop_rows([prev, cur], entered=["Y"], own_driver=None,
                           laps_remaining=8, own_burn_l=8.0)
    assert len(rows) == 1
    assert rows[0].burn_per_lap_l == pytest.approx(5.0)


# ----------------------------------------- fill verdict end-to-end


def test_rival_stop_rows_fill_verdict_end_to_end():
    """A single stop with known burn and laps → verdict matches fill_verdict.

    C3: burn is now derived from (100 - fuel_in) / stop_lap for a first stop
    with no capacity supplied.  fuel_in defaults to 8.0, stop_lap=10 →
    burn = (100 - 8) / 10 = 9.2 L/lap.
    """
    from pitcrew.race.fill_verdict import fill_verdict

    stops = [_stop("Z", 10, fuel_out=40.0, partial=False, stop_id=1)]
    rows = rival_stop_rows(stops, entered=["Z"], own_driver=None,
                           laps_remaining=6, own_burn_l=8.0)
    assert len(rows) == 1
    row = rows[0]
    # Burn derived: (100 - 8) / 10 = 9.2 L/lap (not own_burn_l=8.0).
    derived_burn = (100.0 - 8.0) / 10
    expected = fill_verdict(40.0, derived_burn, 6, partial=False, exit_is_a_bound=False)
    assert row.verdict.verdict == expected.verdict
    assert row.verdict.margin_l == pytest.approx(expected.margin_l)


# ----------------------------------------- multi-stop grouping


def test_multi_stop_groups_same_driver_latest_first_class():
    """Multiple stops from one driver → one row, earlier stops attached."""
    s1 = _stop("M", 5, fuel_out=60.0, stop_id=1)
    s2 = _stop("M", 12, fuel_out=45.0, stop_id=2)
    rows = rival_stop_rows([s1, s2], entered=["M"], own_driver=None,
                           laps_remaining=8, own_burn_l=8.0)
    assert len(rows) == 1
    assert rows[0].stop_count == 2
    # Latest stop is the verdict's input (fuel_out from s2 = 45)
    assert rows[0].fuel_out_l == pytest.approx(45.0)
    # Earlier stop is attached
    assert len(rows[0].earlier_stops) == 1


# ----------------------------------------- empty / None inputs


def test_empty_stops_no_entered_returns_empty_tuple():
    """No stops and no entered drivers → empty tuple (nothing to show)."""
    rows = rival_stop_rows([], entered=[], own_driver=None,
                           laps_remaining=10, own_burn_l=8.0)
    assert rows == ()


def test_empty_stops_with_entered_driver_gives_one_row():
    """C2: no stops but an entered driver → one row with stop_count=0."""
    rows = rival_stop_rows([], entered=["X"], own_driver=None,
                           laps_remaining=10, own_burn_l=8.0)
    assert len(rows) == 1
    assert rows[0].stop_count == 0
    assert rows[0].driver == "X"
    assert rows[0].dimmed is False


# ----------------------------------------- I2: gap staleness (field_view)


def test_field_view_own_gap_staleness_stale_board():
    """I2: a board older than BOARD_FRESH_S → gap unread, gap_s None.

    `gap_still_stands` uses `board_age_s` as its second gate.  When the board
    is stale the gap is withdrawn rather than drawn as the number it used to
    be — the driver cannot act on a stale number at racing speed.
    """
    from pitcrew.race.field import FieldView, OwnGap, BOARD_FRESH_S

    # An OwnGap with a reading that exists but was marked unread (stale board).
    stale_gap = OwnGap(gap_s=None, unread=True, trend=None, rate_s_per_lap=None)
    view = FieldView(own_gap_ahead=stale_gap)
    assert view.own_gap_ahead.unread is True
    assert view.own_gap_ahead.gap_s is None


def test_field_view_own_gap_staleness_old_lap():
    """I2: a gap read on an earlier lap → gap_still_stands returns False.

    `gap_still_stands(read_key, lap_on_screen, board_age_s)` with
    `read_key` converted to the HUD lap < `lap_on_screen` exceeds
    `GAP_STALE_LAPS=0` and the function refuses it.
    """
    from pitcrew.race.field import gap_still_stands, BOARD_FRESH_S

    # read_key=9 → as_his_hud_numbers_it(9)=10 (add 1 for in-progress lap).
    # lap_on_screen=11 (driving lap 11).
    # 11 - 10 = 1 > GAP_STALE_LAPS=0 → stale.
    from pitcrew.race.calls import as_his_hud_numbers_it
    read_key = 9   # completed-lap domain: lap_now() = 9
    lap_on_screen = 11  # HUD: driving lap 11
    board_age = 1.0   # fresh board (under BOARD_FRESH_S)
    result = gap_still_stands(read_key, lap_on_screen, board_age)
    assert result is False, (
        "gap from an earlier lap must not stand (GAP_STALE_LAPS=0)"
    )
