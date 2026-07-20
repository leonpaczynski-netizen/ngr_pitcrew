"""Phase 36-38 — runtime verification: real temp DB, determinism, DB immutability, no write."""
import hashlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data.session_db import SessionDB
from tests._assurance_pack_helpers import seed_contradiction, applied, KW


def _seeded(path):
    db = SessionDB(path)
    seed_contradiction(db, 3, 2)
    return db


def test_db_byte_identical_before_and_after_brief(tmp_path):
    p = str(tmp_path / "r.db")
    db = _seeded(p); db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db = SessionDB(p)
    r = db.build_race_engineer_team_brief(applied_setup=applied(), now_date="2026-07-10", **KW)
    uv = db._conn.execute("PRAGMA user_version").fetchone()[0]
    db.close()
    assert r["ok"] and uv == 27
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0


def test_brief_deterministic_across_restart(tmp_path):
    p = str(tmp_path / "d.db")
    db = _seeded(p)
    fp1 = db.build_race_engineer_team_brief(applied_setup=applied(), now_date="2026-07-10",
                                            **KW)["content_fingerprint"]
    db.close()
    db = SessionDB(p)
    fp2 = db.build_race_engineer_team_brief(applied_setup=applied(), now_date="2026-07-11",
                                            **KW)["content_fingerprint"]
    db.close()
    assert fp1 == fp2  # wall-clock now_date does not affect the fingerprint


def test_exact_evidence_classified_from_real_records(tmp_path):
    db = _seeded(str(tmp_path / "e.db"))
    r = db.build_race_engineer_team_brief(applied_setup=applied(), now_date="2026-07-10", **KW)
    db.close()
    assert r["ok"] and r["exact_evidence_count"] == 5  # 3 confirm + 2 regress, all Fuji/Race exact
    assert r["completeness"] in ("sufficient", "complete")


def test_context_change_alters_fingerprint(tmp_path):
    db = _seeded(str(tmp_path / "c.db"))
    a = db.build_race_engineer_team_brief(applied_setup=applied(), now_date="2026-07-10",
                                          **KW)["context_fingerprint"]
    # a different current track (session identity) => a different context fingerprint.
    kw2 = dict(KW); kw2["track"] = "Daytona"
    b = db.build_race_engineer_team_brief(applied_setup=applied(), now_date="2026-07-10",
                                          **kw2)["context_fingerprint"]
    db.close()
    assert a != b
