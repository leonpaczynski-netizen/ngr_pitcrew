"""Phase 45 — immutable context snapshot: serialization, persistence, immutability, reconstruction."""
import os
import tempfile

from strategy.engineering_context_snapshot import (
    build_context_snapshot, snapshots_semantically_equal, snapshot_semantic_digest,
    EngineeringContextSnapshotContent,
)
from strategy.historical_context_resolution import resolve_historical_context
from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION


_CONTENT = dict(driver="Leon", car="Porsche 911 RSR", car_variant="991", track="Fuji", layout_id="fc",
                event_id="E1", event_name="Fuji Practice", discipline="race", compound="RH",
                bop_state="off", tuning_permitted="yes", tyre_multiplier="5", fuel_multiplier="3",
                gt7_version="1.49", applied_setup_id="S1", applied_setup_fingerprint="sf1")


def _db(tmp_path, name="p"):
    return SessionDB(str(tmp_path / f"{name}.db"))


# ---- 3. canonical serialization + fingerprint ----------------------------------------------- #
def test_snapshot_deterministic_and_event_name_excluded():
    a = build_context_snapshot(_CONTENT)
    b = build_context_snapshot(dict(_CONTENT, event_name="Totally Different Display Name"))
    assert a.semantic_digest == b.semantic_digest   # display name is not semantic
    assert a.short_fingerprint.startswith("engineering_context_snapshot_v1:snap:")


def test_material_edit_changes_digest():
    a = snapshot_semantic_digest(_CONTENT)
    b = snapshot_semantic_digest(dict(_CONTENT, tyre_multiplier="8"))
    assert a != b


# ---- 4/5. persistence + immutability -------------------------------------------------------- #
def test_capture_persists_and_dedups(tmp_path):
    db = _db(tmp_path)
    r1 = db.capture_context_snapshot(_CONTENT, ref_kind="setup_experiment", ref_key="exp1",
                                     captured_at="2026-07-20T10:00:00Z")
    r2 = db.capture_context_snapshot(dict(_CONTENT, event_name="X"), ref_kind="experiment_outcome",
                                     ref_key="out1", captured_at="2026-07-20T11:00:00Z")
    assert r1["ok"] and r2["ok"] and r1["semantic_digest"] == r2["semantic_digest"]
    n = db._conn.execute("SELECT COUNT(*) FROM engineering_context_snapshots").fetchone()[0]
    assert n == 1   # content-addressed dedup
    db.close()


def test_snapshot_immutable_content(tmp_path):
    db = _db(tmp_path, "i")
    db.capture_context_snapshot(_CONTENT, ref_kind="session", ref_key="s1",
                                captured_at="2026-07-20T10:00:00Z")
    got = db.get_snapshot_for_ref("session", "s1")
    assert got["content"]["tyre_multiplier"] == "5"
    # a re-capture with the SAME digest but different display cannot change stored semantic content
    db.capture_context_snapshot(dict(_CONTENT, event_name="Y"), ref_kind="session", ref_key="s2",
                                captured_at="2026-07-20T12:00:00Z")
    again = db.get_snapshot_for_ref("session", "s1")
    assert again["content"]["tyre_multiplier"] == "5"
    db.close()


# ---- 6. semantic dedup / equivalence -------------------------------------------------------- #
def test_semantic_equivalence_across_db_instances(tmp_path):
    d1 = _db(tmp_path, "a"); d2 = _db(tmp_path, "b")
    r1 = d1.capture_context_snapshot(_CONTENT, ref_kind="session", ref_key="s1",
                                     captured_at="2026-07-20T10:00:00Z")
    r2 = d2.capture_context_snapshot(_CONTENT, ref_kind="session", ref_key="s1",
                                     captured_at="2026-07-20T20:00:00Z")   # different audit time
    assert r1["semantic_digest"] == r2["semantic_digest"]   # identical content across DBs
    d1.close(); d2.close()


# ---- 7. event-edit historical reconstruction proof ------------------------------------------ #
def test_event_edit_reconstruction(tmp_path):
    db = _db(tmp_path, "recon")
    # 1-2. event tyre x5 fuel x3 BoP off; capture the experiment's snapshot
    old = dict(_CONTENT, tyre_multiplier="5", fuel_multiplier="3", bop_state="off")
    db.capture_context_snapshot(old, ref_kind="setup_experiment", ref_key="exp_old",
                                captured_at="2026-07-20T10:00:00Z")
    # 3. event edited to tyre x8 fuel x5 BoP on; new evidence captured under the new conditions
    new = dict(_CONTENT, tyre_multiplier="8", fuel_multiplier="5", bop_state="on")
    db.capture_context_snapshot(new, ref_kind="setup_experiment", ref_key="exp_new",
                                captured_at="2026-07-20T14:00:00Z")
    # 4. historical evidence still resolves to tyre x5 fuel x3 BoP off
    old_res = db.resolve_historical_context("setup_experiment", "exp_old")["resolution"]
    old_by = {f["field"]: f["value"] for f in old_res["fields"]}
    assert old_by["tyre_multiplier"] == "5" and old_by["fuel_multiplier"] == "3" \
        and old_by["bop_state"] == "off"
    # 5. new evidence resolves to the new conditions
    new_res = db.resolve_historical_context("setup_experiment", "exp_new")["resolution"]
    new_by = {f["field"]: f["value"] for f in new_res["fields"]}
    assert new_by["tyre_multiplier"] == "8" and new_by["bop_state"] == "on"
    # 6. the two contexts are not the same snapshot (not merged as exact)
    assert old_res["semantic_digest"] != new_res["semantic_digest"]
    db.close()


# ---- 8. legacy record behaviour ------------------------------------------------------------- #
def test_legacy_record_without_snapshot_is_partial():
    res = resolve_historical_context(None, ref_kind="setup_experiment", ref_key="legacy")
    assert res.has_snapshot is False and res.confidence_cap == "legacy_partial"
    assert all(f["source"] == "unknown" for f in res.fields)
    # never fabricated
    assert res.known_count == 0


def test_missing_ref_resolves_unknown(tmp_path):
    db = _db(tmp_path, "miss")
    r = db.resolve_historical_context("setup_experiment", "does_not_exist")
    assert r["ok"] and r["resolution"]["has_snapshot"] is False
    db.close()


# ---- schema coherence ----------------------------------------------------------------------- #
def test_fresh_db_is_v27(tmp_path):
    db = _db(tmp_path, "v")
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 27
    db.close()


# ---- property: adding unknown legacy records cannot create exact context -------------------- #
def test_unknown_records_never_exact():
    for _ in range(10):
        r = resolve_historical_context(None, ref_key="x")
        assert r.confidence_cap != "exact"
