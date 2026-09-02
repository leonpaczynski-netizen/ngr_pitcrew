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

### Two limits, and the second is the larger one

**Only `S` has ever been seen.** The whole field ran Racing Soft, so that is
the only glyph in the bank. Anything else is refused - `None`, not a guess -
which is the right failure, but it does mean this cannot yet tell you a rival
switched to a harder tyre. Add the glyph from the first race that shows one.

**And a non-red disc never reaches here at all - which is now a confirmed
defect rather than a worry.** `pit_columns` finds a disc by red dominance, and
the driver confirmed on 3 Sep 2026 that **GT7 changes the disc colour with the
compound**. Every disc in the archive was (200, 25, 0) because the whole field
ran Racing Soft, so the footage could not have shown it.

The consequence is bigger than an unread letter: the disc is not found, the
pit column is not found, and the car reads as never having pitted at all. Until
`pit_columns` knows the colour set, **the pit wall can only see rivals who are
on the same tyre he is.** One frame per compound closes it.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

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
RED_MIN, RED_RATIO = 140, 2.0
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
    red = ((patch[..., 0] > RED_MIN)
           & (patch[..., 0] > patch[..., 1] * RED_RATIO)
           & (patch[..., 0] > patch[..., 2] * RED_RATIO))
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


def read(patch) -> str | None:
    """The compound letter in this disc, or `None` if it cannot be read.

    `None` rather than a guess, and that matters more here than in most
    readers: a compound is a fact about a rival's whole remaining race, and a
    wrong one is worse than a missing one in exactly the way CLAUDE.md rule 3
    describes.
    """
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


def known() -> tuple[str, ...]:
    """The letters this bank can recognise. Everything else reads as `None`."""
    _, templates = _bank()
    return tuple(sorted(templates))
