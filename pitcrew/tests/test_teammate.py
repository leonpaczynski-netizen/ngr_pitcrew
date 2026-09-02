"""Where the teammate is, and the larger number of things the screen will not say."""
from __future__ import annotations

from pitcrew.race.rivals import Stop
from pitcrew.race.teammate import (
    Teammate,
    fuel_to_the_flag,
    separation_s,
    status,
    where_is_he,
)


def mate(position=3, ours=5, **kw):
    return Teammate(name="Rocky", position=position, ours=ours, **kw)


# --- where he is -----------------------------------------------------------

def test_position_is_exact_because_the_board_is_in_race_order():
    assert where_is_he(mate(3, 5)) == "Rocky is P3, 2 places ahead."
    assert where_is_he(mate(7, 5)) == "Rocky is P7, 2 places behind."


def test_one_place_reads_as_one_place():
    assert "1 place ahead" in where_is_he(mate(4, 5))


def test_a_teammate_not_on_the_board_gets_no_sentence():
    assert where_is_he(Teammate(name="Rocky")) is None


def test_without_our_own_position_his_place_still_stands_alone():
    assert where_is_he(Teammate(name="Rocky", position=3)) == "Rocky is P3."


def test_nearby_is_about_places_not_seconds():
    assert mate(3, 5).nearby
    assert not mate(1, 9).nearby


# --- separation ------------------------------------------------------------

def test_the_gap_is_only_real_when_he_is_the_car_next_to_us():
    seconds, why = separation_s(mate(4, 5), gap_ahead_s=1.4, gap_behind_s=9.0)
    assert seconds == 1.4 and why == "gap to the car ahead"
    seconds, why = separation_s(mate(6, 5), gap_ahead_s=1.4, gap_behind_s=9.0)
    assert seconds == 9.0 and why == "gap to the car behind"


def test_a_teammate_two_places_away_has_no_gap_and_says_why():
    """GT7 draws three gaps and no others. Building one from lap times would be
    worse than none at 0.918 s of lap-to-lap noise."""
    seconds, why = separation_s(mate(3, 5), gap_ahead_s=1.4, gap_behind_s=9.0)
    assert seconds is None
    assert "next to you" in why


def test_a_gap_that_was_not_drawn_is_not_a_gap_of_zero():
    seconds, why = separation_s(mate(4, 5), gap_ahead_s=None,
                                gap_behind_s=None)
    assert seconds is None and "not drawn" in why


def test_a_teammate_off_the_board_has_no_separation():
    seconds, why = separation_s(Teammate(name="Rocky"), 1.0, 1.0)
    assert seconds is None and "not on the board" in why


# --- his fuel --------------------------------------------------------------

def test_a_tank_that_reaches_the_flag_reads_true():
    stop = Stop(lap=11, fuel_in_l=12.0, fuel_out_l=80.0)
    assert fuel_to_the_flag(mate(stop=stop), laps_left=9,
                            burn_per_lap_l=8.0) is True


def test_a_tank_short_of_the_flag_reads_false():
    stop = Stop(lap=11, fuel_in_l=12.0, fuel_out_l=41.0)
    assert fuel_to_the_flag(mate(stop=stop), laps_left=9,
                            burn_per_lap_l=8.0) is False


def test_an_unread_tank_is_neither_full_nor_empty():
    """CLAUDE.md rule 3: the answer is None, not False."""
    assert fuel_to_the_flag(mate(stop=Stop(lap=11)), laps_left=9,
                            burn_per_lap_l=8.0) is None
    assert fuel_to_the_flag(mate(), laps_left=9, burn_per_lap_l=8.0) is None


# --- the whole status ------------------------------------------------------

def test_before_his_stop_the_useful_fact_is_that_he_has_not_stopped():
    """No pit columns drawn is an assertion, not a gap."""
    said = status(mate(3, 5))
    assert said == ["Rocky is P3, 2 places ahead.", "He has not stopped yet."]


def test_after_his_stop_the_useful_fact_is_whether_he_can_finish():
    stop = Stop(lap=11, fuel_in_l=12.0, fuel_out_l=41.0)
    said = status(mate(3, 5, pitted=True, stop=stop), laps_left=9,
                  burn_per_lap_l=8.0)
    assert "come in again" in said[-1]


def test_an_adjacent_teammate_gets_his_seconds_in_the_same_sentence():
    said = status(mate(4, 5), gap_ahead_s=1.4)
    assert said[0] == "Rocky is P4, 1 place ahead, 1.4 seconds up the road."


def test_a_teammate_who_stopped_with_an_unreadable_tank_says_so():
    said = status(mate(3, 5, pitted=True, stop=Stop(lap=11)), laps_left=9,
                  burn_per_lap_l=8.0)
    assert "not readable" in said[-1]


def test_nothing_here_gives_a_team_order():
    """Two drivers agree what to do about each other beforehand. This says
    where he is and stops."""
    stop = Stop(lap=11, fuel_in_l=12.0, fuel_out_l=80.0)
    said = " ".join(status(mate(4, 5, pitted=True, stop=stop), laps_left=9,
                           burn_per_lap_l=8.0, gap_ahead_s=1.4)).lower()
    for order in ("hold station", "let him", "let past", "stay behind",
                  "move over", "swap"):
        assert order not in said
