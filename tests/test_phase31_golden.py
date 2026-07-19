"""Phase 31 — golden scenarios (10 mandated behaviours).

1.  A clean programme (all facts, no defects) is ASSURED and yields a CLEAN finding.
2.  A blocking open contradiction prevents ASSURED (NOT_ASSURED).
3.  An unresolved regression prevents ASSURED.
4.  Only major findings (no blocking) -> PARTIALLY_ASSURED.
5.  Only moderate/minor findings -> ASSURED_WITH_LIMITATIONS.
6.  No known knowledge -> INSUFFICIENT_EVIDENCE + NO_KNOWN_KNOWLEDGE.
7.  A missing deterministic identity (non-determinism) is a blocking defect.
8.  A ready domain carrying a capping assumption is a mismatch defect.
9.  Unverified-proxy / unknown-attribute reliance are surfaced as findings.
10. No fabricated grade; restart + shuffled input identical; grade exposes counts.
"""
from strategy.assurance_finding import AssuranceFindingType as F
from strategy.assurance_grade import ProgrammeAssuranceGrade as G
from strategy.programme_assurance_report import build_programme_assurance_report


SRC = {"car": "GT-R", "discipline": "race", "gt7_version": "1", "driver": "L"}


def _readiness(items, fp="p28"):
    return {"source_programme": SRC, "items": items, "content_fingerprint": fp}


def _report(readiness, contra=None, assum=None, cov=None, reval=None):
    return build_programme_assurance_report(readiness, contra or {"content_fingerprint": "p29"},
                                            assum or {"content_fingerprint": "p30"},
                                            cov or {"content_fingerprint": "p27"},
                                            reval or {"content_fingerprint": "p26"}).to_dict()


def _types(r):
    return {f["finding_type"] for f in r["findings"]}


# 1
def test_g1_clean_assured():
    r = _report(_readiness([{"domain": "d", "readiness_status": "ready"}]),
                cov={"domain_coverage": [{"domain": "d", "gap_count": 0}],
                     "content_fingerprint": "p27"})
    assert r["assurance_grade"] == G.ASSURED.value
    assert F.CLEAN.value in _types(r)


# 2
def test_g2_open_contradiction_not_assured():
    r = _report(_readiness([{"domain": "d", "readiness_status": "conflicted"}]),
                contra={"open_contradictions": [{"domain": "d"}], "content_fingerprint": "p29"})
    assert r["assurance_grade"] == G.NOT_ASSURED.value
    assert r["blocking"]


# 3
def test_g3_regression_not_assured():
    r = _report(_readiness([{"domain": "d", "readiness_status": "regressed"}]))
    assert r["assurance_grade"] == G.NOT_ASSURED.value


# 4
def test_g4_major_partially_assured():
    r = _report(_readiness([{"domain": "d", "readiness_status": "needs_revalidation"}]))
    assert r["assurance_grade"] == G.PARTIALLY_ASSURED.value


# 5
def test_g5_moderate_with_limitations():
    r = _report(_readiness([{"domain": "d", "readiness_status": "context_bound_only"}]),
                assum={"assumptions": [{"domain": "d",
                                        "assumption_type": "generalisation_from_single_context",
                                        "impact": "narrows_scope"}], "content_fingerprint": "p30"})
    assert r["assurance_grade"] == G.ASSURED_WITH_LIMITATIONS.value


# 6
def test_g6_no_known_insufficient():
    r = _report(_readiness([]))
    assert r["assurance_grade"] == G.INSUFFICIENT_EVIDENCE.value
    assert F.NO_KNOWN_KNOWLEDGE.value in _types(r)


# 7
def test_g7_non_determinism_blocking():
    # an assumptions product with content but no fingerprint is a blocking structural defect
    r = _report(_readiness([{"domain": "d", "readiness_status": "provisional"}]),
                assum={"assumptions": [{"domain": "d", "assumption_type": "x",
                                        "impact": "informational"}], "content_fingerprint": ""})
    assert F.NON_DETERMINISTIC_OUTPUT.value in _types(r)
    assert r["assurance_grade"] == G.NOT_ASSURED.value


# 8
def test_g8_ready_with_capping_assumption_mismatch():
    r = _report(_readiness([{"domain": "d", "readiness_status": "ready"}]),
                assum={"assumptions": [{"domain": "d", "assumption_type": "independence_assumed",
                                        "impact": "caps_readiness"}], "content_fingerprint": "p30"},
                cov={"domain_coverage": [{"domain": "d", "gap_count": 0}],
                     "content_fingerprint": "p27"})
    assert F.ASSUMPTION_CAPS_READINESS_MISMATCH.value in _types(r)


# 9
def test_g9_proxy_and_attribute_reliance():
    r = _report(_readiness([{"domain": "d", "readiness_status": "provisional"}]),
                assum={"assumptions": [
                    {"domain": "d", "assumption_type": "unverified_proxy_assumed",
                     "impact": "blocks_reliance"},
                    {"domain": "d", "assumption_type": "unknown_vehicle_attribute_assumed",
                     "impact": "caps_readiness"}], "content_fingerprint": "p30"})
    t = _types(r)
    assert F.UNVERIFIED_PROXY_RELIANCE.value in t and F.UNKNOWN_ATTRIBUTE_RELIANCE.value in t


# 10
def test_g10_restart_shuffle_identical_and_counts_exposed():
    items = [{"domain": "differential", "readiness_status": "conflicted"},
             {"domain": "springs", "readiness_status": "needs_revalidation"},
             {"domain": "aero_balance", "readiness_status": "ready"}]
    a = _report(_readiness(items),
                cov={"domain_coverage": [{"domain": "aero_balance", "gap_count": 0}],
                     "content_fingerprint": "p27"})
    b = _report(_readiness(list(reversed(items))),
                cov={"domain_coverage": [{"domain": "aero_balance", "gap_count": 0}],
                     "content_fingerprint": "p27"})
    assert a["content_fingerprint"] == b["content_fingerprint"]
    assert "counts" in a["grade_detail"] and a["grade_detail"]["counts"]["blocking"] >= 1
