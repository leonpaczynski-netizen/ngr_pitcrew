"""Phase 60-62 — safety invariants: no new listener, DB-free, gates + logo preserved (section 17, item 37)."""
from __future__ import annotations

import pathlib

from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION

_ROOT = pathlib.Path(__file__).resolve().parents[1]

_NEW_STRATEGY = [
    "strategy/runtime_context_resolution.py", "strategy/live_pit_wall_controller.py",
    "strategy/live_pit_wall_build.py", "strategy/driver_event_loop.py", "strategy/discipline_workflow.py",
    "strategy/binding_debrief_workflow.py", "strategy/live_restart_recovery.py",
]

_FORBIDDEN = ["import openai", "anthropic", "requests.get", "urllib.request", "http://", "https://",
              "api_key", "API_KEY", "pyttsx", "cloud", "os.system", "eval(", "exec(", "pickle"]
_FORBIDDEN_LISTENER = ["recvfrom", "socket.socket", "0xdeadbeef", "sock.recv", "import socket"]
# no new UI module may draw / recolour / generate the official NGR logo
_FORBIDDEN_LOGO = ["logo_pixmap(", "drawlogo", "generate_logo", "recolor", "recolour"]


def test_new_strategy_no_ai_network_tts_or_keys():
    for rel in _NEW_STRATEGY:
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        for bad in _FORBIDDEN:
            assert bad.lower() not in src, f"{rel} contains forbidden token {bad!r}"


def test_new_strategy_creates_no_telemetry_listener():
    for rel in _NEW_STRATEGY:
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        for bad in _FORBIDDEN_LISTENER:
            assert bad not in src, f"{rel} appears to create a telemetry listener ({bad!r})"


def test_new_strategy_is_db_free_and_qt_free():
    for rel in _NEW_STRATEGY:
        src = (_ROOT / rel).read_text(encoding="utf-8")
        assert "session_db" not in src and "sqlite" not in src, f"{rel} touches the DB"
        assert "PyQt6" not in src and "PyQt5" not in src, f"{rel} imports Qt"


def test_new_ui_modules_do_not_generate_or_alter_the_logo():
    for rel in ("ui/ngr_live_pit_wall_vm.py",):
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        for bad in _FORBIDDEN_LOGO:
            assert bad not in src, f"{rel} appears to render/alter the logo ({bad!r})"


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


def test_production_build_touches_no_db():
    from strategy.gt7_live_adapter import TrackerRuntimeSnapshot, SelectedActivityContext
    from strategy.live_pit_wall_controller import LivePitWallNavigationContext
    from strategy.live_pit_wall_build import build_live_pit_wall_view
    v = build_live_pit_wall_view(
        TrackerRuntimeSnapshot(car="P", track="F", last_packet_monotonic=100.0),
        SelectedActivityContext(activity_id="a", car="P", track="F"),
        LivePitWallNavigationContext(active_event_id="c1", selected_activity_id="a", started=True),
        was_running=True, now_monotonic=100.2)
    assert v["ok"] is True and v["activity_completed"] is False


def test_opening_and_refreshing_live_never_completes():
    from strategy.gt7_live_adapter import TrackerRuntimeSnapshot, SelectedActivityContext
    from strategy.live_pit_wall_controller import LivePitWallNavigationContext
    from strategy.live_pit_wall_build import build_live_pit_wall_view
    nav = LivePitWallNavigationContext(active_event_id="c1", selected_activity_id="a", entered_live=True,
                                       started=False)
    v = build_live_pit_wall_view(TrackerRuntimeSnapshot(car="P", track="F", session_state="ended",
                                                        valid_laps=9, last_packet_monotonic=100.0),
                                 SelectedActivityContext(activity_id="a", car="P", track="F"), nav,
                                 was_running=False, now_monotonic=100.2)
    assert v["activity_completed"] is False and v["production_state"] in ("awaiting_start", "starting")


def test_config_selection_is_explicit_only_and_isolated(tmp_path):
    # the dashboard writes active_cycle_id only on explicit selection; a stub proves no engineering write
    import ui.dashboard as dash

    class _Stub:
        pass
    stub = _Stub.__new__(_Stub)
    stub._config = {}
    stub._db = None
    stub._event_command_centre_panel = None
    dash.MainWindow._cc_select_active_cycle(stub, "cyc-x")
    assert stub._config["active_cycle_id"] == "cyc-x"  # operational nav state, no DB write
