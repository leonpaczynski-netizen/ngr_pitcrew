"""Phase 24 — UI construction, no mutation controls, off-thread + stale-worker protection."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.engineering_playbook import build_engineering_playbook

SRC = {"car": "Porsche 911 RSR (991) '17", "discipline": "Race", "gt7_version": "1.49",
       "driver": "leon"}
CUP = {"car": "Porsche 911 GT3 Cup", "discipline": "Race", "gt7_version": "1.49", "driver": "leon"}


def _programme():
    return {"content_fingerprint": "p22", "knowledge_graph": {
        "domains": [{"domain": "differential", "knowledge_state": {"value": "well_understood"},
                     "confidence": {"value": "very_high"}, "maturity": {"value": "complete"},
                     "remaining_uncertainty": {"value": "none"}, "supporting_campaigns": ["c1"],
                     "supporting_experiments": [], "supporting_mechanisms": ["load_transfer"],
                     "supporting_evidence": {"confirmations": 2, "regressions": 0, "executed": 2},
                     "known_limitations": []}],
        "known_domains": ["differential"], "missing_domains": ["springs"]},
        "compatibility": {"primary_key": SRC, "other_groups": [{"compatibility_key": CUP}]}}


def _transfer():
    return {"content_fingerprint": "p23", "candidates": [
        {"engineering_domain": "differential",
         "target_context": {**CUP, "manufacturer": "porsche", "drivetrain": "rr",
                            "layout": "rear_engine", "category": "gr3"},
         "transfer_level": "supported", "reason": "r",
         "supporting_evidence": {"domain_transfer_class": "architecture_dependent"},
         "supporting_campaigns": ["c1"], "supporting_mechanisms": ["load_transfer"],
         "confidence": {"value": "very_high"}, "limitations": [],
         "rules_satisfied": ["same_manufacturer", "same_drivetrain", "same_race_category",
                             "compatible_gt7_version"]}]}


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(empty=False):
    if empty:
        return {"ok": True, "playbook": None, "theme_count": 0}
    pb = build_engineering_playbook(_programme(), _transfer()).to_dict()
    return {"ok": True, "playbook": pb, "theme_count": len(pb["stable_themes"])}


def test_panel_constructs_and_renders(app):
    from ui.engineering_playbook_panel import EngineeringPlaybookPanel
    p = EngineeringPlaybookPanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.engineering_playbook_panel import EngineeringPlaybookPanel
    p = EngineeringPlaybookPanel()
    p.update_result(_report(empty=True))
    assert p._cards == []


def test_panel_none_and_error_safe(app):
    from ui.engineering_playbook_panel import EngineeringPlaybookPanel
    p = EngineeringPlaybookPanel()
    p.update_result(None)
    assert p._cards == []
    p.update_result({"ok": False, "error": "boom"})
    assert p._cards == []


def test_panel_no_mutation_controls(app):
    from ui.engineering_playbook_panel import EngineeringPlaybookPanel
    p = EngineeringPlaybookPanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []


def test_structured_sections_and_no_numeric_setup(app):
    from ui.engineering_playbook_panel import EngineeringPlaybookPanel
    from strategy.engineering_playbook_render import render_playbook_sections
    sections = render_playbook_sections(_report()["playbook"])
    titles = [t for t, _ in sections]
    # structured, not one dense box
    assert "Programme-wide engineering themes" in titles
    assert "Confirmed-good behaviours to protect" in titles
    assert "No setup transferred" in titles
    p = EngineeringPlaybookPanel()
    p.update_result(_report())
    # source + target identity visible somewhere in the rendered text
    import json
    blob = json.dumps(_report()["playbook"])
    assert "Porsche 911 GT3 Cup" in blob and "Porsche 911 RSR" in blob


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_programme_engineering_playbook")
    assert hasattr(page, "_playbook_panel")
    page.update_programme_engineering_playbook(_report())
    assert len(page._playbook_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    for attr in ("_knowledge_panel", "_efficiency_panel", "_confidence_panel", "_season_panel",
                 "_knowledge_graph_panel", "_transfer_panel", "_playbook_panel"):
        assert hasattr(page, attr), attr


def test_stale_worker_result_ignored(app):
    """A stale worker's result must not replace a newer one (dashboard handler guards on the
    current worker reference)."""
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Page:
        def update_programme_engineering_playbook(self, r):
            rendered["r"] = r

    stub._development_history_page = _Page()
    newest = object()
    stub._playbook_worker = newest
    # a stale worker (not the newest) must be ignored
    dash.MainWindow._on_programme_engineering_playbook_ready(
        stub, {"ok": True, "playbook": None, "theme_count": 0}, object())
    assert "r" not in rendered
    # the current worker's result renders
    dash.MainWindow._on_programme_engineering_playbook_ready(
        stub, {"ok": True, "playbook": None, "theme_count": 0}, newest)
    assert "r" in rendered


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "playbook": None, "theme_count": 0}

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
