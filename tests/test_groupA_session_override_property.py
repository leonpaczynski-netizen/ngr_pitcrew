"""Tests for Group A — Live tab cleanup: session_type property honours override.

Verifies that tracker.session_type returns _session_type_override when set, falls
back to auto-detected _session_type when the override is None, and that
set_session_type_override(None) correctly clears the lock.
"""
from __future__ import annotations

import queue
import unittest

from telemetry.state import (
    RaceStateTracker,
    SessionType,
    TyreThresholds,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracker() -> tuple[RaceStateTracker, "queue.PriorityQueue"]:
    q: queue.PriorityQueue = queue.PriorityQueue()
    tracker = RaceStateTracker(q, TyreThresholds())
    return tracker, q


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSessionTypeOverrideProperty(unittest.TestCase):

    # 1. Override shadows the auto-detected value --------------------------

    def test_override_takes_precedence_over_auto_detected(self):
        """session_type returns the override, not _session_type, when override is set."""
        tracker, _ = _make_tracker()

        # Simulate auto-detection writing RACE to the internal field.
        tracker._session_type = SessionType.RACE

        # User selects QUALIFYING in the Live tab.
        tracker.set_session_type_override(SessionType.QUALIFYING)

        self.assertEqual(
            tracker.session_type,
            SessionType.QUALIFYING,
            "session_type must return the override when set, not the auto-detected value",
        )

    def test_override_shadows_every_session_type_value(self):
        """Override works regardless of which SessionType is forced."""
        tracker, _ = _make_tracker()
        tracker._session_type = SessionType.RACE

        for forced in (SessionType.PRACTICE, SessionType.QUALIFYING, SessionType.RACE, SessionType.UNKNOWN):
            tracker.set_session_type_override(forced)
            self.assertEqual(
                tracker.session_type,
                forced,
                f"Expected override {forced} but got {tracker.session_type}",
            )

    # 2. None clears the override — auto-detect resumes -------------------

    def test_set_override_none_reverts_to_auto_detected(self):
        """set_session_type_override(None) removes the override; auto-detected value is returned."""
        tracker, _ = _make_tracker()
        tracker._session_type = SessionType.PRACTICE

        # Set an override, then clear it.
        tracker.set_session_type_override(SessionType.QUALIFYING)
        self.assertEqual(tracker.session_type, SessionType.QUALIFYING)  # sanity check

        tracker.set_session_type_override(None)

        self.assertEqual(
            tracker.session_type,
            SessionType.PRACTICE,
            "After clearing the override, session_type must return the auto-detected _session_type",
        )

    def test_set_override_none_on_fresh_tracker(self):
        """set_session_type_override(None) on a tracker with no prior override is a no-op."""
        tracker, _ = _make_tracker()
        tracker._session_type = SessionType.RACE

        tracker.set_session_type_override(None)

        self.assertEqual(
            tracker.session_type,
            SessionType.RACE,
        )

    # 3. reset() — backend contract ----------------------------------------

    def test_reset_does_not_clear_override(self):
        """reset() preserves _session_type_override (clearing it is the UI's responsibility).
        After reset(), session_type therefore still returns the override, not UNKNOWN."""
        tracker, _ = _make_tracker()
        tracker.set_session_type_override(SessionType.QUALIFYING)

        tracker.reset()

        # _session_type is UNKNOWN right after reset; the override is preserved.
        self.assertEqual(
            tracker._session_type,
            SessionType.UNKNOWN,
            "_session_type must be reset to UNKNOWN by reset()",
        )
        self.assertEqual(
            tracker._session_type_override,
            SessionType.QUALIFYING,
            "_session_type_override must NOT be cleared by reset() — that is the UI's job",
        )
        # Consequently the public property still surfaces the override.
        self.assertEqual(
            tracker.session_type,
            SessionType.QUALIFYING,
        )

    def test_override_cleared_via_setter_after_reset(self):
        """After reset(), set_session_type_override(None) correctly reverts to auto-detect."""
        tracker, _ = _make_tracker()
        tracker.set_session_type_override(SessionType.QUALIFYING)
        tracker.reset()

        # UI calls the setter to clear the lock.
        tracker.set_session_type_override(None)

        # _session_type is UNKNOWN (no packets received after reset).
        self.assertEqual(
            tracker.session_type,
            SessionType.UNKNOWN,
            "After clearing the override post-reset, auto-detected UNKNOWN must be returned",
        )


if __name__ == "__main__":
    unittest.main()
