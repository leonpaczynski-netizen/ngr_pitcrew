"""UAT remediation (post-merge, real use) — Command Centre routing, car authority, layout.

DEF-073-018: the Command Centre "Primary Action" for a cumulative-evidence objective ("Build
  setup_base evidence") hardcoded target_surface="practice", so "Open" went to Practice Review
  instead of the Setup Builder. It now routes by the objective's evidence DOMAIN.
DEF-073-019: activating an event overwrote the cycle's SAVED car with a drifted strategy car, so the
  Setup Builder showed the wrong car. Activation now restores the cycle's car into the strategy
  context; the Garage "pick a car" path still wins.
DEF-073-020: the Command Centre panel squished / clipped on a non-maximised window (no scroll region).
"""
from __future__ import annotations

import os

import pytest

from data.session_db import SessionDB


# --------------------------------------------------------------------------- #
# DEF-073-018 — objective routes to the surface that performs it
# --------------------------------------------------------------------------- #
def _cycle(db, cid="c1", **kw):
    base = dict(cycle_id=cid, event_name="Cup R3", track="Fuji", car="P",
                official_race_date="2026-06-21", format_profile_id="multiweek", explicit_state="active")
    base.update(kw)
    db.upsert_preparation_cycle(base)


def test_setup_base_objective_routes_to_setup_builder():
    db = SessionDB(":memory:")
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "base", "cycle_id": "c1",
                                    "activity_type": "baseline_practice", "order_index": 0, "state": "planned"})
    v = db.build_event_command_centre_view(selected_cycle_id="c1", now_date="2026-06-11")
    na = v["next_action"]
    assert na["category"] == "next_activity"
    assert na["headline"].startswith("Build setup_base")     # weakest domain, no evidence
    assert na["target_surface"] == "setup"                   # NOT "practice" (the DEF-073-018 bug)
    db.close()


def test_domain_surface_map_covers_setup_and_pace():
    from strategy.event_command_centre import _OBJECTIVE_DOMAIN_TO_SURFACE as m
    assert m["setup_base"] == "setup"
    assert m["setup_race"] == "setup"
    assert m["setup_qualifying"] == "setup"
    assert m["race_pace"] == "practice"       # pace evidence is gathered by driving
    assert m["strategy"] == "strategy"


def test_objective_carries_its_domain():
    # to_objective must tag the objective with the domain so the router can map it
    from strategy.preparation_evidence import build_cumulative_evidence, to_objective
    obj = to_objective(build_cumulative_evidence([]))   # no samples → weakest = setup_base
    assert obj.domain == "setup_base"


# --------------------------------------------------------------------------- #
# DEF-073-019 — car authority on activation vs Garage pick
# --------------------------------------------------------------------------- #
class _FakeDB:
    def __init__(self, existing=None, event=None):
        self._existing = existing
        self._event = event or {}
        self.upserted = None

    def get_event(self, name):
        return dict(self._event)

    def get_preparation_cycle(self, cid):
        return dict(self._existing) if self._existing else None

    def upsert_preparation_cycle(self, cycle):
        self.upserted = cycle


def _mk(config, existing=None, event=None):
    from ui.event_planner_ui import EventPlannerMixin

    class _Stub:
        pass

    s = _Stub()
    s._db = _FakeDB(existing, event)
    s._config = config
    s._active_event = lambda: {}
    return s, EventPlannerMixin._ensure_active_preparation_cycle.__get__(s)


def test_activation_restores_saved_cycle_car_over_drifted_strategy_car():
    # cycle saved Cayman; strategy car drifted to RSR17 → activation must keep Cayman and restore it
    config = {"strategy": {"car": "Porsche 911 RSR '17"}}
    existing = {"cycle_id": "cycle-gr-enduro-rd2", "car": "Porsche Cayman GT4", "explicit_state": ""}
    s, fn = _mk(config, existing=existing)
    fn("GR Enduro Rd2")                                    # activation (prefer_strategy_car=False)
    assert s._db.upserted["car"] == "Porsche Cayman GT4"   # cycle car preserved, not clobbered
    assert config["strategy"]["car"] == "Porsche Cayman GT4"  # and restored into the strategy context


def test_garage_pick_lets_the_new_strategy_car_win():
    # user picked Cayman in the Garage; cycle still has the old RSR17 → the new pick wins
    config = {"strategy": {"car": "Porsche Cayman GT4"}}
    existing = {"cycle_id": "cycle-gr-enduro-rd2", "car": "Porsche 911 RSR '17", "explicit_state": ""}
    s, fn = _mk(config, existing=existing)
    fn("GR Enduro Rd2", prefer_strategy_car=True)
    assert s._db.upserted["car"] == "Porsche Cayman GT4"


def test_brand_new_cycle_uses_strategy_car():
    config = {"strategy": {"car": "Porsche Cayman GT4"}}
    s, fn = _mk(config, existing=None, event={})           # no existing cycle
    fn("GR Enduro Rd2")
    assert s._db.upserted["car"] == "Porsche Cayman GT4"


# --------------------------------------------------------------------------- #
# DEF-073-020 — Command Centre panel scrolls (no squish/clip)
# --------------------------------------------------------------------------- #
def test_command_centre_panel_wraps_body_in_a_scroll_area():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication, QScrollArea
    except Exception:
        pytest.skip("PyQt6 not available")
    QApplication.instance() or QApplication([])
    from ui.event_command_centre_panel import EventCommandCentrePanel
    p = EventCommandCentrePanel()
    assert isinstance(p._body_scroll, QScrollArea)
    assert p._body_scroll.widgetResizable() is True
    assert p._body_scroll.widget() is p._body
