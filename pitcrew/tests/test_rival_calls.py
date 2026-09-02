"""The rival call layer, including the much longer list of things it refuses.

Every figure in here is a real one: the Spa replay's own entry and exit fuel,
his measured 8 L/lap at Spa and the 1.0 L/s refuel rate confirmed three ways.
"""
from pitcrew.race.calls import DECISION, register_of
from pitcrew.race.rival_calls import (
    RIVAL_BOXED,
    RIVAL_COMMITTED,
    STAY_OUT_FUEL,
    Rival,
    must_stop_by,
    rival_boxed,
    stay_out,
)
from pitcrew.race.rivals import Stop

SPA_BURN = 8.0
RATE = 1.0


def _rival(name="Rocky", came_in=None, left_on=None, lap=11, pitted=True):
    return Rival(name=name, pitted=pitted,
                 stop=Stop(lap=lap, fuel_in_l=came_in, fuel_out_l=left_on))


def test_every_kind_is_registered_as_a_decision():
    # `register_of` raises on an unclassified kind, deliberately - so this is
    # the test that a new call cannot reach the voice unrouted.
    for kind in (RIVAL_BOXED, RIVAL_COMMITTED, STAY_OUT_FUEL):
        assert register_of(kind) == DECISION


def test_no_call_says_the_word_gap():
    """Rule 13. `_fuel_gap` already owns "gap" meaning laps of fuel in hand."""
    said = [
        rival_boxed(_rival(came_in=10.0), lap=11, laps_left=9,
                    burn_per_lap_l=SPA_BURN, refuel_rate_lps=RATE,
                    ours=Stop(lap=11, fuel_in_l=19.0, fuel_out_l=91.0)),
        must_stop_by(_rival(left_on=41.0), SPA_BURN, lap=11, laps_total=20),
        stay_out(lap=5, laps_left=15, burn_per_lap_l=SPA_BURN,
                 refuel_rate_lps=RATE, capacity_l=100.0, laps_total=20,
                 planned_stop_lap=11),
    ]
    for call in said:
        assert call is not None
        assert "gap" not in (call.call + " " + call.reason).lower()


# --- rival_boxed -----------------------------------------------------------

def test_a_rival_who_came_in_emptier_stands_longer():
    # He came in on 19 and took 72 L. A rival in on 4 needs 68... no: needs
    # more. Fill to the flag is 9 x 8 = 72, so from 4 L he takes 68 s against
    # our 72 - he is QUICKER. From 40 L he takes 32 s: 40 s less.
    call = rival_boxed(_rival(came_in=40.0), lap=11, laps_left=9,
                       burn_per_lap_l=SPA_BURN, refuel_rate_lps=RATE,
                       ours=Stop(lap=11, fuel_in_l=19.0, fuel_out_l=91.0))
    assert call is not None
    assert "40 seconds less" in call.reason


def test_a_rival_who_stops_earlier_stands_longer_than_us():
    # Same entry fuel, but eighteen laps to fill for instead of nine.
    call = rival_boxed(_rival(came_in=19.0, lap=2), lap=2, laps_left=18,
                       burn_per_lap_l=SPA_BURN, refuel_rate_lps=RATE,
                       ours=Stop(lap=11, fuel_in_l=19.0, fuel_out_l=91.0))
    assert call is not None
    assert "longer than you" in call.reason


def test_a_swing_too_small_to_drive_to_is_not_said():
    # He took 72 L. A rival in on 5 fills 67 - five seconds across the whole
    # stop cycle, which is not something a driver can drive to.
    assert rival_boxed(_rival(came_in=5.0), lap=11, laps_left=9,
                       burn_per_lap_l=SPA_BURN, refuel_rate_lps=RATE,
                       ours=Stop(lap=11, fuel_in_l=19.0,
                                 fuel_out_l=91.0)) is None


def test_an_unread_tank_is_not_a_full_one():
    """CLAUDE.md rule 3. A fuel figure that never resolved is not zero."""
    assert rival_boxed(_rival(came_in=None), lap=11, laps_left=9,
                       burn_per_lap_l=SPA_BURN, refuel_rate_lps=RATE,
                       ours=None) is None


def test_nothing_is_said_about_a_car_that_has_not_pitted():
    assert rival_boxed(_rival(came_in=10.0, pitted=False), lap=11, laps_left=9,
                       burn_per_lap_l=SPA_BURN, refuel_rate_lps=RATE,
                       ours=None) is None


def test_without_our_own_stop_it_still_reports_his_standing_time():
    call = rival_boxed(_rival(came_in=10.0), lap=11, laps_left=9,
                       burn_per_lap_l=SPA_BURN, refuel_rate_lps=RATE,
                       ours=None)
    assert call is not None
    assert "62 seconds standing" in call.reason


# --- must_stop_by ----------------------------------------------------------

def test_a_forced_second_stop_is_said():
    call = must_stop_by(_rival(left_on=41.0), SPA_BURN, lap=11, laps_total=20)
    assert call is not None
    assert "lap 16" in call.reason and "stop again" in call.reason


def test_a_limit_beyond_the_flag_binds_nothing_so_is_not_said():
    """The Spa replay's own defect: "must stop by lap 22" in a 20-lap race."""
    assert must_stop_by(_rival(left_on=93.0), SPA_BURN, lap=11,
                        laps_total=20) is None


def test_without_a_race_length_it_reports_the_reach_anyway():
    # Nothing to compare against is not a reason to withhold the fact.
    assert must_stop_by(_rival(left_on=41.0), SPA_BURN, lap=11) is not None


def test_an_unread_exit_figure_refuses():
    assert must_stop_by(_rival(left_on=None), SPA_BURN, lap=11,
                        laps_total=20) is None


# --- stay_out --------------------------------------------------------------

def test_before_the_tank_can_reach_the_flag_the_call_is_the_floor():
    """Rule 12: the limit that bound is the one reported."""
    call = stay_out(lap=5, laps_left=15, burn_per_lap_l=SPA_BURN,
                    refuel_rate_lps=RATE, capacity_l=100.0, laps_total=20,
                    planned_stop_lap=11)
    assert call is not None
    assert call.call == "Stay out."
    assert "cannot reach the flag" in call.reason


def test_after_the_floor_it_costs_a_lap_of_fuel_to_defer():
    call = stay_out(lap=8, laps_left=12, burn_per_lap_l=SPA_BURN,
                    refuel_rate_lps=RATE, capacity_l=100.0, laps_total=20,
                    planned_stop_lap=11)
    assert call is not None
    assert "8 seconds less standing" in call.reason


def test_on_and_after_the_planned_lap_it_goes_quiet():
    assert stay_out(lap=11, laps_left=9, burn_per_lap_l=SPA_BURN,
                    refuel_rate_lps=RATE, capacity_l=100.0, laps_total=20,
                    planned_stop_lap=11) is None


def test_where_a_lap_of_fuel_is_not_worth_saying_nothing_is_said():
    # A circuit burning 2 L/lap saves 2 s a lap deferred, under the threshold.
    assert stay_out(lap=8, laps_left=12, burn_per_lap_l=2.0,
                    refuel_rate_lps=RATE, capacity_l=100.0, laps_total=20,
                    planned_stop_lap=11) is None


def test_an_unmeasured_refuel_rate_refuses_rather_than_assumes_one():
    assert stay_out(lap=8, laps_left=12, burn_per_lap_l=SPA_BURN,
                    refuel_rate_lps=None, capacity_l=100.0, laps_total=20,
                    planned_stop_lap=11) is None
