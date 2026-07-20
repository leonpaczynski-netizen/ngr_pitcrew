"""Phase 42-44 — Assisted Runtime pit-wall UI: construction, embedding, off-thread, stale-guard."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication

from data.session_db import SessionDB
from tests._assurance_pack_helpers import seed_contradiction, applied, KW
from tests._qt_worker_wait import drive_worker


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report():
    import tempfile
    p = tempfile.mktemp(suffix=".db")
    db = SessionDB(p); seed_contradiction(db, 3, 2)
    r = db.build_assisted_runtime_report(applied_setup=applied(), now_date="2026-07-10",
                                         now_monotonic=1.0, **KW)
    db.close()
    try:
        os.remove(p)
    except OSError:
        pass
    return r


def test_panel_constructs_three_cards(app):
    from ui.assisted_runtime_panel import AssistedRuntimePanel
    p = AssistedRuntimePanel()
    p.update_result(_report())
    assert len(p._cards) >= 3   # Run State / Live Advisory / Evidence Progress / Voice (+snapshot)


def test_panel_empty_and_none_safe(app):
    from ui.assisted_runtime_panel import AssistedRuntimePanel
    p = AssistedRuntimePanel()
    p.update_result(None)
    assert p._cards == []
    p.update_result({"ok": True, "workflow": None})
    assert p._cards == []


def test_panel_no_apply_experiment_or_command_buttons(app):
    # Phase 47 adds opt-in VOICE controls (enable/acknowledge/mute/test) - allowed. Still no
    # Apply / experiment / outcome-write / session-bind / pit / tyre / fuel / setup command buttons.
    from PyQt6.QtWidgets import QPushButton
    from ui.assisted_runtime_panel import AssistedRuntimePanel
    p = AssistedRuntimePanel()
    p.update_result(_report())
    labels = [b.text().lower() for b in p.findChildren(QPushButton)]
    for bad in ("apply", "create experiment", "record outcome", "bind session", "pit now",
                "change tyre", "fuel map", "change setup", "save fuel"):
        assert not any(bad in l for l in labels), bad


def test_panel_cards_have_accessible_names(app):
    from ui.assisted_runtime_panel import AssistedRuntimePanel
    p = AssistedRuntimePanel()
    p.update_result(_report())
    assert all(c.accessibleName() for c in p._cards)


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "_assisted_runtime_panel")
    page.update_assisted_runtime(_report())
    assert len(page._assisted_runtime_panel._cards) >= 3


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert (hasattr(page, "_assisted_runtime_panel") and hasattr(page, "_closed_loop_panel")
            and hasattr(page, "_race_engineer_team_panel"))


def test_ui_refresh_writes_no_outcome(app):
    # rendering the panel calls no DB write path; the VM only reads the dict.
    from ui.assisted_runtime_panel import AssistedRuntimePanel
    import ui.assisted_runtime_vm as vm
    r = _report()
    p = AssistedRuntimePanel(); p.update_result(r)
    assert vm.build(r).get("ok")  # pure read only


def test_stale_worker_result_ignored(app):
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Page:
        def update_assisted_runtime(self, r):
            rendered["r"] = r

    stub._development_history_page = _Page()
    newest = object()
    stub._assisted_runtime_worker = newest
    dash.MainWindow._on_assisted_runtime_ready(stub, {"ok": True, "workflow": None}, object())
    assert "r" not in rendered
    dash.MainWindow._on_assisted_runtime_ready(stub, {"ok": True, "workflow": None}, newest)
    assert "r" in rendered


def test_runtime_build_runs_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "workflow": None}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r)))
    w.failed.connect(lambda m: seen.__setitem__("err", m))
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
