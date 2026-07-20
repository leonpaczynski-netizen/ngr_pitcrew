"""Phase 60 — DB-free pit-wall build + off-thread worker + stale/event-switch guard (task items 6-9, 34-35)."""
from __future__ import annotations

import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests._qt_worker_wait import drive_worker
from strategy.gt7_live_adapter import TrackerRuntimeSnapshot, SelectedActivityContext
from strategy.live_pit_wall_controller import LivePitWallNavigationContext as NAV
from strategy.live_pit_wall_build import build_live_pit_wall_view


def _tracker(**kw):
    base = dict(car="Porsche", track="Fuji", layout="Full", applied_setup_fingerprint="fp",
                valid_laps=5, last_packet_monotonic=100.0, session_state="running",
                live_context_digest="ctx", tyre_compound="MR")
    base.update(kw)
    return TrackerRuntimeSnapshot(**base)


def _ctx():
    return SelectedActivityContext(cycle_id="c1", activity_id="exp", activity_type="setup_experiment",
                                   discipline="race", car="Porsche", track="Fuji", layout="Full",
                                   expected_setup_fingerprint="fp", event_context_digest="ctx",
                                   run_plan_fingerprint="rp", target_laps=8, objective="rotation")


# --- DB-free build ---------------------------------------------------------

def test_build_view_is_deterministic_and_db_free():
    nav = NAV(active_event_id="c1", selected_activity_id="exp", started=True)
    a = build_live_pit_wall_view(_tracker(), _ctx(), nav, was_running=True, now_monotonic=100.5)
    b = build_live_pit_wall_view(_tracker(), _ctx(), nav, was_running=True, now_monotonic=100.5)
    assert a["state_fingerprint"] == b["state_fingerprint"]
    assert a["production_state"] == "exact_match" and a["activity_completed"] is False


def test_build_view_opening_live_not_started():
    nav = NAV(active_event_id="c1", selected_activity_id="exp", entered_live=True, started=False)
    v = build_live_pit_wall_view(_tracker(), _ctx(), nav, was_running=False, now_monotonic=100.5)
    assert v["production_state"] in ("awaiting_start", "starting")  # opening Live never starts


def test_build_view_module_has_no_db_import():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "strategy" / "live_pit_wall_build.py").read_text(encoding="utf-8")
    assert "session_db" not in src and "sqlite" not in src


# --- off-thread + stale guard (dashboard) ----------------------------------

@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    a = QApplication.instance() or QApplication([])
    yield a


def test_pit_wall_build_runs_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}
    nav = NAV(active_event_id="c1", selected_activity_id="exp", started=True)

    def build():
        seen["worker"] = threading.get_ident()
        return build_live_pit_wall_view(_tracker(), _ctx(), nav, was_running=True, now_monotonic=100.5)

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r)))
    w.failed.connect(lambda m: seen.__setitem__("err", m))
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen["result"]["production_state"]


def test_stale_worker_result_ignored(app):
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Panel:
        def update_result(self, r):
            rendered["r"] = r

    stub._live_pit_wall_panel = _Panel()
    stub._config = {"active_cycle_id": "c1"}
    stub._live_selected_activity_id = "exp"
    newest = object()
    stub._live_pit_wall_worker = newest
    # a different (stale) worker's result is dropped
    dash.MainWindow._on_live_pit_wall_ready(stub, {"ok": True}, object(), ("c1", "exp"))
    assert "r" not in rendered
    # the current worker with the current nav key renders
    dash.MainWindow._on_live_pit_wall_ready(stub, {"ok": True}, newest, ("c1", "exp"))
    assert rendered.get("r", {}).get("ok")


def test_event_switch_rejects_result_for_previous_event(app):
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Panel:
        def update_result(self, r):
            rendered["r"] = r

    stub._live_pit_wall_panel = _Panel()
    # selection has since switched to event c2
    stub._config = {"active_cycle_id": "c2"}
    stub._live_selected_activity_id = "other"
    worker = object()
    stub._live_pit_wall_worker = worker
    # a result computed for event c1 (previous) is dropped
    dash.MainWindow._on_live_pit_wall_ready(stub, {"ok": True}, worker, ("c1", "exp"))
    assert "r" not in rendered
