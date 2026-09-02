"""The compound letter inside the pit-lane disc.

Built from 96 discs across a whole Spa race, every one of them Racing Soft:
median distance to the average glyph 0.046, 90th percentile 0.064, worst 0.494
where a pit crew stood in front of one. `MATCH_FLOOR` sits in that gap.
"""
from __future__ import annotations

import numpy as np

from pitcrew.telemetry.compound import MATCH_FLOOR, _bank, glyph, known, read

RED = (205, 42, 44)
DARK = (20, 16, 18)
BEHIND = (60, 64, 70)


def a_disc(letter="S", size=28, filled=True):
    """A red circle with a dark glyph in it, on a darker HUD."""
    patch = np.zeros((size + 8, size + 8, 3), dtype=int)
    patch[:] = BEHIND
    centre, radius = (size + 8) / 2.0, size / 2.0
    ys, xs = np.mgrid[0:size + 8, 0:size + 8]
    inside = (ys - centre) ** 2 + (xs - centre) ** 2 <= radius ** 2
    patch[inside] = RED
    if letter is None:
        return patch
    cell, templates = _bank()
    if filled and letter in templates:
        from PIL import Image
        grid = np.asarray(
            Image.fromarray(((templates[letter] > 0.5) * 255).astype("uint8"))
            .resize((int(size * 0.42), int(size * 0.52)), Image.NEAREST)) > 127
        top = int(centre - grid.shape[0] / 2)
        left = int(centre - grid.shape[1] / 2)
        block = patch[top:top + grid.shape[0], left:left + grid.shape[1]]
        block[grid] = DARK
    return patch


# --- what it reads ---------------------------------------------------------

def test_the_letter_in_the_disc_is_read():
    assert read(a_disc("S")) == "S"


def test_the_bank_says_what_it_can_recognise():
    """Only Racing Soft has ever been seen: the whole measured field ran it.
    Anything else refuses rather than guessing, which is the right failure but
    does mean a switch to a harder tyre cannot yet be reported."""
    assert known() == ("S",)


def test_the_glyph_comes_from_inside_the_circle():
    """Taking dark pixels from the disc's bounding box picks up the HUD behind
    the corners, which is darker than the letter and larger than it. A first
    cut did exactly that and produced a filled blob on every frame."""
    found = glyph(a_disc("S"))
    assert found is not None
    # An S is mostly empty space; a blob of the whole box would not be.
    assert 0.15 < float((found > 0.5).mean()) < 0.75


# --- what it refuses -------------------------------------------------------

def test_a_disc_with_no_letter_is_not_a_compound():
    assert read(a_disc(letter=None)) is None


def test_something_that_is_not_a_disc_at_all_refuses():
    plain = np.zeros((36, 36, 3), dtype=int)
    plain[:] = BEHIND
    assert read(plain) is None


def test_an_unknown_letter_refuses_rather_than_answering_with_the_nearest():
    """A compound is a fact about a rival's whole remaining race, and a wrong
    one is worse than a missing one."""
    patch = a_disc(letter=None)
    centre = patch.shape[0] // 2
    # A bold cross: dark, inside the circle, and nothing like an S.
    patch[centre - 6:centre + 6, centre - 1:centre + 2] = DARK
    patch[centre - 1:centre + 2, centre - 6:centre + 6] = DARK
    assert read(patch) is None


def test_rubbish_never_raises():
    assert read(None) is None
    assert read(np.zeros((4, 4), dtype=int)) is None
    assert read(np.zeros((0, 0, 3), dtype=int)) is None
    assert glyph(None) is None


def test_the_floor_sits_between_the_measured_populations():
    """0.064 was the 90th percentile of a real S; 0.494 the worst obscured
    one."""
    assert 0.064 < MATCH_FLOOR < 0.494
