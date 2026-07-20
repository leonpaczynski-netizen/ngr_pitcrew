"""Phase 31 — pure domain unit tests: findings taxonomy, audit derivation, rule-based grade.

Core doctrine: a single BLOCKING finding prevents ASSURED; hidden assumptions, unresolved conflicts,
regressions, missing transfer boundaries, non-determinism and data mutation are defects; the grade
is rule-based over visible severity counts, not an opaque score.
"""
from strategy.assurance_finding import (
    AssuranceFindingType, AssuranceSeverity, ASSURANCE_SEVERITY_PRIORITY, default_severity,
    finding_text,
)
from strategy.assurance_grade import (
    ProgrammeAssuranceGrade as G, grade_assurance,
)
from strategy.knowledge_assurance import audit


def _readiness(*items, fp="p28"):
    return {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                                 "driver": "L"}, "items": list(items), "content_fingerprint": fp}


def _item(domain, status, blind=""):
    return {"domain": domain, "readiness_status": status, "blind_spot_severity": blind}


def _types(findings):
    return {f["finding_type"] for f in findings}


# ---- enums / helpers -------------------------------------------------------------------------

def test_22_finding_types_5_severities_5_grades():
    assert len(list(AssuranceFindingType)) == 22
    assert len(list(AssuranceSeverity)) == 5
    assert len(list(G)) == 5
    for s in AssuranceSeverity:
        assert s.value in ASSURANCE_SEVERITY_PRIORITY


def test_default_severity_and_text():
    assert default_severity(AssuranceFindingType.OPEN_CONTRADICTION.value) == "blocking"
    assert default_severity(AssuranceFindingType.SINGLE_CONTEXT_RELIANCE.value) == "moderate"
    assert finding_text(AssuranceFindingType.OPEN_CONTRADICTION.value)


# ---- audit derivation ------------------------------------------------------------------------

def test_open_contradiction_is_blocking():
    findings, known = audit(_readiness(_item("differential", "conflicted")),
                            {"open_contradictions": [{"domain": "differential"}]}, {}, {}, {})
    assert known
    oc = [f for f in findings if f["finding_type"] == "open_contradiction"]
    assert oc and oc[0]["severity"] == "blocking"


def test_regression_is_blocking():
    findings, _ = audit(_readiness(_item("springs", "regressed")), {}, {}, {}, {})
    assert AssuranceFindingType.UNRESOLVED_REGRESSION.value in _types(findings)


def test_assumption_reliance_findings():
    assum = {"assumptions": [
        {"domain": "d1", "assumption_type": "unverified_proxy_assumed", "impact": "blocks_reliance"},
        {"domain": "d2", "assumption_type": "generalisation_from_single_context",
         "impact": "narrows_scope"},
        {"domain": "d3", "assumption_type": "independence_assumed", "impact": "caps_readiness"}]}
    findings, _ = audit(_readiness(_item("d1", "provisional")), {}, assum, {}, {})
    t = _types(findings)
    assert AssuranceFindingType.UNVERIFIED_PROXY_RELIANCE.value in t
    assert AssuranceFindingType.SINGLE_CONTEXT_RELIANCE.value in t
    assert AssuranceFindingType.DEPENDENT_EVIDENCE_RELIANCE.value in t


def test_assumption_caps_readiness_mismatch():
    assum = {"assumptions": [{"domain": "ready_dom", "assumption_type": "independence_assumed",
                              "impact": "caps_readiness"}]}
    findings, _ = audit(_readiness(_item("ready_dom", "ready")), {}, assum,
                        {"domain_coverage": [{"domain": "ready_dom", "gap_count": 0}]}, {})
    assert AssuranceFindingType.ASSUMPTION_CAPS_READINESS_MISMATCH.value in _types(findings)


def test_non_deterministic_output_when_fingerprint_missing():
    # a coverage report with content but no fingerprint is a structural defect
    findings, _ = audit(_readiness(_item("d", "provisional")), {},
                        {"assumptions": [{"domain": "d", "assumption_type": "x", "impact": "informational"}],
                         "content_fingerprint": ""}, {}, {})
    assert AssuranceFindingType.NON_DETERMINISTIC_OUTPUT.value in _types(findings)


def test_no_known_knowledge_flag():
    findings, known = audit(_readiness(), {}, {}, {}, {})
    assert not known
    assert AssuranceFindingType.NO_KNOWN_KNOWLEDGE.value in _types(findings)


def test_clean_when_no_defects():
    findings, known = audit(_readiness(_item("d", "ready")), {}, {},
                            {"domain_coverage": [{"domain": "d", "gap_count": 0}],
                             "content_fingerprint": "p27"}, {})
    assert known
    assert AssuranceFindingType.CLEAN.value in _types(findings)


def test_findings_dedup_keeps_most_severe():
    # same (type, domain) from readiness + contradiction -> a single blocking finding
    findings, _ = audit(_readiness(_item("differential", "conflicted")),
                        {"open_contradictions": [{"domain": "differential"}]}, {}, {}, {})
    oc = [f for f in findings if f["finding_type"] == "open_contradiction"
          and f["domain"] == "differential"]
    assert len(oc) == 1


# ---- grade -----------------------------------------------------------------------------------

def test_blocking_prevents_assured():
    g = grade_assurance([{"severity": "blocking"}, {"severity": "moderate"}], True)
    assert g["grade"] == G.NOT_ASSURED.value and g["counts"]["blocking"] == 1


def test_major_gives_partially():
    g = grade_assurance([{"severity": "major"}, {"severity": "minor"}], True)
    assert g["grade"] == G.PARTIALLY_ASSURED.value


def test_moderate_minor_gives_with_limitations():
    g = grade_assurance([{"severity": "moderate"}], True)
    assert g["grade"] == G.ASSURED_WITH_LIMITATIONS.value


def test_no_findings_gives_assured():
    g = grade_assurance([{"severity": "informational"}], True)
    assert g["grade"] == G.ASSURED.value


def test_no_known_gives_insufficient():
    g = grade_assurance([], False)
    assert g["grade"] == G.INSUFFICIENT_EVIDENCE.value


def test_grade_exposes_counts_and_rule():
    g = grade_assurance([{"severity": "blocking"}], True)
    assert set(g) >= {"grade", "counts", "rule", "reasons", "total_findings"}
