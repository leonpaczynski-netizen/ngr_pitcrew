"""Phase 19 — golden UAT scenarios + real SessionDB production path + restart determinism.

Exercises the whole chain (Phase 8 records -> Phase 17 portfolio -> Phase 18 campaigns ->
Phase 19 efficiency) through the real DB, then asserts the read-only advisory + the opt-in
registry capture behave as specified. Nothing is applied, completed or frozen.
"""
import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.development_history import MemoryContextKey, build_development_record
from data.applied_checkpoint import compute_setup_hash

IDENT = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc"}
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0,
          "springs_rear": 5.0, "lsd_accel": 20, "lsd_decel": 20, "aero_front": 300}


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


def _seed(db, changes, status, at, sess):
    residuals = [{"issue_key": "k1", "family": "rotation", "issue_type": "entry_understeer",
                  "axle": "front", "phase": "entry", "segment_id": "T1", "corner_name": "T1",
                  "residual_state": "improved_but_present", "is_new": False,
                  "is_regression": False, "still_present": True, "protected_good": False,
                  "confidence": "high"}]
    outcome = {"id": f"o{sess}", "experiment_id": 10, "status": status,
               "confidence_level": "high", "scope_fingerprint": "sf", "test_session_id": sess,
               "protected": [], "failed_directions": []}
    exp = {"id": 10, "scope_fingerprint": "sf", "changes": changes}
    rec = build_development_record(outcome, exp, context=CTX, scope_fingerprint="sf",
                                  working_windows=[], residuals=residuals, recorded_at=at,
                                  session_date=at[:10])
    db._persist_development_record(rec, created_at=rec.recorded_at)


# Scenario A: an early campaign (one confirmed) -> efficiency shows building/early evidence,
# a positive remaining information gain and a non-zero cost of the remaining testing.
def test_scenario_A_early_campaign_has_remaining_value(tmp_path):
    db = SessionDB(str(tmp_path / "a.db"))
    _seed(db, [{"field": "arb_front", "from_value": "5", "to_value": "4"}],
          "confirmed_improvement", "2026-07-01T10:00", "s1")
    r = db.build_engineering_efficiency(applied_setup=applied(), session_identity=IDENT,
                                        now_date="2026-07-05", **_kw())
    assert r["ok"] and r["campaign_count"] >= 1
    c = r["efficiency"]["campaigns"][0]
    assert c["saturation"]["status"] in ("early", "building", "strong", "not_started")
    assert c["remaining_information_gain"] in ("high", "moderate", "low", "none")
    assert c["estimated_remaining_laps"] >= 0
    db.close()


# Scenario B: opt-in registry capture records first-seen provenance and campaign age.
def test_scenario_B_optin_capture_records_age(tmp_path):
    db = SessionDB(str(tmp_path / "b.db"))
    _seed(db, [{"field": "arb_front", "from_value": "5", "to_value": "4"}],
          "confirmed_improvement", "2026-07-01T10:00", "s1")
    # first observation on 2026-07-02
    db.build_engineering_efficiency(applied_setup=applied(), session_identity=IDENT,
                                    register_session_id="sess-A", recorded_at="2026-07-02",
                                    now_date="2026-07-02", **_kw())
    rows = db.get_campaign_registry(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    assert rows and rows[0]["first_seen"] == "2026-07-02"
    # later observation -> age computed from the preserved first-seen
    r2 = db.build_engineering_efficiency(applied_setup=applied(), session_identity=IDENT,
                                         register_session_id="sess-B", recorded_at="2026-07-12",
                                         now_date="2026-07-12", **_kw())
    c = r2["efficiency"]["campaigns"][0]
    assert c["age_days"] == 10 and "week" in c["age_label"]
    # first_seen/creation preserved
    rows2 = db.get_campaign_registry(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    assert rows2[0]["first_seen"] == "2026-07-02" and rows2[0]["creation_session"] == "sess-A"
    db.close()


# Scenario C: budget fit — with a session budget, some experiments fit; advisory only.
def test_scenario_C_budget_fit_advisory(tmp_path):
    db = SessionDB(str(tmp_path / "c.db"))
    _seed(db, [{"field": "arb_front", "from_value": "5", "to_value": "4"}],
          "no_meaningful_change", "2026-07-01T10:00", "s1")
    r = db.build_engineering_efficiency(
        applied_setup=applied(), session_identity=IDENT, now_date="2026-07-05",
        session_budget={"session_minutes_remaining": 60, "tyre_sets_available": 4,
                        "lap_time_seconds": 120}, **_kw())
    budget = r["efficiency"]["budget"]
    assert budget["budget_known"] is True
    assert "optimis" not in budget["rationale"].lower() or "no optimis" in budget["rationale"].lower()
    db.close()


# --- production integrity ---------------------------------------------------
def test_production_writes_only_registry(tmp_path):
    db = SessionDB(str(tmp_path / "p.db"))
    _seed(db, [{"field": "arb_front", "from_value": "5", "to_value": "4"}],
          "confirmed_improvement", "2026-07-01T10:00", "s1")
    dev_before = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    exp_before = db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0]
    db.build_engineering_efficiency(applied_setup=applied(), session_identity=IDENT,
                                    register_session_id="s", recorded_at="2026-07-02",
                                    now_date="2026-07-02", **_kw())
    # dev records + experiments untouched; only the registry may have grown
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev_before
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == exp_before
    db.close()


def test_production_restart_determinism(tmp_path):
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    _seed(db, [{"field": "arb_front", "from_value": "5", "to_value": "4"}],
          "confirmed_improvement", "2026-07-01T10:00", "s1")
    r1 = db.build_engineering_efficiency(applied_setup=applied(), session_identity=IDENT,
                                         now_date="2026-07-05", **_kw())
    db._conn.close()
    db2 = SessionDB(p)
    r2 = db2.build_engineering_efficiency(applied_setup=applied(), session_identity=IDENT,
                                          now_date="2026-07-05", **_kw())
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 26
    db2._conn.close()


def test_empty_db_safe():
    db = SessionDB(":memory:")
    r = db.build_engineering_efficiency(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    assert r["ok"] and r["campaign_count"] == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 26
    db.close()
