"""Group 50 — Race Strategy Brain Phase 4: evidence source display tests.

Covers the evidence-source projection in ui/race_strategy_vm.py:
  • SessionDB measured evidence shown as measured
  • event settings shown as event
  • derived tyre-degradation proxy labelled derived
  • default/assumption shown honestly; missing shown as missing
  • false-certainty wording absent

All tests are pure/offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
from strategy.race_strategy_pipeline import recommend_strategy_from_session  # noqa: E402
from ui.race_strategy_vm import (  # noqa: E402
    build_race_plan_view_model,
    format_evidence_sources,
    render_race_plan_html,
)


def _seed(db, *, n=12, fuel=4.0):
    sid = db.open_session(car_id=911, track="Fuji Speedway", session_type="Practice", car_name="RSR")
    remaining = 100.0
    for i in range(n):
        db.write_lap(session_id=sid, lap_num=i + 1, lap_time_ms=100000 + i * 80,
                     fuel_used=fuel, stats=None, compound="RM",
                     fuel_start=remaining, fuel_end=remaining - fuel)
        remaining -= fuel
    return sid


def _vm(db, sid, **over):
    kw = dict(
        car_id=911, track="Fuji Speedway", race_duration_minutes=50.0,
        fuel_multiplier=3.0, tyre_multiplier=8.0, refuel_rate_lps=1.0,
        pit_loss_seconds=22.0, available_compounds=("RM", "RH"),
    )
    kw.update(over)
    return build_race_plan_view_model(recommend_strategy_from_session(db, session_id=sid, **kw))


@pytest.fixture()
def db():
    yield SessionDB(":memory:")


class TestCategoryClassification:
    def test_measured_event_derived_missing(self):
        summary = {"fields": {
            "race_pace": "SessionDB measured (7 clean laps)",
            "fuel_use": "SessionDB measured (5 laps)",
            "tyre_degradation": "SessionDB derived from lap-time drift (6 increments)",
            "compound_pace": "missing",
            "refuel_rate": "event setting",
            "pit_loss": "default/missing",
            "weather": "assumed",
        }}
        rows = {r["label"]: r["category"] for r in format_evidence_sources(summary)}
        assert rows["Race pace"] == "measured"
        assert rows["Tyre degradation"] == "derived"
        assert rows["Compound pace"] == "missing"
        assert rows["Refuel rate"] == "event"
        assert rows["Pit loss"] == "missing"
        assert rows["Weather"] == "default"

    def test_manual_category(self):
        rows = {r["label"]: r["category"]
                for r in format_evidence_sources({"fields": {"pit_loss": "manual input"}})}
        assert rows["Pit loss"] == "manual"

    def test_garbage_safe(self):
        assert format_evidence_sources({}) == []
        assert format_evidence_sources({"fields": None}) == []


class TestDisplay:
    def test_measured_and_derived_present_in_vm(self, db):
        vm = _vm(db, _seed(db))
        cats = {r["label"]: r["category"] for r in vm.evidence_source_rows}
        assert cats["Race pace"] == "measured"
        assert cats["Fuel use"] == "measured"
        assert cats["Tyre degradation"] == "derived"

    def test_event_setting_present(self, db):
        vm = _vm(db, _seed(db))
        cats = {r["label"]: r["category"] for r in vm.evidence_source_rows}
        assert cats["Refuel rate"] == "event"

    def test_missing_shown_when_pit_loss_absent(self, db):
        vm = _vm(db, _seed(db), pit_loss_seconds=0.0)
        cats = {r["label"]: r["category"] for r in vm.evidence_source_rows}
        assert cats["Pit loss"] == "missing"
        # and the missing evidence list surfaces it too
        assert any("pit" in m.lower() for m in vm.missing_evidence_rows)

    def test_html_shows_evidence_sources(self, db):
        vm = _vm(db, _seed(db))
        html = render_race_plan_html(vm)
        assert "Evidence sources" in html
        assert "SessionDB measured" in html
        assert "derived" in html.lower()

    def test_no_false_certainty(self, db):
        vm = _vm(db, _seed(db))
        html = render_race_plan_html(vm).lower()
        for banned in ("guaranteed", "definitely the best", "perfect strategy",
                       "the winning strategy"):
            assert banned not in html


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
