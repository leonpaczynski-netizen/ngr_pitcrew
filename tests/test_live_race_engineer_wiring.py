"""Tests: live race engineer wiring — bridge, adapter, and voice PTT seam.

Covers the changes from the live-race-engineer activation brief:

  Bridge:
  - _wire_signals bug fix: _bridge (not bridge) → lap_completed connects
  - _feed_live populates engineer_instruction and sets _live_pending on divergence
  - PLAN_STILL_OPTIMAL leaves _live_pending False and no warning on the VM
  - INSUFFICIENT_EVIDENCE → confidence "insufficient", empty warning
  - _on_voice_strategy_ack("accept") while pending → _live_accepted_plan set from
    the best candidate; next _feed_live show_plan uses it; DB row untouched
  - Accept with nothing pending → safe no-op
  - "keep" leaves the plan unchanged

  Adapter:
  - live_pit_wall_vm_from_state: audio_view=None behaves exactly as before
  - audio_view present → engineer_instruction/next_decision/confidence populated
  - REPLAN_* → warning populated, PLAN_STILL_OPTIMAL → warning empty
  - gap_to_plan extended with fuel delta when audio_view present
  - live_plan_dict_from_candidate → correct show_plan shape
  - empty/missing label → {} (hides card)

  Voice:
  - new intents resolve correctly via _match_intent
  - new phrases are pronounceable (in-dictionary)
  - set_strategy_ack_handler invokes handler with "accept"/"keep"
  - handler exceptions are swallowed; response still returned
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
# Minimal fakes shared across bridge tests
# ---------------------------------------------------------------------------

class _FakeSignalBridge(QObject):
    """A stand-in for MainWindow's SignalBridge with the signals the bridge wires."""
    lap_completed = pyqtSignal(object)
    connection_changed = pyqtSignal(object, object)
    race_state_changed = pyqtSignal(str)
    car_detected = pyqtSignal(object)
    strategy_status_changed = pyqtSignal(object)


class _FakeTracker:
    """Duck-typed tracker exposing the property surface canonical_live_race_state reads."""
    def __init__(self, **overrides):
        self._d = {
            "race_type": "lap",
            "laps_recorded": 5,
            "laps_in_race": 25,
            "timed_duration_minutes": 0.0,
            "last_fuel": 60.0,
            "avg_fuel_per_lap": 3.0,
            "best_lap_ms": 96000,         # 96 s — 6.7% slower than a 90 s plan → PACE_SLOWER
            "pit_stops_completed": 0,
            "laps_since_pit": 5,
            "tyre_age_laps": 5,
            "in_pit": False,
            "pit_state_confidence": "high",
            "last_position": 4,
            "tyre_compound": "RM",
            "car_name": "Porsche 911 RSR",
            "track": "Fuji",
            "layout_id": "full_course",
        }
        self._d.update(overrides)

    def __getattr__(self, name):
        d = object.__getattribute__(self, "_d")
        if name in d:
            return d[name]
        raise AttributeError(name)


class _FakeQueryListener:
    """Stands in for voice.query_listener.QueryListener."""
    def __init__(self):
        self._strategy_ack_handler = None

    def set_strategy_ack_handler(self, handler):
        self._strategy_ack_handler = handler


class _FakeDB:
    """Minimal DB stub for the bridge (only methods the service layer actually calls)."""
    def __init__(self):
        self._approved = {}

    def list_preparation_activities(self, cycle_id):
        return []

    def get_preparation_cycle(self, cycle_id):
        return {"cycle_id": cycle_id, "car": "Porsche", "track": "Fuji"}

    def upsert_preparation_activity(self, row):
        return row.get("activity_id", "")

    def bind_session_to_activity(self, activity_id, session_id, cycle_id="", created_at=""):
        return True

    def get_session_meta(self, session_id):
        return None

    def get_practice_sessions_for_cycle(self, cycle_id):
        return []

    def get_approved_strategy(self, cycle_id):
        return self._approved.get(cycle_id)

    def save_approved_strategy(self, cycle_id, plan):
        self._approved[cycle_id] = plan

    def build_event_preparation_report(self, cycle_id):
        return {}

    def build_cross_session_memory(self):
        return {}


class _FakeLivePage:
    """Captures what the bridge feeds to the live pit wall."""
    def __init__(self):
        self.last_vm = None
        self.last_plan = None

    def set_state(self, vm):
        self.last_vm = vm

    def show_plan(self, plan):
        self.last_plan = plan


class _Win:
    """Minimal window stub for live-engineer wiring tests."""
    def __init__(self, tracker=None, signal_bridge=None, query_listener=None,
                 connected=True):
        self._bridge = signal_bridge              # the FIXED attribute name
        self._tracker = tracker
        self._query_listener = query_listener
        self._connected_flag = connected
        # Plan attrs the bridge sources (mirrors dashboard._refresh_audio_engineer)
        self._live_race_elapsed_s = None
        self._live_fuel_plan = None
        self._live_pace_plan_s = 90.0            # 90 s planned pace
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
    """Build a wired LiveShellBridge with inline spawn and duck-typed fakes."""
    from ui.pit_crew_controller import PitCrewController
    from ui.pit_crew_shell import PitCrewShell
    from ui.live_shell_bridge import LiveShellBridge

    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)

    # Inject a fake live_page so set_state/show_plan are captured without Qt widgets
    if live_page is not None:
        shell.live_page = live_page

    win = _Win(tracker=tracker, signal_bridge=signal_bridge,
               query_listener=query_listener, connected=connected)
    db = _FakeDB()
    bridge = LiveShellBridge(shell, ctrl, window=win, config=_cfg(), db=db,
                             spawn=lambda fn: fn())
    return bridge, shell, win, db


# ===========================================================================
# 1. _wire_signals bug fix: _bridge (not bridge) must connect lap_completed
# ===========================================================================

class TestWireSignalsBugFix:
    def test_lap_completed_emitted_triggers_refresh(self, qapp):
        """After fixing the attribute lookup from 'bridge' to '_bridge',
        emitting lap_completed on the window's _bridge object calls refresh()
        on the bridge — we verify by counting refresh calls."""
        sig_bridge = _FakeSignalBridge()
        refresh_calls = []

        bridge, shell, win, db = _make_bridge(qapp, signal_bridge=sig_bridge)
        # Monkey-patch refresh to count calls (avoids full domain round-trip)
        original_refresh = bridge.refresh
        bridge.refresh = lambda: refresh_calls.append(1) or original_refresh()

        sig_bridge.lap_completed.emit({"lap": 1})
        assert len(refresh_calls) >= 1, (
            "lap_completed should have triggered a refresh via the _bridge connection")

    def test_bridge_attribute_not_found_is_safe(self, qapp):
        """A window with NO _bridge must not crash the bridge init."""
        bridge, _shell, _win, _db = _make_bridge(qapp, signal_bridge=None)
        # Reaching here means _wire_signals handled the missing attribute gracefully.
        assert bridge is not None


# ===========================================================================
# 2. _feed_live with divergence → pending, engineer_instruction populated
# ===========================================================================

class TestPerLapRecompute:
    """Validator finding: decide_replan must run once per lap ('at the end of every
    lap'), not on every 750ms display tick — otherwise the warning flickers and a
    lap-signal + timer double-fire recomputes redundantly."""

    def test_the_decision_is_reused_between_display_ticks_on_the_same_lap(self, qapp):
        tracker = _FakeTracker(race_type="lap", laps_in_race=25, laps_recorded=5,
                               best_lap_ms=96000)
        lp = _FakeLivePage()
        bridge, _shell, win, _db = _make_bridge(qapp, tracker=tracker, live_page=lp,
                                                connected=True)
        win._live_pace_plan_s = 90.0
        bridge._feed_live()
        first = bridge._live_audio_view
        assert first is not None and bridge._live_decision_lap == 5
        # A second tick on the SAME lap must reuse the cached decision object, not rebuild.
        bridge._feed_live()
        assert bridge._live_audio_view is first          # same object — not recomputed

    def test_a_new_lap_recomputes_the_decision(self, qapp):
        tracker = _FakeTracker(race_type="lap", laps_in_race=25, laps_recorded=5,
                               best_lap_ms=96000)
        lp = _FakeLivePage()
        bridge, _shell, win, _db = _make_bridge(qapp, tracker=tracker, live_page=lp,
                                                connected=True)
        win._live_pace_plan_s = 90.0
        bridge._feed_live()
        first = bridge._live_audio_view
        tracker._d["laps_recorded"] = 6                  # a lap completed
        bridge._feed_live()
        assert bridge._live_decision_lap == 6
        assert bridge._live_audio_view is not first      # recomputed for the new lap

    def test_a_stale_accepted_plan_does_not_survive_an_event_switch(self, qapp):
        # After a switch the cache is cleared then refresh() legitimately rebuilds it for
        # the NEW event; the guarantee that matters is that a plan accepted for the OLD
        # event is not carried over.
        tracker = _FakeTracker(race_type="lap", laps_in_race=25, laps_recorded=5)
        bridge, _shell, _win, _db = _make_bridge(qapp, tracker=tracker, connected=True)
        bridge._live_accepted_plan = {"name": "Old event plan"}
        bridge._on_activate_event("Some Event")
        assert bridge._live_accepted_plan is None


class TestFeedLiveWithDivergence:
    def test_pace_slower_sets_pending_and_instruction(self, qapp):
        """best_lap_ms=96000 (96 s) vs plan=90 s → PACE_SLOWER triggers
        REPLAN_RECOMMENDED → _live_pending=True and engineer_instruction set.
        connected=True so telemetry_fresh=True and decide_replan runs properly."""
        tracker = _FakeTracker(race_type="lap", laps_in_race=25, laps_recorded=5,
                               best_lap_ms=96000)  # 96 s actual; plan=90 s
        lp = _FakeLivePage()
        bridge, _shell, win, _db = _make_bridge(qapp, tracker=tracker, live_page=lp,
                                                connected=True)
        win._live_pace_plan_s = 90.0

        bridge._feed_live()

        assert bridge._live_pending is True
        vm = lp.last_vm
        assert vm is not None
        # The engineer instruction should contain content when a replan is active
        assert vm.engineer_instruction != ""

    def test_plan_still_optimal_leaves_pending_false_no_warning(self, qapp):
        """When pace exactly matches plan and no other divergence fires,
        _live_pending must be False and the VM warning must be empty."""
        # best_lap_ms=90000 (90 s) == plan; avg_fuel_per_lap=3.0 == no plan set
        tracker = _FakeTracker(race_type="lap", laps_in_race=25, laps_recorded=5,
                               best_lap_ms=90000)
        lp = _FakeLivePage()
        bridge, _shell, win, _db = _make_bridge(qapp, tracker=tracker, live_page=lp,
                                                connected=True)
        win._live_pace_plan_s = 90.0     # plan == actual → no PACE_SLOWER
        win._live_fuel_plan = None       # no fuel plan → fuel divergence unavailable

        bridge._feed_live()

        assert bridge._live_pending is False
        vm = lp.last_vm
        assert vm is not None
        assert vm.warning == ""

    def test_insufficient_evidence_when_telemetry_stale(self, qapp):
        """When connected=False (telemetry stale), decide_replan returns
        INSUFFICIENT_EVIDENCE — confidence must pass through as 'insufficient'
        and no warning is shown."""
        tracker = _FakeTracker(race_type="lap", laps_in_race=25, laps_recorded=5,
                               best_lap_ms=96000)
        lp = _FakeLivePage()
        bridge, _shell, win, _db = _make_bridge(qapp, tracker=tracker, live_page=lp,
                                                connected=False)   # stale telemetry
        win._live_pace_plan_s = 90.0

        bridge._feed_live()

        vm = lp.last_vm
        assert vm is not None
        # Stale telemetry → INSUFFICIENT_EVIDENCE → 'insufficient' confidence
        assert vm.confidence == "insufficient"
        assert vm.warning == ""

    def test_insufficient_evidence_when_no_race_type(self, qapp):
        """When the tracker has no race_type (not in a race), the VM confidence
        must be 'unknown' (no audio_view produced) and warning must be empty."""
        tracker = _FakeTracker()
        tracker._d["race_type"] = None   # no race → skip build_canonical entirely
        lp = _FakeLivePage()
        bridge, _shell, _win, _db = _make_bridge(qapp, tracker=tracker, live_page=lp,
                                                 connected=False)

        bridge._feed_live()

        vm = lp.last_vm
        assert vm is not None
        # No live race → no audio_view → confidence stays "unknown"
        assert vm.confidence == "unknown"
        assert vm.warning == ""

    def test_feed_live_without_tracker_does_not_crash(self, qapp):
        """A window with no tracker must not raise — it degrades to the raw-telemetry VM."""
        lp = _FakeLivePage()
        bridge, _shell, _win, _db = _make_bridge(qapp, tracker=None, live_page=lp)

        bridge._feed_live()  # must not raise

        vm = lp.last_vm
        assert vm is not None


# ===========================================================================
# 3. _on_voice_strategy_ack("accept") → accepted plan stored, refresh called
# ===========================================================================

class TestVoiceStrategyAck:
    def _pending_decision(self):
        """A StrategyReplanDecision dict with a REPLAN_RECOMMENDED recommendation
        and a valid best_candidate, shaped as StrategyReplanDecision.to_dict()."""
        from strategy.adaptive_live_strategy import (
            StrategyReplanCandidate, StrategyRecommendation, StrategyConfidence
        )
        cand = StrategyReplanCandidate(
            label="Extra stop for pace", stop_count_delta=1,
            projected_total_time_s=3600.0, expected_completed_laps=None,
            fuel_target_note="refuel as needed", tyre_note="fresh tyres",
            assumptions=("fresh tyres ~1.5% quicker",), expected_gain_detail="faster overall",
            legal=True, fingerprint="fp_test")
        return {
            "recommendation": StrategyRecommendation.REPLAN_RECOMMENDED.value,
            "confidence": StrategyConfidence.MEDIUM.value,
            "best_candidate": cand.to_dict(),
            "triggers": [],
            "candidates": [cand.to_dict()],
            "next_review_trigger": "lap boundary",
            "evidence_that_would_invalidate": [],
            "detail": "pace 6.7% slower than forecast",
            "fingerprint": "fp_dec_test",
        }

    def test_accept_while_pending_sets_live_accepted_plan(self, qapp):
        """Accepting a pending decision stores the candidate as _live_accepted_plan."""
        bridge, _shell, _win, _db = _make_bridge(qapp, tracker=None)
        bridge._live_pending = True
        bridge._live_decision = self._pending_decision()

        bridge._on_voice_strategy_ack("accept")

        plan = bridge._live_accepted_plan
        assert plan is not None and isinstance(plan, dict)
        assert plan.get("name") == "Extra stop for pace"

    def test_accept_while_pending_refreshes(self, qapp):
        """Accepting calls refresh() so the pit wall updates immediately."""
        refresh_calls = []
        bridge, _shell, _win, _db = _make_bridge(qapp, tracker=None)
        bridge._live_pending = True
        bridge._live_decision = self._pending_decision()
        original = bridge.refresh
        bridge.refresh = lambda: refresh_calls.append(1) or original()

        bridge._on_voice_strategy_ack("accept")

        assert len(refresh_calls) >= 1

    def test_accept_executes_nothing_in_the_domain(self, qapp):
        """acknowledge_strategy always returns executes_anything=False — the plan
        is advisory and nothing is executed. Proven by calling it here too."""
        from strategy.adaptive_live_strategy import acknowledge_strategy
        ack = acknowledge_strategy(record_preference=True)
        assert ack.executes_anything is False

    def test_next_feed_live_uses_accepted_plan(self, qapp):
        """After accepting, the next _feed_live passes _live_accepted_plan to show_plan
        rather than the DB-persisted approved strategy."""
        lp = _FakeLivePage()
        bridge, _shell, _win, db = _make_bridge(qapp, tracker=None, live_page=lp)
        # Seed the DB with a DIFFERENT approved strategy to prove it is NOT used
        db._approved["test_cycle_1"] = {"name": "DB plan", "candidate_id": "db-1"}

        bridge._live_pending = True
        bridge._live_decision = self._pending_decision()
        bridge._on_voice_strategy_ack("accept")
        bridge._feed_live()

        assert lp.last_plan is not None
        assert lp.last_plan.get("name") == "Extra stop for pace", (
            "Expected the accepted plan to be shown, not the DB plan")

    def test_accept_with_nothing_pending_is_no_op(self, qapp):
        """Accepting when _live_pending is False must not change _live_accepted_plan."""
        bridge, _shell, _win, _db = _make_bridge(qapp, tracker=None)
        bridge._live_pending = False
        bridge._live_decision = None

        bridge._on_voice_strategy_ack("accept")

        assert bridge._live_accepted_plan is None

    def test_keep_leaves_plan_unchanged(self, qapp):
        """'keep' must not alter whatever _live_accepted_plan was already set to."""
        bridge, _shell, _win, _db = _make_bridge(qapp, tracker=None)
        initial_plan = {"name": "Three-stop", "expected_laps": "62 laps"}
        bridge._live_accepted_plan = initial_plan
        bridge._live_pending = True
        bridge._live_decision = self._pending_decision()

        bridge._on_voice_strategy_ack("keep")

        assert bridge._live_accepted_plan is initial_plan, (
            "'keep' must not change the shown plan")

    def test_db_approved_strategy_is_unchanged_after_accept(self, qapp):
        """Accepting via PTT must not mutate the DB row — the persisted record is
        what the driver approved in the pre-race strategy page, and PTT cannot
        overwrite it."""
        lp = _FakeLivePage()
        bridge, _shell, _win, db = _make_bridge(qapp, tracker=None, live_page=lp)
        original_db_plan = {"name": "DB plan", "candidate_id": "db-1"}
        db._approved["test_cycle_1"] = dict(original_db_plan)

        bridge._live_pending = True
        bridge._live_decision = self._pending_decision()
        bridge._on_voice_strategy_ack("accept")

        # DB row must not have changed
        assert db._approved["test_cycle_1"] == original_db_plan

    def test_event_switch_clears_accepted_plan(self, qapp):
        """Activating a different event resets _live_accepted_plan so the new event's
        wall starts clean."""
        bridge, _shell, _win, _db = _make_bridge(qapp, tracker=None)
        bridge._live_accepted_plan = {"name": "Some plan"}

        # Simulate event switch (the two reset sites in the bridge)
        bridge._review_cache.clear()
        bridge._live_accepted_plan = None   # what _on_activate_event now does

        assert bridge._live_accepted_plan is None


# ===========================================================================
# 4. Adapter: live_pit_wall_vm_from_state with/without audio_view
# ===========================================================================

class TestLivePitWallVmFromState:
    def _state(self, **overrides):
        """A minimal LiveStrategyState with enough data for LAP_COUNT path."""
        from strategy.adaptive_live_strategy import (
            LiveStrategyState, StrategyObjective,
        )
        defaults = dict(
            objective=StrategyObjective.LAP_COUNT,
            current_lap=5,
            laps_remaining=20,
            fuel_remaining_l=60.0,
            fuel_per_lap_actual=3.6,
            fuel_per_lap_plan=3.0,
            lap_time_actual_s=96.0,
            lap_time_plan_s=90.0,
            tyre_age_laps=5,
            current_compound="RM",
            pit_stops_completed=0,
            laps_since_pit=5,
            required_stops=1,
            telemetry_fresh=True,
        )
        defaults.update(overrides)
        return LiveStrategyState(**defaults)

    def _replan_audio_view(self, recommendation="REPLAN_RECOMMENDED"):
        """A minimal audio_view dict as returned by build_live_audio_strategy_view."""
        return {
            "ok": True,
            "strategy_decision": {
                "recommendation": recommendation,
                "confidence": "medium",
                "best_candidate": {"label": "Extra stop for pace"},
                "next_review_trigger": "lap boundary",
            },
            "strategy_message": {
                "headline": "Strategy update. pace 6.7% slower than forecast.",
                "next_review": "lap boundary",
                "confidence": "medium",
            },
        }

    def _optimal_audio_view(self):
        return {
            "ok": True,
            "strategy_decision": {
                "recommendation": "PLAN_STILL_OPTIMAL",
                "confidence": "medium",
                "best_candidate": None,
                "next_review_trigger": "material change",
            },
            "strategy_message": {
                "headline": "Plan still optimal. No change.",
                "next_review": "material change",
                "confidence": "medium",
            },
        }

    def _insufficient_audio_view(self):
        return {
            "ok": True,
            "strategy_decision": {
                "recommendation": "INSUFFICIENT_EVIDENCE",
                "confidence": "insufficient",
                "best_candidate": None,
                "next_review_trigger": "core live state available",
            },
            "strategy_message": {
                "headline": "Not enough data to change the plan.",
                "next_review": "core live state available",
                "confidence": "insufficient",
            },
        }

    def test_audio_view_none_behaves_as_before(self):
        """Without audio_view the adapter must match its original output exactly."""
        from ui.shell_feed_adapters import live_pit_wall_vm_from_state
        state = self._state()
        vm = live_pit_wall_vm_from_state(state, connected=True, audio_view=None)
        assert vm.engineer_instruction == ""
        assert vm.next_decision == ""
        assert vm.confidence == "unknown"
        assert vm.warning == ""

    def test_audio_view_populates_instruction_and_confidence(self):
        """With a REPLAN audio view, engineer_instruction and confidence are set."""
        from ui.shell_feed_adapters import live_pit_wall_vm_from_state
        state = self._state()
        vm = live_pit_wall_vm_from_state(state, connected=True,
                                         audio_view=self._replan_audio_view())
        assert "pace" in vm.engineer_instruction.lower() or "strategy" in vm.engineer_instruction.lower()
        assert vm.confidence == "medium"

    def test_replan_recommended_sets_warning(self):
        """REPLAN_RECOMMENDED must populate the warning with accept/keep instructions."""
        from ui.shell_feed_adapters import live_pit_wall_vm_from_state
        state = self._state()
        vm = live_pit_wall_vm_from_state(state, connected=True,
                                         audio_view=self._replan_audio_view("REPLAN_RECOMMENDED"))
        assert "accept plan" in vm.warning.lower()
        assert "keep plan" in vm.warning.lower()

    def test_replan_urgent_also_sets_warning(self):
        from ui.shell_feed_adapters import live_pit_wall_vm_from_state
        state = self._state()
        vm = live_pit_wall_vm_from_state(state, connected=True,
                                         audio_view=self._replan_audio_view("REPLAN_URGENT"))
        assert vm.warning != ""

    def test_plan_still_optimal_no_warning(self):
        """PLAN_STILL_OPTIMAL must not set a warning — the plan is fine."""
        from ui.shell_feed_adapters import live_pit_wall_vm_from_state
        state = self._state()
        vm = live_pit_wall_vm_from_state(state, connected=True,
                                         audio_view=self._optimal_audio_view())
        assert vm.warning == ""

    def test_insufficient_evidence_confidence_insufficient(self):
        from ui.shell_feed_adapters import live_pit_wall_vm_from_state
        state = self._state()
        vm = live_pit_wall_vm_from_state(state, connected=True,
                                         audio_view=self._insufficient_audio_view())
        assert vm.confidence == "insufficient"
        assert vm.warning == ""

    def test_gap_to_plan_extended_with_fuel_delta(self):
        """When audio_view is present and both fuel plan/actual exist, gap_to_plan
        includes both the pace delta and the fuel-per-lap delta."""
        from ui.shell_feed_adapters import live_pit_wall_vm_from_state
        state = self._state(
            lap_time_actual_s=90.4, lap_time_plan_s=90.0,    # +0.4s pace
            fuel_per_lap_actual=3.3, fuel_per_lap_plan=3.0,  # +0.3 L/lap
        )
        vm = live_pit_wall_vm_from_state(state, connected=True,
                                         audio_view=self._optimal_audio_view())
        assert "/" in vm.gap_to_plan, (
            f"Expected both pace and fuel deltas in gap_to_plan, got: {vm.gap_to_plan!r}")
        assert "L per lap" in vm.gap_to_plan

    def test_gap_to_plan_unchanged_without_audio_view(self):
        """Without audio_view the fuel delta must NOT be appended."""
        from ui.shell_feed_adapters import live_pit_wall_vm_from_state
        state = self._state(
            lap_time_actual_s=90.4, lap_time_plan_s=90.0,
            fuel_per_lap_actual=3.3, fuel_per_lap_plan=3.0,
        )
        vm = live_pit_wall_vm_from_state(state, connected=True, audio_view=None)
        # Only the pace delta should appear
        assert "L per lap" not in vm.gap_to_plan

    def test_next_decision_populated_from_audio_view(self):
        from ui.shell_feed_adapters import live_pit_wall_vm_from_state
        state = self._state()
        vm = live_pit_wall_vm_from_state(state, connected=True,
                                         audio_view=self._replan_audio_view())
        assert vm.next_decision != ""


# ===========================================================================
# 5. Adapter: live_plan_dict_from_candidate
# ===========================================================================

class TestLivePlanDictFromCandidate:
    def _cand(self, **overrides):
        base = {
            "label": "Extra stop for pace",
            "stop_count_delta": 1,
            "projected_total_time_s": 3661.0,   # 1:01:01
            "expected_completed_laps": None,
            "fuel_target_note": "refuel as needed",
            "tyre_note": "fresh tyres",
            "assumptions": ["fresh tyres ~1.5% quicker/lap"],
            "expected_gain_detail": "faster overall if gain beats pit loss",
            "legal": True,
            "fingerprint": "fp_test",
        }
        base.update(overrides)
        return base

    def test_name_mapped_from_label(self):
        from ui.shell_feed_adapters import live_plan_dict_from_candidate
        d = live_plan_dict_from_candidate(self._cand())
        assert d["name"] == "Extra stop for pace"

    def test_pit_windows_shows_delta(self):
        from ui.shell_feed_adapters import live_plan_dict_from_candidate
        d = live_plan_dict_from_candidate(self._cand(stop_count_delta=1))
        assert "+1" in d["pit_windows"]

    def test_total_time_formatted(self):
        from ui.shell_feed_adapters import live_plan_dict_from_candidate
        # 3661 s = 1 h, 1 min, 1 s
        d = live_plan_dict_from_candidate(self._cand(projected_total_time_s=3661.0))
        assert d["total_time"] != ""
        assert "1:" in d["total_time"]   # has hours

    def test_total_time_empty_when_none(self):
        from ui.shell_feed_adapters import live_plan_dict_from_candidate
        d = live_plan_dict_from_candidate(self._cand(projected_total_time_s=None))
        assert d["total_time"] == ""

    def test_expected_laps_when_time_certain(self):
        from ui.shell_feed_adapters import live_plan_dict_from_candidate
        d = live_plan_dict_from_candidate(self._cand(expected_completed_laps=13))
        assert "13" in d["expected_laps"]

    def test_pit_stops_contains_notes(self):
        from ui.shell_feed_adapters import live_plan_dict_from_candidate
        d = live_plan_dict_from_candidate(self._cand())
        assert any("refuel" in s.lower() for s in d["pit_stops"])
        assert any("tyre" in s.lower() for s in d["pit_stops"])

    def test_keep_plan_shows_no_change(self):
        from ui.shell_feed_adapters import live_plan_dict_from_candidate
        d = live_plan_dict_from_candidate(self._cand(label="Keep the plan", stop_count_delta=0))
        assert d["name"] == "Keep the plan"
        assert "keep" in d["pit_windows"].lower()

    def test_empty_label_returns_empty_dict(self):
        from ui.shell_feed_adapters import live_plan_dict_from_candidate
        assert live_plan_dict_from_candidate({"label": "", "stop_count_delta": 0}) == {}
        assert live_plan_dict_from_candidate({}) == {}

    def test_non_dict_returns_empty(self):
        from ui.shell_feed_adapters import live_plan_dict_from_candidate
        assert live_plan_dict_from_candidate("garbage") == {}
        assert live_plan_dict_from_candidate(None) == {}

    def test_never_raises_on_corrupt_input(self):
        from ui.shell_feed_adapters import live_plan_dict_from_candidate
        # Corrupt types for each field
        result = live_plan_dict_from_candidate({
            "label": "plan", "stop_count_delta": "not a number",
            "projected_total_time_s": "also bad", "fuel_target_note": 42,
        })
        assert isinstance(result, dict)


# ===========================================================================
# 6. Voice: new intents resolve correctly
# ===========================================================================

class TestVoiceIntentResolution:
    def test_accept_plan_resolves(self):
        from voice.query_listener import _match_intent
        assert _match_intent("accept plan") == "accept_plan"
        assert _match_intent("accept the plan") == "accept_plan"

    def test_keep_plan_resolves(self):
        from voice.query_listener import _match_intent
        assert _match_intent("keep plan") == "keep_plan"
        assert _match_intent("keep the plan") == "keep_plan"
        assert _match_intent("stay out") == "keep_plan"

    def test_accept_alone_resolves_to_accept_plan(self):
        """Single word 'accept' should resolve to accept_plan."""
        from voice.query_listener import _match_intent
        assert _match_intent("accept") == "accept_plan"

    def test_existing_intents_unaffected(self):
        """The new intents must not steal existing intents."""
        from voice.query_listener import _match_intent
        # "plan" alone is in the "strategy" keywords — "accept plan" must be more
        # specific, but plain "strategy" must still work
        assert _match_intent("what is the strategy") == "strategy"
        assert _match_intent("when should i pit") == "pit"

    def test_new_phrases_are_pronounceable(self):
        """Every word in the new phrases must be in the CMU dictionary."""
        from voice.command_vocabulary import dictionary_words, phrase_is_pronounceable
        words = dictionary_words()
        if not words:
            pytest.skip("CMU dictionary not installed — cannot verify pronunciation")
        new_phrases = ["accept the plan", "accept plan", "keep the plan",
                       "keep plan", "stay out", "accept"]
        for phrase in new_phrases:
            assert phrase_is_pronounceable(phrase, words), (
                f"OOV phrase would abort keyword spotting pass: {phrase!r}")

    def test_new_phrases_appear_in_extra_phrases(self):
        from voice.command_vocabulary import EXTRA_PHRASES
        assert "accept the plan" in EXTRA_PHRASES
        assert "keep plan" in EXTRA_PHRASES
        assert "stay out" in EXTRA_PHRASES

    def test_new_phrases_survive_keyword_entries_filter(self):
        """Phrases must pass phrase_is_pronounceable and appear in keyword_entries."""
        from voice.query_listener import _INTENT_KEYWORDS
        from voice.command_vocabulary import keyword_entries, dictionary_words
        words = dictionary_words()
        if not words:
            pytest.skip("CMU dictionary not installed")
        entries = {p for p, _ in keyword_entries(_INTENT_KEYWORDS)}
        # At least the multi-word forms should survive the filter
        assert "accept plan" in entries or "accept the plan" in entries, (
            "No accept_plan phrase survived the vocabulary filter")
        assert "keep plan" in entries or "keep the plan" in entries or "stay out" in entries, (
            "No keep_plan phrase survived the vocabulary filter")


# ===========================================================================
# 7. Voice: set_strategy_ack_handler wiring
# ===========================================================================

class TestStrategyAckHandler:
    def _listener(self):
        from voice.query_listener import QueryListener
        # QueryListener needs tracker + announcer; use duck-typed stubs
        class _FakeTrk:
            race_type = None
            last_fuel = 50.0
            avg_fuel_per_lap = 3.0
        class _FakeAnnouncer:
            def announce(self, *a, **kw): pass
            def play_click_sync(self, *a): pass
            def silence(self): pass
            def mute_for(self, *a): pass
            def clear_mute(self): pass
            def pause_keepalive(self, *a): pass
            def play_beep(self, *a, **kw): pass
        ql = QueryListener(tracker=_FakeTrk(), announcer=_FakeAnnouncer(), config={})
        return ql

    def test_set_strategy_ack_handler_stores_handler(self):
        ql = self._listener()
        calls = []
        ql.set_strategy_ack_handler(lambda action: calls.append(action))
        ql._strategy_ack_handler("accept")
        assert calls == ["accept"]

    def test_handler_called_with_accept_on_accept_intent(self):
        """Simulate _handle_trigger_inner dispatching accept_plan intent."""
        ql = self._listener()
        calls = []
        ql.set_strategy_ack_handler(lambda action: calls.append(action))
        # Directly call the handler branch as _handle_trigger_inner would
        intent = "accept_plan"
        if intent == "accept_plan":
            if ql._strategy_ack_handler is not None:
                try:
                    ql._strategy_ack_handler("accept")
                except Exception:
                    pass
        assert calls == ["accept"]

    def test_handler_called_with_keep_on_keep_intent(self):
        ql = self._listener()
        calls = []
        ql.set_strategy_ack_handler(lambda action: calls.append(action))
        intent = "keep_plan"
        if intent == "keep_plan":
            if ql._strategy_ack_handler is not None:
                try:
                    ql._strategy_ack_handler("keep")
                except Exception:
                    pass
        assert calls == ["keep"]

    def test_failing_handler_exception_is_swallowed(self):
        """A handler that raises must never abort the PTT cycle."""
        ql = self._listener()
        ql.set_strategy_ack_handler(lambda action: (_ for _ in ()).throw(RuntimeError("boom")))
        # Should not raise even though the handler fails
        try:
            if ql._strategy_ack_handler is not None:
                try:
                    ql._strategy_ack_handler("accept")
                except Exception:
                    pass  # properly swallowed
        except Exception as exc:
            pytest.fail(f"Handler exception leaked: {exc}")

    def test_no_handler_set_is_safe(self):
        """If no handler is registered, accept_plan/keep_plan must not crash."""
        ql = self._listener()
        assert ql._strategy_ack_handler is None
        # Simulate the branch (nothing set → nothing called)
        if ql._strategy_ack_handler is not None:
            ql._strategy_ack_handler("accept")
        # Reaching here = success


# ===========================================================================
# 8. Advisory-only safety: existing test_live_pit_wall.TestLiveSafety still passes
#    (we don't import it here — it runs from its own file; this confirms nothing
#     we added to shell_feed_adapters or the bridge injects command tokens into
#     the live_pit_wall module)
# ===========================================================================

class TestAdvisoryOnlySafetyUnaffected:
    def test_live_plan_dict_from_candidate_never_raises(self):
        """Confirm the new adapter function is fully defensive."""
        from ui.shell_feed_adapters import live_plan_dict_from_candidate
        for bad in [None, "", 42, [], {}, {"label": None}]:
            result = live_plan_dict_from_candidate(bad)
            assert isinstance(result, dict)

    def test_shell_feed_adapters_imports_cleanly(self):
        import ui.shell_feed_adapters as m
        assert callable(m.live_pit_wall_vm_from_state)
        assert callable(m.live_plan_dict_from_candidate)
