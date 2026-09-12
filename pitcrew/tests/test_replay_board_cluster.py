"""Grouping a driver's name bitmap across a replay, without reading it.

`tools/read_replay_board.py` identifies rivals by clustering the name strips
rather than transcribing them - exact where OCR would be probabilistic, and the
operator labels each cluster once. The failure that matters is a SPLIT: one
driver arriving as two clusters invents a rival and is invisible, where a merge
shows on the sheet the moment it is looked at.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def board():
    spec = importlib.util.spec_from_file_location(
        "read_replay_board", ROOT / "tools" / "read_replay_board.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["read_replay_board"] = module
    try:
        spec.loader.exec_module(module)
    except SystemExit:          # the tool calls main() under __main__ only
        pass
    return module


def a_name(seed: int, shape=(16, 64), noise: float = 0.0):
    rng = np.random.default_rng(seed)
    bits = rng.random(shape) > 0.6
    if noise:
        flip = rng.random(shape) < noise
        bits = bits ^ flip
    return bits


def test_the_same_name_seen_twice_is_one_cluster(board):
    """The Spa 112 defect: PUNISHED came back as cluster 0 with 591 sightings
    and cluster 9 with one, 0.205 apart against a threshold of 0.18."""
    a = a_name(1)
    b = a_name(1, noise=0.20)          # a little further apart than 0.205
    groups = board.cluster([("first", a), ("second", b)])
    assert len(groups) == 1
    assert len(groups[0]["seen"]) == 2


def test_two_different_names_stay_apart(board):
    """Across the Spa roster the nearest different pair was 0.289."""
    groups = board.cluster([("a", a_name(1)), ("b", a_name(2))])
    assert len(groups) == 2


def test_the_threshold_stays_below_the_nearest_different_pair_measured(board):
    """Spa 112: same driver 0.205, nearest different pair 0.289. Sardegna 159
    narrowed that to 0.244 and 0.283 — 0.039 apart in total.

    The binding constraint is the UPPER one. A merge puts one driver's name on
    another's car and there is nothing left to notice it by; a split is now
    cheap, because the operator is handed a readable crop and gives both
    clusters the same label.
    """
    assert board.SAME_NAME_MAX_DIFF < 0.283, (
        "above the nearest different pair measured, two real drivers merge")
    assert board.SAME_NAME_MAX_DIFF > 0.205


def test_a_bitmap_joins_its_NEAREST_cluster_not_the_first_one(board):
    """The old loop took whichever group was created first, so a strip close
    to one name and closer to another joined by order of appearance."""
    far = a_name(3)
    near = a_name(4)
    almost = a_name(4, noise=0.03)     # unmistakably the second name
    groups = board.cluster([("far", far), ("near", near), ("x", almost)])
    assert len(groups) == 2
    home = next(g for g in groups if len(g["seen"]) == 2)
    assert {k for k, in [(k,) for k in home["seen"]]} == {"near", "x"}


def test_the_exemplar_averages_rather_than_keeping_the_first_sample(board):
    """A cluster founded on an atypical crop compared everything against its
    worst member for the rest of the race."""
    base = a_name(5)
    groups = board.cluster([("a", base),
                            ("b", a_name(5, noise=0.05)),
                            ("c", a_name(5, noise=0.05))])
    assert len(groups) == 1
    assert "sum" in groups[0], "the running total must be carried"
    assert groups[0]["sum"].sum() == pytest.approx(
        sum(b.sum() for b in (base, a_name(5, noise=0.05),
                              a_name(5, noise=0.05))))


def test_clusters_come_back_most_seen_first(board):
    seen = [("a", a_name(6)), ("b", a_name(7)), ("c", a_name(7))]
    groups = board.cluster(seen)
    assert [len(g["seen"]) for g in groups] == sorted(
        [len(g["seen"]) for g in groups], reverse=True)


def test_nothing_at_all_clusters_to_nothing(board):
    assert board.cluster([]) == []


def test_clustering_does_not_depend_on_the_order_frames_arrived(board):
    """One streaming pass compares each bitmap against an average that has
    not converged, so a cluster founded early on an atypical crop is never
    re-examined — nothing re-compares two groups once both exist.

    Sardegna 159 ended with `J.Jonas` as two clusters whose final exemplars
    were 0.244 apart, inside the threshold: by the end the evidence said one
    driver and the answer still said two.
    """
    numpy = pytest.importorskip("numpy")
    # Distances built exactly rather than sampled, so the split is forced
    # rather than hoped for. Flat `true` is the name as it settles; `first`
    # and `odd` are two early crops of it.
    true = numpy.zeros((16, 64), dtype=bool)
    first = true.copy()
    first.reshape(-1)[:123] = True                     # 0.120 from `true`
    odd = true.copy()
    odd.reshape(-1)[123:328] = True                    # 0.200 from `true`
    assert (first != odd).mean() > board.SAME_NAME_MAX_DIFF, (
        "the two early crops must be far enough apart to split")
    assert (true != odd).mean() < board.SAME_NAME_MAX_DIFF, (
        "...and the settled exemplars close enough to belong together")

    seen = [("first", first), ("odd", odd)] + [(f"t{i}", true)
                                               for i in range(6)]
    groups = board.cluster(seen)
    assert len(groups) == 1, (
        "the same driver came back as two clusters: `odd` arrived while the "
        "running average was still `first`, and nothing re-compared them "
        "once both groups existed")
    assert len(groups[0]["seen"]) == 8


def test_two_real_drivers_are_not_merged_by_that_pass(board):
    """The merge uses the same threshold, so it can only join what the
    threshold already calls one name. Jonas and Graebs measured 0.283."""
    groups = board.cluster([("a", a_name(12)), ("b", a_name(13))])
    assert len(groups) == 2


# ------------------------------------------- what the operator is handed to read

def test_the_name_read_keeps_the_native_crop_beside_the_normalised_bits(board):
    """The 64x16 exemplar is the clustering's working copy, not a picture.

    A name column is 142x24 on the canvas. Squashed to 64x16 the strokes that
    separate one driver from another are gone, so a roster labelled off the
    exemplar is a guess at a driver's name - the one thing every other step of
    this tool refuses to do.
    """
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    # Bright strokes on a dark translucent panel - upright stems with a
    # crossbar, which is what the fill band is measured against. A solid block
    # is NOT a name and is rejected; see the test below.
    pixels = numpy.zeros((300, 400, 3), dtype=numpy.uint8) + 40
    for x in range(110, 230, 8):
        pixels[100:118, x:x + 2] = 230
    pixels[107:109, 110:230] = 230
    read = board.name_bitmap(pixels, 109, own=False)
    assert read is not None
    bits, crop = read
    assert bits.shape == board.NAME_SHAPE[::-1], "the bits stay normalised"
    assert crop.shape[0] > bits.shape[0], (
        "the crop handed to the operator must be taller than the exemplar - "
        "it is the one they read the name off")


def test_the_readable_png_is_bigger_than_the_exemplar_png(board, tmp_path):
    """Nearest-neighbour only: no interpolation may invent a stroke."""
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    from PIL import Image
    crop = numpy.zeros((24, 142), dtype=bool)
    crop[6:18, 10:120] = True
    out = tmp_path / "raw.png"
    board._legible([crop, crop], out)
    assert out.exists()
    width, height = Image.open(out).size
    assert width == 142 * board.RAW_SCALE
    # Two samples stacked, with the gap between them.
    assert height == (24 * 2 + 2) * board.RAW_SCALE
    assert width > board.NAME_SHAPE[0] * 4, (
        "the readable render must beat the 4x exemplar the tool used to hand "
        "over as the thing to look at")


def _board_frame(numpy, board, rows, own_y, banner_y=None):
    """A canvas the real `flag_rows` finds rows in.

    Each row gets a saturated blue flag in the flag column. His row is a white
    panel; everyone else is a dark panel with bright strokes for a name.
    """
    pixels = numpy.zeros((800, 400, 3), dtype=numpy.uint8) + 25
    for y in list(rows) + ([banner_y] if banner_y else []):
        pixels[y - 10:y + 10, board.FLAG_X[0]:board.FLAG_X[1]] = (20, 40, 200)
        if y == own_y:
            pixels[y - 12:y + 12, board.NAME_X[0]:board.NAME_X[1]] = 210
            continue
        pixels[y - 12:y + 12, board.NAME_X[0]:board.NAME_X[1]] = 40
        for x in range(board.NAME_X[0] + 4, board.NAME_X[0] + 90, 7):
            pixels[y - 8:y + 8, x:x + 2] = 235
    return pixels


def test_the_reading_path_never_returns_the_banner(board):
    """The wiring, not the pieces.

    Every guard here is worthless if the reading loop does not call it, and
    while that loop lived inside `main` nothing could check that it did —
    reverting the one line that prunes the rows passed the whole suite.
    """
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    rows, banner = [197, 265, 304], 592
    # **He must be LAST on the board**, because that is the only arrangement
    # in which the banner is the next row down. Putting him at the top proves
    # nothing: the banner is never adjacent there, and the test passes just as
    # well with the pruning ripped out.
    pixels = _board_frame(numpy, board, rows, own_y=304, banner_y=banner)
    assert banner in board.flag_rows(pixels), (
        "the fixture must actually put a flag on the banner, or this test "
        "proves nothing")
    found = board.read_frame(pixels)
    assert found is not None, "his white row should have been found"
    assert all(y != banner for _side, y, _bits, _crop in found), (
        "the fastest-lap banner was read as the car behind the last driver")
    assert [y for _s, y, _b, _c in found] == [265], (
        "last on the board: the car ahead, and nobody behind")


def test_a_close_banner_is_refused_too(board):
    """The step rule does not catch this one and cannot.

    `MAX_ROW_STEP` was measured on a three-car board, where the banner sits
    259-291 px below the last row because nothing is between them. On a FULL
    board — Daytona session 142, rows at 196/235/276/316/356/423/489/529 — the
    banner is at 589, sixty pixels down, inside the range a gap readout
    already occupies. No threshold separates them. What holds is that it is
    the last thing on the board wearing a flag.
    """
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    rows, banner = [196, 235, 276, 316, 356, 423, 489, 529], 589
    # He is LAST of the real drivers, so the banner is the next row down.
    pixels = _board_frame(numpy, board, rows, own_y=529, banner_y=banner)
    assert banner - rows[-1] < board.MAX_ROW_STEP, (
        "the fixture must reproduce a banner the step rule lets through")
    found = board.read_frame(pixels)
    assert found is not None
    assert all(y != banner for _s, y, _b, _c in found), (
        "the fastest-lap banner was read as the car behind the last driver")
    assert [s for s, _y, _b, _c in found] == ["ahead"]


def test_scenery_far_above_the_board_is_not_the_car_ahead(board):
    """The bottom-flag guard covers the banner, which is always below. It
    cannot cover the other direction, and the other direction is measured:
    session 160 frame at 300 s found flags at [163, 424, 592] — his row at
    424, the fastest-lap banner at 592, and SKY at 163, two hundred and
    sixty-one pixels above him. Unpruned, that sky is the car ahead.
    """
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    pixels = _board_frame(numpy, board, [424, 464], own_y=424, banner_y=163)
    assert 163 in board.flag_rows(pixels)
    found = board.read_frame(pixels)
    assert found is not None
    assert all(y != 163 for _s, y, _b, _c in found), (
        "scenery above the board was read as the car ahead")


def test_the_reading_path_finds_both_neighbours(board):
    """And it must not be so strict that it names nobody."""
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    rows = [197, 265, 304]
    pixels = _board_frame(numpy, board, rows, own_y=265, banner_y=592)
    found = board.read_frame(pixels)
    assert sorted(y for _s, y, _b, _c in found) == [197, 304]
    assert sorted(s for s, _y, _b, _c in found) == ["ahead", "behind"]


def test_the_roster_names_the_readable_png_and_that_file_exists(
        board, tmp_path, monkeypatch):
    """`read_this` must name a file that is actually written, and that file
    must carry the NATIVE crop — not the exemplar under another name."""
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    from PIL import Image
    pixels = _board_frame(numpy, board, [197, 265, 304], own_y=197)
    found = board.read_frame(pixels)
    _side, _y, bits, crop = found[0]
    out = tmp_path / "name-1-0-raw.png"
    board._legible([crop], out)
    assert out.exists(), "no readable PNG was written"
    width, height = Image.open(out).size
    assert (width, height) == (crop.shape[1] * board.RAW_SCALE,
                               crop.shape[0] * board.RAW_SCALE)
    assert height > bits.shape[0] * 4, (
        "the readable render must beat the 4x exemplar the tool used to hand "
        "over as the thing to look at")


def test_a_row_with_no_ink_is_still_no_name(board):
    """The second return value must not turn an empty row into a reading."""
    numpy = pytest.importorskip("numpy")
    pixels = numpy.zeros((300, 400, 3), dtype=numpy.uint8) + 40
    assert board.name_bitmap(pixels, 109, own=False) is None


def test_legible_writes_nothing_rather_than_an_empty_image(board, tmp_path):
    out = tmp_path / "none.png"
    board._legible([], out)
    assert not out.exists()


def test_more_than_one_sighting_is_shown(board):
    """One crop can have a marshal's post through the middle of it; the point
    of showing several is that the next will not have it in the same place."""
    assert board.RAW_SAMPLES > 1
    assert board.RAW_SHORTLIST >= board.RAW_SAMPLES


def test_legible_stacks_every_crop_it_is_given(board, tmp_path):
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    from PIL import Image
    crop = numpy.zeros((24, 100), dtype=bool)
    crop[6:18, 10:80] = True
    out = tmp_path / "three.png"
    board._legible([crop, crop, crop], out)
    _width, height = Image.open(out).size
    assert height == (24 * 3 + 2 * 2) * board.RAW_SCALE, (
        "three crops and the two gaps between them")


def test_the_readable_png_is_dark_on_light(board, tmp_path):
    """The board draws these bright on a translucent panel; ink on paper is
    what an eye reads best at this size, and the inversion is what makes it
    that. Dropped, the operator gets white-on-black again."""
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    from PIL import Image
    crop = numpy.zeros((24, 100), dtype=bool)
    crop[6:18, 10:40] = True                      # a minority of ink
    out = tmp_path / "polarity.png"
    board._legible([crop], out)
    pixels = numpy.asarray(Image.open(out).convert("L"))
    assert pixels.mean() > 127, "the ground must be light and the strokes dark"


# ------------------------------------- a flag is not a place in the running order

def _rows_with_a_banner(numpy, board, order, banner_y):
    """A canvas whose brightest row is one of the board's."""
    pixels = numpy.zeros((800, 400, 3), dtype=numpy.uint8) + 30
    for i, y in enumerate(order):
        value = 200 if i == 0 else 90        # his row is the white-backed one
        pixels[y - 13:y + 13, board.NAME_X[0]:board.NAME_X[1]] = value
    pixels[banner_y - 13:banner_y + 13,
           board.NAME_X[0]:board.NAME_X[1]] = 20
    return pixels


def test_the_fastest_lap_banner_is_not_the_car_behind_the_last_one(board):
    """The Sardegna rehearsal: a three-car race in which the tool found a
    fourth driver 27 times, and the name it read off the banner was his own.

    The banner carries a real flag and a real name, so nothing downstream can
    tell that the car it named was never in the order.
    """
    numpy = pytest.importorskip("numpy")
    order = [197, 265, 304]                  # measured, Sardegna session 159
    banner = 592                             # ...and its FL banner
    pixels = _rows_with_a_banner(numpy, board, order, banner)
    kept = board.board_rows(pixels, order + [banner])
    assert kept == order, "the banner is not a row of the running order"


def test_the_board_keeps_the_run_holding_his_own_row(board):
    """Not the topmost run - the one his white-backed row is in."""
    numpy = pytest.importorskip("numpy")
    pixels = numpy.zeros((800, 400, 3), dtype=numpy.uint8) + 30
    # Something bright and flag-shaped above the board, then the board.
    pixels[160 - 13:160 + 13, board.NAME_X[0]:board.NAME_X[1]] = 60
    for y in (420, 460, 500):
        pixels[y - 13:y + 13, board.NAME_X[0]:board.NAME_X[1]] = 90
    pixels[420 - 13:420 + 13, board.NAME_X[0]:board.NAME_X[1]] = 200
    kept = board.board_rows(pixels, [160, 420, 460, 500])
    assert kept == [420, 460, 500]


def test_a_gap_row_step_still_counts_as_one_board(board):
    """67-72 px is a gap row, not another panel. Splitting there would cut the
    board in half and lose the cars below the split."""
    numpy = pytest.importorskip("numpy")
    order = [197, 265, 304, 371]
    pixels = _rows_with_a_banner(numpy, board, order, 700)
    assert board.board_rows(pixels, order) == order


def test_a_lone_bright_panel_is_not_a_running_order(board):
    """If the banner is the brightest thing wearing a flag — a white wall
    behind it — the run holding it is one row long. The frame must be counted
    as one his row could not be told apart, not treated as a board of one."""
    numpy = pytest.importorskip("numpy")
    pixels = numpy.zeros((800, 400, 3), dtype=numpy.uint8) + 30
    for y in (197, 265, 304):
        pixels[y - 13:y + 13, board.NAME_X[0]:board.NAME_X[1]] = 90
    pixels[592 - 13:592 + 13, board.NAME_X[0]:board.NAME_X[1]] = 250
    kept = board.board_rows(pixels, [197, 265, 304, 592])
    assert kept == [], "a one-row run is not a board"
    assert board.own_row(pixels, kept) is None


def test_no_rows_and_one_row_are_handled(board):
    numpy = pytest.importorskip("numpy")
    pixels = numpy.zeros((800, 400, 3), dtype=numpy.uint8) + 30
    assert board.board_rows(pixels, []) == []
    assert board.board_rows(pixels, [200]) == []


def test_the_step_threshold_clears_a_doubled_gap_row(board):
    """Within the board 37-72 px; down to the banner 259-291.

    The lower bound is NOT the 72 px gap-row step. GT7 draws a gap readout
    above AND below his own row, so if his own flag is missed — and his is the
    likeliest to be missed, his row being washed toward white — the step from
    the row above him to the row below is 68 + 68 = 136. A threshold under
    that splits the board through his row and reads the far side as a
    neighbour.
    """
    assert board.MAX_ROW_STEP > 136, "a doubled gap row splits the board"
    assert board.MAX_ROW_STEP < 259, "the banner must stay out"


def test_his_row_must_outshine_every_flag_in_the_picture(board):
    """Not merely the ones sharing its panel.

    Choosing the run first and asking which row is his second made this
    margin strictly easier to pass: pruning only removes rows, so the
    brightest survivor beats a weaker field than the brightest of everything
    did. The anchor is therefore chosen before the pruning.
    """
    numpy = pytest.importorskip("numpy")
    pixels = numpy.zeros((800, 400, 3), dtype=numpy.uint8) + 25
    # Two panels, each with a bright row: neither out-shines the other, so
    # neither is his and the frame must be refused outright.
    for y, value in ((197, 200), (265, 90), (304, 95), (592, 190)):
        pixels[y - 13:y + 13, board.NAME_X[0]:board.NAME_X[1]] = value
    assert board.board_rows(pixels, [197, 265, 304, 592]) == [], (
        "two rival bright rows means his own cannot be told apart")


def test_the_anchor_must_look_like_a_white_backed_row(board):
    """The brightest thing present is not automatically his row — a dark
    banner alone in a dark frame wins a contest it should not have entered."""
    numpy = pytest.importorskip("numpy")
    pixels = numpy.zeros((800, 400, 3), dtype=numpy.uint8) + 10
    for y, value in ((197, 20), (265, 22), (592, 60)):
        pixels[y - 13:y + 13, board.NAME_X[0]:board.NAME_X[1]] = value
    assert board.board_rows(pixels, [197, 265, 592]) == []


def test_his_own_white_row_read_as_a_rival_is_not_a_name(board):
    """Reading a WHITE row with the rival polarity makes the BACKGROUND the
    ink - a solid block, which clusters with every other solid block and
    arrives as a driver nobody can identify."""
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    pixels = numpy.zeros((300, 400, 3), dtype=numpy.uint8) + 30
    # His row: a filled white panel, no dark glyphs worth the name.
    pixels[97:121, board.NAME_X[0]:board.NAME_X[1]] = 230
    assert board.name_bitmap(pixels, 109, own=False) is None


def test_the_fill_band_is_wide_of_every_name_measured(board):
    """A rival's name filled 0.126-0.422 of its box; his own row read wrong
    filled 0.906+; scenery 0.018, and 0.595 upward. The band must clear the
    names in both directions and the scenery in one."""
    low, high = board.NAME_FILL
    assert low < 0.126, "a real name must not be rejected as too sparse"
    assert high > 0.422, "a real name must not be rejected as too dense"
    # **The binding bound.** The same sweep measured scenery from 0.595 up. A
    # ceiling at or above that admits the exact thing this constant was added
    # to reject, which is where it was first set — five thousandths clear.
    assert high < 0.595, "the ceiling must clear the scenery floor measured"
