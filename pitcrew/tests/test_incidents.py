"""Laps with an off or a spin in them.

Validated against the capture set by taking the seventeen laps the driver
struck by hand, un-striking them, and asking the detector cold:

* nine were lap 1 of a session, which the out-lap rule now names — see
  `test_out_laps`;
* seven were genuine incidents and all seven are found here;
* one, session 1 lap 2, lost 2.6 s and is deliberately below the threshold.

It also found four he had not struck and should have, including a 12.8 s loss
where the car came to a complete stop.
"""
from __future__ import annotations

import pytest

from pitcrew.analysis.incidents import (
    CRAWL,
    Evidence,
    OFF_TRACK,
    SPIN,
    find_incidents,
    read_evidence,
)
from pitcrew.analysis.session import LapInput

HZ = 60.0


def frames(*, speeds=None, surfaces=None, yaws=None, count=6000) -> list[dict]:
    """A lap of frames, flat out on tarmac unless told otherwise."""
    out = []
    for index in range(count):
        speed = speeds[index] if speeds and index < len(speeds) else 180.0
        surface = surfaces[index] if surfaces and index < len(surfaces) else "T"
        yaw = yaws[index] if yaws and index < len(yaws) else 0.05
        out.append({"speed_kph": speed, "yaw_rate": yaw,
                    "surf_fl": surface, "surf_fr": surface,
                    "surf_rl": surface, "surf_rr": surface})
    return out


def with_span(base: list, value, at_s: float, length_s: float) -> list:
    start = int(at_s * HZ)
    return base[:start] + [value] * int(length_s * HZ) + base[start:]


def a_lap(lap_num: int, lap_ms: int, lap_frames=None, **overrides) -> LapInput:
    fields = dict(lap_num=lap_num, lap_time_ms=lap_ms,
                  fuel_start=100.0 - 6.0 * (lap_num - 1),
                  fuel_end=100.0 - 6.0 * lap_num,
                  compound="RH", session_id=1, practice_mode="time-trial",
                  frames=lap_frames)
    fields.update(overrides)
    return LapInput(**fields)


def judge(laps):
    return find_incidents(
        laps, lambda lap: (read_evidence(lap.frames) if lap.frames
                           else Evidence()))


def a_stint(times, frames_by_lap=None):
    frames_by_lap = frames_by_lap or {}
    return [a_lap(n, ms, frames_by_lap.get(n, frames()))
            for n, ms in enumerate(times, start=1)]


# ------------------------------------------------------------ what it catches

def test_a_car_that_came_to_a_stop_mid_lap_is_an_incident():
    """Session 19 lap 9: +13.3 s, and he had not struck it."""
    stopped = frames(speeds=with_span([180.0] * 6000, 0.0, 40.0, 2.0))
    found = judge(a_stint([109_000, 109_000, 109_000, 122_400, 109_000],
                          {4: stopped}))
    assert set(found) == {4}
    assert CRAWL in found[4].signals
    assert "came to a stop" in found[4].describe()


def test_a_long_excursion_is_an_incident():
    """Session 9 lap 12: 6.8 s off the road and 28 s lost."""
    off = frames(surfaces=with_span(["T"] * 6000, "G", 30.0, 6.8))
    found = judge(a_stint([109_000, 109_000, 109_000, 137_900, 109_000],
                          {4: off}))
    assert OFF_TRACK in found[4].signals
    assert "6.8 s off the road" in found[4].describe()


def test_a_spin_that_never_left_the_tarmac_is_an_incident():
    """Session 9 lap 6: 0.2 s off-track in the whole lap, and a 14 s loss.
    The surface channel cannot see it; the rotation can.

    2.5 rad/s, not the 1.7 this fixture used to carry. The detector ran on the
    roll axis, so the number never had to be a plausible yaw rate. Against a
    reconstructed yaw channel session 9 lap 6 sustains 2.48 rad/s and the 113
    laps that lost no time top out at 1.83, which is why the threshold moved
    into the band between them.
    """
    spun = frames(speeds=with_span([180.0] * 6000, 40.0, 40.0, 1.0),
                  yaws=with_span([0.05] * 6000, 2.5, 40.0, 1.0))
    found = judge(a_stint([109_000, 109_000, 109_000, 123_300, 109_000],
                          {4: spun}))
    assert SPIN in found[4].signals


# ------------------------------------------------------- what it leaves alone

def test_running_the_kerbs_hard_on_a_quick_lap_is_not_an_incident():
    """A corroborating signal on its own is a driver getting away with it.

    This is the failure the two-signal rule exists to prevent: a clean lap of
    Monza spends one to two seconds with two wheels off tarmac and kerb, and
    thresholding that alone flags 70 laps in 132.
    """
    off = frames(surfaces=with_span(["T"] * 6000, "G", 30.0, 4.0))
    assert judge(a_stint([109_000, 109_000, 108_500, 109_000], {3: off})) == {}


def test_losing_time_with_nothing_to_show_for_it_is_not_an_incident():
    """Traffic, a lift, a cold set. Slow is not the same as something
    happening, and the app must not invent a cause for it."""
    assert judge(a_stint([109_000, 109_000, 116_000, 109_000])) == {}


def test_the_grid_is_not_an_incident():
    """A lobby session opens with up to eighty seconds stationary in the box.
    That is where the car starts, not where it stopped."""
    grid = frames(speeds=[0.0] * 4800 + [180.0] * 6000, count=0)
    found = judge(a_stint([113_500, 109_000, 109_000, 109_000], {1: grid}))
    assert found == {}


def test_a_lap_is_judged_against_its_own_run():
    """A stint on old tyres is slower than one on new, and neither fact is an
    incident. Fitted across both, every lap of the second stint reads as a
    loss."""
    stopped = frames(speeds=with_span([180.0] * 6000, 0.0, 40.0, 2.0))
    fresh = [a_lap(n, 109_000) for n in range(1, 5)]
    # The tank goes back up at lap 5 and then falls again, so laps 5-9 are one
    # new run rather than five runs of one lap.
    worn = [a_lap(n, 115_000, frames(),
                  fuel_start=100.0 - 6.0 * (n - 5),
                  fuel_end=100.0 - 6.0 * (n - 4))
            for n in range(5, 10)]
    assert judge(fresh + worn) == {}
    worn[2] = a_lap(7, 128_000, stopped, fuel_start=88.0, fuel_end=82.0)
    assert set(judge(fresh + worn)) == {7}


def test_half_a_stint_gives_no_verdict_at_all():
    """The median of two laps is not a reference, and half a stint is exactly
    where a confident wrong answer would do most damage."""
    stopped = frames(speeds=with_span([180.0] * 6000, 0.0, 40.0, 2.0))
    assert judge(a_stint([109_000, 128_000], {2: stopped})) == {}


def test_a_lap_with_no_frames_is_never_an_incident():
    """Not measured is not the same as nothing happened."""
    laps = a_stint([109_000, 109_000, 109_000, 128_000, 109_000])
    laps[3] = a_lap(4, 128_000, None)
    assert judge(laps) == {}


def test_an_out_lap_is_not_judged_for_losing_time_it_is_meant_to_lose():
    stopped = frames(speeds=with_span([180.0] * 6000, 0.0, 40.0, 2.0))
    laps = a_stint([124_000, 109_000, 109_000, 109_000], {1: stopped})
    laps = [a_lap(lap.lap_num, lap.lap_time_ms, lap.frames,
                  practice_mode="lobby") for lap in laps]
    assert judge(laps) == {}


# ------------------------------------------------------------- the two verdicts

def test_an_incident_leaves_pace_and_stays_in_the_diagnosis():
    """Both halves of what he asked for: out of strategy, in for setup."""
    lap = a_lap(3, 128_000, incident=True)
    assert lap.counted is False
    assert lap.diagnostic is True


def test_the_evidence_is_reported_whether_or_not_it_crossed_a_threshold():
    """`derived` carries what was seen, not just the verdict, so retuning a
    threshold reads as a change in the detector."""
    off = frames(surfaces=with_span(["T"] * 6000, "G", 30.0, 1.2))
    seen = read_evidence(off)
    assert seen.off_track_s == pytest.approx(1.2, abs=0.05)
    assert seen.signals == ()


def test_no_surface_channel_reads_as_not_available_never_as_no_excursions():
    """Surface type arrives only in the `~` and `C` packets, and the listener
    falls back to `A` after `FORMAT_PATIENCE_S` without a decode. Every lap of
    that session then computed `off_track_s` as 0.0 and stored and exported it
    as a measurement that the car never left the road — which is the exact
    confusion `meta.packet` exists to prevent (§3.1).
    """
    blind = [{"speed_kph": 180.0, "yaw_rate": 0.05} for _ in range(6000)]
    seen = read_evidence(blind)
    assert seen.off_track_s is None
    assert seen.crawl_s == 0.0          # the speed channel was there
    assert seen.signals == ()


def test_stored_evidence_keeps_each_columns_own_null():
    """And the lap rack's rows have no `frames` attribute at all — a lap with
    null evidence used to raise `AttributeError` inside `load_active_event`,
    which is the app dying on launch rather than a bad number."""
    from pitcrew.analysis.incidents import stored_or_read

    class Row:
        crawl_s, off_track_s, spin_s = 0.4, None, 0.0

    seen = stored_or_read(Row())
    assert (seen.crawl_s, seen.off_track_s, seen.spin_s) == (0.4, None, 0.0)

    class Blank:
        crawl_s = off_track_s = spin_s = None

    assert stored_or_read(Blank()) == Evidence()


# ------------------------------------------- time lost that nothing explains

def _captured(lap):
    """Evidence where the frames exist, `None` where they never did.

    Deliberately not `judge`'s accessor, which answers `Evidence()` for a lap
    with no frames - that reads as "measured, and nothing happened", which is
    right for asking whether a lap is an incident and wrong for asking whether
    its loss is unexplained. Not measured is not unexplained.
    """
    return read_evidence(lap.frames) if lap.frames else None


def test_an_unexplained_loss_is_reported_without_becoming_an_incident():
    """**The gap, found on session 93 lap 3.** The time-loss gate opens, the
    frames are read, nothing corroborates, and `judge` drops the lap - so it
    is counted as clean and goes into every median of its run with no trace
    that a question was ever raised. It went on to drive an 18x sector-spread
    reading that was very nearly diagnosed as a setup problem.

    Reported, never excluded: slow is not the same as something happening,
    and `test_losing_time_with_nothing_to_show_for_it_is_not_an_incident`
    still stands.
    """
    from pitcrew.analysis.incidents import unexplained_losses

    laps = a_stint([51_000, 51_000, 57_500, 51_000, 51_000])
    assert judge(laps) == {}, "it must not have become an incident"
    found = unexplained_losses(laps, _captured)
    assert [u.lap_num for u in found] == [3]
    assert found[0].lost_s > 6.0
    assert found[0].fraction > 0.10
    assert "nothing on file explains it" in found[0].describe()


def test_a_loss_that_is_small_relative_to_the_lap_is_not_reported():
    """**Absolute seconds are the wrong unit and the first attempt used
    them.** Six seconds is 5% of a 110 s Monza lap and 13% of a 51 s Red Bull
    Ring lap; traffic and a lift live in the low single percent."""
    from pitcrew.analysis.incidents import unexplained_losses

    long_lap = a_stint([110_000, 110_000, 116_000, 110_000, 110_000])
    assert unexplained_losses(long_lap, _captured) == []


def test_a_lap_with_no_frames_is_not_called_unexplained():
    """"Not measured" is not "unexplained" - the second is a claim about
    frames that exist and are silent."""
    from pitcrew.analysis.incidents import unexplained_losses

    laps = a_stint([51_000, 51_000, 51_000, 58_000, 51_000])
    laps[3] = a_lap(4, 58_000, None)
    assert unexplained_losses(laps, _captured) == []


def test_a_corroborated_lap_belongs_to_judge_and_is_not_double_reported():
    """One lap, one owner. A lap the frames DO explain is an incident and
    must not also appear as a question."""
    from pitcrew.analysis.incidents import unexplained_losses

    laps = a_stint([51_000, 51_000, 58_000, 51_000, 51_000])
    # An accessor that says lap 3's frames DO explain it. Given directly
    # rather than through synthetic frames, because what is under test is the
    # boundary between the two functions, not the reading of a trace.
    def explained(lap):
        return Evidence(crawl_s=4.0) if lap.lap_num == 3 else Evidence()

    assert 3 in find_incidents(laps, explained), "judge should own this lap"
    assert unexplained_losses(laps, explained) == [], "and own it alone"
