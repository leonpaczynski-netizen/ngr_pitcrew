"""Phase 28 — golden scenarios (10 mandated behaviours).

1.  Strong, current, well-covered knowledge is READY (usable as a decision).
2.  An unresolved conflict blocks readiness (CONFLICTED, not ready).
3.  A regression blocks readiness (REGRESSED).
4.  A version/context change needs re-validation before relying on it.
5.  A critical blind spot (strong claim, thin evidence) needs more evidence.
6.  Context-bound knowledge is ready only within its context.
7.  Superseded knowledge is not ready.
8.  Too little evidence yields INSUFFICIENT_EVIDENCE, never a false grade.
9.  The programme grade is rule-based: a single blocker prevents HIGH; counts are exposed.
10. No fabricated domains; 'ready' never marks unvalidated; restart + shuffle identical.
"""
from strategy.knowledge_readiness import KnowledgeReadinessStatus as R, classify_readiness
from strategy.readiness_grade import ProgrammeReadinessGrade as G
from strategy.programme_readiness_report import build_programme_knowledge_readiness_report


def _conv(domain="differential", **kw):
    base = {"domain": domain, "convergence_status": "strongly_converged",
            "independent_support_count": 3, "dependent_support_count": 0, "confirmed_good": True,
            "compatible_contexts": 3, "current_maturity": "mature", "current_confidence": "high"}
    base.update(kw)
    return base


def _rd(conv, fresh="current", gap=0, blind=""):
    return classify_readiness(conv, {"freshness_status": fresh},
                              {"gap_count": gap, "blind_spot_severity": blind})


# 1
def test_g1_strong_current_well_covered_ready():
    item = _rd(_conv())
    assert item.readiness_status == R.READY.value and item.usable_as == "decision"


# 2
def test_g2_conflict_blocks():
    assert _rd(_conv(convergence_status="conflicting", conflict_count=1),
               fresh="weakened_by_conflict").readiness_status == R.CONFLICTED.value


# 3
def test_g3_regression_blocks():
    assert _rd(_conv(convergence_status="regressed", regression_count=1),
               fresh="weakened_by_regression").readiness_status == R.REGRESSED.value


# 4
def test_g4_version_change_needs_revalidation():
    assert _rd(_conv(), fresh="invalidated_by_version_change").readiness_status == \
        R.NEEDS_REVALIDATION.value


# 5
def test_g5_critical_blind_spot_needs_more_evidence():
    assert _rd(_conv(), blind="critical").readiness_status == R.NEEDS_MORE_EVIDENCE.value


# 6
def test_g6_context_bound_only():
    item = _rd(_conv(convergence_status="stable_but_context_bound"))
    assert item.readiness_status == R.CONTEXT_BOUND_ONLY.value
    assert item.usable_as == "decision within its context"


# 7
def test_g7_superseded_not_ready():
    assert _rd(_conv(convergence_status="superseded"), fresh="superseded").readiness_status == \
        R.SUPERSEDED.value


# 8
def test_g8_insufficient_evidence_grade_not_false():
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"},
          "convergence_summaries": [_conv("differential", convergence_status="insufficient_evidence",
                                          confirmed_good=False)],
          "timeline_points": [], "content_fingerprint": "p25"}
    r = build_programme_knowledge_readiness_report(
        tl, {"content_fingerprint": "p22"},
        {"items": [{"domain": "differential", "freshness_status": "insufficient_context_evidence"}]},
        {"domain_coverage": []}).to_dict()
    assert r["programme_grade"] == G.INSUFFICIENT_EVIDENCE.value


# 9
def test_g9_single_blocker_prevents_high_and_counts_exposed():
    summaries = [_conv("differential"),
                 _conv("weight_transfer", convergence_status="strongly_converged"),
                 _conv("aero_balance", convergence_status="strongly_converged"),
                 _conv("springs", convergence_status="conflicting", conflict_count=1,
                       confirmed_good=False)]
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"},
          "convergence_summaries": summaries, "timeline_points": [], "content_fingerprint": "p25"}
    reval = {"items": [{"domain": "springs", "freshness_status": "weakened_by_conflict"}]}
    cov = {"domain_coverage": [{"domain": d, "gap_count": 0}
                               for d in ("differential", "weight_transfer", "aero_balance",
                                         "springs")]}
    r = build_programme_knowledge_readiness_report(tl, {"content_fingerprint": "p22"}, reval,
                                                   cov).to_dict()
    assert r["programme_grade"] != G.HIGH.value
    assert r["grade_detail"]["blocking"] == 1
    assert r["grade_detail"]["counts"].get("conflicted") == 1


# 10
def test_g10_no_fabricated_domains_restart_shuffle_identical():
    summaries = [_conv("differential"),
                 _conv("weight_transfer", convergence_status="conflicting", conflict_count=1,
                       confirmed_good=False),
                 _conv("aero_balance", convergence_status="converging", confirmed_good=False)]
    tl_a = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                                 "driver": "L"},
            "convergence_summaries": summaries, "timeline_points": [], "content_fingerprint": "p25"}
    tl_b = dict(tl_a); tl_b["convergence_summaries"] = list(reversed(summaries))
    reval = {"items": [], "content_fingerprint": "p26"}
    cov = {"domain_coverage": [], "content_fingerprint": "p27"}
    a = build_programme_knowledge_readiness_report(tl_a, {"content_fingerprint": "p22"}, reval,
                                                   cov).to_dict()
    b = build_programme_knowledge_readiness_report(tl_b, {"content_fingerprint": "p22"}, reval,
                                                   cov).to_dict()
    assert a["content_fingerprint"] == b["content_fingerprint"]
    assert {i["domain"] for i in a["items"]} == {"differential", "weight_transfer", "aero_balance"}
    # converging weight_transfer / aero must never be READY
    for i in a["items"]:
        if i["domain"] in ("weight_transfer", "aero_balance"):
            assert i["readiness_status"] != R.READY.value
