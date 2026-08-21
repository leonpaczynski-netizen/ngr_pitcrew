"""Closing the loop the engineer opens every time he asks for a saving.

He says *"Short-shift 450."* and then never comes back. A real engineer returns
two or three laps later and says whether it worked - and if it did not, the
shortfall the instruction was meant to cover is still there, and the driver
needs to know while he can still box.

**The case this was built from is a real race.** On 19 Aug the engineer asked
for a short-shift on lap 14. The burn moved from 5.478 L to 5.422 L - **1.0%,
against a detection floor of 0.9%** - which is at the floor and
indistinguishable from nothing, set against a measured short-shift effect of
21.6%. He did not save. Nothing told him.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.race.expectations import ExpectationTracker


@dataclass
class Lap:
    lap_num: int
    lap_time_ms: int
    fuel_used: float
    is_pit_lap: bool = False
    is_out_lap: bool = False
    short_shift_rpm: float | None = None


def tracker(burns: list[tuple[int, float]], *, saving_from: int | None = None):
    """Feed laps as (lap number, litres), all at the same clean lap time."""
    out = ExpectationTracker()
    for lap_num, fuel in burns:
        out.note_lap(Lap(
            lap_num=lap_num, lap_time_ms=110_000, fuel_used=fuel,
            short_shift_rpm=(450.0 if saving_from is not None
                             and lap_num > saving_from else None)))
    return out


def test_a_real_saving_is_reported_as_working():
    before = [(n, 6.20) for n in range(2, 10)]
    after = [(n, 4.85) for n in range(10, 16)]
    got = tracker(before + after, saving_from=9).saving_response(9)
    assert got is not None and got.saved
    assert "That's working" in got.call() and "22 percent down" in got.call()


def test_the_race_that_prompted_this_reads_as_not_enough():
    """19 Aug: instructed on lap 14, burn 5.478 -> 5.422. At the floor."""
    before = [(n, 5.478) for n in range(2, 14)]
    after = [(n, 5.422 + (0.06 if n % 2 else -0.06)) for n in range(15, 26)]
    got = tracker(before + after, saving_from=14).saving_response(14)
    assert got is not None
    assert abs(got.change) < 0.03, "a 1% move is not a saving"
    assert not got.saved


def test_a_change_below_the_floor_says_it_cannot_be_resolved():
    """**Three answers, never two.** A difference smaller than the detection
    floor is not a small effect - it is no measurement, and saying "you did
    not save" would be a claim the data cannot support."""
    before = [(n, 6.00) for n in range(2, 10)]
    after = [(n, 6.00 + (0.5 if n % 2 else -0.5)) for n in range(10, 16)]
    got = tracker(before + after, saving_from=9).saving_response(9)
    assert got is not None and not got.measurable
    assert "can't resolve a change that small" in got.call()


def test_it_waits_for_enough_laps_after_the_instruction():
    """One lap is not an answer. Silence until it is."""
    burns = [(n, 6.0) for n in range(2, 10)] + [(10, 5.0)]
    assert tracker(burns, saving_from=9).saving_response(9) is None


def test_it_needs_something_to_compare_against():
    burns = [(2, 6.0)] + [(n, 5.0) for n in range(3, 8)]
    assert tracker(burns, saving_from=2).saving_response(2) is None


def test_the_saving_laps_are_measured_and_still_kept_out_of_the_plans_burn():
    """**Both at once, and that is the point.** A saving lap is evidence about
    the instruction, not about the car, so it must never reach the burn the
    plan is costed on - a trailing window that admitted two of them read 12%
    under the real rate. Here it is exactly what is being measured.
    """
    burns = [(n, 6.0) for n in range(2, 10)] + [(n, 4.5) for n in range(10, 16)]
    got = tracker(burns, saving_from=9)

    assert got.saving_response(9).saved, "the saving laps were not measured"
    current = got.current()
    assert current.fuel_per_lap_l is not None
    assert abs(current.fuel_per_lap_l - 6.0) < 0.2, (
        "saving laps contaminated the burn the plan is costed on")


def test_a_burn_that_went_up_is_not_a_saving():
    before = [(n, 5.0) for n in range(2, 10)]
    after = [(n, 6.5) for n in range(10, 16)]
    got = tracker(before + after, saving_from=9).saving_response(9)
    assert got is not None and got.measurable and not got.saved
    assert "Not enough" in got.call()
