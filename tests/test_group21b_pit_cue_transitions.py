"""
Group 21B — Pit Lane Mapping: pit lane entry/exit transition cue tests.

Pure Python, no PyQt6 / no QApplication required.

Tests the transition logic that fires "Entering pit lane." and "Pit lane exit."
announcements exactly once per actual state change, using a mock VoiceAnnouncer.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call
from telemetry.state import Priority


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_announcer():
    """Return a MagicMock that mimics VoiceAnnouncer.announce()."""
    return MagicMock()


def _run_transitions(sequence: list[bool]) -> MagicMock:
    """
    Simulate the dashboard pit-lane transition logic for the given
    sequence of is_pit_likely boolean values.

    Returns the mock announcer so callers can assert on its calls.
    """
    announcer = _make_announcer()
    pit_lane_active = False  # mirrors self._pit_lane_active

    for pit_now in sequence:
        if pit_now != pit_lane_active:
            pit_lane_active = pit_now
            if pit_now:
                announcer.announce(
                    "Entering pit lane.",
                    Priority.HIGH, "pit_lane_entry", 5.0,
                )
            else:
                announcer.announce(
                    "Pit lane exit.",
                    Priority.HIGH, "pit_lane_exit", 5.0,
                )

    return announcer


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPitCueTransitions:
    """Verify that announcements fire on state changes only."""

    def test_false_to_true_fires_pit_entry(self):
        """False → True: one 'Entering pit lane.' announcement."""
        ann = _run_transitions([False, True])
        ann.announce.assert_called_once_with(
            "Entering pit lane.", Priority.HIGH, "pit_lane_entry", 5.0
        )

    def test_true_to_false_fires_pit_exit(self):
        """True → False: one 'Pit lane exit.' announcement."""
        # Start state is False; we need to prime it to True first.
        ann = _run_transitions([True, False])
        # First call: entry, second call: exit
        assert ann.announce.call_count == 2
        last_call = ann.announce.call_args_list[-1]
        assert last_call == call("Pit lane exit.", Priority.HIGH, "pit_lane_exit", 5.0)

    def test_true_to_true_fires_no_extra_cue(self):
        """True → True (no change): only the initial entry cue fires."""
        ann = _run_transitions([True, True, True])
        # Only one cue: the False→True transition at position 0
        ann.announce.assert_called_once_with(
            "Entering pit lane.", Priority.HIGH, "pit_lane_entry", 5.0
        )

    def test_false_to_false_fires_no_cue(self):
        """False → False: no announcements at all."""
        ann = _run_transitions([False, False, False])
        ann.announce.assert_not_called()

    def test_multiple_rapid_transitions_one_cue_per_change(self):
        """F→T→F→T→F produces exactly one cue per actual transition."""
        ann = _run_transitions([False, True, False, True, False])
        assert ann.announce.call_count == 4
        calls = ann.announce.call_args_list
        assert calls[0] == call("Entering pit lane.", Priority.HIGH, "pit_lane_entry", 5.0)
        assert calls[1] == call("Pit lane exit.",     Priority.HIGH, "pit_lane_exit",  5.0)
        assert calls[2] == call("Entering pit lane.", Priority.HIGH, "pit_lane_entry", 5.0)
        assert calls[3] == call("Pit lane exit.",     Priority.HIGH, "pit_lane_exit",  5.0)

    def test_sustained_in_pit_then_exit(self):
        """Multiple True frames followed by False: exactly one exit cue."""
        ann = _run_transitions([True, True, True, False])
        assert ann.announce.call_count == 2
        calls = ann.announce.call_args_list
        assert calls[0] == call("Entering pit lane.", Priority.HIGH, "pit_lane_entry", 5.0)
        assert calls[1] == call("Pit lane exit.",     Priority.HIGH, "pit_lane_exit",  5.0)

    def test_no_transitions_no_cues(self):
        """Empty sequence: zero announcements."""
        ann = _run_transitions([])
        ann.announce.assert_not_called()
