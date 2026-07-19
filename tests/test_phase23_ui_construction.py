"""Phase 23 — UI construction, no mutation controls, off-thread worker reuse."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.programme_transfer_report import build_transfer_report


def _graph():
    return {"domains": [
        {"domain": "springs", "maturity": {"value": "mature"}, "confidence": {"value": "high"},
         "knowledge_state": {"value": "well_understood"},
         "supporting_mechanisms": ["stiffness"], "supporting_campaigns": ["c1"]},
        {"domain": "vehicle_balance", "maturity": {"value": "complete"},
         "confidence": {"value": "very_high"}, "knowledge_state": {"value": "well_understood"},
         "supporting_mechanisms": ["balance"], "supporting_campaigns": ["c2"]}]}


def _src():
    return {"car": "Porsche 911 RSR (991) '17", "discipline": "Race", "gt7_version": "1.49",
            "driver": "leon"}


def _targets():
    return [{"car": "Porsche 911 GT3 Cup", "discipline": "Race", "gt7_version": "1.49",
             "driver": "leon"}]


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(empty=False):
    if empty:
        return {"ok": True, "transfer_report": None, "candidate_count": 0}
    tr = build_transfer_report(_graph(), _src(), _targets()).to_dict()
    return {"ok": True, "transfer_report": tr, "candidate_count": len(tr["candidates"])}


def test_panel_constructs_and_renders(app):
    from ui.engineering_transfer_panel import EngineeringTransferPanel
    p = EngineeringTransferPanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.engineering_transfer_panel import EngineeringTransferPanel
    p = EngineeringTransferPanel()
    p.update_result(_report(empty=True))
    assert p._cards == []


def test_panel_none_safe(app):
    from ui.engineering_transfer_panel import EngineeringTransferPanel
    p = EngineeringTransferPanel()
    p.update_result(None)
    assert p._cards == []


def test_panel_no_mutation_controls(app):
    from ui.engineering_transfer_panel import EngineeringTransferPanel
    p = EngineeringTransferPanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_programme_transfer_report")
    assert hasattr(page, "_transfer_panel")
    page.update_programme_transfer_report(_report())
    assert len(page._transfer_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    for attr in ("_knowledge_panel", "_efficiency_panel", "_confidence_panel", "_season_panel",
                 "_knowledge_graph_panel", "_transfer_panel"):
        assert hasattr(page, attr), attr


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "transfer_report": None, "candidate_count": 0}

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
