"""Phase 18 — UI construction, no mutation controls, off-thread."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.mechanism_annotation import annotate_diagnosis
from strategy.intervention_hypothesis import build_intervention_hypotheses as BIH
from strategy.experiment_synthesis import synthesize_from_report
from strategy.experiment_portfolio import build_portfolio
from strategy.engineering_campaign import build_campaign_programme
from strategy.setup_ranges import resolve_ranges
from data.applied_checkpoint import compute_setup_hash

RANGES = resolve_ranges("Porsche 911 RSR")
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0}
SCOPE = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "discipline": "Race",
         "driver": "leon", "gt7_version": "1.49"}


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(empty=False):
    if empty:
        return {"ok": True, "programme": None, "campaign_count": 0}
    ap = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "setup_id": "S",
          "name": "B", "revision": 1, "state": "applied", "fields": dict(FIELDS),
          "purpose": "Race"}
    ap["setup_hash"] = compute_setup_hash(FIELDS)
    a = annotate_diagnosis({"issue_family": "rotation", "issue_type": "entry_understeer",
                            "axle": "front", "phase": "entry", "residual_state": "unchanged",
                            "recurring": True, "valid_laps": 4, "key": "d1"})
    rep = synthesize_from_report({"ok": True, "hypothesis_sets": [BIH(a.to_dict()).to_dict()]},
                                 applied_setup=ap,
                                 session_identity={"car": "Porsche 911 RSR", "track": "Fuji",
                                                   "layout_id": "fc"}, ranges=RANGES)
    prog = build_campaign_programme(build_portfolio(rep).to_dict(), scope=SCOPE,
                                    active_context=SCOPE)
    return {"ok": True, "programme": prog.to_dict(), "campaign_count": len(prog.campaigns)}


def test_panel_constructs_and_renders(app):
    from ui.engineering_campaign_panel import EngineeringCampaignPanel
    p = EngineeringCampaignPanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.engineering_campaign_panel import EngineeringCampaignPanel
    p = EngineeringCampaignPanel()
    p.update_result(_report(empty=True))
    assert p._cards == []


def test_panel_no_mutation_controls(app):
    from ui.engineering_campaign_panel import EngineeringCampaignPanel
    p = EngineeringCampaignPanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_engineering_campaigns")
    assert hasattr(page, "_campaign_panel")
    page.update_engineering_campaigns(_report())
    assert len(page._campaign_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "programme": None, "campaign_count": 0}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r), app.quit()))
    w.failed.connect(lambda m: (seen.__setitem__("err", m), app.quit()))
    from tests._qt_worker_wait import drive_worker
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
