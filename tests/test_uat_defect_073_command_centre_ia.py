"""UAT remediation — Command Centre department information-architecture (DEF-073-014/015/016).

Setup Development is ordered before Practice Programme; Telemetry is not an event department; Driver Coaching
routes to a DISTINCT destination (Practice Review) rather than the same Development History catch-all as
Event Briefing.
"""
from __future__ import annotations

from strategy.event_command_centre import QUICK_ACTION_SURFACES


def _surfaces():
    return [s for (_label, s) in QUICK_ACTION_SURFACES]


def test_setup_before_practice():
    surfaces = _surfaces()
    assert surfaces.index("setup") < surfaces.index("practice")


def test_telemetry_is_not_a_department():
    assert "telemetry" not in _surfaces()


def test_coaching_routes_distinctly_from_briefing():
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent.joinpath("ui", "dashboard.py").read_text(encoding="utf-8")
    # extract the _CC_SURFACE_TABS mapping block and confirm coaching != briefing destination
    assert '"coaching": "practice_review"' in src
    assert '"briefing": "development_history"' in src


def test_departments_still_present_and_unique():
    surfaces = _surfaces()
    assert len(surfaces) == len(set(surfaces))            # no duplicate departments
    for required in ("briefing", "garage", "setup", "practice", "strategy", "qualifying", "live",
                     "debrief", "development_history"):
        assert required in surfaces
