"""Phase 21 — golden UAT + real SessionDB production path + restart determinism.

Exercises the whole chain (Phase 8 records -> Phase 17/18 -> Phase 19 -> Phase 20 -> Phase 21
season report) through the real DB. Read-only; writes nothing; DB stays v26.
"""
import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.development_history import MemoryContextKey, build_development_record
from data.applied_checkpoint import compute_setup_hash

IDENT = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc"}
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0, "lsd_accel": 20}


def applied():
    d = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "setup_id": "S1",
         "name": "Base", "revision": 1, "state": "applied", "fields": dict(FIELDS),
         "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


CTX = MemoryContextKey(driver="leon", car="Porsche 911 RSR", track="Fuji", layout_id="fc",
                       discipline="Race", gt7_version="1.49", compound="RH")


def _kw():
    return dict(car="Porsche 911 RSR", track="Fuji", layout_id="fc", discipline="Race",
                driver="leon", gt7_version="1.49", compound="RH")


def _seed(db, status, at, sess, issue_type="entry_understeer", family="rotation",
          axle="front", phase="entry", field="arb_front"):
    residuals = [{"issue_key": f"k_{sess}", "family": family, "issue_type": issue_type,
                  "axle": axle, "phase": phase, "segment_id": "T1", "corner_name": "T1",
                  "residual_state": "improved_but_present", "is_new": False,
                  "is_regression": False, "still_present": True, "protected_good": False,
                  "confidence": "high"}]
    outcome = {"id": f"o{sess}", "experiment_id": 10, "status": status,
               "confidence_level": "high", "scope_fingerprint": "sf", "test_session_id": sess,
               "protected": [], "failed_directions": []}
    exp = {"id": 10, "scope_fingerprint": "sf",
           "changes": [{"field": field, "from_value": "5", "to_value": "4"}]}
    rec = build_development_record(outcome, exp, context=CTX, scope_fingerprint="sf",
                                  working_windows=[], residuals=residuals, recorded_at=at,
                                  session_date=at[:10])
    db._persist_development_record(rec, created_at=rec.recorded_at)


# Scenario A: one campaign, single confirmation -> a knowledge map + summary appear.
def test_scenario_A_single_campaign_summary(tmp_path):
    db = SessionDB(str(tmp_path / "a.db"))
    _seed(db, "confirmed_improvement", "2026-07-01T10:00", "s1")
    r = db.build_season_engineering_report(applied_setup=applied(), session_identity=IDENT,
                                           now_date="2026-07-05", **_kw())
    assert r["ok"] and r["campaign_count"] >= 1
    rep = r["season_report"]
    assert rep["development"]["metrics"]["campaign_count"]["value"] >= 1
    assert len(rep["knowledge_map"]) == r["campaign_count"]
    assert "relationships" in rep and "safety_statement" in rep
    db.close()


# Scenario B: two distinct systems -> both campaigns appear, relationships computed.
def test_scenario_B_multi_system(tmp_path):
    db = SessionDB(str(tmp_path / "b.db"))
    _seed(db, "confirmed_improvement", "2026-07-01T10:00", "s1",
          issue_type="entry_understeer", family="rotation", axle="front", phase="entry",
          field="arb_front")
    _seed(db, "regression", "2026-07-02T10:00", "s2",
          issue_type="wheelspin", family="traction", axle="rear", phase="exit",
          field="lsd_accel")
    r = db.build_season_engineering_report(applied_setup=applied(), session_identity=IDENT,
                                           now_date="2026-07-05", **_kw())
    assert r["ok"]
    rep = r["season_report"]
    # a knowledge map entry per campaign; relationships object present (possibly isolated)
    assert len(rep["knowledge_map"]) == r["campaign_count"]
    assert isinstance(rep["relationships"]["edges"], list)
    db.close()


# --- production integrity ---------------------------------------------------
def test_production_writes_nothing(tmp_path):
    db = SessionDB(str(tmp_path / "p.db"))
    _seed(db, "confirmed_improvement", "2026-07-01T10:00", "s1")
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    exp0 = db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0]
    reg0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0]
    db.build_season_engineering_report(applied_setup=applied(), session_identity=IDENT,
                                       now_date="2026-07-05", **_kw())
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == exp0
    # Phase 21 uses the read-only registry read; it triggers no registry write.
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0] == reg0 == 0
    db.close()


def test_production_restart_determinism(tmp_path):
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    _seed(db, "confirmed_improvement", "2026-07-01T10:00", "s1")
    r1 = db.build_season_engineering_report(applied_setup=applied(), session_identity=IDENT,
                                            now_date="2026-07-05", **_kw())
    db._conn.close()
    db2 = SessionDB(p)
    r2 = db2.build_season_engineering_report(applied_setup=applied(), session_identity=IDENT,
                                             now_date="2026-07-05", **_kw())
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 26
    db2._conn.close()


def test_empty_db_safe():
    db = SessionDB(":memory:")
    r = db.build_season_engineering_report(car="Porsche 911 RSR", track="Fuji",
                                           discipline="Race")
    assert r["ok"] and r["campaign_count"] == 0 and r["season_report"] is None
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 26
    db.close()
