"""Stint-plan average deltas — the current-stint summary for the tablet.

`stint_plan_averages` filters `lap_history` to the current stint and returns
the mean lap-time and burn deltas, plus a count.  These tests hold the two
rules that matter most: the stint resets at the LAST pit lap, and fewer than
two qualifying laps is not a trend.
"""
from __future__ import annotations

from pitcrew.race.stint_averages import stint_plan_averages


def _lap(n, *, delta=0.5, burn=0.1, pit=False, out=False):
    """One lap history row with the keys `stint_plan_averages` reads."""
    return {"lap": n, "lap_ms": 101_000 + n * 100,
            "lap_delta_s": None if (pit or out) else delta,
            "burn_delta_l": None if (pit or out) else burn,
            "pit": pit, "out": out}


# ----------------------------------------- the pit/out exclusion rule


def test_pit_and_out_laps_excluded_from_average():
    """Pit and out laps carry no delta; only the green laps count."""
    history = [
        _lap(1, delta=0.5, burn=0.2),
        _lap(2, delta=1.5, burn=0.4),
        _lap(3, pit=True),
        _lap(4, out=True),
        _lap(5, delta=1.0, burn=0.3),
    ]
    lap_ms, burn_l, count = stint_plan_averages(history)
    # The pit lap (3) ends the stint so only lap 5 is in the current stint,
    # and the out-lap (4) is excluded.  One qualifying lap → (None, None, 0).
    assert (lap_ms, burn_l, count) == (None, None, 0)


def test_fewer_than_two_qualifying_laps_returns_none_triple():
    """One lap is not a trend (rule 4)."""
    history = [_lap(1, delta=0.5, burn=0.2)]
    assert stint_plan_averages(history) == (None, None, 0)


def test_empty_history_returns_none_triple():
    assert stint_plan_averages([]) == (None, None, 0)
    assert stint_plan_averages(None) == (None, None, 0)


# ----------------------------------------- the stint-reset rule


def test_resets_at_last_pit_excludes_earlier_laps():
    """Only laps AFTER the last pit entry are in the current stint."""
    history = [
        _lap(1, delta=10.0, burn=5.0),   # pre-pit: huge delta, excluded
        _lap(2, delta=10.0, burn=5.0),   # pre-pit: huge delta, excluded
        _lap(3, pit=True),
        _lap(4, out=True),
        _lap(5, delta=0.2, burn=0.1),
        _lap(6, delta=0.4, burn=0.3),
    ]
    lap_ms, burn_l, count = stint_plan_averages(history)
    assert count == 2
    # mean of 0.2 and 0.4 s = 0.3 s = 300 ms
    assert lap_ms == 300
    # mean of 0.1 and 0.3 L = 0.2 L
    assert abs(burn_l - 0.2) < 1e-9


def test_no_pit_lap_uses_whole_history():
    """With no pit lap in the history, every qualifying lap counts."""
    history = [
        _lap(1, delta=0.5, burn=0.1),
        _lap(2, delta=1.5, burn=0.3),
        _lap(3, out=True),               # out-lap always excluded
        _lap(4, delta=0.5, burn=0.1),
    ]
    lap_ms, burn_l, count = stint_plan_averages(history)
    # laps 1, 2, 4 qualify (out-lap excluded); (0.5 + 1.5 + 0.5) / 3 = 0.833...
    assert count == 3
    assert abs(lap_ms - round(0.833_333 * 1000)) <= 1


def test_lap_delta_ms_rounds_to_integer():
    """The return is milliseconds, rounded to the nearest integer."""
    history = [_lap(1, delta=0.2, burn=0.1),
               _lap(2, delta=0.3, burn=0.1),
               _lap(3, delta=0.5, burn=0.1)]
    lap_ms, _, count = stint_plan_averages(history)
    assert count == 3
    # mean 0.3333... s → 333 ms (round-half-to-even → 333)
    assert isinstance(lap_ms, int)
    assert lap_ms == 333


def test_laps_missing_delta_or_burn_excluded():
    """A lap with a null delta or burn is not a qualifying lap."""
    history = [
        {"lap": 1, "lap_ms": 100_000, "lap_delta_s": None,
         "burn_delta_l": 0.2, "pit": False, "out": False},
        {"lap": 2, "lap_ms": 100_200, "lap_delta_s": 0.5,
         "burn_delta_l": None, "pit": False, "out": False},
        {"lap": 3, "lap_ms": 100_400, "lap_delta_s": 0.6,
         "burn_delta_l": 0.3, "pit": False, "out": False},
        {"lap": 4, "lap_ms": 100_600, "lap_delta_s": 0.4,
         "burn_delta_l": 0.1, "pit": False, "out": False},
    ]
    lap_ms, burn_l, count = stint_plan_averages(history)
    # only laps 3 and 4 qualify; mean delta = 0.5 s = 500 ms
    assert count == 2
    assert lap_ms == 500
    assert abs(burn_l - 0.2) < 1e-9
