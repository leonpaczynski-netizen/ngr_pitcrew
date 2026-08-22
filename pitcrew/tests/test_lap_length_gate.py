"""Laps whose integrated distance disagrees with the session's own median.

**`lap_distance_m` is not in any packet format.** `telemetry/recorder.py`
integrates it from speed, and its docstring claims the result "lands within a
percent or two of the circuit's published length and does so consistently lap
to lap". Measured 22 Aug 2026 over 307 clean laps, the first half is true of
the MEDIAN and the second half is not true at all: at Monza, true length
5793 m, the integrated length runs from **203 m to 11,187 m** and its standard
deviation *within one run* is 620 m - over a tenth of a lap.

A corner window is a fixed distance range. So a lap that integrates long is not
imprecise about its corners, it is measuring a different piece of road, and
averaging it in moves the aggregate toward a corner that was never driven. On
the archive this holds out 34 laps, including a Yas lap of 153 m and two
Watkins laps of ~8,000 m that had swallowed a crossing.
"""
from __future__ import annotations

from pitcrew.analysis import thresholds
from pitcrew.analysis.corners import (
    CountedLap,
    aggregate_corners,
    integrated_length,
    length_gate,
)

from .test_corners import a_model, frame


def a_lap(number: int, length_m: float, *, step: float = 10.0) -> CountedLap:
    """A lap whose integrated distance ends at `length_m`."""
    frames = []
    distance, index = 0.0, 0
    while distance <= length_m:
        frames.append(frame(distance, 150.0, index))
        distance += step
        index += 1
    return CountedLap(number, frames)


def a_session(count: int = 10, length_m: float = 5000.0) -> list[CountedLap]:
    return [a_lap(n, length_m) for n in range(1, count + 1)]


# ------------------------------------------------------------- the measure

def test_a_lap_reports_its_own_integrated_length():
    assert integrated_length(a_lap(1, 5000.0)) == 5000.0


def test_a_lap_with_no_distance_channel_reports_none():
    frames = [{**frame(0.0, 150.0, i), "lap_distance_m": None}
              for i in range(20)]
    assert integrated_length(CountedLap(1, frames)) is None


# ---------------------------------------------------------------- the gate

def test_a_lap_that_swallowed_a_crossing_is_held_out():
    """The measured case: Watkins laps 13 and 39 integrate to ~8,000 m on a
    5,410 m circuit, because a crossing went missing and one row holds two
    laps."""
    laps = a_session() + [a_lap(11, 8000.0)]
    gate = length_gate(laps)
    assert [lap.lap for lap, _ in gate.dropped] == [11]
    assert len(gate.kept) == 10


def test_a_fragment_is_held_out():
    """Yas lap 15 integrates to 153 m and was not excluded on any other
    ground."""
    gate = length_gate(a_session() + [a_lap(11, 150.0)])
    assert [lap.lap for lap, _ in gate.dropped] == [11]


def test_a_lap_inside_the_tolerance_is_kept():
    inside = 5000.0 * (1 + thresholds.LAP_LENGTH_TOLERANCE * 0.5)
    gate = length_gate(a_session() + [a_lap(11, inside)])
    assert gate.dropped == []


def test_the_reference_is_the_session_median_not_a_published_length():
    """**The integration has its own scale error** - consistent, and the same
    for every lap of a session. Gating against a published figure would reject
    a whole session for being uniformly short, which is exactly the case the
    windows handle perfectly well."""
    short = a_session(10, length_m=5000.0 * 0.985)      # 1.5% under, all of it
    gate = length_gate(short)
    assert gate.dropped == []
    assert gate.median_m is not None


def test_too_few_laps_means_the_gate_did_not_run():
    """"The gate found nothing" and "the gate did not run" are different
    claims about the same empty list."""
    gate = length_gate(a_session(thresholds.LAP_LENGTH_MIN_LAPS - 1))
    assert gate.ran is False
    assert gate.dropped == []
    assert len(gate.kept) == thresholds.LAP_LENGTH_MIN_LAPS - 1


def test_a_lap_with_no_distance_at_all_is_kept():
    """It contributes no corner windows anyway, so dropping it would report an
    exclusion that changed no number."""
    frames = [{**frame(0.0, 150.0, i), "lap_distance_m": None}
              for i in range(20)]
    gate = length_gate(a_session() + [CountedLap(11, frames)])
    assert gate.dropped == []
    assert len(gate.kept) == 11


# ---------------------------------------------------------------- the note

def test_the_exclusion_is_declared_and_names_the_laps():
    """An exclusion nobody is told about is worse than no exclusion."""
    gate = length_gate(a_session() + [a_lap(11, 8000.0), a_lap(12, 150.0)])
    note = gate.as_note()
    assert note is not None
    assert "11" in note and "12" in note
    assert "fixed distance range" in note
    # And it says the laps themselves are untouched - only the corners.
    assert "lap times are unaffected" in note


def test_nothing_dropped_means_nothing_said():
    assert length_gate(a_session()).as_note() is None


# --------------------------------------------------------- and it is applied

def test_the_aggregate_actually_excludes_them():
    """The gate is worthless if `aggregate_corners` does not apply it."""
    model = a_model()
    corner = model.corners[0]
    good = [a_lap(n, 5000.0) for n in range(1, 11)]
    # A lap twice the length: its window falls on a different piece of road.
    bad = a_lap(11, 10_000.0)
    with_bad = aggregate_corners(model, good + [bad])
    without = aggregate_corners(model, good)
    assert with_bad and without
    by_id = {c["id"]: c for c in with_bad}
    assert by_id[corner.id]["samples"] == \
        {c["id"]: c for c in without}[corner.id]["samples"]
