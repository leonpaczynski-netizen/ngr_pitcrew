"""Phase 13 — UI construction + off-thread + no-Apply tests (Section 23.10, 20).

Constructs the panel and the Development History page, renders a real annotation and an
invalid-annotation state, proves there are no Apply/Revert controls, that heavy work is not
done in the widget (the panel only renders a pre-built dict), and that the worker runs the
build OFF the Qt thread.
"""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QPushButton
from PyQt6.QtCore import QTimer

from strategy.mechanism_annotation import annotate_diagnosis


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(**over):
    d = {"issue_family": "traction", "issue_type": "wheelspin", "axle": "rear",
         "phase": "exit", "segment_id": "T4", "residual_state": "worsened",
         "recurring": True, "valid_laps": 5, "key": "u"}
    d.update(over)
    a = annotate_diagnosis(d, failed_directions=[("lsd_accel", "increase")])
    return {"ok": True, "annotations": [a.to_dict()], "count": 1, "supported_count": 1}


def test_panel_constructs_and_renders(app):
    from ui.mechanism_annotation_panel import MechanismAnnotationPanel
    p = MechanismAnnotationPanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_renders_invalid_state(app):
    from ui.mechanism_annotation_panel import MechanismAnnotationPanel
    inv = annotate_diagnosis({"issue_family": "traction", "issue_type": "wheelspin",
                              "axle": "rear", "phase": "exit",
                              "residual_state": "invalid_comparison", "key": "j"},
                             decision_state="invalid")
    p = MechanismAnnotationPanel()
    p.update_result({"ok": True, "annotations": [inv.to_dict()], "count": 1})
    assert len(p._cards) == 1   # renders the "unavailable" explanation card


def test_panel_empty_state(app):
    from ui.mechanism_annotation_panel import MechanismAnnotationPanel
    p = MechanismAnnotationPanel()
    p.update_result({"ok": True, "annotations": [], "count": 0})
    assert p._cards == []


def test_panel_has_no_apply_or_revert_controls(app):
    from ui.mechanism_annotation_panel import MechanismAnnotationPanel
    p = MechanismAnnotationPanel()
    p.update_result(_report())
    assert p.findChildren(QPushButton) == []   # no action controls whatsoever


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_mechanism_annotations")
    assert hasattr(page, "_mechanism_panel")
    page.update_mechanism_annotations(_report())
    assert len(page._mechanism_panel._cards) == 1
    # the rest of the Development History workflow is intact
    page.update_result({"ok": True, "record_count": 0})


def test_worker_runs_build_off_the_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "annotations": [], "count": 0}

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
