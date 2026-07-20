"""Phase 29 — UI construction, no mutation controls, off-thread + stale-worker protection."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.programme_contradiction_report import build_programme_contradiction_report


def _rec(track="Fuji", session="s1", outcome="confirmed_improvement", date="2026-07-01"):
    return {"context": {"track": track, "car": "GT-R", "driver": "L", "compound": "RH",
                        "gt7_version": "1", "discipline": "race", "layout_id": "fc"},
            "changes": [{"field": "arb_front"}], "residual_states": [{"family": "rotation"}],
            "outcome_status": outcome, "confidence_level": "high", "test_session_id": session,
            "session_date": date}


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(empty=False):
    if empty:
        return {"ok": True, "contradiction": None, "contradiction_count": 0}
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"}, "content_fingerprint": "p25"}
    # one genuine open (same context) + one context-resolved (different track)
    recs = [_rec(session="c1"), _rec(session="c2"),
            _rec(session="r1", outcome="regression"), _rec(session="r2", outcome="regression")]
    rep = build_programme_contradiction_report(tl, {"content_fingerprint": "p22"}, recs).to_dict()
    return {"ok": True, "contradiction": rep, "contradiction_count": len(rep["contradictions"]),
            "open_count": len(rep["open_contradictions"])}


def test_panel_constructs_and_renders(app):
    from ui.engineering_contradiction_panel import EngineeringContradictionPanel
    p = EngineeringContradictionPanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.engineering_contradiction_panel import EngineeringContradictionPanel
    p = EngineeringContradictionPanel()
    p.update_result(_report(empty=True))
    assert p._cards == []


def test_panel_none_and_error_safe(app):
    from ui.engineering_contradiction_panel import EngineeringContradictionPanel
    p = EngineeringContradictionPanel()
    p.update_result(None)
    assert p._cards == []
    p.update_result({"ok": False, "error": "boom"})
    assert p._cards == []


def test_panel_no_mutation_controls(app):
    from ui.engineering_contradiction_panel import EngineeringContradictionPanel
    p = EngineeringContradictionPanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []


def test_states_distinguishable_without_colour(app):
    from strategy.programme_contradiction_report_render import render_contradiction_sections
    titles = [t for t, _ in render_contradiction_sections(_report()["contradiction"])]
    for expected in ("Open contradictions (evidence does not tell us which is right)",
                     "Resolved / explained contradictions"):
        assert expected in titles


def test_no_setup_values_rendered(app):
    from strategy.programme_contradiction_report_render import render_contradiction_text
    import re
    txt = render_contradiction_text(_report()["contradiction"])
    assert not re.search(r"(arb_front|lsd_accel|springs_front)\s*[=:]\s*-?\d", txt)


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_programme_contradiction_report")
    assert hasattr(page, "_contradiction_panel")
    page.update_programme_contradiction_report(_report())
    assert len(page._contradiction_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    for attr in ("_knowledge_panel", "_transfer_panel", "_playbook_panel", "_timeline_panel",
                 "_revalidation_panel", "_coverage_panel", "_readiness_panel",
                 "_contradiction_panel"):
        assert hasattr(page, attr), attr


def test_stale_worker_result_ignored(app):
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Page:
        def update_programme_contradiction_report(self, r):
            rendered["r"] = r

    stub._development_history_page = _Page()
    newest = object()
    stub._contradiction_worker = newest
    dash.MainWindow._on_programme_contradiction_report_ready(
        stub, {"ok": True, "contradiction": None, "contradiction_count": 0}, object())
    assert "r" not in rendered
    dash.MainWindow._on_programme_contradiction_report_ready(
        stub, {"ok": True, "contradiction": None, "contradiction_count": 0}, newest)
    assert "r" in rendered


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "contradiction": None, "contradiction_count": 0}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r), app.quit()))
    w.failed.connect(lambda m: (seen.__setitem__("err", m), app.quit()))
    from tests._qt_worker_wait import drive_worker
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
