"""Phase 51 — dashboard Command Centre integration: off-thread refresh, stale-worker rejection,
navigation + selection handlers, and read-only DB view (task items 29, 31, 32, 35)."""
from __future__ import annotations

import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests._qt_worker_wait import drive_worker


@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    a = QApplication.instance() or QApplication([])
    yield a


# --- read-only DB view -----------------------------------------------------

def test_command_centre_view_no_active_event(tmp_path):
    from data.session_db import SessionDB
    db = SessionDB(str(tmp_path / "cc.db"))
    v = db.build_event_command_centre_view(now_date="2026-06-11")
    assert v["ok"] and v["resolution_state"] == "no_active_event"
    assert v["next_action"]["category"] == "create_event"
    db.close()


def test_command_centre_view_multiple_requires_selection(tmp_path):
    from data.session_db import SessionDB
    db = SessionDB(str(tmp_path / "cc.db"))
    for cid in ("a", "b"):
        db.upsert_preparation_cycle({"cycle_id": cid, "event_name": cid, "explicit_state": "active",
                                     "official_race_date": "2026-06-21"})
    v = db.build_event_command_centre_view(now_date="2026-06-11")
    assert v["resolution_state"] == "event_requires_selection"
    assert len(v["candidates"]) == 2
    # explicit selection resolves to it (operational state)
    v2 = db.build_event_command_centre_view(selected_cycle_id="b", now_date="2026-06-11")
    assert v2["resolution_state"] == "one_active_event"
    db.close()


def test_command_centre_view_is_read_only(tmp_path):
    import hashlib
    from data.session_db import SessionDB
    p = str(tmp_path / "cc.db")
    db = SessionDB(p)
    db.upsert_preparation_cycle({"cycle_id": "c1", "event_name": "Cup", "track": "Fuji", "car": "P",
                                 "official_race_date": "2026-06-21", "explicit_state": "active",
                                 "format_profile_id": "multiweek"})
    db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db2 = SessionDB(p)
    db2.build_event_command_centre_view(selected_cycle_id="c1", now_date="2026-06-11")
    db2.build_event_command_centre_view(selected_cycle_id="c1", now_date="2026-06-12")
    db2.close()
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0  # a Home refresh writes nothing


# --- off-thread build ------------------------------------------------------

def test_command_centre_build_runs_off_ui_thread(app, tmp_path):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    from data.session_db import SessionDB
    db = SessionDB(str(tmp_path / "cc.db"))
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return db.build_event_command_centre_view(now_date="2026-06-11")

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r)))
    w.failed.connect(lambda m: seen.__setitem__("err", m))
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
    db.close()


# --- stale-worker rejection ------------------------------------------------

def test_stale_command_centre_worker_result_ignored(app):
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Panel:
        def update_result(self, r):
            rendered["r"] = r

    stub._event_command_centre_panel = _Panel()
    newest = object()
    stub._event_command_centre_worker = newest
    # a DIFFERENT (stale) worker's result is dropped
    dash.MainWindow._on_event_command_centre_ready(stub, {"ok": True}, object())
    assert "r" not in rendered
    # the current worker's result renders
    dash.MainWindow._on_event_command_centre_ready(stub, {"ok": True}, newest)
    assert rendered.get("r", {}).get("ok")


# --- navigation + selection handlers ---------------------------------------

def test_cc_navigate_maps_surface_to_tab():
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    calls = {}
    stub._CC_SURFACE_TABS = dash.MainWindow._CC_SURFACE_TABS  # class attr, as a real instance has
    stub.has_tab = lambda key: True
    stub.select_tab = lambda key: calls.__setitem__("tab", key)
    dash.MainWindow._cc_navigate(stub, "setup")
    assert calls["tab"] == "setup_builder"
    dash.MainWindow._cc_navigate(stub, "telemetry")
    assert calls["tab"] == "telemetry"


def test_cc_select_persists_operational_state_only():
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    stub._config = {}
    stub._db = None  # no DB -> refresh is a no-op; we only assert config selection
    stub._event_command_centre_panel = None
    dash.MainWindow._cc_select_active_cycle(stub, "cyc-b")
    assert stub._config["active_cycle_id"] == "cyc-b"  # operational nav state, not an engineering write
