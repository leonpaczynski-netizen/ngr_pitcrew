"""Plan row 5.0 - the instrument gate - checked against answers known in advance.

The 4 Sep 2026 floors table cannot be re-derived: the scripts that produced it
were never saved, so neither its clean-lap definition nor how "terminal 6th"
was taken is on record (tried 14 Sep on sessions 118/119/114 - the split counts
match the method, the values do not). So the helper is pinned here on data
whose answer is arithmetic, and every floor it produces from now on carries its
method into the measurement store.
"""
from __future__ import annotations

import math
import random
import statistics

from pitcrew.analysis.instrument_gate import (
    MIN_LAPS,
    between_run_floor,
    can_it_move,
    gate,
    known_answer,
    same_setup_floor,
)


def test_the_floor_of_normal_noise_is_what_the_arithmetic_says():
    """For n laps of noise sd s, a half-mean difference has sd s*sqrt(4/n) and
    its absolute value a median of 0.6745 times that."""
    rng = random.Random(7)
    n, sd = 12, 2.0
    medians = []
    for _ in range(40):
        laps = [rng.gauss(100.0, sd) for _ in range(n)]
        medians.append(same_setup_floor(laps).median)
    expected = 0.6745 * sd * math.sqrt(4 / n)
    assert abs(statistics.median(medians) - expected) / expected < 0.25


def test_every_split_is_counted_once():
    floor = same_setup_floor([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    assert floor.splits == math.comb(7, 3)
    even = same_setup_floor([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert even.splits == math.comb(6, 3) // 2


def test_too_few_laps_is_no_floor_not_a_zero_floor():
    floor = same_setup_floor([1.0, 2.0, 3.0])
    assert floor.median is None and floor.p90 is None
    assert not floor.established
    assert str(MIN_LAPS) in floor.why_none


def test_identical_laps_do_not_establish_a_floor():
    """Rule 9's clamp in disguise: zero spread says every difference resolves."""
    assert not same_setup_floor([5.0] * 8).established


def test_the_between_run_floor_is_run_against_run():
    """Pairs of run means, so adding runs does not shrink it toward zero."""
    runs = [[10.0, 10.2], [11.0, 11.1], [10.5], [9.8, 9.9, 10.1], [None, None]]
    floor = between_run_floor(runs)
    assert floor.n == 4 and floor.splits == 6
    rng = random.Random(11)
    few = between_run_floor([[rng.gauss(50, 1)] for _ in range(4)]).median
    many = between_run_floor([[rng.gauss(50, 1)] for _ in range(40)]).median
    assert many > 0.5 * few                  # a half-split would fall ~3x
    assert between_run_floor([[1.0], [2.0]]).median is None


def test_a_pinned_channel_is_caught():
    """5 Sep 2026: ABS held 43-47% of heavy-braking front slip in 0.86-0.92."""
    rng = random.Random(3)
    pinned = [rng.uniform(0.86, 0.92) for _ in range(460)] + \
             [rng.uniform(0.5, 1.0) for _ in range(540)]
    rng.shuffle(pinned)
    assert can_it_move(pinned, band_width=0.06).movable is False
    free = [rng.uniform(0.5, 1.0) for _ in range(1000)]
    assert can_it_move(free, band_width=0.06).movable is True
    assert can_it_move([0.9] * 5, band_width=0.06).movable is None


def test_known_answer_separates_blind_from_seeing_from_backwards():
    floor = same_setup_floor([10.0, 10.4, 9.8, 10.1, 10.3, 9.9, 10.2, 10.0])
    assert known_answer([10.0] * 5, [10.05] * 5, expected="up",
                        floor=floor).verdict == "blind"
    assert known_answer([10.0] * 5, [12.0] * 5, expected="up",
                        floor=floor).verdict == "sees it"
    assert known_answer([10.0] * 5, [8.0] * 5, expected="up",
                        floor=floor).verdict == "wrong way"
    no_floor = same_setup_floor([1.0])
    assert known_answer([1.0], [2.0], expected="up",
                        floor=no_floor).verdict == "cannot tell"


def test_the_gate_passes_only_with_every_check_run_and_passed():
    floor = same_setup_floor([10.0, 10.4, 9.8, 10.1, 10.3, 9.9, 10.2, 10.0])
    seen = known_answer([10.0] * 5, [12.0] * 5, expected="up", floor=floor)
    free = can_it_move([i / 100 for i in range(100)], band_width=0.05)
    assert gate(floor, known=seen, movable=free).usable
    missing = gate(floor)
    assert not missing.usable
    assert any("known-answer" in r for r in missing.reasons)
    assert any("pinned" in r for r in missing.reasons)
    runs = gate(floor, known=seen, movable=free, needs_between_run=True)
    assert not runs.usable and any("between-run" in r for r in runs.reasons)
