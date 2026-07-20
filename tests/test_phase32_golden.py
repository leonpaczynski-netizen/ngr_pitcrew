"""Phase 32 — golden scenarios (8 mandated states); restart-identical + ordering-identical.

1. one blocking contradiction
2. multiple findings resolved by one high-leverage investigation
3. stale version-sensitive knowledge
4. readiness capped by assumptions
5. severe blind spots with no negative conclusion
6. dependent evidence requiring independent confirmation
7. fully assured programme
8. negative-only programme with no current known domain
"""
from strategy.assurance_engineering_priority import (
    InvestigationType as T, InvestigationPriorityBand as B,
    build_assurance_engineering_priority,
)


SRC = {"car": "GT-R", "discipline": "race", "gt7_version": "1", "driver": "L"}


def _f(ftype, severity, domain, phase="P31"):
    return {"finding_type": ftype, "severity": severity, "domain": domain, "source_phase": phase}


def _assurance(findings, grade="not_assured"):
    return {"source_programme": SRC, "assurance_grade": grade,
            "totals": {"blocking": sum(1 for f in findings if f["severity"] == "blocking"),
                       "major": sum(1 for f in findings if f["severity"] == "major")},
            "findings": findings, "content_fingerprint": "p31"}


def _cov(rows):
    return {"domain_coverage": [{"domain": d, "gap_count": 1,
                                 "evidence_totals": {"independent": i, "dependent": dep,
                                                     "record_count": rc}}
                                for (d, i, dep, rc) in rows], "content_fingerprint": "p27"}


def _build(a, cov=None):
    return build_assurance_engineering_priority(a, {}, cov or {}, {}, {}).to_dict()


def _restart_identical(a, cov):
    r1 = build_assurance_engineering_priority(a, {}, cov, {}, {}).to_dict()
    r2 = build_assurance_engineering_priority(a, {}, cov, {}, {}).to_dict()
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    return r1


# 1
def test_g1_one_blocking_contradiction():
    a = _assurance([_f("open_contradiction", "blocking", "differential")])
    cov = _cov([("differential", 3, 0, 3)])   # independent already -> discrimination is actionable
    r = _restart_identical(a, cov)
    top = r["prioritised_candidates"][0]
    assert top["investigation_type"] == T.CONTRADICTION_DISCRIMINATION.value
    assert top["priority_band"] == B.BLOCKING.value


# 2
def test_g2_one_high_leverage_investigation_clears_many():
    a = _assurance([_f("dependent_evidence_reliance", "blocking", "differential"),
                    _f("unresolved_regression", "major", "differential"),
                    _f("confirmed_good_unverified", "major", "differential")])
    cov = _cov([("differential", 1, 4, 5)])
    r = _restart_identical(a, cov)
    indep = [c for c in r["prioritised_candidates"] + r["deferred_candidates"]
             if c["investigation_type"] == T.INDEPENDENCE_IMPROVEMENT.value]
    assert len(indep) == 1 and len(indep[0]["linked_finding_ids"]) == 3


# 3
def test_g3_stale_version_sensitive():
    a = _assurance([_f("version_sensitivity_unaddressed", "major", "differential"),
                    _f("stale_knowledge", "major", "springs")])
    cov = _cov([("differential", 2, 0, 2), ("springs", 2, 0, 2)])
    r = _restart_identical(a, cov)
    types = {c["investigation_type"] for c in r["prioritised_candidates"] + r["deferred_candidates"]}
    assert T.VERSION_SENSITIVE_CONFIRMATION.value in types
    assert T.REVALIDATION.value in types


# 4
def test_g4_readiness_capped_by_assumptions():
    a = _assurance([_f("unverified_proxy_reliance", "major", "differential"),
                    _f("unknown_attribute_reliance", "moderate", "springs")])
    cov = _cov([("differential", 2, 0, 2), ("springs", 2, 0, 2)])
    r = _restart_identical(a, cov)
    ass = [c for c in r["prioritised_candidates"] + r["deferred_candidates"]
           if c["investigation_type"] == T.ASSUMPTION_ESTABLISHMENT.value]
    assert ass and all("assumption" in c["impact_limitations"].lower() for c in ass)


# 5
def test_g5_severe_blind_spots_no_negative_conclusion():
    a = _assurance([_f("critical_blind_spot", "major", "differential")])
    cov = _cov([("differential", 0, 0, 0)])
    r = _restart_identical(a, cov)
    mc = [c for c in r["prioritised_candidates"] + r["deferred_candidates"]
          if c["investigation_type"] == T.MISSING_DOMAIN_COVERAGE.value][0]
    blob = (mc["why_needed"] + mc["discriminating_requirement"] + mc["evidence_requested"]).lower()
    assert "not evidence of absence" in blob or "untested" in blob


# 6
def test_g6_dependent_requires_independent_confirmation_first():
    a = _assurance([_f("open_contradiction", "blocking", "differential"),
                    _f("dependent_evidence_reliance", "moderate", "differential")])
    cov = _cov([("differential", 1, 5, 6)])
    r = _restart_identical(a, cov)
    disc = [c for c in r["deferred_candidates"]
            if c["investigation_type"] == T.CONTRADICTION_DISCRIMINATION.value]
    indep = [c for c in r["prioritised_candidates"]
             if c["investigation_type"] == T.INDEPENDENCE_IMPROVEMENT.value]
    assert disc and disc[0]["dependencies"]        # contradiction deferred behind independence
    assert indep                                   # independence is the actionable prerequisite


# 7
def test_g7_fully_assured_no_action():
    a = _assurance([{"finding_type": "clean", "severity": "informational", "domain": "",
                     "source_phase": "audit"}], grade="assured")
    r = _restart_identical(a, {})
    assert r["candidate_count"] == 0
    assert r["prioritised_candidates"] == [] and r["no_action_statement"]


# 8
def test_g8_negative_only_no_known_domain_still_visible():
    # a programme whose only findings are negative/insufficient must still produce a truthful result
    a = _assurance([_f("unresolved_regression", "blocking", "differential"),
                    _f("insufficient_evidence_for_grade", "informational", "differential")],
                   grade="not_assured")
    cov = _cov([("differential", 1, 2, 3)])
    r = _restart_identical(a, cov)
    all_c = r["prioritised_candidates"] + r["deferred_candidates"]
    assert all_c   # negative evidence remains visible as investigations
    assert any(c["investigation_type"] == T.INDEPENDENCE_IMPROVEMENT.value for c in all_c)


def test_all_golden_orderings_stable_under_shuffle():
    findings = [_f("open_contradiction", "blocking", "differential"),
                _f("single_context_reliance", "major", "springs"),
                _f("version_sensitivity_unaddressed", "major", "aero_balance"),
                _f("critical_blind_spot", "moderate", "brake_balance")]
    cov = _cov([("differential", 3, 0, 3), ("springs", 2, 0, 2), ("aero_balance", 2, 0, 2),
                ("brake_balance", 1, 0, 1)])
    r1 = build_assurance_engineering_priority(_assurance(findings), {}, cov, {}, {}).to_dict()
    r2 = build_assurance_engineering_priority(_assurance(list(reversed(findings))), {}, cov,
                                             {}, {}).to_dict()
    ids1 = [c["candidate_id"] for c in r1["prioritised_candidates"] + r1["deferred_candidates"]]
    ids2 = [c["candidate_id"] for c in r2["prioritised_candidates"] + r2["deferred_candidates"]]
    assert ids1 == ids2 and r1["content_fingerprint"] == r2["content_fingerprint"]
