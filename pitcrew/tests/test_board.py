"""Finding the leaderboard: the guards, each of which was earned on a real frame.

Every test here corresponds to a version that returned a confident wrong answer
on a live capture during the 2 Sep session.
"""
from __future__ import annotations

import numpy as np
import pytest

from pitcrew.telemetry.board import ASPECT, Board, find, gap_lines, own_row

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
