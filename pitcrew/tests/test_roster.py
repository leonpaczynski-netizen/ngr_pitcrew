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
    chain,
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


# --- the pitch chain -------------------------------------------------------

def test_a_constant_pitch_is_kept_whole():
    # The first step out is larger: GT7 inserts a gap readout either side of
    # the driver's own row. Every step after it is the board's true pitch.
    found = chain([192, 232, 272, 340, 408, 448, 488, 528], own_y=340,
                  height=43)
    assert found == [192, 232, 272, 340, 408, 448, 488, 528]


def test_scenery_breaks_the_chain_and_everything_past_it_is_dropped():
    """A leaderboard is a ruler; a pit lane is not."""
    found = chain([192, 232, 272, 340, 408, 448, 488, 528, 588, 618, 967],
                  own_y=340, height=43)
    assert found == [192, 232, 272, 340, 408, 448, 488, 528]


def test_a_lone_far_candidate_is_not_a_neighbouring_row():
    assert chain([340, 900], own_y=340, height=43) == [340]


def test_the_pitch_is_measured_not_assumed():
    # Half the row spacing, as a smaller HUD would give. Nothing is hard-coded
    # to 40 px, so this survives whole.
    found = chain([96, 116, 136, 170, 204, 224, 244], own_y=170, height=21)
    assert found == [96, 116, 136, 170, 204, 224, 244]


def test_no_candidates_is_no_rows():
    assert chain([], own_y=340, height=43) == []


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
