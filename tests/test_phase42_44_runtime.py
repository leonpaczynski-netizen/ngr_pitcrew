"""Phase 42-44 — runtime verification: real temp DB, immutability, determinism."""
import hashlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data.session_db import SessionDB
from tests._assurance_pack_helpers import seed_contradiction, applied, KW


def _seeded(path):
    db = SessionDB(path); seed_contradiction(db, 3, 2); return db


def test_db_byte_identical_before_after_runtime_report(tmp_path):
    p = str(tmp_path / "r.db")
    db = _seeded(p); db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db = SessionDB(p)
    db.build_material_context_trust_report(applied_setup=applied(), now_date="2026-07-10", **KW)
    db.build_assisted_runtime_report(applied_setup=applied(), now_date="2026-07-10",
                                     now_monotonic=1.0, **KW)
    uv = db._conn.execute("PRAGMA user_version").fetchone()[0]
    db.close()
    assert uv == 26
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0


def test_runtime_report_deterministic_across_restart_and_clock(tmp_path):
    p = str(tmp_path / "d.db")
    db = _seeded(p)
    fp1 = db.build_assisted_runtime_report(applied_setup=applied(), now_date="2026-07-10",
                                           now_monotonic=1.0, **KW)["content_fingerprint"]
    db.close()
    db = SessionDB(p)
    fp2 = db.build_assisted_runtime_report(applied_setup=applied(), now_date="2026-07-11",
                                           now_monotonic=99999.0, **KW)["content_fingerprint"]
    db.close()
    assert fp1 == fp2   # restart + a different monotonic clock do not change the semantic fingerprint


def test_material_report_context_change_alters_fingerprint(tmp_path):
    db = _seeded(str(tmp_path / "c.db"))
    a = db.build_material_context_trust_report(applied_setup=applied(), now_date="2026-07-10",
                                               **KW)["context_fingerprint"]
    kw2 = dict(KW); kw2["track"] = "Daytona"
    b = db.build_material_context_trust_report(applied_setup=applied(), now_date="2026-07-10",
                                               **kw2)["context_fingerprint"]
    db.close()
    assert a != b


def test_user_version_stays_26(tmp_path):
    db = _seeded(str(tmp_path / "v.db"))
    db.build_assisted_runtime_report(applied_setup=applied(), now_date="2026-07-10",
                                     now_monotonic=1.0, **KW)
    uv = db._conn.execute("PRAGMA user_version").fetchone()[0]
    db.close()
    assert uv == 26
