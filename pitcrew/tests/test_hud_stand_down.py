"""A reader that cannot see the gauge says so once and stops.

Fuji, 24 Aug 2026: **553 attempts after the green and not one accepted.** Almost
every one wrote a warning, so half a thousand log lines said the same thing —
and the driver had been told in the brief that the gauge was being watched.

`MAX_CONSECUTIVE_FAILURES` covers the source dying: OBS shut, the projector
closed. Nothing covered the case where the source is perfectly healthy and the
gauge simply is not in what it returns. **That is the VR case, and it is now the
normal case** — he races in VR, where GT7 draws the HUD on the car's dashboard
in 3D and a fixed rectangle cannot hold it.

The distinction that makes this safe: **in VR the gauge is intermittent, not
absent.** At Road Atlanta it answered 6 crossings of 22, because a sample only
needs the driver to be looking forward. So any accepted reading resets the
timer, and only a run of pure nothing for BLIND_WINDOW_S stands the reader down.
"""
from __future__ import annotations

import logging

import pytest

from pitcrew.telemetry.hud import (
    BLIND_WINDOW_S,
    LiveWearSampler,
    Reading,
)

from .test_hud_wear import FakeSource


def a_sampler(status=None):
    return LiveWearSampler(FakeSource((None, "unused")),
                           lambda lap, wear: None, on_status=status)


def nothing_for(sampler, elapsed_s: float) -> None:
    """Simulate a continuous gap of `elapsed_s` seconds with no gauge reading.

    Two calls: one at t=0 (starts the timer) and one at t=elapsed_s (triggers
    the check).  Passing _now gives us deterministic time control without
    patching time.monotonic().
    """
    sampler._saw_nothing(_now=0.0)
    sampler._saw_nothing(_now=elapsed_s)


def a_reading(at: float = 0.30):
    return Reading({"fl": at, "fr": at, "rl": at, "rr": at})


# ------------------------------------------------------------ it stands down

def test_a_run_of_nothing_stands_the_reader_down():
    sampler = a_sampler()

    nothing_for(sampler, BLIND_WINDOW_S + 1.0)

    assert sampler.stood_down is True


def test_it_holds_on_until_the_cap():
    """Standing down early throws away a gauge that is merely occluded."""
    sampler = a_sampler()

    nothing_for(sampler, BLIND_WINDOW_S - 1.0)

    assert sampler.stood_down is False


def test_it_says_so_once_and_names_the_replay():
    """"I cannot see it" is not the end of the sentence. The gauge is the only
    ground truth for wear that exists, and in VR it can still be read off a
    chase-view replay afterwards."""
    logger = logging.getLogger("pitcrew.hud")
    records: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    logger.addHandler(handler)
    try:
        sampler = a_sampler()
        nothing_for(sampler, BLIND_WINDOW_S + 1.0)
        # Extra calls after stood-down must not add more log lines.
        nothing_for(sampler, BLIND_WINDOW_S + 100.0)
    finally:
        logger.removeHandler(handler)

    said = [line for line in records if "not visible this session" in line]
    assert len(said) == 1, "one fact, said once - not once per sample"
    assert "read_hud_wear" in said[0], "tell him where the number comes from"
    assert "VR" in said[0]


def test_the_driver_is_told_through_the_status_channel():
    seen: list[Reading] = []
    sampler = a_sampler(status=seen.append)

    nothing_for(sampler, BLIND_WINDOW_S + 1.0)

    assert seen, "silence from a perception layer reads as nothing to report"
    assert "replay" in seen[-1].reason


# --------------------------------------------- an intermittent gauge survives

def test_one_good_reading_clears_the_timer():
    """**The Road Atlanta case: 6 crossings of 22 answered.** A timer a partial
    success could not clear would throw those six away."""
    sampler = a_sampler()

    nothing_for(sampler, BLIND_WINDOW_S - 1.0)
    assert sampler._keep(0.0, a_reading()) is True
    # Timer reset by the accept — now the full window must pass again.
    nothing_for(sampler, BLIND_WINDOW_S - 1.0)

    assert sampler.stood_down is False, (
        "an intermittent gauge is not a blind one")


def test_a_new_session_starts_looking_again():
    """The sampler outlives the session. A race that went blind must not make
    the next practice blind too."""
    sampler = a_sampler()
    nothing_for(sampler, BLIND_WINDOW_S + 1.0)
    assert sampler.stood_down is True

    sampler.new_session()

    assert sampler.stood_down is False
    assert sampler._nothing_seen == 0
    assert sampler._nothing_since_s is None


def test_standing_down_stops_the_free_run_sampling():
    """The point is not only the log - it is that the grabs stop. At Fuji they
    did not, for 53 minutes."""
    source = FakeSource((None, "unused"))
    sampler = LiveWearSampler(source, lambda lap, wear: None, interval_s=0.01)
    sampler.stood_down = True

    sampler._free_run()

    assert source.calls == 0


def test_the_cap_is_far_past_any_ordinary_occlusion():
    """A long left-hander or a menu must never reach it."""
    assert BLIND_WINDOW_S >= 300.0, (
        "10 minutes: a typical race is 20-45 min and the longest plausible "
        "occlusion is a pit stop + menu (< 2 min)")


# ---------------------------------------- rate-independence: same outcome at
# 2 s, 0.5 s and and 0.2 s intervals

@pytest.mark.parametrize("interval_s", [2.0, 0.5, 0.2])
def test_stand_down_fires_at_the_same_wall_time_at_every_sample_rate(
        interval_s):
    """The threshold is wall time, not sample count, so changing the interval
    must not change when standing-down occurs."""
    sampler = a_sampler()
    # Just under the window — must not stand down regardless of rate.
    t = 0.0
    while t < BLIND_WINDOW_S - interval_s:
        sampler._saw_nothing(_now=t)
        t += interval_s
    assert sampler.stood_down is False

    # One more step takes us past the window.
    sampler._saw_nothing(_now=t + interval_s)
    assert sampler.stood_down is True


@pytest.mark.parametrize("interval_s", [2.0, 0.5, 0.2])
def test_reseed_fires_at_the_same_wall_time_at_every_sample_rate(interval_s):
    """REFUSALS_WINDOW_S is a wall-clock duration, not a sample count."""
    from pitcrew.telemetry.hud import REFUSALS_WINDOW_S

    sampler = a_sampler()
    # Seed the sampler.
    assert sampler._keep(0.0, a_reading(0.60))

    # Refuse for just under the window — baseline must survive.
    t = interval_s
    while t < REFUSALS_WINDOW_S - interval_s:
        sampler._keep(t, a_reading(0.30))
        t += interval_s
    assert sampler.series, "baseline discarded too early"

    # One refusal past the window — baseline drops.
    sampler._keep(REFUSALS_WINDOW_S + interval_s, a_reading(0.30))
    assert sampler.series == [], "baseline must be discarded at the window"
