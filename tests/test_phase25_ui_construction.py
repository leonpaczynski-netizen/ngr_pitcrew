"""Phase 25 — UI construction, no mutation controls, off-thread + stale-worker protection."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QSlider,
)
from PyQt6.QtCore import QTimer

from strategy.programme_timeline_report import build_programme_timeline

SRC = {"car": "Porsche 911 RSR (991) '17", "discipline": "Race", "gt7_version": "1.49",
       "driver": "leon"}


def _programme():
    return {"content_fingerprint": "p22", "knowledge_graph": {
        "domains": [{"domain": "differential", "knowledge_state": {"value": "well_understood"},
                     "confidence": {"value": "very_high"}, "maturity": {"value": "complete"},
                     "remaining_uncertainty": {"value": "none"}, "supporting_campaigns": ["c1"],
                     "supporting_experiments": [], "supporting_mechanisms": ["load_transfer"],
                     "supporting_evidence": {"confirmations": 3, "regressions": 0, "executed": 3},
                     "known_limitations": []},
                    {"domain": "springs", "knowledge_state": {"value": "needs_confirmation"},
                     "confidence": {"value": "low"}, "maturity": {"value": "developing"},
                     "remaining_uncertainty": {"value": "high"}, "supporting_campaigns": ["c2"],
                     "supporting_experiments": [], "supporting_mechanisms": ["stiffness"],
                     "supporting_evidence": {"confirmations": 1, "regressions": 1, "executed": 2},
                     "known_limitations": ["conflicting evidence present"]}],
        "known_domains": ["differential", "springs"], "missing_domains": []},
        "compatibility": {"primary_key": SRC, "other_groups": []}}


def _playbook():
    return {"content_fingerprint": "p24", "stable_themes": [
        {"engineering_domain": "differential", "confirmed_good_protections": [{"behaviour": "x"}]}],
        "knowledge_boundaries": [{"boundary_type": "conflicting_evidence", "domain": "springs",
                                  "target_car": "", "reason": "conflict"}]}


def _rec(field, family, status, session, scope, date):
    return {"record_key": f"{field}-{session}-{status}", "test_session_id": session,
            "scope_fingerprint": scope, "session_date": date, "outcome_status": status,
            "confidence_level": "high", "changes": [{"field": field}],
            "residual_states": [{"family": family}],
            "context": {"car": SRC["car"], "track": "Fuji", "layout_id": "fc",
                        "discipline": "Race"}}


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _report(empty=False):
    if empty:
        return {"ok": True, "timeline": None, "point_count": 0}
    records = [_rec("lsd_accel", "traction", "confirmed_improvement", f"s{i}", f"sc{i}",
                    f"2026-07-0{i}") for i in (1, 3, 5)]
    records += [_rec("springs_front", "rotation", "confirmed_improvement", "sp1", "scS",
                     "2026-07-01"),
                _rec("springs_front", "rotation", "regression", "sp2", "scS", "2026-07-04")]
    tl = build_programme_timeline(_programme(), _playbook(), records).to_dict()
    return {"ok": True, "timeline": tl, "point_count": len(tl["timeline_points"])}


def test_panel_constructs_and_renders(app):
    from ui.engineering_timeline_panel import EngineeringTimelinePanel
    p = EngineeringTimelinePanel()
    p.update_result(_report())
    assert len(p._cards) == 1


def test_panel_empty_state(app):
    from ui.engineering_timeline_panel import EngineeringTimelinePanel
    p = EngineeringTimelinePanel()
    p.update_result(_report(empty=True))
    assert p._cards == []


def test_panel_none_and_error_safe(app):
    from ui.engineering_timeline_panel import EngineeringTimelinePanel
    p = EngineeringTimelinePanel()
    p.update_result(None)
    assert p._cards == []
    p.update_result({"ok": False, "error": "boom"})
    assert p._cards == []


def test_panel_no_mutation_controls(app):
    from ui.engineering_timeline_panel import EngineeringTimelinePanel
    p = EngineeringTimelinePanel()
    p.update_result(_report())
    controls = (p.findChildren(QPushButton) + p.findChildren(QLineEdit)
                + p.findChildren(QSpinBox) + p.findChildren(QDoubleSpinBox)
                + p.findChildren(QComboBox) + p.findChildren(QSlider))
    assert controls == []


def test_states_distinguishable_without_colour(app):
    """Confirmed-good / conflict / regression sections carry text tags (not colour alone)."""
    from strategy.programme_timeline_report_render import render_timeline_sections
    titles = [t for t, _ in render_timeline_sections(_report()["timeline"])]
    for expected in ("Confirmed-good preservation", "Unresolved conflicts",
                     "Regressions and retired directions", "Superseded conclusions"):
        assert expected in titles
    # unknowns and independence lineage are stated in text
    import json
    blob = json.dumps(_report()["timeline"]).lower()
    assert "independent" in blob and "lineage" in blob


def test_no_setup_values_rendered(app):
    from strategy.programme_timeline_report_render import render_timeline_text
    txt = render_timeline_text(_report()["timeline"])
    import re
    assert not re.search(r"(arb_front|lsd_accel|springs_front)\s*[=:]\s*-?\d", txt)


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "update_programme_knowledge_timeline")
    assert hasattr(page, "_timeline_panel")
    page.update_programme_knowledge_timeline(_report())
    assert len(page._timeline_panel._cards) == 1
    page.update_result({"ok": True, "record_count": 0})


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    for attr in ("_knowledge_panel", "_efficiency_panel", "_confidence_panel", "_season_panel",
                 "_knowledge_graph_panel", "_transfer_panel", "_playbook_panel",
                 "_timeline_panel"):
        assert hasattr(page, attr), attr


def test_stale_worker_result_ignored(app):
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Page:
        def update_programme_knowledge_timeline(self, r):
            rendered["r"] = r

    stub._development_history_page = _Page()
    newest = object()
    stub._timeline_worker = newest
    dash.MainWindow._on_programme_knowledge_timeline_ready(
        stub, {"ok": True, "timeline": None, "point_count": 0}, object())
    assert "r" not in rendered
    dash.MainWindow._on_programme_knowledge_timeline_ready(
        stub, {"ok": True, "timeline": None, "point_count": 0}, newest)
    assert "r" in rendered


def test_worker_runs_build_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "timeline": None, "point_count": 0}

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
