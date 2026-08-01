"""Live Activation 1 — pure activation/lifecycle/lap/reconnect/switch decisions.

Offline, deterministic proof of the authoritative Practice-recording rules. No Qt, no DB.
"""
from __future__ import annotations

from strategy.live_practice_activation import (
    ActivationVerdict, EventSwitchAction, LiveRunEvent, LiveRunState, ReconnectAction,
    REQUIRED_CONTEXT, advance_live_run, evaluate_live_lap, is_recording_open,
    resolve_event_switch, resolve_live_practice_activation, resolve_reconnect,
)


def _full_ctx(**over):
    ctx = {
        "event_programme_id": "prog-1", "event_id": "42", "session_plan_id": "plan-1",
        "car_id": "333", "car_spec_revision_id": "spec-1", "driver_profile_version_id": "drv-1",
        "context_revision_id": "ctx-1", "setup_snapshot_id": "setup-1",
        "track_model_version_id": "trk-1",
    }
    ctx.update(over)
    return ctx


# --------------------------------------------------------------------------- A. gate
def test_full_context_practice_activates():
    a = resolve_live_practice_activation(_full_ctx(), planned_session_type="Practice")
    assert a.ok and a.verdict == ActivationVerdict.ACTIVATED
    assert a.identity["event_id"] == "42" and a.identity["session_type"] == "practice"
    assert a.identity["setup_snapshot_id"] == "setup-1"


def test_wrong_session_type_blocks_even_with_full_context():
    for st in ("Qualifying", "Race", "", "practice-ish"):
        a = resolve_live_practice_activation(_full_ctx(), planned_session_type=st)
        assert not a.ok and a.verdict == ActivationVerdict.BLOCKED_WRONG_SESSION_TYPE


def test_each_missing_required_field_blocks_with_exact_name():
    for fieldname in REQUIRED_CONTEXT:
        a = resolve_live_practice_activation(
            _full_ctx(**{fieldname: ""}), planned_session_type="Practice")
        assert not a.ok and a.verdict == ActivationVerdict.BLOCKED_INCOMPLETE_CONTEXT
        assert fieldname in a.missing and fieldname in a.reason


def test_zero_valued_id_counts_as_missing():
    a = resolve_live_practice_activation(_full_ctx(event_id="0"), planned_session_type="Practice")
    assert not a.ok and "event_id" in a.missing


def test_optional_fields_absent_do_not_block():
    a = resolve_live_practice_activation(
        _full_ctx(setup_snapshot_id="", track_model_version_id=""), planned_session_type="Practice")
    assert a.ok
    assert a.identity["setup_snapshot_id"] == "" and a.identity["track_model_version_id"] == ""


def test_gate_never_raises_on_garbage():
    assert resolve_live_practice_activation(None, planned_session_type=None).verdict \
        == ActivationVerdict.BLOCKED_WRONG_SESSION_TYPE


# --------------------------------------------------------------------------- B. FSM
def test_happy_path_lifecycle():
    st = LiveRunState.NOT_STARTED
    for ev, exp in [
        (LiveRunEvent.START, LiveRunState.STARTING),
        (LiveRunEvent.CONFIRM_RECORDING, LiveRunState.RECORDING),
        (LiveRunEvent.BEGIN_COMPLETE, LiveRunState.COMPLETING),
        (LiveRunEvent.FINALIZE, LiveRunState.COMPLETED),
    ]:
        t = advance_live_run(st, ev)
        assert t.ok and t.state == exp
        st = t.state


def test_completed_run_never_reopens():
    for ev in LiveRunEvent:
        t = advance_live_run(LiveRunState.COMPLETED, ev)
        assert not t.ok and t.state == LiveRunState.COMPLETED


def test_cannot_start_twice_or_from_recording():
    assert not advance_live_run(LiveRunState.RECORDING, LiveRunEvent.START).ok
    assert not advance_live_run(LiveRunState.STARTING, LiveRunEvent.START).ok


def test_reconnect_is_restore_not_new_start():
    # telemetry lost then restored returns to RECORDING via TELEMETRY_RESTORED, not START
    t = advance_live_run(LiveRunState.RECORDING, LiveRunEvent.TELEMETRY_LOST)
    assert t.state == LiveRunState.DISCONNECTED
    assert advance_live_run(t.state, LiveRunEvent.START).ok is False
    assert advance_live_run(t.state, LiveRunEvent.TELEMETRY_RESTORED).state == LiveRunState.RECORDING


def test_abandon_from_any_active_state():
    for st in (LiveRunState.STARTING, LiveRunState.RECORDING, LiveRunState.PAUSED,
               LiveRunState.DISCONNECTED, LiveRunState.COMPLETING):
        assert advance_live_run(st, LiveRunEvent.ABANDON).state == LiveRunState.ABANDONED


def test_is_recording_open_only_when_recording():
    assert is_recording_open(LiveRunState.RECORDING)
    for st in (LiveRunState.PAUSED, LiveRunState.DISCONNECTED, LiveRunState.COMPLETED,
               LiveRunState.NOT_STARTED):
        assert not is_recording_open(st)


# --------------------------------------------------------------------------- C. reconnect
def test_reconnect_same_event_plan_resumes_same_run():
    d = resolve_reconnect(authorised_run_id="run-1", run_state=LiveRunState.DISCONNECTED,
                          incoming_event_id="42", incoming_session_plan_id="plan-1",
                          authorised_event_id="42", authorised_session_plan_id="plan-1")
    assert d.action == ReconnectAction.RESUME_SAME_RUN and d.run_id == "run-1"


def test_reconnect_different_event_requires_new_run():
    d = resolve_reconnect(authorised_run_id="run-1", run_state=LiveRunState.DISCONNECTED,
                          incoming_event_id="99", incoming_session_plan_id="plan-9",
                          authorised_event_id="42", authorised_session_plan_id="plan-1")
    assert d.action == ReconnectAction.REQUIRE_NEW_RUN


def test_reconnect_never_reopens_completed():
    d = resolve_reconnect(authorised_run_id="run-1", run_state=LiveRunState.COMPLETED,
                          incoming_event_id="42", incoming_session_plan_id="plan-1",
                          authorised_event_id="42", authorised_session_plan_id="plan-1")
    assert d.action == ReconnectAction.REQUIRE_NEW_RUN


# --------------------------------------------------------------------------- D. lap guard
def _lap(**over):
    kw = dict(run_state=LiveRunState.RECORDING, lap_session_run_id="run-1",
              active_session_run_id="run-1", lap_event_id="42", active_event_id="42",
              lap_number=3, last_finalised_lap=2, lap_time_ms=85000)
    kw.update(over)
    return evaluate_live_lap(**kw)


def test_valid_lap_records_and_counts():
    d = _lap()
    assert d.record and d.valid and not d.invalid_reasons


def test_lap_rejected_when_not_recording():
    assert not _lap(run_state=LiveRunState.DISCONNECTED).record
    assert not _lap(run_state=LiveRunState.COMPLETED).record


def test_stale_run_and_other_event_rejected():
    assert not _lap(lap_session_run_id="other").record
    assert not _lap(lap_event_id="99").record


def test_duplicate_or_reset_lap_number_rejected():
    assert not _lap(lap_number=2, last_finalised_lap=2).record   # duplicate
    assert not _lap(lap_number=1, last_finalised_lap=5).record   # counter reset / replay


def test_zero_length_lap_rejected():
    assert not _lap(lap_time_ms=0).record


def test_pit_out_incomplete_recorded_but_invalid():
    for kw, tag in [({"is_pit_lap": True}, "pit_lap"), ({"is_out_lap": True}, "out_lap"),
                    ({"telemetry_complete": False}, "incomplete_telemetry")]:
        d = _lap(**kw)
        assert d.record and not d.valid and tag in d.invalid_reasons


# --------------------------------------------------------------------------- E. event switch
def test_switch_allowed_only_when_no_active_run():
    for st in (LiveRunState.NOT_STARTED, LiveRunState.COMPLETED, LiveRunState.ABANDONED):
        assert resolve_event_switch(run_state=st).action == EventSwitchAction.ALLOW
    for st in (LiveRunState.STARTING, LiveRunState.RECORDING, LiveRunState.PAUSED,
               LiveRunState.DISCONNECTED, LiveRunState.COMPLETING):
        assert resolve_event_switch(run_state=st).action == EventSwitchAction.BLOCK
