"""Phase 32 — UI construction, no mutation/priority controls, off-thread + stale-worker protection."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.assurance_engineering_priority import build_assurance_engineering_priority


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(empty=False, no_action=False):
    if empty:
        return {"ok": True, "priority": None, "grade": "insufficient_evidence", "candidate_count": 0}
    if no_action:
        a = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                                  "driver": "L"}, "assurance_grade": "assured",
             "totals": {"blocking": 0, "major": 0},
             "findings": [{"finding_type": "clean", "severity": "informational", "domain": "",
                           "source_phase": "audit"}], "content_fingerprint": "p31"}
        rep = build_assurance_engineering_priority(a, {}, {}, {}, {}).to_dict()
        return {"ok": True, "priority": rep, "grade": rep["assurance_grade"],
                "candidate_count": rep["candidate_count"]}
    a = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1", "driver": "L"},
         "assurance_grade": "not_assured", "totals": {"blocking": 1, "major": 1},
         "findings": [{"finding_type": "open_contradiction", "severity": "blocking",
                       "domain": "differential", "source_phase": "P31"},
                      {"finding_type": "dependent_evidence_reliance", "severity": "moderate",
                       "domain": "differential", "source_phase": "P30"},
                      {"finding_type": "single_context_reliance", "severity": "major",
                       "domain": "springs", "source_phase": "P30"}],
         "content_fingerprint": "p31"}
    cov = {"domain_coverage": [
        {"domain": "differential", "gap_count": 1, "evidence_totals": {"independent": 1,
         "dependent": 5, "record_count": 6}},
        {"domain": "springs", "gap_count": 1, "evidence_totals": {"independent": 2, "dependent": 0,
         "record_count": 2}}], "content_fingerprint": "p27"}
    rep = build_assurance_engineering_priority(a, {}, cov, {}, {}).to_dict()
    return {"ok": True, "priority": rep, "grade": rep["assurance_grade"],
            "candidate_count": rep["candidate_count"]}


def test_panel_constructs_and_renders(app):
    from ui.assurance_engineering_priority_panel import AssuranceEngineeringPriorityPanel
    p = AssuranceEngineeringPriorityPanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.assurance_engineering_priority_panel import AssuranceEngineeringPriorityPanel
    p = AssuranceEngineeringPriorityPanel()
    p.update_result(_report(empty=True))
    assert p._cards == []


def test_panel_no_action_state_renders_truthfully(app):
    from ui.assurance_engineering_priority_panel import AssuranceEngineeringPriorityPanel
    from ui import assurance_engineering_priority_vm as vm
    p = AssuranceEngineeringPriorityPanel()
    r = _report(no_action=True)
    p.update_result(r)
    # a fully-assured programme shows the no-action card, not an empty panel
    assert len(p._cards) == 1
    assert "no action" in vm.top_priority(r) or "protected" in vm.header_text(r).lower()


def test_panel_none_and_error_safe(app):
    from ui.assurance_engineering_priority_panel import AssuranceEngineeringPriorityPanel
    p = AssuranceEngineeringPriorityPanel()
    p.update_result(None)
    assert p._cards == []
    p.update_result({"ok": False, "error": "boom"})
    assert p._cards == []


def test_panel_no_mutation_or_priority_controls(app):
    from ui.assurance_engineering_priority_panel import AssuranceEngineeringPriorityPanel
    p = AssuranceEngineeringPriorityPanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []   # no Apply/Run/Create/Schedule buttons, no editable priority inputs


def test_score_breakdown_and_dependencies_visible(app):
    from strategy.assurance_engineering_priority_render import render_priority_sections
    titles = [t for t, _ in render_priority_sections(_report()["priority"])]
    assert "Highest-priority evidence to collect" in titles
    assert "Unresolved prerequisites" in titles
    text = "\n".join(ln for _, lines in render_priority_sections(_report()["priority"])
                     for ln in lines)
    assert "Score breakdown" in text and "Dependencies" in text and "Expected effect" in text


def test_no_setup_values_rendered(app):
    from strategy.assurance_engineering_priority_render import render_priority_text
    import re
    txt = render_priority_text(_report()["priority"])
    assert not re.search(r"(arb_front|lsd_accel|springs_front)\s*[=:]\s*-?\d", txt)


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_assurance_engineering_priority_report")
    assert hasattr(page, "_priority_panel")
    page.update_assurance_engineering_priority_report(_report())
    assert len(page._priority_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    for attr in ("_knowledge_panel", "_transfer_panel", "_playbook_panel", "_timeline_panel",
                 "_revalidation_panel", "_coverage_panel", "_readiness_panel",
                 "_contradiction_panel", "_assumption_panel", "_assurance_panel", "_priority_panel"):
        assert hasattr(page, attr), attr


def test_stale_worker_result_ignored(app):
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Page:
        def update_assurance_engineering_priority_report(self, r):
            rendered["r"] = r

    stub._development_history_page = _Page()
    newest = object()
    stub._priority_worker = newest
    dash.MainWindow._on_assurance_engineering_priority_report_ready(
        stub, {"ok": True, "priority": None, "grade": "insufficient_evidence",
               "candidate_count": 0}, object())
    assert "r" not in rendered
    dash.MainWindow._on_assurance_engineering_priority_report_ready(
        stub, {"ok": True, "priority": None, "grade": "insufficient_evidence",
               "candidate_count": 0}, newest)
    assert "r" in rendered


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "priority": None, "grade": "insufficient_evidence", "candidate_count": 0}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r), app.quit()))
    w.failed.connect(lambda m: (seen.__setitem__("err", m), app.quit()))
    from tests._qt_worker_wait import drive_worker
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
