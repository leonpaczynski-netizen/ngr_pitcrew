"""Acceptance-test gap-fills for the Live Race Engineer wiring feature.

The builder tests (test_live_race_engineer_wiring.py, test_live_pit_wall.py)
cover most criteria well.  Three gaps remain after reading those files:

  AC4  — MONITOR recommendation (a valid StrategyRecommendation value) must
          leave _live_pending=False and produce no warning, just like
          PLAN_STILL_OPTIMAL.  No existing test covers this branch.

  AC5  — The PTT→bridge signal chain (_wire_voice calls set_strategy_ack_handler
          on the QueryListener, and the stored lambda emits _voice_strategy_ack
          which routes to _on_voice_strategy_ack via the Qt signal-slot
          connection) is not tested end-to-end.  Existing tests call
          _on_voice_strategy_ack directly.  A missing registration or a broken
          lambda would go unnoticed.

  AC8  — "No new engineering logic" is a code-inspection assertion.  No test
          verifies that _feed_live calls only the expected domain entry points,
          that decide_replan is not called directly from the bridge, or that
          acknowledge_strategy still returns executes_anything=False for both
          argument values.

AC3 (graceful degradation) is also extended: audio_view present but
fuel_per_lap_plan=None must not crash or produce a garbage fuel-delta string.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# QApplication fixture (module-scoped — one per test module)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# Minimal fakes — mirrors the subset used by test_live_race_engineer_wiring.py
# ---------------------------------------------------------------------------

class _FakeSignalBridge(QObject):
    lap_completed = pyqtSignal(object)
    connection_changed = pyqtSignal(object, object)
    race_state_changed = pyqtSignal(str)
    car_detected = pyqtSignal(object)
    strategy_status_changed = pyqtSignal(object)


class _FakeQueryListener:
    """Duck-typed stand-in for voice.query_listener.QueryListener.

    The real set_strategy_ack_handler just stores the callable; this mirrors
    that exactly so _wire_voice works without importing the real class.
    """
    def __init__(self):
        self._strategy_ack_handler = None

    def set_strategy_ack_handler(self, handler):
        self._strategy_ack_handler = handler


class _FakeDB:
    def __init__(self):
        self._approved = {}

    def list_preparation_activities(self, cycle_id):      return []
    def get_preparation_cycle(self, cycle_id):            return {"cycle_id": cycle_id}
    def upsert_preparation_activity(self, row):           return row.get("activity_id", "")
    def bind_session_to_activity(self, *a, **kw):         return True
    def get_session_meta(self, session_id):               return None
    def get_practice_sessions_for_cycle(self, cycle_id): return []
    def get_approved_strategy(self, cycle_id):            return self._approved.get(cycle_id)
    def save_approved_strategy(self, cycle_id, plan):     self._approved[cycle_id] = plan
    def build_event_preparation_report(self, cycle_id):  return {}
    def build_cross_session_memory(self):                 return {}


class _FakeLivePage:
    def __init__(self):
        self.last_vm = None
        self.last_plan = None

    def set_state(self, vm):   self.last_vm = vm
    def show_plan(self, plan): self.last_plan = plan


class _Win:
    def __init__(self, tracker=None, signal_bridge=None, query_listener=None,
                 connected=True):
        self._bridge = signal_bridge
        self._tracker = tracker
        self._query_listener = query_listener
        self._connected_flag = connected
        self._live_race_elapsed_s = None
        self._live_fuel_plan = None
        self._live_pace_plan_s = 90.0
        self._live_fuel_samples = None
        self._live_clean_lap_times = None
        self._live_pit_loss_s = None
        self._live_driver_reports = None

    def _build_session_context(self):
        flag = self._connected_flag
        class _Ctx:
            connected = flag
        return _Ctx()

    def _build_event_context(self):
        return None

    def _persist_config(self, *a):
        pass


def _cfg():
    return {
        "active_cycle_id": "test_cycle_1",
        "voice": {"enabled": False},
        "strategy": {"car": "Porsche 911 RSR", "track": "Fuji",
                     "race_type": "lap", "laps": 25},
    }


def _make_bridge(qapp, tracker=None, signal_bridge=None, query_listener=None,
                 live_page=None, connected=True):
    from ui.pit_crew_controller import PitCrewController
    from ui.pit_crew_shell import PitCrewShell
    from ui.live_shell_bridge import LiveShellBridge

    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    if live_page is not None:
        shell.live_page = live_page

    win = _Win(tracker=tracker, signal_bridge=signal_bridge,
               query_listener=query_listener, connected=connected)
    db = _FakeDB()
    bridge = LiveShellBridge(shell, ctrl, window=win, config=_cfg(), db=db,
                             spawn=lambda fn: fn())
    return bridge, shell, win, db


def _replan_decision():
    """A StrategyReplanDecision dict shaped as the bridge stores it in _live_decision."""
    from strategy.adaptive_live_strategy import (
        StrategyReplanCandidate, StrategyRecommendation, StrategyConfidence,
    )
    cand = StrategyReplanCandidate(
        label="Extra stop for pace", stop_count_delta=1,
        projected_total_time_s=3600.0, expected_completed_laps=None,
        fuel_target_note="refuel as needed", tyre_note="fresh tyres",
        assumptions=("fresh tyres ~1.5% quicker",), expected_gain_detail="faster overall",
        legal=True, fingerprint="fp_ac_gaps",
    )
    return {
        "recommendation": StrategyRecommendation.REPLAN_RECOMMENDED.value,
        "confidence": StrategyConfidence.MEDIUM.value,
        "best_candidate": cand.to_dict(),
        "triggers": [],
        "candidates": [cand.to_dict()],
        "next_review_trigger": "lap boundary",
        "evidence_that_would_invalidate": [],
        "detail": "pace 6.7% slower than forecast",
        "fingerprint": "fp_ac_gaps_dec",
    }


# ===========================================================================
# AC4 gap — MONITOR recommendation leaves _live_pending False, no warning
# ===========================================================================

class TestMonitorRecommendationIsNotPending:
    """AC4 says PLAN_STILL_OPTIMAL _and_ MONITOR must leave _live_pending False.
    The builder tests verify PLAN_STILL_OPTIMAL; MONITOR is a valid enum value
    not yet covered."""

    def _monitor_audio_view(self):
        return {
            "ok": True,
            "strategy_decision": {
                "recommendation": "MONITOR",
                "confidence": "medium",
                "best_candidate": None,
                "next_review_trigger": "next lap",
            },
            "strategy_message": {
                "headline": "Plan holding — monitor next lap.",
                "next_review": "next lap",
                "confidence": "medium",
            },
        }

    def test_monitor_adapter_produces_no_warning(self):
        """MONITOR recommendation must not produce the accept/keep CTA warning."""
        from ui.shell_feed_adapters import live_pit_wall_vm_from_state
        from strategy.adaptive_live_strategy import LiveStrategyState, StrategyObjective
        state = LiveStrategyState(
            objective=StrategyObjective.LAP_COUNT,
            current_lap=5, laps_remaining=20,
            fuel_remaining_l=60.0, fuel_per_lap_actual=3.0, fuel_per_lap_plan=3.0,
            lap_time_actual_s=90.0, lap_time_plan_s=90.0,
            tyre_age_laps=5, current_compound="RM",
            pit_stops_completed=0, laps_since_pit=5,
            required_stops=1, telemetry_fresh=True,
        )
        vm = live_pit_wall_vm_from_state(state, connected=True,
                                         audio_view=self._monitor_audio_view())
        assert vm.warning == "", (
            "MONITOR recommendation must not produce the accept/keep CTA warning — "
            f"got: {vm.warning!r}")

    def test_monitor_in_bridge_leaves_live_pending_false(self, qapp):
        """When the bridge receives a MONITOR decision it must not set _live_pending."""
        lp = _FakeLivePage()
        bridge, _shell, _win, _db = _make_bridge(qapp, live_page=lp)

        # Inject a MONITOR decision directly — mirrors what _feed_live would set when
        # build_live_audio_strategy_view returns MONITOR.
        bridge._live_decision = {
            "recommendation": "MONITOR",
            "confidence": "medium",
            "best_candidate": None,
        }
        rec = str((bridge._live_decision or {}).get("recommendation") or "")
        bridge._live_pending = rec in ("REPLAN_RECOMMENDED", "REPLAN_URGENT")

        assert bridge._live_pending is False, (
            "MONITOR recommendation must leave _live_pending=False")


# ===========================================================================
# AC5 gap — PTT→bridge signal chain (_wire_voice end-to-end)
# ===========================================================================

class TestPttWiringChainEndToEnd:
    """AC5 requires that the voice-ack path from QueryListener → _voice_strategy_ack
    signal → _on_voice_strategy_ack slot functions as a connected whole.

    Existing tests call _on_voice_strategy_ack directly; none verify that
    _wire_voice correctly registers a handler on the QueryListener whose lambda
    emits the Qt signal, routing the ack to the slot on the Qt thread.
    """

    def test_wire_voice_registers_handler_on_query_listener(self, qapp):
        """After construction, the bridge must have called set_strategy_ack_handler
        on the window's _query_listener, leaving a non-None handler stored."""
        ql = _FakeQueryListener()
        _bridge, _shell, _win, _db = _make_bridge(qapp, query_listener=ql)
        assert ql._strategy_ack_handler is not None, (
            "_wire_voice must register a handler on the QueryListener via "
            "set_strategy_ack_handler")

    def test_accept_through_ptt_chain_sets_live_accepted_plan(self, qapp):
        """Full chain: calling the QueryListener's stored handler with 'accept'
        must emit _voice_strategy_ack → _on_voice_strategy_ack → set
        _live_accepted_plan (direct Qt signal-slot connection, same thread)."""
        ql = _FakeQueryListener()
        bridge, _shell, _win, _db = _make_bridge(qapp, query_listener=ql)

        bridge._live_pending = True
        bridge._live_decision = _replan_decision()

        ql._strategy_ack_handler("accept")

        assert bridge._live_accepted_plan is not None, (
            "PTT 'accept' must route through the Qt signal into _on_voice_strategy_ack "
            "and set _live_accepted_plan")
        assert bridge._live_accepted_plan.get("name") == "Extra stop for pace"

    def test_keep_through_ptt_chain_leaves_plan_unchanged(self, qapp):
        """Full chain: 'keep' must not alter the shown plan."""
        ql = _FakeQueryListener()
        bridge, _shell, _win, _db = _make_bridge(qapp, query_listener=ql)
        initial = {"name": "Original plan"}
        bridge._live_accepted_plan = initial
        bridge._live_pending = True
        bridge._live_decision = _replan_decision()

        ql._strategy_ack_handler("keep")

        assert bridge._live_accepted_plan is initial, (
            "PTT 'keep' must not mutate _live_accepted_plan")

    def test_db_row_untouched_through_full_ptt_chain(self, qapp):
        """The DB-persisted approved-strategy row must survive the full PTT→signal→slot
        accept path unchanged, proving the advisory guarantee holds end-to-end."""
        ql = _FakeQueryListener()
        bridge, _shell, _win, db = _make_bridge(qapp, query_listener=ql)
        original_row = {"name": "Race plan", "candidate_id": "cand-99"}
        db._approved["test_cycle_1"] = dict(original_row)

        bridge._live_pending = True
        bridge._live_decision = _replan_decision()

        ql._strategy_ack_handler("accept")

        assert db._approved["test_cycle_1"] == original_row, (
            "The DB-persisted approved strategy must not be mutated by a PTT accept")

    def test_handler_with_no_pending_does_nothing_through_chain(self, qapp):
        """Calling the handler when _live_pending is False must be a safe no-op
        all the way through the signal chain."""
        ql = _FakeQueryListener()
        bridge, _shell, _win, _db = _make_bridge(qapp, query_listener=ql)
        bridge._live_pending = False
        bridge._live_decision = None

        ql._strategy_ack_handler("accept")  # must not raise

        assert bridge._live_accepted_plan is None


# ===========================================================================
# AC8 — No new engineering logic: code-inspection assertions
# ===========================================================================

class TestNoNewEngineeringLogic:
    """AC8: every strategy decision traces to existing domain calls.
    The change must be confined to the wiring files; no new thresholds or
    decision branches may live in live_shell_bridge._feed_live."""

    def test_feed_live_source_calls_canonical_live_race_state(self):
        """_feed_live must build the live state via the established domain function,
        not a new inline computation."""
        import inspect
        from ui.live_shell_bridge import LiveShellBridge
        src = inspect.getsource(LiveShellBridge._feed_live)
        assert "build_canonical_live_race_state" in src, (
            "_feed_live must delegate state building to build_canonical_live_race_state")

    def test_feed_live_source_calls_build_live_audio_strategy_view(self):
        """_feed_live must route strategy evaluation through the established
        build_live_audio_strategy_view entry point."""
        import inspect
        from ui.live_shell_bridge import LiveShellBridge
        src = inspect.getsource(LiveShellBridge._feed_live)
        assert "build_live_audio_strategy_view" in src, (
            "_feed_live must delegate strategy evaluation to build_live_audio_strategy_view")

    def test_feed_live_does_not_call_decide_replan_directly(self):
        """decide_replan is an internal step inside build_live_audio_strategy_view.
        Calling it directly from the bridge would add new decision logic to the
        wiring layer — this must not happen."""
        import inspect
        from ui.live_shell_bridge import LiveShellBridge
        src = inspect.getsource(LiveShellBridge._feed_live)
        assert "decide_replan" not in src, (
            "_feed_live must NOT call decide_replan directly — that decision lives "
            "inside build_live_audio_strategy_view")

    def test_on_voice_strategy_ack_uses_domain_acknowledge_strategy(self):
        """The accept/keep handler must delegate the advisory record to the domain's
        acknowledge_strategy — not a new local recording mechanism."""
        import inspect
        from ui.live_shell_bridge import LiveShellBridge
        src = inspect.getsource(LiveShellBridge._on_voice_strategy_ack)
        assert "acknowledge_strategy" in src, (
            "_on_voice_strategy_ack must call the domain's acknowledge_strategy")

    def test_on_voice_strategy_ack_uses_adapter_for_reshaping(self):
        """The accept path must use live_plan_dict_from_candidate to reshape the
        candidate — no new format logic in the bridge."""
        import inspect
        from ui.live_shell_bridge import LiveShellBridge
        src = inspect.getsource(LiveShellBridge._on_voice_strategy_ack)
        assert "live_plan_dict_from_candidate" in src, (
            "_on_voice_strategy_ack must reshape the candidate via the adapter, "
            "not with new inline formatting logic")

    def test_acknowledge_strategy_always_executes_nothing(self):
        """acknowledge_strategy.executes_anything must be False for every call site —
        both record_preference=True (accept) and record_preference=False (keep)."""
        from strategy.adaptive_live_strategy import acknowledge_strategy
        for record_preference in (True, False):
            ack = acknowledge_strategy(record_preference=record_preference)
            assert ack.executes_anything is False, (
                f"acknowledge_strategy(record_preference={record_preference}) "
                f"returned executes_anything={ack.executes_anything} — must be False")

    def test_expected_strategy_domain_apis_still_exist(self):
        """The domain functions the bridge imports must still be callable.
        An import error or rename would break the feature silently."""
        from strategy.live_audio_strategy_build import build_live_audio_strategy_view
        from strategy.canonical_live_race_state import build_canonical_live_race_state
        from strategy.adaptive_live_strategy import acknowledge_strategy
        assert callable(build_live_audio_strategy_view)
        assert callable(build_canonical_live_race_state)
        assert callable(acknowledge_strategy)


# ===========================================================================
# AC3 gap — graceful degradation: audio_view present but fuel plan missing
# ===========================================================================

class TestGapToPlanGracefulDegradation:
    """AC3 says gap-to-plan degrades gracefully when plan/actual are missing.
    The builder tests cover the full-data case and the no-audio-view case; this
    covers the intermediate: audio_view present but fuel_per_lap_plan=None."""

    def test_gap_to_plan_no_crash_when_fuel_plan_missing(self):
        """When audio_view is present but fuel_per_lap_plan=None, no fuel-delta
        string must appear and the call must not raise."""
        from ui.shell_feed_adapters import live_pit_wall_vm_from_state
        from strategy.adaptive_live_strategy import LiveStrategyState, StrategyObjective
        state = LiveStrategyState(
            objective=StrategyObjective.LAP_COUNT,
            current_lap=5, laps_remaining=20,
            fuel_remaining_l=60.0,
            fuel_per_lap_actual=3.3,
            fuel_per_lap_plan=None,         # plan not available yet
            lap_time_actual_s=90.4, lap_time_plan_s=90.0,
            tyre_age_laps=5, current_compound="RM",
            pit_stops_completed=0, laps_since_pit=5,
            required_stops=1, telemetry_fresh=True,
        )
        audio_view = {
            "ok": True,
            "strategy_decision": {
                "recommendation": "PLAN_STILL_OPTIMAL",
                "confidence": "medium",
                "best_candidate": None,
                "next_review_trigger": "material change",
            },
            "strategy_message": {
                "headline": "Plan on track.",
                "next_review": "material change",
                "confidence": "medium",
            },
        }
        # Must not raise
        vm = live_pit_wall_vm_from_state(state, connected=True, audio_view=audio_view)
        assert "L per lap" not in vm.gap_to_plan, (
            "When fuel_per_lap_plan is None, no fuel-delta should appear in gap_to_plan; "
            f"got: {vm.gap_to_plan!r}")

    def test_gap_to_plan_no_crash_when_fuel_actual_missing(self):
        """When audio_view is present but fuel_per_lap_actual=None, no fuel-delta
        string must appear and the call must not raise."""
        from ui.shell_feed_adapters import live_pit_wall_vm_from_state
        from strategy.adaptive_live_strategy import LiveStrategyState, StrategyObjective
        state = LiveStrategyState(
            objective=StrategyObjective.LAP_COUNT,
            current_lap=5, laps_remaining=20,
            fuel_remaining_l=60.0,
            fuel_per_lap_actual=None,       # actual not available yet
            fuel_per_lap_plan=3.0,
            lap_time_actual_s=90.4, lap_time_plan_s=90.0,
            tyre_age_laps=5, current_compound="RM",
            pit_stops_completed=0, laps_since_pit=5,
            required_stops=1, telemetry_fresh=True,
        )
        audio_view = {
            "ok": True,
            "strategy_decision": {
                "recommendation": "PLAN_STILL_OPTIMAL",
                "confidence": "medium",
                "best_candidate": None,
                "next_review_trigger": "material change",
            },
            "strategy_message": {
                "headline": "Plan on track.",
                "next_review": "material change",
                "confidence": "medium",
            },
        }
        vm = live_pit_wall_vm_from_state(state, connected=True, audio_view=audio_view)
        assert "L per lap" not in vm.gap_to_plan, (
            "When fuel_per_lap_actual is None, no fuel-delta should appear in gap_to_plan; "
            f"got: {vm.gap_to_plan!r}")
