"""Reading the HUD's digits, and refusing when it cannot.

The bank was built from 32 fuel figures in the Spa replay of 1 Sep 2026 and
validated on frames it had never seen against physics rather than labels: at
1 Hz across a stop it produced 14, 18 in four seconds and 34, 38, 42 in
four-second steps, which is 1.0 L/s — the refuel rate, emerging from the OCR
and agreeing with a figure taken three other ways.
"""
from __future__ import annotations

import numpy as np
import pytest

from pitcrew.telemetry.hud_digits import (
    MATCH_FLOOR,
    _bank,
    _match,
    glyphs,
    read_fuel,
    read_number,
)

CELL, TEMPLATES = _bank()


def a_patch(chars, *, icon=False, scale=2, noise=0.0):
    """Render digits from the bank's own templates, upscaled."""
    w, h = CELL
    pieces = []
    if icon:
        blob = np.zeros((h, w))
        blob[2:h - 2, 1:w - 3] = 1.0
        pieces.append(blob)
    for char in chars:
        pieces.append(TEMPLATES[char])
    gap = np.zeros((h, 2))
    grid = pieces[0]
    for piece in pieces[1:]:
        grid = np.hstack([grid, gap, piece])
    grid = np.kron(grid, np.ones((scale, scale)))
    if noise:
        rng = np.random.default_rng(7)
        grid = np.clip(grid + rng.normal(0, noise, grid.shape), 0, 1)
    rgb = np.repeat((grid * 255)[:, :, None], 3, axis=2).astype(int)
    return np.pad(rgb, ((3, 3), (3, 3), (0, 0)))


def test_every_digit_has_a_template():
    assert set(TEMPLATES) == {str(d) for d in range(10)}


@pytest.mark.parametrize("value", ["0", "1", "7", "8", "12", "45", "93", "100"])
def test_a_number_reads_back_as_itself(value):
    assert read_number(a_patch(value)) == int(value)


def test_the_pump_icon_is_dropped_and_not_read_as_a_digit():
    """The fuel figure carries an icon before its digits."""
    assert read_fuel(a_patch("45", icon=True)) == 45


def test_a_glyph_that_matches_nothing_is_refused_rather_than_guessed():
    """CLAUDE.md rule 3. This feeds a stop decision, and a fabricated tank
    reading is worse than a missing one."""
    w, h = CELL
    junk = np.zeros((h, w))
    junk[::2, ::2] = 1.0
    grid = np.kron(junk, np.ones((2, 2)))
    rgb = np.repeat((grid * 255)[:, :, None], 3, axis=2).astype(int)
    assert read_number(np.pad(rgb, ((3, 3), (3, 3), (0, 0)))) is None


def test_the_floor_sits_below_every_correct_read_and_above_a_confusion():
    """The worst correct glyph in the build set scored 0.882."""
    assert 0.5 < MATCH_FLOOR < 0.88
    for char, template in TEMPLATES.items():
        got, score = _match(template > 0.5)
        assert score >= MATCH_FLOOR, (char, score)


def test_too_many_glyphs_is_not_a_number():
    """A fuel figure is one to three digits; anything longer means the box was
    cut wrong and the answer would be arithmetic on scenery."""
    assert read_number(a_patch("1234"), max_digits=3) is None


def test_nothing_at_all_reads_as_nothing():
    assert read_number(None) is None
    assert read_number(np.zeros((0, 0, 3), dtype=int)) is None
    assert read_number(np.zeros((20, 40, 3), dtype=int)) is None


def test_an_empty_box_is_not_a_zero():
    """A dark patch has no ink, and no ink is not the digit 0."""
    dark = np.full((24, 60, 3), 10, dtype=int)
    assert read_number(dark) is None


def test_it_survives_noise_at_the_level_a_capture_carries():
    assert read_number(a_patch("47", noise=0.06)) == 47


def test_glyph_segmentation_splits_on_ink_not_on_a_fixed_pitch():
    """Digit widths vary — a `1` is narrower than a `0` — so a fixed pitch
    would slice through the wrong place as soon as the value changed."""
    assert len(glyphs(a_patch("10"))) == 2
    assert len(glyphs(a_patch("111"))) == 3
    assert len(glyphs(a_patch("8"))) == 1
