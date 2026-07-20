"""Phase 32 fingerprint-completeness remediation tests.

Proves that EVERY material candidate field independently changes the priority fingerprint, that
unchanged semantic content retains the same fingerprint, that shuffled legal ordering is stable, and
documents the intentional (domain, investigation_type) grouping (no cross-domain over-merge).
"""
import copy

from strategy.assurance_engineering_priority import (
    content_fingerprint_for_candidates, build_investigation_candidates,
    build_assurance_engineering_priority, knowledge_versions,
)


SRC = {"car": "GT-R", "discipline": "race", "gt7_version": "1", "driver": "L"}


def _f(ftype, severity, domain, phase="P31"):
    return {"finding_type": ftype, "severity": severity, "domain": domain, "source_phase": phase}


def _assurance(findings):
    return {"source_programme": SRC, "assurance_grade": "not_assured",
            "totals": {"blocking": sum(1 for f in findings if f["severity"] == "blocking"),
                       "major": sum(1 for f in findings if f["severity"] == "major")},
            "findings": findings, "content_fingerprint": "p31"}


def _cov(domain, independent=1, dependent=5, record_count=6):
    return {"domain_coverage": [{"domain": domain, "gap_count": 1,
                                 "evidence_totals": {"independent": independent,
                                                     "dependent": dependent,
                                                     "record_count": record_count}}],
            "content_fingerprint": "p27"}


def _candidate_dicts():
    a = _assurance([_f("open_contradiction", "blocking", "differential"),
                    _f("dependent_evidence_reliance", "moderate", "differential"),
                    _f("single_context_reliance", "major", "springs")])
    cands = build_investigation_candidates(a, {}, _cov("differential"), {}, {})
    return [c.to_dict() for c in cands]


def _fp(cands):
    return content_fingerprint_for_candidates(SRC, "not_assured", 1, 1, cands, knowledge_versions())


# ---- every material candidate field participates in the fingerprint -------------------------

# scalar string/number fields on a candidate that must be material
_MATERIAL_SCALAR_FIELDS = [
    "candidate_id", "investigation_type", "max_severity", "evidence_requested", "why_needed",
    "current_evidence_state", "discriminating_requirement", "expected_assurance_impact",
    "impact_limitations", "priority_score", "priority_band", "defer_conditions", "rationale",
    "advisory_statement",
]


def test_every_material_scalar_field_changes_fingerprint():
    base = _candidate_dicts()
    base_fp = _fp(base)
    for field in _MATERIAL_SCALAR_FIELDS:
        m = copy.deepcopy(base)
        target = next(c for c in m if c.get(field) not in (None, "", [])) if any(
            c.get(field) not in (None, "", []) for c in m) else m[0]
        cur = target.get(field)
        target[field] = (cur + 0.5) if isinstance(cur, (int, float)) else (str(cur) + "_MUT")
        assert _fp(m) != base_fp, f"fingerprint ignored material field: {field}"


def test_linked_finding_ids_material():
    base = _candidate_dicts(); base_fp = _fp(base)
    m = copy.deepcopy(base)
    m[0]["linked_finding_ids"] = list(m[0]["linked_finding_ids"]) + ["af_injected"]
    assert _fp(m) != base_fp


def test_finding_types_material():
    base = _candidate_dicts(); base_fp = _fp(base)
    m = copy.deepcopy(base)
    m[0]["finding_types"] = list(m[0]["finding_types"]) + ["mut_type"]
    assert _fp(m) != base_fp


def test_each_dimension_raw_weight_contribution_material():
    base = _candidate_dicts(); base_fp = _fp(base)
    for key in ("raw", "weight", "contribution", "name", "rationale"):
        m = copy.deepcopy(base)
        dim = m[0]["dimensions"][0]
        dim[key] = (dim[key] + 1) if isinstance(dim[key], (int, float)) else str(dim[key]) + "_x"
        assert _fp(m) != base_fp, f"fingerprint ignored dimension.{key}"


def test_dependency_fields_material():
    # find a candidate that has a dependency
    base = _candidate_dicts()
    dep_cand = next((c for c in base if c.get("dependencies")), None)
    assert dep_cand is not None, "expected a dependent candidate in the fixture"
    base_fp = _fp(base)
    for key in ("prerequisite_candidate_id", "prerequisite_type", "reason"):
        m = copy.deepcopy(base)
        target = next(c for c in m if c.get("dependencies"))
        target["dependencies"][0][key] = str(target["dependencies"][0][key]) + "_z"
        assert _fp(m) != base_fp, f"fingerprint ignored dependency.{key}"


def test_candidate_membership_material():
    base = _candidate_dicts(); base_fp = _fp(base)
    assert _fp(base[:-1]) != base_fp   # dropping a candidate changes the fingerprint


def test_candidate_order_material():
    base = _candidate_dicts()
    assert len(base) >= 2
    swapped = [base[1], base[0]] + base[2:]
    assert _fp(swapped) != _fp(base)   # order is material


def test_unchanged_content_retains_fingerprint():
    base = _candidate_dicts()
    assert _fp(base) == _fp(copy.deepcopy(base))


def test_grade_and_counts_material():
    base = _candidate_dicts()
    fp0 = content_fingerprint_for_candidates(SRC, "not_assured", 1, 1, base, knowledge_versions())
    assert content_fingerprint_for_candidates(SRC, "partially_assured", 1, 1, base,
                                              knowledge_versions()) != fp0
    assert content_fingerprint_for_candidates(SRC, "not_assured", 2, 1, base,
                                              knowledge_versions()) != fp0
    assert content_fingerprint_for_candidates(SRC, "not_assured", 1, 2, base,
                                              knowledge_versions()) != fp0
    assert content_fingerprint_for_candidates({**SRC, "car": "Supra"}, "not_assured", 1, 1, base,
                                              knowledge_versions()) != fp0


def test_full_report_fingerprint_reacts_to_evidence_request_change_via_type():
    # a real end-to-end guard: a different investigation type (different evidence_requested/why)
    # yields a different report fingerprint
    a1 = _assurance([_f("open_contradiction", "blocking", "differential")])
    a2 = _assurance([_f("stale_knowledge", "blocking", "differential")])
    r1 = build_assurance_engineering_priority(a1, {}, _cov("differential", independent=3,
                                                           dependent=0, record_count=3), {}, {}).to_dict()
    r2 = build_assurance_engineering_priority(a2, {}, _cov("differential", independent=3,
                                                           dependent=0, record_count=3), {}, {}).to_dict()
    assert r1["content_fingerprint"] != r2["content_fingerprint"]


def test_shuffled_finding_order_stable_fingerprint():
    findings = [_f("open_contradiction", "blocking", "differential"),
                _f("single_context_reliance", "major", "springs"),
                _f("stale_knowledge", "major", "aero_balance")]
    cov = {"domain_coverage": [
        {"domain": "differential", "gap_count": 1, "evidence_totals": {"independent": 3,
         "dependent": 0, "record_count": 3}},
        {"domain": "springs", "gap_count": 1, "evidence_totals": {"independent": 2, "dependent": 0,
         "record_count": 2}},
        {"domain": "aero_balance", "gap_count": 1, "evidence_totals": {"independent": 2,
         "dependent": 0, "record_count": 2}}], "content_fingerprint": "p27"}
    r1 = build_assurance_engineering_priority(_assurance(findings), {}, cov, {}, {}).to_dict()
    r2 = build_assurance_engineering_priority(_assurance(list(reversed(findings))), {}, cov,
                                             {}, {}).to_dict()
    assert r1["content_fingerprint"] == r2["content_fingerprint"]


# ---- cross-domain grouping is intentional (documented, not a defect) ------------------------

def test_cross_domain_grouping_does_not_over_merge():
    """Two same-type findings in DIFFERENT domains stay as two distinct candidates - each domain
    needs its own distinct evidence, so they are intentionally NOT consolidated cross-domain.
    Cross-finding leverage accrues only WITHIN a (domain, investigation_type) group."""
    a = _assurance([_f("open_contradiction", "blocking", "differential"),
                    _f("open_contradiction", "blocking", "springs")])
    cov = {"domain_coverage": [
        {"domain": "differential", "gap_count": 1, "evidence_totals": {"independent": 3,
         "dependent": 0, "record_count": 3}},
        {"domain": "springs", "gap_count": 1, "evidence_totals": {"independent": 3, "dependent": 0,
         "record_count": 3}}], "content_fingerprint": "p27"}
    cands = list(build_investigation_candidates(a, {}, cov, {}, {}))
    disc = [c for c in cands if c.investigation_type == "contradiction_discrimination"]
    assert len(disc) == 2
    assert {c.domains for c in disc} == {("differential",), ("springs",)}
    # each links exactly its own domain's finding (no cross-domain leverage inflation)
    for c in disc:
        assert len(c.linked_finding_ids) == 1


def test_same_domain_same_type_merges_with_leverage():
    a = _assurance([_f("dependent_evidence_reliance", "major", "differential"),
                    _f("unresolved_regression", "major", "differential"),
                    _f("confirmed_good_unverified", "major", "differential")])
    cands = list(build_investigation_candidates(a, {}, _cov("differential", independent=1,
                                                            dependent=3, record_count=4), {}, {}))
    indep = [c for c in cands if c.investigation_type == "independence_improvement"]
    assert len(indep) == 1 and len(indep[0].linked_finding_ids) == 3
