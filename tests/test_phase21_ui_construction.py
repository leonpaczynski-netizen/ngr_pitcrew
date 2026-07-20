"""Phase 21 — UI construction, no mutation controls, off-thread worker reuse."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.season_engineering_report import build_season_report


def _prog(cid, fam, reg, fields, mech):
    return {"identity": {"campaign_id": cid, "objective_family": fam, "objective_region": reg,
                         "car": "RSR", "track": "Fuji", "layout": "fc", "discipline": "Race"},
            "objective": {"title": f"{fam}-{reg}", "source_mechanisms": mech}, "status": "active",
            "experiments": [{"field": f, "engineering_value": 0.6} for f in fields]}


def _eff(cid):
    return {"campaign_id": cid, "objective": cid, "remaining_information_gain": "high",
            "estimated_remaining_laps": 13, "estimated_remaining_tyre_sets": 1.0,
            "estimated_remaining_time_minutes": 26.0,
            "experiment_costs": [{"engineering_value": 0.6, "testable": True,
                                  "field": "arb_front"}],
            "saturation": {"signals": {"confirmations": 1, "regressions": 0, "executed": 1,
                                       "conflicting_evidence": False, "unresolved_mechanisms": 0,
                                       "remaining_untested_experiments": 1}}}


def _qual(cid):
    return {"campaign_id": cid, "objective": cid,
            "confidence": {"overall_level": "medium", "overall_score": 0.7},
            "roi": {"knowledge_gap": 0.3, "testable": True},
            "opportunity": {"opportunity": "worth_another_confirmation", "worthwhile": True}}


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(empty=False):
    if empty:
        return {"ok": True, "season_report": None, "campaign_count": 0}
    prog = {"content_fingerprint": "p", "context_summary": {"car": "RSR"},
            "campaigns": [_prog("A", "rotation", "front", ["arb_front"], ["m1"]),
                          _prog("B", "rotation", "front", ["arb_front"], ["m2"])]}
    eff = {"content_fingerprint": "e", "campaigns": [_eff("A"), _eff("B")]}
    qual = {"content_fingerprint": "q", "campaigns": [_qual("A"), _qual("B")]}
    rep = build_season_report(prog, eff, qual).to_dict()
    return {"ok": True, "season_report": rep, "campaign_count": len(rep["campaigns"])}


def test_panel_constructs_and_renders(app):
    from ui.engineering_season_panel import EngineeringSeasonPanel
    p = EngineeringSeasonPanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.engineering_season_panel import EngineeringSeasonPanel
    p = EngineeringSeasonPanel()
    p.update_result(_report(empty=True))
    assert p._cards == []


def test_panel_none_safe(app):
    from ui.engineering_season_panel import EngineeringSeasonPanel
    p = EngineeringSeasonPanel()
    p.update_result(None)
    assert p._cards == []


def test_panel_no_mutation_controls(app):
    from ui.engineering_season_panel import EngineeringSeasonPanel
    p = EngineeringSeasonPanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_season_engineering_report")
    assert hasattr(page, "_season_panel")
    page.update_season_engineering_report(_report())
    assert len(page._season_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "_knowledge_panel")     # Phase 12
    assert hasattr(page, "_efficiency_panel")     # Phase 19
    assert hasattr(page, "_confidence_panel")     # Phase 20
    assert hasattr(page, "_season_panel")         # Phase 21


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "season_report": None, "campaign_count": 0}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r), app.quit()))
    w.failed.connect(lambda m: (seen.__setitem__("err", m), app.quit()))
    from tests._qt_worker_wait import drive_worker
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
