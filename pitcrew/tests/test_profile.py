"""What can be learned about a rival from his stops, and what cannot.

The Spa numbers here are the ones read off the replay of 1 Sep 2026:
CruisingChaos in on 10 L, Rocky on 8, Boxhead out on 41 in a 20-lap race, at a
measured 8 L a lap.
"""
from __future__ import annotations

from pitcrew.race.profile import (
    BURN_DIFFERENCE_L,
    MIN_STOPS_FOR_HABIT,
    Observation,
    Profile,
    burn_against,
    describe,
    field_stop_fraction,
    stops_earlier_than,
)

SPA = dict(race="spa-r5", laps_total=20)


def spa(driver, lap, fuel_in=None, fuel_out=None, **kw):
    return Observation(driver=driver, lap=lap, fuel_in_l=fuel_in,
                       fuel_out_l=fuel_out, **{**SPA, **kw})


# --- burn ------------------------------------------------------------------

def test_burn_comes_out_of_the_entry_figure_and_the_lap_count():
    # Full tank, in on lap 11 showing 12 L: 88 L over 11 laps.
    profile = Profile("Rocky")
    profile.add(spa("Rocky", lap=11, fuel_in=12.0))
    burn, count = profile.burn_per_lap_l()
    assert burn == 8.0 and count == 1


def test_a_tank_fuller_than_it_started_is_a_misread_not_a_car_making_fuel():
    """CLAUDE.md rule 9: the arithmetic went negative, so it refuses."""
    assert spa("Rocky", lap=11, fuel_in=100.0).burn_per_lap_l is None
    assert spa("Rocky", lap=11, fuel_in=120.0).burn_per_lap_l is None


def test_an_unread_entry_figure_is_not_an_empty_tank():
    assert spa("Rocky", lap=11, fuel_in=None).burn_per_lap_l is None


def test_a_start_on_less_than_a_full_tank_is_carried_with_the_observation():
    """The one assumption that could make every burn figure wrong at once."""
    light = spa("Rocky", lap=11, fuel_in=12.0, assumed_start_l=60.0)
    assert light.assumed_start_l == 60.0
    assert abs(light.burn_per_lap_l - 48.0 / 11) < 1e-9


def test_the_sample_count_travels_with_the_mean():
    """CLAUDE.md rule 4."""
    profile = Profile("Rocky")
    assert profile.burn_per_lap_l() == (None, 0)
    profile.add(spa("Rocky", lap=10, fuel_in=20.0))
    profile.add(spa("Rocky", lap=10, fuel_in=30.0))
    burn, count = profile.burn_per_lap_l()
    assert count == 2 and abs(burn - 7.5) < 1e-9


def test_burn_against_ours_is_signed_and_negative_means_he_uses_less():
    profile = Profile("Rocky")
    profile.add(spa("Rocky", lap=11, fuel_in=23.0))     # 7 L a lap
    difference, count = burn_against(profile, ours_l=8.0)
    assert count == 1 and abs(difference + 1.0) < 1e-9


def test_burn_against_nothing_is_not_a_difference_of_zero():
    profile = Profile("Rocky")
    profile.add(spa("Rocky", lap=11, fuel_in=12.0))
    assert burn_against(profile, ours_l=None)[0] is None


# --- the fill --------------------------------------------------------------

def test_a_car_leaving_short_of_the_flag_has_to_stop_again():
    """Boxhead, out on 41 L with nine laps to run at 8 L a lap."""
    observation = spa("Boxhead", lap=11, fuel_in=12.0, fuel_out=41.0)
    assert observation.fill_surplus_l(8.0) == 41.0 - 72.0


def test_a_car_filling_exactly_to_the_flag_carries_nothing():
    observation = spa("Rocky", lap=11, fuel_in=12.0, fuel_out=72.0)
    assert observation.fill_surplus_l(8.0) == 0.0


def test_an_unread_exit_figure_is_not_an_empty_tank():
    assert spa("Rocky", lap=11, fuel_in=12.0).fill_surplus_l(8.0) is None


def test_without_a_race_length_the_surplus_cannot_be_computed():
    observation = Observation(driver="Rocky", race="x", lap=11,
                              fuel_in_l=12.0, fuel_out_l=72.0)
    assert observation.fill_surplus_l(8.0) is None


# --- when he stops ---------------------------------------------------------

def test_stop_timing_is_a_fraction_of_the_race_so_lengths_can_be_pooled():
    profile = Profile("Rocky")
    profile.add(spa("Rocky", lap=10, fuel_in=20.0))
    profile.add(Observation(driver="Rocky", race="monza", lap=20,
                            laps_total=40, fuel_in_l=20.0))
    fraction, count = profile.stop_fraction()
    assert count == 2 and abs(fraction - 0.5) < 1e-9


def test_stopping_earlier_than_the_field_is_reported_as_a_fact():
    early, late = Profile("Early"), Profile("Late")
    early.add(spa("Early", lap=8, fuel_in=30.0))
    late.add(spa("Late", lap=12, fuel_in=10.0))
    middle = field_stop_fraction([early, late])
    assert abs(middle - 0.5) < 1e-9
    ahead, _ = stops_earlier_than(early, middle)
    assert ahead > 0


def test_with_no_field_to_compare_against_there_is_no_comparison():
    profile = Profile("Rocky")
    profile.add(spa("Rocky", lap=11, fuel_in=12.0))
    assert stops_earlier_than(profile, None)[0] is None
    assert field_stop_fraction([]) is None


# --- what gets said --------------------------------------------------------

def test_a_driver_nobody_has_watched_produces_no_sentences():
    assert describe(Profile("Nobody")) == []


def test_one_stop_says_so_rather_than_presenting_itself_as_a_habit():
    profile = Profile("Rocky")
    profile.add(spa("Rocky", lap=11, fuel_in=12.0, fuel_out=72.0))
    said = " ".join(describe(profile, ours_burn_l=8.0, field_fraction=0.5))
    assert "1 stop over 1 race" in said
    assert "Too few stops" in said


def test_a_habit_is_only_called_one_after_enough_stops():
    profile = Profile("Early")
    for _ in range(MIN_STOPS_FOR_HABIT):
        profile.add(spa("Early", lap=6, fuel_in=52.0))
    said = " ".join(describe(profile, field_fraction=0.55))
    assert "earlier than the field" in said


def test_a_burn_difference_too_small_to_matter_is_not_mentioned():
    profile = Profile("Rocky")
    profile.add(spa("Rocky", lap=10, fuel_in=100.0 - 10 * 8.2))
    said = " ".join(describe(profile, ours_burn_l=8.0))
    assert "than you" not in said
    assert BURN_DIFFERENCE_L > 0.2


def test_a_rival_carrying_fuel_he_does_not_need_is_worth_a_sentence():
    profile = Profile("Heavy")
    profile.add(spa("Heavy", lap=11, fuel_in=12.0, fuel_out=95.0))
    said = " ".join(describe(profile))
    assert "more than he needs" in said and "seconds longer" in said


def test_a_rival_who_must_stop_again_is_worth_a_sentence():
    profile = Profile("Boxhead")
    profile.add(spa("Boxhead", lap=11, fuel_in=12.0, fuel_out=41.0))
    said = " ".join(describe(profile))
    assert "planning another stop" in said


def test_nothing_here_calls_a_stop_an_undercut():
    """The screen shows WHEN he stopped, never why. Two different cars - one
    jumping somebody, one short of fuel - look identical from outside."""
    profile = Profile("Early")
    for _ in range(4):
        profile.add(spa("Early", lap=5, fuel_in=60.0, fuel_out=90.0))
    said = " ".join(describe(profile, ours_burn_l=8.0, field_fraction=0.55))
    assert "undercut" not in said.lower()
