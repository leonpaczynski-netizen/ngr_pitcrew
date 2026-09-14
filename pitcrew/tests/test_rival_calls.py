"""The rival call layer, including the much longer list of things it refuses.

Every figure in here is a real one: the Spa replay's own entry and exit fuel,
his measured 8 L/lap at Spa and the 1.0 L/s refuel rate confirmed three ways.
"""
from pitcrew.race.calls import (
    CLOSING,
    DECISION,
    FACT,
    HIGH,
    REJOIN,
    register_of,
)
from pitcrew.race.gaps import GapTrend
from pitcrew.race.rival_calls import (
    RIVAL_BOXED,
    RIVAL_COMMITTED,
    STAY_OUT_FUEL,
    Rival,
    closing_call,
    must_stop_by,
    rejoin_call,
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
    # 72 L needed less 10 aboard = 62 s of fill, plus the 16.9 s dead time
    # before a hose is connected. "Standing" means one thing on this voice.
    assert "79 seconds standing" in call.reason


# --- must_stop_by ----------------------------------------------------------

def test_a_forced_second_stop_is_said():
    call = must_stop_by(_rival(left_on=41.0), SPA_BURN, lap=11, laps_total=20)
    assert call is not None
    assert "lap 16" in call.reason and "stop again" in call.reason


def test_a_limit_beyond_the_flag_binds_nothing_so_is_not_said():
    """The Spa replay's own defect: "must stop by lap 22" in a 20-lap race."""
    assert must_stop_by(_rival(left_on=93.0), SPA_BURN, lap=11,
                        laps_total=20) is None


def test_without_a_race_length_it_asserts_nothing():
    """**It used to report the reach anyway**, on the argument that nothing to
    compare against is not a reason to withhold a fact. But the sentence it
    speaks is not the reach - it is "so he has to stop again", and with no race
    length there is no way to tell a forced stop from a car that lifts to the
    flag. That is exactly the over-claim `short_to_the_flag` was written to
    correct, left live on the branch where least is known.

    It is not a rare branch: `laps_total` is None until the coordinator has a
    distance, and the pit wall is deliberately started at arm, before the
    green, because the columns are only drawn while a car is standing."""
    assert must_stop_by(_rival(left_on=41.0), SPA_BURN, lap=11) is None


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
    # Row 1.10: "Stay out." and the fold's "Staying out? You should make
    # it." are one syllable apart and mean different things - this is *do
    # not box yet*, that is *you have driven past the box and it works*.
    assert call.call == "Don't box yet."
    # NOT "the tank cannot reach the flag": under a helmet those are the words
    # of an emergency and this call means the opposite - too much fuel aboard.
    assert "Too much fuel aboard" in call.reason
    assert "cannot reach" not in call.reason


def test_above_the_tank_clamp_there_is_no_seconds_argument_so_nothing_is_said():
    """The correction. The fill is the same length whatever lap it happens on,
    so "every lap you stay out is a shorter stop" was a claim of eight seconds
    a lap where the true figure is zero."""
    assert stay_out(lap=8, laps_left=12, burn_per_lap_l=SPA_BURN,
                    refuel_rate_lps=RATE, capacity_l=100.0, laps_total=20,
                    planned_stop_lap=11) is None


def test_a_rival_who_came_in_with_more_than_he_needs_is_refused_not_zeroed():
    """CLAUDE.md rule 9, in the module that quotes it. He is not standing for
    zero seconds - he is doing something this arithmetic does not describe."""
    assert rival_boxed(_rival(came_in=90.0), lap=11, laps_left=9,
                       burn_per_lap_l=SPA_BURN, refuel_rate_lps=RATE,
                       ours=None) is None


def test_on_and_after_the_planned_lap_it_goes_quiet():
    """`planned_stop_lap` is the plan's in-lap: it is in progress with one
    lap fewer completed, where the box call says "Box this lap."."""
    for lap in (10, 11):
        assert stay_out(lap=lap, laps_left=20 - lap, burn_per_lap_l=SPA_BURN,
                        refuel_rate_lps=RATE, capacity_l=100.0,
                        laps_total=20, planned_stop_lap=11) is None


def test_where_a_lap_of_fuel_is_not_worth_saying_nothing_is_said():
    # A circuit burning 2 L/lap never comes near the tank clamp, so there is
    # no lap on which deferring shortens the stop at all.
    assert stay_out(lap=8, laps_left=12, burn_per_lap_l=2.0,
                    refuel_rate_lps=RATE, capacity_l=100.0, laps_total=20,
                    planned_stop_lap=11) is None


def test_an_unmeasured_refuel_rate_refuses_rather_than_assumes_one():
    assert stay_out(lap=8, laps_left=12, burn_per_lap_l=SPA_BURN,
                    refuel_rate_lps=None, capacity_l=100.0, laps_total=20,
                    planned_stop_lap=11) is None


def test_a_rivals_own_burn_is_used_where_the_book_has_watched_him():
    """Applying OUR rate to him is a stated fallback, not a measurement. At
    0.5 L/lap out over twelve laps that is six litres - six seconds - on calls
    gated at eight, so a call could fire on nothing but the mismatch."""
    thirsty = Rival(name="Rocky", pitted=True, burn_per_lap_l=10.0,
                    stop=Stop(lap=11, fuel_in_l=12.0, fuel_out_l=41.0))
    # 41 L at HIS 10 L a lap reaches lap 15, not the lap 16 ours would give.
    call = must_stop_by(thirsty, SPA_BURN, lap=11, laps_total=20)
    assert call is not None and "lap 15" in call.reason


def test_without_his_own_burn_ours_stands_in(): 
    borrowed = Rival(name="Rocky", pitted=True,
                     stop=Stop(lap=11, fuel_in_l=12.0, fuel_out_l=41.0))
    call = must_stop_by(borrowed, SPA_BURN, lap=11, laps_total=20)
    assert call is not None and "lap 16" in call.reason


# --- the rejoin, which decides a place rather than seconds ------------------

def test_a_car_closer_than_the_stop_is_told_about():
    """The engineer's largest omission: every car within our own pit loss
    behind us comes out in front, and it is one subtraction."""
    call = rejoin_call(lap=11, gap_behind_s=40.0, litres_to_take=60.0,
                       refuel_rate_lps=1.0, pit_loss_s=19.5, who="Rocky")
    assert call is not None and call.confidence == HIGH
    assert "comes out in front" in call.call
    # Row 1.10: both REJOIN branches name the stop's unit the same way.
    assert "40 seconds back" in call.reason
    assert "80 second stop" in call.reason


def test_coming_out_comfortably_ahead_is_not_worth_saying():
    assert rejoin_call(lap=11, gap_behind_s=140.0, litres_to_take=60.0,
                       refuel_rate_lps=1.0, pit_loss_s=19.5) is None


def test_marginal_is_said_because_a_silence_is_not_actionable():
    call = rejoin_call(lap=11, gap_behind_s=80.0, litres_to_take=60.0,
                       refuel_rate_lps=1.0, pit_loss_s=19.5)
    assert call is not None and "too close to call" in call.call


def test_no_gap_and_no_pit_loss_mean_no_rejoin_call():
    """CLAUDE.md rule 3. An unread gap is not a gap of zero, and it must not
    produce a confident "he comes out in front"."""
    assert rejoin_call(lap=11, gap_behind_s=None, litres_to_take=60.0,
                       refuel_rate_lps=1.0, pit_loss_s=19.5) is None
    assert rejoin_call(lap=11, gap_behind_s=40.0, litres_to_take=60.0,
                       refuel_rate_lps=1.0, pit_loss_s=None) is None


# --- the closing rate, which is a fact and never an instruction -------------

def test_closing_is_said_with_the_laps_behind_it():
    """CLAUDE.md rule 4. The rate has to clear a random walk, which is a much
    larger number than it looks - see `gaps.TREND_WORTH_SAYING_S`."""
    trend = GapTrend(side="ahead")
    for lap, gap in enumerate([10.0, 8.9, 7.8, 6.7, 5.6], start=6):
        trend.note(lap, gap)
    call = closing_call(trend, lap=10, who="Rocky")
    assert call is not None
    assert "taking" in call.call and "Rocky" in call.call
    assert "laps at that rate" in call.reason


def test_losing_ground_is_said_too():
    trend = GapTrend(side="ahead")
    for lap, gap in enumerate([5.0, 6.1, 7.2, 8.3, 9.4], start=6):
        trend.note(lap, gap)
    call = closing_call(trend, lap=10)
    assert call is not None and "losing" in call.call


def test_the_car_behind_closing_is_said_the_other_way_round():
    """CLAUDE.md rule 13. The same shrinking gap means us catching him on one
    side and him catching us on the other, and those demand opposite driving."""
    behind = GapTrend(side="behind")
    for lap, gap in enumerate([10.0, 8.9, 7.8, 6.7, 5.6], start=6):
        behind.note(lap, gap)
    call = closing_call(behind, lap=10, who="Rocky")
    assert call is not None
    assert "Rocky is taking" in call.call and "out of you" in call.call


def test_a_car_behind_dropping_away_is_not_worth_saying():
    behind = GapTrend(side="behind")
    for lap, gap in enumerate([5.0, 6.1, 7.2, 8.3, 9.4], start=6):
        behind.note(lap, gap)
    assert closing_call(behind, lap=10) is None


def test_too_few_laps_is_not_a_trend():
    trend = GapTrend()
    for lap, gap in enumerate([8.0, 7.0, 6.0], start=6):
        trend.note(lap, gap)
    assert closing_call(trend, lap=8) is None


def test_a_rate_inside_the_random_walk_is_not_said():
    """0.15 s/lap fired on three five-lap windows in four where the two cars
    had identical pace. Half a second a lap is still inside it."""
    trend = GapTrend()
    for lap, gap in enumerate([8.0, 7.6, 7.2, 6.8, 6.4], start=6):
        trend.note(lap, gap)
    assert closing_call(trend, lap=10) is None


def test_the_closing_call_is_a_fact_and_the_rejoin_a_decision():
    """What to do about catching somebody is the driver's; where a stop puts
    him is the engineer's."""
    assert register_of(CLOSING) == FACT
    assert register_of(REJOIN) == DECISION
