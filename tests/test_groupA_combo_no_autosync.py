"""Tests for Group A — Live tab cleanup: combo must never be driven by telemetry.

DECISION A: Manual always wins from the first packet.  Automation must NEVER
set the Live-tab session combo.  The auto-sync block has been removed from
_update_live(); these tests verify that the removal is complete and that the
remaining behaviours (manual lock, reset clears lock) are correct.

Three behavioural contracts verified:
  1. _update_live() never calls combo.setCurrentText() or combo.blockSignals()
     — verified structurally (source-text check) and behaviourally (stub).
  2. Manual selection persists: after _on_live_mode_changed("Qualifying"),
     packets that auto-detect RACE leave combo on "Qualifying" and
     tracker.session_type == QUALIFYING.
  3. Reset clears the lock: after a manual selection, _on_reset_clicked()
     results in tracker.session_type returning the auto-detected value.
"""
from __future__ import annotations

import pathlib
import unittest
from unittest.mock import MagicMock

from telemetry.state import RaceStateTracker, SessionType, TyreThresholds


# ---------------------------------------------------------------------------
# Source-text helpers (no QApplication needed)
# ---------------------------------------------------------------------------

_ROOT = pathlib.Path(__file__).parent.parent
_DASHBOARD_SRC = (_ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8") + (_ROOT / "ui" / "live_ui.py").read_text(encoding="utf-8")


def _method_body(source: str, method_name: str) -> str:
    start = source.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = source.find("\n    def ", start + 1)
    return source[start:end] if end != -1 else source[start:]


# ---------------------------------------------------------------------------
# Stub objects — no PyQt6 required
# ---------------------------------------------------------------------------

class FakeCombo:
    """Minimal stand-in for QComboBox."""

    def __init__(self, initial_text: str = "Race"):
        self._text = initial_text
        self.set_current_text_calls: list[str] = []
        self.block_signals_calls: list[bool] = []

    def currentText(self) -> str:
        return self._text

    def setCurrentText(self, text: str) -> None:
        self.set_current_text_calls.append(text)
        self._text = text

    def blockSignals(self, block: bool) -> None:
        self.block_signals_calls.append(block)


class FakeLabel:
    """Minimal stand-in for BigValueLabel / QLabel."""

    def __init__(self):
        self._value = ""

    def set_value(self, v: str) -> None:
        self._value = v

    def setText(self, v: str) -> None:
        self._value = v

    @property
    def text(self) -> str:
        return self._value


class FakePacket:
    """Minimal GT7Packet stand-in — only the fields _update_live reads."""

    def __init__(self, session_type_int: int = 0):
        self.speed_kmh = 100.0
        self.current_gear = 3
        self.engine_rpm = 6000.0
        self.current_position = 1
        self.total_cars = 20
        self.cars_in_race = 20
        self.laps_in_race = 5
        self.last_lap_ms = 0
        self.best_lap_ms = 0
        # Not read directly by _update_live after the auto-sync removal, but kept
        # to document intent.
        self._session_type_int = session_type_int


def _make_tracker() -> RaceStateTracker:
    import queue
    q: queue.PriorityQueue = queue.PriorityQueue()
    return RaceStateTracker(q, TyreThresholds())


class FakeDashboard:
    """Minimal stub that replicates _update_live and _on_reset_clicked logic
    without requiring a QApplication or PyQt6 widgets."""

    def __init__(self, combo_text: str = "Race"):
        self._combo_live_mode = FakeCombo(combo_text)
        self._lbl_session = FakeLabel()
        self._lbl_speed = FakeLabel()
        self._lbl_gear = FakeLabel()
        self._lbl_rpm = FakeLabel()
        self._lbl_position = FakeLabel()
        self._lbl_countdown = FakeLabel()
        self._lbl_current_lap = FakeLabel()
        self._lbl_last_lap = FakeLabel()
        self._lbl_best_lap = FakeLabel()
        self._lbl_delta = FakeLabel()
        self._live_label_cache: dict = {}
        self._tracker: RaceStateTracker | None = None
        self._strategy_engine = None
        self._bridge = MagicMock()

    def _update_live(self, p: FakePacket) -> None:
        """Mirrors the post-cleanup _update_live() — NO combo writes, NO blockSignals."""
        self._lbl_speed.set_value(f"{p.speed_kmh:.0f}")
        self._lbl_gear.set_value(str(p.current_gear) if p.current_gear > 0 else "N")
        _new = f"{p.engine_rpm:.0f}"
        if self._live_label_cache.get("lbl_rpm") != _new:
            self._live_label_cache["lbl_rpm"] = _new
            self._lbl_rpm.setText(_new)
        if p.current_position > 0:
            pos_str = f"P{p.current_position}/{p.total_cars}"
        else:
            pos_str = "—"
        self._lbl_position.set_value(pos_str)
        # --- Session label uses combo as master source (no auto-sync of combo) ---
        cars = p.cars_in_race
        session_text = self._combo_live_mode.currentText()
        if cars > 0:
            session_text += f" ({cars} cars)"
        self._lbl_session.set_value(session_text)
        recorded = self._tracker.laps_recorded if self._tracker is not None else 0
        if p.laps_in_race > 0:
            laps_rem = max(0, p.laps_in_race - recorded)
            self._lbl_countdown.set_value(f"{laps_rem} laps")
        _new = f"Lap {recorded + 1}"
        if self._live_label_cache.get("lbl_current_lap") != _new:
            self._live_label_cache["lbl_current_lap"] = _new
            self._lbl_current_lap.setText(_new)

    def _on_live_mode_changed(self, mode: str) -> None:
        """Mirrors the real _on_live_mode_changed — writes override to tracker."""
        if self._tracker is not None:
            _mode_map = {
                "Practice":   SessionType.PRACTICE,
                "Qualifying": SessionType.QUALIFYING,
                "Race":       SessionType.RACE,
            }
            self._tracker.set_session_type_override(_mode_map.get(mode))

    def _on_reset_clicked(self) -> None:
        """Mirrors the real _on_reset_clicked — reset + clear override."""
        if self._tracker is not None:
            self._tracker.reset()
            self._tracker.set_session_type_override(None)
        self._bridge.race_state_changed.emit("IDLE")


# ---------------------------------------------------------------------------
# 1. Structural: _update_live() body must not contain combo writes
# ---------------------------------------------------------------------------

class TestUpdateLiveStructural(unittest.TestCase):
    """Source-text checks that the auto-sync block is absent from _update_live."""

    def setUp(self):
        self._body = _method_body(_DASHBOARD_SRC, "_update_live")
        self.assertTrue(self._body, "_update_live not found in dashboard.py")

    def test_no_blockSignals_for_combo_live_mode(self):
        """_update_live must not call _combo_live_mode.blockSignals()."""
        # The only allowed blockSignals in _update_live are for other widgets;
        # the specific pattern targeting the live mode combo must be absent.
        import re
        hits = re.findall(r"_combo_live_mode\.blockSignals\s*\(", self._body)
        self.assertEqual(
            hits, [],
            "_update_live must not call _combo_live_mode.blockSignals() — "
            "auto-sync block was not fully removed"
        )

    def test_no_setCurrentText_on_combo_live_mode(self):
        """_update_live must not call _combo_live_mode.setCurrentText()."""
        import re
        hits = re.findall(r"_combo_live_mode\.setCurrentText\s*\(", self._body)
        self.assertEqual(
            hits, [],
            "_update_live must not call _combo_live_mode.setCurrentText() — "
            "auto-sync block was not fully removed"
        )

    def test_no_last_auto_session_type_reference(self):
        """_update_live must not reference _last_auto_session_type."""
        self.assertNotIn(
            "_last_auto_session_type", self._body,
            "_last_auto_session_type must be absent from _update_live() "
            "after auto-sync removal"
        )

    def test_no_last_auto_session_type_in_whole_file(self):
        """_last_auto_session_type must not appear anywhere in dashboard.py."""
        self.assertNotIn(
            "_last_auto_session_type", _DASHBOARD_SRC,
            "_last_auto_session_type attribute must be completely removed from dashboard.py"
        )


# ---------------------------------------------------------------------------
# 2. Structural: _on_reset_clicked() body must call set_session_type_override
# ---------------------------------------------------------------------------

class TestResetStructural(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_DASHBOARD_SRC, "_on_reset_clicked")
        self.assertTrue(self._body, "_on_reset_clicked not found in dashboard.py")

    def test_reset_calls_set_session_type_override_none(self):
        """_on_reset_clicked must call set_session_type_override(None) after reset()."""
        self.assertIn(
            "set_session_type_override(None)", self._body,
            "_on_reset_clicked must call tracker.set_session_type_override(None) "
            "to implement DECISION B (reset clears the lock)"
        )

    def test_reset_calls_tracker_reset(self):
        """_on_reset_clicked must still call tracker.reset()."""
        self.assertIn(
            "self._tracker.reset()", self._body,
            "_on_reset_clicked must call self._tracker.reset() before clearing override"
        )


# ---------------------------------------------------------------------------
# 3. Structural: _live_try_load_active_event_map deleted
# ---------------------------------------------------------------------------

class TestLiveTryLoadDeleted(unittest.TestCase):

    def test_method_absent_from_dashboard(self):
        """_live_try_load_active_event_map must not appear in dashboard.py."""
        self.assertNotIn(
            "_live_try_load_active_event_map", _DASHBOARD_SRC,
            "_live_try_load_active_event_map must be removed from dashboard.py "
            "(both call sites deleted)"
        )

    def test_method_absent_from_mixin(self):
        """_live_try_load_active_event_map must not appear in track_modelling_ui.py."""
        mixin_src = (_ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "_live_try_load_active_event_map", mixin_src,
            "_live_try_load_active_event_map must be deleted from track_modelling_ui.py"
        )


# ---------------------------------------------------------------------------
# 4. Structural: _live_map_widget / _live_lbl_track removed from source
# ---------------------------------------------------------------------------

class TestLiveMapWidgetDeleted(unittest.TestCase):

    def test_live_map_widget_absent_from_dashboard(self):
        """_live_map_widget must not be referenced in dashboard.py."""
        self.assertNotIn(
            "_live_map_widget", _DASHBOARD_SRC,
            "_live_map_widget must be removed from dashboard.py (Live-tab map deleted)"
        )

    def test_live_lbl_track_absent_from_dashboard(self):
        """_live_lbl_track must not be referenced in dashboard.py."""
        self.assertNotIn(
            "_live_lbl_track", _DASHBOARD_SRC,
            "_live_lbl_track must be removed from dashboard.py"
        )

    def test_live_map_widget_absent_from_mixin(self):
        """_live_map_widget must not be referenced in track_modelling_ui.py."""
        mixin_src = (_ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "_live_map_widget", mixin_src,
            "_live_map_widget must be removed from track_modelling_ui.py"
        )

    def test_live_lbl_track_absent_from_mixin(self):
        """_live_lbl_track must not be referenced in track_modelling_ui.py."""
        mixin_src = (_ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "_live_lbl_track", mixin_src,
            "_live_lbl_track must be removed from track_modelling_ui.py"
        )


# ---------------------------------------------------------------------------
# 5. Behavioural (stub): _update_live never touches the combo
# ---------------------------------------------------------------------------

class TestUpdateLiveBehavioural(unittest.TestCase):
    """Feed packets that change tracker.session_type; assert combo is untouched."""

    def _make_dash_with_race_tracker(self) -> FakeDashboard:
        dash = FakeDashboard(combo_text="Race")
        dash._tracker = _make_tracker()
        # Simulate auto-detection writing RACE
        dash._tracker._session_type = SessionType.RACE
        return dash

    def test_combo_text_unchanged_after_packet_with_race_session(self):
        """After a packet when tracker is RACE and combo is Race, combo text stays."""
        dash = self._make_dash_with_race_tracker()
        pkt = FakePacket()

        dash._update_live(pkt)

        self.assertEqual(dash._combo_live_mode.currentText(), "Race")
        self.assertEqual(dash._combo_live_mode.set_current_text_calls, [],
                         "_update_live must not call setCurrentText on the combo")

    def test_combo_blockSignals_never_called(self):
        """_update_live must not call blockSignals on _combo_live_mode."""
        dash = self._make_dash_with_race_tracker()
        pkt = FakePacket()

        # Call many times to simulate a long race
        for _ in range(10):
            dash._update_live(pkt)

        self.assertEqual(dash._combo_live_mode.block_signals_calls, [],
                         "_update_live must never call blockSignals on _combo_live_mode")

    def test_session_label_reads_from_combo_not_tracker(self):
        """_lbl_session shows the combo text (manual choice), regardless of auto-detect."""
        dash = FakeDashboard(combo_text="Qualifying")
        dash._tracker = _make_tracker()
        # Auto-detect says RACE
        dash._tracker._session_type = SessionType.RACE
        pkt = FakePacket()

        dash._update_live(pkt)

        # Label must reflect the COMBO selection ("Qualifying"), not auto-detected RACE
        self.assertIn("Qualifying", dash._lbl_session.text,
                      "_lbl_session must show the combo's manual selection, not the auto-detected type")
        self.assertNotIn("Race", dash._lbl_session.text)


# ---------------------------------------------------------------------------
# 6. Behavioural (stub): manual selection persists through packets
# ---------------------------------------------------------------------------

class TestManualSelectionPersists(unittest.TestCase):
    """After user picks Qualifying, packets with auto-detected RACE must not change it."""

    def test_combo_stays_qualifying_after_race_packets(self):
        """Combo stays on Qualifying; tracker.session_type stays QUALIFYING.

        In the real app the user clicks the combo, which sets the combo text
        then fires _on_live_mode_changed via currentTextChanged signal.  The
        stub simulates that by setting the combo text directly before calling
        _on_live_mode_changed, matching the real call sequence.
        """
        dash = FakeDashboard(combo_text="Race")
        dash._tracker = _make_tracker()

        # Simulate user clicking the combo: combo text changes first, then the
        # signal fires _on_live_mode_changed (clear the call log so the manual
        # setCurrentText doesn't inflate the assertion below).
        dash._combo_live_mode.setCurrentText("Qualifying")
        dash._combo_live_mode.set_current_text_calls.clear()
        dash._on_live_mode_changed("Qualifying")

        # Simulate auto-detection resolving to RACE (written directly to internal attr)
        dash._tracker._session_type = SessionType.RACE

        # Feed several packets — _update_live must NOT touch the combo
        pkt = FakePacket()
        for _ in range(5):
            dash._update_live(pkt)

        # Combo must still be Qualifying (no further setCurrentText calls from _update_live)
        self.assertEqual(
            dash._combo_live_mode.currentText(), "Qualifying",
            "Combo must stay on Qualifying after packets — no auto-sync allowed"
        )
        self.assertEqual(
            dash._combo_live_mode.set_current_text_calls, [],
            "_update_live must not call setCurrentText on the combo at all"
        )
        # Tracker must honour the override
        self.assertEqual(
            dash._tracker.session_type, SessionType.QUALIFYING,
            "tracker.session_type must return QUALIFYING (override) not RACE (auto-detected)"
        )

    def test_tracker_override_set_when_mode_changed(self):
        """_on_live_mode_changed calls set_session_type_override with correct SessionType."""
        dash = FakeDashboard()
        dash._tracker = _make_tracker()

        dash._on_live_mode_changed("Practice")
        self.assertEqual(dash._tracker.session_type, SessionType.PRACTICE)

        dash._on_live_mode_changed("Qualifying")
        self.assertEqual(dash._tracker.session_type, SessionType.QUALIFYING)

        dash._on_live_mode_changed("Race")
        self.assertEqual(dash._tracker.session_type, SessionType.RACE)


# ---------------------------------------------------------------------------
# 7. Behavioural (stub): reset clears the lock
# ---------------------------------------------------------------------------

class TestResetClearsLock(unittest.TestCase):
    """After a manual selection, _on_reset_clicked() clears the session override."""

    def test_reset_clears_override_so_auto_detect_resumes(self):
        """After reset, tracker.session_type returns auto-detected value (override gone)."""
        dash = FakeDashboard(combo_text="Race")
        dash._tracker = _make_tracker()

        # User locks to Qualifying
        dash._on_live_mode_changed("Qualifying")
        self.assertEqual(dash._tracker.session_type, SessionType.QUALIFYING)  # sanity

        # Simulate auto-detection writing PRACTICE to the internal field
        dash._tracker._session_type = SessionType.PRACTICE

        # User clicks Reset Session
        dash._on_reset_clicked()

        # Override must be cleared; auto-detected value (UNKNOWN after reset) takes over
        self.assertIsNone(
            dash._tracker._session_type_override,
            "reset must clear _session_type_override to None"
        )
        # After reset() the internal _session_type is UNKNOWN
        self.assertEqual(
            dash._tracker.session_type, SessionType.UNKNOWN,
            "After reset+clear, tracker.session_type must return UNKNOWN (auto-detected)"
        )

    def test_reset_calls_tracker_reset_then_clears_override(self):
        """_on_reset_clicked calls tracker.reset() AND set_session_type_override(None)."""
        dash = FakeDashboard()
        tracker = _make_tracker()
        tracker.set_session_type_override(SessionType.QUALIFYING)
        dash._tracker = tracker

        dash._on_reset_clicked()

        # Both operations must have happened
        self.assertIsNone(tracker._session_type_override)
        self.assertEqual(tracker._session_type, SessionType.UNKNOWN)

    def test_reset_no_tracker_is_safe(self):
        """_on_reset_clicked with _tracker=None must not raise."""
        dash = FakeDashboard()
        dash._tracker = None

        try:
            dash._on_reset_clicked()
        except Exception as exc:
            self.fail(f"_on_reset_clicked raised with no tracker: {exc}")


if __name__ == "__main__":
    unittest.main()
