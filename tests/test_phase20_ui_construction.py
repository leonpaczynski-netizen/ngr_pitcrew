"""Phase 20 — UI construction, no mutation controls, off-thread worker reuse."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.knowledge_quality import build_knowledge_quality


def _efficiency(cid="c1"):
    return {"content_fingerprint": "fp", "context_summary": {"car": "RSR"}, "campaigns": [{
        "campaign_id": cid, "objective": "Cure entry understeer", "status": "active",
        "remaining_information_gain": "high", "estimated_remaining_laps": 13,
        "estimated_remaining_tyre_sets": 1.0, "estimated_remaining_time_minutes": 26.0,
        "saturation": {"status": "building", "information_gain_remaining": "high", "signals": {
            "confirmations": 1, "partial_improvements": 0, "regressions": 0, "no_change": 0,
            "executed": 1, "conflicting_evidence": False, "unresolved_mechanisms": 1,
            "remaining_untested_experiments": 1, "remaining_discriminating_experiments": 1}}}]}


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(empty=False):
    if empty:
        return {"ok": True, "knowledge_quality": None, "campaign_count": 0}
    q = build_knowledge_quality(_efficiency(),
                                calibration={"calibration": {"reconciliations": 2,
                                                             "overall_accuracy": 0.8}}).to_dict()
    return {"ok": True, "knowledge_quality": q, "campaign_count": len(q["campaigns"])}


def test_panel_constructs_and_renders(app):
    from ui.engineering_confidence_panel import EngineeringConfidencePanel
    p = EngineeringConfidencePanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.engineering_confidence_panel import EngineeringConfidencePanel
    p = EngineeringConfidencePanel()
    p.update_result(_report(empty=True))
    assert p._cards == []


def test_panel_none_safe(app):
    from ui.engineering_confidence_panel import EngineeringConfidencePanel
    p = EngineeringConfidencePanel()
    p.update_result(None)
    assert p._cards == []


def test_panel_no_mutation_controls(app):
    from ui.engineering_confidence_panel import EngineeringConfidencePanel
    p = EngineeringConfidencePanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_engineering_knowledge_quality")
    assert hasattr(page, "_confidence_panel")
    page.update_engineering_knowledge_quality(_report())
    assert len(page._confidence_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_phase12_knowledge_panel_still_present(app):
    """The Phase-20 panel must NOT displace the Phase-12 EngineeringKnowledgePanel."""
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "_knowledge_panel")       # Phase 12
    assert hasattr(page, "_confidence_panel")       # Phase 20 (distinct)


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "knowledge_quality": None, "campaign_count": 0}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r), app.quit()))
    w.failed.connect(lambda m: (seen.__setitem__("err", m), app.quit()))
    from tests._qt_worker_wait import drive_worker
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
