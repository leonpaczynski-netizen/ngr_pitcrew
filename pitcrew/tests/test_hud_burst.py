"""Pit burst sampling: the sampler speeds up while any rival Visit is open.

The disc flip that reveals the departure compound lasts only 0.25-0.35 s
(measured on s188, 60fps).  At the normal hud_sample_interval_s of 2 s the
exit frame is missed almost always.  The fix: while PitWall.any_visit_open is
True, grab at BURST_INTERVAL_S (0.2 s); keep bursting for BURST_TAIL_S (3 s)
after the last visit closes; cap continuous burst at BURST_MAX_S (120 s).

Tests here cover only the burst logic — not the gauge reading, not the board
reader, and not the pass-frame path.  Those have their own suites.
"""
from __future__ import annotations

import time

import pytest

from pitcrew.telemetry.hud import (
    BURST_INTERVAL_S,
    BURST_MAX_S,
    BURST_TAIL_S,
    LiveWearSampler,
)


# ---------------------------------------------------------------------------
# A minimal wall stub: just the `any_visit_open` property
# ---------------------------------------------------------------------------

class _Wall:
    """Minimal stub that exposes `any_visit_open`."""

    def __init__(self, open_: bool = False):
        self.open_ = open_

    @property
    def any_visit_open(self) -> bool:
        return self.open_


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sampler(**kw) -> LiveWearSampler:
    kw.setdefault("source", None)
    kw.setdefault("write", lambda *a, **k: None)
    return LiveWearSampler(**kw)


# ---------------------------------------------------------------------------
# set_burst_watch wires the wall reference
# ---------------------------------------------------------------------------

def test_set_burst_watch_stores_wall():
    s = _sampler()
    wall = _Wall()
    s.set_burst_watch(wall)
    assert s._burst_wall is wall


def test_set_burst_watch_none_clears_burst():
    s = _sampler()
    s.set_burst_watch(_Wall())
    s.set_burst_watch(None)
    assert s._burst_wall is None


def test_set_burst_watch_accepts_custom_intervals():
    s = _sampler()
    s.set_burst_watch(_Wall(), burst_interval_s=0.1, burst_tail_s=5.0, burst_max_s=60.0)
    assert s._burst_interval_s == pytest.approx(0.1)
    assert s._burst_tail_s == pytest.approx(5.0)
    assert s._burst_max_s == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# _burst_in_effect: state machine
# ---------------------------------------------------------------------------

def test_no_wall_burst_never_fires():
    s = _sampler()
    assert s._burst_in_effect(time.monotonic()) is False


def test_burst_starts_when_visit_opens(caplog):
    s = _sampler()
    wall = _Wall(open_=True)
    s.set_burst_watch(wall)
    now = time.monotonic()
    with caplog.at_level("INFO", logger="pitcrew.hud"):
        result = s._burst_in_effect(now)
    assert result is True
    assert s._burst_active is True
    assert "start" in caplog.text


def test_burst_logs_start_only_once(caplog):
    s = _sampler()
    wall = _Wall(open_=True)
    s.set_burst_watch(wall)
    now = time.monotonic()
    with caplog.at_level("INFO", logger="pitcrew.hud"):
        s._burst_in_effect(now)
        s._burst_in_effect(now + 0.1)
        s._burst_in_effect(now + 0.2)
    starts = [r for r in caplog.records if "start" in r.message]
    assert len(starts) == 1, "burst start logged exactly once"


def test_burst_stays_active_during_tail(caplog):
    s = _sampler()
    wall = _Wall(open_=True)
    s.set_burst_watch(wall, burst_tail_s=3.0)
    now = time.monotonic()
    s._burst_in_effect(now)          # opens burst, last_open = now
    wall.open_ = False               # close the visit
    # Still within the tail window.
    result = s._burst_in_effect(now + 1.0)
    assert result is True


def test_burst_stops_after_tail_expires(caplog):
    s = _sampler()
    wall = _Wall(open_=True)
    s.set_burst_watch(wall, burst_tail_s=3.0)
    now = time.monotonic()
    s._burst_in_effect(now)          # opens burst
    wall.open_ = False
    # Past the tail.
    with caplog.at_level("INFO", logger="pitcrew.hud"):
        result = s._burst_in_effect(now + 10.0)
    assert result is False
    assert s._burst_active is False
    assert "stop" in caplog.text


def test_burst_logs_stop_only_once(caplog):
    s = _sampler()
    wall = _Wall(open_=True)
    s.set_burst_watch(wall, burst_tail_s=0.1)
    now = time.monotonic()
    s._burst_in_effect(now)         # opens burst
    wall.open_ = False
    with caplog.at_level("INFO", logger="pitcrew.hud"):
        s._burst_in_effect(now + 1.0)    # past tail, should log stop
        s._burst_in_effect(now + 2.0)    # already inactive, no second log
    stops = [r for r in caplog.records if "stop" in r.message]
    assert len(stops) == 1, "burst stop logged exactly once"


def test_burst_caps_at_max_s(caplog):
    s = _sampler()
    wall = _Wall(open_=True)
    s.set_burst_watch(wall, burst_max_s=10.0)
    now = time.monotonic()
    s._burst_in_effect(now)           # opens burst
    # Visit still open but we've exceeded the cap.
    with caplog.at_level("INFO", logger="pitcrew.hud"):
        result = s._burst_in_effect(now + 15.0)
    assert result is False
    assert "cap" in caplog.text


def test_burst_cap_does_not_restart_while_visit_stays_open(caplog):
    """A stuck visit must not restart burst after the cap fires — the whole
    point of the cap is to prevent indefinite burst on a visit that never
    closes."""
    s = _sampler()
    wall = _Wall(open_=True)
    s.set_burst_watch(wall, burst_max_s=10.0)
    now = time.monotonic()
    s._burst_in_effect(now)            # burst starts
    s._burst_in_effect(now + 15.0)    # cap fires, burst stops

    assert s._burst_capped is True

    # Visit still open — must NOT restart burst.
    with caplog.at_level("INFO", logger="pitcrew.hud"):
        result = s._burst_in_effect(now + 20.0)
    assert result is False, "cap must hold while visit stays open"
    assert "start" not in caplog.text


def test_burst_cap_clears_when_visit_closes(caplog):
    """The cap lifts once the visit closes so the next visit can burst
    normally."""
    s = _sampler()
    wall = _Wall(open_=True)
    s.set_burst_watch(wall, burst_max_s=10.0)
    now = time.monotonic()
    s._burst_in_effect(now)            # burst starts
    s._burst_in_effect(now + 15.0)    # cap fires
    assert s._burst_capped is True

    # Visit closes — cap must clear.
    wall.open_ = False
    s._burst_in_effect(now + 20.0)    # tail still active or expired — doesn't matter
    assert s._burst_capped is False

    # Visit reopens — burst may start again.
    wall.open_ = True
    with caplog.at_level("INFO", logger="pitcrew.hud"):
        result = s._burst_in_effect(now + 25.0)
    assert result is True
    assert s._burst_active is True


def test_burst_cap_clears_on_new_session():
    """Burst state including the cap is session state."""
    s = _sampler()
    wall = _Wall(open_=True)
    s.set_burst_watch(wall, burst_max_s=10.0)
    now = time.monotonic()
    s._burst_in_effect(now)
    s._burst_in_effect(now + 15.0)    # cap fires
    assert s._burst_capped is True

    s.new_session()
    assert s._burst_capped is False


def test_burst_resets_across_new_session(caplog):
    s = _sampler()
    wall = _Wall(open_=True)
    s.set_burst_watch(wall)
    now = time.monotonic()
    s._burst_in_effect(now)           # activate burst
    assert s._burst_active is True

    s.new_session()
    assert s._burst_active is False
    assert s._burst_last_open_s == 0.0
    assert s._burst_start_s == 0.0


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def test_burst_defaults_match_module_constants():
    s = _sampler()
    assert s._burst_interval_s == pytest.approx(BURST_INTERVAL_S)
    assert s._burst_tail_s == pytest.approx(BURST_TAIL_S)
    assert s._burst_max_s == pytest.approx(BURST_MAX_S)
