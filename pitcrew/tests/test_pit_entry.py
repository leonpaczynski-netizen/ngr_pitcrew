"""Knowing exactly when the car went into the pits.

The driver asked for this directly - *"the engineer should know exactly when I
am in the pits"* - and suggested the 60 km/h limiter. The limiter turns out not
to be visible: across the pit laps on file the longest stretch anywhere near
60 km/h is 3.4 s with a 10 km/h spread, which is a car passing through that
speed rather than one held at it.

**What is visible is better.** GT7 takes the car over at the pit entry and
places it in the box, so the speed does not decelerate - it steps. Measured:
145.6, 227.3, 226.3 and 211.1 km/h to zero between two consecutive frames, once
per pit lap, and never a matching step outwards because the car accelerates out
of the box normally.

That is exact to the frame, where the fuel-rise signal only finds the start of
refuelling several seconds later.
"""
from __future__ import annotations

from pitcrew.telemetry.pit_detect import entered_the_pits, pit_entry_frame


def test_the_step_into_the_box_is_found():
    speeds = [200.0, 210.0, 220.0, 227.3, 0.0, 0.0, 0.0]
    assert pit_entry_frame(speeds) == 4


def test_real_braking_is_not_a_pit_entry():
    """At 60 Hz even a 3 g stop from 227 km/h sheds about half a km/h a frame.
    Anything that decelerates is the driver, not the game."""
    speeds = [227.0 - n * 0.5 for n in range(400)] + [0.0]
    assert pit_entry_frame(speeds[:-1]) is None


def test_a_normal_lap_has_no_entry():
    speeds = [80.0, 140.0, 200.0, 240.0, 180.0, 90.0, 120.0]
    assert pit_entry_frame(speeds) is None


def test_a_slow_crawl_to_a_halt_is_not_an_entry():
    """A spin, a stall or a stop on circuit reaches zero the long way."""
    speeds = [70.0, 50.0, 30.0, 15.0, 6.0, 2.0, 0.0]
    assert pit_entry_frame(speeds) is None


def test_only_the_first_entry_is_reported():
    """A lap has one pit entry. A second step would be a decode artefact."""
    speeds = [200.0, 0.0, 0.0, 190.0, 0.0]
    assert pit_entry_frame(speeds) == 1


def test_missing_samples_break_the_pair_rather_than_spanning_it():
    """A gap in the stream is not a step. Spanning one would invent an entry
    out of a dropped packet."""
    assert pit_entry_frame([200.0, None, 0.0]) is None


def test_the_live_form_answers_on_two_frames():
    assert entered_the_pits(227.3, 0.0) is True
    assert entered_the_pits(40.0, 0.0) is False
    assert entered_the_pits(227.3, 200.0) is False
    assert entered_the_pits(None, 0.0) is False
