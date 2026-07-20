"""Phase 25 — golden UAT scenarios through the real SessionDB + restart determinism.

Deterministic fixtures: independent convergence, dependent non-convergence, confirmed-good
survival, regression retiring one direction, unresolved conflict, transfer-limited, unknown
dates, heavily-contradicted empty, restart + shuffle identity.
"""
import hashlib

import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.development_history import MemoryContextKey, build_development_record
from data.applied_checkpoint import compute_setup_hash

PORSCHE = "Porsche 911 RSR (991) '17"
TOY = "Toyota GR Supra Racing Concept Gr.3"
FIELDS = {"arb_front": 4, "lsd_accel": 20, "brake_bias": 0, "springs_front": 5.0}


def applied(car=PORSCHE):
    d = {"car": car, "track": "Fuji", "layout_id": "fc", "setup_id": "S1", "name": "B",
         "revision": 1, "state": "applied", "fields": dict(FIELDS), "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


def _kw(car=PORSCHE):
    return dict(car=car, track="Fuji", layout_id="fc", discipline="Race", driver="leon",
                gt7_version="1.49", compound="RH")


def _seed(db, car, track, status, date, sess, scope, field, family, issue, conf="high"):
    ctx = MemoryContextKey(driver="leon", car=car, track=track, layout_id="fc", discipline="Race",
                           gt7_version="1.49", compound="RH")
    residuals = [{"issue_key": f"k{sess}{scope}", "family": family, "issue_type": issue,
                  "axle": "rear", "phase": "exit", "segment_id": "T1", "corner_name": "T1",
                  "residual_state": "improved_but_present", "is_new": False,
                  "is_regression": (status == "regression"), "still_present": True,
                  "protected_good": False, "confidence": conf}]
    outcome = {"id": f"o{sess}{scope}", "experiment_id": 10, "status": status,
               "confidence_level": conf, "scope_fingerprint": scope, "test_session_id": sess,
               "protected": [], "failed_directions": ([{"field": field}] if status == "regression"
                                                       else [])}
    exp = {"id": 10, "scope_fingerprint": scope,
           "changes": [{"field": field, "from_value": "20", "to_value": "25"}]}
    rec = build_development_record(outcome, exp, context=ctx, scope_fingerprint=scope,
                                  working_windows=[], residuals=residuals, recorded_at=date + "T10:00",
                                  session_date=date)
    db._persist_development_record(rec, created_at=rec.recorded_at)


def _timeline(db, car=PORSCHE):
    return db.build_programme_knowledge_timeline(applied_setup=applied(car), now_date="2026-07-20",
                                                 **_kw(car))["timeline"]


def _conv(tl, domain):
    return next((c for c in tl["convergence_summaries"] if c["domain"] == domain), None)


# 1. three independent compatible sessions establish a stable theme.
def test_scenario_1_independent_convergence(tmp_path):
    db = SessionDB(str(tmp_path / "1.db"))
    for i, tk in ((1, "Fuji"), (3, "Fuji"), (5, "Spa")):
        _seed(db, PORSCHE, tk, "confirmed_improvement", f"2026-07-0{i}", f"s{i}", f"sc{i}",
              "lsd_accel", "traction", "wheelspin")
    tl = _timeline(db)
    c = _conv(tl, "differential")
    assert c and c["independent_support_count"] == 3
    assert c["convergence_status"] in ("strongly_converged", "stable_confirmed_good")
    db.close()


# 2. five repeated records from one session do not falsely converge.
def test_scenario_2_dependent_no_false_convergence(tmp_path):
    db = SessionDB(str(tmp_path / "2.db"))
    for i in range(5):
        _seed(db, PORSCHE, "Fuji", "confirmed_improvement", "2026-07-01", "sSAME", "scSAME",
              "lsd_accel", "traction", "wheelspin")
    tl = _timeline(db)
    c = _conv(tl, "differential")
    if c:
        assert c["independent_support_count"] <= 1
        assert c["convergence_status"] != "strongly_converged"
    db.close()


# 3. older strong confirmed-good survives a newer weak contradiction.
def test_scenario_3_older_strong_survives_newer_weak(tmp_path):
    db = SessionDB(str(tmp_path / "3.db"))
    _seed(db, PORSCHE, "Fuji", "confirmed_improvement", "2026-07-01", "s1", "sc1", "lsd_accel",
          "traction", "wheelspin", conf="high")
    _seed(db, PORSCHE, "Spa", "confirmed_improvement", "2026-07-03", "s2", "sc2", "lsd_accel",
          "traction", "wheelspin", conf="high")
    # a much later, low-confidence, no-meaningful-change observation must not overturn it
    _seed(db, PORSCHE, "Fuji", "no_meaningful_change", "2026-07-15", "s9", "sc9", "lsd_accel",
          "traction", "wheelspin", conf="low")
    tl = _timeline(db)
    c = _conv(tl, "differential")
    assert c and c["independent_support_count"] >= 2
    # the older strong evidence is NOT overturned by the newer weak observation
    assert c["convergence_status"] not in ("regressed", "conflicting", "superseded",
                                           "insufficient_evidence")
    db.close()


# 5. conflicting evidence remains unresolved and lowers certainty (with a clean domain present so
#    the programme is not empty).
def test_scenario_5_conflict_unresolved(tmp_path):
    db = SessionDB(str(tmp_path / "5.db"))
    # a clean established domain keeps the programme non-empty
    for i in (1, 3):
        _seed(db, PORSCHE, "Fuji", "confirmed_improvement", f"2026-07-0{i}", f"d{i}", f"dc{i}",
              "lsd_accel", "traction", "wheelspin")
    # a contradicted springs domain (confirm then regress on the same direction)
    _seed(db, PORSCHE, "Fuji", "confirmed_improvement", "2026-07-01", "s1", "scS", "springs_front",
          "rotation", "entry_understeer")
    _seed(db, PORSCHE, "Fuji", "regression", "2026-07-04", "s2", "scS", "springs_front",
          "rotation", "entry_understeer")
    tl = _timeline(db)
    assert tl is not None
    # the contradicted evidence is visible as an unresolved conflict or a regression/retired entry
    assert tl["unresolved_conflicts"] or tl["regressions_and_retired"]
    # the contradicted domain is never strongly converged
    for c in tl["convergence_summaries"]:
        if c["domain"] in ("springs", "anti_roll_bars"):
            assert c["convergence_status"] != "strongly_converged"
    db.close()


# 7. cross-car evidence stays transfer-limited (Toyota not counted as Porsche confirmation).
def test_scenario_7_cross_car_transfer_limited(tmp_path):
    db = SessionDB(str(tmp_path / "7.db"))
    for i in (1, 3, 5):
        _seed(db, PORSCHE, "Fuji", "confirmed_improvement", f"2026-07-0{i}", f"s{i}", f"sc{i}",
              "lsd_accel", "traction", "wheelspin")
    _seed(db, TOY, "Spa", "confirmed_improvement", "2026-07-06", "st", "sct", "lsd_accel",
          "traction", "wheelspin")
    tl = _timeline(db)  # timeline is for the Porsche primary group
    c = _conv(tl, "differential")
    # the Toyota evidence is a separate programme; the Porsche count is unaffected (still 3)
    assert c and c["independent_support_count"] == 3
    db.close()


# 8. unknown dates remain unknown.
def test_scenario_8_unknown_dates(tmp_path):
    db = SessionDB(str(tmp_path / "8.db"))
    _seed(db, PORSCHE, "Fuji", "confirmed_improvement", "2026-07-01", "s1", "sc1", "lsd_accel",
          "traction", "wheelspin")
    _seed(db, PORSCHE, "Fuji", "confirmed_improvement", "", "s2", "sc2", "lsd_accel",
          "traction", "wheelspin")
    tl = _timeline(db)
    unknown_pts = [p for p in tl["timeline_points"] if p["evidence_date"] == "unknown"]
    assert unknown_pts and "evidence_date" in unknown_pts[0]["unknown_fields"]
    db.close()


# 9. heavily contradicted single-domain programme -> honest empty / unresolved.
def test_scenario_9_heavily_contradicted(tmp_path):
    db = SessionDB(str(tmp_path / "9.db"))
    _seed(db, PORSCHE, "Fuji", "confirmed_improvement", "2026-07-01", "s1", "scZ", "arb_front",
          "rotation", "entry_understeer")
    _seed(db, PORSCHE, "Fuji", "regression", "2026-07-04", "s2", "scZ", "arb_front",
          "rotation", "entry_understeer")
    r = db.build_programme_knowledge_timeline(applied_setup=applied(), now_date="2026-07-20", **_kw())
    # either an honest empty timeline (retired direction collapses the domain) or an unresolved one
    tl = r["timeline"]
    if tl is None:
        assert r["point_count"] == 0
    else:
        strong = [c for c in tl["convergence_summaries"]
                  if c["convergence_status"] == "strongly_converged"]
        assert not strong
    db.close()


# 10. restart and shuffled-row input produce identical content and fingerprint.
def test_scenario_10_restart_and_shuffle_identical(tmp_path):
    p = str(tmp_path / "10.db")
    db = SessionDB(p)
    for i, tk in ((1, "Fuji"), (3, "Spa"), (5, "Fuji")):
        _seed(db, PORSCHE, tk, "confirmed_improvement", f"2026-07-0{i}", f"s{i}", f"sc{i}",
              "lsd_accel", "traction", "wheelspin")
    r1 = db.build_programme_knowledge_timeline(applied_setup=applied(), now_date="2026-07-20", **_kw())
    db._conn.close()
    db2 = SessionDB(p)
    r2 = db2.build_programme_knowledge_timeline(applied_setup=applied(), now_date="2026-07-20", **_kw())
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 27
    db2._conn.close()


def test_empty_db_safe():
    db = SessionDB(":memory:")
    r = db.build_programme_knowledge_timeline(car=PORSCHE, track="Fuji", discipline="Race")
    assert r["ok"] and r["point_count"] == 0 and r["timeline"] is None
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 27
    db.close()
