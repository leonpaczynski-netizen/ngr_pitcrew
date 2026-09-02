"""Reading GT7's HUD digits, without OpenCV or Tesseract.

GT7 renders the HUD font identically frame to frame, so a template matched in
numpy is exact and costs microseconds. Neither of the usual libraries is
installed here and neither is wanted: a model would be a dependency, a slower
read and a thing nobody can audit, against a font with ten glyphs in it.

**The bank was built from 32 fuel figures in the Spa replay of 1 Sep 2026**,
hand-labelled off the frames, covering every digit 0-9. Read back it scored 29
of 29 with no misreads.

**And then validated on frames it had never seen, against physics rather than
against labels.** Fuel climbs during a stop at the refuel rate, so a series of
reads either evolves smoothly or it does not. At 1 Hz across the Spa stop it
produced 14, 18 in four seconds and 34, 38, 42 in four-second steps - **1.0 L/s,
the measured refuel rate, emerging from the OCR**. Two cars, independently,
agreeing with a figure taken three other ways.

### Refusing is the important half

A glyph that matches nothing well is refused rather than guessed. `read` takes
a floor and returns `None` below it, because the caller is deciding when to
pit: a wrong rival fuel figure is worse than a missing one, and this app has
already written a confident 0.000 into the archive off a reader with no floor.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

BANK_PATH = Path(__file__).with_name("hud_digits.json")

# A glyph that matches its best template less well than this is not read. The
# worst correct glyph in the build set scored 0.882 and the digit `8` is the
# hardest; 0.80 sits below every correct read and above a confusion.
MATCH_FLOOR = 0.80

# White ink on a dark plate.
INK = 150


@lru_cache(maxsize=1)
def _bank():
    data = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    cell = tuple(data["cell"])
    return cell, {k: np.asarray(v, dtype=float)
                  for k, v in data["templates"].items()}


def _runs(indices, merge: int):
    if len(indices) == 0:
        return []
    breaks = np.where(np.diff(indices) > merge)[0]
    out, start = [], 0
    for edge in list(breaks) + [len(indices) - 1]:
        out.append(indices[start:edge + 1])
        start = edge + 1
    return out


def glyphs(patch) -> list:
    """Ink runs across a patch, each tightened to its own rows."""
    ink = patch.min(axis=2) > INK
    used = np.where(ink.any(axis=0))[0]
    out = []
    for run in _runs(used, 1):
        if len(run) < 2:
            continue
        piece = ink[:, run[0]:run[-1] + 1]
        rows = np.where(piece.any(axis=1))[0]
        if len(rows) < 5:
            continue
        out.append(piece[rows[0]:rows[-1] + 1])
    return out


def _cell(bits):
    cell, _ = _bank()
    image = Image.fromarray((bits * 255).astype("uint8"), "L")
    return np.asarray(image.resize(cell, Image.BILINEAR)) / 255.0


def _match(bits) -> tuple[str | None, float]:
    _, templates = _bank()
    grid = _cell(bits)
    best, score = None, -1.0
    for char, template in templates.items():
        similar = 1.0 - float(np.abs(grid - template).mean())
        if similar > score:
            best, score = char, similar
    return best, score


def read_number(patch, *, drop_leading: int = 0,
                max_digits: int = 3) -> int | None:
    """The number in this patch, or `None` if it cannot be read confidently.

    `drop_leading` discards that many ink runs from the left — the fuel figure
    carries a pump icon before its digits, and the icon is not a digit.

    `None` rather than a guess wherever the segmentation is not what a number
    looks like, or any glyph falls below `MATCH_FLOOR`. CLAUDE.md rule 3: this
    feeds a stop decision, and a fabricated tank reading is worse than none.
    """
    if patch is None or getattr(patch, "ndim", 0) != 3 or patch.size == 0:
        return None
    found = glyphs(patch)[drop_leading:]
    if not found or len(found) > max_digits:
        return None
    text = ""
    for bits in found:
        char, score = _match(bits)
        if char is None or score < MATCH_FLOOR:
            return None
        text += char
    return int(text) if text else None


def read_fuel(patch) -> int | None:
    """The fuel figure from a pit column's box: litres, and also percent.

    Every GT7 tank is 100 L, so the two are the same number — which is why the
    HUD can show one figure and mean both.
    """
    return read_number(patch, drop_leading=1, max_digits=3)
