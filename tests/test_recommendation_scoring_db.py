"""Tests for OFR-1 DB methods on SessionDB — migration v9 and scoring round-trip.

Uses SessionDB(':memory:') throughout; never touches the real config.json.

Covers:
  - Migration v9 adds the three scoring columns with correct defaults
  - Full round-trip: insert rec → mark applied → insert lap rows → persist_score
    → columns populated
  - Write-once: second persist_score returns False, values unchanged
  - Layout guard: mismatched layout_id excluded; '' matches '' rows
  - get_previous_session_id ordering
  - has_learning_for_car_track False → True transition
  - get_scored_recs_for_prompt: threshold + limit + verdict filters
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

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
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _insert_rec(
    db: SessionDB,
    *,
    car_id: int = 1,
    track: str = "Spa",
    layout_id: str = "",
    session_id: int = 1,
    rec_text: str = '{"changes":[{"field":"ARB front","from":4,"to":3,"why":"reduce understeer"}]}',
    status: str = "proposed",
    before_metrics: str = "{}",
) -> int:
    """Insert a setup_recommendations row and return its id."""
    with db._lock:
        cur = db._conn.execute(
            """INSERT INTO setup_recommendations
               (ai_interaction_id, session_id, car_id, track, layout_id,
                feature, recommendation_text, status, outcome,
                before_metrics, after_metrics, created_at)
               VALUES (NULL, ?, ?, ?, ?, 'Setup Advice', ?, ?, 'not_verified', ?, '{}', ?)""",
            (session_id, car_id, track, layout_id, rec_text, status, before_metrics, _now()),
        )
        db._conn.commit()
        return cur.lastrowid


def _insert_lap(
    db: SessionDB,
    session_id: int,
    *,
    lap_time_ms: int = 90_000,
    is_pit_lap: int = 0,
    is_out_lap: int = 0,
    compound: str = "RM",
    car_id: int = 1,
    track: str = "Spa",
    lock_up_count: int = 1,
    wheelspin_count: int = 2,
    oversteer_count: int = 0,
    oversteer_throttle_on: int = 0,
    bottoming_count: int = 0,
    brake_consistency_m: float = 5.0,
) -> None:
    with db._lock:
        db._conn.execute(
            """INSERT INTO lap_records
               (session_id, car_id, track, lap_num, lap_time_ms, fuel_used,
                lock_up_count, wheelspin_count, brake_consistency_m,
                max_speed_kmh, avg_throttle_pct, avg_brake_pct,
                compound, is_pit_lap, is_out_lap,
                oversteer_count, oversteer_throttle_on, bottoming_count)
               VALUES (?,?,?,
                (SELECT COALESCE(MAX(lap_num),0)+1 FROM lap_records WHERE session_id=?),
                ?,?,?,?,?,200.0,60.0,20.0,?,?,?,?,?,?)""",
            (session_id, car_id, track, session_id,
             lap_time_ms, 1.8,
             lock_up_count, wheelspin_count, brake_consistency_m,
             compound, is_pit_lap, is_out_lap,
             oversteer_count, oversteer_throttle_on, bottoming_count),
        )
        db._conn.commit()


# ---------------------------------------------------------------------------
# Migration v9 — columns present with correct defaults
# ---------------------------------------------------------------------------

def test_v9_columns_exist(db):
    """Migration v9 must add score_confidence, score_verdict, score_details."""
    cols = {row[1] for row in db._conn.execute(
        "PRAGMA table_info(setup_recommendations)"
    ).fetchall()}
    assert "score_confidence" in cols
    assert "score_verdict" in cols
    assert "score_details" in cols


def test_v9_schema_version(db):
    """Schema version must equal the current schema (DB_VERSION) after opening a
    fresh DB. Historically v10 (driver_feedback setup_id + rating); the fresh DB
    always migrates to the latest (Group 62: v14)."""
    version = db._conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == DB_VERSION


def test_v9_default_score_confidence(db):
    """score_confidence default must be -1.0 (sentinel = unscored)."""
    rec_id = _insert_rec(db)
    row = db._conn.execute(
        "SELECT score_confidence FROM setup_recommendations WHERE id=?", (rec_id,)
    ).fetchone()
    assert row[0] == pytest.approx(-1.0)


def test_v9_default_score_verdict(db):
    """score_verdict default must be '' (empty = unscored)."""
    rec_id = _insert_rec(db)
    row = db._conn.execute(
        "SELECT score_verdict FROM setup_recommendations WHERE id=?", (rec_id,)
    ).fetchone()
    assert row[0] == ""


def test_v9_default_score_details(db):
    """score_details default must be '{}'."""
    rec_id = _insert_rec(db)
    row = db._conn.execute(
        "SELECT score_details FROM setup_recommendations WHERE id=?", (rec_id,)
    ).fetchone()
    assert row[0] == "{}"


# ---------------------------------------------------------------------------
# Full round-trip
# ---------------------------------------------------------------------------

def test_full_round_trip(db):
    """Insert rec → mark applied → insert laps → persist_score → columns populated."""
    sid = db.open_session(car_id=1, track="Spa", session_type="Practice")
    rec_id = _insert_rec(db, car_id=1, track="Spa", session_id=sid, status="applied")

    # Insert 4 clean laps for the "after" session
    after_sid = db.open_session(car_id=1, track="Spa", session_type="Race")
    for ms in [89_000, 88_800, 89_200, 89_100]:
        _insert_lap(db, after_sid, lap_time_ms=ms, lock_up_count=1)

    verdict = "improved"
    confidence = 0.75
    details = {"delta_ms": -500, "before_source": "creation_session"}

    wrote = db.persist_score(rec_id, verdict, confidence, details)
    assert wrote is True

    row = db._conn.execute(
        "SELECT score_verdict, score_confidence, score_details "
        "FROM setup_recommendations WHERE id=?",
        (rec_id,),
    ).fetchone()
    assert row[0] == verdict
    assert row[1] == pytest.approx(confidence)
    stored = json.loads(row[2])
    assert stored["delta_ms"] == -500


def test_persist_score_write_once(db):
    """Second persist_score call returns False and leaves values unchanged."""
    rec_id = _insert_rec(db, status="applied")

    details_1 = {"delta_ms": -400, "before_source": "creation_session"}
    details_2 = {"delta_ms": +200, "before_source": "creation_session"}

    wrote_1 = db.persist_score(rec_id, "improved", 0.8, details_1)
    wrote_2 = db.persist_score(rec_id, "worsened", 0.2, details_2)

    assert wrote_1 is True
    assert wrote_2 is False

    row = db._conn.execute(
        "SELECT score_verdict, score_confidence FROM setup_recommendations WHERE id=?",
        (rec_id,),
    ).fetchone()
    # First write wins
    assert row[0] == "improved"
    assert row[1] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# get_applied_unverified_recs — layout guard
# ---------------------------------------------------------------------------

def test_get_applied_unverified_recs_basic(db):
    """Returns applied rows with empty score_verdict for matching car+track+layout."""
    rec_id = _insert_rec(db, status="applied", layout_id="")
    recs = db.get_applied_unverified_recs(car_id=1, track="Spa", layout_id="")
    ids = [r["id"] for r in recs]
    assert rec_id in ids


def test_get_applied_unverified_recs_excludes_proposed(db):
    """proposed status rows are excluded."""
    _insert_rec(db, status="proposed", layout_id="")
    recs = db.get_applied_unverified_recs(car_id=1, track="Spa", layout_id="")
    assert len(recs) == 0


def test_get_applied_unverified_recs_excludes_already_scored(db):
    """Rows already scored (score_verdict != '') are excluded."""
    rec_id = _insert_rec(db, status="applied", layout_id="")
    db.persist_score(rec_id, "improved", 0.8, {"before_source": "creation_session"})
    recs = db.get_applied_unverified_recs(car_id=1, track="Spa", layout_id="")
    ids = [r["id"] for r in recs]
    assert rec_id not in ids


def test_layout_guard_mismatch_excluded(db):
    """Different layout_id must not match."""
    _insert_rec(db, status="applied", layout_id="spa__full")
    recs = db.get_applied_unverified_recs(car_id=1, track="Spa", layout_id="spa__short")
    assert len(recs) == 0


def test_layout_guard_empty_matches_empty(db):
    """'' layout_id matches '' layout_id rows."""
    _insert_rec(db, status="applied", layout_id="")
    recs = db.get_applied_unverified_recs(car_id=1, track="Spa", layout_id="")
    assert len(recs) == 1


def test_layout_guard_named_matches_named(db):
    """Named layout matches only the same name."""
    _insert_rec(db, status="applied", layout_id="spa__full")
    _insert_rec(db, status="applied", layout_id="")
    recs = db.get_applied_unverified_recs(car_id=1, track="Spa", layout_id="spa__full")
    assert len(recs) == 1
    assert recs[0]["layout_id"] == "spa__full"


# ---------------------------------------------------------------------------
# get_laps_for_scoring
# ---------------------------------------------------------------------------

def test_get_laps_for_scoring_returns_correct_fields(db):
    """get_laps_for_scoring must return the required telemetry fields."""
    sid = db.open_session(car_id=1, track="Spa", session_type="Race")
    _insert_lap(db, sid, lap_time_ms=90_000, lock_up_count=2, wheelspin_count=3)

    laps = db.get_laps_for_scoring(sid)
    assert len(laps) == 1
    lap = laps[0]
    required_fields = {
        "lap_time_ms", "is_pit_lap", "is_out_lap", "compound",
        "lock_up_count", "wheelspin_count", "oversteer_count",
        "oversteer_throttle_on", "bottoming_count", "brake_consistency_m",
    }
    missing = required_fields - set(lap.keys())
    assert not missing, f"Missing fields: {missing}"


def test_get_laps_for_scoring_excludes_zero_time(db):
    """Laps with lap_time_ms=0 are excluded."""
    sid = db.open_session(car_id=1, track="Spa", session_type="Race")
    with db._lock:
        db._conn.execute(
            """INSERT INTO lap_records
               (session_id, car_id, track, lap_num, lap_time_ms, fuel_used,
                lock_up_count, wheelspin_count, brake_consistency_m,
                max_speed_kmh, avg_throttle_pct, avg_brake_pct)
               VALUES (?,1,'Spa',1,0,1.0,0,0,0.0,0.0,0.0,0.0)""",
            (sid,),
        )
        db._conn.commit()
    laps = db.get_laps_for_scoring(sid)
    assert len(laps) == 0


def test_get_laps_for_scoring_includes_pit_and_out(db):
    """get_laps_for_scoring returns pit and out laps — caller filters."""
    sid = db.open_session(car_id=1, track="Spa", session_type="Race")
    _insert_lap(db, sid, lap_time_ms=90_000, is_pit_lap=1)
    _insert_lap(db, sid, lap_time_ms=95_000, is_out_lap=1)
    _insert_lap(db, sid, lap_time_ms=88_000)

    laps = db.get_laps_for_scoring(sid)
    assert len(laps) == 3


def test_get_laps_for_scoring_empty_session(db):
    laps = db.get_laps_for_scoring(session_id=9999)
    assert laps == []


# ---------------------------------------------------------------------------
# get_previous_session_id
# ---------------------------------------------------------------------------

def test_get_previous_session_id_returns_most_recent(db):
    """Returns the highest id < before_session_id for car+track."""
    sid1 = db.open_session(car_id=1, track="Spa", session_type="Race")
    sid2 = db.open_session(car_id=1, track="Spa", session_type="Race")
    sid3 = db.open_session(car_id=1, track="Spa", session_type="Race")

    prev = db.get_previous_session_id(car_id=1, track="Spa", before_session_id=sid3)
    assert prev == sid2


def test_get_previous_session_id_excludes_other_car(db):
    """Different car_id is excluded."""
    db.open_session(car_id=2, track="Spa", session_type="Race")
    sid2 = db.open_session(car_id=1, track="Spa", session_type="Race")

    prev = db.get_previous_session_id(car_id=1, track="Spa", before_session_id=sid2)
    assert prev == 0


def test_get_previous_session_id_excludes_other_track(db):
    """Different track is excluded."""
    db.open_session(car_id=1, track="Monza", session_type="Race")
    sid2 = db.open_session(car_id=1, track="Spa", session_type="Race")

    prev = db.get_previous_session_id(car_id=1, track="Spa", before_session_id=sid2)
    assert prev == 0


def test_get_previous_session_id_no_prior_session(db):
    """Returns 0 when no session exists before the given id."""
    sid = db.open_session(car_id=1, track="Spa", session_type="Race")
    prev = db.get_previous_session_id(car_id=1, track="Spa", before_session_id=sid)
    assert prev == 0


def test_get_previous_session_id_multiple_candidates(db):
    """With multiple prior sessions, returns the most recent (highest id)."""
    sid1 = db.open_session(car_id=1, track="Spa", session_type="Race")
    sid2 = db.open_session(car_id=1, track="Spa", session_type="Race")
    sid3 = db.open_session(car_id=1, track="Spa", session_type="Race")
    sid4 = db.open_session(car_id=1, track="Spa", session_type="Race")

    prev = db.get_previous_session_id(car_id=1, track="Spa", before_session_id=sid4)
    assert prev == sid3


# ---------------------------------------------------------------------------
# has_learning_for_car_track
# ---------------------------------------------------------------------------

def test_has_learning_false_when_no_recs(db):
    assert db.has_learning_for_car_track(car_id=1, track="Spa") is False


def test_has_learning_false_when_only_unscored(db):
    _insert_rec(db, status="applied")  # score_verdict defaults to ''
    assert db.has_learning_for_car_track(car_id=1, track="Spa") is False


def test_has_learning_false_when_only_insufficient_data(db):
    rec_id = _insert_rec(db, status="applied")
    db.persist_score(rec_id, "insufficient_data", 0.0, {})
    assert db.has_learning_for_car_track(car_id=1, track="Spa") is False


def test_has_learning_true_after_scoring(db):
    rec_id = _insert_rec(db, status="applied")
    db.persist_score(rec_id, "improved", 0.75, {"before_source": "creation_session"})
    assert db.has_learning_for_car_track(car_id=1, track="Spa") is True


def test_has_learning_true_for_worsened(db):
    rec_id = _insert_rec(db, status="applied")
    db.persist_score(rec_id, "worsened", 0.6, {})
    assert db.has_learning_for_car_track(car_id=1, track="Spa") is True


# ---------------------------------------------------------------------------
# get_scored_recs_for_prompt
# ---------------------------------------------------------------------------

def test_get_scored_recs_for_prompt_returns_qualifying(db):
    rec_id = _insert_rec(db, status="applied", layout_id="")
    db.persist_score(rec_id, "improved", 0.7, {"before_source": "creation_session"})

    recs = db.get_scored_recs_for_prompt(car_id=1, track="Spa", layout_id="")
    assert len(recs) == 1
    assert recs[0]["score_verdict"] == "improved"


def test_get_scored_recs_for_prompt_excludes_insufficient_data(db):
    rec_id = _insert_rec(db, status="applied", layout_id="")
    db.persist_score(rec_id, "insufficient_data", 0.0, {})

    recs = db.get_scored_recs_for_prompt(car_id=1, track="Spa", layout_id="")
    assert len(recs) == 0


def test_get_scored_recs_for_prompt_excludes_below_threshold(db):
    """score_confidence < 0.5 is excluded."""
    rec_id = _insert_rec(db, status="applied", layout_id="")
    db.persist_score(rec_id, "improved", 0.4, {})

    recs = db.get_scored_recs_for_prompt(car_id=1, track="Spa", layout_id="")
    assert len(recs) == 0


def test_get_scored_recs_for_prompt_at_threshold(db):
    """score_confidence == 0.5 is included (>= threshold)."""
    rec_id = _insert_rec(db, status="applied", layout_id="")
    db.persist_score(rec_id, "improved", 0.5, {})

    recs = db.get_scored_recs_for_prompt(car_id=1, track="Spa", layout_id="")
    assert len(recs) == 1


def test_get_scored_recs_for_prompt_layout_guard(db):
    """Mismatched layout_id is excluded."""
    rec_id = _insert_rec(db, status="applied", layout_id="spa__full")
    db.persist_score(rec_id, "improved", 0.7, {})

    recs = db.get_scored_recs_for_prompt(car_id=1, track="Spa", layout_id="spa__short")
    assert len(recs) == 0


def test_get_scored_recs_for_prompt_limit_5(db):
    """At most 5 rows are returned."""
    for i in range(8):
        rec_id = _insert_rec(db, status="applied", layout_id="")
        db.persist_score(rec_id, "improved", 0.7, {"idx": i})

    recs = db.get_scored_recs_for_prompt(car_id=1, track="Spa", layout_id="")
    assert len(recs) <= 5


def test_get_scored_recs_for_prompt_newest_first(db):
    """Results should be newest (highest id) first."""
    ids = []
    for i in range(3):
        rec_id = _insert_rec(db, status="applied", layout_id="")
        db.persist_score(rec_id, "improved", 0.8, {})
        ids.append(rec_id)

    recs = db.get_scored_recs_for_prompt(car_id=1, track="Spa", layout_id="")
    returned_ids = [r["id"] for r in recs]
    assert returned_ids == sorted(returned_ids, reverse=True)


def test_get_scored_recs_for_prompt_excludes_empty_verdict(db):
    """Rows with score_verdict='' (unscored) are excluded."""
    _insert_rec(db, status="applied", layout_id="")
    recs = db.get_scored_recs_for_prompt(car_id=1, track="Spa", layout_id="")
    assert len(recs) == 0
