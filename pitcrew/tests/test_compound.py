"""The compound letter inside the pit-lane disc.

Built from 96 discs across a whole Spa race, every one of them Racing Soft:
median distance to the average glyph 0.046, 90th percentile 0.064, worst 0.494
where a pit crew stood in front of one. `MATCH_FLOOR` sits in that gap.
"""
from __future__ import annotations

import numpy as np
import pytest

from pitcrew.telemetry.compound import (
    MATCH_FLOOR,
    _bank,
    colour_of,
    glyph,
    known,
    known_letters,
    known_measured,
    letter,
    read,
)

RED = (205, 42, 44)
DARK = (20, 16, 18)
BEHIND = (60, 64, 70)


def a_disc(letter="S", size=28, filled=True, colour=RED):
    """A coloured circle with a dark glyph in it, on a darker HUD."""
    patch = np.zeros((size + 8, size + 8, 3), dtype=int)
    patch[:] = BEHIND
    centre, radius = (size + 8) / 2.0, size / 2.0
    ys, xs = np.mgrid[0:size + 8, 0:size + 8]
    inside = (ys - centre) ** 2 + (xs - centre) ** 2 <= radius ** 2
    patch[inside] = colour
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


def test_all_five_compounds_are_named_from_their_disc_colour():
    """The colour IS the compound, given by the driver from GT7's timing
    totem: red soft, yellow medium, white hard, blue wet, green intermediate.
    Until 3 Sep 2026 this searched for red alone, which cost the whole stop for
    any rival on another tyre rather than merely the letter."""
    assert known() == ("S", "M", "H", "W", "I")


@pytest.mark.parametrize("code,rgb", [
    ("S", (205, 42, 44)), ("M", (210, 190, 40)), ("H", (235, 238, 240)),
    ("W", (40, 90, 210)), ("I", (40, 190, 70)),
])
def test_each_disc_colour_reads_as_its_compound(code, rgb):
    assert colour_of(a_disc(letter=None, colour=rgb)) == code


def test_only_red_is_measured_and_the_module_says_so():
    """The other four thresholds come from a description, not from pixels, and
    should be tightened the first time each is actually seen."""
    assert known_measured() == ("S",)
    assert known_letters() == ("S",)


def test_the_body_colour_is_taken_from_the_disc_and_not_the_crop():
    """Averaging the brightest half of a square crop of a circle mixes in the
    grey HUD outside it, which dragged every colour towards white - only white
    survived, because that is what red-averaged-with-grey looks like."""
    assert colour_of(a_disc(letter=None, colour=(205, 42, 44))) == "S"


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


def test_a_letter_that_disagrees_with_the_colour_refuses():
    """The colour decides and the letter corroborates. Two readings that
    disagree are not one reading, and a compound is a fact about a rival's
    whole remaining race."""
    patch = a_disc(letter=None)
    centre = patch.shape[0] // 2
    # A bold cross: dark, inside the circle, and nothing like an S.
    patch[centre - 6:centre + 6, centre - 1:centre + 2] = DARK
    patch[centre - 1:centre + 2, centre - 6:centre + 6] = DARK
    assert colour_of(patch) == "S"      # the disc is still red
    assert letter(patch) is None
    assert read(patch) is None


def test_a_colour_with_no_glyph_on_file_stands_on_its_own():
    """Only the S glyph is in the bank. A yellow disc has nothing to
    corroborate against, and refusing it would throw away the colour - which
    is the stronger evidence of the two."""
    assert read(a_disc(letter=None, colour=(210, 190, 40))) == "M"


def test_rubbish_never_raises():
    assert read(None) is None
    assert read(np.zeros((4, 4), dtype=int)) is None
    assert read(np.zeros((0, 0, 3), dtype=int)) is None
    assert glyph(None) is None


def test_the_floor_reads_av1_s_discs_and_respects_live_feed():
    """MATCH_FLOOR must cover AV1-compressed S discs and not clobber the live feed.

    `letter()` is called ONLY for S compounds: M and H short-circuit in `read()`
    before letter() is consulted, so their template distances (0.411-0.520 for M,
    0.335-0.524 for H) carry no false-positive risk.

    Measured on actual disc sub-crops from s213 and s188 groundtruth video at
    LETTER_MAX=160:
      - S discs:        0.397-0.453  (must be ≤ MATCH_FLOOR to pass)
      - live-feed S:    0.046-0.064  (well inside; unchanged)

    The floor must be ≥ 0.453 (worst observed AV1 S crop).  A prior value of
    0.35 was based on a measurement error (distances from the full 32×440 pitcrop
    strip rather than the disc sub-crop).  0.455 covers all 13 observed S crops.
    The upper bound is 0.50 — the live-feed S population is 0.046-0.064 and any
    value up to 0.50 reads them all; the M/H paths don't use letter() so they
    don't constrain it.
    """
    assert 0.064 < MATCH_FLOOR <= 0.50


@pytest.mark.parametrize("fixture", [
    "disc_S_s213_punished.png",
    "disc_S_s213_rocky_l10.png",
    "disc_S_s188_jubby.png",
    "disc_S_s188_maddyL26_exit.png",
])
def test_av1_s_disc_reads_as_soft(fixture):
    """Real disc sub-crops from AV1-compressed recordings decode as S.

    These crops were extracted from the s213 (Monza) and s188 (Sardegna)
    groundtruth video frames using the stored disc bounding boxes.  With
    LETTER_MAX=160, each crop returns a glyph; with MATCH_FLOOR=0.455 the
    glyph scores inside the floor.  Colour_of reads S on all three.

    disc_S_s188_maddyL26_exit.png is Magical daddy's lap-26 exit frame
    (t=2782.0 s), ground truth H→S.  It is the disc that was missed at the
    every=3 replay cadence (phase alignment: k=13910, 13910 % 3 = 2).  Added
    to confirm the exit S IS readable once captured.
    """
    from pathlib import Path
    from PIL import Image
    p = Path(__file__).parent / "fixtures" / fixture
    img = np.array(Image.open(p).convert("RGB"))
    assert colour_of(img) == "S", "disc body should read as red (S)"
    assert read(img) == "S", "full read should return S"


def test_av1_h_disc_reads_as_hard():
    """Real hard disc from s188 Magical daddy's standing frames (t=2775 s).

    This is the arrival compound — H throughout the stop — confirming the
    standing disc does NOT read as S and would not cause a false change.
    """
    from pathlib import Path
    from PIL import Image
    p = Path(__file__).parent / "fixtures" / "disc_H_s188_maddyL26_standing.png"
    img = np.array(Image.open(p).convert("RGB"))
    assert colour_of(img) == "H", "standing disc should read as H (hard)"
    assert read(img) == "H", "full read should return H"
