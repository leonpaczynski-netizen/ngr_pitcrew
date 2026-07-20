"""Phase 18 — golden UAT scenarios A-D + real SessionDB production path + restart."""
import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.development_history import MemoryContextKey, build_development_record
from strategy.mechanism_annotation import annotate_diagnosis
from strategy.intervention_hypothesis import build_intervention_hypotheses as BIH
from strategy.experiment_synthesis import synthesize_from_report
from strategy.experiment_portfolio import build_portfolio
from strategy.engineering_campaign import CampaignStatus, CampaignRole, build_campaign_programme
from strategy.setup_ranges import resolve_ranges
from data.applied_checkpoint import compute_setup_hash

RANGES = dict(resolve_ranges("Porsche 911 RSR"))
IDENT = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc"}
SCOPE = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "discipline": "Race",
         "driver": "leon", "gt7_version": "1.49"}
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0,
          "springs_rear": 5.0, "lsd_accel": 20, "lsd_decel": 20, "aero_front": 300,
          "toe_front": 0.10, "dampers_rear_ext": 5}


def applied():
    d = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "setup_id": "S1",
         "name": "Base", "revision": 1, "state": "applied", "fields": dict(FIELDS),
         "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


def _ann(fam, it, ax, ph, key):
    return annotate_diagnosis({"issue_family": fam, "issue_type": it, "axle": ax, "phase": ph,
                              "segment_id": "T1", "residual_state": "unchanged",
                              "recurring": True, "valid_laps": 4, "sessions_seen": 2,
                              "telemetry_available": True, "key": key})


def _prog(diags, outcome_history=None, active=None):
    hsets = [BIH(_ann(*d).to_dict()).to_dict() for d in diags]
    rep = synthesize_from_report({"ok": True, "hypothesis_sets": hsets}, applied_setup=applied(),
                                 session_identity=IDENT, ranges=RANGES)
    port = build_portfolio(rep, outcome_history=outcome_history).to_dict()
    return build_campaign_programme(port, scope=SCOPE, active_context=active or SCOPE,
                                    outcome_history=outcome_history)


# Scenario A: rear braking instability, competing mechanisms, successful intervention,
# validation not yet complete -> one campaign, VALIDATION_REQUIRED, not completed.
def test_scenario_A_rear_braking_validation_required():
    p = _prog([("braking", "rear_loose_under_braking", "rear", "braking", "dA")],
              outcome_history=[{"fields": ["lsd_decel"], "direction": "increase",
                                "outcome_status": "confirmed_improvement", "session_id": "s1"}])
    braking = [c for c in p.campaigns if c["identity"]["objective_family"] == "braking"]
    assert len(braking) == 1
    c = braking[0]
    assert c["status"] == CampaignStatus.VALIDATION_REQUIRED.value
    assert c["progress"]["confirmed_improvement"] >= 1
    assert c["progress"]["progress_pct"] < 100      # validation stage still open
    # not an Apply claim
    assert "applied" not in c["next_action"].lower() or "apply gate" not in c["next_action"].lower()


# Scenario B: exit wheelspin, a prior experiment caused regression, alternative exists ->
# failed direction retired/obsolete, regression visible, progress not inflated.
def test_scenario_B_exit_traction_regression_history():
    # a prior LSD-accel increase regressed; that exact (field, direction) is a wheelspin
    # candidate, so Phase 17 retires it and the campaign shows the failed direction.
    p = _prog([("traction", "wheelspin", "rear", "exit", "dB")],
              outcome_history=[{"fields": ["lsd_accel"], "direction": "increase",
                                "outcome_status": "regression", "session_id": "s1"}])
    traction = [c for c in p.campaigns if c["identity"]["objective_family"] == "traction"][0]
    # regression visible
    assert traction["progress"]["regressions"] >= 1
    # progress does not inflate merely because an experiment ran
    assert traction["progress"]["progress_pct"] < 60
    # the failed lsd_accel direction is retired/visible (retained, not dropped)
    lsd = [e for e in traction["experiments"] if e["field"] == "lsd_accel"]
    assert lsd and (lsd[0]["retirement_state"] or lsd[0]["outcome_state"] == "regression")
    # an alternative legal experiment remains
    assert any(e["campaign_role"] != CampaignRole.RETIRED.value for e in traction["experiments"])


# Scenario C: confirmed campaign, validation repeated across two sessions ->
# READY_TO_FREEZE or COMPLETED, roadmap points at the existing freeze authority.
def test_scenario_C_confirmed_campaign_ready_to_freeze():
    p = _prog([("rotation", "entry_understeer", "front", "entry", "dC")],
              outcome_history=[{"fields": ["arb_front"], "direction": "decrease",
                                "outcome_status": "confirmed_improvement", "session_id": "s1"},
                               {"fields": ["arb_front"], "direction": "decrease",
                                "outcome_status": "confirmed_improvement", "session_id": "s2"}])
    c = p.campaigns[0]
    assert c["status"] in (CampaignStatus.READY_TO_FREEZE.value, CampaignStatus.COMPLETED.value)
    freeze_stage = [s for s in c["stages"] if s["stage_type"] == "freeze"][0]
    assert "existing" in freeze_stage["advisory_next_action"].lower() or \
        "authority" in freeze_stage["advisory_next_action"].lower()


# Scenario D: stale campaign (active context changed materially).
def test_scenario_D_stale_campaign():
    p = _prog([("rotation", "entry_understeer", "front", "entry", "dD")],
              active={**SCOPE, "discipline": "Qualifying", "track": "Spa"})
    assert all(c["status"] == CampaignStatus.STALE.value for c in p.campaigns)
    # context mismatch explained; evidence retained; no executable recommendation
    assert any("track" in b or "discipline" in b for b in p.programme_blockers)
    for c in p.campaigns:
        assert "do not execute" in c["next_action"].lower()


# --- real production path (DB) ----------------------------------------------
CTX = MemoryContextKey(driver="leon", car="Porsche 911 RSR", track="Fuji", layout_id="fc",
                       discipline="Race", gt7_version="1.49", compound="RH")


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


def _kw():
    return dict(car="Porsche 911 RSR", track="Fuji", layout_id="fc", discipline="Race",
                driver="leon", gt7_version="1.49", compound="RH")


def test_production_path_multi_session(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    _seed(db, [{"field": "arb_front", "from_value": "5", "to_value": "4"}],
          "confirmed_improvement", "2026-07-01T10:00", "s1")
    r = db.build_engineering_campaign_programme(applied_setup=applied(), session_identity=IDENT,
                                                **_kw())
    assert r["ok"] and r["campaign_count"] >= 1
    prog = r["programme"]
    assert prog["campaigns"][0]["progress"]["confirmed_improvement"] >= 1
    # nothing written
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == 1
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == 0
    db.close()


def test_production_restart_determinism(tmp_path):
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    _seed(db, [{"field": "arb_front", "from_value": "5", "to_value": "4"}],
          "confirmed_improvement", "2026-07-01T10:00", "s1")
    r1 = db.build_engineering_campaign_programme(applied_setup=applied(), session_identity=IDENT,
                                                 **_kw())
    db._conn.close()
    db2 = SessionDB(p)
    r2 = db2.build_engineering_campaign_programme(applied_setup=applied(), session_identity=IDENT,
                                                  **_kw())
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 28
    db2._conn.close()


def test_empty_db_safe():
    db = SessionDB(":memory:")
    r = db.build_engineering_campaign_programme(car="Porsche 911 RSR", track="Fuji",
                                                discipline="Race")
    assert r["ok"] and r["campaign_count"] == 0
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 28
    db.close()
