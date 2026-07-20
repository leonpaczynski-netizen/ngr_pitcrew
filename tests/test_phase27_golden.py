"""Phase 27 — golden scenarios (10 mandated behaviours).

1.  Missing coverage is not a negative result (MISSING != REGRESSION_ONLY).
2.  A blind spot is not a problem — early-stage gaps are informational.
3.  A large dependent count is not strong coverage.
4.  One track/car/driver/compound/format is a single context, not multi-context.
5.  Multi-context independent evidence is well covered (no blind spot raised).
6.  Confirmed-good resting on thin evidence is a raised (critical/material) blind spot.
7.  An unresolved conflict in a relied-upon domain is a critical blind spot.
8.  Only-positive evidence leaves the failure boundary untested (a gap, not a fault).
9.  Re-validation currency reuses the Phase-26 authority verbatim.
10. No fabricated domains; restart and shuffled input remain identical.
"""
from strategy.coverage_dimension import CoverageStatus as S, BlindSpotSeverity as Sev
from strategy.evidence_coverage import assess_domain_coverage
from strategy.knowledge_blind_spot import classify_blind_spot
from strategy.programme_coverage_report import build_programme_evidence_coverage_report


def _rec(track="Fuji", car="GT-R", **kw):
    ctx = {"track": track, "car": car, "driver": "L", "compound": "RH", "discipline": "race",
           "gt7_version": "1", "layout_id": "fc"}
    ctx.update({k: v for k, v in kw.items() if k in ctx})
    return {"context": ctx, "residual_states": [{"family": "rotation", "phase": "entry",
            "segment_id": "T1"}], "outcome_status": kw.get("outcome", "confirmed_improvement"),
            "confidence_level": kw.get("conf", "high")}


def _conv(**kw):
    base = {"domain": "differential", "convergence_status": "converging",
            "independent_support_count": 1, "dependent_support_count": 0, "regression_count": 0,
            "conflict_count": 0, "confirmed_good": False, "compatible_contexts": 1,
            "current_maturity": "developing", "current_confidence": "medium"}
    base.update(kw)
    return base


def _dim(cov, name):
    return next(d for d in cov["dimensions"] if d["dimension"] == name)


# 1
def test_g1_missing_is_not_negative():
    cov = assess_domain_coverage("differential", [], _conv(compatible_contexts=0), {}).to_dict()
    assert _dim(cov, "track_variety")["status"] == S.MISSING.value
    assert _dim(cov, "track_variety")["status"] != S.REGRESSION_ONLY.value


# 2
def test_g2_blind_spot_early_stage_is_informational():
    cov = assess_domain_coverage("differential", [_rec()],
                                 _conv(current_maturity="emerging", current_confidence="low"),
                                 {"freshness_status": "current"}).to_dict()
    assert classify_blind_spot(cov).severity == Sev.INFORMATIONAL.value


# 3
def test_g3_large_dependent_count_not_strong():
    cov = assess_domain_coverage("differential", [_rec()],
                                 _conv(independent_support_count=1, dependent_support_count=99),
                                 {}).to_dict()
    assert _dim(cov, "independent_replication")["status"] == S.DEPENDENT_EVIDENCE_ONLY.value


# 4
def test_g4_single_context_not_multi():
    cov = assess_domain_coverage("differential", [_rec(track="Fuji"), _rec(track="Fuji")],
                                 _conv(), {}).to_dict()
    assert _dim(cov, "track_variety")["status"] == S.SINGLE_CONTEXT_ONLY.value


# 5
def test_g5_multi_context_independent_well_covered():
    recs = [_rec(track=t) for t in ("Fuji", "Suzuka", "Spa")]
    cov = assess_domain_coverage(
        "differential", recs,
        _conv(convergence_status="strongly_converged", independent_support_count=3,
              compatible_contexts=3, current_maturity="mature", current_confidence="high",
              confirmed_good=True),
        {"freshness_status": "current"}).to_dict()
    assert _dim(cov, "track_variety")["status"] == S.WELL_COVERED.value
    assert _dim(cov, "independent_replication")["status"] == S.WELL_COVERED.value


# 6
def test_g6_confirmed_good_thin_is_raised():
    cov = assess_domain_coverage(
        "differential", [_rec()],
        _conv(confirmed_good=True, current_maturity="mature", current_confidence="very_high",
              independent_support_count=1, dependent_support_count=6),
        {"freshness_status": "current"}).to_dict()
    assert classify_blind_spot(cov).severity in (Sev.CRITICAL.value, Sev.MATERIAL.value)


# 7
def test_g7_unresolved_conflict_relied_upon_critical():
    cov = assess_domain_coverage(
        "differential", [_rec()],
        _conv(convergence_status="conflicting", conflict_count=1, current_maturity="established",
              current_confidence="high", independent_support_count=2, compatible_contexts=2),
        {"freshness_status": "weakened_by_conflict"}).to_dict()
    assert classify_blind_spot(cov).severity == Sev.CRITICAL.value


# 8
def test_g8_only_positive_leaves_failure_untested():
    cov = assess_domain_coverage("differential", [_rec(outcome="confirmed_improvement")],
                                 _conv(regression_count=0), {}).to_dict()
    rc = _dim(cov, "regression_check")
    assert rc["status"] == S.PARTIALLY_COVERED.value and "untested" in rc["detail"]


# 9
def test_g9_revalidation_currency_from_phase26():
    for fresh, expected in (("current", S.WELL_COVERED.value),
                            ("revalidation_required", S.PARTIALLY_COVERED.value),
                            ("weakened_by_regression", S.REGRESSION_ONLY.value)):
        cov = assess_domain_coverage("differential", [_rec()], _conv(),
                                     {"freshness_status": fresh}).to_dict()
        assert _dim(cov, "revalidation_currency")["status"] == expected


# 10
def test_g10_no_fabricated_domains_and_restart_shuffle_identical():
    summaries = [_conv(domain="differential", convergence_status="strongly_converged",
                       independent_support_count=3, compatible_contexts=3),
                 _conv(domain="weight_transfer", convergence_status="conflicting", conflict_count=1),
                 _conv(domain="aero_balance", convergence_status="regressed", regression_count=2)]
    tl_a = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                                 "driver": "L"},
            "convergence_summaries": summaries, "timeline_points": [], "content_fingerprint": "p25"}
    tl_b = dict(tl_a); tl_b["convergence_summaries"] = list(reversed(summaries))
    prog = {"compatibility": {}, "content_fingerprint": "p22"}
    reval = {"items": [], "content_fingerprint": "p26"}
    recs = [_rec()]
    a = build_programme_evidence_coverage_report(tl_a, prog, reval, recs).to_dict()
    b = build_programme_evidence_coverage_report(tl_b, prog, reval, recs).to_dict()
    assert a["content_fingerprint"] == b["content_fingerprint"]
    # only the three real convergence domains appear — nothing fabricated.
    assert {c["domain"] for c in a["domain_coverage"]} == {"differential", "weight_transfer",
                                                           "aero_balance"}
