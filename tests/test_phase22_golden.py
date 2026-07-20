"""Phase 22 — golden UAT + real SessionDB production path + restart determinism.

Exercises the whole chain (Phase 8 records across events -> Phase 17/18/19/20/21 -> Phase 22
knowledge graph) through the real DB. Read-only; writes nothing; DB stays v26.
"""
import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.development_history import MemoryContextKey, build_development_record
from data.applied_checkpoint import compute_setup_hash

FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0, "lsd_accel": 20}


def applied():
    d = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "setup_id": "S1",
         "name": "Base", "revision": 1, "state": "applied", "fields": dict(FIELDS),
         "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


def _kw(track="Fuji", discipline="Race"):
    return dict(car="Porsche 911 RSR", track=track, layout_id="fc", discipline=discipline,
                driver="leon", gt7_version="1.49", compound="RH")


def _seed(db, track, discipline, status, at, sess, field, family, issue):
    ctx = MemoryContextKey(driver="leon", car="Porsche 911 RSR", track=track, layout_id="fc",
                           discipline=discipline, gt7_version="1.49", compound="RH")
    residuals = [{"issue_key": f"k{sess}", "family": family, "issue_type": issue,
                  "axle": "front", "phase": "entry", "segment_id": "T1", "corner_name": "T1",
                  "residual_state": "improved_but_present", "is_new": False,
                  "is_regression": False, "still_present": True, "protected_good": False,
                  "confidence": "high"}]
    outcome = {"id": f"o{sess}", "experiment_id": 10, "status": status,
               "confidence_level": "high", "scope_fingerprint": "sf", "test_session_id": sess,
               "protected": [], "failed_directions": []}
    exp = {"id": 10, "scope_fingerprint": "sf",
           "changes": [{"field": field, "from_value": "5", "to_value": "4"}]}
    rec = build_development_record(outcome, exp, context=ctx, scope_fingerprint="sf",
                                  working_windows=[], residuals=residuals, recorded_at=at,
                                  session_date=at[:10])
    db._persist_development_record(rec, created_at=rec.recorded_at)


# Scenario A: knowledge organised by domain appears for a single event.
def test_scenario_A_single_event_domains(tmp_path):
    db = SessionDB(str(tmp_path / "a.db"))
    _seed(db, "Fuji", "Race", "confirmed_improvement", "2026-07-01T10:00", "s1",
          "arb_front", "rotation", "entry_understeer")
    r = db.build_programme_knowledge_report(applied_setup=applied(),
                                            now_date="2026-07-05", **_kw())
    assert r["ok"] and r["known_domain_count"] >= 1
    pk = r["programme_knowledge"]
    assert len(pk["knowledge_graph"]["domains"]) == 17
    assert pk["knowledge_graph"]["missing_domains"]        # some domains still missing
    assert pk["safety_statement"]
    db.close()


# Scenario B: two compatible events (same car/discipline, different tracks) roll up together.
def test_scenario_B_multi_event_rollup(tmp_path):
    db = SessionDB(str(tmp_path / "b.db"))
    _seed(db, "Fuji", "Race", "confirmed_improvement", "2026-07-01T10:00", "s1",
          "arb_front", "rotation", "entry_understeer")
    _seed(db, "Spa", "Race", "confirmed_improvement", "2026-07-02T10:00", "s2",
          "lsd_accel", "traction", "wheelspin")
    r = db.build_programme_knowledge_report(applied_setup=applied(),
                                            now_date="2026-07-05", **_kw())
    pk = r["programme_knowledge"]
    assert pk["compatibility"]["events_merged"] == 2
    assert set(pk["compatibility"]["primary_tracks"]) == {"Fuji", "Spa"}
    db.close()


# Scenario C: an incompatible event (different discipline) is NOT merged; reason exposed.
def test_scenario_C_incompatible_excluded(tmp_path):
    db = SessionDB(str(tmp_path / "c.db"))
    _seed(db, "Fuji", "Race", "confirmed_improvement", "2026-07-01T10:00", "s1",
          "arb_front", "rotation", "entry_understeer")
    _seed(db, "Fuji", "Qualifying", "confirmed_improvement", "2026-07-02T10:00", "s2",
          "brake_bias", "braking", "rear_loose_under_braking")
    r = db.build_programme_knowledge_report(applied_setup=applied(),
                                            now_date="2026-07-05", **_kw(discipline="Race"))
    pk = r["programme_knowledge"]
    assert pk["compatibility"]["events_merged"] == 1
    excl = pk["compatibility"]["excluded_reasons"]
    assert excl and "discipline" in excl[0]["differing_fields"]
    db.close()


# --- production integrity ---------------------------------------------------
def test_production_writes_nothing(tmp_path):
    db = SessionDB(str(tmp_path / "p.db"))
    _seed(db, "Fuji", "Race", "confirmed_improvement", "2026-07-01T10:00", "s1",
          "arb_front", "rotation", "entry_understeer")
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    reg0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0]
    db.build_programme_knowledge_report(applied_setup=applied(), now_date="2026-07-05", **_kw())
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0] == reg0 == 0
    db.close()


def test_production_restart_determinism(tmp_path):
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    _seed(db, "Fuji", "Race", "confirmed_improvement", "2026-07-01T10:00", "s1",
          "arb_front", "rotation", "entry_understeer")
    _seed(db, "Spa", "Race", "confirmed_improvement", "2026-07-02T10:00", "s2",
          "lsd_accel", "traction", "wheelspin")
    r1 = db.build_programme_knowledge_report(applied_setup=applied(),
                                             now_date="2026-07-05", **_kw())
    db._conn.close()
    db2 = SessionDB(p)
    r2 = db2.build_programme_knowledge_report(applied_setup=applied(),
                                              now_date="2026-07-05", **_kw())
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 27
    db2._conn.close()


def test_empty_db_safe():
    db = SessionDB(":memory:")
    r = db.build_programme_knowledge_report(car="Porsche 911 RSR", track="Fuji",
                                            discipline="Race")
    assert r["ok"] and r["known_domain_count"] == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 27
    db.close()
