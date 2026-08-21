"""A physics update is a discontinuity, not a decay."""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.analysis.version import prefer_current, versions_present


@dataclass
class Lap:
    lap_num: int
    game_version: str | None = None


def laps(*spec) -> list[Lap]:
    return [Lap(i, v) for i, v in enumerate(spec, 1)]


def test_current_version_evidence_is_used_alone():
    got = prefer_current(laps("1.70", "1.70", "1.71", "1.71"), "1.71")
    assert [lap.lap_num for lap in got.laps] == [3, 4]
    assert got.version == "1.71" and not got.stale
    # Silence about the held-back laps would read as "there were only two".
    assert "held back" in got.note and "1.70" in got.note


def test_nothing_is_blended_across_a_patch():
    """An average across a patch describes nothing that was ever driven."""
    got = prefer_current(laps("1.70", "1.71"), "1.71")
    assert versions_present(got.laps) == ["1.71"]


def test_too_little_new_evidence_falls_back_and_says_so():
    """Falling back beats returning two laps into a check that needs five.

    A sample-count refusal downstream would produce silence with no reason
    attached, and silence is what CLAUDE.md keeps insisting must never stand in
    for a finding.
    """
    got = prefer_current(laps("1.70", "1.70", "1.70", "1.71"), "1.71", minimum=5)
    assert len(got.laps) == 4 and got.stale
    assert "no usable evidence on GT7 1.71" in got.note
    assert "re-measure on 1.71" in got.note


def test_a_clean_current_set_needs_no_caveat():
    got = prefer_current(laps("1.71", "1.71"), "1.71")
    assert got.note is None and not got.stale


def test_laps_with_no_version_are_not_treated_as_current():
    """Unrecorded is not the same as recorded under the version installed."""
    got = prefer_current(laps(None, None), "1.71")
    assert got.version is None and not got.stale
    assert "no lap carries a game version" in got.note


def test_an_unset_installed_version_cannot_sort_anything():
    got = prefer_current(laps("1.70", "1.71"), None)
    assert len(got.laps) == 2
    assert "installed GT7 version is not set" in got.note


def test_no_laps_is_not_an_error():
    got = prefer_current([], "1.71")
    assert not got and got.note is None
