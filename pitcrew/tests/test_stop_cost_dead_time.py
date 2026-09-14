"""A pit loss measured as the whole stop less the fuel already holds the dead
time, and is not charged it twice.

Bathurst, 14 Sep 2026, lap 8: "A stop now puts you behind the car behind. He
is 1 seconds back against a 70 second stop." The event's pit loss, 23.13 s,
was derived by `race/pit_loss.py` as the whole stop minus the refuelling, and
`stop_costs_s` added `PIT_DEAD_TIME_S` on top because the coordinator filed
every event-page "measured" under the lane-only source.
"""
from __future__ import annotations

import pytest

from pitcrew.race.coordinator import RaceCoordinator
from pitcrew.race.gaps import stop_costs_s
from pitcrew.strategy.model import (PIT_DEAD_TIME_S, PIT_LOSS_MEASURED,
                                    PIT_LOSS_MEASURED_EX_FUEL)

BATHURST_LOSS_S = 23.13


def test_a_whole_stop_less_fuel_is_not_charged_the_dead_time_again():
    cost = stop_costs_s(40.0, 1.0, BATHURST_LOSS_S, PIT_LOSS_MEASURED_EX_FUEL)
    assert cost == pytest.approx(40.0 + BATHURST_LOSS_S)


def test_a_lane_only_measurement_still_gets_it():
    cost = stop_costs_s(40.0, 1.0, 15.7, PIT_LOSS_MEASURED)
    assert cost == pytest.approx(40.0 + 15.7 + PIT_DEAD_TIME_S)


def test_the_event_pages_measured_loss_arrives_as_whole_stop_less_fuel():
    """The only writer of `events.pit_loss_source = 'measured'` is
    `race/pit_loss.py`, whose figure is `ex_fuel_s` - lane plus dead time."""
    race = RaceCoordinator({}, pit_loss_s=BATHURST_LOSS_S,
                           pit_loss_measured=True)
    assert race.state.pit_loss_source == PIT_LOSS_MEASURED_EX_FUEL
    declared = RaceCoordinator({}, pit_loss_s=20.0)
    assert declared.state.pit_loss_source is None


def test_pit_loss_py_figure_includes_the_dead_time():
    """The recipe's own claim, pinned: ex-fuel is total less litres / rate,
    so whatever stood still before the hose is still in it."""
    from pitcrew.race.pit_loss import measure

    rows = ([{"lap_num": n, "lap_time_ms": 120_000} for n in range(2, 8)]
            + [{"lap_num": 8, "lap_time_ms": 130_000, "is_pit_lap": 1},
               {"lap_num": 9, "lap_time_ms": 173_130, "is_out_lap": 1,
                "fuel_added_l": 40.0}])
    stop = measure(rows, refuel_rate_lps=1.0)[0]
    # 250.13 - 240 = 63.13 s all in; less 40 s of fuel = 23.13 s.
    assert stop.ex_fuel_s == pytest.approx(BATHURST_LOSS_S)
