"""Phase 16 — UI construction, no Apply/edit controls, off-thread."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.experiment_lifecycle import assemble_lifecycle_summary


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report():
    summ = assemble_lifecycle_summary(
        candidate={"candidate_id": "c1", "status": "ready_for_preflight",
                   "deltas": [{"source_mechanism_id": "m1"}], "baseline": {"setup_hash": "h"}},
        hypothesis_set={"source_diagnosis_key": "d1",
                        "canonical_issue": {"issue_type": "entry_understeer"},
                        "source_annotation": {"primary_mechanism":
                                              {"name": "Front roll stiffness", "mechanism_id": "m1"}}},
        experiment={"id": "42", "status": "completed"},
        outcome={"id": "9", "status": "confirmed_improvement"},
        reconciliation={"record_key": "rk", "prediction_fingerprint": "pf"},
        calibration={"reconciliations": 2, "overall_accuracy": 0.7}, diagnosis_key="d1")
    return {"ok": True, "stages": [summ.to_dict()], "count": 1, "ready_count": 1,
            "reconciliation_count": 2, "calibration": {"reconciliations": 2}}


def test_panel_constructs_and_renders(app):
    from ui.engineering_lifecycle_panel import EngineeringLifecyclePanel
    p = EngineeringLifecyclePanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.engineering_lifecycle_panel import EngineeringLifecyclePanel
    p = EngineeringLifecyclePanel()
    p.update_result({"ok": True, "stages": [], "count": 0})
    assert p._cards == []


def test_panel_no_apply_or_edit_controls(app):
    from ui.engineering_lifecycle_panel import EngineeringLifecyclePanel
    p = EngineeringLifecyclePanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_engineering_lifecycle")
    assert hasattr(page, "_lifecycle_panel")
    page.update_engineering_lifecycle(_report())
    assert len(page._lifecycle_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "stages": [], "count": 0}

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
