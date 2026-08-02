"""Live Activation 3 — the LiveRaceCoordinator orchestration against a fake port. Offline,
deterministic; proves the coordinator gates, records and finalises correctly without a DB."""
from __future__ import annotations

from strategy.live_practice_activation import LiveRunState, ReconnectAction
from strategy.live_race_runtime import LiveRaceCoordinator
from strategy.race_engineer_state_machine import RaceEngineerEvent, events_from_race_signals


def _race_ctx(**over):
    ctx = dict(
        event_programme_id="ep1", event_id="7", session_plan_id="sp1", car_id="42",
        car_spec_revision_id="csr1", driver_profile_version_id="dpv1", context_revision_id="fp1",
        planned_session_type="Race",
        race_plan_id="rp1", race_plan_revision_id="rev3",
        plan_event_id="7", plan_car_id="42", plan_track_id="wg", plan_layout_id="full",
        track_id="wg", layout_id="full",
    )
    ctx.update(over)
    return ctx


class FakePort:
    def __init__(self, ctx):
        self.ctx = ctx
        self.created = 0
        self.laps = []
        self.status = []

    def resolve_activation_context(self):
        return self.ctx

    def create_run(self, identity):
        self.created += 1
        return ("run-1", "stint-1")

    def persist_lap(self, **k):
        self.laps.append(k)

    def set_run_status(self, run_id, status):
        self.status.append(status)


def _active_coordinator(**over):
    co = LiveRaceCoordinator(FakePort(_race_ctx(**over)))
    co.activate()
    co.telemetry_connected()
    return co


# ================================ activation =================================
def test_activation_opens_one_run_and_carries_plan_identity():
    port = FakePort(_race_ctx())
    co = LiveRaceCoordinator(port)
    act = co.activate()
    assert act.ok and co.run_id == "run-1" and port.created == 1
    assert co.state == LiveRunState.STARTING
    assert co.identity["race_plan_id"] == "rp1"
    assert co.identity["race_plan_revision_id"] == "rev3"


def test_blocked_plan_mismatch_creates_no_run():
    port = FakePort(_race_ctx(plan_car_id="999"))
    co = LiveRaceCoordinator(port)
    act = co.activate()
    assert not act.ok and co.run_id == "" and port.created == 0
    assert co.state == LiveRunState.NOT_STARTED
    assert "car" in co.plan_block


def test_blocked_car_zero_creates_no_run():
    port = FakePort(_race_ctx(car_id="0"))
    co = LiveRaceCoordinator(port)
    assert not co.activate().ok
    assert port.created == 0 and co.state == LiveRunState.NOT_STARTED


def test_blocked_missing_race_plan_creates_no_run():
    port = FakePort(_race_ctx(race_plan_id=""))
    co = LiveRaceCoordinator(port)
    assert not co.activate().ok and port.created == 0


# ============================== lap recording ================================
def test_records_valid_laps():
    co = _active_coordinator()
    for e in events_from_race_signals("idle", "racing"):
        co.apply_race_event(e)
    out = co.on_lap(session_run_id="run-1", event_id="7", lap_number=1, lap_time_ms=95000)
    assert out.recorded and out.valid
    assert co.completed_laps == 1 and co.valid_lap_count == 1


def test_duplicate_lap_number_rejected():
    co = _active_coordinator()
    co.on_lap(session_run_id="run-1", event_id="7", lap_number=1, lap_time_ms=95000)
    dup = co.on_lap(session_run_id="run-1", event_id="7", lap_number=1, lap_time_ms=94000)
    assert not dup.recorded
    assert len(co._port.laps) == 1


def test_cross_event_lap_rejected():
    co = _active_coordinator()
    out = co.on_lap(session_run_id="run-1", event_id="99", lap_number=1, lap_time_ms=95000)
    assert not out.recorded and co._port.laps == []


def test_lap_rejected_when_not_recording():
    port = FakePort(_race_ctx())
    co = LiveRaceCoordinator(port)
    co.activate()  # STARTING, not RECORDING
    out = co.on_lap(session_run_id="run-1", event_id="7", lap_number=1, lap_time_ms=95000)
    assert not out.recorded


def test_pit_lap_recorded_but_invalid():
    co = _active_coordinator()
    out = co.on_lap(session_run_id="run-1", event_id="7", lap_number=1, lap_time_ms=120000,
                    is_pit_lap=True)
    assert out.recorded and not out.valid
    assert co.invalid_lap_count == 1 and "pit_lap" in out.invalid_reasons


# =========================== telemetry lifecycle =============================
def test_telemetry_lost_and_resume_same_run():
    co = _active_coordinator()
    assert co.is_recording
    co.telemetry_lost()
    assert co.state == LiveRunState.DISCONNECTED
    action = co.reconnect(incoming_event_id="7", incoming_session_plan_id="sp1")
    assert action == ReconnectAction.RESUME_SAME_RUN and co.is_recording


def test_reconnect_different_event_requires_new_run():
    co = _active_coordinator()
    co.telemetry_lost()
    action = co.reconnect(incoming_event_id="8", incoming_session_plan_id="sp1")
    assert action == ReconnectAction.REQUIRE_NEW_RUN
    assert co.state == LiveRunState.DISCONNECTED  # never silently resumed


# ============================ completion / switch ============================
def test_complete_finalises_and_reaches_finished_phase():
    co = _active_coordinator()
    co.on_lap(session_run_id="run-1", event_id="7", lap_number=1, lap_time_ms=95000)
    assert co.complete()
    assert co.state == LiveRunState.COMPLETED
    assert co.phase == "finished"
    assert "completed" in co._port.status


def test_event_switch_blocked_while_recording():
    co = _active_coordinator()
    ok, reason = co.can_switch_event()
    assert not ok and "abandon" in reason.lower()


def test_event_switch_allowed_after_complete():
    co = _active_coordinator()
    co.complete()
    ok, _ = co.can_switch_event()
    assert ok


def test_abandon_then_terminal():
    co = _active_coordinator()
    assert co.abandon()
    assert co.state == LiveRunState.ABANDONED
    # a finalize after abandon cannot reopen
    assert not co.complete()
