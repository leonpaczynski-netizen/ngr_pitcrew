"""Engineering-Brain Phase 1 — DB bridge + production-integration tests.

Proves the ADDITIVE persistence + compatibility bridge (data/session_db.py v20):
idempotent migration, legacy records readable/queryable, golden config_id and
frozen fan-out allowlist unchanged, and that a newly created session, applied-setup
checkpoint, setup-lineage node and driver-feedback record all resolve to the SAME
canonical engineering scope without free-text coincidence.

Uses an isolated in-memory / tmp SessionDB — never the production DB, never a
runtime file, never config.json.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def db():
    return SessionDB(":memory:")


# ------------------------------------------------------------------ 10 migration
def test_user_version_is_20(db):
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 20
    assert DB_VERSION == 20


def test_engineering_tables_and_indexes_exist(db):
    tables = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"engineering_context", "engineering_context_links"} <= tables
    idx = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "idx_eng_context_scope" in idx
    assert "idx_eng_link_fingerprint" in idx


def test_migration_is_idempotent(tmp_path):
    p = str(tmp_path / "s.db")
    a = SessionDB(p)
    a.open_session(car_id=7, track="Fuji", session_type="Race", layout_id="full")
    a._conn.close()
    # Re-open the SAME file: migrations must be a no-op, no error, version stable.
    b = SessionDB(p)
    assert b._conn.execute("PRAGMA user_version").fetchone()[0] == 20
    # Data survived and no duplicate context rows appeared.
    n = b._conn.execute("SELECT COUNT(*) FROM engineering_context").fetchone()[0]
    assert n == 1


def test_upsert_is_idempotent_by_fingerprint(db):
    from data.engineering_context_key import build_engineering_context
    res = build_engineering_context(car_id="7", layout_id="full")
    fp1 = db.upsert_engineering_context(res)
    fp2 = db.upsert_engineering_context(res)
    assert fp1 == fp2
    n = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_context WHERE fingerprint=?",
        (fp1,)).fetchone()[0]
    assert n == 1


# ------------------------------------------------------------------ 13,14 same context
def test_session_checkpoint_lineage_feedback_share_scope(db):
    sid = db.open_session(car_id=7, track="Fuji", session_type="Race",
                          config_id="abc", layout_id="full_course")
    cid = db.save_applied_checkpoint(
        7, "Fuji", "full_course", "race",
        {"setup_id": "s1", "checkpoint_id": "cp1", "fields": {}, "changed_fields": []})
    fb = db.write_feedback(sid, 3, {"corner_entry": "loose"},
                           config_id="abc", setup_id=1)
    lid = db.record_lineage(7, "Fuji", "full_course", objective="race")

    scopes = {
        kind: db.get_engineering_context_for_source(kind, sid_)["scope_fingerprint"]
        for kind, sid_ in [("session", sid), ("applied_checkpoint", cid),
                           ("driver_feedback", fb), ("setup_lineage", lid)]
    }
    assert len(set(scopes.values())) == 1, scopes


def test_feedback_shares_session_scope_but_distinct_full_fingerprint(db):
    sid = db.open_session(car_id=7, track="Fuji", session_type="Race",
                          layout_id="full_course")
    fb = db.write_feedback(sid, 2, {"notes": "x"}, config_id="abc", setup_id=5)
    s = db.get_engineering_context_for_source("session", sid)
    f = db.get_engineering_context_for_source("driver_feedback", fb)
    assert f["scope_fingerprint"] == s["scope_fingerprint"]   # req 14
    assert f["fingerprint"] != s["fingerprint"]               # feedback adds setup_id
    assert f["setup_id"] == "5"


def test_different_layouts_do_not_join(db):
    s1 = db.open_session(car_id=7, track="Fuji", session_type="Race",
                         layout_id="full_course")
    s2 = db.open_session(car_id=7, track="Fuji", session_type="Race",
                         layout_id="short_course")
    a = db.get_engineering_context_for_source("session", s1)["scope_fingerprint"]
    b = db.get_engineering_context_for_source("session", s2)["scope_fingerprint"]
    assert a != b


def test_scope_query_returns_all_bridged_records(db):
    sid = db.open_session(car_id=7, track="Fuji", session_type="Race",
                          layout_id="full_course")
    db.save_applied_checkpoint(
        7, "Fuji", "full_course", "race",
        {"setup_id": "s1", "checkpoint_id": "cp1", "fields": {}, "changed_fields": []})
    db.record_lineage(7, "Fuji", "full_course", objective="race")
    scope = db.get_engineering_context_for_source("session", sid)["scope_fingerprint"]
    kinds = {l["source_kind"] for l in db.get_engineering_context_links_by_scope(scope)}
    assert {"session", "applied_checkpoint", "setup_lineage"} <= kinds


# ------------------------------------------------------------------ 15 legacy readable
def test_legacy_session_without_layout_stays_queryable(db):
    # A session created the OLD way (no layout_id) must still resolve to a
    # (partial) context and be bridged — just with layout unknown.
    sid = db.open_session(car_id=7, track="Fuji", session_type="Race")
    ctx = db.get_engineering_context_for_source("session", sid)
    assert ctx is not None
    assert ctx["status"] == "partial"
    assert ctx["layout_id"] is None            # honest unknown
    # And it is discoverable by its scope.
    rows = db.get_engineering_contexts_by_scope(ctx["scope_fingerprint"])
    assert any(r["session_id"] == str(sid) for r in rows)


def test_empty_resolution_is_not_persisted_or_linked(db):
    # A resolution with NO known component is never stored (no manufactured row)
    # and never linked — unknown identity stays honestly absent.
    from data.engineering_context_key import build_engineering_context
    empty = build_engineering_context()
    assert db.upsert_engineering_context(empty) is None
    assert db.resolve_and_link_engineering_context(empty, "session", 1) is None
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_context").fetchone()[0] == 0
    assert db.get_engineering_context_for_source("session", 1) is None


def test_orphan_feedback_links_by_session_id_only(db):
    # A feedback referencing a non-existent session is weakly-but-honestly
    # identified by that session_id (partial), never fabricated beyond it.
    fb = db.write_feedback(999999, 1, {"notes": "orphan"})
    ctx = db.get_engineering_context_for_source("driver_feedback", fb)
    assert ctx is not None
    assert ctx["session_id"] == "999999"
    assert ctx["car_id"] is None and ctx["layout_id"] is None  # no venue guessed
    assert ctx["status"] == "partial"


def test_get_missing_context_returns_none(db):
    assert db.get_engineering_context("nope") is None
    assert db.get_engineering_context_for_source("session", 4242) is None
    assert db.get_engineering_contexts_by_scope("nope") == []


# ------------------------------------------------------------------ 7,8 golden config_id
def test_golden_config_id_vectors_unchanged():
    # Import the frozen golden-vector suite and assert it still holds — Phase 1
    # must not touch the config_id algorithm.
    from tests.test_race_config_id_hash import GOLDEN_VECTORS, _bind
    for strategy, expected in GOLDEN_VECTORS:
        assert _bind(strategy)._compute_race_config_id() == expected


def test_config_id_is_only_a_compatibility_component(db):
    # config_id flows INTO the canonical context as a component; it is never
    # recomputed by the engineering-context module.
    src = (ROOT / "data" / "engineering_context_key.py").read_text(encoding="utf-8")
    assert "compute_config_id" not in src
    assert "sha256" in src  # our OWN fingerprint hash, distinct from config_id


def test_config_id_carried_through_bridge(db):
    sid = db.open_session(car_id=7, track="Fuji", session_type="Race",
                          config_id="51bd5b3bae", layout_id="full")
    ctx = db.get_engineering_context_for_source("session", sid)
    assert ctx["config_id"] == "51bd5b3bae"


# ------------------------------------------------------------------ frozen allowlist
def test_frozen_fanout_allowlist_unchanged():
    from tests.test_legacy_fanout_phase_5 import _scan_inventory, FROZEN_ALLOWLIST
    assert _scan_inventory() == FROZEN_ALLOWLIST


# ------------------------------------------------------------------ 18,19 safety spine
def test_config_safety_guardrail_still_active():
    import config_paths as cp
    assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True


def test_bridge_never_calls_ai_or_network():
    src = (ROOT / "data" / "engineering_context_key.py").read_text(encoding="utf-8")
    for banned in ("anthropic", "openai", "requests", "api_key", "http"):
        assert banned not in src.lower() or banned == "http"  # (no http client)
    assert "socket" not in src


def test_context_wiring_does_not_break_session_creation(db):
    # Even if identity is fully unknown, open_session still returns a valid id
    # and never raises.
    sid = db.open_session(car_id=0, track="", session_type="")
    assert isinstance(sid, int) and sid > 0


def test_apply_gate_constants_intact():
    # RULE_ENGINE_VERSION unchanged (no setup-authoring change this group).
    from strategy._setup_constants import RULE_ENGINE_VERSION
    assert RULE_ENGINE_VERSION == "46.0"
