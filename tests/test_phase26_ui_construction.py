"""Phase 26 — UI construction, no mutation controls, off-thread + stale-worker protection."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.programme_revalidation_report import build_revalidation_report


def _conv(domain, **kw):
    base = {"domain": domain, "convergence_status": "strongly_converged",
            "independent_support_count": 3, "dependent_support_count": 0, "regression_count": 0,
            "conflict_count": 0, "transfer_limitations": [], "retired_directions": [],
            "confirmed_good": True, "current_maturity": "complete",
            "current_confidence": "very_high", "compatible_contexts": 2}
    base.update(kw)
    return base


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(empty=False):
    if empty:
        return {"ok": True, "revalidation": None, "domain_count": 0}
    timeline = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1.0",
                                     "driver": "L"},
                "convergence_summaries": [
                    _conv("differential"),
                    _conv("weight_transfer", convergence_status="conflicting", conflict_count=1,
                          confirmed_good=False),
                    _conv("aero_balance", convergence_status="superseded", confirmed_good=False)],
                "timeline_points": [{"knowledge_domain": "differential",
                                     "evidence_date": "2026-01-01"}],
                "content_fingerprint": "p25:x"}
    prog = {"compatibility": {}, "content_fingerprint": "p22:y"}
    rep = build_revalidation_report(timeline, prog).to_dict()
    return {"ok": True, "revalidation": rep, "domain_count": len(rep["items"])}


def test_panel_constructs_and_renders(app):
    from ui.engineering_revalidation_panel import EngineeringRevalidationPanel
    p = EngineeringRevalidationPanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.engineering_revalidation_panel import EngineeringRevalidationPanel
    p = EngineeringRevalidationPanel()
    p.update_result(_report(empty=True))
    assert p._cards == []


def test_panel_none_and_error_safe(app):
    from ui.engineering_revalidation_panel import EngineeringRevalidationPanel
    p = EngineeringRevalidationPanel()
    p.update_result(None)
    assert p._cards == []
    p.update_result({"ok": False, "error": "boom"})
    assert p._cards == []


def test_panel_no_mutation_controls(app):
    from ui.engineering_revalidation_panel import EngineeringRevalidationPanel
    p = EngineeringRevalidationPanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []


def test_states_distinguishable_without_colour(app):
    """Protected / conflict / regression / superseded sections carry text tags (not colour alone)."""
    from strategy.programme_revalidation_report_render import render_revalidation_sections
    titles = [t for t, _ in render_revalidation_sections(_report()["revalidation"])]
    for expected in ("Current / protected knowledge", "Weakened by conflict",
                     "Superseded / retired (inactive)"):
        assert expected in titles


def test_no_setup_values_rendered(app):
    from strategy.programme_revalidation_report_render import render_revalidation_text
    import re
    txt = render_revalidation_text(_report()["revalidation"])
    assert not re.search(r"(arb_front|lsd_accel|springs_front)\s*[=:]\s*-?\d", txt)


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_programme_revalidation_report")
    assert hasattr(page, "_revalidation_panel")
    page.update_programme_revalidation_report(_report())
    assert len(page._revalidation_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    for attr in ("_knowledge_panel", "_efficiency_panel", "_confidence_panel", "_season_panel",
                 "_knowledge_graph_panel", "_transfer_panel", "_playbook_panel",
                 "_timeline_panel", "_revalidation_panel"):
        assert hasattr(page, attr), attr


def test_stale_worker_result_ignored(app):
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Page:
        def update_programme_revalidation_report(self, r):
            rendered["r"] = r

    stub._development_history_page = _Page()
    newest = object()
    stub._revalidation_worker = newest
    dash.MainWindow._on_programme_revalidation_report_ready(
        stub, {"ok": True, "revalidation": None, "domain_count": 0}, object())
    assert "r" not in rendered
    dash.MainWindow._on_programme_revalidation_report_ready(
        stub, {"ok": True, "revalidation": None, "domain_count": 0}, newest)
    assert "r" in rendered


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "revalidation": None, "domain_count": 0}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r), app.quit()))
    w.failed.connect(lambda m: (seen.__setitem__("err", m), app.quit()))
    from tests._qt_worker_wait import drive_worker
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
