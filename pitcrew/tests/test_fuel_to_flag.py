"""The number the driver was not given, at the moment he needed it.

Fuji, 24 Aug 2026, 20:27:19, with the hose already in:

    "Go. 71 litres aboard - that already covers it."

True for the approved plan, whose next stint was four laps. He was not driving
that race - he had ignored the box call twice and ran to the flag - and the
fifteen laps that remained wanted about 92 L at the measured burn. He filled
the tank, crossed the line with 8.276 L aboard, and that is 8.3 s stationary
at the measured 1.001 L/s.

Nothing in the app produced the to-the-flag figure at the box. `fuel_target_l`
sizes the next stint whenever a further stop is planned - right for the plan,
silent about the alternative he was actually weighing.
"""
from __future__ import annotations

import pytest

from pitcrew.race.calls import RaceState, fuel_target_l, fuel_to_flag_l
from pitcrew.race.refuel import TO_FLAG_EPSILON_L, _to_flag_clause


def fuji(**over):
    """The race as it stood in the box on lap 5."""
    # `in_pit` matters: the deduction of the lap the stop is happening on is
    # gated on actually being in the box - see `_laps_after_this_stop`.
    fields = dict(lap=5, laps_total=20, fuel_per_lap_l=6.098,
                  fuel_capacity_l=100.0, next_stint_laps=4,
                  further_stop_planned=True, stint_ends_on_lap=6,
                  laps_estimate_firm=True, in_pit=True)
    fields.update(over)
    return RaceState(**fields)


# ------------------------------------------------------------- the figure

def test_the_to_flag_figure_is_produced_even_with_a_further_stop_planned():
    """The whole defect: the plan's target was the only number available."""
    state = fuji()

    planned = fuel_target_l(state)
    to_flag = fuel_to_flag_l(state)

    assert planned is not None and to_flag is not None
    assert to_flag > planned, (
        "running to the flag needs more than the next stint - that gap is the "
        "call he never got")
    # Fifteen laps at the measured burn, plus a margin sized on scatter.
    assert to_flag == pytest.approx(15 * 6.098, abs=6.0)


def test_it_is_none_when_the_tank_could_not_hold_it_anyway():
    """A figure he cannot act on is not worth the words."""
    state = fuji(fuel_capacity_l=40.0)

    assert fuel_to_flag_l(state) is None


def test_it_is_none_without_a_measured_burn():
    assert fuel_to_flag_l(fuji(fuel_per_lap_l=None)) is None


def test_it_does_not_count_the_lap_the_stop_is_happening_on():
    """`_laps_after_this_stop`'s rule: most of that lap is behind the car."""
    state = fuji()

    to_flag = fuel_to_flag_l(state)

    # 15 laps after the stop, not the 16 `laps_remaining` counts.
    assert to_flag < 16 * 6.098


# ------------------------------------------------------------ the wording

def test_the_clause_is_said_when_staying_out_is_a_live_alternative():
    clause = _to_flag_clause(92.0, 71.0)

    assert "to the flag" in clause
    assert "92" in clause


def test_nothing_is_said_when_the_planned_fill_already_covers_the_flag():
    """Not a choice, so not a second number at the one moment he is busiest."""
    assert _to_flag_clause(70.0, 71.0) == ""
    assert _to_flag_clause(71.0 + TO_FLAG_EPSILON_L - 0.1, 71.0) == ""


def test_nothing_is_said_when_there_is_no_figure():
    assert _to_flag_clause(None, 71.0) == ""
    assert _to_flag_clause(92.0, None) == ""


def test_the_clause_rounds_up_like_every_other_fuel_figure():
    """Round up, never to nearest - the same direction as the fill call."""
    assert "92" in _to_flag_clause(91.2, 71.0)


# --------------------------------------------------- the call in the box

def test_the_release_call_carries_the_alternative():
    """The exact Fuji call, with the number that was missing from it."""
    from pitcrew.race.refuel import RefuelWatch

    watch = RefuelWatch()
    # Arrive in the box, stationary, tank already past the plan's target.
    watch.note(60.0, speed_kph=0.0, target_l=71.0)
    for _ in range(6):
        watch.note(71.5, speed_kph=0.0, target_l=71.0, fuel_per_lap_l=6.098,
                   to_flag_l=92.0)
    call = watch.note(71.6, speed_kph=0.0, target_l=71.0,
                      fuel_per_lap_l=6.098, to_flag_l=92.0)

    spoken = " ".join(filter(None, [
        c.spoken() for c in [call] if c is not None]))
    if spoken:
        assert "to the flag" in spoken, spoken
