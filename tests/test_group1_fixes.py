"""Tests for Remediation Group 1 fixes.

DEF-P1-003: Save Session crash — _lbl_bank_status missing after SUP-002
DEF-P1-004: Practice Analysis prompt uses wrong race type (timed race = 1 lap)
DEF-P1-008: Practice mode triggers RACE_FINISHED after timed event duration
"""
from __future__ import annotations

import queue
import time
import unittest
from unittest.mock import MagicMock

from telemetry.state import (
    RacePhase, RaceStateTracker, RaceType, SessionType, TyreThresholds,
    EventType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracker() -> tuple[RaceStateTracker, "queue.PriorityQueue"]:
    q: queue.PriorityQueue = queue.PriorityQueue()
    tracker = RaceStateTracker(q, TyreThresholds())
    return tracker, q


def _drain_events(q: "queue.PriorityQueue") -> list:
    events = []
    while not q.empty():
        _, _, evt = q.get_nowait()
        events.append(evt)
    return events


def _make_loading_packet(last_lap_ms: int = 0) -> MagicMock:
    """Minimal packet that triggers the loading branch without recording a new lap."""
    p = MagicMock()
    p.loading = True
    p.packet_id = 100
    p.car_on_track = True
    p.last_lap_ms = last_lap_ms   # 0 → _check_lap exits immediately
    p.best_lap_ms = 0
    p.fuel_level = 20.0
    p.speed_kmh = 0.0
    p.current_position = 1
    p.total_cars = 1
    return p


# ---------------------------------------------------------------------------
# DEF-P1-003 — _set_bank_status helper does not crash when label is absent
# ---------------------------------------------------------------------------

class TestSetBankStatusHelper(unittest.TestCase):

    def test_no_bare_lbl_bank_status_settext_in_dashboard(self):
        """No bare self._lbl_bank_status.setText( calls remain in dashboard.py.
        All must go through _set_bank_status() which has a hasattr guard.
        Tested by source scan — does not require a Qt display."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "ui" / "dashboard.py"
        text = src.read_text(encoding="utf-8")
        self.assertNotIn(
            "_lbl_bank_status.setText(",
            text,
            "Bare _lbl_bank_status.setText( found — must use _set_bank_status() instead",
        )

    def test_set_bank_status_method_exists_in_source(self):
        """_set_bank_status method is defined in dashboard.py."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "ui" / "dashboard.py"
        text = src.read_text(encoding="utf-8")
        self.assertIn("def _set_bank_status(self, msg: str)", text)
        self.assertIn("if hasattr(self, \"_lbl_bank_status\"):", text)

    def test_set_bank_status_guard_logic(self):
        """_set_bank_status helper guard works: no crash without label, setText called with label."""
        label_calls = []

        class _FakeLbl:
            def setText(self, msg):
                label_calls.append(msg)

        class _FakeWindow:
            def _set_bank_status(self, msg: str) -> None:
                if hasattr(self, "_lbl_bank_status"):
                    self._lbl_bank_status.setText(msg)

        # Without the attribute: no crash
        w = _FakeWindow()
        w._set_bank_status("no label")
        self.assertEqual(label_calls, [])

        # With the attribute: setText called
        w._lbl_bank_status = _FakeLbl()
        w._set_bank_status("with label")
        self.assertEqual(label_calls, ["with label"])


# ---------------------------------------------------------------------------
# DEF-P1-008 — Practice mode suppresses RACE_FINISHED
# ---------------------------------------------------------------------------

class TestRaceFinishedPracticeGuard(unittest.TestCase):

    def _setup_expired_timed_race(self, tracker: RaceStateTracker) -> None:
        """Put the tracker into a state where a timed race has just expired."""
        tracker.set_race_config(RaceType.TIMED, duration_minutes=0.001)  # 60 ms
        tracker._phase = RacePhase.RACING
        tracker._race_start_time = time.monotonic() - 10.0  # started 10 s ago
        tracker._lap_time_hist = [90_000]  # one lap recorded

    def test_race_finished_suppressed_in_practice_mode(self):
        """RACE_FINISHED must NOT fire when session_type_override is PRACTICE."""
        tracker, q = _make_tracker()
        tracker.set_session_type_override(SessionType.PRACTICE)
        self._setup_expired_timed_race(tracker)

        # Verify the timer is indeed expired
        self.assertEqual(tracker.computed_remaining_ms(), 0)

        packet = _make_loading_packet()
        tracker.update(packet)

        events = _drain_events(q)
        race_finished = [e for e in events if e.type == EventType.RACE_FINISHED]
        self.assertEqual(len(race_finished), 0,
            "RACE_FINISHED must not fire during a practice session")

    def test_race_finished_fires_in_race_mode(self):
        """RACE_FINISHED must still fire when session_type_override is RACE."""
        tracker, q = _make_tracker()
        tracker.set_session_type_override(SessionType.RACE)
        self._setup_expired_timed_race(tracker)

        self.assertEqual(tracker.computed_remaining_ms(), 0)

        packet = _make_loading_packet()
        tracker.update(packet)

        events = _drain_events(q)
        race_finished = [e for e in events if e.type == EventType.RACE_FINISHED]
        self.assertEqual(len(race_finished), 1,
            "RACE_FINISHED must fire when in race mode and timer expires")

    def test_race_finished_fires_when_override_is_none(self):
        """RACE_FINISHED fires when no override is set (default / auto-detect path)."""
        tracker, q = _make_tracker()
        tracker.set_session_type_override(None)
        self._setup_expired_timed_race(tracker)

        self.assertEqual(tracker.computed_remaining_ms(), 0)

        packet = _make_loading_packet()
        tracker.update(packet)

        events = _drain_events(q)
        race_finished = [e for e in events if e.type == EventType.RACE_FINISHED]
        self.assertEqual(len(race_finished), 1,
            "RACE_FINISHED must fire when override is None (auto-detect mode)")


if __name__ == "__main__":
    unittest.main()
