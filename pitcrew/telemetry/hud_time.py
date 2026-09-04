"""Reading a time off the HUD: a lap, a gap, an interval.

`hud_digits` reads whole numbers - a fuel figure. A time is `M:SS.mmm` or
`SS.mmm`, so it needs two things that a fuel figure does not: punctuation, and
a rule for turning the pieces back into seconds.

### The digit bank already reads this font, which was worth checking first

The bank was built on the pit-lane fuel figures. Run against the fastest-lap
banner - white on purple, and its value is known - every digit came back right:

    truth   2  :  1  3  .  4  8  4
    read    2  ?  1  3  ?  4  8  4
    score  .90 -  .86 .81 -  .84 .85 .82

against a floor of 0.80. So there is no second bank here, and a change to the
HUD font is still one thing to fix rather than two.

**The punctuation is where it stops.** A colon scored 0.635 as a "2" and a full
stop 0.731 as a "1" - both under the floor, so they were refused rather than
guessed, which is the right failure and also why they cannot be read this way.
They are told apart by shape instead: both are far narrower than any digit, and
a colon is tall where a stop is short and sits on the baseline.

### `--:--.---` is not a time and must not read as one

GT7 draws that in a gap box that has no value yet - at the start of a race, and
for a car with nobody ahead of it. Measured across a whole 48-minute replay,
**every gap box on every frame showed exactly that**, which is also why the gap
reading in this module was for a long time validated on its structure and on
the fastest-lap banner rather than on a real gap. A dash is a wide, short,
mid-height bar; a digit is not.

### 5 Sep 2026 - the gap font is half the size, and it needed its own reader

The race capture of 4 Sep does draw real gaps, and none of the above could read
one. Two faults, both fixed here and both measured on that capture:

* **The sign was being read as punctuation.** GT7 draws `+ 2.344`, and the `+`
  is shorter than a digit, so it fell through the `DIGIT_MIN_HEIGHT` branch
  below and came out as a `:` or a `.`. That corrupted the token stream before
  any parsing began. `+` and `-` are now characters in their own right, they
  are in the small-font bank, and `read_gap` returns the one it found - because
  on a gap box the sign is the difference between `0.435` and a clipped
  `10.435`, which is the same ten-second error this file's other guards exist
  to prevent.
* **The bank was the wrong scale.** A gap glyph is 11-12 px tall against the
  fuel bank's 20-odd, every one of twenty measured scored 0.526-0.744 against
  the 0.80 floor, and no ink threshold segments the font at that size at all.
  That is `telemetry/smallfont.py`, which this module falls back to wherever
  the fuel bank refuses. **The clipped-box guard below runs before that
  fallback and applies to both**, which is the whole reason the split is here
  rather than in the caller.
"""
from __future__ import annotations

import numpy as np

from pitcrew.telemetry import smallfont
from pitcrew.telemetry.board import _runs
from pitcrew.telemetry.hud_digits import INK, MATCH_FLOOR, _match

# **Punctuation is SHORTER than a digit, and that is the whole test.** Measured
# on the fastest-lap banner, where the value is known:
#
#     glyph   2    :    1    3    .    4
#     h/tall 1.00 0.71 1.00 1.00 0.21 1.00
#     w/wide 1.00 0.22 0.56 1.00 0.33 1.00
#
# Width does not separate them - the "1" is narrower than the full stop is
# wide, relative to the tallest glyph - but height does, with a clear gap
# either side. A first cut used width and read the 1 as a colon.
DIGIT_MIN_HEIGHT = 0.85
# ...and among punctuation, a colon spans most of the height where a full stop
# sits in the bottom fifth.
COLON_MIN_HEIGHT = 0.45

# A piece wider than this many times the tallest glyph is not a glyph at all -
# it is a plate, a bar or a row of dashes run together - and a box containing
# one is not a clean time box.
NOT_A_GLYPH_WIDE = 2.0

# A run narrower or shorter than this is not a glyph - it is a sliver, and a
# sliver would otherwise become a piece and be classified as punctuation.
#
# **Two, not the five `hud_digits.glyphs` uses.** That floor is safe for a fuel
# figure, which is all digits; here the smallest legitimate glyph is the full
# stop, measured at 3 x 3 px on the fastest-lap banner. Setting this to 5 threw
# the decimal point away and turned a known 133.484 into a refusal - and the
# synthetic fixture did not catch it, because it renders the stop at six pixels.
MIN_RUN_WIDE, MIN_RUN_TALL = 2, 2



def _pieces(ink):
    """(x0, x1, top, bottom) for every ink run across a patch."""
    used = np.where(ink.any(axis=0))[0]
    out = []
    for run in _runs(used, 1):
        piece = ink[:, run[0]:run[-1] + 1]
        rows = np.where(piece.any(axis=1))[0]
        if len(run) < MIN_RUN_WIDE or len(rows) < MIN_RUN_TALL:
            continue
        out.append((int(run[0]), int(run[-1]), int(rows[0]), int(rows[-1])))
    return out


def _large(ink, pieces, tallest) -> list[str] | None:
    """The fuel-bank path: a glyph per run, punctuation told by height."""
    out: list[str] = []
    for x0, x1, top, bottom in pieces:
        wide, tall = x1 - x0 + 1, bottom - top + 1
        if wide > NOT_A_GLYPH_WIDE * tallest:
            return None                  # a plate or a run of dashes, not text
        if tall / tallest < DIGIT_MIN_HEIGHT:
            out.append(":" if tall / tallest >= COLON_MIN_HEIGHT else ".")
            continue
        char, score = _match(ink[top:bottom + 1, x0:x1 + 1])
        if char is None or score < MATCH_FLOOR:
            return None                  # a glyph it cannot read is a refusal
        out.append(char)
    return out


def tokens(patch) -> list[str] | None:
    """The glyphs in this patch as characters, or `None` if it is not a time.

    Returns digits, `:` and `.`. A patch of dashes returns `None` rather than
    an empty list: "no value drawn" is a fact about the box, and it is not the
    same as "nothing found in it".
    """
    if patch is None or getattr(patch, "ndim", 0) != 3 or patch.size == 0:
        return None
    ink = patch.min(axis=2) > INK
    if ink.sum() == 0:
        return None
    pieces = _pieces(ink)
    if not pieces:
        return None
    # **Ink touching either edge means the box was cut, and a cut time can
    # parse cleanly as a shorter one.** Sweeping a `1:23.456` across the band,
    # eleven offsets of 121 returned a well-formed WRONG answer - `3.456` for a
    # true 83.456 - against fifteen that were right. A clipped box is refused
    # rather than read.
    if pieces[0][0] <= 0 or pieces[-1][1] >= ink.shape[1] - 1:
        return None
    tallest = max(bottom - top + 1 for _, _, top, bottom in pieces)
    if tallest < 5:
        return None
    # **The fuel bank first, and the small-font bank only where it refuses.**
    # Size cannot choose between them and it was the first thing tried: a gap
    # glyph measures 12 px tall on 155 of 162 real boxes, and the fastest-lap
    # banner - which the fuel bank does read, and which is the one known-value
    # fixture this module has ever had - draws a three-pixel full stop, so
    # it is about 14. Two pixels apart is not a rule, and one set between
    # them took the banner away.
    #
    # A fallback needs the first path to refuse the second path's input rather
    # than misread it, and that is measured rather than hoped: over the 162 gap
    # boxes framed on the 4 Sep race capture, `_large` returned `None` on
    # **every one**, because a 12 px glyph resized into the fuel bank's cell
    # scores 0.526-0.744 against a 0.80 floor. `test_hud_time` holds that line
    # against the committed real crops.
    out = _large(ink, pieces, tallest)
    if out is None:
        out = smallfont.read_glyphs(patch)
    if not out:
        return None
    if not any(c.isdigit() for c in out):
        # "--:--.---" and anything else with no figures in it. The box exists
        # and carries no value, which is a fact about the box.
        return None
    return out or None


def read_gap(patch) -> tuple[str, float] | None:
    """`(sign, seconds)` for a gap readout, or `None`.

    The sign is `"+"` or `"-"`, and **it is required**, which is a correctness
    guard rather than a nicety. GT7 right-aligns the gap field, so a box framed
    a few pixels too far right loses the leading character - and `+10.435`
    stripped of its `+` and its `1` reads as a perfectly well-formed `0.435`,
    ten seconds wrong, in a figure `rejoin_against` is about to compare with a
    pit-stop cost. There is nothing in the digits to say it happened. There is
    in the sign: if the sign is there, nothing to its right was cut, because
    the sign is the leftmost thing GT7 draws.

    Measured over 169 gap boxes on the 4 Sep capture, the sign is present on
    165 and agrees with the side of the driver's row on all 165 - `+` on the
    row above, `-` on the row below. The four without one are exactly the four
    the box was framed too tight on.
    """
    found = tokens(patch)
    if not found or found[0] not in ("+", "-"):
        return None
    seconds = _seconds("".join(found[1:]))
    return None if seconds is None else (found[0], seconds)


def read_seconds(patch) -> float | None:
    """The time in this patch, in seconds, or `None`.

    Accepts `M:SS.mmm`, `SS.mmm` and `S.mmm`, with an optional leading sign -
    the MAGNITUDE, because a gap is a distance and every caller subtracts it
    from something. Use `read_gap` where the sign matters. Refuses anything
    else outright: a partly-read time is the one thing worse than an unread
    one here.
    """
    found = tokens(patch)
    if not found:
        return None
    text = "".join(found)
    if text[:1] in ("+", "-"):
        text = text[1:]
    return _seconds(text)


def _seconds(text: str) -> float | None:
    """`M:SS.mmm` / `SS.mmm` / `S.mmm` as seconds, or `None`."""
    minutes = 0.0
    has_minutes = ":" in text
    if has_minutes:
        head, _, text = text.partition(":")
        # **One digit of minutes, and no more.** GT7 draws `M:SS.mmm`, so
        # "12:34.567" is not a long lap - it is two glyphs that should not both
        # be there, and it parsed happily as 754 seconds.
        if len(head) != 1 or not head.isdigit() or text.count(":"):
            return None
        minutes = float(head)
    if "." not in text:
        return None
    whole, _, fraction = text.partition(".")
    if not whole.isdigit() or not fraction.isdigit():
        return None
    if len(fraction) != 3:
        return None
    # **The seconds field is zero-padded whenever minutes are shown, and that
    # is the guard that catches a clipped box.** `1:2.345` is not a time GT7
    # draws; it is what `1:12.345` looks like with a digit cut off, and it
    # parsed as 62.345 against a true 72.345 - ten seconds wrong, silently, in
    # a number the caller is about to subtract from something.
    if has_minutes and len(whole) != 2:
        return None
    if len(whole) > 2 or (not has_minutes and not whole):
        return None
    seconds = float(whole) + float(fraction) / 1000.0
    if seconds >= 60.0:
        return None
    return minutes * 60.0 + seconds
