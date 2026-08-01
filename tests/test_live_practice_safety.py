"""Live Activation 1 — safety invariants (§11).

The new authoritative-recording code must never author a setup value, create a strategy
revision, issue a pit instruction, or persist a raw PTT transcript; and the decision core must
stay deterministic + offline (Qt-free, DB-free, no network/AI/wall-clock).
"""
from __future__ import annotations

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]

_NEW = [
    "strategy/live_practice_activation.py",
    "strategy/live_practice_runtime.py",
    "ui/live_practice_db_port.py",
]

# Never-author + no cloud/AI/network tokens.
_FORBIDDEN = [
    "import openai", "anthropic", "requests.get", "urllib.request", "http://", "https://",
    "socket.", "api_key", "pyttsx", "os.system", "eval(", "exec(", "pickle",
    "append_strategy_revision", "set_plan", "mark_applied", "apply_setup",
    "pit_command", "transcript", "record_ptt_interaction",
]


def test_new_modules_author_nothing_forbidden():
    for rel in _NEW:
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        for bad in _FORBIDDEN:
            assert bad.lower() not in src, f"{rel} contains forbidden token {bad!r}"


def test_decision_core_is_qt_and_db_free():
    for rel in ("strategy/live_practice_activation.py", "strategy/live_practice_runtime.py"):
        src = (_ROOT / rel).read_text(encoding="utf-8")
        assert "PyQt6" not in src, f"{rel} must be Qt-free"
        assert "sqlite3" not in src and "session_db" not in src, f"{rel} must be DB-free"


def test_decision_core_uses_no_wall_clock():
    # Timestamps are injected via the port/DB, never read from the clock in the pure core.
    for rel in ("strategy/live_practice_activation.py", "strategy/live_practice_runtime.py"):
        src = (_ROOT / rel).read_text(encoding="utf-8")
        assert "datetime.now" not in src and "time.time" not in src, f"{rel} reads the wall clock"


def test_activation_and_lap_never_raise_on_garbage():
    from strategy.live_practice_activation import (
        evaluate_live_lap, resolve_event_switch, resolve_live_practice_activation)
    assert not resolve_live_practice_activation(None, planned_session_type=None).ok
    assert not evaluate_live_lap(
        run_state="junk", lap_session_run_id=None, active_session_run_id=None,
        lap_event_id=None, active_event_id=None, lap_number="x", last_finalised_lap=None,
        lap_time_ms="y").record
    assert resolve_event_switch(run_state="junk").action.value == "block"


def test_coordinator_records_no_lap_when_blocked():
    from strategy.live_practice_runtime import LivePracticeCoordinator

    class _Port:
        def __init__(self):
            self.laps = []
        def resolve_activation_context(self):
            return {"planned_session_type": "Race"}      # not Practice → blocked
        def create_run(self, identity):
            raise AssertionError("must not create a run for a blocked activation")
        def persist_lap(self, **kw):
            self.laps.append(kw)
        def set_run_status(self, *a):
            pass

    port = _Port()
    co = LivePracticeCoordinator(port)
    assert not co.activate().ok
    # a lap arriving before any authorised run records nothing
    assert not co.on_lap(session_run_id="x", event_id="1", lap_number=1, lap_time_ms=90000).recorded
    assert port.laps == []
