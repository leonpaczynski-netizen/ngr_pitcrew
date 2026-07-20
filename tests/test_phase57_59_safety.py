"""Phase 57-59 — safety invariants: no new listener, DB-free domain, gates preserved (section 17)."""
from __future__ import annotations

import pathlib

from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION

_ROOT = pathlib.Path(__file__).resolve().parents[1]

_NEW_STRATEGY = [
    "strategy/gt7_live_adapter.py", "strategy/live_runtime_cache.py", "strategy/live_runtime_authority.py",
    "strategy/ngr_live_pit_wall.py", "strategy/live_pit_wall_integration.py",
]
_NEW_UI_VM = ["ui/ngr_live_pit_wall_vm.py"]

_FORBIDDEN = ["import openai", "anthropic", "requests.get", "urllib.request", "http://", "https://",
              "api_key", "API_KEY", "pyttsx", "cloud", "os.system", "eval(", "exec(", "pickle"]
# no NEW telemetry listener / UDP socket OPERATIONS in the new modules (a prose reference to the existing
# UDPListener the adapter reuses is fine; actual socket ops are not)
_FORBIDDEN_LISTENER = ["recvfrom", "socket.socket", "0xdeadbeef", "sock.recv", "import socket"]


def test_new_modules_no_ai_network_tts_or_keys():
    for rel in _NEW_STRATEGY + _NEW_UI_VM:
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        for bad in _FORBIDDEN:
            assert bad.lower() not in src, f"{rel} contains forbidden token {bad!r}"


def test_new_modules_create_no_telemetry_listener():
    for rel in _NEW_STRATEGY + _NEW_UI_VM:
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        for bad in _FORBIDDEN_LISTENER:
            assert bad not in src, f"{rel} appears to create a telemetry listener ({bad!r})"


def test_new_domain_modules_are_db_free_and_qt_free():
    for rel in _NEW_STRATEGY:
        src = (_ROOT / rel).read_text(encoding="utf-8")
        assert "session_db" not in src and "sqlite" not in src, f"{rel} touches the DB"
        assert "PyQt6" not in src and "PyQt5" not in src, f"{rel} imports Qt"


def test_versions_pinned_and_no_new_migration():
    assert DB_VERSION == 28 and RULE_ENGINE_VERSION == "46.0"
    src = (_ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
    assert f"_migrate_v{DB_VERSION + 1}" not in src


def test_apply_gate_and_voice_gate_untouched():
    from data.setup_state_authority import ActiveSetupAuthority
    from strategy.shadow_advisory import voice_gate_allows, LiveValidationReadiness
    assert hasattr(ActiveSetupAuthority, "mark_applied")
    assert voice_gate_allows(LiveValidationReadiness.VOICE_ELIGIBLE.value) is True
    assert voice_gate_allows(LiveValidationReadiness.NOT_READY.value) is False


def test_telemetry_evaluation_touches_no_db():
    # evaluate_live_runtime is a pure function of its inputs; there is no DB handle anywhere in the path
    from strategy.gt7_live_adapter import TrackerRuntimeSnapshot, SelectedActivityContext, evaluate_live_runtime
    e = evaluate_live_runtime(TrackerRuntimeSnapshot(car="P", track="F", last_packet_monotonic=100.0),
                              SelectedActivityContext(activity_id="a", car="P", track="F"),
                              now_monotonic=100.2)
    assert e.fingerprint  # produced without any DB access


def test_runtime_transition_never_completes_activity():
    from strategy.gt7_live_adapter import TrackerRuntimeSnapshot, SelectedActivityContext, evaluate_live_runtime
    from strategy.live_runtime_authority import evaluate_runtime_transition
    e = evaluate_live_runtime(TrackerRuntimeSnapshot(car="P", track="F", session_state="ended", valid_laps=9,
                                                     last_packet_monotonic=100.0),
                              SelectedActivityContext(activity_id="a", car="P", track="F", target_laps=8),
                              now_monotonic=100.2)
    assert evaluate_runtime_transition(e, was_running=True).activity_completed is False


def test_command_centre_view_still_read_only(tmp_path):
    import hashlib
    from data.session_db import SessionDB
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    db.upsert_preparation_cycle({"cycle_id": "c1", "event_name": "Cup", "track": "Fuji", "car": "P",
                                 "official_race_date": "2026-06-21", "format_profile_id": "multiweek",
                                 "explicit_state": "active"})
    db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db2 = SessionDB(p)
    for _ in range(3):
        db2.build_event_command_centre_view(selected_cycle_id="c1", now_date="2026-06-11")
        db2.build_command_centre_truth("c1")
    db2.close()
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0
