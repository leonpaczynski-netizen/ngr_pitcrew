"""Reading GT7's SMALL HUD font — the gap readouts — without segmenting it.

`hud_digits` reads the pit-column fuel figures, which are big: a glyph there is
20-odd pixels tall, every glyph is separated from its neighbours by a clear
column of plate, and one template per character is enough. The three gap
readouts on the leaderboard are the same typeface at about half that size, and
at that size two things break at once.

### The bank was the wrong scale, and every glyph fell under the floor

Measured on real frames of the 4 Sep Daytona race (`2026-09-04 22-12-04.mp4`,
1920x1080) at t=900, 1200 and 1805 s: a gap digit is **4-8 px wide and 11-12 px
tall**, against a fuel digit's 20. Put through `hud_digits._match`, twenty gap
glyphs scored **0.526 to 0.744 against the 0.80 floor** — every one refused,
and several would have been the wrong character had the floor let them through.
`read_gaps` therefore returned `None` on every box of every frame ever tried,
which is exactly the right failure and is also why the driver's engineer could
not tell him the one thing no telemetry channel carries.

**The floor is not the problem and it has not moved.** A gap spoken to a driver
mid-race is acted on; `race/gaps.py` records an eleven-offset sweep in which a
clipped box returned a *well-formed wrong* time — 3.456 for a true 83.456 — and
that is the failure this floor exists to prevent. What changed is the bank: the
templates below are hand-labelled from the gap font at its own scale.

### And segmentation cannot work at this size, at any threshold

The obvious repair — a second bank, same reader — does not work, because that
reader cuts glyphs apart at columns of empty plate and at 12 px there are none.
Swept across one box whose value is known to be `+ 0.435`, six glyphs:

    ink threshold   150 (the fuel one)   140   120   110   100    80
    pieces found          7                6     6     5     4     4

Seven at the top of the range because anti-aliasing snaps a stroke in half,
four at the bottom because neighbouring glyphs bridge. Two thresholds hit six —
and **neither of them is the right six**: at 140 the pieces come out 8, 5, 1,
1, 7 and 15 px wide, two of them single-pixel slivers of the full stop and one
covering the `3` and the `5` together. Across the corpus the same sweep gave
merged pieces of 9, 10, 13 and 15 px where a single digit is 4-8.

A fixed-width split of a merged piece is a guess, and the font is not fixed
width anyway. Measured over 135 aligned boxes, the advance is **9 px after most
digits, 8 after a `1` or a `2`, 10 after a `+`, and 4 after a full stop** — so
a guess would be wrong on any value containing a one, a two or a point, which
is very nearly every gap.

So this module **never segments**. Each template carries its own advance, and a
dynamic program walks the box left to right placing cells end to end, taking
the parse that accounts for every inked column at the lowest total pixel error.
A merge is not a case to be handled: two glyphs that touch are two placements
with no blank between them, which is what the program was going to try anyway.

### Why a separate bank, and several templates per character

`hud_digits._match` resizes every glyph into one small cell and compares. That
is what a bank of one template per character needs, and it is why that bank
survives a change of HUD scale. It is also what destroys a 12 px glyph: the
resize is where the 0.526-0.744 scores come from, not the font. So the small
font gets its own bank and its own matcher, matched at its own resolution
against a band normalised only in height. The fuel bank is untouched, and
`read_fuel` and `pit_columns` read exactly what they read before.

And it holds **three to five cells per character, because of sub-pixel phase**.
The gap field is right-aligned in a fixed layout, so a `0` in the units column
lands on the same fractional pixel every frame while a `0` in the milliseconds
lands on three others. One averaged template is the mean of all four and
matches none of them well: on box `f00111.00 ahead`, a known `+0.074`, the
single `0` template scored 0.970 on the units digit and below the floor on the
millisecond `0` two glyphs later, which came back as a `6` at 0.893.

### What the templates are, and what they were measured at

Built by `tools/gap_bank.py`, **which owns `hud_smallfont.json` — do not hand-
edit it** — from **135 gap boxes hand-labelled off 120 frames** of the 4 Sep
Daytona race at 60 + 17k s. Every character in `0123456789.:+-` is covered.

Read back on **172 boxes from 100 frames at 53.4 + 21.3k s**, a set that shares
no frame with the first and was transcribed before the reader saw it:

    of 147 boxes carrying a value            109 right   2 differ   36 refused
    of the 116 that were cleanly framed      109 right   2 differ    5 refused
    of 25 boxes carrying NO value              0 read as a value

Both disagreements are one digit in the MILLISECONDS, on a glyph the capture's
own inter-frame compression has half eaten, and on neither is it clear that the
transcription is the right one. Neither is wrong in the sign, in the seconds,
or by a whole digit anywhere that changes a call.

**Thirty-one of the 36 refusals are `board.gap_lines` framing scenery into the
box** rather than this module failing to read one: 21 came back wider than
90 px and 10 taller than 16, against a gap readout's 51-70 by 12. That is a
separate fault in a separate function, it is the next thing worth fixing here,
and it costs yield rather than correctness — a box with a grandstand in it is
refused, not guessed at.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

BANK_PATH = Path(__file__).with_name("hud_smallfont.json")

# Every band is scaled to this many rows before matching, and its columns are
# scaled by the same factor, so the templates are in one coordinate system
# whatever projector size the board is drawn at. 12 is the measured height of
# the gap text at a 1080-row capture, so at that size this is the identity.
BAND_H = 12

# The ink threshold used only to FIND the text band and the blank columns
# inside it, as a fraction of the box's own plate-to-ink span. Matching itself
# is done on the greyscale, never on a threshold: at 12 px the anti-aliasing is
# most of the glyph, and throwing it away is what cost the fuel bank its score.
INK_FRAC = 0.35

# A glyph whose best template agrees with it less well than this is not read.
#
# **The same 0.80 that `hud_digits` uses, on the same metric, and deliberately
# so.** The floor was never the fault - the bank's scale was - so it has not
# moved, and nothing here would work if it had to.
#
# Measured over 1,588 glyphs placed at their true positions across both frame
# sets, agreement for the CORRECT character runs 0.604-0.992 with a median of
# 0.966 and a fifth percentile of 0.825. It is the weakest of the three gates
# on its own - the best a wrong character reached at a true glyph position is
# 0.967, over 20,644 tries - which is why there are three.
MATCH_FLOOR = 0.80

# ...and the window must also carry the ink the template says is there.
#
# **A shape score alone lets a blank window read as a glyph, and it did.** The
# score above is `1 - mean|window - template|`, which is a claim about
# agreement, and a template that is mostly plate agrees beautifully with a
# patch that is entirely plate: a full stop is four columns with three lit
# pixels in them, so an empty stretch of bar scored it 0.95. The first run of
# this reader got 124 of 132 boxes wrong for exactly that reason, nearly all of
# them by inventing punctuation on blank plate - a known `+0.435` came back as
# `--0..433-`.
#
# So a placement must clear gates that fail in opposite directions: agreement
# bounds the ink the window has and the template does not, coverage bounds the
# ink the template has and the window does not. Measured across both frame
# sets, coverage of a correct glyph has a median of 0.944 and a fifth
# percentile of 0.669; over 6,874 six-column stretches of blank plate, the best
# any template reached is 0.504.
MIN_COVER = 0.50

# ...and the correlation between window and template, which is what actually
# tells two round digits apart.
#
# **Agreement alone could not, and the numbers say why.** A cell is 12 rows by
# 9 columns and most of it is plate, so a whole stroke's worth of disagreement
# moves a mean absolute difference by about 0.02. Measured on box
# `f00451.00 ahead`, a known `+0.869`: at the `8`, agreement ranked `3` at
# 0.890, `6` at 0.886, `9` at 0.873 and the true `8` at 0.803 - a spread of
# 0.087 across four different characters. Correlation subtracts the plate from
# both sides before comparing, and on the same cell it ranks the `8` first: the
# correct character has a median correlation of 0.988 against a wrong one's
# 0.143. It is the dynamic program's cost function for the same reason.
#
# **The three gates together are what refuses blank plate.** Individually each
# is beatable by an empty stretch of bar - measured maxima 0.922 agreement,
# 0.504 coverage, 0.858 correlation. Together, **0 of 6,874 blank windows pass
# all three**, and no box carrying no value read as a value on either set.
SHAPE_FLOOR = 0.80

# How far a glyph's start may sit from exactly one advance past the last one.
#
# Measured over 135 aligned boxes, the spacing after a digit is 9 px on the
# large majority and 8 or 10 on the rest; after a `1` it is 7, 8 or 9 in the
# ratio 10:38:26, because a bare vertical stroke does not pin its own position
# to better than a pixel. Two is what covers that spread. One left the reader
# unable to reach the glyph after a `1` at all: every one of the 14 boxes it
# still refused on the build set contained one.
KERN = 2


@lru_cache(maxsize=1)
def _bank():
    data = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    out = {}
    for char, spec in data["templates"].items():
        out[char] = ([np.asarray(v, dtype=float) for v in spec["variants"]],
                     int(spec["advance"]))
    return out


def band_of(patch):
    """The text band of a gap box as greyscale in 0..1, `BAND_H` rows tall.

    `None` where the patch is not a plate with ink on it at all. The floor and
    ceiling are the box's OWN 5th and 99th percentiles rather than fixed
    levels, because the gap plate is semi-transparent: measured across the
    race, the same readout sits on a plate reading 2-60 depending on whether
    the car is passing grandstand, sky or grass.
    """
    if patch is None or getattr(patch, "ndim", 0) != 3 or patch.size == 0:
        return None
    if patch.shape[0] < 5 or patch.shape[1] < 5:
        return None
    lum = patch.min(axis=2).astype(float)
    low, high = np.percentile(lum, 5), np.percentile(lum, 99)
    if high - low < 40:
        return None                  # no ink on it, or a blown-out white bar
    grey = np.clip((lum - low) / (high - low), 0.0, 1.0)
    rows = np.where((grey > INK_FRAC).any(axis=1))[0]
    cols = np.where((grey > INK_FRAC).any(axis=0))[0]
    if len(rows) < 5 or len(cols) < 3:
        return None
    grey = grey[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    if grey.shape[0] == BAND_H:
        return grey
    scale = BAND_H / grey.shape[0]
    wide = max(3, int(round(grey.shape[1] * scale)))
    image = Image.fromarray((grey * 255).astype("uint8"), "L")
    return np.asarray(image.resize((wide, BAND_H), Image.BILINEAR)) / 255.0


def _score(window, template) -> tuple[float, float]:
    """`(agreement, coverage)` for one template laid over one window.

    Agreement is `1 - mean|window - template|`, the same metric and the same
    scale as `hud_digits._match`, so `MATCH_FLOOR` means the same thing in both
    banks. Coverage is the share of the template's own ink that the window
    actually has under it, which is the half agreement cannot see.
    """
    if window.shape[1] < template.shape[1]:
        window = np.pad(window, ((0, 0), (0, template.shape[1]
                                          - window.shape[1])))
    window = window[:, :template.shape[1]]
    agreement = 1.0 - float(np.abs(window - template).mean())
    weight = float(template.sum())
    cover = 0.0 if weight <= 0 else float(
        np.minimum(window, template).sum()) / weight
    a = window - window.mean()
    b = template - template.mean()
    spread = float(np.sqrt((a * a).sum() * (b * b).sum()))
    shape = 0.0 if spread <= 0 else float((a * b).sum()) / spread
    return agreement, cover, shape


def read_text(band, *, spans: bool = False):
    """Every glyph in this band, left to right, or `None`.

    A dynamic program over start positions rather than a segmentation - see the
    module docstring for why segmentation cannot work at this size. Each
    placement must clear `MATCH_FLOOR`, and the parse must cover every column
    that carries ink, so a glyph the bank cannot account for is a refusal for
    the whole box rather than a hole in the middle of a number.

    With `spans=True` returns `(char, x0, x1)` triples, which is what the bank
    builder needs to cut the next generation of templates out.
    """
    if band is None or band.size == 0:
        return None
    bank = _bank()
    wide = band.shape[1]
    inked = (band > INK_FRAC).any(axis=0)

    def skip(x):
        while x < wide and not inked[x]:
            x += 1
        return x

    best: dict[int, tuple | None] = {}

    def solve(x):
        x = skip(x)
        if x >= wide:
            return 0.0, []
        if x in best:
            return best[x]
        best[x] = None                      # cycles are not parses
        found = None
        for char, (variants, advance) in bank.items():
            got, cover, shape, template = -1.0, 0.0, -1.0, variants[0]
            for one in variants:
                agree, seen, fit = _score(band[:, x:x + one.shape[1]], one)
                if fit > shape:
                    got, cover, shape, template = agree, seen, fit, one
            if got < MATCH_FLOOR or cover < MIN_COVER or shape < SHAPE_FLOOR:
                continue
            # **The cost is per PIXEL, not per glyph, and that is what stops
            # the reader inventing punctuation.** Ranking parses by total score
            # rewards every extra glyph, because each one adds another term
            # near 1.0: on the first run `+0.435` came back as `+0..435`, the
            # second full stop scoring 0.844 on the four blank columns between
            # the real one and the `4`, for a total of 6.243 against the
            # correct parse's 5.451. Summed pixel error has no such bias - the
            # correct parse cost 55.2 against the doubled one's 65.5 - and it
            # is still additive, so the dynamic program still holds.
            cost = (1.0 - shape) * template.shape[1]
            for drift in range(-KERN, KERN + 1):
                nxt = x + advance + drift
                if nxt <= x:
                    continue
                rest = solve(nxt)
                if rest is None:
                    continue
                total = cost + rest[0]
                if found is None or total < found[0]:
                    found = (total, [(char, x, x + template.shape[1])]
                             + rest[1])
        best[x] = found
        return found

    parsed = solve(0)
    if parsed is None or not parsed[1]:
        return None
    return parsed[1] if spans else [c for c, _, _ in parsed[1]]


def read_glyphs(patch) -> list[str] | None:
    """The characters in a small-font patch, or `None`.

    `band_of` and then `read_text`, which is all any caller outside
    this module wants.
    """
    return read_text(band_of(patch))
