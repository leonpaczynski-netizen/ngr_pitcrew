"""A rival short of fuel either lifts or stops again, and both are good for us.

`must_stop_by` used to fire whenever a car could not reach the flag on its exit
fuel and say "he has to stop again" - right when he is miles short and wrong
when he is a few per cent light, because a stop costs a pit loss and a lift
costs tenths. A driver told to wait for a stop that never comes does not attack
the car in front of him that is going slowly.

**The call does not say WHY he is short**, and the first version did. "He is
saving to the flag" asserts intent, and `profile.py`'s own header refuses
exactly that: a car that stopped early because it was short looks identical to
one that stopped early to jump somebody. The app cannot tell a lift from a
two-stop - and it does not need to, because either way the instruction is the
same.

**Every fixture here fits in the tank.** The first version of these tests used
exit fuel of 110, 114, 118 and 130 litres in a game whose tank is 100, so the
headline example could not happen and the one sweep that could have caught the
tank-cap defect could not see it.
"""
from __future__ import annotations

from pitcrew.race.calls import (
    RIVAL_COMMITTED,
    RIVAL_SHORT,
    RaceState,
    clear_stint,
    next_call,
)
from pitcrew.race.rival_calls import (
    TANK_L,
    Rival,
    candidates,
    fuel_shortfall,
    must_stop_by,
    short_to_the_flag,
)
from pitcrew.race.rivals import Stop

# Spa, 20 laps, 8 L a lap. A stop on lap 11 leaves nine laps to the flag and
# needs 72 L - comfortably inside the 100 L tank, so the fill is a CHOICE and
# the arithmetic is about him rather than about the tank.
LAPS, BURN, STOP_LAP = 20, 8.0, 11
NEEDS = (LAPS - STOP_LAP) * BURN            # 72 L


def a_rival(fuel_out, *, lap=STOP_LAP, burn=BURN, name="Boxhead", **kw):
    return Rival(name=name, stop=Stop(lap=lap, fuel_out_l=fuel_out),
                 burn_per_lap_l=burn, pitted=True, **kw)


def said(rival, *, lap=12, laps_total=LAPS, our_position=None):
    """Whatever George would say about this car, or None."""
    return (short_to_the_flag(rival, None, lap=lap, laps_total=laps_total,
                              our_position=our_position)
            or must_stop_by(rival, None, lap=lap, laps_total=laps_total))


# --- the three cases --------------------------------------------------------

def test_a_car_that_reaches_the_flag_is_not_worth_a_call():
    assert said(a_rival(NEEDS + 10)) is None


def test_a_car_a_few_per_cent_light_is_short_and_that_is_the_call():
    """The case that used to be silent, and the one worth driving to."""
    call = said(a_rival(58.0))                     # 14 L light of 72
    assert call is not None and call.kind == RIVAL_SHORT
    assert call.call == "Boxhead is short to the flag. Attack."
    assert "14 litres light over 9 laps" in call.reason
    assert "he lifts or he stops again" in call.reason


def test_the_call_never_claims_to_know_why_he_is_short():
    """Intent is not observable. A car saving to the flag and a car on a
    two-stop are the same picture from outside."""
    call = said(a_rival(58.0))
    assert "saving" not in call.call.lower()
    assert "saving" not in call.reason.lower()


def test_no_pace_figure_is_spoken_for_a_car_we_have_never_timed():
    """It used to say "about 0.2 seconds a lap" - a linear interpolation
    through one measured point on OUR car, applied to his. Three assumptions
    presented as a measurement (rule 5). The model still decides whether to
    speak at all; it no longer speaks its own output."""
    call = said(a_rival(58.0))
    assert "seconds a lap" not in call.reason
    assert "short-shift" not in call.reason


def test_a_car_that_is_genuinely_short_still_has_to_stop():
    call = said(a_rival(20.0))
    assert call is not None and call.kind == RIVAL_COMMITTED
    assert "has to stop again" in call.reason


def test_the_two_calls_never_both_fire_for_one_car():
    for fuel in range(0, int(TANK_L) + 1, 2):
        rival = a_rival(float(fuel))
        both = [short_to_the_flag(rival, None, lap=12, laps_total=LAPS),
                must_stop_by(rival, None, lap=12, laps_total=LAPS)]
        assert len([c for c in both if c is not None]) <= 1, fuel


# --- the tank ---------------------------------------------------------------

def test_a_brim_full_tank_that_is_still_short_says_it_was_full():
    """**A fill cannot exceed the tank.** A rival who leaves on 100 L and is
    still short did not choose the shortfall - he took everything the game
    allows - so nothing about it says what he intends. The call says the tank
    was full, which is the fact that makes "he lifts or he stops again" the
    only reading."""
    early = a_rival(TANK_L, lap=6)               # needs 112 L, has 100
    call = said(early, lap=7)
    assert call.kind == RIVAL_SHORT
    assert "He left on a full tank." in call.reason


def test_one_lap_of_stop_timing_no_longer_flips_the_meaning():
    """It used to flip between "he has to stop again" and "he is saving to the
    flag. Attack." on one lap of difference, for an identical car with an
    identical full tank - two calls demanding opposite driving. They are now
    the same claim at different strengths: short, and cannot-possibly-make-it."""
    kinds = [said(a_rival(TANK_L, lap=n), lap=n + 1) for n in (3, 4, 5, 6)]
    assert kinds[0].kind == RIVAL_COMMITTED     # 136 L needed: hopeless
    assert all(c.kind == RIVAL_SHORT for c in kinds[1:])
    for call in kinds[1:]:
        assert "he lifts or he stops again" in call.reason


# --- what it refuses --------------------------------------------------------

def test_a_race_of_unknown_length_asserts_nothing_at_all():
    """**Both** calls refuse. `must_stop_by` went on claiming a forced stop
    with no race length - verbatim the defect the short call exists to fix -
    and `laps_total` is None before the coordinator has a distance, while the
    pit wall is deliberately started at arm, before the green."""
    assert said(a_rival(66.0), laps_total=None) is None
    assert said(a_rival(20.0), laps_total=None) is None


def test_an_exit_figure_that_is_only_a_lower_bound_prices_nothing():
    """A car drops off the visible top eight exactly while it is standing, so
    a visit closed on the clock has `max(readings)` from the middle of the
    fill. Measured shape: 10 -> 89 L read to 50 L looks just like a car that
    chose to underfill, and 50 L against 72 needed is a shortfall that is not
    there."""
    bounded = a_rival(50.0, exit_is_a_bound=True)
    assert fuel_shortfall(bounded, None, laps_total=LAPS) is None
    assert said(bounded) is None
    assert said(a_rival(50.0)) is not None       # the same figure, measured


def test_the_uncertainty_grows_with_the_laps_still_to_run():
    """It was a flat four litres, justified as "two readings and a burn". The
    readings are integers and contribute about two; the burn is the dominant
    term and `profile.py` puts driver-to-driver difference at 0.4 L/lap, which
    over fifteen laps is six litres on its own."""
    near = fuel_shortfall(a_rival(60.0, lap=17), None, laps_total=LAPS)
    far = fuel_shortfall(a_rival(60.0, lap=2), None, laps_total=LAPS)
    assert near.error_l < far.error_l
    assert far.error_l > 4.0            # the old flat floor was over-confident


def test_a_shortfall_inside_the_uncertainty_is_not_a_finding():
    assert short_to_the_flag(a_rival(NEEDS - 3.0), None, lap=12,
                             laps_total=LAPS) is None


def test_nothing_is_said_with_the_race_nearly_over():
    """A shortfall he has to drive out over two laps costs him a fraction of a
    second in total, and "14 litres light over 9 laps" said with two to go
    describes a window seven-ninths spent."""
    assert short_to_the_flag(a_rival(58.0), None, lap=19,
                             laps_total=LAPS) is None


def test_a_car_far_up_the_road_is_not_something_to_attack():
    """§5.5 asks for an instruction he can act on. "Attack" a car six places
    away is noise - and an unknown position is not a refusal, because the
    board reads worst exactly where it matters."""
    far = a_rival(58.0, position=1)
    assert short_to_the_flag(far, None, lap=12, laps_total=LAPS,
                             our_position=9) is None
    assert short_to_the_flag(far, None, lap=12, laps_total=LAPS,
                             our_position=3) is not None
    assert short_to_the_flag(a_rival(58.0), None, lap=12, laps_total=LAPS,
                             our_position=9) is not None    # position unknown


def test_an_unread_exit_figure_is_not_a_full_tank():
    rival = Rival(name="X", stop=Stop(lap=STOP_LAP, fuel_out_l=None),
                  pitted=True)
    assert fuel_shortfall(rival, BURN, laps_total=LAPS) is None
    assert said(rival) is None


def test_a_car_that_has_not_stopped_is_not_reasoned_about():
    assert fuel_shortfall(Rival(name="X"), BURN, laps_total=LAPS) is None


def test_his_own_burn_is_preferred_to_ours_and_the_call_says_which():
    """`profile.py` puts 0.4 L/lap outside reading error - over nine laps that
    is nearly four litres, enough on its own to invent a shortfall."""
    ours_only = Rival(name="X", stop=Stop(lap=STOP_LAP, fuel_out_l=58.0),
                      pitted=True)
    assert fuel_shortfall(ours_only, BURN, laps_total=LAPS).needs == NEEDS
    on_ours = short_to_the_flag(ours_only, BURN, lap=12, laps_total=LAPS)
    assert "on our burn" in on_ours.reason
    assert "on our burn" not in said(a_rival(58.0)).reason


# --- the road in ------------------------------------------------------------

def test_a_rival_call_reaches_the_ranking():
    state = RaceState(lap=12, laps_total=LAPS, fuel_per_lap_l=BURN)
    state.rivals["Boxhead"] = a_rival(58.0)
    call = next_call(state)
    assert call is not None and call.kind == RIVAL_SHORT


def test_no_rivals_seen_costs_the_ranking_nothing():
    assert candidates(RaceState(lap=12, laps_total=LAPS)) == []


def test_a_forced_stop_outranks_a_lift():
    state = RaceState(lap=12, laps_total=LAPS, fuel_per_lap_l=BURN)
    state.rivals["Boxhead"] = a_rival(58.0)
    state.rivals["Rocky"] = a_rival(20.0, name="Rocky")
    assert {c.kind for c in candidates(state)} == {RIVAL_SHORT,
                                                   RIVAL_COMMITTED}
    assert next_call(state).kind == RIVAL_COMMITTED


def test_the_more_urgent_forced_stop_is_the_one_that_gets_said():
    """`must_stop_by` carried no severity, so several forced stops all tied at
    zero and a stable sort picked whichever car's columns the sampler happened
    to catch first - and a kind is said once, so the other was never said."""
    state = RaceState(lap=12, laps_total=LAPS, fuel_per_lap_l=BURN)
    state.rivals["First"] = a_rival(40.0, name="First")     # reaches lap 16
    state.rivals["Second"] = a_rival(8.0, name="Second")    # reaches lap 12
    assert next_call(state).call.startswith("Second")


def test_a_rival_is_not_announced_again_after_our_own_stop():
    """`clear_stint` drops `said` and keeps `said_tags`, so the tag is what
    makes this once-per-race. Re-announced, a shortfall frozen at his stop lap
    describes a window that is mostly spent."""
    state = RaceState(lap=12, laps_total=LAPS, fuel_per_lap_l=BURN)
    state.rivals["Boxhead"] = a_rival(58.0)
    first = next_call(state)
    state.record(first)
    clear_stint(state, tyres_changed=True)
    assert next_call(state) is None


def test_two_rivals_do_not_swallow_each_other():
    """Tagged per driver, so the second is a different occasion of one kind."""
    state = RaceState(lap=12, laps_total=LAPS, fuel_per_lap_l=BURN)
    state.rivals["Boxhead"] = a_rival(58.0)
    state.record(next_call(state))
    state.rivals["Rocky"] = a_rival(56.0, name="Rocky")
    assert next_call(state).call.startswith("Rocky")


# --- the coordinator seam, which was reachable only in production -----------

class _Seen:
    """What the pit wall hands over when a stop closes."""

    def __init__(self, driver="Boxhead", fuel_out=58.0, lap=STOP_LAP,
                 bound=False):
        self.driver = driver
        self.driver_id = 1
        self.stop = Stop(lap=lap, fuel_out_l=fuel_out)
        self.reads = 6
        self.compound_reads = 2
        self.watched_s = 40.0
        self.partial = False
        self.exit_is_a_bound = bound


def a_coordinator(lap=12):
    from pitcrew.race.coordinator import RacePhase, RaceCoordinator

    race = RaceCoordinator()
    race.phase = RacePhase.RUNNING
    race.state.lap = lap
    race.state.laps_total = LAPS
    race.state.fuel_per_lap_l = BURN
    return race


def test_a_watched_stop_becomes_a_call():
    """**The seam that did not exist.** `note_rival_stop` and the Qt slot that
    feeds it were reachable only in production; the tests wrote `state.rivals`
    by hand, which is the same shape as the defect this exists to correct."""
    race = a_coordinator()
    race.note_rival_stop(_Seen(), burn_per_lap_l=BURN, burn_stops=2)
    assert race.state.rivals["Boxhead"].burn_stops == 2
    assert next_call(race.state).kind == RIVAL_SHORT


def test_a_stop_that_arrives_before_the_green_is_refused():
    """The pit wall starts at ARM, deliberately - the columns are only drawn
    while a car is standing, so a watcher that starts late gets nothing."""
    from pitcrew.race.coordinator import RacePhase

    race = a_coordinator()
    race.phase = RacePhase.ARMED
    race.note_rival_stop(_Seen())
    assert race.state.rivals == {}


def test_a_nameless_stop_is_refused():
    race = a_coordinator()
    race.note_rival_stop(_Seen(driver=None))
    assert race.state.rivals == {}


def test_a_bounded_exit_figure_travels_and_silences_the_call():
    race = a_coordinator()
    race.note_rival_stop(_Seen(fuel_out=50.0, bound=True))
    assert race.state.rivals["Boxhead"].exit_is_a_bound
    assert next_call(race.state) is None


def test_positions_refresh_onto_a_rival_already_filed():
    """A stop's position is read while the car is STANDING, which is the one
    moment it does not describe where he is racing."""
    race = a_coordinator()
    race.note_rival_stop(_Seen(), burn_per_lap_l=BURN)
    assert race.state.rivals["Boxhead"].position is None
    race.note_rival_positions({"Boxhead": 4})
    assert race.state.rivals["Boxhead"].position == 4
    race.state.position = 12
    assert next_call(race.state) is None       # eight places away
    race.state.position = 5
    assert next_call(race.state).kind == RIVAL_SHORT
