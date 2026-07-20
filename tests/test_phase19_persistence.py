"""Phase 19 — campaign persistence (registry), age, efficiency assembly, migration idempotency."""
import inspect

import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.campaign_persistence import (
    CampaignRegistryEntry, registry_entry_from_campaign, campaign_age_days,
    build_engineering_efficiency, knowledge_versions, CAMPAIGN_PERSISTENCE_VERSION,
)


def _campaign(cid="camp_1", family="rotation", region="entry", status="active",
              progress=None, experiments=None):
    return {
        "identity": {"campaign_id": cid, "car": "Porsche 911 RSR", "track": "Fuji",
                     "layout": "fc", "discipline": "Race", "objective_family": family,
                     "objective_region": region, "gt7_version": "1.49"},
        "objective": {"title": f"Cure {family}", "completion_criteria": "confirmed twice"},
        "status": status,
        "experiments": experiments if experiments is not None else [
            {"candidate_id": "c1", "phase17_rank": 0, "engineering_value": 0.8,
             "campaign_role": "primary_discriminator", "outcome_state": "not_tested",
             "field": "arb_front", "attribution_scope": "single_field",
             "needs_further_testing": True}],
        "progress": progress or {"confirmed_improvement": 0, "regressions": 0,
                                 "inconclusive": 0, "unresolved_mechanisms": 1,
                                 "progress_pct": 0},
    }


# ---- registry entry -------------------------------------------------------- #
def test_registry_entry_from_campaign_stable_id():
    e = registry_entry_from_campaign(_campaign(), session_id="s1", recorded_at="2026-07-10")
    assert e.campaign_id == "camp_1"
    assert e.creation_session == "s1" and e.first_seen == e.last_seen == "2026-07-10"
    assert e.linked_experiments == ("c1",)
    assert e.manual_archive_flag is False and e.notes == ""


def test_registry_entry_row_round_trip():
    import json
    e = registry_entry_from_campaign(_campaign(), session_id="s1", recorded_at="2026-07-10")
    # a DB row stores the link columns as JSON strings and the archive flag as 0/1
    row = e.to_dict()
    row["linked_development_records"] = json.dumps(row["linked_development_records"])
    row["linked_experiments"] = json.dumps(row["linked_experiments"])
    row["linked_outcomes"] = json.dumps(row["linked_outcomes"])
    row["manual_archive_flag"] = 1 if row["manual_archive_flag"] else 0
    back = CampaignRegistryEntry.from_row(row)
    assert back.to_dict() == e.to_dict()


# ---- age (dates are data; no wall-clock) ----------------------------------- #
def test_campaign_age_days():
    assert campaign_age_days("2026-07-01", "2026-07-10") == 9
    assert campaign_age_days("2026-07-10", "2026-07-10") == 0
    assert campaign_age_days("", "2026-07-10") is None
    assert campaign_age_days("2026-07-10", "not-a-date") is None


# ---- efficiency assembly (pure) -------------------------------------------- #
def test_efficiency_assembly_composes_all_layers():
    prog = {"content_fingerprint": "fp0", "context_summary": {"car": "RSR"},
            "campaigns": [_campaign()]}
    reg = [registry_entry_from_campaign(_campaign(), session_id="s1",
                                        recorded_at="2026-07-01").to_dict()]
    eff = build_engineering_efficiency(prog, registry=reg,
                                       session_budget={"session_minutes_remaining": 60},
                                       now_date="2026-07-10").to_dict()
    c = eff["campaigns"][0]
    assert c["age_days"] == 9
    assert "saturation" in c and "experiment_costs" in c
    assert c["remaining_information_gain"] in ("high", "moderate", "low", "none")
    assert eff["budget"]["budget_known"] is True
    assert eff["knowledge_versions"]["campaign_persistence"] == CAMPAIGN_PERSISTENCE_VERSION
    assert eff["safety_statement"]


def test_efficiency_deterministic_fingerprint():
    prog = {"content_fingerprint": "fp0", "campaigns": [_campaign()]}
    a = build_engineering_efficiency(prog, registry=[], now_date="2026-07-10").to_dict()
    b = build_engineering_efficiency(prog, registry=[], now_date="2026-07-10").to_dict()
    assert a["content_fingerprint"] == b["content_fingerprint"]


def test_efficiency_saturation_independent_of_status():
    """Same evidence, different campaign status -> same saturation status in the view."""
    prog_active = {"campaigns": [_campaign(status="active",
                                           progress={"confirmed_improvement": 2},
                                           experiments=[])]}
    prog_freeze = {"campaigns": [_campaign(status="ready_to_freeze",
                                           progress={"confirmed_improvement": 2},
                                           experiments=[])]}
    a = build_engineering_efficiency(prog_active, now_date="2026-07-10").to_dict()
    b = build_engineering_efficiency(prog_freeze, now_date="2026-07-10").to_dict()
    assert a["campaigns"][0]["saturation"]["status"] == \
        b["campaigns"][0]["saturation"]["status"]


def test_efficiency_never_raises_on_garbage():
    for junk in (None, {}, {"campaigns": None}, {"campaigns": [None, 5]}):
        eff = build_engineering_efficiency(junk, now_date="2026-07-10")
        assert eff.safety_statement


# ---- DB registry write (idempotent, additive) ------------------------------ #
def _kw():
    return dict(car="Porsche 911 RSR", track="Fuji", layout_id="fc", discipline="Race")


def test_registry_write_idempotent_preserves_provenance(tmp_path):
    db = SessionDB(str(tmp_path / "r.db"))
    prog = {"campaigns": [_campaign()]}
    db.record_engineering_campaigns(prog, session_id="s1", recorded_at="2026-07-01")
    db.record_engineering_campaigns(prog, session_id="s2", recorded_at="2026-07-05")
    rows = db.get_campaign_registry(**_kw())
    assert len(rows) == 1
    r = rows[0]
    assert r["first_seen"] == "2026-07-01" and r["creation_session"] == "s1"
    assert r["last_seen"] == "2026-07-05"          # refreshed
    db.close()


def test_set_note_and_archive_preserved_on_rewrite(tmp_path):
    db = SessionDB(str(tmp_path / "n.db"))
    prog = {"campaigns": [_campaign()]}
    db.record_engineering_campaigns(prog, session_id="s1", recorded_at="2026-07-01")
    db.set_campaign_note("camp_1", notes="watch rear temps", manual_archive_flag=True)
    # re-record must NOT clobber the user-owned notes / archive flag
    db.record_engineering_campaigns(prog, session_id="s2", recorded_at="2026-07-09")
    r = db.get_campaign_registry(**_kw())[0]
    assert r["notes"] == "watch rear temps" and r["manual_archive_flag"] == 1
    db.close()


def test_registry_survives_restart(tmp_path):
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    db.record_engineering_campaigns({"campaigns": [_campaign()]}, session_id="s1",
                                    recorded_at="2026-07-01")
    db._conn.close()
    db2 = SessionDB(p)
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 27
    assert len(db2.get_campaign_registry(**_kw())) == 1
    db2.close()


# ---- migration idempotency ------------------------------------------------- #
def test_migration_v26_idempotent(tmp_path):
    p = str(tmp_path / "m.db")
    db = SessionDB(p)
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 27
    # running the migration again is a harmless no-op (IF NOT EXISTS everywhere)
    db._migrate_v26()
    db._migrate_v26()
    assert db._conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
        "AND name='engineering_campaign_registry'").fetchone()[0] == 1
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 27
    db.close()


def test_build_efficiency_optin_registry_capture(tmp_path):
    """build_engineering_efficiency writes NOTHING by default; with register_session_id it
    performs the single additive registry capture."""
    db = SessionDB(str(tmp_path / "o.db"))
    before = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0]
    db.build_engineering_efficiency(**_kw())            # no register_session_id -> read-only
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_campaign_registry").fetchone()[0] == before == 0
    db.close()


def test_no_forbidden_imports_persistence():
    src = inspect.getsource(__import__("strategy.campaign_persistence", fromlist=["x"]))
    for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                   "date.today", "time.time", "from data.session_db"):
        assert banned not in src
    assert set(knowledge_versions()) >= {"campaign_persistence", "evidence_saturation",
                                         "engineering_cost", "schema"}
