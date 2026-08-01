"""Live Activation 2 — qualifying gate + coordinator (offline).

Proves the authoritative QUALIFYING gate and the coordinator that composes the generic recording
lifecycle with the qualifying phase machine (out-lap → flying lap → PB/deleted → cooldown).
"""
from __future__ import annotations

from strategy.live_practice_activation import (
    ActivationVerdict, LiveRunState, ReconnectAction, resolve_live_qualifying_activation,
)
from strategy.live_qualifying_runtime import LiveQualifyingCoordinator


def _ctx(session_type="Qualifying", **over):
    ctx = {
        "planned_session_type": session_type, "event_programme_id": "cyc-1", "event_id": "42",
        "session_plan_id": "plan-q", "car_id": "333", "car_spec_revision_id": "spec-1",
        "driver_profile_version_id": "drv-1", "context_revision_id": "ctx-1",
        "setup_snapshot_id": "setup-1", "track_model_version_id": "trk-1",
    }
    ctx.update(over)
    return ctx


# --------------------------------------------------------------------------- gate
def test_qualifying_gate_activates_on_a_qualifying_plan():
    a = resolve_live_qualifying_activation(_ctx(), planned_session_type="Qualifying")
    assert a.ok and a.identity["session_type"] == "qualifying"


def test_qualifying_gate_blocks_a_practice_plan():
    a = resolve_live_qualifying_activation(_ctx(session_type="Practice"),
                                           planned_session_type="Practice")
    assert not a.ok and a.verdict == ActivationVerdict.BLOCKED_WRONG_SESSION_TYPE
    assert "Qualifying" in a.reason


def test_qualifying_gate_blocks_missing_context():
    a = resolve_live_qualifying_activation(_ctx(car_spec_revision_id=""),
                                           planned_session_type="Qualifying")
    assert not a.ok and "car_spec_revision_id" in a.missing


# --------------------------------------------------------------------------- coordinator
class FakePort:
    def __init__(self, ctx):
        self._ctx = dict(ctx)
        self.laps = []
        self.runs = {}
        self._n = 0

    def resolve_activation_context(self):
        return dict(self._ctx)

    def create_run(self, identity):
        self._n += 1
        rid = f"qrun-{self._n}"
        self.runs[rid] = {"status": "starting", "event_id": identity.get("event_id")}
        return rid, f"stint-{self._n}"

    def persist_lap(self, **kw):
        self.laps.append(kw)

    def set_run_status(self, run_id, status):
        self.runs[run_id]["status"] = status


def _running():
    co = LiveQualifyingCoordinator(FakePort(_ctx()))
    assert co.activate().ok and co.telemetry_connected()
    return co


def test_full_qualifying_attempt_tracks_best_lap():
    co = _running()
    assert co.phase == "preparation"

    co.pit_exit()
    assert co.phase == "out_lap" and co.attempt == 1
    # out-lap completes → flying lap underway
    co.on_lap(session_run_id=co.run_id, event_id="42", lap_number=1, lap_time_ms=140000,
              is_out_lap=True)
    assert co.phase == "flying_lap"
    # flying lap → personal best
    out = co.on_lap(session_run_id=co.run_id, event_id="42", lap_number=2, lap_time_ms=90000)
    assert out.recorded and out.valid
    assert co.phase == "lap_complete" and co.best_lap_ms == 90000
    assert co.qstate.last_lap_was_pb is True

    # cool down, go again, improve
    co.cooldown()
    co.pit_exit()
    assert co.attempt == 2
    co.on_lap(session_run_id=co.run_id, event_id="42", lap_number=3, lap_time_ms=141000, is_out_lap=True)
    co.on_lap(session_run_id=co.run_id, event_id="42", lap_number=4, lap_time_ms=89000)
    assert co.best_lap_ms == 89000

    # a deleted flying lap does NOT improve the best
    co.cooldown(); co.pit_exit()
    co.on_lap(session_run_id=co.run_id, event_id="42", lap_number=5, lap_time_ms=142000, is_out_lap=True)
    co.on_lap(session_run_id=co.run_id, event_id="42", lap_number=6, lap_time_ms=88000,
              valid=False, invalidation_reason="track limits")
    assert co.best_lap_ms == 89000                 # unchanged
    assert co.qstate.last_lap_valid is False

    assert co.complete() and co.state == LiveRunState.COMPLETED


def test_cue_tracks_the_phase():
    co = _running()
    assert "one lap" in co.cue().lower()                          # preparation
    co.pit_exit()
    assert "out-lap" in co.cue().lower()                          # out lap
    co.on_lap(session_run_id=co.run_id, event_id="42", lap_number=1, lap_time_ms=140000, is_out_lap=True)
    assert "commit" in co.cue().lower()                          # flying lap — terse
    co.on_lap(session_run_id=co.run_id, event_id="42", lap_number=2, lap_time_ms=90000)
    assert "personal best" in co.cue().lower()                   # PB report


def test_box_returns_to_preparation():
    co = _running()
    co.pit_exit()
    co.box()
    assert co.phase == "preparation"


def test_stale_and_zero_laps_rejected_and_switch_guarded():
    co = _running()
    co.pit_exit()
    assert not co.on_lap(session_run_id="ghost", event_id="42", lap_number=1, lap_time_ms=90000).recorded
    assert not co.on_lap(session_run_id=co.run_id, event_id="42", lap_number=1, lap_time_ms=0).recorded
    ok, _ = co.can_switch_event()
    assert ok is False                              # can't switch while recording


def test_reconnect_resumes_same_run():
    co = _running()
    rid = co.run_id
    co.telemetry_lost()
    assert co.state == LiveRunState.DISCONNECTED
    assert co.reconnect(incoming_event_id="42", incoming_session_plan_id="plan-q") \
        == ReconnectAction.RESUME_SAME_RUN
    assert co.is_recording and co.run_id == rid


def test_blocked_activation_creates_no_run():
    port = FakePort(_ctx(planned_session_type="Practice"))
    co = LiveQualifyingCoordinator(port)
    assert not co.activate().ok
    assert co.run_id == "" and port.runs == {}
