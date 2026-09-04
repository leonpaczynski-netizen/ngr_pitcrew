"""Reading a time off the HUD, and refusing a box that has none.

Validated against the fastest-lap banner, whose value is known: white on
purple, `2:13.484`, read back as 133.484 exactly. That banner is also the
reason there is no second digit bank - the fuel bank built on the pit columns
reads this font at 0.81 to 0.90 against a floor of 0.80.
"""
from __future__ import annotations

import numpy as np
import pytest

from pitcrew.telemetry.hud_digits import _bank
from pitcrew.telemetry.hud_time import read_gap, read_seconds, tokens

INK = (240, 244, 246)
DARK = (18, 14, 26)


def _glyph(char, scale=2):
    cell, templates = _bank()
    grid = np.asarray(templates[char] > 0.5)
    from PIL import Image
    return np.asarray(
        Image.fromarray((grid * 255).astype("uint8")).resize(
            (cell[0] * scale, cell[1] * scale), Image.NEAREST)) > 127


def a_time(text, scale=2, gap=3):
    """A time rendered from the REAL digit bank, plus drawn punctuation.

    Not a stand-in: the whole point is that these glyphs are the ones the
    reader will meet, at the proportions it will meet them.
    """
    tall = 14 * scale
    pieces = []
    for char in text:
        if char == ":":
            block = np.zeros((tall, 2 * scale), dtype=bool)
            block[int(tall * 0.25):int(tall * 0.35), :] = True
            block[int(tall * 0.65):int(tall * 0.75), :] = True
            pieces.append(block)
        elif char == ".":
            # Three pixels square at scale 1, which is what the real banner
            # draws - see `test_the_full_stop_is_only_three_pixels`.
            block = np.zeros((tall, 3 * scale), dtype=bool)
            block[tall - 3 * scale:, :] = True
            pieces.append(block)
        else:
            pieces.append(_glyph(char, scale))
    wide = sum(p.shape[1] + gap for p in pieces) + gap
    canvas = np.zeros((tall, wide), dtype=bool)
    x = gap
    for piece in pieces:
        canvas[:piece.shape[0], x:x + piece.shape[1]] = piece
        x += piece.shape[1] + gap
    patch = np.zeros((tall + 8, wide + 8, 3), dtype=int)
    patch[:] = DARK
    patch[4:4 + tall, 4:4 + wide][canvas] = INK
    return patch


def dashes(scale=2):
    """`--:--.---`, which is what GT7 draws in a box with no value."""
    tall = 14 * scale
    patch = np.zeros((tall + 8, 120, 3), dtype=int)
    patch[:] = DARK
    x = 6
    for char in "--:--.---":
        if char == "-":
            patch[4 + tall // 2:4 + tall // 2 + 2 * scale, x:x + 5 * scale] = INK
            x += 5 * scale + 3
        else:
            patch[4 + int(tall * 0.3):4 + int(tall * 0.7), x:x + 2 * scale] = INK
            x += 2 * scale + 3
    return patch


# --- what it reads ---------------------------------------------------------

def test_a_lap_time_reads_back_in_seconds():
    assert read_seconds(a_time("2:13.484")) == pytest.approx(133.484)


def test_the_full_stop_is_only_three_pixels_and_must_survive():
    """Measured on the real banner: the stop is 3 x 3 px. A minimum-run floor
    of 5 - safe for a fuel figure, which is all digits - threw the decimal
    point away and turned a known 133.484 into a refusal. The synthetic
    fixture did not catch it because it renders the stop at six pixels, so
    this test uses the real proportions."""
    patch = a_time("2:13.484", scale=1)
    assert read_seconds(patch) == pytest.approx(133.484)


def test_a_clipped_box_is_refused_rather_than_read_as_a_shorter_time():
    """Sweeping a 1:23.456 across a too-narrow band, eleven offsets of 121
    returned a well-formed WRONG answer - 3.456 for a true 83.456."""
    full = a_time("1:23.456")
    for cut in (14, 22, 30):
        assert read_seconds(full[:, cut:]) is None


def test_gt7_zero_pads_the_seconds_so_a_dropped_digit_is_refused():
    """`1:2.345` is not a time GT7 draws - it is what `1:12.345` looks like
    with a digit cut off, and it parsed as 62.345 against a true 72.345."""
    assert read_seconds(a_time("1:2.345")) is None


def test_more_than_one_digit_of_minutes_is_refused():
    assert read_seconds(a_time("12:34.567")) is None


def test_a_gap_without_minutes_reads_too():
    assert read_seconds(a_time("4.512")) == pytest.approx(4.512)
    assert read_seconds(a_time("41.007")) == pytest.approx(41.007)


def test_the_punctuation_is_told_apart_by_height():
    """A colon spans most of the digit height; a full stop sits on the
    baseline. Width does not separate them - the "1" is narrower than the stop
    is wide - and a first cut that used width read the 1 as a colon."""
    assert tokens(a_time("2:13.484")) == list("2:13.484")


# --- what it refuses -------------------------------------------------------

def test_a_box_of_dashes_is_no_value_rather_than_a_gap_of_zero():
    """Every gap box in every frame of available footage looked like this."""
    assert tokens(dashes()) is None
    assert read_seconds(dashes()) is None


def test_a_time_with_no_fraction_is_refused():
    assert read_seconds(a_time("213")) is None


def test_sixty_seconds_or_more_in_the_seconds_field_is_a_misread():
    assert read_seconds(a_time("61.000")) is None


def test_a_second_colon_is_refused():
    assert read_seconds(a_time("1:2:3.456")) is None


def test_rubbish_never_raises():
    assert read_seconds(None) is None
    assert read_seconds(np.zeros((4, 4), dtype=int)) is None
    assert read_seconds(np.zeros((0, 0, 3), dtype=int)) is None
    assert tokens(np.zeros((20, 40, 3), dtype=int)) is None


def test_a_plate_is_not_text():
    """A wide solid bar is a leaderboard plate, not a glyph, and a box holding
    one is not a clean time box."""
    patch = np.zeros((30, 200, 3), dtype=int)
    patch[:] = DARK
    patch[8:22, 10:190] = INK
    assert read_seconds(patch) is None


# --- the small font, on real crops -----------------------------------------
#
# The gap readouts are the same typeface at half the size, and the bank above
# scores them 0.526-0.744 against its 0.80 floor. `smallfont` reads them; what
# is tested here is the SEAM - that the guards in this module still run first,
# and that the small font arriving does not change anything the fuel bank was
# already reading. Per-glyph accuracy is `test_smallfont.py`.

def a_real_gap(name):
    import pathlib
    from PIL import Image
    where = pathlib.Path(__file__).parent / "fixtures" / name
    with Image.open(where) as image:
        return np.asarray(image.convert("RGB"))


def test_the_clipped_box_guard_runs_before_the_small_font_too():
    """It is in `tokens`, ahead of the choice of bank, and that is the whole
    reason the choice is here rather than in `race/gaps`. Trim a column off a
    real gap box and its ink touches the edge; the reading must not become a
    shorter, well-formed, wrong one."""
    full = a_real_gap("gap-plus-27.712.png")
    assert read_seconds(full) == pytest.approx(27.712)
    for cut in (7, 9, 11, 13):
        assert read_seconds(full[:, cut:]) is None, cut


def test_the_sign_comes_back_as_a_sign_and_not_as_punctuation():
    """The `+` is shorter than a digit, so `DIGIT_MIN_HEIGHT` classified it as
    a `:` or a `.` and corrupted the token stream before parsing began."""
    assert tokens(a_real_gap("gap-minus-10.839.png"))[0] == "-"
    assert read_seconds(a_real_gap("gap-minus-10.839.png")) == pytest.approx(
        10.839), "the magnitude, because a gap is a distance"


def test_a_gap_needs_its_sign_and_a_lap_time_does_not():
    """`read_gap` requires one because a gap field is right-aligned and losing
    the sign means possibly losing a leading digit with it. `read_seconds` does
    not, because the fastest-lap banner has never carried one."""
    assert read_gap(a_real_gap("gap-plus-0.435.png")) == ("+",
                                                          pytest.approx(0.435))
    assert read_gap(a_time("2:13.484")) is None
    assert read_seconds(a_time("2:13.484")) == pytest.approx(133.484)
