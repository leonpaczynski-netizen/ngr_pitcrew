"""Phase 17 — golden end-to-end through the real SessionDB production path + restart."""
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


def _seed(db, issues, at="2026-07-01T10:00"):
    residuals = [{"issue_key": f"k{i}", "family": "rotation", "issue_type": it,
                  "axle": ax, "phase": ph, "segment_id": f"T{i}", "corner_name": f"T{i}",
                  "residual_state": "unchanged", "is_new": False, "is_regression": False,
                  "still_present": True, "protected_good": False, "confidence": "high"}
                 for i, (it, ax, ph) in enumerate(issues)]
    outcome = {"id": "300", "experiment_id": 10, "status": "no_meaningful_change",
               "confidence_level": "high", "scope_fingerprint": "sf", "test_session_id": "s1",
               "protected": [], "failed_directions": []}
    exp = {"id": 10, "scope_fingerprint": "sf",
           "changes": [{"field": "arb_front", "from_value": "5", "to_value": "4"}]}
    rec = build_development_record(outcome, exp, context=CTX, scope_fingerprint="sf",
                                  working_windows=[], residuals=residuals, recorded_at=at,
                                  session_date=at[:10])
    db._persist_development_record(rec, created_at=rec.recorded_at)


def _kw():
    return dict(car="Porsche 911 RSR", track="Fuji", layout_id="fc", discipline="Race",
                driver="leon", gt7_version="1.49", compound="RH")


def test_portfolio_production_path(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    _seed(db, [("entry_understeer", "front", "entry"), ("mid_corner_understeer", "front", "apex")])
    r = db.build_experiment_portfolio(
        applied_setup=applied(), session_identity=IDENT,
        session_context={"practice_minutes_remaining": 30, "tyre_sets_available": 3}, **_kw())
    assert r["ok"] and r["count"] >= 1
    port = r["portfolio"]
    assert port["dimension_weights"]["information_gain"] == max(port["dimension_weights"].values())
    # not written
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == 1
    import re
    assert not re.search(r"set \w+ to \d", str(r).lower())
    db.close()


def test_portfolio_restart_determinism(tmp_path):
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    _seed(db, [("entry_understeer", "front", "entry")])
    r1 = db.build_experiment_portfolio(applied_setup=applied(), session_identity=IDENT, **_kw())
    db._conn.close()
    db2 = SessionDB(p)
    r2 = db2.build_experiment_portfolio(applied_setup=applied(), session_identity=IDENT, **_kw())
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 28
    db2._conn.close()


def test_empty_db_safe():
    db = SessionDB(":memory:")
    r = db.build_experiment_portfolio(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    assert r["ok"] and r["count"] == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 28
    db.close()
