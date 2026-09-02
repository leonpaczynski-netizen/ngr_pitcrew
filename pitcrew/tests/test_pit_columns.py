"""The pit columns: who has stopped, on what, with how much fuel.

Guards in this file are in the order they were earned. Each one was added
because the version without it produced a confident wrong answer on real
frames from the Spa replay of 1 Sep 2026 or on 92 Daytona frames in which
nobody had pitted.
"""
from __future__ import annotations

import numpy as np
import pytest

from pitcrew.telemetry.pit_columns import PitRow, pitted_count, read

W, H = 1920, 1080
DARK = (22, 28, 34)
DISC = (205, 42, 44)
INK = (238, 242, 244)
BOARD = (39, 400, 254, 438)          # a plausible own-row box


def a_frame(*, rows=3, pitch=40, disc_x=291, size=28, top=220,
            fuel=True, flag=False, decoy=None, skip=()):
    frame = np.zeros((H, W, 3), dtype=int)
    frame[:] = DARK
    for i in range(rows):
        if i in skip:
            continue
        y = top + i * pitch
        frame[y:y + size, disc_x:disc_x + size] = DISC
        if fuel:
            # Scaled with the disc: the reader looks for the number in a window
            # measured in disc widths, so an unscaled box falls outside it at
            # small sizes. A fixture artefact, not a property of the reader.
            gap, span = int(size * 0.7), int(size * 2.6)
            frame[y + size // 4:y + 3 * size // 4,
                  disc_x + size + gap:disc_x + size + span] = INK
        if flag:
            frame[y:y + size, 8:30] = INK
    if decoy is not None:
        for (dx, dy, dw, dh) in decoy:
            frame[dy:dy + dh, dx:dx + dw] = DISC
    return frame


def test_a_column_of_discs_with_numbers_is_read():
    rows = read(a_frame(rows=5), board=BOARD)
    assert len(rows) == 5
    assert all(isinstance(r, PitRow) for r in rows)
    assert all(r.fuel_box is not None for r in rows)


def test_nobody_pitted_means_nothing_at_all():
    """The ordinary state for the first half of a race, and not a failure."""
    blank = np.full((H, W, 3), DARK, dtype=int)
    assert read(blank, board=BOARD) == []
    assert pitted_count(blank) == 0


def test_a_disc_with_no_number_beside_it_is_not_a_pit_column():
    """The guard that finally worked. Colour, size, alignment and row pitch
    between them still let 15 pieces of scenery through on 92 frames where
    nobody had pitted; every one had no fuel box."""
    assert read(a_frame(rows=4, fuel=False), board=BOARD) == []


def test_scenery_that_is_red_and_square_but_not_on_a_pitch_is_refused():
    """Pit-crew gloves, shoes and helmets are all of these things."""
    frame = np.full((H, W, 3), DARK, dtype=int)
    for x, y in ((700, 300), (703, 361), (698, 447), (705, 502)):
        frame[y:y + 28, x:x + 28] = DISC
    assert read(frame, board=BOARD) == []


def test_a_column_outside_the_leaderboard_is_refused():
    """A disc belongs to a leaderboard row, so it sits within a couple of
    row-widths of the board's left edge. Nothing in the scene is."""
    far = a_frame(rows=4, disc_x=1500)
    assert read(far, board=BOARD) == []
    assert len(read(far, board=(1400, 400, 1615, 438))) == 4


def test_a_single_disc_is_never_a_column():
    assert read(a_frame(rows=1), board=BOARD) == []


def test_a_gap_in_the_column_is_allowed_because_a_car_may_not_have_stopped():
    """Rows are at a fixed pitch and a car with no stop leaves a hole — a
    multiple of the pitch, never a fractional offset."""
    rows = read(a_frame(rows=5, skip=(2,)), board=BOARD)
    assert len(rows) == 4


def test_the_pit_flag_is_read_only_where_the_board_bounds_the_strip():
    """Without the board there is nothing to bound the strip the flag lives
    in, and a bright sky would answer for it."""
    frame = a_frame(rows=3, flag=True)
    assert all(r.has_pitted for r in read(frame, board=BOARD))
    assert not any(r.has_pitted for r in read(frame, board=None))


def test_no_flag_means_not_pitted_rather_than_unknown():
    frame = a_frame(rows=3, flag=False)
    assert not any(r.has_pitted for r in read(frame, board=BOARD))


def test_the_rows_come_back_in_screen_order():
    rows = read(a_frame(rows=4), board=BOARD)
    assert [r.y for r in rows] == sorted(r.y for r in rows)


@pytest.mark.parametrize("scale", [0.75, 1.0, 1.4])
def test_the_geometry_is_expressed_as_fractions_so_it_scales(scale):
    """The HUD scales with the canvas; pixel constants are why the live gauge
    went silent at 1440p. Below about 0.7 the disc falls under
    `DISC_MIN_FRAC` and is refused, which is deliberate — a 16 px disc on a
    1080-row frame is not a disc anyone can read a letter out of."""
    size = int(28 * scale)
    rows = read(a_frame(rows=4, size=size, pitch=int(40 * scale)), board=BOARD)
    assert len(rows) == 4


def test_it_never_raises_on_rubbish():
    assert read(None) == []
    assert read(np.zeros((10, 10, 3), dtype=int)) == []
    assert pitted_count(np.zeros((4, 4, 3), dtype=int)) == 0
