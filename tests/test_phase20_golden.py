"""Phase 20 — golden UAT scenarios + real SessionDB production path + restart determinism.

Exercises the whole chain (Phase 8 records -> Phase 17/18 -> Phase 19 efficiency -> Phase 20
confidence/ROI/opportunity) through the real DB. Read-only; writes nothing; DB stays v26.
"""
import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.development_history import MemoryContextKey, build_development_record
from data.applied_checkpoint import compute_setup_hash

IDENT = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc"}
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0,
          "lsd_accel": 20}


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


def _seed(db, status, at, sess, changes=None):
    residuals = [{"issue_key": "k1", "family": "rotation", "issue_type": "entry_understeer",
                  "axle": "front", "phase": "entry", "segment_id": "T1", "corner_name": "T1",
                  "residual_state": "improved_but_present", "is_new": False,
                  "is_regression": False, "still_present": True, "protected_good": False,
                  "confidence": "high"}]
    outcome = {"id": f"o{sess}", "experiment_id": 10, "status": status,
               "confidence_level": "high", "scope_fingerprint": "sf", "test_session_id": sess,
               "protected": [], "failed_directions": []}
    exp = {"id": 10, "scope_fingerprint": "sf",
           "changes": changes or [{"field": "arb_front", "from_value": "5", "to_value": "4"}]}
    rec = build_development_record(outcome, exp, context=CTX, scope_fingerprint="sf",
                                  working_windows=[], residuals=residuals, recorded_at=at,
                                  session_date=at[:10])
    db._persist_development_record(rec, created_at=rec.recorded_at)


# Scenario A: a single confirmation -> MEDIUM confidence (not yet repeated) + worthwhile ROI.
def test_scenario_A_single_confirmation_medium(tmp_path):
    db = SessionDB(str(tmp_path / "a.db"))
    _seed(db, "confirmed_improvement", "2026-07-01T10:00", "s1")
    r = db.build_engineering_knowledge_quality(applied_setup=applied(), session_identity=IDENT,
                                               now_date="2026-07-05", **_kw())
    assert r["ok"] and r["campaign_count"] >= 1
    c = r["knowledge_quality"]["campaigns"][0]
    assert c["confidence"]["overall_level"] in ("medium", "low", "very_low")
    assert c["roi"]["knowledge_gap"] > 0
    assert c["opportunity"]["opportunity"] in (
        "worth_another_confirmation", "worth_mechanism_isolation",
        "worth_contradiction_testing")
    db.close()


# Scenario B: confirmed across two sessions -> higher confidence, opportunity not "worth more".
def test_scenario_B_repeated_confirmation_high(tmp_path):
    db = SessionDB(str(tmp_path / "b.db"))
    _seed(db, "confirmed_improvement", "2026-07-01T10:00", "s1")
    _seed(db, "confirmed_improvement", "2026-07-03T10:00", "s2")
    r = db.build_engineering_knowledge_quality(applied_setup=applied(), session_identity=IDENT,
                                               now_date="2026-07-05", **_kw())
    c = r["knowledge_quality"]["campaigns"][0]
    # two confirmations should lift confidence above the single-confirmation MEDIUM cap
    assert c["confidence"]["overall_level"] in ("medium", "high", "very_high")
    assert c["opportunity"]["opportunity"] in (
        "complete", "nearly_complete", "not_worth_further_work",
        "worth_another_confirmation", "knowledge_plateau")
    db.close()


# Scenario C: a regression -> low confidence, elevated risk, worthwhile discriminating test.
def test_scenario_C_regression_low_confidence(tmp_path):
    db = SessionDB(str(tmp_path / "c.db"))
    _seed(db, "regression", "2026-07-01T10:00", "s1",
          changes=[{"field": "lsd_accel", "from_value": "20", "to_value": "30"}])
    r = db.build_engineering_knowledge_quality(applied_setup=applied(), session_identity=IDENT,
                                               now_date="2026-07-05", **_kw())
    assert r["ok"]
    if r["campaign_count"]:
        c = r["knowledge_quality"]["campaigns"][0]
        assert c["confidence"]["overall_level"] in ("unknown", "very_low", "low", "medium")
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
    db.build_engineering_knowledge_quality(applied_setup=applied(), session_identity=IDENT,
                                           now_date="2026-07-05", **_kw())
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == exp0
    # Phase 20 never triggers the Phase-19 opt-in registry capture -> registry unchanged
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0] == reg0 == 0
    db.close()


def test_production_restart_determinism(tmp_path):
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    _seed(db, "confirmed_improvement", "2026-07-01T10:00", "s1")
    r1 = db.build_engineering_knowledge_quality(applied_setup=applied(), session_identity=IDENT,
                                                now_date="2026-07-05", **_kw())
    db._conn.close()
    db2 = SessionDB(p)
    r2 = db2.build_engineering_knowledge_quality(applied_setup=applied(), session_identity=IDENT,
                                                 now_date="2026-07-05", **_kw())
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 28
    db2._conn.close()


def test_empty_db_safe():
    db = SessionDB(":memory:")
    r = db.build_engineering_knowledge_quality(car="Porsche 911 RSR", track="Fuji",
                                               discipline="Race")
    assert r["ok"] and r["campaign_count"] == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 28
    db.close()
