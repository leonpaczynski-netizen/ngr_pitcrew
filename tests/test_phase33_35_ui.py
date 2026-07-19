"""Phases 33-35 — Assurance Review Pack UI tests: construction, off-thread, stale-guard, safety."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider
from PyQt6.QtCore import QTimer

from strategy.assurance_review_package import build_review_package_spec
from strategy.assurance_snapshot_comparison import compare_assurance_snapshots
from tests._assurance_pack_helpers import synthetic_export


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _preview(has_comparison=False, baseline_valid=None):
    exp = synthetic_export()
    comp = None
    if has_comparison:
        comp = compare_assurance_snapshots(synthetic_export(grade="assured_with_limitations",
                                                            contra_open=False, independent=3,
                                                            findings=[]), exp).to_dict()
    pkg = build_review_package_spec(exp, comp).to_dict()
    return {"ok": True, "package": pkg, "grade": pkg["assurance_grade"],
            "has_comparison": bool(comp), "baseline_valid": baseline_valid}


def test_panel_constructs_standalone(app):
    from ui.assurance_review_pack_panel import AssuranceReviewPackPanel
    p = AssuranceReviewPackPanel()
    p.update_result(_preview())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.assurance_review_pack_panel import AssuranceReviewPackPanel
    p = AssuranceReviewPackPanel()
    p.update_result({"ok": True, "package": None})
    assert p._cards == []
    # compare/export disabled without a current package
    assert not p._compare_btn.isEnabled() and not p._export_btn.isEnabled()


def test_panel_none_and_error_safe(app):
    from ui.assurance_review_pack_panel import AssuranceReviewPackPanel
    p = AssuranceReviewPackPanel()
    p.update_result(None)
    assert p._cards == []
    p.update_result({"ok": False})
    assert p._cards == []


def test_only_export_action_buttons_no_apply_or_editable(app):
    from ui.assurance_review_pack_panel import AssuranceReviewPackPanel
    from PyQt6.QtWidgets import QPushButton
    p = AssuranceReviewPackPanel()
    p.update_result(_preview())
    labels = [b.text().lower() for b in p.findChildren(QPushButton)]
    assert labels == ["preview assurance review", "compare baseline...", "export review package..."]
    for lab in labels:
        for banned in ("apply", "run experiment", "create campaign", "schedule", "certif", "approve"):
            assert banned not in lab
    # no editable data controls at all
    editable = (p.findChildren(QLineEdit) + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert editable == []


def test_no_setup_values_rendered(app):
    import re
    from strategy.assurance_review_package_render import render_package_text
    txt = render_package_text(_preview()["package"])
    assert not re.search(r"(arb_front|lsd_accel)\s*[=:]\s*-?\d", txt)


def test_export_requires_explicit_action(app):
    # the panel never writes; it only fires the injected export handler on an explicit click
    from ui.assurance_review_pack_panel import AssuranceReviewPackPanel
    p = AssuranceReviewPackPanel()
    p.update_result(_preview())
    fired = {"export": 0}
    p.set_action_handlers(export=lambda: fired.__setitem__("export", fired["export"] + 1))
    assert fired["export"] == 0            # nothing happens without a click
    p._export_btn.click()
    assert fired["export"] == 1            # only on explicit action


def test_action_handlers_fire(app):
    from ui.assurance_review_pack_panel import AssuranceReviewPackPanel
    p = AssuranceReviewPackPanel()
    p.update_result(_preview())
    fired = {"p": 0, "c": 0, "e": 0}
    p.set_action_handlers(preview=lambda: fired.__setitem__("p", 1),
                          compare=lambda: fired.__setitem__("c", 1),
                          export=lambda: fired.__setitem__("e", 1))
    p._preview_btn.click(); p._compare_btn.click(); p._export_btn.click()
    assert fired == {"p": 1, "c": 1, "e": 1}


def test_export_status_reports_destination_and_errors(app):
    from ui.assurance_review_pack_panel import AssuranceReviewPackPanel
    p = AssuranceReviewPackPanel()
    p.update_export_status({"ok": True, "destination": "/tmp/x", "files_written": [{"name": "a"}],
                            "archive_path": ""})
    assert "/tmp/x" in p._status.text() and "exported" in p._status.text().lower()
    p.update_export_status({"ok": False, "errors": ["disk full"]})
    assert "failed" in p._status.text().lower() and "disk full" in p._status.text().lower()


def test_baseline_invalid_visible_in_header(app):
    from ui.assurance_review_pack_panel import AssuranceReviewPackPanel
    p = AssuranceReviewPackPanel()
    p.update_result(_preview(baseline_valid=False))
    assert "baseline invalid" in p._header.text().lower()


def test_incompatible_comparison_shows_no_trend(app):
    from strategy.assurance_snapshot_comparison_render import render_comparison_text
    comp = compare_assurance_snapshots(synthetic_export(car="GT-R"),
                                       synthetic_export(car="Supra")).to_dict()
    txt = render_comparison_text(comp).lower()
    assert "no assurance trend" in txt


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_assurance_review_pack")
    assert hasattr(page, "_review_pack_panel")
    page.update_assurance_review_pack(_preview())
    assert len(page._review_pack_panel._cards) == 1


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    for attr in ("_assurance_panel", "_priority_panel", "_review_pack_panel"):
        assert hasattr(page, attr), attr


def test_stale_worker_result_ignored(app):
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Page:
        def update_assurance_review_pack(self, r):
            rendered["r"] = r

    stub._development_history_page = _Page()
    newest = object()
    stub._review_pack_worker = newest
    dash.MainWindow._on_assurance_review_pack_ready(stub, {"ok": True, "package": None}, object())
    assert "r" not in rendered
    dash.MainWindow._on_assurance_review_pack_ready(stub, {"ok": True, "package": None}, newest)
    assert "r" in rendered


def test_export_worker_runs_off_ui_thread(app):
    # the build-and-write happens in a MechanismAnnotationWorker off the UI thread
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "destination": "/tmp/x", "files_written": []}

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
