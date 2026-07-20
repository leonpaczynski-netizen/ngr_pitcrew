"""Phase 22 — UI construction, no mutation controls, off-thread worker reuse."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.programme_knowledge_report import build_programme_knowledge


def _camp(cid, fields, track="Fuji"):
    return {"campaign_id": cid, "objective": cid, "family": "traction", "fields": fields,
            "mechanisms": ["load_transfer"], "confidence_level": "high",
            "knowledge_state": "well_understood", "track": track, "confirmations": 2,
            "regressions": 0, "conflicting": False, "unresolved_mechanisms": 0, "executed": 2,
            "remaining_information_gain": "low", "testable": False}


def _ctx():
    return {"car": "RSR", "track": "Fuji", "layout": "fc", "discipline": "Race",
            "gt7_version": "1.49", "driver": "leon"}


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(empty=False):
    if empty:
        return {"ok": True, "programme_knowledge": None, "known_domain_count": 0}
    events = [{"context": _ctx(), "campaigns": [_camp("a", ["lsd_accel"]),
                                                _camp("b", ["arb_front"])]}]
    pk = build_programme_knowledge(events, primary_context=_ctx()).to_dict()
    return {"ok": True, "programme_knowledge": pk,
            "known_domain_count": len(pk["knowledge_graph"]["known_domains"])}


def test_panel_constructs_and_renders(app):
    from ui.engineering_knowledge_graph_panel import EngineeringKnowledgeGraphPanel
    p = EngineeringKnowledgeGraphPanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.engineering_knowledge_graph_panel import EngineeringKnowledgeGraphPanel
    p = EngineeringKnowledgeGraphPanel()
    p.update_result(_report(empty=True))
    assert p._cards == []


def test_panel_none_safe(app):
    from ui.engineering_knowledge_graph_panel import EngineeringKnowledgeGraphPanel
    p = EngineeringKnowledgeGraphPanel()
    p.update_result(None)
    assert p._cards == []


def test_panel_no_mutation_controls(app):
    from ui.engineering_knowledge_graph_panel import EngineeringKnowledgeGraphPanel
    p = EngineeringKnowledgeGraphPanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_programme_knowledge_report")
    assert hasattr(page, "_knowledge_graph_panel")
    page.update_programme_knowledge_report(_report())
    assert len(page._knowledge_graph_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "_knowledge_panel")          # Phase 12
    assert hasattr(page, "_efficiency_panel")          # Phase 19
    assert hasattr(page, "_confidence_panel")          # Phase 20
    assert hasattr(page, "_season_panel")              # Phase 21
    assert hasattr(page, "_knowledge_graph_panel")     # Phase 22


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "programme_knowledge": None, "known_domain_count": 0}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r), app.quit()))
    w.failed.connect(lambda m: (seen.__setitem__("err", m), app.quit()))
    from tests._qt_worker_wait import drive_worker
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
