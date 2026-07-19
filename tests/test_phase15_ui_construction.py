"""Phase 15 — UI construction, no editable/Apply controls, off-thread (Section 20)."""
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
from strategy.experiment_synthesis import synthesize_bounded_experiments as SYN
from strategy.setup_ranges import resolve_ranges
from data.applied_checkpoint import compute_setup_hash

RANGES = dict(resolve_ranges("Porsche 911 RSR"))
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0, "lsd_accel": 20}


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report():
    applied = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "setup_id": "S1",
               "name": "Base", "revision": 1, "state": "applied", "fields": dict(FIELDS),
               "purpose": "Race"}
    applied["setup_hash"] = compute_setup_hash(FIELDS)
    a = annotate_diagnosis({"issue_family": "rotation", "issue_type": "entry_understeer",
                            "axle": "front", "phase": "entry", "segment_id": "T1",
                            "residual_state": "unchanged", "recurring": True, "valid_laps": 4,
                            "sessions_seen": 2, "telemetry_available": True, "key": "k"})
    res = SYN(BIH(a.to_dict()).to_dict(), applied_setup=applied,
              session_identity={"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc"},
              ranges=RANGES)
    return {"ok": True, "synthesis_results": [res.to_dict()], "count": 1,
            "ready_for_preflight": 1, "safety_statement": "advisory only"}


def test_panel_constructs_and_renders(app):
    from ui.experiment_synthesis_panel import ExperimentSynthesisPanel
    p = ExperimentSynthesisPanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_and_blocked(app):
    from ui.experiment_synthesis_panel import ExperimentSynthesisPanel
    p = ExperimentSynthesisPanel()
    p.update_result({"ok": True, "synthesis_results": [], "count": 0})
    assert p._cards == []


def test_panel_no_editable_or_apply_controls(app):
    from ui.experiment_synthesis_panel import ExperimentSynthesisPanel
    p = ExperimentSynthesisPanel()
    p.update_result(_report())
    editable = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert editable == []   # no Apply/Approve/Revert and no numeric editors


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_experiment_synthesis")
    assert hasattr(page, "_synthesis_panel")
    page.update_experiment_synthesis(_report())
    assert len(page._synthesis_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "synthesis_results": [], "count": 0}

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
