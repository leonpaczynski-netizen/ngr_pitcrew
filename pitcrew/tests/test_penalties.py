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


# ------------------------ a corner the model is missing (critic pass 6)

def _found(at_m):
    from pitcrew.analysis.penalties import Penalty

    return [Penalty(at_m=at_m, brake_s=0.9, speed_from_kph=250.0,
                    speed_to_kph=190.0, lost_s=1.5)]


def test_a_place_braked_on_every_lap_is_the_road():
    """A corner missing from an auto-segment model brakes on every lap. The
    fourth consecutive lap retires it and hands the first three back - a
    guard that could not retire its own reading is CLAUDE.md rule 10."""
    ledger = RoadNotPenalty()
    for lap in (4, 5, 6):
        verdict = ledger.filter(lap, _found(5200.0 + lap))
        assert len(verdict.kept) == 1 and verdict.give_back == ()
    verdict = ledger.filter(7, _found(5210.0))
    assert verdict.kept == ()
    assert verdict.give_back == (4, 5, 6), "the run goes back into the pace"
    assert ledger.retired() == (5204.0,)
    assert any("corner the model is missing" in note
               for note in verdict.notes)
    # And it stays retired while it keeps being braked.
    for lap in range(8, 12):
        assert ledger.filter(lap, _found(5205.0)).kept == ()


def test_the_retirement_can_itself_be_retired():
    """Rule 10, both halves: a place that then runs four laps with nothing
    flagged is not braked every lap, so it was never a corner."""
    ledger = RoadNotPenalty()
    for lap in (1, 2, 3, 4):
        ledger.filter(lap, _found(5200.0))
    assert ledger.retired() == (5200.0,)
    for lap in (5, 6, 7):
        assert ledger.filter(lap, []).kept == ()
        assert ledger.retired() == (5200.0,), "three clean laps is not four"
    verdict = ledger.filter(8, [])
    assert ledger.retired() == ()
    assert any("it is not a corner" in note for note in verdict.notes)
    assert len(ledger.filter(9, _found(5200.0)).kept) == 1


def test_two_penalties_a_session_at_one_place_are_both_kept():
    """Daytona, 4 Sep: sessions 121, 124 and 125 each carry two at 5,200 m,
    on laps 3 and 6, 2 and 6, and 6 and 8 - and session 114 carries two on
    laps 5 and 6, CONSECUTIVELY. That pair is why the run is four and not
    two: a penalty is served on a lap and a corner is there on all of them,
    but two in a row is a thing this driver has actually done."""
    for laps in ((3, 6), (2, 6), (6, 8), (5, 6)):
        ledger = RoadNotPenalty()
        for lap in laps:
            verdict = ledger.filter(lap, _found(5198.0 + lap))
            assert len(verdict.kept) == 1 and verdict.give_back == ()


def test_the_daytona_race_that_alternated_is_all_kept():
    """Session 118, 3 Sep: flagged on laps 2, 4, 6, 8 and 10 of ten. The
    frames say the odd laps carry no brake at all through 5,100-5,400 m at a
    flat 269 km/h, so it is not a corner - and the run never reaches two."""
    ledger = RoadNotPenalty()
    kept = 0
    for lap in range(1, 11):
        kept += len(ledger.filter(lap, _found(5215.0) if lap % 2 == 0
                                  else []).kept)
    assert kept == 5
    assert ledger.retired() == ()


def test_a_penalty_somewhere_else_is_its_own_place():
    """Two different stretches of road do not retire each other."""
    ledger = RoadNotPenalty()
    assert len(ledger.filter(4, _found(5200.0)).kept) == 1
    verdict = ledger.filter(5, _found(1200.0))
    assert len(verdict.kept) == 1 and verdict.give_back == ()
    assert ledger.retired() == ()


def test_a_lap_that_could_not_be_looked_at_breaks_the_run():
    """`None` is a lap with no frames, or a pit lap, or one the detector
    stood down on. It is not evidence that the place was braked, so it
    cannot complete a run - the same argument `GapTrend._window` makes about
    fitting a line through a hole in the readings, and the safe direction:
    a hole delays a retirement, it never causes one."""
    ledger = RoadNotPenalty()
    for lap in (1, 2, 3):
        ledger.filter(lap, _found(5200.0))
    assert ledger.filter(4, None) == Verdict((), (), ())
    assert ledger.retired() == (), "an unlooked-at lap did not extend the run"
    verdict = ledger.filter(5, _found(5200.0))
    assert len(verdict.kept) == 1, "and it did not complete the run either"
    assert ledger.retired() == ()


def test_nothing_found_is_nothing_retired():
    ledger = RoadNotPenalty()
    assert ledger.filter(4, []) == Verdict((), (), ())
    assert ledger.retired() == ()
