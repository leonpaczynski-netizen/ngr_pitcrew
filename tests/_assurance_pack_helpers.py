"""Shared helpers for the Phase 33-35 Assurance Review Pack tests (not collected by pytest)."""
from __future__ import annotations

import os

from strategy.assurance_chain_export import build_assurance_chain_export
from strategy.assurance_chain_serialization import content_digest, recomputed_content_digest

PORSCHE = "Porsche 911 RSR (991) '17"
FIELDS = {"arb_front": 4, "lsd_accel": 20}
KW = dict(car=PORSCHE, track="Fuji", layout_id="fc", discipline="Race", driver="d",
          gt7_version="1", compound="RH")


def applied():
    from data.applied_checkpoint import compute_setup_hash
    d = {"car": PORSCHE, "track": "Fuji", "layout_id": "fc", "setup_id": "S1", "name": "B",
         "revision": 1, "state": "applied", "fields": dict(FIELDS), "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


def _mk(db, key, outcome, i, fam="rotation", field="arb_front"):
    from strategy.development_history import MemoryContextKey, build_development_record
    ctx = MemoryContextKey(driver="d", car=PORSCHE, track="Fuji", layout_id="fc", discipline="Race",
                           gt7_version="1", compound="RH")
    rec = build_development_record(
        {"id": key, "experiment_id": 100 + i, "status": outcome, "confidence_level": "high",
         "scope_fingerprint": f"sf{key}", "test_session_id": f"s{key}", "protected": [],
         "failed_directions": []},
        {"id": 100 + i, "scope_fingerprint": f"sf{key}", "changes": [{"field": field}]},
        context=ctx, scope_fingerprint=f"sf{key}", working_windows=[],
        residuals=[{"issue_key": f"k{key}", "family": fam, "issue_type": "entry_understeer",
                    "axle": "front", "phase": "entry", "segment_id": f"T{i}", "corner_name": f"T{i}",
                    "residual_state": "unchanged", "is_new": False,
                    "is_regression": outcome == "regression", "still_present": True,
                    "protected_good": False, "confidence": "high"}],
        recorded_at=f"2026-07-0{1 + (i % 8)}T10:00", session_date=f"2026-07-0{1 + (i % 8)}")
    db._persist_development_record(rec, created_at=rec.recorded_at)


def seed_contradiction(db, n_confirm=3, n_regress=2):
    fams = ["rotation", "traction", "braking"]
    for i in range(n_confirm):
        _mk(db, f"c{i}", "confirmed_improvement", i, fam=fams[i % 3])
    for i in range(n_regress):
        _mk(db, f"r{i}", "regression", i + 3, fam="rotation")


def seed_negative_only(db, n=3):
    for i in range(n):
        _mk(db, f"neg{i}", "regression", i)


def real_products_and_context(db):
    return db._assurance_chain_products(applied_setup=applied(), now_date="2026-07-10", **KW)


def real_export(db):
    products, ctx = real_products_and_context(db)
    if products is None:
        return None
    return build_assurance_chain_export(products, ctx).to_dict()


# ---- synthetic products (fast, deterministic) -----------------------------------------------

def synthetic_products(*, grade="not_assured", contra_open=True, independent=1,
                       findings=None, car="GT-R"):
    prog = {"car": car, "discipline": "race", "gt7_version": "1", "driver": "L"}
    if findings is None:
        findings = ([{"finding_type": "open_contradiction", "severity": "blocking",
                      "domain": "differential", "source_phase": "P29"}] if contra_open else [])
    return {
        "phase26_revalidation": {"items": [{"domain": "differential", "freshness_status": "current"}],
                                 "source_programme": prog, "content_fingerprint": "p26",
                                 "knowledge_versions": {"schema": 1}},
        "phase27_coverage": {"domain_coverage": [{"domain": "differential", "gap_count": 1,
                             "evidence_totals": {"independent": independent, "dependent": 3,
                                                 "record_count": independent + 3}}],
                             "content_fingerprint": "p27", "knowledge_versions": {"schema": 1}},
        "phase28_readiness": {"items": [{"domain": "differential",
                              "readiness_status": "conflicted" if contra_open else "ready"}],
                              "programme_grade": grade, "content_fingerprint": "p28",
                              "knowledge_versions": {"schema": 1}},
        "phase29_contradiction": {"contradictions": [{"domain": "differential",
                                  "is_open": contra_open,
                                  "status": "unresolved" if contra_open else "resolved_by_independence"}],
                                  "open_contradictions": ([{"domain": "differential"}]
                                                          if contra_open else []),
                                  "content_fingerprint": "p29", "knowledge_versions": {"schema": 1}},
        "phase30_assumptions": {"assumptions": [{"domain": "differential",
                                "assumption_type": "independence_assumed", "status": "unverified",
                                "impact": "caps_readiness", "is_conservative_bound": False}],
                                "content_fingerprint": "p30", "knowledge_versions": {"schema": 1}},
        "phase31_assurance": {"assurance_grade": grade, "totals": {"blocking": len(findings), "major": 0},
                              "findings": findings, "source_programme": prog,
                              "content_fingerprint": "p31", "knowledge_versions": {"schema": 1}},
        "phase32_priority": {"assurance_grade": grade, "prioritised_candidates":
                             ([{"candidate_id": "aei_x", "domains": ["differential"],
                                "investigation_type": "contradiction_discrimination",
                                "priority_band": "blocking"}] if contra_open else []),
                             "deferred_candidates": [], "content_fingerprint": "p32",
                             "knowledge_versions": {"schema": 1}},
    }


def synthetic_context(*, car="GT-R", db_v=26, rule="46.0"):
    return {"programme": {"car": car, "discipline": "race", "gt7_version": "1", "driver": "L"},
            "layout_id": "fc", "compound": "rh", "domains": ["differential"],
            "db_schema_version": db_v, "rule_engine_version": rule,
            "source_chain": {"programme_fingerprint": "pk:x"}}


def synthetic_export(**kw):
    ctx_kw = {k: kw.pop(k) for k in ("car", "db_v", "rule") if k in kw}
    car = ctx_kw.get("car", "GT-R")
    return build_assurance_chain_export(synthetic_products(car=car, **kw),
                                        synthetic_context(**ctx_kw)).to_dict()
