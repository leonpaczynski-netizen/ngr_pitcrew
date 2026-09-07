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
from pitcrew.race.pit_wall import Entered
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


# --- the four that were ranked, registered, tested and unemittable ---------

from pitcrew.strategy.model import PIT_LOSS_MEASURED  # noqa: E402


def a_state(lap=8):
    """A race with the pit-lane figures the calls price a stop with."""
    state = RaceState(lap=lap, laps_total=LAPS, fuel_per_lap_l=BURN)
    state.refuel_rate_lps = 1.0            # measured
    state.pit_loss_s = 17.6                # measured, Monza
    # **The canonical constant, not the bare word.** `stop_costs_s` compares
    # against `strategy.model.PIT_LOSS_MEASURED` ("measured-this-track"), and
    # `coordinator` used to write the literal "measured" - so the comparison
    # never matched, `PIT_DEAD_TIME_S` was never added by any pit-lane call,
    # and this file called itself measured while exercising the declared
    # branch. Fixing the coordinator without fixing this would have left the
    # suite green over a stop priced 7.5 s cheap.
    state.pit_loss_source = PIT_LOSS_MEASURED
    state.fuel_capacity_l = TANK_L
    return state


def a_trend(side, readings, subject=7):
    from pitcrew.race.gaps import GapTrend

    trend = GapTrend(side=side)
    for lap, gap in readings:
        trend.note(lap, gap, subject=subject)
    return trend


def test_a_rival_entering_the_lane_is_said_while_he_is_still_in_it():
    """**`rival_boxed` ranks ABOVE both wired calls** on the stated argument
    that it is "the one that can still be acted on", and it could not be
    emitted. It is fed by its own event, because the finished stop arrives
    when he LEAVES - a minute too late for a call whose whole content is what
    his fill is about to cost him."""
    state = a_state()
    state.our_stop = Stop(lap=6, fuel_in_l=20.0, fuel_out_l=70.0)
    state.rivals_entering.append(Entered(driver="Boxhead", driver_id=1, lap=8,
                                         fuel_in_l=12, partial=False))
    call = next_call(state)
    assert call.kind == "rival-boxed"
    assert "Boxhead has boxed on 12 litres." == call.call
    assert "seconds longer than you did" in call.reason
    # **Drained.** Left in place, the same lap-8 entry was re-spoken after our
    # own stop reset `said`, five laps later, with a swing computed against a
    # tank that had changed underneath it.
    assert state.rivals_entering == []


def test_two_cars_entering_in_one_frame_are_both_offered():
    """A single slot lost one of them before either was spoken."""
    state = a_state()
    state.rivals_entering += [
        Entered(driver="Boxhead", driver_id=1, lap=8, fuel_in_l=12,
                partial=False),
        Entered(driver="Rocky", driver_id=2, lap=8, fuel_in_l=6,
                partial=False)]
    boxed = [c for c in candidates(state) if c.kind == "rival-boxed"]
    assert {c.call.split()[0] for c in boxed} == {"Boxhead", "Rocky"}


def test_an_entry_figure_that_is_only_an_upper_bound_prices_nothing():
    """`partial` means nobody saw him arrive, so the lowest reading is a bound
    on what he came in with. The mirror of the exit bound."""
    state = a_state()
    state.rivals_entering.append(Entered(driver="Boxhead", driver_id=1, lap=8,
                                         fuel_in_l=12, partial=True))
    assert [c for c in candidates(state) if c.kind == "rival-boxed"] == []


def test_a_rivals_fill_cannot_exceed_the_tank():
    """A stop taken while the remaining laps cost more than a tank priced his
    fill at more than the car holds - the whole first half of a long race."""
    state = a_state(lap=2)
    state.our_stop = Stop(lap=2, fuel_in_l=5.0, fuel_out_l=100.0)
    state.rivals_entering.append(Entered(driver="Boxhead", driver_id=1, lap=2,
                                         fuel_in_l=5, partial=False))
    boxed = [c for c in candidates(state) if c.kind == "rival-boxed"]
    # 18 laps to go at 8 L/lap is 144 L; the tank is 100, so his fill is the
    # same 95 L ours was and there is no swing worth saying.
    assert boxed == []


def test_the_call_says_when_the_burn_behind_it_is_ours():
    """`_burn_of` can only find a rival's own burn after he has ALREADY
    completed a stop this race, so on his first stop ours is always what is
    used - and this call leans on it harder than the one that says so."""
    state = a_state()
    state.rivals_entering.append(Entered(driver="Rocky", driver_id=2, lap=8,
                                         fuel_in_l=6, partial=False))
    call = next(c for c in candidates(state) if c.kind == "rival-boxed")
    assert "on our burn" in call.reason


def test_a_gap_coming_down_is_said_with_the_name_the_board_gave_him():
    state = a_state()
    state.gap_ahead = a_trend("ahead", [(4, 8.0), (5, 6.5), (6, 5.0),
                                        (7, 3.5), (8, 2.0)])
    state.gap_ahead_name = "Rocky"
    call = next_call(state)
    assert call.kind == "closing"
    assert "out of Rocky" in call.call


def test_a_stop_now_that_would_drop_us_behind_is_said():
    state = a_state()
    state.stint_ends_on_lap = 10                 # the stop is in prospect
    state.gap_behind = a_trend("behind", [(8, 9.0)], subject=3)
    state.gap_behind_name = "Chook"
    state.next_stint_load_l = 68.0
    state.fuel_l = 8.0                           # so the FILL is 60 L
    # Through `candidates`: eight litres aboard is genuinely a fuel emergency
    # and `FUEL_SHORT` rightly wins the crossing. The point is that the rejoin
    # is OFFERED, and with the fill priced rather than the stint's load.
    call = next(c for c in candidates(state) if c.kind == "rejoin")
    # Lap 8 with the stop planned for lap 10: not due, so the arithmetic is
    # said as the conditional it is - "Box now" is reserved for a stop that
    # is (7 Sep 2026, noise cut 0.7).
    assert call.call == "A stop now puts you behind Chook."
    # 60 L at 1 L/s + a 17.6 s lane + the 7.5 s dead time, because the source
    # says this loss was measured here. `strategy/model.stop_overhead_s`
    # carries the evidence: Watkins 15.7 measured + 7.5 = 23.2 against a
    # frame-measured 23.07 total.
    assert "85 second stop" in call.reason


def test_a_rejoin_is_not_argued_before_the_stop_is_in_prospect():
    """It answers "if I box now, does he come out ahead?" - only asked when a
    stop is close. It carries no tag per stint, so said on lap 1 against a
    nine-second gap it was suppressed for the rest of the stint and silent on
    the lap it exists for."""
    state = a_state(lap=1)
    state.stint_ends_on_lap = 10
    state.gap_behind = a_trend("behind", [(1, 9.0)], subject=3)
    state.gap_behind_name = "Chook"
    state.next_stint_load_l = 68.0
    state.fuel_l = 8.0
    assert [c for c in candidates(state) if c.kind == "rejoin"] == []


def test_the_rejoin_prices_the_fill_and_not_the_stints_whole_load():
    """`next_stint_load_l` is what the car STARTS the next stint on; the
    litres through the hose are that minus what is aboard when we arrive.
    Priced as a fill it overstated the stop by the fuel already in the car,
    and `REJOIN_MARGIN_S` is three seconds."""
    from pitcrew.race.rival_calls import _fill_at_the_stop

    state = a_state()
    state.next_stint_load_l = 88.0
    state.fuel_l = 8.0
    assert _fill_at_the_stop(state) == 80.0
    state.fuel_l = None                          # nothing aboard is not zero
    assert _fill_at_the_stop(state) is None
    state.fuel_l = 95.0                          # arrives with more than needed
    assert _fill_at_the_stop(state) is None      # not a zero-litre stop


def test_the_tank_argument_needs_no_rival_at_all():
    """`stay_out` is about OUR fuel and survives every way reading a rival can
    fail - which is why a short-circuit on `state.rivals` being empty was the
    worst place to put one."""
    # Lap 7 of a 20-lap race on a 100 L tank: the earliest a fill can usefully
    # happen is lap 8, so there is still too much aboard to take a full one.
    state = a_state(lap=7)
    state.stint_ends_on_lap = 10        # the stop is three laps away
    assert not state.rivals
    # Through `candidates` rather than `next_call`: `BOX_SOON` ranks above it
    # and rightly wins this crossing. The point here is that it is OFFERED
    # with no rival on file at all.
    offered = [c for c in candidates(state) if c.kind == "stay-out-fuel"]
    assert offered and "Too much fuel aboard to fill" in offered[0].reason


def test_the_tank_argument_is_silent_until_a_stop_is_in_prospect():
    """It ranks immediately below `BOX_SOON` because the two answer the same
    question - so where nothing is asking it, answering outranks real calls.
    Offered from lap 1 it displaced the cold-tyre warning that opens the race."""
    state = a_state(lap=1)
    state.stint_ends_on_lap = 10
    assert next_call(state) is None


def test_no_inputs_means_no_calls_rather_than_an_exception():
    """A race with no board reader, no plan and no measured pump."""
    assert candidates(RaceState(lap=8, laps_total=LAPS)) == []


def test_every_kind_that_needs_a_rival_can_be_emitted_at_once():
    """**The test the last two commits both needed and neither had.** Four of
    these were ranked in `URGENCY`, classified in `REGISTER`, covered by unit
    tests and reachable from no production caller - and a guard added with the
    first two made three of them unreachable a second time.

    `stay-out-fuel` is the sixth and is deliberately absent here: above the
    tank clamp a lap deferred saves exactly zero seconds, so it is right that
    it says nothing in this state. It has its own test above.
    """
    state = a_state()
    state.our_stop = Stop(lap=6, fuel_in_l=20.0, fuel_out_l=70.0)
    state.rivals_entering.append(Entered(driver="Boxhead", driver_id=1, lap=8,
                                         fuel_in_l=12, partial=False))
    state.stint_ends_on_lap = 10
    state.next_stint_load_l = 68.0
    state.fuel_l = 8.0
    state.rivals["Rocky"] = a_rival(20.0, name="Rocky")
    state.rivals["Chook"] = a_rival(58.0, name="Chook")
    state.gap_ahead = a_trend("ahead", [(4, 8.0), (5, 6.5), (6, 5.0),
                                        (7, 3.5), (8, 2.0)])
    state.gap_ahead_name = "Rocky"
    state.gap_behind = a_trend("behind", [(8, 9.0)], subject=3)
    state.gap_behind_name = "Chook"
    kinds = {call.kind for call in candidates(state)}
    assert kinds == {"rival-boxed", "rival-committed", RIVAL_SHORT,
                     "closing", "rejoin"}
