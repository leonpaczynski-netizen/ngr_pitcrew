"""Grouping a driver's name bitmap across a replay, without reading it.

`tools/read_replay_board.py` identifies rivals by clustering the name strips
rather than transcribing them - exact where OCR would be probabilistic, and the
operator labels each cluster once. The failure that matters is a SPLIT: one
driver arriving as two clusters invents a rival and is invisible, where a merge
shows on the sheet the moment it is looked at.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def board():
    spec = importlib.util.spec_from_file_location(
        "read_replay_board", ROOT / "tools" / "read_replay_board.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["read_replay_board"] = module
    try:
        spec.loader.exec_module(module)
    except SystemExit:          # the tool calls main() under __main__ only
        pass
    return module


def a_name(seed: int, shape=(16, 64), noise: float = 0.0):
    rng = np.random.default_rng(seed)
    bits = rng.random(shape) > 0.6
    if noise:
        flip = rng.random(shape) < noise
        bits = bits ^ flip
    return bits


def test_the_same_name_seen_twice_is_one_cluster(board):
    """The Spa 112 defect: PUNISHED came back as cluster 0 with 591 sightings
    and cluster 9 with one, 0.205 apart against a threshold of 0.18."""
    a = a_name(1)
    b = a_name(1, noise=0.20)          # a little further apart than 0.205
    groups = board.cluster([("first", a), ("second", b)])
    assert len(groups) == 1
    assert len(groups[0]["seen"]) == 2


def test_two_different_names_stay_apart(board):
    """Across the Spa roster the nearest different pair was 0.289."""
    groups = board.cluster([("a", a_name(1)), ("b", a_name(2))])
    assert len(groups) == 2


def test_the_threshold_sits_between_the_two_measured_populations(board):
    """Same driver 0.205, nearest different pair 0.289 — the threshold must
    separate them with margin either side."""
    assert 0.205 < board.SAME_NAME_MAX_DIFF < 0.289


def test_a_bitmap_joins_its_NEAREST_cluster_not_the_first_one(board):
    """The old loop took whichever group was created first, so a strip close
    to one name and closer to another joined by order of appearance."""
    far = a_name(3)
    near = a_name(4)
    almost = a_name(4, noise=0.03)     # unmistakably the second name
    groups = board.cluster([("far", far), ("near", near), ("x", almost)])
    assert len(groups) == 2
    home = next(g for g in groups if len(g["seen"]) == 2)
    assert {k for k, in [(k,) for k in home["seen"]]} == {"near", "x"}


def test_the_exemplar_averages_rather_than_keeping_the_first_sample(board):
    """A cluster founded on an atypical crop compared everything against its
    worst member for the rest of the race."""
    base = a_name(5)
    groups = board.cluster([("a", base),
                            ("b", a_name(5, noise=0.05)),
                            ("c", a_name(5, noise=0.05))])
    assert len(groups) == 1
    assert "sum" in groups[0], "the running total must be carried"
    assert groups[0]["sum"].sum() == pytest.approx(
        sum(b.sum() for b in (base, a_name(5, noise=0.05),
                              a_name(5, noise=0.05))))


def test_clusters_come_back_most_seen_first(board):
    seen = [("a", a_name(6)), ("b", a_name(7)), ("c", a_name(7))]
    groups = board.cluster(seen)
    assert [len(g["seen"]) for g in groups] == sorted(
        [len(g["seen"]) for g in groups], reverse=True)


def test_nothing_at_all_clusters_to_nothing(board):
    assert board.cluster([]) == []
