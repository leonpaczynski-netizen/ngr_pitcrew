"""UAT remediation — DEF-073-003 (+012/015): Development History split into purpose-specific sub-tabs.

The one ~30-panel catch-all page is now a QTabWidget of purpose-specific sub-tabs; every panel attribute is
preserved (so the off-thread refresh methods are unchanged), and Command Centre departments can land on a
distinct sub-tab.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 not available")
    return QApplication.instance() or QApplication([])


def _page(qapp):
    from ui.development_history_page import DevelopmentHistoryPage
    return DevelopmentHistoryPage()


def test_page_is_split_into_purpose_specific_subtabs(qapp):
    p = _page(qapp)
    names = [p._subtabs.tabText(i) for i in range(p._subtabs.count())]
    assert p._subtabs.count() >= 5              # no longer one catch-all scroll
    for expected in ("Readiness & Assurance", "Certification & UAT", "Overview & Records"):
        assert expected in names


def test_all_panels_preserved_for_refresh(qapp):
    p = _page(qapp)
    # the refresh methods reference these attributes — they must survive the restructure
    for a in ("_readiness_panel", "_assurance_panel", "_priority_panel", "_review_pack_panel",
              "_race_engineer_team_panel", "_closed_loop_panel", "_assisted_runtime_panel",
              "_event_preparation_panel", "_race_weekend_panel", "_certification_panel",
              "_uat_runtime_panel", "_bench_uat_panel", "_manual_uat_panel", "_context_panel",
              "_mechanism_panel", "_season_panel", "_knowledge_graph_panel", "_scorecard_grid",
              "_timeline", "_experiments", "_knowledge_panel"):
        assert hasattr(p, a), a


def test_refresh_methods_still_work(qapp):
    p = _page(qapp)
    p.update_result({"ok": True, "record_count": 0})   # must not raise
    p.update_uat_runtime(None)
    p.update_certification(None)


def test_select_subtab_routes_to_distinct_destinations(qapp):
    p = _page(qapp)
    assert p.select_subtab("Certification & UAT") is True
    assert p._subtabs.tabText(p._subtabs.currentIndex()) == "Certification & UAT"
    assert p.select_subtab("Overview & Records") is True
    assert p._subtabs.tabText(p._subtabs.currentIndex()) == "Overview & Records"
    assert p.select_subtab("Nonexistent") is False


def test_briefing_and_debrief_route_to_different_subtabs():
    # source-level: the department → sub-tab map gives Briefing and Debrief DISTINCT homes
    from ui.dashboard import MainWindow
    m = MainWindow._CC_SURFACE_SUBTABS
    assert m["briefing"] != m["debrief"]
