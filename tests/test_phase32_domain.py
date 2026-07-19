"""Phase 32 — pure domain unit tests: candidate generation, doctrine, dedup, dependencies, bands.

Core doctrine: assurance blockers matter but severity alone is not the sole rule; independent
evidence outranks dependent repetition; contradictions need discriminating evidence; assumptions
stay assumptions; missing evidence is not negative; confirmed-good is protected; duplicates merge;
prerequisites are respected; no scheduling; no setup values; no experiment creation.
"""
from strategy.assurance_engineering_priority import (
    InvestigationPriorityBand as B, InvestigationType as T,
    build_investigation_candidates, build_assurance_engineering_priority, finding_id,
)


SRC = {"car": "GT-R", "discipline": "race", "gt7_version": "1", "driver": "L"}


def _f(ftype, severity, domain, phase="Phase 31"):
    return {"finding_type": ftype, "severity": severity, "domain": domain, "source_phase": phase}


def _assurance(findings, grade="not_assured", totals=None):
    t = totals or {"blocking": sum(1 for f in findings if f["severity"] == "blocking"),
                   "major": sum(1 for f in findings if f["severity"] == "major")}
    return {"source_programme": SRC, "assurance_grade": grade, "totals": t, "findings": findings,
            "content_fingerprint": "p31"}


def _cov(domain, independent=1, dependent=0, record_count=1, gap=1):
    return {"domain_coverage": [{"domain": domain, "gap_count": gap,
                                 "evidence_totals": {"independent": independent,
                                                     "dependent": dependent,
                                                     "record_count": record_count}}],
            "content_fingerprint": "p27"}


def _cands(assurance, cov=None):
    return list(build_investigation_candidates(assurance, {}, cov or {}, {}, {}))


def _by_type(cands, t):
    return [c for c in cands if c.investigation_type == t.value]


# ---- finding -> investigation type mapping --------------------------------------------------

def test_open_contradiction_makes_discrimination_candidate():
    c = _cands(_assurance([_f("open_contradiction", "blocking", "differential")]),
              _cov("differential", independent=1, dependent=4, record_count=5))
    disc = _by_type(c, T.CONTRADICTION_DISCRIMINATION)
    assert disc and "distinguish" in disc[0].evidence_requested
    assert disc[0].discriminating_requirement  # must state what has to differ


def test_regression_and_dependent_make_independence_candidate():
    for ft in ("unresolved_regression", "dependent_evidence_reliance", "confirmed_good_unverified"):
        c = _cands(_assurance([_f(ft, "major", "differential")]),
                  _cov("differential", independent=1, dependent=3, record_count=4))
        assert _by_type(c, T.INDEPENDENCE_IMPROVEMENT), ft


def test_stale_makes_revalidation():
    c = _cands(_assurance([_f("stale_knowledge", "major", "d")]), _cov("d"))
    assert _by_type(c, T.REVALIDATION)


def test_version_makes_version_confirmation():
    c = _cands(_assurance([_f("version_sensitivity_unaddressed", "major", "d")]), _cov("d"))
    assert _by_type(c, T.VERSION_SENSITIVE_CONFIRMATION)


def test_single_context_makes_context_expansion():
    c = _cands(_assurance([_f("single_context_reliance", "moderate", "d")]), _cov("d"))
    assert _by_type(c, T.CONTEXT_EXPANSION)


def test_blind_spot_makes_missing_coverage_and_says_untested_not_disproven():
    c = _cands(_assurance([_f("critical_blind_spot", "major", "d")]), _cov("d", record_count=0))
    mc = _by_type(c, T.MISSING_DOMAIN_COVERAGE)
    assert mc
    blob = (mc[0].discriminating_requirement + mc[0].why_needed + mc[0].evidence_requested).lower()
    assert "absence of evidence is not evidence of absence" in blob or "untested" in blob


def test_assumption_findings_make_assumption_establishment():
    for ft in ("unknown_attribute_reliance", "unverified_proxy_reliance",
               "blocking_assumption_present", "assumption_caps_readiness_mismatch"):
        c = _cands(_assurance([_f(ft, "major", "d")]), _cov("d"))
        ae = _by_type(c, T.ASSUMPTION_ESTABLISHMENT)
        assert ae, ft
        assert "assumption" in ae[0].discriminating_requirement.lower()  # stays an assumption


def test_maturity_and_insufficient_make_convergence():
    for ft in ("conflicting_maturity_signals", "insufficient_evidence_for_grade"):
        c = _cands(_assurance([_f(ft, "moderate", "d")]), _cov("d"))
        assert _by_type(c, T.CONVERGENCE_CONFIRMATION), ft


def test_provenance_findings_make_provenance():
    for ft in ("superseded_still_referenced", "missing_transfer_boundary",
               "non_deterministic_output", "data_mutation_detected"):
        c = _cands(_assurance([_f(ft, "minor", "")]), {})
        assert _by_type(c, T.PROVENANCE_IMPROVEMENT), ft


# ---- doctrine -------------------------------------------------------------------------------

def test_blocker_prioritised_when_feasible_and_no_prereq():
    # a blocking contradiction with existing independent evidence (no independence prereq needed)
    c = _cands(_assurance([_f("open_contradiction", "blocking", "d")]),
              _cov("d", independent=3, dependent=0, record_count=3))
    disc = _by_type(c, T.CONTRADICTION_DISCRIMINATION)[0]
    assert disc.priority_band == B.BLOCKING.value and not disc.dependencies


def test_severity_not_sole_rule_dependent_blocker_deferred_behind_prereq():
    # dependent-heavy domain: contradiction (blocking) depends on independence (moderate) -> deferred
    a = _assurance([_f("open_contradiction", "blocking", "d"),
                    _f("dependent_evidence_reliance", "moderate", "d")])
    c = _cands(a, _cov("d", independent=1, dependent=5, record_count=6))
    disc = _by_type(c, T.CONTRADICTION_DISCRIMINATION)[0]
    indep = _by_type(c, T.INDEPENDENCE_IMPROVEMENT)[0]
    assert disc.dependencies and disc.priority_band == B.DEFER.value
    assert indep.priority_band in ("medium", "high", "blocking", "low")  # prerequisite is actionable
    # the prerequisite ranks above the deferred dependent blocker
    order = [x.candidate_id for x in c]
    assert order.index(indep.candidate_id) < order.index(disc.candidate_id)


def test_independence_outranks_dependent_repetition():
    # independence_improvement (adds independence) vs repeated_confirmation (correlated) same effort tier
    a = _assurance([_f("dependent_evidence_reliance", "major", "d1"),
                    _f("readiness_without_coverage", "major", "d2")])
    cov = {"domain_coverage": [
        {"domain": "d1", "gap_count": 1, "evidence_totals": {"independent": 1, "dependent": 4,
                                                             "record_count": 5}},
        {"domain": "d2", "gap_count": 1, "evidence_totals": {"independent": 3, "dependent": 0,
                                                             "record_count": 3}}],
        "content_fingerprint": "p27"}
    c = _cands(a, cov)
    indep = _by_type(c, T.INDEPENDENCE_IMPROVEMENT)[0]
    rep = _by_type(c, T.REPEATED_CONFIRMATION)[0]
    assert indep.priority_score > rep.priority_score


def test_duplicate_findings_merge_into_one_candidate_with_leverage():
    # two findings for the same domain both mapping to independence_improvement -> one candidate
    a = _assurance([_f("unresolved_regression", "major", "d"),
                    _f("dependent_evidence_reliance", "moderate", "d")])
    c = _cands(a, _cov("d", independent=1, dependent=3, record_count=4))
    indep = _by_type(c, T.INDEPENDENCE_IMPROVEMENT)
    assert len(indep) == 1
    assert len(indep[0].linked_finding_ids) == 2
    lev = indep[0].dimension("cross_finding_leverage")
    assert lev["contribution"] > 0


def test_infeasible_candidate_deferred():
    # a domain with no recorded evidence cannot be strengthened -> low availability -> DEFER
    c = _cands(_assurance([_f("dependent_evidence_reliance", "major", "d")]),
              _cov("d", independent=0, dependent=0, record_count=0))
    indep = _by_type(c, T.INDEPENDENCE_IMPROVEMENT)[0]
    av = indep.dimension("evidence_availability")
    assert av["raw"] < 0.5 and indep.priority_band == B.DEFER.value


def test_confirmed_good_clean_programme_no_candidates():
    a = _assurance([{"finding_type": "clean", "severity": "informational", "domain": "",
                     "source_phase": "audit"}], grade="assured", totals={"blocking": 0, "major": 0})
    assert _cands(a) == []


def test_fully_assured_report_no_action():
    a = _assurance([{"finding_type": "clean", "severity": "informational", "domain": "",
                     "source_phase": "audit"}], grade="assured", totals={"blocking": 0, "major": 0})
    r = build_assurance_engineering_priority(a, {}, {}, {}, {}).to_dict()
    assert r["candidate_count"] == 0 and r["no_action_statement"]
    assert "protected" in r["no_action_statement"].lower()


def test_empty_programme_truthful():
    r = build_assurance_engineering_priority({}, {}, {}, {}, {}).to_dict()
    assert r["candidate_count"] == 0 and r["prioritised_candidates"] == []


def test_no_action_finding_types_produce_nothing():
    a = _assurance([_f("no_known_knowledge", "informational", "")],
                   grade="insufficient_evidence", totals={"blocking": 0, "major": 0})
    assert _cands(a) == []


def test_no_setup_values_and_no_scheduling_in_output():
    import re
    a = _assurance([_f("open_contradiction", "blocking", "d"),
                    _f("single_context_reliance", "major", "d2")])
    r = build_assurance_engineering_priority(a, {}, _cov("d", independent=2, record_count=2),
                                            {}, {}).to_dict()
    import json
    blob = json.dumps(r)
    assert not re.search(r'"(arb_front|lsd_accel|springs_front|brake_bias|ride_height)"\s*:\s*-?\d',
                         blob)
    # no dates / sessions / drivers ASSIGNED (the advisory statement denies scheduling; that's fine)
    low = blob.lower()
    for positive in ("session 1", "session 2", "monday", "tuesday", "09:", "o'clock",
                     "due date", "assigned to", "run on", "next session:"):
        assert positive not in low
    # a date pattern like 2026-07-20 must never appear
    assert not re.search(r"\d{4}-\d{2}-\d{2}", blob)


def test_finding_id_is_stable_and_timestamp_free():
    f = _f("open_contradiction", "blocking", "d")
    assert finding_id(f) == finding_id(dict(f))
    assert finding_id(f).startswith("af_")
