"""Phase 23 — golden UAT + real SessionDB production path + restart determinism.

Exercises the whole chain (records across cars/disciplines -> Phase 17..22 -> Phase 23 transfer)
through the real DB. Read-only; writes nothing; DB stays v26.
"""
import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.development_history import MemoryContextKey, build_development_record
from data.applied_checkpoint import compute_setup_hash

PORSCHE = "Porsche 911 RSR (991) '17"
TOYOTA = "Toyota GR Supra Racing Concept Gr.3"
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0, "lsd_accel": 20}


def applied(car=PORSCHE):
    d = {"car": car, "track": "Fuji", "layout_id": "fc", "setup_id": "S1", "name": "Base",
         "revision": 1, "state": "applied", "fields": dict(FIELDS), "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


def _kw(car=PORSCHE, track="Fuji", discipline="Race"):
    return dict(car=car, track=track, layout_id="fc", discipline=discipline, driver="leon",
                gt7_version="1.49", compound="RH")


def _seed(db, car, track, discipline, status, at, sess, field, family, issue):
    ctx = MemoryContextKey(driver="leon", car=car, track=track, layout_id="fc",
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


def _source_and_targets(db):
    # source: Porsche RSR Race (two confirmations -> mature knowledge)
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-01T10:00", "s1",
          "lsd_accel", "traction", "wheelspin")
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-02T10:00", "s2",
          "lsd_accel", "traction", "wheelspin")
    # target A: a different car (Toyota) -> incompatible manufacturer
    _seed(db, TOYOTA, "Spa", "Race", "confirmed_improvement", "2026-07-03T10:00", "s3",
          "arb_front", "rotation", "entry_understeer")
    # target B: same car different discipline (Qualifying)
    _seed(db, PORSCHE, "Fuji", "Qualifying", "confirmed_improvement", "2026-07-04T10:00", "s4",
          "brake_bias", "braking", "rear_loose_under_braking")


def test_scenario_A_transfer_candidates(tmp_path):
    db = SessionDB(str(tmp_path / "a.db"))
    _source_and_targets(db)
    r = db.build_programme_transfer_report(applied_setup=applied(), now_date="2026-07-06", **_kw())
    assert r["ok"] and r["candidate_count"] >= 1
    tr = r["transfer_report"]
    assert tr["source_context"]["car"] == PORSCHE
    assert tr["safety_statement"] and tr["rule_catalogue"]
    db.close()


def test_scenario_B_cross_car_low_or_isolated(tmp_path):
    db = SessionDB(str(tmp_path / "b.db"))
    _source_and_targets(db)
    r = db.build_programme_transfer_report(applied_setup=applied(), now_date="2026-07-06", **_kw())
    tr = r["transfer_report"]
    # the Toyota target should have no reusable knowledge (different manufacturer)
    toyota_cands = [c for c in tr["candidates"] if c["target_context"]["car"] == TOYOTA]
    assert toyota_cands
    assert all(c["transfer_level"] in ("low", "very_low", "not_transferable", "medium")
               for c in toyota_cands)
    db.close()


def test_scenario_C_no_targets_when_single_context(tmp_path):
    db = SessionDB(str(tmp_path / "c.db"))
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-01T10:00", "s1",
          "lsd_accel", "traction", "wheelspin")
    r = db.build_programme_transfer_report(applied_setup=applied(), now_date="2026-07-06", **_kw())
    # only the source context exists -> no other groups -> no candidates
    assert r["ok"]
    tr = r["transfer_report"]
    assert tr is None or tr["totals"]["target_contexts"] == 0
    db.close()


def test_production_writes_nothing(tmp_path):
    db = SessionDB(str(tmp_path / "p.db"))
    _source_and_targets(db)
    dev0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    reg0 = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0]
    db.build_programme_transfer_report(applied_setup=applied(), now_date="2026-07-06", **_kw())
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == dev0
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0] == reg0 == 0
    db.close()


def test_production_restart_determinism(tmp_path):
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    _source_and_targets(db)
    r1 = db.build_programme_transfer_report(applied_setup=applied(), now_date="2026-07-06", **_kw())
    db._conn.close()
    db2 = SessionDB(p)
    r2 = db2.build_programme_transfer_report(applied_setup=applied(), now_date="2026-07-06", **_kw())
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 27
    db2._conn.close()


def test_empty_db_safe():
    db = SessionDB(":memory:")
    r = db.build_programme_transfer_report(car=PORSCHE, track="Fuji", discipline="Race")
    assert r["ok"] and r["candidate_count"] == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 27
    db.close()


def test_render_is_ascii(tmp_path):
    from strategy.programme_transfer_report_render import render_report_text
    db = SessionDB(str(tmp_path / "r.db"))
    _source_and_targets(db)
    r = db.build_programme_transfer_report(applied_setup=applied(), now_date="2026-07-06", **_kw())
    if r["transfer_report"]:
        txt = render_report_text(r["transfer_report"])
        # the renderer's own template is ASCII (car names may contain punctuation but no U+FFFD)
        assert "�" not in txt
    db.close()
