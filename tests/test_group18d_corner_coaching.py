"""Tests for Group 18D — live_position forwarding through build_coaching_response()."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from strategy.driving_advisor import DrivingAdvisor


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

class _FakeRecorder:
    def recent_laps(self, n):
        lap = MagicMock()
        lap.lap_num = 1
        lap.lap_time_ms = 90000
        lap.lock_up_count = 0
        lap.wheelspin_count = 0
        lap.oversteer_count = 0
        lap.oversteer_throttle_on_count = 0
        lap.brake_consistency_m = 5.0
        lap.max_speed_kmh = 200.0
        lap.max_lat_g = 2.0
        lap.avg_throttle_pct = 60.0
        lap.avg_brake_pct = 30.0
        lap.kerb_count = 0
        lap.bottoming_count = 0
        lap.snap_throttle_count = 0
        lap.rev_limiter_count = 0
        lap.rev_limiter_by_gear = {}
        lap.lock_up_positions = []
        lap.wheelspin_positions = []
        lap.oversteer_positions = []
        lap.snap_throttle_positions = []
        lap.over_braking_positions = []
        lap.over_braking_count = 0
        lap.abrupt_release_count = 0
        lap.car_max_speed_theoretical_kmh = 0.0
        lap.avg_tyre_radius = {}
        lap.off_track_count = 0
        return [lap]

    def best_lap(self):
        lap = MagicMock()
        lap.lap_time_ms = 90000
        lap.lap_num = 1
        return lap

    def last_lap(self):
        return self.recent_laps(1)[0]


def _make_advisor():
    config = {"anthropic": {"api_key": "test-key"}, "strategy": {}}
    recorder = _FakeRecorder()
    tracker = MagicMock()
    return DrivingAdvisor(recorder=recorder, tracker=tracker, config=config)


# ---------------------------------------------------------------------------
# Test 5 — live_position sentinel is forwarded to _build_coaching_prompt
# ---------------------------------------------------------------------------

def test_live_position_forwarded():
    advisor = _make_advisor()
    sentinel = object()

    with patch.object(advisor, "_build_coaching_prompt", return_value="prompt text") as mock_prompt, \
         patch("strategy.driving_advisor.call_api", return_value="coaching response"):
        advisor.build_coaching_response(live_position=sentinel)

    call_kwargs = mock_prompt.call_args
    assert call_kwargs is not None
    # live_position should be passed as keyword arg
    assert call_kwargs.kwargs.get("live_position") is sentinel


# ---------------------------------------------------------------------------
# Test 6 — live_position=None does not crash and injects no position content
# ---------------------------------------------------------------------------

def test_live_position_none_no_crash():
    advisor = _make_advisor()

    # Capture every (arg, return_value) pair from _get_live_segment_context
    # without replacing its logic, so we can assert on both inputs and outputs.
    _real_fn = advisor._get_live_segment_context
    _calls: list[tuple] = []  # list of (live_position_arg, return_value)

    def _spy(live_position=None):
        rv = _real_fn(live_position)
        _calls.append((live_position, rv))
        return rv

    with patch.object(advisor, "_get_live_segment_context", side_effect=_spy) as mock_seg_ctx, \
         patch("strategy.driving_advisor.call_api", return_value="coaching response"):
        result = advisor.build_coaching_response(live_position=None)

    # Should return the mocked API response without raising
    assert isinstance(result, str)
    assert len(result) > 0

    # _get_live_segment_context must have been called (not skipped entirely)
    assert mock_seg_ctx.called, "_get_live_segment_context was never called"

    # Every call must have received live_position=None and returned "" (no
    # position content injected into the prompt)
    for pos_arg, rv in _calls:
        assert pos_arg is None, (
            f"Expected live_position=None but got {pos_arg!r}"
        )
        assert rv == "", (
            f"Expected _get_live_segment_context to return '' for None "
            f"live_position, got {rv!r}"
        )
