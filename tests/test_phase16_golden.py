"""Phase 16 — golden end-to-end through the real SessionDB production path + restart."""
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


def _seed(db, at="2026-07-01T10:00"):
    outcome = {"id": "300", "experiment_id": 10, "status": "no_meaningful_change",
               "confidence_level": "high", "scope_fingerprint": "sf", "test_session_id": "s1",
               "protected": [], "failed_directions": []}
    exp = {"id": 10, "scope_fingerprint": "sf",
           "changes": [{"field": "arb_front", "from_value": "5", "to_value": "4"}]}
    residuals = [{"issue_key": "k1", "family": "rotation", "issue_type": "entry_understeer",
                  "axle": "front", "phase": "entry", "segment_id": "T1", "corner_name": "T1",
                  "residual_state": "unchanged", "is_new": False, "is_regression": False,
                  "still_present": True, "protected_good": False, "confidence": "high"}]
    rec = build_development_record(outcome, exp, context=CTX, scope_fingerprint="sf",
                                  working_windows=[], residuals=residuals, recorded_at=at,
                                  session_date=at[:10])
    db._persist_development_record(rec, created_at=rec.recorded_at)


def _kw():
    return dict(car="Porsche 911 RSR", track="Fuji", layout_id="fc", discipline="Race",
                driver="leon", gt7_version="1.49", compound="RH")


def test_aggregate_lifecycle_shows_forward_chain(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    _seed(db)
    r = db.build_engineering_lifecycle(applied_setup=applied(), session_identity=IDENT, **_kw())
    assert r["ok"] and r["count"] >= 1
    stage = r["stages"][0]
    ss = stage["stage_states"]
    # forward chain present: diagnosis -> mechanism -> hypothesis -> synthesis
    assert ss["diagnosis"] == "present" and ss["mechanism"] == "present"
    assert ss["hypothesis"] == "present"
    assert stage["trace"]["diagnosis_key"] and stage["trace"]["synthesis_candidate_id"]
    db.close()


def test_single_candidate_execution_through_real_preflight(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    _seed(db)
    synth = db.build_bounded_setup_experiments(applied_setup=applied(), session_identity=IDENT,
                                               **_kw())
    cand = None
    for res in synth["synthesis_results"]:
        cand = res.get("selected_candidate")
        if cand:
            break
    assert cand is not None
    ex = db.build_experiment_execution(cand, diagnosis_key="diag", **_kw())
    assert ex["ok"] and ex["lifecycle_state"] == "ready_for_manual_apply"
    # a real Phase-10 preflight review was produced (existing authority)
    assert ex["preflight_review"] and ex["preflight_review"].get("ok")
    # a canonical SetupExperiment was built (not persisted)
    assert ex["request"]["setup_experiment"]["status"] == "draft"
    # nothing was written
    assert db._conn.execute(
        "SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == 0
    db.close()


def test_lifecycle_restart_determinism(tmp_path):
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    _seed(db)
    r1 = db.build_engineering_lifecycle(applied_setup=applied(), session_identity=IDENT, **_kw())
    db._conn.close()
    db2 = SessionDB(p)
    r2 = db2.build_engineering_lifecycle(applied_setup=applied(), session_identity=IDENT, **_kw())
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 27
    db2._conn.close()


def test_empty_db_safe():
    db = SessionDB(":memory:")
    r = db.build_engineering_lifecycle(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    assert r["ok"] and r["count"] == 0
    ex = db.build_experiment_execution({}, car="Porsche 911 RSR", track="Fuji")
    assert ex["ok"] and ex["lifecycle_state"] == "not_actionable"
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 27
    db.close()
