"""The one thing in the app that speaks mid-lap, and what keeps it quiet.

*"Agree data should come on straights not corners."* - the driver, 22 Aug.

`race/straight.py` was written from a measurement and then never called. The
measurement is the reason it cannot be a throttle test: sustained full throttle
over a clean Monza race lap finds **nineteen windows**, broken by upshifts
rather than by corners, several of them above 1.7 g. Speaking at 2.78 g is
worse than speaking in a braking zone. With the lateral gate it is five.

The data tier MOVED here off the crossing rather than being added, so these
tests are mostly about the budget being unchanged.
"""
from __future__ import annotations

from pitcrew.race.colour import CHATTY, DATA, NORMAL, QUIET, ColourCalls
from pitcrew.race.straight import MAX_LATERAL_G, MIN_HELD_S, Straight


def straight_frames(seconds: float, *, hz: float = 60.0):
    """Full throttle, no lateral load - the main straight."""
    return [{"throttle_pct": 100.0, "speed_ms": 70.0, "yaw_rate": 0.0,
             "now": i / hz} for i in range(int(seconds * hz))]


def drive(detector: Straight, frames) -> list[bool]:
    return [detector.update(**f) for f in frames]


# ------------------------------------------------------------ the detector

def test_a_long_flat_full_throttle_run_is_a_straight():
    assert any(drive(Straight(), straight_frames(MIN_HELD_S + 1.0)))


def test_it_is_not_a_straight_until_it_has_been_held():
    """A momentary straightening mid-corner is not a straight."""
    assert not any(drive(Straight(), straight_frames(MIN_HELD_S - 0.5)))


def test_lateral_load_disqualifies_it_however_open_the_throttle():
    """**The gate that does the real work.** Monza's flat-out kinks and the
    Parabolica exit are all full throttle and all above 1.5 g."""
    detector = Straight()
    # v * yaw / 9.81 well over the limit, at full throttle throughout.
    frames = [{"throttle_pct": 100.0, "speed_ms": 70.0, "yaw_rate": 0.25,
               "now": i / 60.0} for i in range(300)]
    assert not any(drive(detector, frames))


def test_lifting_ends_the_straight_and_resets_the_hold():
    detector = Straight()
    assert any(drive(detector, straight_frames(MIN_HELD_S + 1.0)))
    assert detector.update(throttle_pct=10.0, speed_ms=70.0, yaw_rate=0.0,
                           now=99.0) is False
    assert detector.held_s == 0.0


def test_it_stays_true_for_the_rest_of_the_straight():
    """So a caller with something to say does not have to catch one frame -
    which is exactly why the caller de-duplicates on the LAP, not the frame."""
    results = drive(Straight(), straight_frames(MIN_HELD_S + 2.0))
    assert results[-1] and results[-2] and results[-3]


def test_a_missing_channel_is_not_a_straight():
    """The 'A' packet format carries no yaw. Absent is not zero."""
    detector = Straight()
    assert detector.update(throttle_pct=100.0, speed_ms=70.0, yaw_rate=None,
                           now=1.0) is False


def test_the_lateral_limit_is_the_documented_one():
    detector = Straight()
    just_inside = MAX_LATERAL_G * 9.81 / 70.0 * 0.9
    frames = [{"throttle_pct": 100.0, "speed_ms": 70.0,
               "yaw_rate": just_inside, "now": i / 60.0} for i in range(300)]
    assert any(drive(detector, frames))


# --------------------------------------------------------- the data tier

def a_colour(level=CHATTY) -> ColourCalls:
    return ColourCalls(level=level)


def test_the_straight_reads_out_a_measured_number():
    call = a_colour().data_line(lap=4, fuel_laps_in_hand=6.2)
    assert call is not None and call.kind == DATA
    assert "6.2" in call.spoken()


def test_only_chatty_mode_reads_numbers_out():
    for level in (QUIET, NORMAL):
        assert a_colour(level).data_line(lap=4, fuel_laps_in_hand=6.2) is None


def test_at_most_one_number_a_lap():
    """`Straight.update` stays true for the whole straight, so without this a
    caller polling every frame would be told yes six hundred times."""
    colour = a_colour()
    assert colour.data_line(lap=4, fuel_laps_in_hand=6.2) is not None
    assert colour.data_line(lap=4, fuel_laps_in_hand=6.2) is None
    assert colour.data_line(lap=5, fuel_laps_in_hand=6.1) is not None


def test_with_nothing_measured_it_says_nothing():
    """Every number in this tier is measured. None available is silence, not
    a sentence about having no data."""
    assert a_colour().data_line(lap=4) is None


# ----------------------------------------------- the budget is UNCHANGED

def test_the_crossing_no_longer_spends_a_lap_on_a_number():
    """**The point of moving it.** Ranked at the crossing, the data tier
    displaced a FINDING on every lap it fired - and findings are rare where a
    number is always available, so the rare thing lost every collision."""
    colour = a_colour()
    call = colour.consider(lap=3, lap_time_ms=92_000, laps_remaining=17,
                           fuel_laps_in_hand=6.2, include_data=False)
    assert call is None or call.kind != DATA


def test_the_crossing_still_speaks_findings():
    """Spaced past `GAP_LAPS[CHATTY]`, which is 3: the gap belongs to the
    finding kinds and holding a number back does not shorten it."""
    colour = a_colour()
    # Three laps of history before a best is believed, and spaced past the gap.
    for lap, time_ms in ((1, 95_000), (2, 95_400), (3, 95_200)):
        colour.consider(lap=lap, lap_time_ms=time_ms,
                        laps_remaining=20 - lap, include_data=False)
    best = colour.consider(lap=8, lap_time_ms=92_000, laps_remaining=12,
                           include_data=False)
    assert best is not None and best.kind != DATA


def test_a_gapped_chatty_lap_is_now_silent_at_the_line():
    """**And that is the intended change.** In chatty mode a gapped crossing
    used to read out a number; it stays quiet now and the straight carries it,
    which is where he asked for numbers to be."""
    colour = a_colour()
    colour.consider(lap=1, lap_time_ms=95_000, laps_remaining=19,
                    include_data=False)
    assert colour.consider(lap=2, lap_time_ms=95_500, laps_remaining=18,
                           fuel_laps_in_hand=6.2, include_data=False) is None
    assert colour.data_line(lap=2, fuel_laps_in_hand=6.2) is not None


def test_include_data_defaults_to_the_old_behaviour():
    """Nothing that has not been told about the straight loses its numbers."""
    colour = a_colour()
    call = colour.consider(lap=3, lap_time_ms=92_000, laps_remaining=17,
                           fuel_laps_in_hand=6.2)
    assert call is not None


def test_a_fresh_set_makes_the_numbers_news_again():
    colour = a_colour()
    assert colour.data_line(lap=4, fuel_laps_in_hand=6.2) is not None
    colour.new_stint()
    assert colour.data_line(lap=4, fuel_laps_in_hand=6.2) is None, \
        "the per-lap guard is about the LAP, and the lap has not changed"
    assert colour.data_line(lap=5, fuel_laps_in_hand=6.2) is not None
