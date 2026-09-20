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


def test_a_merge_is_counted_and_said_out_loud(monkeypatch):
    """**Rule 10: log the accepts, not only the refusals.**

    `counts` carried `matched / founded / contested` and nothing for a merge,
    and no merge was ever logged - so the Bathurst race of 20 Sep 2026, which
    filed twenty-seven identities for seven cars, could not say whether the
    one path that undoes a split had run once or never. The refusals were
    printed every two minutes throughout.
    """
    import pitcrew.telemetry.roster as roster_module

    lines = []
    monkeypatch.setattr(roster_module._log, "info",
                        lambda msg, *a, **k: lines.append(msg % a if a
                                                          else msg))
    roster = Roster()
    one, two = roster.see(A), roster.see(C)
    roster.label(one, "Rocky")
    assert roster.counts["merged"] == 0
    roster._groups[two]["bits"] = NEAR_A
    roster._groups[two]["sum"] = NEAR_A.astype(float)
    roster._merge_converged(two)
    assert roster.counts["merged"] == 1
    folded = [line for line in lines if "folded into" in line]
    assert len(folded) == 1 and "Rocky" in folded[0]


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


# --- which row is ours -----------------------------------------------------
#
# **The rung is somewhere in the plate, and the midpoint is not where the
# ladder put it.** The driver's own white plate registers as flag colour over
# its whole height, so `board.flag_ladder` takes rungs out of its top and
# bottom EDGES - 365 and 396 on the frame traced in `board.CLIPPED_PLATE`,
# never one at its centre, 381. Asking whether a rung is within 8 px of the
# plate's midpoint then answers no on a correctly located plate.
#
# Measured 20 Sep 2026 over 292 frames of Bathurst and 182 of Sardegna: this
# is the half of the fix that stops a regression - repairing the box while
# this still asked about the midpoint took the own row from 82.9% to 58.9%,
# because a box grown to the plate's true extent moves its midpoint away from
# the rung the plate was found on.

W, H = 1920, 1080
DARK_ROW = (24, 30, 38)
PLATE_ROW = (36, 46, 60)
WHITE_PLATE = (232, 236, 238)
NAME_BRIGHT = (228, 230, 232)
FLAG = (30, 60, 190)
FLAG_X0, FLAG_X1 = 256, 281
PLATE_X0, PLATE_X1 = 40, 243
OWN_TOP, OWN_BOTTOM = 363, 397
# The rung the plate was found on: inside the plate, and 15 px from its
# midpoint - which `ROW_MATCH_TOL` (8) rejects.
OWN_RUNG = 365
OTHER_RUNGS = [192, 232, 272, 312, 448, 488]


def a_board_frame():
    """A leaderboard with a position digit and a name on every row."""
    frame = np.zeros((H, W, 3), dtype=int)
    frame[:] = DARK_ROW
    for y in OTHER_RUNGS:
        frame[y - 16:y + 17, PLATE_X0:PLATE_X1 + 1] = PLATE_ROW
        frame[y - 5:y + 6, 50:61] = NAME_BRIGHT          # his position digit
        frame[y - 5:y + 6, 90:201] = NAME_BRIGHT         # ...and his name
    frame[OWN_TOP:OWN_BOTTOM + 1, PLATE_X0:PLATE_X1 + 1] = WHITE_PLATE
    centre = (OWN_TOP + OWN_BOTTOM) // 2
    frame[centre - 5:centre + 6, 50:61] = DARK_ROW       # dark on his plate
    frame[centre - 5:centre + 6, 90:201] = DARK_ROW
    for y in OTHER_RUNGS + [OWN_RUNG]:
        frame[y - 9:y + 9, FLAG_X0:FLAG_X1 + 1] = FLAG
    box = (PLATE_X0, OWN_TOP, PLATE_X1, OWN_BOTTOM)
    return frame, box, (FLAG_X0, FLAG_X1, sorted(OTHER_RUNGS + [OWN_RUNG]))


def test_a_rung_inside_the_plate_is_ours_however_far_from_its_midpoint():
    from pitcrew.telemetry.roster import ROW_MATCH_TOL, read

    frame, box, ladder = a_board_frame()
    midpoint = (box[1] + box[3]) // 2
    assert abs(OWN_RUNG - midpoint) > ROW_MATCH_TOL, (
        "the rung this fixture is built around is one the old test rejected")

    rows = read(frame, box, ladder)
    ours = [row for row in rows if row.is_own]
    assert [row.y for row in ours] == [OWN_RUNG]
    assert ours[0].name is not None, (
        "and it is read as dark ink on a white plate, not bright on a dark one")


def test_the_column_vote_asks_the_same_question_as_everything_else():
    """**`name_column` kept its own version of "is this row ours", and the
    better the box got the more often it answered wrong.** Rule 13.

    `read()` computed `(board[1] + board[3]) // 2` and handed it down, and
    `name_column` tested `abs(y - own_y) <= ROW_MATCH_TOL` - the exact
    relation `is_own_row` replaced, two lines above the loop that already
    called `is_own_row`. The answer chooses between DARK glyphs on his white
    plate and BRIGHT glyphs on everyone else's dark one, so getting it wrong
    inverts the ink test for that row.

    And it gets it wrong precisely when the box is right: with the plate
    clipped the midpoint sat near the rung and the midpoint test said yes;
    with the box repaired to the plate's true extent the midpoint is the
    plate's centre while the ladder's rungs are its EDGES, so it says no.
    The bright test then lights the WHOLE white plate as one ink group and
    the row votes for the plate's left edge, x=40, instead of where his name
    starts, x=90 - and `name_x` is a consensus across all rows, so one row
    voting on a plate edge re-keys every name bitmap on the frame at once.

    Asserted on the question rather than on the vote it produces, because
    the vote is a majority: on a full board the six correct rows outvote the
    one wrong one, so the board's `name_x` is the same either way and the
    defect hides behind the majority it corrupts. What is on trial is which
    relation the row is classified by, and there is now one of those.
    """
    import pitcrew.telemetry.roster as roster_module

    frame, box, ladder = a_board_frame()
    flag_x0, flag_x1, _ = ladder
    right = max(0, flag_x0 - (flag_x1 - flag_x0 + 1))
    rungs = sorted(OTHER_RUNGS + [OWN_RUNG])

    asked: list[bool] = []
    real_ink = roster_module._ink

    def watched(strip, is_own):
        asked.append(bool(is_own))
        return real_ink(strip, is_own)

    roster_module._ink = watched
    try:
        roster_module.name_column(frame, box, rungs, right)
    finally:
        roster_module._ink = real_ink

    assert asked == [roster_module.is_own_row(box, y) for y in rungs], (
        "the column vote classifies rows by its own midpoint test, not by "
        "the one relation `read`, `is_own_row` and `PitWall._own_driver` "
        "share")
    assert asked == [False] * 4 + [True] + [False] * 2, (
        "and on this board that is his row and only his")


def test_only_one_row_of_a_frame_is_ever_ours():
    """Two rows marked ours at once is what a box grown past its own row
    would cause. Measured over 474 frames of two races: 0."""
    from pitcrew.telemetry.roster import read

    frame, box, ladder = a_board_frame()
    assert sum(row.is_own for row in read(frame, box, ladder)) == 1


def test_one_plate_is_one_row_although_the_ladder_put_two_rungs_in_it():
    """**A plate holds one row, so at most one rung of it is ours.**

    `is_own_row` is a containment test, and the whole premise of the box
    repair is that one white plate yields TWO rungs - its top and bottom
    edge. `board.flag_ladder` folds that pair before it ever leaves, but it
    refuses to fold a crowd of three (rule 3), so a plate with more than one
    rung still in it is reachable: measured 21 Sep 2026, one frame of 292 at
    Bathurst.

    Marking both is a reading the frame itself disproves - one car cannot
    hold two rows, which is the fact `Roster._together` is built on. And it
    is not harmless: `PitWall._see` takes `next(row for row in rows if
    row.is_own)` for `own_row_place`, which is insertion order, i.e.
    whichever half of the plate is higher up the screen - and
    `own_row_place` is what the car ahead and the car behind are read off.

    The rung nearest the plate's centre is the row, which is how
    `PitWall._own_driver` already settles the same tie (rule 13).
    """
    from pitcrew.telemetry.roster import read

    frame, box, ladder = a_board_frame()
    flag_x0, flag_x1, ys = ladder
    # The plate's other edge, the rung the fold upstream did not remove.
    crowded = (flag_x0, flag_x1, sorted(ys + [OWN_BOTTOM - 1]))
    rows = read(frame, box, crowded)

    ours = [row.y for row in rows if row.is_own]
    assert len(ours) == 1, f"one plate, one row - got rungs {ours}"
    assert ours == [OWN_RUNG], (
        "and it is the rung nearest the plate's centre, not the first one "
        "the board reader happened to hand over")
