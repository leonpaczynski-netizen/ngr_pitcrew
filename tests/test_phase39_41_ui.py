"""Phase 39-41 — closed-loop workflow UI: construction, embedding, off-thread, stale-guard."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication

from data.session_db import SessionDB
from tests._assurance_pack_helpers import seed_contradiction, applied, KW
from tests._qt_worker_wait import drive_worker


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _workflow(observation=None):
    import tempfile
    p = tempfile.mktemp(suffix=".db")
    db = SessionDB(p); seed_contradiction(db, 3, 2)
    r = db.build_closed_loop_workflow_report(observation=observation, applied_setup=applied(),
                                             parent_setup={"name": "A"}, now_date="2026-07-10", **KW)
    db.close()
    try:
        os.remove(p)
    except OSError:
        pass
    return r


def test_panel_constructs_three_steps(app):
    from ui.closed_loop_workflow_panel import ClosedLoopWorkflowPanel
    p = ClosedLoopWorkflowPanel()
    p.update_result(_workflow())
    assert len(p._cards) == 3   # Evidence Readiness / Practice Run Plan / Outcome Review


def test_panel_empty_and_none_safe(app):
    from ui.closed_loop_workflow_panel import ClosedLoopWorkflowPanel
    p = ClosedLoopWorkflowPanel()
    p.update_result(None)
    assert p._cards == []
    p.update_result({"ok": True, "run_plan": None})
    assert p._cards == []


def test_panel_has_no_apply_or_experiment_buttons(app):
    from PyQt6.QtWidgets import QPushButton
    from ui.closed_loop_workflow_panel import ClosedLoopWorkflowPanel
    p = ClosedLoopWorkflowPanel()
    p.update_result(_workflow())
    labels = [b.text().lower() for b in p.findChildren(QPushButton)]
    for bad in ("apply", "create experiment", "record outcome", "promote", "schedule"):
        assert not any(bad in l for l in labels), bad


def test_panel_cards_have_accessible_names(app):
    from ui.closed_loop_workflow_panel import ClosedLoopWorkflowPanel
    p = ClosedLoopWorkflowPanel()
    p.update_result(_workflow())
    assert all(c.accessibleName() for c in p._cards)


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "_closed_loop_panel")
    page.update_closed_loop_workflow(_workflow())
    assert len(page._closed_loop_panel._cards) == 3


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert (hasattr(page, "_race_engineer_team_panel") and hasattr(page, "_closed_loop_panel")
            and hasattr(page, "_review_pack_panel"))


def test_outcome_review_shows_rollback_on_regression(app):
    obs = dict(candidate_tested=True, applied_setup_matches_plan=True, context_matches_plan=True,
               telemetry_complete=True, clean_laps=5, min_clean_required=3, compound_used="RH",
               planned_compound="RH", new_regressions=["rear"])
    r = _workflow(observation=obs)
    assert (r["closed_loop"] or {}).get("primary_next_action", {}).get("kind") == "roll_back"


def test_stale_worker_result_ignored(app):
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Page:
        def update_closed_loop_workflow(self, r):
            rendered["r"] = r

    stub._development_history_page = _Page()
    newest = object()
    stub._closed_loop_worker = newest
    dash.MainWindow._on_closed_loop_workflow_ready(stub, {"ok": True, "run_plan": None}, object())
    assert "r" not in rendered
    dash.MainWindow._on_closed_loop_workflow_ready(stub, {"ok": True, "run_plan": None}, newest)
    assert "r" in rendered


def test_workflow_build_runs_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "run_plan": None}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r)))
    w.failed.connect(lambda m: seen.__setitem__("err", m))
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
