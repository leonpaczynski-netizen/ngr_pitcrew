"""The hold has to re-arm on the value, or it only ever works once.

Fuji, 24 Aug 2026: 31 warnings between the pit stop and the flag, alternating

    20:47:45  GT7 has counted 2 crossing(s) the app did not, app still on lap 16
    20:47:47  GT7 has counted 1 crossing(s) the app did not, app still on lap 17

...and never converging. The "2" warnings land on the exact `recorded_at` of
rows 16, 17, 18 and 19 - the instants the calls are composed - so the run-in
went out a lap early all the way to the flag:

    "4 to go"     with five to go
    "Two to go"   with three to go
    "Last lap"    with two to go
    (nothing)     on the actual last lap

The permanent +1 was CORRECT: a crossing inside GT7's pit sequence never
reaches the app. The +2 was the Qt thread not having reached LAP_COMPLETED
yet, which is exactly the transient `LAP_COUNTER_HOLD_FRAMES` exists to
swallow.

It could not. `_gt7_pending` counted frames where the two counters differed
**at all**, so once the genuine +1 had parked the discrepancy above zero the
counter sat saturated for the rest of the race - and the moment a crossing
pushed it to 2, the 2 was believed on the very next frame. The hold fired once
and was then permanently defeated by the thing it had just corrected.
"""
from __future__ import annotations

import pytest

from pitcrew.race.coordinator import (
    LAP_COUNTER_HOLD_FRAMES,
    MAX_LIVE_MISSED_LAPS,
    RaceCoordinator,
    RacePhase,
)

from .conftest import make_packet


def a_coordinator(*, app_lap: int, offset: int = 0) -> RaceCoordinator:
    """A race running, with the two counters related by `offset`."""
    race = RaceCoordinator(None)
    race.phase = RacePhase.RUNNING
    race.state.lap = app_lap
    race._gt7_offset = offset
    return race


def feed(race: RaceCoordinator, *, counted: int, frames: int) -> None:
    for _ in range(frames):
        race.note_packet(make_packet(laps_completed=counted))


# ------------------------------------------------------ the transient

def test_a_crossing_transient_is_not_believed_on_top_of_a_real_correction():
    """The Fuji sequence, exactly: a real +1, then a crossing pushing it to 2."""
    race = a_coordinator(app_lap=16)

    # A genuine dropped crossing: app on 16, GT7 says 17. Held long enough.
    feed(race, counted=17, frames=LAP_COUNTER_HOLD_FRAMES + 5)
    assert race.state.laps_dropped_seen == 1

    # Now an ordinary crossing. GT7's counter moves a few frames before the
    # app's LAP_COMPLETED lands, so the discrepancy briefly reads 2.
    feed(race, counted=18, frames=10)

    assert race.state.laps_dropped_seen == 1, (
        "the crossing transient was believed and the run-in went out a lap "
        "early for the rest of the race")


def test_the_transient_would_have_been_believed_before_the_fix():
    """Guards the mechanism rather than the symptom: a value that has not
    served its own hold must never reach `laps_dropped_seen`."""
    race = a_coordinator(app_lap=16)
    feed(race, counted=17, frames=LAP_COUNTER_HOLD_FRAMES + 5)

    # One single frame at the new value. Before the fix `_gt7_pending` was
    # already saturated and this frame alone was enough.
    feed(race, counted=18, frames=1)

    assert race.state.laps_dropped_seen == 1


def test_a_genuine_second_dropped_lap_is_still_believed():
    """The hold delays the claim; it must not refuse it. A crossing really
    missed for a whole lap has to reach the fuel arithmetic."""
    race = a_coordinator(app_lap=16)
    feed(race, counted=17, frames=LAP_COUNTER_HOLD_FRAMES + 5)

    feed(race, counted=18, frames=LAP_COUNTER_HOLD_FRAMES + 5)

    assert race.state.laps_dropped_seen == 2


def test_the_first_correction_still_works():
    """The ordinary case the detector was written for."""
    race = a_coordinator(app_lap=13)

    feed(race, counted=14, frames=LAP_COUNTER_HOLD_FRAMES + 5)

    assert race.state.laps_dropped_seen == 1


def test_agreement_withdraws_the_claim():
    """Assigned, not ratcheted - the next agreeing frame clears it."""
    race = a_coordinator(app_lap=13)
    feed(race, counted=14, frames=LAP_COUNTER_HOLD_FRAMES + 5)
    assert race.state.laps_dropped_seen == 1

    feed(race, counted=13, frames=1)

    assert race.state.laps_dropped_seen == 0


def test_a_transient_that_settles_back_leaves_the_claim_untouched():
    """The full Fuji oscillation: 1 -> 2 -> 1, repeatedly, for sixteen laps.
    The claim must sit still at 1 throughout."""
    race = a_coordinator(app_lap=16)
    feed(race, counted=17, frames=LAP_COUNTER_HOLD_FRAMES + 5)

    for lap in range(4):
        # crossing: GT7 moves first
        feed(race, counted=18 + lap, frames=8)
        assert race.state.laps_dropped_seen == 1
        # the app catches up, and the pair are back to a steady +1
        race.state.lap += 1
        feed(race, counted=18 + lap, frames=20)
        assert race.state.laps_dropped_seen == 1


def test_a_discrepancy_beyond_the_cap_is_ignored():
    race = a_coordinator(app_lap=5)

    feed(race, counted=5 + MAX_LIVE_MISSED_LAPS + 1,
         frames=LAP_COUNTER_HOLD_FRAMES + 5)

    assert race.state.laps_dropped_seen == 0
