"""Phase 27 — UI construction, no mutation controls, off-thread + stale-worker protection."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.programme_coverage_report import build_programme_evidence_coverage_report


def _rec(track="Fuji"):
    return {"context": {"track": track, "car": "GT-R", "driver": "L", "compound": "RH",
                        "discipline": "race", "gt7_version": "1", "layout_id": "fc"},
            "residual_states": [{"family": "rotation", "phase": "entry", "segment_id": "T1"}],
            "outcome_status": "confirmed_improvement", "confidence_level": "high"}


def _conv(domain, **kw):
    base = {"domain": domain, "convergence_status": "converging", "independent_support_count": 1,
            "dependent_support_count": 8, "regression_count": 0, "conflict_count": 0,
            "confirmed_good": True, "compatible_contexts": 1, "current_maturity": "mature",
            "current_confidence": "very_high"}
    base.update(kw)
    return base


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(empty=False):
    if empty:
        return {"ok": True, "coverage": None, "domain_count": 0}
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"},
          "convergence_summaries": [_conv("differential"),
                                    _conv("aero_balance", convergence_status="strongly_converged",
                                          independent_support_count=3, dependent_support_count=0,
                                          compatible_contexts=3)],
          "timeline_points": [], "content_fingerprint": "p25"}
    prog = {"compatibility": {}, "content_fingerprint": "p22"}
    reval = {"items": [{"domain": "differential", "freshness_status": "current"}],
             "content_fingerprint": "p26"}
    rep = build_programme_evidence_coverage_report(tl, prog, reval,
                                                   [_rec(t) for t in ("Fuji", "Suzuka", "Spa")]
                                                   ).to_dict()
    return {"ok": True, "coverage": rep, "domain_count": len(rep["domain_coverage"]),
            "blind_spot_count": len(rep["blind_spots"])}


def test_panel_constructs_and_renders(app):
    from ui.engineering_coverage_panel import EngineeringCoveragePanel
    p = EngineeringCoveragePanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.engineering_coverage_panel import EngineeringCoveragePanel
    p = EngineeringCoveragePanel()
    p.update_result(_report(empty=True))
    assert p._cards == []


def test_panel_none_and_error_safe(app):
    from ui.engineering_coverage_panel import EngineeringCoveragePanel
    p = EngineeringCoveragePanel()
    p.update_result(None)
    assert p._cards == []
    p.update_result({"ok": False, "error": "boom"})
    assert p._cards == []


def test_panel_no_mutation_controls(app):
    from ui.engineering_coverage_panel import EngineeringCoveragePanel
    p = EngineeringCoveragePanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []


def test_states_distinguishable_without_colour(app):
    from strategy.programme_coverage_report_render import render_coverage_sections
    titles = [t for t, _ in render_coverage_sections(_report()["coverage"])]
    for expected in ("Blind spots (more evidence would strengthen these)",
                     "Early-stage gaps (expected; not a concern)", "Well-covered domains",
                     "Per-domain coverage"):
        assert expected in titles


def test_no_setup_values_rendered(app):
    from strategy.programme_coverage_report_render import render_coverage_text
    import re
    txt = render_coverage_text(_report()["coverage"])
    assert not re.search(r"(arb_front|lsd_accel|springs_front)\s*[=:]\s*-?\d", txt)


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_programme_evidence_coverage_report")
    assert hasattr(page, "_coverage_panel")
    page.update_programme_evidence_coverage_report(_report())
    assert len(page._coverage_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    for attr in ("_knowledge_panel", "_efficiency_panel", "_knowledge_graph_panel",
                 "_transfer_panel", "_playbook_panel", "_timeline_panel", "_revalidation_panel",
                 "_coverage_panel"):
        assert hasattr(page, attr), attr


def test_stale_worker_result_ignored(app):
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Page:
        def update_programme_evidence_coverage_report(self, r):
            rendered["r"] = r

    stub._development_history_page = _Page()
    newest = object()
    stub._coverage_worker = newest
    dash.MainWindow._on_programme_evidence_coverage_report_ready(
        stub, {"ok": True, "coverage": None, "domain_count": 0}, object())
    assert "r" not in rendered
    dash.MainWindow._on_programme_evidence_coverage_report_ready(
        stub, {"ok": True, "coverage": None, "domain_count": 0}, newest)
    assert "r" in rendered


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "coverage": None, "domain_count": 0}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r), app.quit()))
    w.failed.connect(lambda m: (seen.__setitem__("err", m), app.quit()))
    from tests._qt_worker_wait import drive_worker
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
