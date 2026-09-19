"""Resolving a leaderboard row to a driver, and refusing to when it cannot.

The pixel-level numbers here - the 27-29 px gutter, the 9 px space, the 0.406
against 0.738 - were all measured on the Spa replay of 1 Sep 2026 and are
recorded in `roster.py` beside the constants they set.
"""
from __future__ import annotations

import numpy as np

from pitcrew.telemetry.roster import (
    NAME_SHAPE,
    SAME_NAME_MAX_DIFF,
    Roster,
    _distance,
)


def bits(*rows):
    """A tiny name bitmap from an ASCII picture."""
    grid = np.zeros(NAME_SHAPE[::-1], dtype=bool)
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            grid[y, x] = char != "."
    return grid


A = bits("####........", "#..#........", "####........")
B = bits("......####..", "......#..#..", "......####..")     # A, moved off
C = bits("############", "#..........#", "############")     # much longer
NEAR_A = bits("####........", "#..#........", "###.........")


# The pitch chain moved to `board.flag_ladder` and is tested in
# `test_board.py`. It was being done twice, by two sets of thresholds, against
# the same landmark.


# --- the distance ----------------------------------------------------------

def test_distance_ignores_the_blank_both_names_share():
    """The measured reason the metric is IoU and not a pixel count.

    Two short names sit in a mostly-empty canvas, so most of what they have in
    common is emptiness. Counting that as agreement put two different drivers
    0.204 apart - inside the distance that means "same driver".
    """
    assert _distance(A, B) > 0.9              # no overlap at all
    assert float((A != B).mean()) < 0.1       # ...yet nearly all pixels agree


def test_a_bitmap_is_identical_to_itself():
    assert _distance(A, A) == 0.0


def test_two_empty_bitmaps_are_maximally_apart_not_identical():
    """Nothing in common is not evidence of sameness."""
    empty = np.zeros(NAME_SHAPE[::-1], dtype=bool)
    assert _distance(empty, empty) == 1.0


# --- clustering ------------------------------------------------------------

def test_the_same_name_lands_in_the_same_cluster():
    roster = Roster()
    first = roster.see(A)
    assert roster.see(NEAR_A) == first
    assert roster.sightings(first) == 2


def test_a_different_name_founds_a_new_cluster():
    roster = Roster()
    assert roster.see(A) != roster.see(C)
    assert len(roster) == 2


def test_an_unreadable_row_is_not_a_new_driver():
    """CLAUDE.md rule 3. A name that could not be read is not a name."""
    roster = Roster()
    assert roster.see(None) is None
    assert len(roster) == 0


def test_a_cluster_that_converges_onto_another_is_folded_into_it():
    """Founding order, not similarity, is what splits one driver in two.

    On the Spa replay CruisingChaos came back as two clusters 0.406 apart while
    the nearest genuinely different pair sat at 0.738.

    The drift is set up directly here rather than driven through `see`, because
    `see` assigns to the NEAREST cluster and that alone prevents most of it -
    which is the point: the merge is the backstop for what real frames did, not
    the ordinary path.
    """
    roster = Roster()
    one = roster.see(A)
    two = roster.see(C)
    assert one != two

    # More evidence arrives and moves the second cluster onto the first.
    roster._groups[two]["bits"] = NEAR_A
    roster._groups[two]["sum"] = NEAR_A.astype(float)
    roster._merge_converged(two)

    assert len(roster) == 1
    # And the id handed out before the merge still resolves to the survivor.
    assert roster.sightings(two) == roster.sightings(one) == 2


def test_two_clusters_a_person_has_named_differently_never_merge():
    """A human saying they are two drivers outranks a bitmap saying they look
    alike."""
    roster = Roster()
    one, two = roster.see(A), roster.see(C)
    roster.label(one, "Rocky")
    roster.label(two, "Beeni")
    roster._groups[two]["bits"] = NEAR_A
    roster._groups[two]["sum"] = NEAR_A.astype(float)
    roster._merge_converged(two)
    assert len(roster) == 2
    assert roster.name_of(one) == "Rocky"
    assert roster.name_of(two) == "Beeni"


def test_a_bad_read_appears_once_and_a_driver_appears_throughout():
    roster = Roster()
    real = roster.see(A)
    for _ in range(20):
        roster.see(A)
    roster.see(C)
    assert roster.drivers(min_sightings=5) == [real]
    assert len(roster.drivers(min_sightings=1)) == 2


def test_drivers_come_back_commonest_first():
    roster = Roster()
    quiet = roster.see(C)
    loud = roster.see(A)
    for _ in range(4):
        roster.see(A)
    assert roster.drivers() == [loud, quiet]


# --- carrying identity into the next race ----------------------------------

def test_a_labelled_roster_seeds_the_next_race():
    first = Roster()
    who = first.see(A)
    first.label(who, "Rocky")

    second = Roster(seed=first.exemplars())
    assert second.name_of(second.see(NEAR_A)) == "Rocky"


def test_only_labelled_clusters_are_carried_forward():
    roster = Roster()
    roster.label(roster.see(A), "Rocky")
    roster.see(C)
    assert list(roster.exemplars()) == ["Rocky"]


def test_an_unknown_id_has_no_name_rather_than_raising():
    roster = Roster()
    assert roster.name_of(None) is None
    assert roster.name_of(99) is None


def test_the_threshold_sits_between_the_two_measured_populations():
    """0.406 was one driver seen twice; 0.738 was the closest two drivers."""
    assert 0.406 < SAME_NAME_MAX_DIFF < 0.738


def test_a_sighting_counts_once_per_spacing_so_the_floor_survives_a_faster_grab():
    """Critic, 19 Sep: `MIN_SIGHTINGS` = 20 was set at a 2 s grab. At 0.5 s a
    misread cluster held for ten seconds reached it and filed a stop as
    "Car #6". Counted at most once per `SIGHTING_SPACING_S`, twenty
    sightings mean forty seconds of being there at any grab rate."""
    from pitcrew.telemetry.roster import SIGHTING_SPACING_S

    roster = Roster()
    step = SIGHTING_SPACING_S / 4                  # a 0.5 s grab
    driver = None
    for i in range(20):                            # ten seconds of frames
        driver = roster.see_frame([A], now=i * step)[0]
    assert roster.sightings(driver) == 20          # every frame still counts
    assert roster.spaced_sightings(driver) == 5    # ...but only 5 spacings
    assert roster.drivers(min_sightings=20, spaced=True) == []
    assert roster.drivers(min_sightings=20) == [driver]
    # Without a clock (the tests, an old caller), every frame counts.
    plain = Roster()
    for _ in range(3):
        plain.see(A)
    assert plain.spaced_sightings(0) == 3
