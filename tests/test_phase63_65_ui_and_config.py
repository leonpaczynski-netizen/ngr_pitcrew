"""Phase 63-65 — offscreen UI construction, panel rendering, PTT config safety, dashboard wiring."""
from __future__ import annotations

import os

import pytest

from strategy.push_to_talk import (
    PushToTalkBinding, PttInputKind, read_ptt_binding, write_ptt_binding,
)


# --- PTT config safety (no Qt) --- #
def test_ptt_binding_read_default_is_unbound():
    assert read_ptt_binding({}).is_bound is False
    assert read_ptt_binding(None).is_bound is False


def test_ptt_binding_write_is_explicit_and_isolated():
    cfg = {}
    b = PushToTalkBinding(kind=PttInputKind.KEYBOARD, input_code="F13", label="PTT")
    write_ptt_binding(cfg, b)
    assert cfg["ptt_binding"]["input_code"] == "F13"
    # round-trips through config
    assert read_ptt_binding(cfg) == b
    # writing never touches any other key
    assert set(cfg.keys()) == {"ptt_binding"}


# --- offscreen Qt construction --- #
@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 not available")
    app = QApplication.instance() or QApplication([])
    yield app


def test_audio_panel_constructs_and_renders(qapp):
    from ui.vr_audio_engineer_panel import VrAudioEngineerPanel
    from strategy.live_audio_strategy_build import build_live_audio_strategy_view
    from strategy.adaptive_live_strategy import LiveStrategyState, StrategyObjective
    from strategy.audio_first_engineer import VrRuntimeMode
    panel = VrAudioEngineerPanel()
    # empty state is safe
    panel.update_result(None)
    # a real view renders a strategy card
    state = LiveStrategyState(objective=StrategyObjective.LAP_COUNT, laps_remaining=20,
                              lap_time_actual_s=90.0, lap_time_plan_s=90.0, pit_loss_s=25.0,
                              tyre_age_laps=10, fuel_per_lap_plan=3.0, fuel_per_lap_actual=3.6,
                              telemetry_fresh=True)
    v = build_live_audio_strategy_view(state, vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                       gate_allows=True, tts_available=True, recognition_available=True,
                                       workload_context={"segment": "straight"})
    panel.update_result(v)
    assert panel._cards  # at least the strategy card rendered


def test_live_tab_hosts_audio_panel(qapp):
    # the Live tab builder attaches the audio-first panel attribute
    import ui.live_ui as live_ui
    src = open(live_ui.__file__, encoding="utf-8").read()
    assert "_vr_audio_engineer_panel" in src and "VrAudioEngineerPanel" in src


def test_dashboard_wiring_present():
    import ui.dashboard as dash
    src = open(dash.__file__, encoding="utf-8").read()
    assert "_refresh_audio_engineer" in src and "_on_audio_engineer_ready" in src
    # dispatched from TAB_LIVE alongside the pit wall
    assert "self._refresh_audio_engineer()" in src


# --- stale-worker rejection logic (no Qt worker needed) --- #
def test_stale_audio_worker_result_is_dropped():
    import ui.dashboard as dash

    class _Stub:
        pass
    stub = _Stub.__new__(_Stub)
    stub._config = {"active_cycle_id": "cyc-A"}
    stub._live_selected_activity_id = "act-1"
    stub._audio_engineer_worker = "current"
    stub._vr_audio_engineer_panel = _Panel()
    # a result from a DIFFERENT worker is ignored
    dash.MainWindow._on_audio_engineer_ready(stub, {"ok": True}, worker="other",
                                             nav_key=("cyc-A", "act-1"))
    assert stub._vr_audio_engineer_panel.updates == 0
    # a result for a PREVIOUS event/activity is ignored
    dash.MainWindow._on_audio_engineer_ready(stub, {"ok": True}, worker="current",
                                             nav_key=("cyc-OLD", "act-1"))
    assert stub._vr_audio_engineer_panel.updates == 0
    # the current worker + current key updates the panel
    dash.MainWindow._on_audio_engineer_ready(stub, {"ok": True}, worker="current",
                                             nav_key=("cyc-A", "act-1"))
    assert stub._vr_audio_engineer_panel.updates == 1


class _Panel:
    def __init__(self):
        self.updates = 0

    def update_result(self, result):
        self.updates += 1
