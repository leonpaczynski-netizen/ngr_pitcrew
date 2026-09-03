"""A rival short of fuel either stops again or drives it out.

Before this there were two answers to that and the race has three. `must_stop_by`
fired whenever a car could not reach the flag on its exit fuel and said "he has
to stop again" - which is right when he is miles short and wrong when he is a
few per cent light, because a stop costs a pit loss and a lift costs tenths. A
driver told to wait for a stop that never comes does not attack the car in front
of him that is going slowly on purpose.

The numbers here are his own: short-shifting measured at -24.9% fuel for
+0.5 s/lap at Monza.
"""
from __future__ import annotations

from pitcrew.race.calls import RIVAL_COMMITTED, RIVAL_SAVING, RaceState, next_call
from pitcrew.race.rival_calls import (
    Rival,
    candidates,
    fuel_shortfall,
    must_stop_by,
    saving_to_the_flag,
)
from pitcrew.race.rivals import Stop


def a_rival(fuel_out, *, lap=5, burn=8.0, name="Boxhead"):
    """He stopped on lap 5 of a 20-lap race and left on `fuel_out` litres.

    Fifteen laps at 8 L/lap needs 120 L, so `fuel_out` IS the shortfall in
    disguise: 120 is exactly enough, 110 is 8% light, 41 is hopeless.
    """
    return Rival(name=name, stop=Stop(lap=lap, fuel_out_l=fuel_out),
                 burn_per_lap_l=burn, pitted=True)


# --- the three cases --------------------------------------------------------

def test_a_car_that_reaches_the_flag_is_not_worth_a_call():
    assert saving_to_the_flag(a_rival(130), None, lap=6, laps_total=20) is None
    assert must_stop_by(a_rival(130), None, lap=6, laps_total=20) is None


def test_a_car_a_few_per_cent_light_is_saving_and_that_is_the_call():
    """The case that used to be silent, and it is the one worth driving to."""
    call = saving_to_the_flag(a_rival(110), None, lap=6, laps_total=20)
    assert call is not None and call.kind == RIVAL_SAVING
    assert "saving to the flag" in call.call and "Attack" in call.call
    assert "10 litres light over 15 laps" in call.reason
    assert "0.2 seconds a lap" in call.reason


def test_a_car_that_is_genuinely_short_still_has_to_stop():
    call = must_stop_by(a_rival(41), None, lap=6, laps_total=20)
    assert call is not None and call.kind == RIVAL_COMMITTED
    assert "has to stop again" in call.reason


def test_the_two_calls_never_both_fire_for_one_car():
    """They are the two answers to one question. Both said about one car in
    one race is a contradiction the driver has to resolve at speed."""
    for fuel in range(20, 140, 5):
        rival = a_rival(fuel)
        both = [saving_to_the_flag(rival, None, lap=6, laps_total=20),
                must_stop_by(rival, None, lap=6, laps_total=20)]
        assert len([c for c in both if c is not None]) <= 1, fuel


def test_a_shortfall_inside_the_reading_error_is_not_a_finding():
    """His burn is one number for a whole stint and the fill is known to about
    four litres. Two litres against that is noise, and reporting noise as a
    finding is what CLAUDE.md rule 5 is about."""
    assert saving_to_the_flag(a_rival(118), None, lap=6, laps_total=20) is None
    short = fuel_shortfall(a_rival(118), None, laps_total=20)
    assert short.litres == 2.0 and not short.certain


def test_a_saving_too_small_to_cost_him_anything_is_not_said():
    """Five litres over fifteen laps is about a tenth a lap - a second and a
    half over the run. Below the threshold it is a car he cannot catch any
    faster than he already was."""
    call = saving_to_the_flag(a_rival(115), None, lap=6, laps_total=20)
    assert call is None


# --- what it refuses --------------------------------------------------------

def test_an_unread_exit_figure_is_not_a_full_tank():
    """CLAUDE.md rule 3. The columns are drawn only while a car is standing,
    so a missed reading is the ordinary case rather than an error."""
    rival = Rival(name="X", stop=Stop(lap=5, fuel_out_l=None), pitted=True)
    assert fuel_shortfall(rival, 8.0, laps_total=20) is None
    assert saving_to_the_flag(rival, 8.0, lap=6, laps_total=20) is None


def test_a_race_of_unknown_length_prices_nothing():
    assert saving_to_the_flag(a_rival(110), None, lap=6,
                              laps_total=None) is None


def test_a_car_that_has_not_stopped_is_not_reasoned_about():
    assert fuel_shortfall(Rival(name="X"), 8.0, laps_total=20) is None


def test_his_own_burn_is_preferred_to_ours():
    """`profile.py` puts 0.4 L/lap outside reading error, which over fifteen
    laps is six litres - enough on its own to invent a shortfall."""
    thirsty = a_rival(110, burn=9.0)
    assert fuel_shortfall(thirsty, 8.0, laps_total=20).needs == 135.0
    ours_only = Rival(name="X", stop=Stop(lap=5, fuel_out_l=110), pitted=True)
    assert fuel_shortfall(ours_only, 8.0, laps_total=20).needs == 120.0


# --- the road in, which did not exist ---------------------------------------

def test_a_rival_call_reaches_the_ranking():
    """**Everything below this was correct and unreachable.** `must_stop_by`
    and `rival_boxed` were called only by their own tests, and the controller
    emitted `rival_stopped` into a signal nothing was connected to."""
    state = RaceState(lap=6, laps_total=20, fuel_per_lap_l=8.0)
    state.rivals["Boxhead"] = a_rival(110)
    call = next_call(state)
    assert call is not None and call.kind == RIVAL_SAVING


def test_no_rivals_seen_costs_the_ranking_nothing():
    assert candidates(RaceState(lap=6, laps_total=20)) == []


def test_two_rivals_are_both_offered_and_the_ranking_picks():
    """A race has several and only one thing is said a lap."""
    state = RaceState(lap=6, laps_total=20, fuel_per_lap_l=8.0)
    state.rivals["Boxhead"] = a_rival(110)
    state.rivals["Rocky"] = a_rival(41, name="Rocky")
    offered = candidates(state)
    assert {c.kind for c in offered} == {RIVAL_SAVING, RIVAL_COMMITTED}
    # A forced stop outranks a lift: it is worth a pit loss, not tenths.
    assert next_call(state).kind == RIVAL_COMMITTED


def test_the_bigger_opportunity_is_the_one_that_gets_said():
    """A call kind is said once a stint, so with two rivals saving the second
    is not said at all. `next_call` sorts by kind and Python's sort is stable,
    which would have picked whichever car happened to stop first."""
    state = RaceState(lap=6, laps_total=20, fuel_per_lap_l=8.0)
    state.rivals["Small"] = a_rival(114, name="Small")   # 1.5 s over the run
    state.rivals["Big"] = a_rival(100, name="Big")       # 5.0 s over the run
    assert next_call(state).call.startswith("Big")
