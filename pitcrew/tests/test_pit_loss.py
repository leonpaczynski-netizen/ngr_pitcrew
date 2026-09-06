"""Pit loss is measured off the race's own lap rows, and stored as measured.

Every event on file carried the app's 20 s default as 'declared'. Deep Forest's
fill was discounted by that 20; the stop took 52. `race/refuel.py` measured the
fill at every stop and wrote nothing down (CLAUDE.md §5.4: measure once per
circuit).
"""
from __future__ import annotations

from pitcrew.race.pit_loss import MIN_CLEAN_LAPS, best, measure
from pitcrew.store.db import Store


def _rows(*, pit_ms=123_214, out_ms=162_090, clean_ms=104_500, added=49.2,
          straddle=False):
    rows = []
    for n in range(1, 21):
        rows.append({"lap_num": n, "lap_time_ms": clean_ms + (n % 3) * 200,
                     "is_pit_lap": 0, "is_out_lap": 0, "fuel_added_l": None,
                     "off_track_s": 0.0, "spin_s": 0.0, "excluded": 0})
    rows[11].update({"lap_time_ms": pit_ms, "is_pit_lap": 1,
                     "fuel_added_l": None if straddle else added})
    rows[12].update({"lap_time_ms": out_ms, "is_out_lap": 1,
                     "fuel_added_l": added if straddle else None})
    return rows


def test_the_daytona_race_of_4_sep_measures_about_twenty_seconds_ex_fuel():
    """s127: pit lap 123.2 s + out-lap 162.1 s - 2 x 104.5, less 49 L at 1 L/s."""
    stops = measure(_rows(), refuel_rate_lps=1.003)
    assert len(stops) == 1
    stop = stops[0]
    assert 75 < stop.total_s < 78
    assert 26 < stop.ex_fuel_s < 29
    assert stop.stop_lap == 12
    assert "49.2 L at 1.00 L/s" in stop.method


def test_the_sum_is_robust_to_which_lap_holds_the_stop():
    """The line inside the lane (Daytona) or after the box (Deep Forest):
    the two laps' sum holds the stop either way."""
    before = measure(_rows(pit_ms=123_214, out_ms=162_090),
                     refuel_rate_lps=1.0)[0]
    after = measure(_rows(pit_ms=162_090, out_ms=123_214),
                    refuel_rate_lps=1.0)[0]
    assert before.total_s == after.total_s


def test_the_fuel_term_is_read_off_either_row():
    straddled = measure(_rows(straddle=True), refuel_rate_lps=1.0)[0]
    assert straddled.fuel_added_l == 49.2


def test_a_stop_with_no_fuel_leaves_the_term_out_rather_than_dividing_by_a_rate():
    stop = measure(_rows(added=0.5), refuel_rate_lps=1.0)[0]
    assert stop.fuel_added_l is None
    assert stop.ex_fuel_s == stop.total_s
    assert "no fuel term" in stop.method


def test_too_few_clean_laps_measures_nothing():
    rows = _rows()[:MIN_CLEAN_LAPS + 1]
    assert measure(rows, refuel_rate_lps=1.0) == []


def test_incident_laps_do_not_set_the_reference():
    rows = _rows()
    for r in rows[2:6]:
        r["lap_time_ms"] = 140_000
        r["off_track_s"] = 5.0
    stop = measure(rows, refuel_rate_lps=1.0)[0]
    assert stop.clean_lap_ms < 105_000


def test_best_prefers_a_stop_with_a_fuel_term():
    with_fuel = measure(_rows(), refuel_rate_lps=1.0)[0]
    without = measure(_rows(added=0.0), refuel_rate_lps=1.0)[0]
    assert best([without, with_fuel]) is with_fuel
    assert best([]) is None


# ------------------------------------------------------------------ the store

def test_a_measured_pit_loss_replaces_the_declared_constant(tmp_path):
    store = Store(tmp_path / "pl.db")
    try:
        event_id = store.create_event(
            name="Daytona", track="Daytona International Speedway",
            layout="Road Course", car_name="Lamborghini Huracán GT3 '15",
            race_type="laps", race_laps=20)
        before = store.get_event(event_id)
        assert before["pit_loss_secs"] == 20.0
        assert store.record_measured_pit_loss(event_id, 27.4, method="test")
        after = store.get_event(event_id)
        assert after["pit_loss_secs"] == 27.4
        assert after["pit_loss_source"] == "measured"
        assert store.record_measured_pit_loss(event_id, 0.0, method="x") is False
    finally:
        store.close()
