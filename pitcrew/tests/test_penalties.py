"""Track-limit penalties served, read off the frames (plan 1.11, G27).

Verified against the archive with `tools/find_penalties.py`: the six laps the
driver named from the 4 Sep 2026 Daytona A/B runs (sessions 121 laps 3 and
6, 122 lap 5, 123 lap 4, 124 laps 2 and 6) are found at 5,194-5,218 m, and
the Bus Stop brake at 3,650-3,720 m on every lap of every session is not -
nor is anything in the twenty-lap race that followed. That run is not a
test because it needs the live file; this file holds the shape of it.
"""
from __future__ import annotations

from pitcrew.analysis.penalties import (APPROACH_M, MAX_LAT_G, RoadNotPenalty,
                                        Verdict, read_rows)

# Daytona's model: T5 (the Bus Stop) starts at 3,775.8 m.
CORNERS = [{"id": "T1", "start_m": 394.8, "end_m": 496.9},
           {"id": "T5", "start_m": 3775.8, "end_m": 3950.8}]


def _lap(*, brakes, length_m=5692.5, hz=60, lat_g=0.1):
    """Frames at 60 Hz round the lap at 250 km/h, with hard brakes at the
    given (start_m, seconds, speed_to) - the car slows through the brake and
    recovers over the next few seconds."""
    frames = []
    v = 250.0
    m = 0.0
    t = 0
    pending = sorted(brakes)
    braking_until = None
    target = None
    while m < length_m:
        brake = 0.0
        if pending and m >= pending[0][0] and braking_until is None:
            _, secs, speed_to = pending.pop(0)
            braking_until = t + int(secs * hz)
            target = speed_to
        if braking_until is not None:
            if t < braking_until:
                brake = 100.0
                v = max(target, v - (250.0 - target) / (braking_until - t + 1))
            else:
                braking_until = None
        elif v < 250.0:
            v = min(250.0, v + 0.8)          # recovering
        frames.append({"lap_distance_m": m, "speed_kph": v,
                       "brake_pct": brake, "lat_g": lat_g})
        m += v / 3.6 / hz
        t += 1
    return frames


def test_a_brake_at_speed_on_the_banking_is_a_penalty():
    served = read_rows(_lap(brakes=[(5200.0, 0.9, 195.0)]), CORNERS)
    assert served is not None and len(served) == 1
    p = served[0]
    assert 5190 <= p.at_m <= 5230
    assert 245.0 <= p.speed_from_kph <= 250.0 and p.speed_to_kph == 195.0
    assert 0.8 <= p.brake_s <= 1.0
    assert p.lost_s > 0.2, "derived, and it is not nothing"


def test_the_bus_stop_brake_is_a_corner_not_a_penalty():
    """The same shape of brake 100 m before T5's start is the corner."""
    served = read_rows(_lap(brakes=[(3775.8 - 100.0, 0.9, 120.0)]), CORNERS)
    assert served == []


def test_the_approach_window_is_the_line():
    just_inside = 3775.8 - APPROACH_M + 5.0
    just_outside = 3775.8 - APPROACH_M - 60.0
    assert read_rows(_lap(brakes=[(just_inside, 0.9, 150.0)]), CORNERS) == []
    assert len(read_rows(_lap(brakes=[(just_outside, 0.9, 150.0)]),
                         CORNERS)) == 1


def test_a_cornering_brake_is_not_a_penalty():
    """Lateral g above the bound means the car is turning: not a zone."""
    frames = _lap(brakes=[(5200.0, 0.9, 195.0)], lat_g=MAX_LAT_G + 0.3)
    assert read_rows(frames, CORNERS) == []


def test_a_dab_is_not_a_penalty():
    assert read_rows(_lap(brakes=[(5200.0, 0.2, 230.0)]), CORNERS) == []


def test_no_frames_is_none_not_zero():
    assert read_rows([], CORNERS) is None
    assert read_rows(None, CORNERS) is None


def test_no_corner_model_is_still_readable_but_the_tool_refuses():
    """With no model every brake on a straight is a candidate; the module
    reads it, and `tools/find_penalties.py` refuses to run without one."""
    served = read_rows(_lap(brakes=[(5200.0, 0.9, 195.0)]), [])
    assert len(served) == 1


# ------------------------ a corner the model is missing (critic pass 7)

def _found(at_m):
    from pitcrew.analysis.penalties import Penalty

    return [Penalty(at_m=at_m, brake_s=0.9, speed_from_kph=250.0,
                    speed_to_kph=190.0, lost_s=1.5)]


def test_a_place_braked_on_every_lap_is_the_road():
    """Yas Marina, session 44 (a RACE): 3,470 m sits in a 1.6 km gap between
    T4 and T5, every one of the fifteen laps brakes 83-100% there, and it was
    flagged on ten of them with a run of nine. The share of laps that BRAKE
    there is what says it is a corner; the share flagged says nothing."""
    ledger = RoadNotPenalty()
    # Laps 2 and 3 brake there and are not flagged - which is already
    # evidence, and is why the first flag on lap 4 is the only one spoken.
    for lap in (2, 3):
        assert ledger.filter(lap, [], braked=[3470.0]).kept == ()
    verdict = ledger.filter(4, _found(3467.0), braked=[3467.0])
    assert len(verdict.kept) == 1, "three laps is not yet an answer"
    verdict = ledger.filter(5, _found(3471.0), braked=[3471.0])
    assert verdict.kept == (), "the fourth lap settles it"
    assert [(w.lap, w.served, w.lost_s) for w in verdict.give_back] \
        == [(4, 0, None)]
    assert ledger.retired() == (3470.0,)
    for lap in range(6, 16):
        assert ledger.filter(lap, _found(3480.0), braked=[3480.0]).kept == ()


def test_a_withdrawal_keeps_the_other_penalty_on_the_same_lap():
    """Critic pass 7's blocker, off session 65: laps 2, 3 and 4 each carry a
    flag at 2,281 m AND one at 6,582 m. Zeroing the lap when one place is
    withdrawn writes "looked at and clean" over a reading that stands."""
    from pitcrew.analysis.penalties import Penalty

    ledger = RoadNotPenalty()
    corner, penalty = 6582.0, 2281.0
    for lap in (2, 3, 4):
        found = [Penalty(corner, 0.9, 250.0, 190.0, 2.0),
                 Penalty(penalty, 0.9, 250.0, 190.0, 1.5)]
        assert len(ledger.filter(lap, found,
                                 braked=[corner, penalty]).kept) == 2
    # Lap 5 brakes at the corner only: four laps, four brakes there.
    verdict = ledger.filter(5, [Penalty(corner, 0.9, 250.0, 190.0, 2.0)],
                            braked=[corner])
    assert verdict.kept == ()
    assert [(w.lap, w.served, w.lost_s) for w in verdict.give_back] \
        == [(2, 1, 1.5), (3, 1, 1.5), (4, 1, 1.5)]
    assert ledger.retired() == (corner,)


def test_a_penalty_place_the_other_laps_do_not_brake_is_kept():
    """Daytona session 118, the 3 Sep race: flagged on laps 2, 4, 6, 8 and
    10, and the odd laps carry NO brake at all there at a flat 269 km/h.
    Braked on 5 of 9 - a corner is braked on all of them."""
    ledger = RoadNotPenalty()
    kept = 0
    for lap in range(2, 11):
        flagged = lap % 2 == 0
        kept += len(ledger.filter(lap, _found(5215.0) if flagged else [],
                                  braked=[5215.0] if flagged else []).kept)
    assert kept == 5
    assert ledger.retired() == ()


def test_two_penalties_a_session_at_one_place_are_both_kept():
    """Daytona, 4 Sep: sessions 121, 124 and 125 each carry two at 5,200 m,
    and session 114 carries two on laps 5 and 6 CONSECUTIVELY - which is why
    a run of consecutive laps cannot be the test."""
    for laps in ((3, 6), (2, 6), (6, 8), (5, 6)):
        ledger = RoadNotPenalty()
        for lap in range(2, 10):
            flagged = lap in laps
            verdict = ledger.filter(lap, _found(5198.0) if flagged else [],
                                    braked=[5198.0] if flagged else [])
            assert len(verdict.kept) == (1 if flagged else 0)
            assert verdict.give_back == ()


def test_the_verdict_is_never_latched():
    """CLAUDE.md rule 10 by construction: the share is recomputed every lap,
    so a place that stops being braked stops being a corner."""
    ledger = RoadNotPenalty()
    for lap in (2, 3, 4, 5):
        ledger.filter(lap, _found(5200.0), braked=[5200.0])
    assert ledger.retired() == (5200.0,)
    for lap in range(6, 12):
        ledger.filter(lap, [], braked=[])
    assert ledger.retired() == (), "4 of 10 is not a corner"
    assert len(ledger.filter(12, _found(5200.0), braked=[5200.0]).kept) == 1


def test_a_modelled_corner_braked_every_lap_is_not_called_missing():
    """`retired()` names corners to ADD to the model, so it may only name
    places a flag was raised at - the Bus Stop is braked on every lap and is
    excluded by `APPROACH_M`, and listing it buries the one that matters."""
    ledger = RoadNotPenalty()
    for lap in range(2, 8):
        ledger.filter(lap, [], braked=[3700.0])
    assert ledger.retired() == ()


def test_a_penalty_somewhere_else_is_its_own_place():
    ledger = RoadNotPenalty()
    assert len(ledger.filter(2, _found(5200.0), braked=[5200.0]).kept) == 1
    verdict = ledger.filter(3, _found(1200.0), braked=[1200.0])
    assert len(verdict.kept) == 1 and verdict.give_back == ()
    assert ledger.retired() == ()


def test_a_lap_that_could_not_be_looked_at_is_not_counted():
    """`None` is a lap with no frames, a pit lap, or one the detector stood
    down on. It is not evidence that the place was braked OR that it was
    not, so it does not move the share either way (CLAUDE.md rule 3)."""
    ledger = RoadNotPenalty()
    for lap in (2, 3, 4):
        ledger.filter(lap, _found(5200.0), braked=[5200.0])
    assert ledger.filter(5, None, braked=[5200.0]) == Verdict((), (), ())
    assert ledger.retired() == (), "three looked-at laps is not four"
    assert ledger.filter(6, _found(5200.0), braked=[5200.0]).kept == ()
    assert ledger.retired() == (5200.0,)


def test_nothing_found_is_nothing_retired():
    ledger = RoadNotPenalty()
    assert ledger.filter(4, []) == Verdict((), (), ())
    assert ledger.retired() == ()


def test_the_accepts_are_written_down_as_well_as_the_refusals():
    """CLAUDE.md rule 10: the Fuji ratchet was invisible for a whole race
    because the number setting the bar never appeared in the log."""
    ledger = RoadNotPenalty()
    verdict = ledger.filter(2, _found(5200.0), braked=[5200.0])
    assert any("kept" in note and "braked on 1 of 1 laps" in note
               for note in verdict.notes)


# ------------------------------------------------- what was braked, and where

def test_braked_at_reads_every_hard_brake_whatever_the_reason():
    """No speed bound, no lateral-g bound, no corner window - the question
    is "is this stretch of road braked for", and each of those filters
    answers a different one."""
    from pitcrew.analysis.penalties import braked_at

    frames = _lap(brakes=[(1000.0, 0.9, 120.0), (3675.8, 0.9, 120.0),
                          (5200.0, 0.9, 195.0)], lat_g=1.4)
    places = braked_at(frames)
    assert len(places) == 3
    assert read_rows(frames, CORNERS) == [], "and none of them is a penalty"


def test_a_dab_is_not_a_braked_place_either():
    from pitcrew.analysis.penalties import braked_at

    assert braked_at(_lap(brakes=[(5200.0, 0.2, 230.0)])) == []
    assert braked_at([]) == []
    assert braked_at(None) == []
