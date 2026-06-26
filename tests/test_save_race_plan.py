"""Tests for the Save Race Plan feature (DB layer).

All tests use an in-memory SQLite database via SessionDB(":memory:").
No Qt is required.
"""
from __future__ import annotations

import json
import pytest

from data.session_db import SessionDB


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    """Fresh in-memory SessionDB for each test."""
    instance = SessionDB(":memory:")
    yield instance
    instance.close()


def _make_plan(db: SessionDB, event_id: int = 1, car_id: int = 10,
               plan_name: str = "Test Plan", stints_json: str = "[]",
               driver_notes: str = "") -> int:
    return db.save_race_plan(
        event_id=event_id,
        car_id=car_id,
        setup_id=None,
        plan_name=plan_name,
        stints_json=stints_json,
        strategy_rank=1,
        strategy_name="Aggressive",
        estimated_time_s=3600.0,
        ai_summary="Good plan",
        ai_risks="Tyre wear",
        ai_positives="Fast",
        ai_negatives="Risky",
        driver_notes=driver_notes,
        setup_name=None,
    )


# ---------------------------------------------------------------------------
# 1. Round-trip save and retrieve
# ---------------------------------------------------------------------------

def test_save_and_retrieve_plan(db):
    stints = [{"laps": 10, "compound": "Hard", "ref_lap_ms": 95000,
                "pace_threshold_ms": 3000, "pit_lap": 10,
                "target_lap_ms": 95000, "fuel_target_l": 30.0}]
    stints_json = json.dumps(stints)
    plan_id = _make_plan(db, stints_json=stints_json, plan_name="Round Trip")

    assert plan_id > 0
    plans = db.get_race_plans(event_id=1, car_id=10)
    assert len(plans) == 1
    plan = plans[0]
    assert plan["plan_name"] == "Round Trip"
    assert plan["event_id"] == 1
    assert plan["car_id"] == 10
    assert plan["strategy_rank"] == 1
    assert plan["estimated_time_s"] == pytest.approx(3600.0)
    assert plan["driver_notes"] == ""
    retrieved_stints = json.loads(plan["stints_json"])
    assert retrieved_stints[0]["compound"] == "Hard"
    assert retrieved_stints[0]["pit_lap"] == 10


# ---------------------------------------------------------------------------
# 2. get_latest_race_plan returns the newest when two exist
# ---------------------------------------------------------------------------

def test_get_latest_returns_newest(db):
    _make_plan(db, plan_name="Older Plan")
    _make_plan(db, plan_name="Newer Plan")

    latest = db.get_latest_race_plan(event_id=1, car_id=10)
    assert latest is not None
    assert latest["plan_name"] == "Newer Plan"


# ---------------------------------------------------------------------------
# 3. Plans are filtered by event+car pair
# ---------------------------------------------------------------------------

def test_get_plans_filters_by_event_car(db):
    _make_plan(db, event_id=1, car_id=10, plan_name="Event1 Car10")
    _make_plan(db, event_id=2, car_id=10, plan_name="Event2 Car10")
    _make_plan(db, event_id=1, car_id=20, plan_name="Event1 Car20")

    plans_e1_c10 = db.get_race_plans(event_id=1, car_id=10)
    assert len(plans_e1_c10) == 1
    assert plans_e1_c10[0]["plan_name"] == "Event1 Car10"

    plans_e2_c10 = db.get_race_plans(event_id=2, car_id=10)
    assert len(plans_e2_c10) == 1
    assert plans_e2_c10[0]["plan_name"] == "Event2 Car10"

    plans_e1_c20 = db.get_race_plans(event_id=1, car_id=20)
    assert len(plans_e1_c20) == 1
    assert plans_e1_c20[0]["plan_name"] == "Event1 Car20"


# ---------------------------------------------------------------------------
# 4. No plan returns None
# ---------------------------------------------------------------------------

def test_no_plan_returns_none(db):
    result = db.get_latest_race_plan(event_id=99, car_id=99)
    assert result is None


# ---------------------------------------------------------------------------
# 5. Cumulative pit_lap values in stints_json
# ---------------------------------------------------------------------------

def test_pit_lap_computation():
    """Verify cumulative pit_lap logic: only last stint has None."""
    stints_raw = [
        {"laps": 10, "compound": "Hard",   "ref_lap_ms": 95000, "pace_threshold_ms": 3000},
        {"laps": 12, "compound": "Medium", "ref_lap_ms": 94000, "pace_threshold_ms": 3000},
        {"laps": 8,  "compound": "Soft",   "ref_lap_ms": 93000, "pace_threshold_ms": 3000},
    ]
    total_rows = len(stints_raw)
    cumulative = 0
    enriched = []
    for i, d in enumerate(stints_raw):
        cumulative += d["laps"]
        is_last = (i == total_rows - 1)
        enriched.append({
            **d,
            "pit_lap": None if is_last else cumulative,
            "target_lap_ms": d["ref_lap_ms"],
            "fuel_target_l": round(d["laps"] * 3.0, 3),
        })

    assert enriched[0]["pit_lap"] == 10
    assert enriched[1]["pit_lap"] == 22
    assert enriched[2]["pit_lap"] is None


# ---------------------------------------------------------------------------
# 6. fuel_target_l = laps × fuel_burn
# ---------------------------------------------------------------------------

def test_fuel_target_per_stint(db):
    fuel_burn = 3.5
    stints = [
        {"laps": 10, "compound": "Hard", "ref_lap_ms": 95000,
         "pace_threshold_ms": 3000, "pit_lap": 10,
         "target_lap_ms": 95000, "fuel_target_l": round(10 * fuel_burn, 3)},
        {"laps": 15, "compound": "Medium", "ref_lap_ms": 94000,
         "pace_threshold_ms": 3000, "pit_lap": None,
         "target_lap_ms": 94000, "fuel_target_l": round(15 * fuel_burn, 3)},
    ]
    plan_id = _make_plan(db, stints_json=json.dumps(stints))
    plan = db.get_latest_race_plan(event_id=1, car_id=10)
    retrieved = json.loads(plan["stints_json"])
    assert retrieved[0]["fuel_target_l"] == pytest.approx(10 * fuel_burn, abs=1e-3)
    assert retrieved[1]["fuel_target_l"] == pytest.approx(15 * fuel_burn, abs=1e-3)


# ---------------------------------------------------------------------------
# 7. Empty driver notes stored as '' not None
# ---------------------------------------------------------------------------

def test_driver_notes_empty_string_when_blank(db):
    _make_plan(db, driver_notes="")
    plan = db.get_latest_race_plan(event_id=1, car_id=10)
    assert plan is not None
    assert plan["driver_notes"] == ""
    assert plan["driver_notes"] is not None
