"""Phase 69-71 — UI construction (offscreen), read-only rendering, stale-worker protection, and the
dashboard wiring for the runtime diagnostics + bench + manual-evidence surfaces."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 not available")
    app = QApplication.instance() or QApplication([])
    yield app


def test_uat_runtime_panel_constructs(qapp):
    from ui.uat_runtime_panel import UatRuntimePanel
    from strategy.live_uat_runtime_snapshot import build_live_uat_runtime_snapshot
    from strategy.canonical_live_race_state import build_canonical_live_race_state
    from strategy.event_programme_certification import live_vr_certification
    import types
    p = UatRuntimePanel()
    p.update_result(None)          # empty state renders
    t = types.SimpleNamespace(race_type="laps", laps_recorded=5, laps_in_race=20, last_fuel=60.0,
                              avg_fuel_per_lap=3.0, best_lap_ms=88000, tyre_compound="RH",
                              laps_since_pit=5, car_name="GT3")
    canon = build_canonical_live_race_state(t, recent_clean_lap_times_s=[88.1, 88.0, 88.2, 88.1, 88.0])
    snap = build_live_uat_runtime_snapshot(canonical=canon, certification=live_vr_certification(),
                                           tracker_connected=True, telemetry_fresh=True)
    p.update_result(snap.to_dict())
    assert p._cards


def test_bench_uat_panel_constructs_and_renders(qapp):
    from ui.bench_uat_panel import BenchUatPanel
    from strategy.bench_uat_harness import run_bench_uat
    p = BenchUatPanel()
    p.update_result(None)
    p.update_result(run_bench_uat().to_dict())
    assert p._cards


def test_bench_uat_runs_off_thread(qapp):
    from ui.bench_uat_panel import BenchUatPanel
    from tests._qt_worker_wait import drive_worker
    p = BenchUatPanel()
    p._on_run_clicked()
    assert p._worker is not None
    assert drive_worker(p._worker if p._worker is not None else _NoWorker())
    # after the worker delivers, the button is re-enabled and results rendered
    assert p._run_btn.isEnabled()
    assert p._cards


class _NoWorker:  # pragma: no cover - guard for the unlikely already-finished race
    def start(self):
        pass

    def wait(self, *_a):
        return True


def test_manual_uat_panel_constructs_and_records(qapp, tmp_path):
    from ui.manual_uat_panel import ManualUatPanel
    from data.manual_uat_store import ManualUatStore
    from strategy.manual_uat_evidence import ManualUatStatus
    store = ManualUatStore(tmp_path / "manual_uat_evidence.json")
    facts = lambda: {"automated_tests_passed": 10277, "automated_tests_failed": 0, "bench_total": 67,
                     "bench_passed": 67, "bench_ready": True, "db_version": 28,
                     "rule_engine_version": "46.0"}
    p = ManualUatPanel(store=store, facts_provider=facts, candidate_commit="c1")
    assert p._cards
    # simulate selecting an area + PASS and recording
    idx = next(i for i in range(p._area_combo.count()) if p._area_combo.itemData(i) == "physical_tts")
    p._area_combo.setCurrentIndex(idx)
    pidx = next(i for i in range(p._status_combo.count()) if p._status_combo.itemData(i) == "pass")
    p._status_combo.setCurrentIndex(pidx)
    p._on_record_clicked()
    assert store.ledger.status_of("physical_tts") == ManualUatStatus.PASS


def test_manual_panel_read_only_without_store(qapp):
    from ui.manual_uat_panel import ManualUatPanel
    p = ManualUatPanel(store=None)
    assert p._record_btn.isEnabled() is False   # cannot record without a store


def test_development_history_page_hosts_all_uat_surfaces(qapp):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "_uat_runtime_panel")
    assert hasattr(page, "_bench_uat_panel")
    assert hasattr(page, "_manual_uat_panel")
    assert hasattr(page, "update_uat_runtime")
    assert hasattr(page, "set_manual_uat_context")


def test_dashboard_wires_uat_runtime_and_manual_context():
    import ui.dashboard as dash
    src = open(dash.__file__, encoding="utf-8").read()
    assert "_refresh_uat_runtime" in src
    assert "_wire_manual_uat_context" in src
    assert "update_uat_runtime" in src


def test_no_duplicate_listener_in_ui_wiring():
    import ui.dashboard as dash
    src = open(dash.__file__, encoding="utf-8").read()
    # the new UAT wiring must not create a second socket/listener
    assert "socket.socket(" not in src.split("_refresh_uat_runtime", 1)[-1][:4000]
