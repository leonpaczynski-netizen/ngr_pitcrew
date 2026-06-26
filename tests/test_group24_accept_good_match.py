"""Tests for Group 24 AC3 — Accept button enabled for GOOD_MATCH and ACCEPTABLE_MATCH."""
import pytest
from ui.track_model_alignment_vm import get_acceptance_button_states, _STATUS_DISPLAY
from data.track_model_alignment import TrackModelMatchStatus


class FakeResult:
    def __init__(self, match_status, blockers=None, accepted=False):
        self.match_status = match_status
        self.blockers = blockers or []
        self.accepted = accepted


def test_accept_enabled_for_good_match():
    result = FakeResult(TrackModelMatchStatus.GOOD_MATCH)
    states = get_acceptance_button_states(result, has_station_map=True)
    assert states["accept"] is True


def test_accept_enabled_for_acceptable_match():
    result = FakeResult(TrackModelMatchStatus.ACCEPTABLE_MATCH)
    states = get_acceptance_button_states(result, has_station_map=True)
    assert states["accept"] is True


def test_accept_disabled_for_partial_match():
    result = FakeResult(TrackModelMatchStatus.PARTIAL_MATCH)
    states = get_acceptance_button_states(result, has_station_map=True)
    assert states["accept"] is False


def test_accept_disabled_for_good_match_with_blockers():
    result = FakeResult(TrackModelMatchStatus.GOOD_MATCH, blockers=["some blocker"])
    states = get_acceptance_button_states(result, has_station_map=True)
    assert states["accept"] is False


def test_accept_disabled_for_already_accepted():
    result = FakeResult(TrackModelMatchStatus.GOOD_MATCH, accepted=True)
    states = get_acceptance_button_states(result, has_station_map=True)
    assert states["accept"] is False


def test_accept_disabled_for_acceptable_match_with_blockers():
    result = FakeResult(TrackModelMatchStatus.ACCEPTABLE_MATCH, blockers=["x"])
    states = get_acceptance_button_states(result, has_station_map=True)
    assert states["accept"] is False


# ---------------------------------------------------------------------------
# AC3 — colour assertions: GOOD_MATCH = amber #ffa500, ACCEPTABLE_MATCH = green #4caf50
# ---------------------------------------------------------------------------

def test_good_match_status_colour_is_amber():
    """GOOD_MATCH maps to amber (#ffa500) in the status display table."""
    _text, colour = _STATUS_DISPLAY[TrackModelMatchStatus.GOOD_MATCH]
    assert colour == "#ffa500", f"Expected #ffa500 for GOOD_MATCH, got {colour}"


def test_acceptable_match_status_colour_is_green():
    """ACCEPTABLE_MATCH maps to green (#4caf50) in the status display table."""
    _text, colour = _STATUS_DISPLAY[TrackModelMatchStatus.ACCEPTABLE_MATCH]
    assert colour == "#4caf50", f"Expected #4caf50 for ACCEPTABLE_MATCH, got {colour}"
