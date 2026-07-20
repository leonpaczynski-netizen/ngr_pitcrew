"""Phase 54-56 — safety invariants + config/DB immutability (task items 33-34, 39-42, section 16)."""
from __future__ import annotations

import hashlib
import pathlib

from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION

_ROOT = pathlib.Path(__file__).resolve().parents[1]

_NEW_MODULES = [
    "strategy/canonical_activity_state.py", "strategy/setup_strategy_readiness.py",
    "strategy/live_activity_bridge.py", "strategy/live_bridge_views.py",
    "strategy/live_session_detection.py", "strategy/event_programme_certification.py",
    "ui/certification_vm.py",
]

_FORBIDDEN = ["import openai", "anthropic", "requests.get", "urllib.request", "http://", "https://",
              "socket.", "api_key", "API_KEY", "pyttsx", "cloud", "os.system", "eval(", "exec(", "pickle"]


def test_new_modules_no_ai_network_tts_or_keys():
    for rel in _NEW_MODULES:
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        for bad in _FORBIDDEN:
            assert bad.lower() not in src, f"{rel} contains forbidden token {bad!r}"


def test_new_domain_modules_qt_free():
    for rel in _NEW_MODULES:
        if rel.startswith("ui/"):
            continue
        assert "PyQt6" not in (_ROOT / rel).read_text(encoding="utf-8"), f"{rel} imports Qt"


def test_versions_pinned_and_no_new_migration():
    assert DB_VERSION == 28 and RULE_ENGINE_VERSION == "46.0"
    src = (_ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
    assert f"_migrate_v{DB_VERSION + 1}" not in src  # this slice added no migration


def test_apply_gate_and_voice_gate_untouched():
    from data.setup_state_authority import ActiveSetupAuthority
    from strategy.shadow_advisory import voice_gate_allows, LiveValidationReadiness
    assert hasattr(ActiveSetupAuthority, "mark_applied")
    assert voice_gate_allows(LiveValidationReadiness.VOICE_ELIGIBLE.value) is True
    assert voice_gate_allows(LiveValidationReadiness.NOT_READY.value) is False


def test_truth_and_command_centre_views_write_nothing(tmp_path):
    from data.session_db import SessionDB
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    db.upsert_preparation_cycle({"cycle_id": "c1", "event_name": "Cup", "track": "Fuji", "car": "P",
                                 "official_race_date": "2026-06-21", "format_profile_id": "multiweek",
                                 "explicit_state": "active"})
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "setup_experiment", "order_index": 0,
                                    "state": "in_progress"})
    db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db2 = SessionDB(p)
    for _ in range(3):
        db2.build_command_centre_truth("c1")
        db2.build_event_command_centre_view(selected_cycle_id="c1", now_date="2026-06-11")
    db2.close()
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0


def test_config_path_change_cannot_change_engineering_fingerprint():
    # engineering fingerprints derive from evidence, not config; the active_cycle_id selection is
    # operational and excluded from the candidate-membership fingerprint.
    from strategy.active_cycle_resolution import CycleCandidate, resolve_active_cycle
    cands = [CycleCandidate("a", explicit_state="active", official_race_date="2026-06-21")]
    f1 = resolve_active_cycle(cands, selected_cycle_id="a").fingerprint
    f2 = resolve_active_cycle(cands, selected_cycle_id="").fingerprint
    assert f1 == f2  # selection state does not enter the semantic fingerprint


def test_session_end_never_auto_completes():
    from strategy.live_session_detection import detect_session_end
    d = detect_session_end(was_running=True, telemetry_fresh=False, session_state="ended",
                           valid_laps=8, evidence_permitted=True)
    assert d.activity_completed is False


def test_bridge_never_issues_commands():
    from strategy.live_activity_bridge import LiveActivityRuntimeSnapshot, classify_live_activity_match
    from strategy.live_bridge_views import build_race_bridge
    snap = LiveActivityRuntimeSnapshot(activity_selected=True, activity_id="r", telemetry_fresh=True,
                                       car_expected="P", car_live="P", track_expected="F", track_live="F",
                                       layout_expected="x", layout_live="x", discipline_expected="race",
                                       discipline_live="race", expected_setup_fingerprint="fp",
                                       live_setup_fingerprint="fp", event_context_digest="c",
                                       live_context_digest="c", tyre_compound="MR", run_plan_fingerprint="rp")
    b = build_race_bridge(snap, classify_live_activity_match(snap))
    assert b.view.issues_commands is False
