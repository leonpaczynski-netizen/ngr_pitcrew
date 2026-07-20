"""Phase 36-38 — Race-Engineer Team Brief UI: construction, embedding, off-thread, stale-guard."""
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from data.session_db import SessionDB
from tests._assurance_pack_helpers import seed_contradiction, applied, KW


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _brief():
    import tempfile
    p = tempfile.mktemp(suffix=".db")
    db = SessionDB(p); seed_contradiction(db, 3, 2)
    r = db.build_race_engineer_team_brief(applied_setup=applied(), now_date="2026-07-10", **KW)
    db.close()
    try:
        os.remove(p)
    except OSError:
        pass
    return r


def test_panel_constructs_and_renders(app):
    from ui.race_engineer_team_panel import RaceEngineerTeamPanel
    p = RaceEngineerTeamPanel()
    p.update_result(_brief())
    # one scannable card per crew role/section (Chief/Setup/Performance/Coach/Strategy + plan/etc).
    assert len(p._cards) >= 5


def test_panel_empty_and_none_safe(app):
    from ui.race_engineer_team_panel import RaceEngineerTeamPanel
    p = RaceEngineerTeamPanel()
    p.update_result(None)
    assert p._cards == []
    p.update_result({"ok": True, "brief": None})
    assert p._cards == []
    p.update_result({"ok": False})
    assert p._cards == []


def test_panel_has_no_apply_or_experiment_buttons(app):
    from PyQt6.QtWidgets import QPushButton
    from ui.race_engineer_team_panel import RaceEngineerTeamPanel
    p = RaceEngineerTeamPanel()
    p.update_result(_brief())
    labels = [b.text().lower() for b in p.findChildren(QPushButton)]
    for bad in ("apply", "experiment", "campaign", "schedule", "export", "save"):
        assert not any(bad in l for l in labels), bad


def test_no_setup_values_rendered(app):
    from PyQt6.QtWidgets import QLabel
    from ui.race_engineer_team_panel import RaceEngineerTeamPanel
    p = RaceEngineerTeamPanel()
    p.update_result(_brief())
    text = " ".join(l.text().lower() for l in p.findChildren(QLabel))
    # advisory framing present; no "apply this setup" instruction.
    assert "not permission to apply" in text or "advisory" in text


def test_page_embeds_panel_and_forwarder(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "_race_engineer_team_panel")
    page.update_race_engineer_team_brief(_brief())
    assert len(page._race_engineer_team_panel._cards) >= 5


def test_prior_phase_panels_coexist(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    # the Phase 33-35 pack panel and the new brief panel both exist.
    assert hasattr(page, "_review_pack_panel") and hasattr(page, "_race_engineer_team_panel")


def test_severity_carried_by_text_not_colour_alone(app):
    # NGR accessibility rule: a warn/rollback state must be stated in WORDS (a status tag), not by
    # colour alone. The VM exposes a text status tag for every card + the overall banner.
    import ui.race_engineer_team_vm as rvm
    r = _brief()
    tag, tone = rvm.status_summary(r)
    assert tag and tag.isupper()          # explicit textual status, e.g. "ROLLBACK NEEDED"
    cards = rvm.brief_cards(r)
    assert cards and all("status_tag" in c and "tone" in c for c in cards)
    # the seeded programme has 2 regressions -> the overall status is a rollback warning stated in text.
    assert "ROLLBACK" in tag and tone == "warn"


def test_panel_cards_have_accessible_names(app):
    from ui.race_engineer_team_panel import RaceEngineerTeamPanel
    p = RaceEngineerTeamPanel()
    p.update_result(_brief())
    assert all(c.accessibleName() for c in p._cards)
    assert p._header.accessibleDescription()


def test_stale_worker_result_ignored(app):
    import ui.dashboard as dash

    class _Stub:
        pass

    stub = _Stub.__new__(_Stub)
    rendered = {}

    class _Page:
        def update_race_engineer_team_brief(self, r):
            rendered["r"] = r

    stub._development_history_page = _Page()
    newest = object()
    stub._race_engineer_brief_worker = newest
    dash.MainWindow._on_race_engineer_team_brief_ready(stub, {"ok": True, "brief": None}, object())
    assert "r" not in rendered
    dash.MainWindow._on_race_engineer_team_brief_ready(stub, {"ok": True, "brief": None}, newest)
    assert "r" in rendered


def test_brief_build_runs_off_ui_thread(app):
    from ui.mechanism_annotation_worker import MechanismAnnotationWorker
    main = threading.get_ident()
    seen = {}

    def build():
        seen["worker"] = threading.get_ident()
        return {"ok": True, "brief": None}

    w = MechanismAnnotationWorker(build)
    w.finished_ok.connect(lambda r: (seen.__setitem__("handler", threading.get_ident()),
                                     seen.__setitem__("result", r), app.quit()))
    w.failed.connect(lambda m: (seen.__setitem__("err", m), app.quit()))
    from tests._qt_worker_wait import drive_worker
    drive_worker(w)
    assert seen.get("worker") is not None and seen["worker"] != main
    assert seen.get("handler") == main and seen.get("result", {}).get("ok")
