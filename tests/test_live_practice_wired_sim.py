"""Live Activation 1 — wired-stack simulation of the Practice recording orchestration.

Drives the REAL LivePracticeCoordinator (not a re-implemented mock) through the full §12
scenario with a fake persistence port, proving the production decision + persistence flow:
select event → planned Practice session → authoritative run → connect → laps → reject an
invalid lap → disconnect/reconnect → complete → "restart" → verify history → switch event
with no data leakage.
"""
from __future__ import annotations

from strategy.live_practice_activation import LiveRunState
from strategy.live_practice_runtime import LivePracticeCoordinator


class FakePort:
    """A production-shaped port: it persists runs + laps and hands back the resolved context."""

    def __init__(self, context):
        self._context = dict(context)
        self.runs = {}          # run_id -> {"status":..., "identity":..., "laps":[...]}
        self.laps = []          # every persisted lap (bound to a run)
        self._run_seq = 0
        self._stint_seq = 0

    # -- port surface ------------------------------------------------------ #
    def resolve_activation_context(self):
        return dict(self._context)

    def create_run(self, identity):
        self._run_seq += 1
        self._stint_seq += 1
        run_id = f"run-{self._run_seq}"
        stint_id = f"stint-{self._stint_seq}"
        self.runs[run_id] = {"status": "starting", "identity": dict(identity),
                             "stint_id": stint_id, "event_id": identity.get("event_id")}
        return run_id, stint_id

    def persist_lap(self, *, run_id, stint_id, lap_number, lap_time_ms, valid, invalid_reasons):
        self.laps.append({"run_id": run_id, "stint_id": stint_id, "lap_number": lap_number,
                          "lap_time_ms": lap_time_ms, "valid": valid,
                          "invalid_reasons": list(invalid_reasons),
                          "event_id": self.runs[run_id]["event_id"]})

    def set_run_status(self, run_id, status):
        self.runs[run_id]["status"] = status

    # -- test helpers ------------------------------------------------------ #
    def switch_event(self, new_context):
        self._context = dict(new_context)

    def laps_for_run(self, run_id):
        return [l for l in self.laps if l["run_id"] == run_id]


def _ctx(event_id="42", plan="plan-1", programme="prog-1"):
    return {"planned_session_type": "Practice", "event_programme_id": programme,
            "event_id": event_id, "session_plan_id": plan, "car_id": "333",
            "car_spec_revision_id": "spec-1", "driver_profile_version_id": "drv-1",
            "context_revision_id": "ctx-1", "setup_snapshot_id": "setup-1",
            "track_model_version_id": "trk-1"}


def test_full_practice_run_lifecycle_persists_correctly():
    port = FakePort(_ctx())
    co = LivePracticeCoordinator(port)

    # 3. start the authoritative run
    act = co.activate()
    assert act.ok and co.run_id == "run-1" and co.state == LiveRunState.STARTING

    # 4. connect telemetry → RECORDING
    assert co.telemetry_connected() and co.is_recording

    # 5. complete valid laps
    for ln, t in [(1, 91000), (2, 89000), (3, 88500)]:
        out = co.on_lap(session_run_id="run-1", event_id="42", lap_number=ln, lap_time_ms=t)
        assert out.recorded and out.valid
    assert co.valid_lap_count == 3

    # 6. reject an invalid / incomplete lap (pit lap records but does not count)
    pit = co.on_lap(session_run_id="run-1", event_id="42", lap_number=4, lap_time_ms=120000,
                    is_pit_lap=True)
    assert pit.recorded and not pit.valid and "pit_lap" in pit.invalid_reasons
    assert co.valid_lap_count == 3

    # a stale-run lap and a zero-length lap write nothing
    assert not co.on_lap(session_run_id="ghost", event_id="42", lap_number=5, lap_time_ms=90000).recorded
    assert not co.on_lap(session_run_id="run-1", event_id="42", lap_number=5, lap_time_ms=0).recorded

    # 7. disconnect and reconnect the SAME event/plan → resumes the SAME run
    assert co.telemetry_lost() and co.state == LiveRunState.DISCONNECTED
    from strategy.live_practice_activation import ReconnectAction
    assert co.reconnect(incoming_event_id="42", incoming_session_plan_id="plan-1") \
        == ReconnectAction.RESUME_SAME_RUN
    assert co.run_id == "run-1" and co.is_recording

    out = co.on_lap(session_run_id="run-1", event_id="42", lap_number=5, lap_time_ms=88000)
    assert out.recorded and out.valid and co.valid_lap_count == 4

    # 8/9. complete the objective + end the run
    assert co.complete() and co.state == LiveRunState.COMPLETED
    assert port.runs["run-1"]["status"] == "completed"

    # every persisted lap traces to run-1 + event 42
    assert all(l["run_id"] == "run-1" and l["event_id"] == "42" for l in port.laps)


def test_restart_does_not_reopen_completed_run():
    port = FakePort(_ctx())
    co = LivePracticeCoordinator(port)
    co.activate(); co.telemetry_connected()
    co.on_lap(session_run_id="run-1", event_id="42", lap_number=1, lap_time_ms=90000)
    co.complete()
    # "restart": a fresh coordinator over the same port. The completed run is history; a new
    # activate() must create a DISTINCT run, never reopen run-1.
    co2 = LivePracticeCoordinator(port)
    co2.activate()
    assert co2.run_id == "run-2" and co2.run_id != "run-1"
    assert port.runs["run-1"]["status"] == "completed"


def test_event_switch_blocked_while_recording_then_no_leakage():
    port = FakePort(_ctx(event_id="42", plan="plan-1"))
    co = LivePracticeCoordinator(port)
    co.activate(); co.telemetry_connected()
    co.on_lap(session_run_id="run-1", event_id="42", lap_number=1, lap_time_ms=90000)

    # 12a. switching event mid-recording is blocked
    ok, _reason = co.can_switch_event()
    assert ok is False

    # a lap arriving tagged with the NEW event never cross-writes to run-1
    assert not co.on_lap(session_run_id="run-1", event_id="99", lap_number=2, lap_time_ms=90000).recorded

    # complete, then switching is allowed; a new event's run is fully separate
    co.complete()
    ok, _ = co.can_switch_event()
    assert ok is True
    port.switch_event(_ctx(event_id="99", plan="plan-9"))
    co2 = LivePracticeCoordinator(port)
    co2.activate(); co2.telemetry_connected()
    co2.on_lap(session_run_id=co2.run_id, event_id="99", lap_number=1, lap_time_ms=90000)
    # no lap from the new run is attached to event 42's run, and vice-versa
    assert all(l["event_id"] == "42" for l in port.laps_for_run("run-1"))
    assert all(l["event_id"] == "99" for l in port.laps_for_run(co2.run_id))


def test_activation_blocked_leaves_no_run():
    ctx = _ctx()
    ctx["car_spec_revision_id"] = ""                    # missing required context
    port = FakePort(ctx)
    co = LivePracticeCoordinator(port)
    act = co.activate()
    assert not act.ok and "car_spec_revision_id" in act.missing
    assert co.run_id == "" and co.state == LiveRunState.NOT_STARTED and port.runs == {}


def test_wrong_session_type_never_records_practice():
    port = FakePort(_ctx())
    port._context["planned_session_type"] = "Qualifying"
    co = LivePracticeCoordinator(port)
    act = co.activate()
    assert not act.ok and co.run_id == "" and port.runs == {}
