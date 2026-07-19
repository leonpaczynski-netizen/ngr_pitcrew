"""Phase 14 — UI construction, no-Apply, off-thread tests (Section 22)."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QPushButton
from PyQt6.QtCore import QTimer

from strategy.mechanism_annotation import annotate_diagnosis
from strategy.intervention_hypothesis import build_intervention_hypotheses


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(**over):
    d = {"issue_family": "rotation", "issue_type": "entry_understeer", "axle": "front",
         "phase": "entry", "segment_id": "T1", "residual_state": "unchanged",
         "recurring": True, "valid_laps": 4, "key": "u"}
    d.update(over)
    a = annotate_diagnosis(d)
    s = build_intervention_hypotheses(a.to_dict())
    return {"ok": True, "hypothesis_sets": [s.to_dict()], "count": 1,
            "sets_with_testable": 1, "safety_statements": ["advisory only"]}


def test_panel_constructs_and_renders(app):
    from ui.intervention_hypothesis_panel import InterventionHypothesisPanel
    p = InterventionHypothesisPanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_and_blocked_states(app):
    from ui.intervention_hypothesis_panel import InterventionHypothesisPanel
    p = InterventionHypothesisPanel()
    p.update_result({"ok": True, "hypothesis_sets": [], "count": 0})
    assert p._cards == []
    blocked = build_intervention_hypotheses(annotate_diagnosis(
        {"issue_family": "traction", "issue_type": "wheelspin", "axle": "rear",
         "phase": "exit", "residual_state": "invalid_comparison", "key": "j"},
        decision_state="invalid").to_dict())
    p.update_result({"ok": True, "hypothesis_sets": [blocked.to_dict()], "count": 1})
    assert len(p._cards) == 1


def test_panel_has_no_apply_or_approve_controls(app):
    from ui.intervention_hypothesis_panel import InterventionHypothesisPanel
    p = InterventionHypothesisPanel()
    p.update_result(_report())
    assert p.findChildren(QPushButton) == []


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_intervention_hypotheses")
    assert hasattr(page, "_intervention_panel")
    page.update_intervention_hypotheses(_report())
    assert len(page._intervention_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})   # rest of workflow intact


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "hypothesis_sets": [], "count": 0}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r), app.quit()))
    w.failed.connect(lambda m: (seen.__setitem__("err", m), app.quit()))
    QTimer.singleShot(0, w.start)
    QTimer.singleShot(5000, app.quit)
    app.exec()
    w.wait(2000)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main
    assert seen.get("result", {}).get("ok")
