"""Phase 24 — golden UAT + real SessionDB production path + restart determinism.

Deterministic fixtures across the required scenarios; read-only; writes nothing; DB stays v26.
"""
import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.development_history import MemoryContextKey, build_development_record
from data.applied_checkpoint import compute_setup_hash

PORSCHE = "Porsche 911 RSR (991) '17"
CUP = "Porsche 911 GT3 Cup"
TOY = "Toyota GR Supra Racing Concept Gr.3"
FIELDS = {"arb_front": 4, "lsd_accel": 20, "springs_front": 5.0, "brake_bias": 0}


def applied(car=PORSCHE):
    d = {"car": car, "track": "Fuji", "layout_id": "fc", "setup_id": "S1", "name": "B",
         "revision": 1, "state": "applied", "fields": dict(FIELDS), "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


def _kw(car=PORSCHE, track="Fuji", discipline="Race", gt7="1.49"):
    return dict(car=car, track=track, layout_id="fc", discipline=discipline, driver="leon",
                gt7_version=gt7, compound="RH")


def _seed(db, car, track, discipline, status, at, sess, field, family, issue, gt7="1.49"):
    ctx = MemoryContextKey(driver="leon", car=car, track=track, layout_id="fc",
                           discipline=discipline, gt7_version=gt7, compound="RH")
    residuals = [{"issue_key": f"k{sess}", "family": family, "issue_type": issue, "axle": "rear",
                  "phase": "exit", "segment_id": "T1", "corner_name": "T1",
                  "residual_state": "improved_but_present", "is_new": False, "is_regression": False,
                  "still_present": True, "protected_good": False, "confidence": "high"}]
    outcome = {"id": f"o{sess}", "experiment_id": 10, "status": status, "confidence_level": "high",
               "scope_fingerprint": "sf", "test_session_id": sess, "protected": [],
               "failed_directions": []}
    exp = {"id": 10, "scope_fingerprint": "sf",
           "changes": [{"field": field, "from_value": "20", "to_value": "25"}]}
    rec = build_development_record(outcome, exp, context=ctx, scope_fingerprint="sf",
                                  working_windows=[], residuals=residuals, recorded_at=at,
                                  session_date=at[:10])
    db._persist_development_record(rec, created_at=rec.recorded_at)


# Scenario 1: same driver, related Porsche programmes — established knowledge, supported transfer.
def test_scenario_1_related_porsche_supported(tmp_path):
    db = SessionDB(str(tmp_path / "1.db"))
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-01T10:00", "s1",
          "lsd_accel", "traction", "wheelspin")
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-02T10:00", "s2",
          "lsd_accel", "traction", "wheelspin")
    _seed(db, CUP, "Spa", "Race", "confirmed_improvement", "2026-07-03T10:00", "s3",
          "arb_front", "rotation", "entry_understeer")
    r = db.build_programme_engineering_playbook(applied_setup=applied(), now_date="2026-07-06",
                                                **_kw())
    assert r["ok"] and r["theme_count"] >= 1
    pb = r["playbook"]
    assert pb["stable_themes"]
    # a reusable theme to the related Porsche exists, with a confirmed-good protection present
    assert pb["global_stable_summary"]["confirmed_good_themes"] >= 1
    assert any(t["compatible_target_programmes"] for t in pb["stable_themes"])
    db.close()


# Scenario 2: Porsche source to unrelated Toyota Gr.3 — low/non-transferable, isolation.
def test_scenario_2_unrelated_toyota_isolated(tmp_path):
    db = SessionDB(str(tmp_path / "2.db"))
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-01T10:00", "s1",
          "lsd_accel", "traction", "wheelspin")
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-02T10:00", "s2",
          "lsd_accel", "traction", "wheelspin")
    _seed(db, TOY, "Spa", "Race", "confirmed_improvement", "2026-07-03T10:00", "s3",
          "arb_front", "rotation", "entry_understeer")
    r = db.build_programme_engineering_playbook(applied_setup=applied(), now_date="2026-07-06",
                                                **_kw())
    pb = r["playbook"]
    toy_brief = next((b for b in pb["new_programme_briefs"]
                      if b["target_programme"]["car"] == TOY), None)
    assert toy_brief is not None
    # no reusable knowledge to the unrelated Toyota + no setup-copy implication
    assert toy_brief["eligible_for_cautious_reuse"] == []
    assert "No setup values" in toy_brief["no_setup_statement"]
    db.close()


# Scenario 4: unknown car attributes — conservative, unknown shown explicitly.
def test_scenario_4_unknown_attributes(tmp_path):
    db = SessionDB(str(tmp_path / "4.db"))
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-01T10:00", "s1",
          "lsd_accel", "traction", "wheelspin")
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-02T10:00", "s2",
          "lsd_accel", "traction", "wheelspin")
    _seed(db, "Some Unlisted Prototype", "Spa", "Race", "confirmed_improvement",
          "2026-07-03T10:00", "s3", "arb_front", "rotation", "entry_understeer")
    r = db.build_programme_engineering_playbook(applied_setup=applied(), now_date="2026-07-06",
                                                **_kw())
    pb = r["playbook"]
    assert any(b["boundary_type"] == "unknown_vehicle_attribute"
               for b in pb["knowledge_boundaries"])
    db.close()


# Scenario 5: contradictory evidence — no false 'established' theme. A regression on a direction
# retires it (Phase-17 authority), so a contradicted domain is never fabricated as confirmed-good;
# a separate clean domain still survives, proving reduced certainty is honest, not averaged.
def test_scenario_5_contradictory_evidence(tmp_path):
    db = SessionDB(str(tmp_path / "5.db"))
    # clean, established domain (differential via lsd_accel, two confirmations)
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-01T10:00", "s1",
          "lsd_accel", "traction", "wheelspin")
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-02T10:00", "s2",
          "lsd_accel", "traction", "wheelspin")
    # contradicted domain (rotation/arb: a confirmation then a regression on the same direction)
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-03T10:00", "s3",
          "arb_front", "rotation", "entry_understeer")
    _seed(db, PORSCHE, "Fuji", "Race", "regression", "2026-07-04T10:00", "s4",
          "arb_front", "rotation", "entry_understeer")
    r = db.build_programme_engineering_playbook(applied_setup=applied(), now_date="2026-07-06",
                                                **_kw())
    pb = r["playbook"]
    assert pb is not None and r["theme_count"] >= 1
    domains = {t["engineering_domain"] for t in pb["stable_themes"]}
    # the clean differential knowledge survives as an established theme
    assert "differential" in domains
    # the contradicted rotation-derived domains are NOT fabricated as confirmed-good themes
    for t in pb["stable_themes"]:
        if t["engineering_domain"] in ("anti_roll_bars", "vehicle_balance"):
            assert not t["confirmed_good_protections"], "contradicted domain must not be confirmed-good"
    # determinism holds under contradiction
    r2 = db.build_programme_engineering_playbook(applied_setup=applied(), now_date="2026-07-06",
                                                 **_kw())
    assert r["content_fingerprint"] == r2["content_fingerprint"]
    db.close()


# Scenario 6: empty + single-context DB.
def test_scenario_6_empty_and_single(tmp_path):
    db = SessionDB(":memory:")
    r = db.build_programme_engineering_playbook(car=PORSCHE, track="Fuji", discipline="Race")
    assert r["ok"] and r["theme_count"] == 0 and r["playbook"] is None
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 28
    db.close()

    db2 = SessionDB(str(tmp_path / "single.db"))
    _seed(db2, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-01T10:00", "s1",
          "lsd_accel", "traction", "wheelspin")
    r2 = db2.build_programme_engineering_playbook(applied_setup=applied(), now_date="2026-07-06",
                                                  **_kw())
    # single programme -> no other groups -> no target briefs, no fabricated targets
    pb = r2["playbook"]
    if pb:
        assert pb["new_programme_briefs"] == []
    db2.close()


# --- production integrity ---------------------------------------------------
def _multi(db):
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-01T10:00", "s1",
          "lsd_accel", "traction", "wheelspin")
    _seed(db, PORSCHE, "Fuji", "Race", "confirmed_improvement", "2026-07-02T10:00", "s2",
          "lsd_accel", "traction", "wheelspin")
    _seed(db, TOY, "Spa", "Race", "confirmed_improvement", "2026-07-03T10:00", "s3",
          "arb_front", "rotation", "entry_understeer")


def test_production_writes_nothing(tmp_path):
    db = SessionDB(str(tmp_path / "p.db"))
    _multi(db)
    counts = {}
    for tbl in ("engineering_development_records", "setup_experiments",
                "engineering_campaign_registry", "setup_history"):
        try:
            counts[tbl] = db._conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        except Exception:
            counts[tbl] = None
    db.build_programme_engineering_playbook(applied_setup=applied(), now_date="2026-07-06", **_kw())
    for tbl, before in counts.items():
        if before is None:
            continue
        assert db._conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0] == before
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 28
    db.close()


def test_production_restart_determinism(tmp_path):
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    _multi(db)
    r1 = db.build_programme_engineering_playbook(applied_setup=applied(), now_date="2026-07-06",
                                                 **_kw())
    db._conn.close()
    db2 = SessionDB(p)
    r2 = db2.build_programme_engineering_playbook(applied_setup=applied(), now_date="2026-07-06",
                                                  **_kw())
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 28
    db2._conn.close()
