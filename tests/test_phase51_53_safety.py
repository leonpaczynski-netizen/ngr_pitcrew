"""Phase 51-53 — safety invariants + query shape (task items 28, 29, 34-37, section 15)."""
from __future__ import annotations

import hashlib
import pathlib

from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION

_ROOT = pathlib.Path(__file__).resolve().parents[1]

_NEW_MODULES = [
    "strategy/active_cycle_resolution.py", "strategy/event_command_centre.py",
    "strategy/live_activity.py", "strategy/live_activity_modes.py", "strategy/activity_binding.py",
    "strategy/programme_resume.py", "strategy/setup_lock_reopen.py", "strategy/event_revision_impact.py",
    "strategy/operational_certification.py", "ui/event_command_centre_vm.py",
]

_FORBIDDEN = ["import openai", "anthropic", "requests.get", "urllib.request", "http://", "https://",
              "socket.", "api_key", "API_KEY", "pyttsx", "cloud", "os.system", "eval(", "exec(", "pickle"]


def test_new_modules_no_ai_network_tts_or_keys():
    for rel in _NEW_MODULES:
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        for bad in _FORBIDDEN:
            assert bad.lower() not in src, f"{rel} contains forbidden token {bad!r}"


def test_new_domain_modules_are_qt_free():
    for rel in _NEW_MODULES:
        if rel.startswith("ui/"):
            continue
        src = (_ROOT / rel).read_text(encoding="utf-8")
        assert "PyQt6" not in src and "PyQt5" not in src, f"{rel} imports Qt"


def test_versions_pinned():
    assert DB_VERSION == 28 and RULE_ENGINE_VERSION == "46.0"  # no new migration, no rule change


def test_no_new_migration_added_by_slice():
    # this slice introduces no schema migration beyond the current declared version
    src = (_ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
    assert f"_migrate_v{DB_VERSION + 1}" not in src


def test_apply_gate_untouched():
    from data.setup_state_authority import ActiveSetupAuthority
    assert hasattr(ActiveSetupAuthority, "mark_applied")


def test_voice_gate_authority_unchanged():
    from strategy.shadow_advisory import voice_gate_allows, LiveValidationReadiness
    assert voice_gate_allows(LiveValidationReadiness.VOICE_ELIGIBLE.value) is True
    assert voice_gate_allows(LiveValidationReadiness.NOT_READY.value) is False


def test_completion_gate_never_auto_completes():
    from strategy.live_activity import assess_completion
    from strategy.event_preparation_cycle import PreparationActivityType as T
    # missing every confirmation -> cannot complete
    assert assess_completion(T.SETUP_EXPERIMENT, session_bound=False, evidence_classified=False,
                             feedback_present=False, debrief_confirmed=False).can_complete is False


def test_command_centre_view_writes_nothing(tmp_path):
    from data.session_db import SessionDB
    p = str(tmp_path / "cc.db")
    db = SessionDB(p)
    db.upsert_preparation_cycle({"cycle_id": "c1", "event_name": "Cup", "explicit_state": "active",
                                 "track": "Fuji", "car": "P", "official_race_date": "2026-06-21",
                                 "format_profile_id": "multiweek"})
    db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db2 = SessionDB(p)
    for _ in range(3):
        db2.build_event_command_centre_view(selected_cycle_id="c1", now_date="2026-06-11")
    db2.close()
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0


def test_command_centre_query_shape_constant(tmp_path):
    """Home refresh query count is constant regardless of the bound-session count (no N+1)."""
    from data.session_db import SessionDB
    db = SessionDB(str(tmp_path / "q.db"))
    db.upsert_preparation_cycle({"cycle_id": "c1", "event_name": "Cup", "explicit_state": "active",
                                 "track": "Fuji", "car": "P", "official_race_date": "2026-06-21",
                                 "format_profile_id": "multiweek"})
    db.upsert_preparation_activity({"activity_id": "a1", "cycle_id": "c1",
                                    "activity_type": "long_race_run", "order_index": 0})

    def _count(n):
        for _ in range(n):
            sid = db.open_session(car_id=1, track="Fuji", session_type="Practice", car_name="P")
            db._conn.execute("UPDATE sessions SET total_laps=8 WHERE CAST(id AS TEXT)=?", (str(sid),))
            db._conn.commit()
            db.bind_session_to_activity("a1", sid, "c1")
        calls = {"n": 0}
        db._conn.set_trace_callback(lambda s: calls.__setitem__("n", calls["n"] + 1)
                                    if s.strip().upper().startswith("SELECT") else None)
        try:
            db.build_event_command_centre_view(selected_cycle_id="c1", now_date="2026-06-11")
        finally:
            db._conn.set_trace_callback(None)
        return calls["n"]

    q1 = _count(1)
    q20 = _count(19)
    assert q1 == q20, f"query count grew with sessions: {q1} vs {q20}"
    db.close()
