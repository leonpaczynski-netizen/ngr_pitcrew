"""Finding the leaderboard: the guards, each of which was earned on a real frame.

Every test here corresponds to a version that returned a confident wrong answer
on a live capture during the 2 Sep session.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest
from PIL import Image

from pitcrew.telemetry.board import (
    ASPECT,
    Board,
    _ladder,
    _own_row_by_plate,
    find,
    flag_ladder,
    gap_lines,
    own_row,
)

W, H = 1920, 1080
DARK = (24, 30, 38)
PLATE = (36, 46, 60)
WHITE = (232, 236, 238)
RED = (196, 40, 44)
SKY = (140, 180, 225)


def a_frame(*, own_at=(40, 400), plate=(216, 38), sky=True,
            ahead=True, behind=True, leader=True, decoy=None):
    """A synthetic board: dark rows, one white row, gap bars either side."""
    frame = np.zeros((H, W, 3), dtype=int)
    frame[:] = DARK
    if sky:
        # The thing that broke first-to-last column spanning.
        frame[:, int(W * 0.55):] = SKY
    x, y = own_at
    pw, ph = plate
    for i in range(-5, 5):
        if i == 0:
            continue
        top = y + i * (ph + 4)
        if 0 <= top < H - ph:
            frame[top:top + ph, x:x + pw] = PLATE
    frame[y:y + ph, x:x + pw] = WHITE
    # The driver's name, black on the white plate — this is what breaks the
    # bright run and is why runs are merged. Scaled with the plate: an
    # unscaled name on a half-size plate leaves no run to find, which is a
    # fixture artefact and not a property of the locator.
    name_h = max(4, int(ph * 0.42))
    name_x, name_w = x + int(pw * 0.09), int(pw * 0.32)
    frame[y + (ph - name_h) // 2:y + (ph + name_h) // 2,
          name_x:name_x + name_w] = DARK
    if leader:
        frame[y:y + ph, x + pw + 4:x + pw + 74] = RED
    for on, top in ((ahead, y - ph - 4), (behind, y + ph + 4)):
        if not on:
            continue
        frame[top:top + ph, x:x + pw] = (18, 22, 28)
        ink_h = max(3, int(ph * 0.32))
        frame[top + (ph - ink_h) // 2:top + (ph + ink_h) // 2,
              x + int(pw * 0.65):x + int(pw * 0.92)] = WHITE
    if decoy is not None:
        dx, dy, dw, dh = decoy
        frame[dy:dy + dh, dx:dx + dw] = WHITE
    return frame


def test_the_driver_s_own_row_is_found_by_its_plate():
    row = own_row(a_frame())
    assert row is not None
    x0, y0, x1, y1 = row
    assert abs(x0 - 40) <= 3 and abs(y0 - 400) <= 3
    assert abs((x1 - x0 + 1) - 216) <= 6


def test_it_is_found_wherever_the_board_sits():
    """The first version searched the left 23% of the frame. The moment the
    board was composited elsewhere it found nothing."""
    for at in ((40, 400), (900, 300), (1200, 600)):
        assert own_row(a_frame(own_at=at, sky=False)) is not None, at


def test_bright_sky_beside_the_plate_does_not_inflate_its_width():
    """Spanning the first qualifying column to the last measured 1780 px on a
    real frame, and the real plate failed its own size guard."""
    row = own_row(a_frame(sky=True))
    assert row is not None
    assert (row[2] - row[0] + 1) < 400


def test_a_wide_bright_band_is_not_mistaken_for_a_row():
    """A live frame returned an 899x46 band across POSITION and LAP. A row is
    about six times wider than tall; that band was 19.5."""
    frame = a_frame(decoy=(88, 75, 899, 46))
    row = own_row(frame)
    assert row is not None
    assert row[1] != 75, "the wide band must not win"
    width, height = row[2] - row[0] + 1, row[3] - row[1] + 1
    assert ASPECT[0] <= width / height <= ASPECT[1]


def test_the_name_printed_on_the_plate_does_not_split_it():
    """Black text on the white plate breaks the bright run; a strict version
    returned a median height of 13 px against a row pitch of 34."""
    row = own_row(a_frame())
    assert (row[3] - row[1] + 1) >= 30


# ------------------------------------------------------------------- gaps

def test_all_three_gaps_are_located():
    board = find(a_frame())
    assert isinstance(board, Board)
    assert board.ahead is not None
    assert board.behind is not None
    assert board.leader is not None
    assert board.leader[0] > board.row[2], "the red box sits after the plate"


def test_the_leader_gap_is_absent_when_he_is_leading():
    """There is no box then, and inventing one writes down a gap of zero for a
    car that has none."""
    board = find(a_frame(leader=False))
    assert board is not None
    assert board.leader is None


def test_a_missing_gap_line_is_none_not_a_guess():
    board = find(a_frame(ahead=False))
    assert board is not None
    assert board.ahead is None
    assert board.behind is not None


def test_no_row_means_no_board_at_all():
    """Without the row there is nothing to anchor the gaps to, and a gap read
    from an unanchored guess is worse than no gap."""
    blank = np.full((H, W, 3), DARK, dtype=int)
    assert own_row(blank) is None
    assert find(blank) is None


def test_it_never_raises_on_rubbish():
    assert own_row(None) is None
    assert own_row(np.zeros((10, 10, 3), dtype=int)) is None
    assert find(np.zeros((5, 5, 3), dtype=int)) is None


def test_gap_lines_survive_a_row_at_the_top_of_the_frame():
    frame = a_frame(own_at=(40, 8), sky=False)
    row = own_row(frame)
    if row is not None:
        ahead, behind = gap_lines(frame, row)
        assert ahead is None or ahead[1] >= 0


@pytest.mark.parametrize("scale", [0.5, 1.0, 1.5])
def test_the_guards_are_shape_based_so_they_survive_magnification(scale):
    """The board may be composited at any size. A bound expressed as a
    fraction of the frame is wrong the moment it is scaled."""
    pw, ph = int(216 * scale), max(10, int(38 * scale))
    row = own_row(a_frame(plate=(pw, ph), sky=False))
    assert row is not None
    width, height = row[2] - row[0] + 1, row[3] - row[1] + 1
    assert ASPECT[0] <= width / height <= ASPECT[1]


# --- the flag ladder -------------------------------------------------------
#
# The plate alone cannot tell a leaderboard from a bright sky. Measured over a
# whole race it found a board on 62 frames of 162 and about half were wrong,
# returning boxes at (1680, 0) and (0, 1047) as confidently as real ones. Every
# test below corresponds to a version that did exactly that.

FLAG_BLUE = (30, 60, 190)
FLAG_RED = (190, 40, 50)


def a_board_with_flags(*, pitch=40, rows=8, own=4, flag_x=256, flag_w=26,
                       sky=True, gap_lines_drawn=True):
    """A board with a country flag on every row, sky above it, scenery below.

    The scenery is the thing that mattered: fence palings make a perfectly
    regular ladder of flag-coloured marks at a 7 px pitch.
    """
    frame = np.zeros((H, W, 3), dtype=int)
    frame[:] = DARK
    if sky:
        frame[:260, :] = SKY
    top = 190
    ys = []
    for index in range(rows):
        y = top + index * pitch
        # The gap readouts either side of the driver's own row push the rest
        # down. Those two steps are pitch PLUS a constant and are equal to each
        # other, because it is the same readout drawn twice.
        if gap_lines_drawn:
            y += 28 * (1 if index == own else (2 if index > own else 0))
        ys.append(y)
        frame[y - 9:y + 9, flag_x:flag_x + flag_w] = FLAG_BLUE
        frame[y - 9:y - 4, flag_x:flag_x + flag_w] = FLAG_RED
        plate = WHITE if index == own else PLATE
        frame[y - 16:y + 16, 40:flag_x - 4] = plate
        if index == own:
            frame[y - 5:y + 5, 90:200] = DARK      # his name, dark on white
    # Fence palings below: flag-coloured, regular, and one pixel tall.
    for y in range(700, 900, 7):
        frame[y:y + 1, 1684:1684 + 14] = FLAG_RED
    return frame, ys


def test_the_ladder_keeps_a_constant_pitch():
    assert _ladder([100, 140, 180, 220], min_pitch=20) == [100, 140, 180, 220]


def test_the_wide_steps_are_pitch_plus_a_constant_not_a_doubled_pitch():
    """GT7 inserts a gap readout above and below the driver's own row. At 1440p
    the pitch is 40 and those two steps are 68 - modelling them as 2x40 threw
    away every row past the driver."""
    ys = [192, 232, 272, 340, 408, 448, 488]
    assert _ladder(ys, min_pitch=20) == ys


def test_the_two_wide_steps_must_agree_with_each_other():
    # One wide step of 68 and one of 100 is not a leaderboard.
    ys = [192, 232, 272, 340, 440, 480]
    assert len(_ladder(ys, min_pitch=20)) < len(ys)


def test_a_pitch_finer_than_a_flag_is_wide_is_refused():
    """Rows cannot be closer together than a flag is wide. Fence palings make a
    perfectly regular ladder at a 7 px pitch."""
    assert _ladder([700, 707, 714, 721], min_pitch=30) == []


def test_a_one_pixel_sliver_is_not_a_flag():
    """The guard that actually rejects palings is their SHAPE, not their pitch:
    any coarse ladder can be found inside a fine one. On a measured frame a
    stack of one-pixel marks at x 1684 in the trees beat the real board."""
    frame, _ = a_board_with_flags()
    found = flag_ladder(frame)
    assert found is not None
    assert found[0] < 1000


def test_the_flag_column_is_found_through_sky():
    frame, ys = a_board_with_flags()
    found = flag_ladder(frame)
    assert found is not None
    x0, x1, rungs = found
    assert abs(x0 - 256) <= 2
    assert len(rungs) >= 5


def test_sky_no_longer_defeats_the_locator():
    """The measured failure: sky is bright AND unsaturated, so it passes the
    plate test and merges every row into one blob."""
    frame, ys = a_board_with_flags(sky=True)
    assert own_row(frame) is not None


def test_the_own_row_is_the_bright_plate_on_the_ladder():
    frame, ys = a_board_with_flags(own=4)
    box = own_row(frame)
    assert box is not None
    centre = (box[1] + box[3]) // 2
    assert min(abs(centre - y) for y in ys) <= 6
    # It ends where the flag begins, not somewhere across the screen.
    assert box[2] < 256


def test_a_board_drawn_without_flags_still_falls_back_to_the_plate():
    plain = a_frame(sky=False)
    assert flag_ladder(plain) is None
    assert own_row(plain) == _own_row_by_plate(plain)


def test_scenery_below_the_board_is_not_returned_as_the_board():
    frame, _ = a_board_with_flags()
    box = own_row(frame)
    assert box is not None
    assert box[1] < 700          # the palings are at y 700+


# --- real frames -----------------------------------------------------------
#
# **Everything above this line is synthetic, and that is why all twenty of
# those tests were green while the locator found a board on 5 frames of 73 in
# the race it was built for.** The fixtures draw a flag as a solid block of two
# colours at one width. GT7 draws Japan as a red disc on white, Germany in
# three bands and Mexico in three, and it right-aligns a white-on-black gap
# readout into the same column - none of which the synthetic board has ever
# contained.
#
# These two are crops of the 4 Sep 2026 Daytona race capture
# (`2026-09-04 22-12-04.mp4`, 1920x1080) at t=600 s and t=1805 s, cut to
# 420x700 about the board. The full height was not kept, but the flags still
# sit inside the height band the locator works in, which is the only thing the
# crop could have changed. They cover two layouts that behave differently:
#
#   p13  he is 13th, mid-board, a gap readout above and below his row
#   p2   he is 2nd, so the FIRST step of the ladder is a wide one - the case
#        that set the pitch to 68 and threw away every row above him
#
# The expected values were read off the frames, not off the code.

REAL = pathlib.Path(__file__).parent / "fixtures"
# Where the flag column and the driver's own plate actually are in both crops.
REAL_FLAG_X = 244
REAL_PLATE_X0, REAL_PLATE_X1 = 39, 243
# The board is drawn at a 40 px row pitch, with a 68 px step either side of the
# driver's own row where GT7 inserts a gap readout.
REAL_PITCH, REAL_WIDE_STEP = 40, 68
# How far a rung may sit from the true row centre: a flag that is only partly
# saturated hands back an ink run that is not centred on its row. Measured at
# +-3 px on these two frames.
REAL_CENTRE_SLOP = 4
REAL_ROWS = 8
REAL_FRAMES = [("daytona-race-board-p13.png", 360),
               ("daytona-race-board-p2.png", 200)]


def a_real_frame(name):
    with Image.open(REAL / name) as image:
        return np.asarray(image.convert("RGB"))


@pytest.mark.parametrize("name,own_y", REAL_FRAMES)
def test_the_ladder_is_found_on_a_real_race_frame(name, own_y):
    found = flag_ladder(a_real_frame(name))
    assert found is not None, "the board is plainly on this frame"
    x0, x1, rungs = found
    assert abs(x0 - REAL_FLAG_X) <= 3, f"the flag column is at {REAL_FLAG_X}"
    assert x1 > x0, "and it has a width"
    assert len(rungs) == REAL_ROWS
    assert own_y in rungs, "his own row is one of the rungs"


@pytest.mark.parametrize("name,_own_y", REAL_FRAMES)
def test_the_real_pitch_is_forty_with_two_equal_wide_steps(name, _own_y):
    """Not 20, and not 40/64/69 on one column at once. The version this
    replaces knitted GT7's multi-coloured flags into blobs and read those three
    pitches off a column whose true pitch is a constant 40.

    To within `REAL_CENTRE_SLOP`, because a rung is the centre of the ink run
    and a flag that is only partly saturated - Japan's disc is 8 px of an 18 px
    flag - hands back a run that is not centred on its row. The ladder carries
    the same tolerance for the same reason.
    """
    _, _, rungs = flag_ladder(a_real_frame(name))
    steps = [b - a for a, b in zip(rungs, rungs[1:])]
    normal = [s for s in steps if abs(s - REAL_PITCH) <= REAL_CENTRE_SLOP]
    wide = [s for s in steps if abs(s - REAL_WIDE_STEP) <= REAL_CENTRE_SLOP]
    assert len(normal) + len(wide) == len(steps), steps
    assert len(wide) == 2, "one gap readout above his row and one below"
    assert abs(wide[0] - wide[1]) <= REAL_CENTRE_SLOP, "the same readout twice"


@pytest.mark.parametrize("name,own_y", REAL_FRAMES)
def test_the_own_row_is_found_on_a_real_race_frame(name, own_y):
    frame = a_real_frame(name)
    box = own_row(frame, flag_ladder(frame))
    assert box is not None
    assert abs((box[1] + box[3]) // 2 - own_y) <= 4
    # The plate, and not the plate plus whatever is bright beside the board.
    assert abs(box[0] - REAL_PLATE_X0) <= 3
    assert abs(box[2] - REAL_PLATE_X1) <= 3


@pytest.mark.parametrize("name,_own_y", REAL_FRAMES)
def test_all_three_gaps_are_framed_on_a_real_race_frame(name, _own_y):
    """He is neither leading nor last on either frame, so all three are drawn.

    Framing them is not reading them: `hud_digits` scores these 12 px glyphs at
    0.60-0.70 against its 0.80 floor and refuses every one, so `read_gaps`
    still returns None on both. The box has to be right first.
    """
    board = find(a_real_frame(name))
    assert board is not None
    assert board.ahead is not None and board.behind is not None
    assert board.leader is not None
    assert board.ahead[3] < board.row[1], "ahead sits above his row"
    assert board.behind[1] > board.row[3], "behind sits below it"
    assert board.leader[0] > board.row[2], "the red box sits after the plate"


@pytest.mark.parametrize("name,_own_y", REAL_FRAMES)
def test_the_gap_readout_is_not_cut_off_by_the_plate_s_width(name, _own_y):
    """It is right-aligned to the FLAG column, which ends 26 px past the plate.

    A band bounded by the row's own width lost the last two glyphs, and
    `hud_time` refuses a box whose ink touches an edge - so a cut box is not a
    shorter reading, it is no reading at all, ever.
    """
    board = find(a_real_frame(name))
    for box in (board.ahead, board.behind):
        assert box[2] > board.row[2], "the readout runs past the plate"
