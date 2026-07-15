"""Tests for Group 18B — Recommendation persistence pipeline (deterministic).

The generative-AI pieces (strategy._rec_parser.parse_recommendations_from_response,
strategy._ai_client.AILogEntry / call_api, the practice-prompt builders, and the
PracticeAnalysis / CarSetupRecommendation dataclasses) were removed with the AI
purge, so the tests that exercised them are gone. What survives:
  - SessionDB schema v5: setup_recommendations table + session_id on ai_interactions
  - SessionDB.insert_setup_recommendations()
  - SessionDB.get_recommendations_for_context()
  - SessionDB.log_ai_interaction() with session_id field
  - DrivingAdvisor session_id_getter wiring + _get_previous_ai_context (DB-backed)
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    d = SessionDB(":memory:")
    yield d
    d.close()


# ---------------------------------------------------------------------------
# TASK 1 — SessionDB schema v5
# ---------------------------------------------------------------------------

def test_setup_recommendations_table_exists(db):
    """setup_recommendations table should be created on first open."""
    rows = db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='setup_recommendations'"
    ).fetchall()
    assert rows, "setup_recommendations table must exist"


def test_ai_interactions_has_session_id_column(db):
    """ai_interactions must have a session_id column after v5 migration."""
    cols = [row[1] for row in db._conn.execute("PRAGMA table_info(ai_interactions)").fetchall()]
    assert "session_id" in cols


def test_insert_setup_recommendations_basic(db):
    """insert_setup_recommendations persists rows correctly."""
    recs = [
        {
            "ai_interaction_id": None,
            "session_id": 7,
            "car_id": 42,
            "track": "Monza",
            "layout_id": "monza__full",
            "feature": "Driver Coaching",
            "recommendation_text": "Brake later at T1.",
            "created_at": "2026-06-26T00:00:00",
        }
    ]
    db.insert_setup_recommendations(recs)
    rows = db._conn.execute("SELECT * FROM setup_recommendations").fetchall()
    assert len(rows) == 1
    assert dict(rows[0])["recommendation_text"] == "Brake later at T1."
    assert dict(rows[0])["car_id"] == 42


def test_insert_setup_recommendations_empty(db):
    """insert_setup_recommendations with empty list does nothing (no error)."""
    db.insert_setup_recommendations([])
    count = db._conn.execute("SELECT COUNT(*) FROM setup_recommendations").fetchone()[0]
    assert count == 0


def test_get_recommendations_for_context_returns_joined(db):
    """get_recommendations_for_context joins rows with separator."""
    for i, txt in enumerate(["Rec A", "Rec B"]):
        db.insert_setup_recommendations([{
            "ai_interaction_id": None,
            "session_id": 0,
            "car_id": 1,
            "track": "Suzuka",
            "layout_id": "",
            "feature": "Setup Advice",
            "recommendation_text": txt,
            "created_at": "2026-06-26T00:00:00",
        }])
    result = db.get_recommendations_for_context(car_id=1, track="Suzuka", limit=2)
    assert "Rec A" in result
    assert "Rec B" in result
    assert "---" in result


def test_get_recommendations_for_context_empty(db):
    """Returns empty string when no rows match."""
    result = db.get_recommendations_for_context(car_id=99, track="NoTrack")
    assert result == ""


def test_get_recommendations_for_context_limit(db):
    """limit parameter restricts returned rows."""
    for i in range(5):
        db.insert_setup_recommendations([{
            "ai_interaction_id": None,
            "session_id": 0,
            "car_id": 5,
            "track": "Fuji",
            "layout_id": "",
            "feature": "Setup Advice",
            "recommendation_text": f"Rec {i}",
            "created_at": "2026-06-26T00:00:00",
        }])
    result = db.get_recommendations_for_context(car_id=5, track="Fuji", limit=2)
    # Two recs separated by one separator
    assert result.count("---") == 1


def test_log_ai_interaction_with_session_id(db):
    """log_ai_interaction persists session_id correctly."""
    entry = {
        "timestamp": "2026-06-26T00:00:00",
        "feature": "Driver Coaching",
        "model": "test",
        "prompt": "p",
        "structured_payload": "{}",
        "response": "r",
        "success": True,
        "duration_ms": 100,
        "prompt_tokens": 10,
        "response_tokens": 20,
        "estimated_cost": 0.001,
        "error_msg": "",
        "validation_warnings": [],
        "car_id": 3,
        "track": "Nurburgring",
        "session_id": 99,
    }
    row_id = db.log_ai_interaction(entry)
    row = db._conn.execute(
        "SELECT session_id FROM ai_interactions WHERE id=?", (row_id,)
    ).fetchone()
    assert row[0] == 99


def test_log_ai_interaction_default_session_id(db):
    """log_ai_interaction defaults session_id to 0 when not provided."""
    entry = {
        "timestamp": "2026-06-26T00:00:00",
        "feature": "Setup Advice",
        "model": "test",
        "prompt": "p",
        "structured_payload": "{}",
        "response": "r",
        "success": True,
        "duration_ms": 50,
        "prompt_tokens": 5,
        "response_tokens": 10,
        "estimated_cost": 0.0,
        "error_msg": "",
        "validation_warnings": [],
        "car_id": 0,
        "track": "",
    }
    row_id = db.log_ai_interaction(entry)
    row = db._conn.execute(
        "SELECT session_id FROM ai_interactions WHERE id=?", (row_id,)
    ).fetchone()
    assert row[0] == 0


# ---------------------------------------------------------------------------
# TASK 5 — DrivingAdvisor session_id_getter
# ---------------------------------------------------------------------------

def test_driving_advisor_default_getter():
    """DrivingAdvisor with no getter defaults to returning 0."""
    from unittest.mock import MagicMock
    from strategy.driving_advisor import DrivingAdvisor
    advisor = DrivingAdvisor(
        recorder=MagicMock(),
        tracker=MagicMock(),
        config={},
    )
    assert advisor._session_id_getter() == 0


def test_driving_advisor_custom_getter():
    """DrivingAdvisor stores and calls a custom session_id_getter."""
    from unittest.mock import MagicMock
    from strategy.driving_advisor import DrivingAdvisor
    getter = lambda: 42
    advisor = DrivingAdvisor(
        recorder=MagicMock(),
        tracker=MagicMock(),
        config={},
        session_id_getter=getter,
    )
    assert advisor._session_id_getter() == 42


def test_driving_advisor_non_callable_getter():
    """Non-callable session_id_getter is replaced by a zero-returning lambda."""
    from unittest.mock import MagicMock
    from strategy.driving_advisor import DrivingAdvisor
    advisor = DrivingAdvisor(
        recorder=MagicMock(),
        tracker=MagicMock(),
        config={},
        session_id_getter="not_callable",
    )
    assert advisor._session_id_getter() == 0


# ---------------------------------------------------------------------------
# Additional tests — gaps identified by test-verifier
# ---------------------------------------------------------------------------

# AC1 — schema version must be 9 after migration (v9 adds OFR-1 scoring columns)
def test_schema_version_is_current(db):
    """PRAGMA user_version must equal the current schema (DB_VERSION) after
    opening a fresh DB.

    History: v10 added driver_feedback setup_id + rating; v11 added Rule-First
    Setup Brain columns; v12 (Group 46) added learning_outcomes table; v13
    (Group 47) added the 5 additive outcome-verification columns; v14 (Group 62)
    added the additive events.abs column.
    """
    version = db._conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == DB_VERSION, f"Expected schema version {DB_VERSION}, got {version}"


# AC3 — setup_recommendations table has correct columns
def test_setup_recommendations_schema(db):
    """setup_recommendations must have the expected column set."""
    cols = {row[1] for row in db._conn.execute(
        "PRAGMA table_info(setup_recommendations)"
    ).fetchall()}
    required = {
        "id", "ai_interaction_id", "session_id", "car_id", "track",
        "layout_id", "feature", "recommendation_text", "status",
        "outcome", "outcome_session_id", "created_at",
    }
    missing = required - cols
    assert not missing, f"setup_recommendations missing columns: {missing}"


# AC5 — get_recommendations_for_context returns newest-first
def test_get_recommendations_newest_first(db):
    """Rows must be returned newest (highest id) first."""
    for txt in ["Older rec", "Newer rec"]:
        db.insert_setup_recommendations([{
            "ai_interaction_id": None,
            "session_id": 0,
            "car_id": 10,
            "track": "Brands Hatch",
            "layout_id": "",
            "feature": "Setup Advice",
            "recommendation_text": txt,
            "created_at": "2026-06-26T00:00:00",
        }])
    result = db.get_recommendations_for_context(car_id=10, track="Brands Hatch", limit=2)
    # Newest inserted (higher id) should appear first in the joined string
    assert result.index("Newer rec") < result.index("Older rec"), (
        "get_recommendations_for_context must return newest entries first"
    )


# AC5 — default limit is 2
def test_get_recommendations_default_limit(db):
    """Default limit=2 returns at most 2 recs."""
    for i in range(4):
        db.insert_setup_recommendations([{
            "ai_interaction_id": None,
            "session_id": 0,
            "car_id": 20,
            "track": "Catalunya",
            "layout_id": "",
            "feature": "Driver Coaching",
            "recommendation_text": f"Tip {i}",
            "created_at": "2026-06-26T00:00:00",
        }])
    result = db.get_recommendations_for_context(car_id=20, track="Catalunya")
    # At most 2 separators means at most 2 recs
    assert result.count("---") <= 1, (
        "Default limit=2 must return at most 2 recommendations"
    )


# AC7 — DrivingAdvisor._get_previous_ai_context returns joined recs from DB
def test_driving_advisor_get_previous_ai_context(db):
    """_get_previous_ai_context must query get_recommendations_for_context and prefix the result."""
    from unittest.mock import MagicMock
    from strategy.driving_advisor import DrivingAdvisor

    db.insert_setup_recommendations([{
        "ai_interaction_id": None,
        "session_id": 0,
        "car_id": 7,
        "track": "Interlagos",
        "layout_id": "",
        "feature": "Driver Coaching",
        "recommendation_text": "Trail-brake later at T1.",
        "created_at": "2026-06-26T00:00:00",
    }])

    advisor = DrivingAdvisor(
        recorder=MagicMock(),
        tracker=MagicMock(),
        config={"strategy": {"track": "Interlagos"}},
        db=db,
        car_id_ref=[7],
    )
    ctx = advisor._get_previous_ai_context("Driver Coaching")
    assert "Trail-brake later at T1." in ctx
    assert "Previous AI Recommendations" in ctx


# AC7 — _get_previous_ai_context returns empty string when no DB
def test_driving_advisor_get_previous_ai_context_no_db():
    """_get_previous_ai_context must return '' when no DB is wired."""
    from unittest.mock import MagicMock
    from strategy.driving_advisor import DrivingAdvisor
    advisor = DrivingAdvisor(
        recorder=MagicMock(),
        tracker=MagicMock(),
        config={"strategy": {"track": "Interlagos"}},
    )
    ctx = advisor._get_previous_ai_context("Driver Coaching")
    assert ctx == ""
