"""Phase 30 — UI construction, no mutation controls, off-thread + stale-worker protection."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.programme_assumption_register import build_programme_assumption_register


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(empty=False):
    if empty:
        return {"ok": True, "assumptions": None, "assumption_count": 0}
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"},
          "convergence_summaries": [{"domain": "differential",
                                     "convergence_status": "stable_but_context_bound",
                                     "confirmed_good": True,
                                     "transfer_limitations": ["gt7_version specific"]}],
          "content_fingerprint": "p25"}
    reval = {"items": [{"domain": "differential", "freshness_status": "revalidation_required"}]}
    cov = {"domain_coverage": [{"domain": "differential", "gap_count": 3,
                                "dimensions": [{"dimension": "track_variety",
                                                "status": "single_context_only"},
                                               {"dimension": "independent_replication",
                                                "status": "dependent_evidence_only"}]}]}
    pb = {"knowledge_boundaries": [{"boundary_type": "unverified_transfer_proxy",
                                    "domain": "differential", "target_car": "", "reason": "proxy"}]}
    rep = build_programme_assumption_register(tl, reval, cov, {"contradictions": []}, pb).to_dict()
    return {"ok": True, "assumptions": rep, "assumption_count": len(rep["assumptions"])}


def test_panel_constructs_and_renders(app):
    from ui.engineering_assumption_panel import EngineeringAssumptionPanel
    p = EngineeringAssumptionPanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.engineering_assumption_panel import EngineeringAssumptionPanel
    p = EngineeringAssumptionPanel()
    p.update_result(_report(empty=True))
    assert p._cards == []


def test_panel_none_and_error_safe(app):
    from ui.engineering_assumption_panel import EngineeringAssumptionPanel
    p = EngineeringAssumptionPanel()
    p.update_result(None)
    assert p._cards == []
    p.update_result({"ok": False, "error": "boom"})
    assert p._cards == []


def test_panel_no_mutation_controls(app):
    from ui.engineering_assumption_panel import EngineeringAssumptionPanel
    p = EngineeringAssumptionPanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []


def test_states_distinguishable_without_colour(app):
    from strategy.programme_assumption_register_render import render_assumption_sections
    titles = [t for t, _ in render_assumption_sections(_report()["assumptions"])]
    for expected in ("Blocking assumptions (conclusion unusable if wrong)",
                     "Readiness-capping assumptions",
                     "Conservative bounds (deliberate cautions, labelled)"):
        assert expected in titles


def test_no_setup_values_rendered(app):
    from strategy.programme_assumption_register_render import render_assumption_text
    import re
    txt = render_assumption_text(_report()["assumptions"])
    assert not re.search(r"(arb_front|lsd_accel|springs_front)\s*[=:]\s*-?\d", txt)


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_programme_assumption_register")
    assert hasattr(page, "_assumption_panel")
    page.update_programme_assumption_register(_report())
    assert len(page._assumption_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    for attr in ("_knowledge_panel", "_transfer_panel", "_playbook_panel", "_timeline_panel",
                 "_revalidation_panel", "_coverage_panel", "_readiness_panel",
                 "_contradiction_panel", "_assumption_panel"):
        assert hasattr(page, attr), attr


def test_stale_worker_result_ignored(app):
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Page:
        def update_programme_assumption_register(self, r):
            rendered["r"] = r

    stub._development_history_page = _Page()
    newest = object()
    stub._assumption_worker = newest
    dash.MainWindow._on_programme_assumption_register_ready(
        stub, {"ok": True, "assumptions": None, "assumption_count": 0}, object())
    assert "r" not in rendered
    dash.MainWindow._on_programme_assumption_register_ready(
        stub, {"ok": True, "assumptions": None, "assumption_count": 0}, newest)
    assert "r" in rendered


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "assumptions": None, "assumption_count": 0}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r), app.quit()))
    w.failed.connect(lambda m: (seen.__setitem__("err", m), app.quit()))
    QTimer.singleShot(0, w.start)
    QTimer.singleShot(5000, app.quit)
    app.exec()
    w.wait(2000)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
