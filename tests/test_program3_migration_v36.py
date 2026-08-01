"""Program 3 Phase B — schema v36: car-spec & track-model version registries."""

import uuid

from data.session_db import SessionDB


def test_tables_exist(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] >= 36
    tables = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"car_spec_revisions", "track_model_versions"} <= tables


def test_car_spec_revisions_recorded_and_scoped(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    r1 = db.add_car_spec_revision(car_id=333, car_name="Porsche 911 RSR '17", event_id=5,
                                  bop_json='{"power": -2, "weight": 10}', label="Round 4 BoP")
    assert uuid.UUID(r1).version == 7
    got = db.get_car_spec_revisions(car_id=333)
    assert len(got) == 1 and got[0]["label"] == "Round 4 BoP"
    assert db.get_car_spec_revisions(car_id=999) == []          # scoped by car
    assert len(db.get_car_spec_revisions(event_id=5)) == 1      # and by event


def test_track_model_versions_and_approved_lookup(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    db.register_track_model_version(track_location_id="fuji", layout_id="full_course",
                                    model_status="draft", approved=False)
    approved = db.register_track_model_version(track_location_id="fuji", layout_id="full_course",
                                               model_status="approved", approved=True,
                                               confidence=0.9, created_at="2026-01-02T00:00:00Z")
    versions = db.get_track_model_versions("fuji", "full_course")
    assert len(versions) == 2
    # the approved lookup returns the approved one, and ignores other layouts/tracks
    got = db.get_approved_track_model_version("fuji", "full_course")
    assert got is not None and got["version_id"] == approved and got["approved"] == 1
    assert db.get_approved_track_model_version("monza", "full_course") is None
    assert db.get_approved_track_model_version("fuji", "layout_b") is None
