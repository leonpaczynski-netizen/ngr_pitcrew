"""Structured Practice Review capture tests (Engineering-Brain Phase 7).

The driver's explicit better/worse-vs-previous report is stored on driver_feedback and
stamps the latest setup-lineage node — closing the loop with direct driver input.
"""
from __future__ import annotations

import json

from data.session_db import SessionDB
from strategy.setup_lineage import vs_previous_to_verdict, rollback_from_lineage


def test_schema_v16_and_columns():
    db = SessionDB(":memory:")
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 16
    cols = [r[1] for r in db._conn.execute("PRAGMA table_info(driver_feedback)").fetchall()]
    assert {"vs_previous", "corner", "phase"} <= set(cols)


def test_write_feedback_stores_directional_fields():
    db = SessionDB(":memory:")
    db.write_feedback(1, 5, {"mid_corner": "pushes wide", "vs_previous": "worse",
                             "corner": "2", "phase": "apex"},
                      config_id="c", setup_id=1, rating="hated")
    row = db._conn.execute(
        "SELECT vs_previous, corner, phase FROM driver_feedback ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert tuple(row) == ("worse", "2", "apex")


def test_vs_previous_maps_to_verdict():
    assert vs_previous_to_verdict("better") == "improved"
    assert vs_previous_to_verdict("worse") == "worsened"
    assert vs_previous_to_verdict("unchanged") == "neutral"
    assert vs_previous_to_verdict("") == ""


def test_explicit_worse_stamps_lineage_and_drives_rollback():
    db = SessionDB(":memory:")
    db._conn.execute(
        "INSERT INTO setup_recommendations (car_id, track, layout_id, status, "
        "approved_changes_json, created_at) VALUES (1,'Fuji','full','proposed',?,'t')",
        (json.dumps([{"field": "lsd_accel", "from": "15", "to": "17"}]),))
    db._conn.commit()
    db.apply_recommendation_for_car_track(1, "Fuji", 10)     # creates an unscored node
    # Driver reports the setup is worse → stamp the latest node.
    db.record_latest_lineage_outcome(1, "Fuji", "full",
                                     vs_previous_to_verdict("worse"), 11)
    lin = db.get_lineage(1, "Fuji", "full")
    assert lin[0]["outcome_verdict"] == "worsened"
    # A node needs a parent to roll back to; with a single node there's nothing to revert.
    # Add a parent chain and confirm rollback fires on the worse child.
    db._conn.execute(
        "INSERT INTO setup_recommendations (car_id, track, layout_id, status, "
        "approved_changes_json, created_at) VALUES (1,'Fuji','full','proposed',?,'t')",
        (json.dumps([{"field": "aero_rear", "from": "600", "to": "630"}]),))
    db._conn.commit()
    db.apply_recommendation_for_car_track(1, "Fuji", 12)     # child node, parent = first
    db.record_latest_lineage_outcome(1, "Fuji", "full", "worsened", 13)
    rb = rollback_from_lineage(db.get_lineage(1, "Fuji", "full"))
    assert rb["recommend_rollback"] is True


def test_record_latest_only_fills_unscored_node():
    db = SessionDB(":memory:")
    db._conn.execute(
        "INSERT INTO setup_recommendations (car_id, track, layout_id, status, "
        "approved_changes_json, created_at) VALUES (1,'Fuji','full','proposed','[]','t')")
    db._conn.commit()
    db.apply_recommendation_for_car_track(1, "Fuji", 10)
    db.record_latest_lineage_outcome(1, "Fuji", "full", "improved", 11)
    # A second call must NOT overwrite the already-scored node (no unscored node left).
    db.record_latest_lineage_outcome(1, "Fuji", "full", "worsened", 12)
    assert db.get_lineage(1, "Fuji", "full")[0]["outcome_verdict"] == "improved"
