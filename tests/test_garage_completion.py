"""Tests for Garage tab completion feature — SessionDb methods only, no Qt."""
from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.session_db import SessionDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> SessionDB:
    return SessionDB(":memory:")


def _insert_rec(db: SessionDb, car_id: int, track: str, text: str = "Some advice") -> None:
    db._conn.execute(
        """INSERT INTO setup_recommendations
           (ai_interaction_id, session_id, car_id, track, layout_id,
            feature, recommendation_text, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (None, 0, car_id, track, "", "suspension", text, time.strftime("%Y-%m-%dT%H:%M:%S")),
    )
    db._conn.commit()


# ---------------------------------------------------------------------------
# Tests for get_tracks_for_car_recommendations
# ---------------------------------------------------------------------------

def test_get_tracks_returns_distinct_sorted():
    db = _make_db()
    # 4 recs across 3 tracks (one duplicated)
    _insert_rec(db, car_id=1, track="Suzuka")
    _insert_rec(db, car_id=1, track="Monza")
    _insert_rec(db, car_id=1, track="Suzuka")   # duplicate
    _insert_rec(db, car_id=1, track="Brands Hatch")
    tracks = db.get_tracks_for_car_recommendations(1)
    assert tracks == ["Brands Hatch", "Monza", "Suzuka"]


def test_get_tracks_empty_when_no_recs():
    db = _make_db()
    tracks = db.get_tracks_for_car_recommendations(99)
    assert tracks == []


def test_get_tracks_excludes_other_cars():
    db = _make_db()
    _insert_rec(db, car_id=1, track="Suzuka")
    _insert_rec(db, car_id=2, track="Monza")
    _insert_rec(db, car_id=2, track="Nurburgring")
    tracks_a = db.get_tracks_for_car_recommendations(1)
    assert tracks_a == ["Suzuka"]
    tracks_b = db.get_tracks_for_car_recommendations(2)
    assert "Monza" in tracks_b and "Nurburgring" in tracks_b
    assert "Suzuka" not in tracks_b


def test_get_tracks_excludes_blank_track():
    db = _make_db()
    _insert_rec(db, car_id=1, track="")
    _insert_rec(db, car_id=1, track="Interlagos")
    tracks = db.get_tracks_for_car_recommendations(1)
    assert "" not in tracks
    assert tracks == ["Interlagos"]


# ---------------------------------------------------------------------------
# Tests for get_setup_history_for_car_track
# ---------------------------------------------------------------------------

def test_history_text_not_empty_when_recs_exist():
    db = _make_db()
    _insert_rec(db, car_id=5, track="Le Mans", text="Soften rear springs by 10%.")
    text = db.get_setup_history_for_car_track(5, "Le Mans", limit=10)
    assert text  # non-empty


def test_history_text_empty_string_when_no_recs():
    db = _make_db()
    text = db.get_setup_history_for_car_track(5, "Le Mans", limit=10)
    assert not text  # falsy / empty string
