"""Measuring the rate the car takes fuel at, instead of believing the form.

At Monza the tank is 100 L and the typed rate is 1.0 L/s, so a full stop is 73
seconds of standing still against 19 s of pit loss. The refuel dominates the
stop, the stop dominates the stop count, and the stop count is the plan — and
the figure had never been measured.
"""
from __future__ import annotations

from pitcrew.analysis.refuel import (
    MIN_FUEL_TAKEN_L,
    measure_refuel_rate,
    refuel_evidence,
    refuel_windows,
)
from pitcrew.analysis.session import LapInput


def a_lap(fuel_series: list[float], *, lap_num: int = 1,
          hz: float = 60.0) -> LapInput:
    """One lap whose tank follows `fuel_series`, one entry per frame."""
    frames = [{"t_ms": int(round(index * 1000.0 / hz)), "fuel_l": litres}
              for index, litres in enumerate(fuel_series)]
    return LapInput(lap_num=lap_num, lap_time_ms=94_000,
                    fuel_start=fuel_series[0], fuel_end=fuel_series[-1],
                    frames=frames)


def a_stop(rate_lps: float, litres: float, *, hz: float = 60.0,
           before: int = 60, after: int = 60) -> list[float]:
    """Steady running, a stop taking `litres` at `rate_lps`, steady running."""
    step = rate_lps / hz
    frames = int(round(litres / step))
    return ([20.0] * before
            + [20.0 + step * (n + 1) for n in range(frames)]
            + [20.0 + litres] * after)


def test_a_stop_is_the_tank_climbing():
    """GT7 marks no pit stop in any packet format, so the rise is both the
    detector and the measurement."""
    windows = refuel_windows(a_lap(a_stop(2.5, 50.0)))
    assert len(windows) == 1
    assert windows[0]["litres"] == 50.0
    assert round(windows[0]["rateLps"], 1) == 2.5


def test_a_lap_with_no_stop_measures_nothing():
    steady = a_lap([80.0 - 0.01 * n for n in range(200)])
    assert refuel_windows(steady) == []


def test_two_stops_in_one_lap_are_two_windows():
    series = a_stop(2.0, 20.0, after=120) + a_stop(2.0, 20.0, before=0)
    assert len(refuel_windows(a_lap(series))) == 2


def test_a_splash_too_small_to_time_is_ignored():
    """Float noise on a channel in litres is hundredths; a measurable splash
    is litres."""
    assert refuel_windows(a_lap(a_stop(2.5, MIN_FUEL_TAKEN_L - 1.0))) == []


def test_an_absurd_rate_is_refused_rather_than_planned_on():
    """A lap boundary landing inside a stop can make the tank appear to fill
    instantly. A plan costed on that would treat stops as free."""
    instant = a_lap([20.0] * 30 + [95.0] * 30)
    assert refuel_windows(instant) == []


def test_the_rate_is_the_median_across_stops():
    """One stop cut short should not move the figure the race is planned on."""
    laps = [a_lap(a_stop(2.5, 40.0), lap_num=1),
            a_lap(a_stop(2.6, 40.0), lap_num=2),
            a_lap(a_stop(9.0, 40.0), lap_num=3)]
    measured = measure_refuel_rate(laps)
    assert measured["stopsMeasured"] == 3
    assert 2.5 <= measured["rateLps"] <= 2.6


def test_no_stop_on_record_refuses_and_says_what_to_drive():
    """Refuelling in the garage between sessions cannot be seen: the recorder
    is stopped and the tank simply reads full again next time."""
    evidence = refuel_evidence([a_lap([80.0, 79.9, 79.8])], 1.0)
    assert evidence["source"] == "declared"
    assert evidence["rateLps"] == 1.0
    assert "never been measured" in evidence["note"]
    assert "one pit stop in practice" in evidence["note"]


def test_a_measured_rate_beats_the_typed_one_and_says_by_how_much():
    evidence = refuel_evidence([a_lap(a_stop(2.5, 50.0))], 1.0)
    assert evidence["source"] == "measured-from-the-fuel-channel"
    assert round(evidence["rateLps"], 1) == 2.5
    assert "against 1.00 L/s declared" in evidence["note"]
    # 100 L at 1.0 L/s is 100 s; at 2.5 L/s it is 40 s. That gap is the plan.
    assert "60 s a stop" in evidence["note"]


def test_a_measured_rate_that_agrees_says_nothing_extra():
    evidence = refuel_evidence([a_lap(a_stop(1.0, 40.0))], 1.0)
    assert evidence["source"] == "measured-from-the-fuel-channel"
    assert "note" not in evidence


def test_a_lap_without_the_fuel_channel_is_silent():
    """Laps recorded before the channel existed decode fine and measure
    nothing, rather than measuring zero."""
    bare = LapInput(lap_num=1, lap_time_ms=94_000, fuel_start=80.0,
                    fuel_end=76.0, frames=[{"t_ms": 0}, {"t_ms": 17}])
    assert refuel_windows(bare) == []
    assert measure_refuel_rate([bare]) is None
