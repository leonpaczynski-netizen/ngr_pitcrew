"""The one place where carrying fuel is pure loss."""
from __future__ import annotations

from pitcrew.race.quali_fuel import MARGIN_L, qualifying_fuel, refusal


def test_it_covers_the_out_lap_the_flyer_and_the_lap_home():
    got = qualifying_fuel(fuel_per_lap_l=6.0, fuel_capacity_l=100.0,
                          fuel_weight_s_per_l_per_lap=0.003)
    assert got.laps_covered == 3
    assert got.litres == 3 * 6.0 + MARGIN_L


def test_the_call_prices_it_in_seconds():
    """He will not accept "put in 20 litres" without being told what the other
    eighty were costing - the same driver who will not carry a spare lap of
    fuel because 6.31 L at the flag is 6.3 seconds standing still."""
    got = qualifying_fuel(fuel_per_lap_l=6.0, fuel_capacity_l=100.0,
                          fuel_weight_s_per_l_per_lap=0.003)
    said = got.call()
    assert said.startswith("Qualifying fuel: 20 litres.")
    assert "6.00 a lap" in said
    assert "s a lap against a full tank" in said


def test_a_derived_coefficient_says_it_is_estimated():
    """`CLAUDE.md` §5.3: the fuel-weight figure is derived, not measured, and
    the driver may overwrite it. It must not travel as a measurement."""
    derived = qualifying_fuel(fuel_per_lap_l=6.0, fuel_capacity_l=100.0,
                              fuel_weight_s_per_l_per_lap=0.003)
    assert "estimated" in derived.call()

    measured = qualifying_fuel(fuel_per_lap_l=6.0, fuel_capacity_l=100.0,
                               fuel_weight_s_per_l_per_lap=0.0041,
                               weight_is_derived=False)
    assert "estimated" not in measured.call()


def test_more_flying_laps_carry_more_fuel():
    one = qualifying_fuel(fuel_per_lap_l=6.0, flying_laps=1)
    two = qualifying_fuel(fuel_per_lap_l=6.0, flying_laps=2)
    assert two.litres > one.litres
    assert two.laps_covered == one.laps_covered + 1


def test_an_unmeasured_burn_produces_no_number_at_all():
    """**The refusal that matters.** A qualifying fuel figure computed from a
    guessed consumption is a guess about the one lap of the weekend that
    cannot be redone."""
    assert qualifying_fuel(fuel_per_lap_l=None) is None
    assert qualifying_fuel(fuel_per_lap_l=0.0) is None

    said = refusal(None)
    assert "nothing has measured" in said and "three laps" in said
    assert refusal(6.0) == ""


def test_a_run_that_will_not_fit_is_capped_at_the_tank():
    got = qualifying_fuel(fuel_per_lap_l=40.0, flying_laps=3,
                          fuel_capacity_l=100.0,
                          fuel_weight_s_per_l_per_lap=0.003)
    assert got.litres == 100.0
    assert got.saving_s_per_lap == 0.0


def test_no_capacity_means_no_seconds_rather_than_a_guess():
    got = qualifying_fuel(fuel_per_lap_l=6.0)
    assert got.saving_s_per_lap is None
    assert "against a full tank" not in got.call()
    assert got.call().startswith("Qualifying fuel: 20 litres.")
