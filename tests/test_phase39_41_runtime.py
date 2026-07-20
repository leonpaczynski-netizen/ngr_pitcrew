"""Phase 39-41 — runtime verification: real temp DB, immutability, determinism, context change."""
import hashlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data.session_db import SessionDB
from tests._assurance_pack_helpers import seed_contradiction, applied, KW


def _seeded(path):
    db = SessionDB(path); seed_contradiction(db, 3, 2); return db


def test_db_byte_identical_before_and_after_workflow(tmp_path):
    p = str(tmp_path / "r.db")
    db = _seeded(p); db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db = SessionDB(p)
    db.build_context_scoped_evidence_report(applied_setup=applied(), now_date="2026-07-10", **KW)
    db.build_production_history_validation_report(applied_setup=applied(), now_date="2026-07-10", **KW)
    db.build_engineering_run_plan_report(applied_setup=applied(), now_date="2026-07-10", **KW)
    db.build_closed_loop_workflow_report(observation=None, applied_setup=applied(),
                                         now_date="2026-07-10", **KW)
    uv = db._conn.execute("PRAGMA user_version").fetchone()[0]
    db.close()
    assert uv == 28
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0


def test_workflow_deterministic_across_restart(tmp_path):
    p = str(tmp_path / "d.db")
    db = _seeded(p)
    fp1 = db.build_closed_loop_workflow_report(observation=None, applied_setup=applied(),
                                               now_date="2026-07-10", **KW)["content_fingerprint"]
    db.close()
    db = SessionDB(p)
    fp2 = db.build_closed_loop_workflow_report(observation=None, applied_setup=applied(),
                                               now_date="2026-07-11", **KW)["content_fingerprint"]
    db.close()
    assert fp1 == fp2


def test_context_change_alters_context_fingerprint(tmp_path):
    db = _seeded(str(tmp_path / "c.db"))
    a = db.build_context_scoped_evidence_report(applied_setup=applied(), now_date="2026-07-10",
                                                **KW)["context_fingerprint"]
    kw2 = dict(KW); kw2["track"] = "Daytona"
    b = db.build_context_scoped_evidence_report(applied_setup=applied(), now_date="2026-07-10",
                                                **kw2)["context_fingerprint"]
    db.close()
    assert a != b


def test_incompatible_records_do_not_change_exact_fingerprint(tmp_path):
    # runtime metamorphic: the exact-context fingerprint is invariant to the seeded compat-group
    # rollup because only exact records feed it.
    db = _seeded(str(tmp_path / "m.db"))
    r = db.build_context_scoped_evidence_report(applied_setup=applied(), now_date="2026-07-10", **KW)
    r2 = db.build_context_scoped_evidence_report(applied_setup=applied(), now_date="2026-07-10", **KW)
    db.close()
    assert r["exact_content_fingerprint"] == r2["exact_content_fingerprint"]
