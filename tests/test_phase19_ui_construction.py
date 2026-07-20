"""Phase 19 — UI construction, no mutation controls, off-thread worker reuse."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.campaign_persistence import build_engineering_efficiency


def _campaign(cid="camp_1"):
    return {
        "identity": {"campaign_id": cid, "car": "Porsche 911 RSR", "track": "Fuji",
                     "layout": "fc", "discipline": "Race", "objective_family": "rotation",
                     "objective_region": "entry", "gt7_version": "1.49"},
        "objective": {"title": "Cure entry understeer"},
        "status": "active",
        "experiments": [{"candidate_id": "c1", "phase17_rank": 0, "engineering_value": 0.8,
                         "campaign_role": "primary_discriminator", "outcome_state": "not_tested",
                         "field": "arb_front", "attribution_scope": "single_field"}],
        "progress": {"confirmed_improvement": 0, "unresolved_mechanisms": 1},
    }


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(empty=False):
    if empty:
        return {"ok": True, "efficiency": None, "campaign_count": 0}
    eff = build_engineering_efficiency(
        {"content_fingerprint": "fp", "context_summary": {"car": "RSR"},
         "campaigns": [_campaign()]},
        registry=[], session_budget={"session_minutes_remaining": 60},
        now_date="2026-07-10").to_dict()
    return {"ok": True, "efficiency": eff, "campaign_count": len(eff["campaigns"])}


def test_panel_constructs_and_renders(app):
    from ui.engineering_efficiency_panel import EngineeringEfficiencyPanel
    p = EngineeringEfficiencyPanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.engineering_efficiency_panel import EngineeringEfficiencyPanel
    p = EngineeringEfficiencyPanel()
    p.update_result(_report(empty=True))
    assert p._cards == []


def test_panel_none_safe(app):
    from ui.engineering_efficiency_panel import EngineeringEfficiencyPanel
    p = EngineeringEfficiencyPanel()
    p.update_result(None)
    assert p._cards == []


def test_panel_no_mutation_controls(app):
    from ui.engineering_efficiency_panel import EngineeringEfficiencyPanel
    p = EngineeringEfficiencyPanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_engineering_efficiency")
    assert hasattr(page, "_efficiency_panel")
    page.update_engineering_efficiency(_report())
    assert len(page._efficiency_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "efficiency": None, "campaign_count": 0}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r), app.quit()))
    w.failed.connect(lambda m: (seen.__setitem__("err", m), app.quit()))
    from tests._qt_worker_wait import drive_worker
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
