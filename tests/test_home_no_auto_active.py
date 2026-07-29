"""No-auto-active-event-on-open — unit tests for the active_cycle_id gate in
``build_initial_app_state`` (ui/new_shell_launch.py).

Qt-free: the function imports app_state (Qt-free) and calls window methods via the
defensive _safe_ctx wrapper; the live_shell_bridge import (PyQt6) is guarded inside
a try/except, so these tests run without a QApplication.

The gate: when config["active_cycle_id"] is absent or empty the event context is
suppressed → EventContext.event_id is None → AppState.has_active_event is False.
Once a cycle is explicitly selected, save_and_activate writes "active_cycle_id" into
the config dict, the gate does not fire, and the normal context path runs.
"""
from __future__ import annotations

from data.event_context import build_event_context
from data.session_context import build_session_context
from data.strategy_context import build_strategy_context
from ui.new_shell_launch import build_initial_app_state
from ui.practice_run_recorder import PracticeRunRecorder


def _fake_window_with_event():
    """A duck-typed window whose _build_event_context returns a non-None event_id.

    Simulates the state where config["strategy"] still carries an event_id from the
    previous session (the regression: on open the header would show that event even
    though active_cycle_id was cleared).
    """
    class _FakeWindow:
        def _build_event_context(self):
            # strategy dict still has an event_id — as happens after a previous session
            return build_event_context(strategy={"event_id": 42, "car": "Porsche 911 GT3 R"})

        def _build_session_context(self):
            return build_session_context()

        def _build_strategy_context(self):
            return build_strategy_context()

    return _FakeWindow()


def test_build_initial_app_state_no_active_cycle_gives_no_active_event():
    """Config with no active_cycle_id → has_active_event is False even if the window's
    event context would otherwise resolve a non-None event_id."""
    window = _fake_window_with_event()
    config = {}  # active_cycle_id absent
    state = build_initial_app_state(window, config)
    assert state.has_active_event is False


def test_build_initial_app_state_with_active_cycle_gives_active_event():
    """Config with a populated active_cycle_id → gate does not fire → event context
    flows through → has_active_event is True."""
    window = _fake_window_with_event()
    config = {"active_cycle_id": "cid-1"}
    state = build_initial_app_state(window, config)
    assert state.has_active_event is True


def test_build_initial_app_state_active_cycle_empty_string_gives_no_active_event():
    """An explicit empty string for active_cycle_id is treated as absent (no selection
    → no auto-active event)."""
    window = _fake_window_with_event()
    config = {"active_cycle_id": ""}
    state = build_initial_app_state(window, config)
    assert state.has_active_event is False


# ---------------------------------------------------------------------------
# End-to-end: open → pick flow (AC5 — lap attribution chain)
# ---------------------------------------------------------------------------

class TestEndToEndLapAttributionChain:
    """Full open→pick flow across all three consumers of config["active_cycle_id"].

    AC5: after an explicit pick, build_initial_app_state gives has_active_event True,
    resolve_active_cycle Rule 1 returns ONE_ACTIVE_EVENT, and
    practice_run_recorder.active_cycle_id() returns the picked cycle so lap
    attribution fires.  Both the initial build AND the 750 ms refresh call
    build_initial_app_state with the same config dict — testing the function once
    covers both paths.
    """

    # -- minimal fake DB for save_and_activate --------------------------------

    class _FakeDB:
        def __init__(self):
            self.events = []
            self.cycles = {}
            self._next_id = 1

        def get_all_events(self):
            return list(self.events)

        def get_event(self, name):
            return next((e for e in self.events if e.get("name") == name), None)

        def upsert_event(self, row):
            row = dict(row)
            row["id"] = self._next_id
            self.events.append(row)
            return self._next_id

        def get_preparation_cycle(self, cycle_id):
            return dict(self.cycles[cycle_id]) if cycle_id in self.cycles else None

        def upsert_preparation_cycle(self, cycle):
            self.cycles[cycle["cycle_id"]] = dict(cycle)

    # -------------------------------------------------------------------------

    def test_on_open_no_active_cycle_id_both_consumers_report_no_attribution(self):
        """On open, config carries a stale strategy.event_id from a previous session
        but no active_cycle_id.  Both consumers must agree: recorder returns "" and
        build_initial_app_state gives has_active_event False (the stale-strategy
        regression guard).

        The 750 ms refresh calls the same build_initial_app_state — confirming the
        gate here covers the refresh path equally (AC3).
        """
        config = {"strategy": {"event_id": 42, "car": "Porsche 911 GT3 R"}}
        recorder = PracticeRunRecorder(db=None, config=config)

        assert recorder.active_cycle_id() == "", (
            "recorder must return '' before any explicit pick"
        )
        state = build_initial_app_state(_fake_window_with_event(), config)
        assert state.has_active_event is False, (
            "has_active_event must be False — stale strategy.event_id must not auto-activate"
        )

    def test_after_explicit_pick_all_three_consumers_agree(self):
        """Directly setting config['active_cycle_id'] is the contract that all three
        consumers depend on: build_initial_app_state, resolve_active_cycle, and
        practice_run_recorder must all see the same cycle.
        """
        from strategy.active_cycle_resolution import (
            CycleCandidate, resolve_active_cycle, ActiveCycleResolutionState as R,
        )

        cycle_id = "cycle-gr-cup-r3"
        config = {}  # no selection yet

        # pre-condition: nothing active
        recorder = PracticeRunRecorder(db=None, config=config)
        assert recorder.active_cycle_id() == ""
        assert build_initial_app_state(_fake_window_with_event(), config).has_active_event is False

        # explicit pick — mirrors what save_and_activate writes
        config["active_cycle_id"] = cycle_id

        # 1. build_initial_app_state lets the event context through
        state = build_initial_app_state(_fake_window_with_event(), config)
        assert state.has_active_event is True

        # 2. resolve_active_cycle Rule 1 returns ONE_ACTIVE_EVENT
        resolution = resolve_active_cycle(
            [CycleCandidate(cycle_id=cycle_id, explicit_state="active", event_name="GR Cup R3")],
            selected_cycle_id=cycle_id,
        )
        assert resolution.state == R.ONE_ACTIVE_EVENT
        assert resolution.resolved_cycle_id == cycle_id
        assert resolution.selection_required is False

        # 3. recorder attribution — reads the same config dict
        assert recorder.active_cycle_id() == cycle_id

    def test_save_and_activate_write_path_unblocks_lap_attribution(self):
        """The REAL save_and_activate write path: before activation recorder.active_cycle_id()
        is ""; after, it equals result.cycle_id and build_initial_app_state gives
        has_active_event True — both reading the shared config dict the service mutated.
        """
        from services.event_setup import EventSetupService, EventDraft

        config = {}
        db = self._FakeDB()
        recorder = PracticeRunRecorder(db=None, config=config)

        assert recorder.active_cycle_id() == "", "no attribution before activation"

        svc = EventSetupService(db=db, config=config, persist=None)
        draft = EventDraft(
            name="GR Cup Round 3",
            car="Porsche Cayman GT4",
            track="Watkins Glen International",
            race_type="lap",
            laps=25,
        )
        result = svc.save_and_activate(draft)
        assert result.ok is True, f"save_and_activate failed: {result.message}"

        # Both consumers read the same config dict — they must agree
        assert recorder.active_cycle_id() == result.cycle_id, (
            "recorder must return the cycle written by save_and_activate"
        )
        state = build_initial_app_state(_fake_window_with_event(), config)
        assert state.has_active_event is True, (
            "has_active_event must be True after save_and_activate sets active_cycle_id"
        )


# ---------------------------------------------------------------------------
# Qt tests: HomePage rendering when resolution_state="event_requires_selection"
# ---------------------------------------------------------------------------
import pytest
from PyQt6.QtWidgets import QApplication
from ui.components.home_page import HomePage
from ui.app_state import AppState

_REQUIRES_SELECTION_PROMPT = (
    "Which event are you preparing for? Pick one below to start attaching laps."
)

_ONE_CANDIDATE_VIEW = {
    "resolution_state": "event_requires_selection",
    "candidates": [{"cycle_id": "c1", "event_name": "NGR Porsche Cup Rd7"}],
}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TestRequiresSelectionHomePage:
    """HomePage rendering for the event_requires_selection resolution state.

    These tests cover the UAT scenario where a single incomplete event arrives
    in the requires-selection state (because no active_cycle_id is set on open).
    """

    def test_requires_selection_shows_count_neutral_prompt(self, qapp):
        """The event_state label must show the count-neutral action prompt and
        must not contain the old "Several" wording."""
        page = HomePage()
        page.render(AppState.empty(), _ONE_CANDIDATE_VIEW)
        text = page._event_state.text()
        assert _REQUIRES_SELECTION_PROMPT in text
        assert "Several" not in text

    def test_requires_selection_shows_event_picker(self, qapp):
        """The candidate combo and Switch button must be visible (not hidden) and
        enabled, and the combo must carry the single candidate item.

        Visibility note: QWidget.isVisible() requires the widget to be in a
        shown window, so we assert isHidden() is False (setVisible(True) was
        called) and isEnabled() is True as the reliable Qt-unit-test proxy.
        """
        page = HomePage()
        page.render(AppState.empty(), _ONE_CANDIDATE_VIEW)
        assert not page._event_combo.isHidden(), (
            "_event_combo was hidden; expected setVisible(True) from have_candidates=True"
        )
        assert page._btn_switch.isEnabled(), (
            "_btn_switch was disabled; expected enabled with one candidate"
        )
        assert not page._btn_switch.isHidden(), (
            "_btn_switch was hidden; expected setVisible(True) from have_candidates=True"
        )
        assert page._event_combo.count() == 1
        assert "NGR Porsche Cup Rd7" in page._event_combo.itemText(0)

    def test_no_active_event_header_when_requires_selection(self, qapp):
        """The event title must show 'No active event' — not an event name —
        when AppState.empty() (has_active_event=False) is paired with the
        requires-selection view."""
        page = HomePage()
        page.render(AppState.empty(), _ONE_CANDIDATE_VIEW)
        assert page._event_title.text() == "No active event"
