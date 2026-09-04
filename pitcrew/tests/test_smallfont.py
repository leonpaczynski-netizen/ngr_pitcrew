"""Reading the gap font, against crops of the race it was built to read.

**Every fixture here is a real gap box** - the exact patch that
`race.gaps.read_gaps` hands the reader, cut out of `2026-09-04 22-12-04.mp4` by
`tools/gap_bank.py fixtures` and committed. There is no synthetic gap-font
fixture anywhere in this file and there must not be one: `test_board.py`'s
predecessor passed twenty tests against frames it drew itself while the live
pit wall read nothing at all for a fortnight, and a bank rendered from its own
templates cannot fail to read them.

### What the reader is measured at, and on which frames

The bank was hand-labelled from **135 gap boxes on 120 frames at 60 + 17k s**,
by `tools/gap_bank.py`, which owns `hud_smallfont.json`. It was then run on
**172 boxes from 100 frames at 53.4 + 21.3k s**, a set that shares no frame
with the first and was transcribed before the reader saw it:

    of 147 boxes carrying a value          109 right   2 differ   36 refused
    of the 116 that were framed cleanly    109 right   2 differ    5 refused
    of 25 boxes carrying NO value            0 read as a value

Both disagreements are one digit in the MILLISECONDS, on a glyph the capture's
own inter-frame compression has half eaten, and on neither is it clear that my
transcription is the right one. Neither is wrong in the sign, in the seconds,
or by a whole digit anywhere that changes a call.

**Thirty-one of the 36 refusals are `board.gap_lines` framing scenery into the
box**, not this reader failing to read one: 21 boxes came back wider than 90 px
and 10 taller than 16, against a gap readout's 51-70 by 12. That is a separate
fault in a separate function and it is the next thing worth fixing here; it
costs yield and it costs no correctness, because a box with a grandstand in it
is refused rather than guessed at.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pitcrew.telemetry.hud_time import read_gap, read_seconds, tokens
from pitcrew.telemetry.smallfont import (
    MATCH_FLOOR,
    MIN_COVER,
    _bank,
    _score,
    band_of,
    read_glyphs,
)

REAL = Path(__file__).parent / "fixtures"

# The value each committed crop actually carries, read off it at 14x.
VALUES = [
    ("gap-plus-0.435.png", "+", 0.435),
    ("gap-minus-0.774.png", "-", 0.774),
    ("gap-plus-27.712.png", "+", 27.712),
    ("gap-minus-10.839.png", "-", 10.839),
]


def a_gap(name):
    with Image.open(REAL / name) as image:
        return np.asarray(image.convert("RGB"))


# --- what it reads ---------------------------------------------------------


@pytest.mark.parametrize("name,sign,seconds", VALUES)
def test_a_real_gap_box_reads_its_own_value(name, sign, seconds):
    """The whole point, and it returned None on every box until 5 Sep 2026."""
    assert read_gap(a_gap(name)) == (sign, pytest.approx(seconds))


@pytest.mark.parametrize("name,_sign,seconds", VALUES)
def test_read_seconds_gives_the_magnitude_with_the_sign_stripped(
        name, _sign, seconds):
    assert read_seconds(a_gap(name)) == pytest.approx(seconds)


def test_the_sign_is_a_glyph_and_not_punctuation():
    """Fault 2: the `+` is shorter than a digit, so the fuel-bank path fell
    through its `DIGIT_MIN_HEIGHT` branch and emitted a `:` or a `.` for it.
    That corrupted the token stream before any parsing began."""
    got = tokens(a_gap("gap-plus-27.712.png"))
    assert got[0] == "+"
    assert ":" not in got


def test_two_digits_of_seconds_read_with_the_sign_tight_against_them():
    """GT7 right-aligns the field, so `+ 0.435` has a space after the sign and
    `+27.712` does not. The advance measured off the spaced form is 16 px and
    off the tight one 9, and a bank that took the first stepped straight over
    the leading `2`."""
    assert read_gap(a_gap("gap-plus-27.712.png")) == (
        "+", pytest.approx(27.712))


# --- and what it refuses ---------------------------------------------------


def test_a_box_of_dashes_is_not_a_time():
    """`--:--.---` is what GT7 draws where there is no value yet. The reader
    reads the dashes and the colon perfectly well; having no digits in it is
    what makes it not a time."""
    patch = a_gap("gap-dashes.png")
    assert "".join(read_glyphs(patch)) == "--:--.---"
    assert tokens(patch) is None
    assert read_gap(patch) is None


def test_a_box_with_no_sign_in_it_is_refused():
    """**The sign is a clipping guard, not a decoration.** GT7 right-aligns the
    field, so a box framed a few pixels too far right loses its leading
    characters - and a `+10.435` stripped of the `+` and the `1` is a
    well-formed `0.435`, ten seconds wrong, with nothing in the digits to say
    so. The sign is the leftmost thing drawn: if it is there, nothing to its
    right was cut."""
    patch = a_gap("gap-no-sign-clipped.png")
    assert read_seconds(patch) is not None, "the digits themselves read fine"
    assert read_gap(patch) is None, "but without a sign it is not a gap"


def test_a_blank_plate_reads_as_nothing_at_all():
    """A template that is mostly plate agrees beautifully with a patch that is
    entirely plate. Shape agreement alone scored a full stop 0.95 on four blank
    columns, and the first run of this reader came back with `--0..433-` for a
    known `+0.435` and got 124 of 132 boxes wrong that way. `MIN_COVER` is the
    gate that fails in the other direction: over 6,874 six-column stretches of
    blank plate the best coverage any template reached is 0.504."""
    plate = np.zeros((12, 60, 3), dtype=int) + 20
    assert read_glyphs(plate) is None
    assert read_gap(plate) is None


def test_a_glyph_the_bank_cannot_account_for_refuses_the_whole_box():
    """A hole in the middle of a number is the one thing worse than no number:
    a caller cannot see it and is about to subtract the result from something.
    """
    patch = a_gap("gap-plus-0.435.png").copy()
    patch[3:9, 30:38] = 255                  # a solid block where a digit was
    assert read_glyphs(patch) is None


@pytest.mark.parametrize("bad", [None, np.zeros((0, 0, 3), dtype=int),
                                 np.zeros((4, 4, 3), dtype=int),
                                 np.zeros((12, 60), dtype=int)])
def test_rubbish_in_is_none_out(bad):
    assert band_of(bad) is None
    assert read_glyphs(bad) is None


# --- the bank itself -------------------------------------------------------


def test_the_bank_covers_every_character_the_font_draws():
    assert set(_bank()) == set("0123456789.:+-")


def test_every_template_clears_the_floor_against_itself():
    """A template that cannot recognise its own cell is a template built from
    two different glyphs averaged together."""
    for char, (variants, advance) in _bank().items():
        assert advance >= 3, char
        for one in variants:
            agree, cover, shape = _score(one, one)
            assert agree >= MATCH_FLOOR, (char, agree)
            assert cover >= MIN_COVER, (char, cover)
            assert shape > 0.99, (char, shape)


def test_the_floor_is_the_same_one_the_fuel_bank_uses():
    """It was never the fault - the bank's scale was - so it has not moved, and
    lowering it is how a fabricated gap reaches a driver mid-race."""
    from pitcrew.telemetry import hud_digits
    assert MATCH_FLOOR == hud_digits.MATCH_FLOOR == 0.80


def test_the_font_is_proportional_so_no_fixed_split_can_work():
    """Measured over 135 aligned boxes: 9 px after most digits, 8 after a `1`
    or a `2`, 10 after a `+`, 4 after a full stop. A fixed-width split of a
    merged piece is therefore wrong on any value containing a one, a two or a
    point - which is very nearly every gap - and that is why the reader places
    cells by advance rather than cutting pieces apart."""
    bank = _bank()
    assert bank["."][1] == 4, "the stop is far narrower than any digit"
    assert len({bank[c][1] for c in "0123456789"}) > 1, "not fixed width"
    for char in "0123456789+-:":
        assert 4 < bank[char][1] <= 11, char


def test_the_fuel_bank_refuses_this_font_so_the_fallback_is_safe():
    """`hud_time.tokens` tries the fuel bank first and only falls back here,
    because the two fonts are two pixels apart in height and size cannot choose
    between them. That is safe only while the first path REFUSES the second
    path's input rather than misreading it - measured `None` on all 162 gap
    boxes framed on the race capture, and held here against the crops."""
    from pitcrew.telemetry.hud_digits import INK
    from pitcrew.telemetry.hud_time import _large, _pieces
    for name, _sign, _seconds in VALUES:
        ink = a_gap(name).min(axis=2) > INK
        pieces = _pieces(ink)
        tallest = max(b - t + 1 for _, _, t, b in pieces)
        assert _large(ink, pieces, tallest) is None, name
