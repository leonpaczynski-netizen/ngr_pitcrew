"""The compound letter inside the pit-lane disc.

`pit_columns` finds the disc. This reads what is written in it, so a rival's
stop carries the tyre he fitted rather than a `None` that nothing later can
fill in.

### It is read from inside the circle, not from the box around it

The disc is a red circle inside a rectangular crop, and the HUD behind the
corners of that crop is darker than the letter and larger than it. A first cut
took the dark pixels of the whole box and produced a filled blob on every
frame. The circle is therefore filled row by row first, and only the dark
pixels inside it are the letter.

Measured over 96 discs across a whole Spa race, every one of them Racing Soft:
the median distance to the average glyph is 0.046 and the 90th percentile
0.064, against a worst case of 0.494 where a pit crew stood in front of one.
`MATCH_FLOOR` sits between them.

### The COLOUR is the compound. The letter corroborates it.

Given by the driver, 3 Sep 2026, from GT7's timing totem:

    red (S) soft      yellow (M) medium     white (H) hard
    blue (W) wet      green (I) intermediate

That is much stronger evidence than the glyph and it is available on every
frame the disc is: a letter can be half behind a pit crew, but the colour of
what is left of the circle is still the colour. So the colour decides, and the
letter is checked against it where the bank has that glyph - a disagreement
refuses rather than picking a side, because a compound is a fact about a
rival's whole remaining race.

**Only red is measured.** It came back (200, 25, 0) across 96 discs. The other
four thresholds are built from the description above and should be tightened
against real pixels the first time each is seen - `known_measured()` says which
is which, so nothing here claims more than it has.

**Only the `S` glyph is in the letter bank**, for the same reason: the whole
field ran Racing Soft. A letter it cannot read is not a refusal of the stop,
just of the corroboration.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from pitcrew.telemetry.pit_columns import disc_mask

BANK_PATH = Path(__file__).with_name("compound_letters.json")

# A glyph further than this from its best template is not read.
#
# **The argument is not "it sits between 0.046 and 0.494". It is what the other
# compounds measure.** With a bank of one class, `read` answers "S" for
# anything inside the floor, so the question that matters is how far away the
# letters GT7 would actually draw instead are. Rendered through this module's
# own normalisation and measured against the shipped template:
#
#     M                     0.455        H                  0.500
#     a blank cell          0.461        5                  0.202
#     6 / 3 / 8 / G         0.274-0.299  an S in another font  0.144-0.299
#
# **M and H are 2.5x the floor**, so there is no plausible route to reading a
# medium as a soft, which is the only confusion that would matter on a pit
# disc. The thin margin is against arbitrary glyphs - a "5" lands 0.022 outside
# - and nothing on a GT7 pit disc is a 5. That margin is what bounds how far
# this may ever be RAISED: at 0.30, five, six, three, eight and G all read as S.
MATCH_FLOOR = 0.18

# The disc body is saturated red; the letter is dark on it.
#
# **Deliberately stricter than `pit_columns.DISC_MIN` (130).** A disc washed out
# by a fluorescent pit crew behind the translucent HUD can pass there and fail
# here, and that is the right way round: `pit_columns` losing the disc costs the
# whole stop, so it should be the more forgiving of the two, while a letter read
# off a washed-out disc is a guess about a rival's whole remaining race.
RED_MIN = 140
# How far one channel must lead the others before the disc is that colour.
CHANNEL_RATIO = 1.35
# Below this much spread between channels the disc is white - the hard compound.
WHITE_SPREAD = 55
LETTER_MAX = 120
# Fewer red pixels than this is not a disc, and fewer dark ones is not a letter.
# **A fraction of the disc, not an absolute count.** 120 pixels needs a disc at
# least 12.4 px across, which is above what `pit_columns.DISC_MIN_FRAC` accepts
# below about 830 rows of frame - the exact shape of the defect that made the
# live gauge go silent at the resolution he actually races at (`396dfcb`).
MIN_DISC_FRACTION, MIN_LETTER_PIXELS = 0.30, 10


@lru_cache(maxsize=1)
def _bank():
    data = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    return (tuple(data["cell"]),
            {k: np.asarray(v, dtype=float) for k, v in data["templates"].items()})


def glyph(patch):
    """The letter inside the disc, normalised to the bank's cell, or `None`."""
    from PIL import Image

    if patch is None or getattr(patch, "ndim", 0) != 3 or patch.size == 0:
        return None
    cell, _ = _bank()
    red = disc_mask(patch)
    # **Fill the circle before looking for ink.** Outside it is the HUD, which
    # is darker than the letter and much larger.
    inside = np.zeros(red.shape, dtype=bool)
    for y in range(red.shape[0]):
        on = np.where(red[y])[0]
        if len(on) >= 4:
            inside[y, on[0]:on[-1] + 1] = True
    if inside.sum() < MIN_DISC_FRACTION * inside.size:
        return None
    dark = inside & (patch.max(axis=2) < LETTER_MAX)
    rows, cols = np.where(dark)
    if len(cols) < MIN_LETTER_PIXELS:
        return None
    crop = dark[rows.min():rows.max() + 1, cols.min():cols.max() + 1]
    if crop.shape[0] < 5 or crop.shape[1] < 3:
        return None
    scaled = Image.fromarray((crop * 255).astype("uint8")).resize(
        cell, Image.BILINEAR)
    return np.asarray(scaled) / 255.0


# The five discs, and the compound each one means. Only `S` is measured.
COMPOUND_COLOURS = ("S", "M", "H", "W", "I")
MEASURED_COLOURS = ("S",)


def colour_of(patch) -> str | None:
    """The compound from the disc's colour, or `None` if it is not one.

    Read off the body of the circle rather than a single pixel: the disc is
    antialiased against whatever is behind a translucent HUD, and the letter
    inside it is dark, so an average over everything would be dragged towards
    the letter.
    """
    if patch is None or getattr(patch, "ndim", 0) != 3 or patch.size == 0:
        return None
    body = _body(patch)
    if body is None:
        return None
    red, green, blue = body
    brightest, darkest = max(body), min(body)
    if brightest < RED_MIN:
        return None
    if brightest - darkest < WHITE_SPREAD:
        return "H"                       # bright and unsaturated
    if red > green * CHANNEL_RATIO and red > blue * CHANNEL_RATIO:
        return "S"
    if green > red * CHANNEL_RATIO and green > blue * CHANNEL_RATIO:
        return "I"
    if blue > red * CHANNEL_RATIO and blue > green * CHANNEL_RATIO:
        return "W"
    if red > blue * CHANNEL_RATIO and green > blue * CHANNEL_RATIO:
        return "M"                       # red and green together
    return None


def _body(patch):
    """Mean RGB of the disc's coloured body, or `None`.

    **Selected with the same mask that found the disc**, not by luminance over
    the whole crop. Averaging the brightest half of the patch mixes in the grey
    HUD outside the circle - which is most of a square crop of a circle - and
    dragged every colour towards it: only white survived, because white is what
    a red disc averaged with grey looks like to a ratio test.
    """
    mask = disc_mask(patch)
    if mask.sum() < MIN_LETTER_PIXELS:
        return None
    kept = patch[mask]
    mean = kept.mean(axis=0)
    return float(mean[0]), float(mean[1]), float(mean[2])


def read(patch) -> str | None:
    """The compound in this disc, or `None` if it cannot be read.

    **The colour decides and the letter corroborates.** Where the bank holds
    the glyph for the colour's compound and the glyph disagrees, this refuses:
    a compound is a fact about a rival's whole remaining race, and two readings
    that disagree are not one reading.

    `None` rather than a guess throughout. CLAUDE.md rule 3.
    """
    code = colour_of(patch)
    if code is None:
        return None
    _, templates = _bank()
    if code not in templates:
        # No glyph on file for this compound - the colour stands alone, which
        # is what it did before there was a bank at all.
        return code
    return code if letter(patch) == code else None


def letter(patch) -> str | None:
    """The glyph inside the disc, matched against the bank, or `None`."""
    found = glyph(patch)
    if found is None:
        return None
    _, templates = _bank()
    best, closest = None, None
    for code, template in templates.items():
        apart = float(np.abs(found - template).mean())
        if closest is None or apart < closest:
            best, closest = code, apart
    if closest is None or closest > MATCH_FLOOR:
        return None
    return best


def known_measured() -> tuple[str, ...]:
    """The compounds whose colour has been measured rather than described.

    The rest are built from the driver's account of GT7's timing totem and
    should be tightened against real pixels the first time each is seen.
    """
    return MEASURED_COLOURS


def known() -> tuple[str, ...]:
    """The compounds this module can name, from their disc colour."""
    return COMPOUND_COLOURS


def known_letters() -> tuple[str, ...]:
    """The glyphs the letter bank holds. Everything else corroborates nothing."""
    _, templates = _bank()
    return tuple(sorted(templates))
