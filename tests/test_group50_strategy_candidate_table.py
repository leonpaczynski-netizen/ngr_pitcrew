"""Group 50 — Race Strategy Brain Phase 4: candidate comparison table tests.

Covers the candidate-comparison rows in ui/race_strategy_vm.py:
  • one-stop and two-stop rows shown; total time, gap, pit+refuel, deg cost, risk,
    confidence, status columns present
  • illegal candidates are not shown as recommended (excluded from scored rows)

All tests are pure/offline (SQLite `:memory:`).
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
    candidate_table_rows,
    CANDIDATE_TABLE_COLUMNS,
)


def _seed(db, *, fuel=4.0, n=12):
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
        rear_traction_fragile=True,
    )
    kw.update(over)
    return build_race_plan_view_model(recommend_strategy_from_session(db, session_id=sid, **kw))


@pytest.fixture()
def db():
    yield SessionDB(":memory:")


class TestTable:
    def test_columns_are_stable(self):
        assert CANDIDATE_TABLE_COLUMNS[0] == "Strategy"
        assert "Total Time" in CANDIDATE_TABLE_COLUMNS
        assert "Gap to Best" in CANDIDATE_TABLE_COLUMNS
        assert "Confidence" in CANDIDATE_TABLE_COLUMNS
        assert "Status" in CANDIDATE_TABLE_COLUMNS

    def test_one_and_two_stop_rows_shown(self, db):
        vm = _vm(db, _seed(db))
        ids = {r["candidate_id"] for r in vm.candidate_comparison_rows}
        assert "1stop" in ids
        assert "2stop" in ids

    def test_row_has_all_required_fields(self, db):
        vm = _vm(db, _seed(db))
        r = next(r for r in vm.candidate_comparison_rows if r["candidate_id"] == "1stop")
        for key in ("strategy", "pit_stops", "compounds", "total_time", "gap_to_best",
                    "pit_refuel_time", "deg_cost", "fuel_save_cost", "risk",
                    "confidence", "status"):
            assert key in r

    def test_total_time_and_gap_shown(self, db):
        vm = _vm(db, _seed(db))
        by_id = {r["candidate_id"]: r for r in vm.candidate_comparison_rows}
        assert by_id["1stop"]["total_time"] != "—"
        assert by_id["1stop"]["gap_to_best"] == "best"
        assert by_id["2stop"]["gap_to_best"].startswith("+")

    def test_pit_refuel_and_deg_shown(self, db):
        vm = _vm(db, _seed(db))
        r = next(r for r in vm.candidate_comparison_rows if r["candidate_id"] == "2stop")
        assert "refuel" in r["pit_refuel_time"]
        assert r["deg_cost"].endswith("s")

    def test_risk_shown_on_push(self, db):
        vm = _vm(db, _seed(db))
        push = next((r for r in vm.candidate_comparison_rows if r["candidate_id"] == "2stop_push"), None)
        assert push is not None
        assert "rear" in push["risk"].lower()

    def test_confidence_shown(self, db):
        vm = _vm(db, _seed(db))
        assert all(r["confidence"] for r in vm.candidate_comparison_rows)

    def test_recommended_marked(self, db):
        vm = _vm(db, _seed(db))
        recs = [r for r in vm.candidate_comparison_rows if r["status"] == "Recommended"]
        assert len(recs) == 1

    def test_illegal_not_shown_as_recommended(self, db):
        # Heavy fuel makes no-stop illegal → it must not appear in the scored rows.
        vm = _vm(db, _seed(db, fuel=6.0))
        ids = {r["candidate_id"] for r in vm.candidate_comparison_rows}
        assert "nostop" not in ids
        # And the recommended row is a legal plan.
        rec = next(r for r in vm.candidate_comparison_rows if r["status"] == "Recommended")
        assert rec["candidate_id"] != "nostop"

    def test_table_rows_match_column_count(self, db):
        vm = _vm(db, _seed(db))
        rows = candidate_table_rows(vm)
        assert rows
        assert all(len(r) == len(CANDIDATE_TABLE_COLUMNS) for r in rows)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
