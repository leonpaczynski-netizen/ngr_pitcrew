"""Phase 30 — pure domain unit tests: classification, impact, assumption derivation.

Core doctrine: facts are NOT assumptions; an assumption can only CAP readiness (never create it);
conservative bounds are labelled.
"""
from strategy.assumption_classification import (
    AssumptionType, AssumptionStatus, ASSUMPTION_STATUS_PRIORITY, type_text,
)
from strategy.assumption_impact import (
    AssumptionImpact, ASSUMPTION_IMPACT_PRIORITY, IMPACT_READINESS_CAP, impact_text, readiness_cap,
)
from strategy.engineering_assumption import (
    is_factual, derive_domain_assumptions,
)


def _conv(**kw):
    base = {"domain": "differential", "convergence_status": "converging", "confirmed_good": False,
            "transfer_limitations": []}
    base.update(kw)
    return base


def _cov(**dims):
    return {"domain": "differential", "gap_count": len(dims),
            "dimensions": [{"dimension": k, "status": v} for k, v in dims.items()]}


def _types(assumptions):
    return {a["assumption_type"] for a in assumptions}


# ---- enums -----------------------------------------------------------------------------------

def test_16_types_8_statuses_6_impacts():
    assert len(list(AssumptionType)) == 16
    assert len(list(AssumptionStatus)) == 8
    assert len(list(AssumptionImpact)) == 6
    for s in AssumptionStatus:
        assert s.value in ASSUMPTION_STATUS_PRIORITY
    for i in AssumptionImpact:
        assert i.value in ASSUMPTION_IMPACT_PRIORITY and i.value in IMPACT_READINESS_CAP


def test_impact_never_positive():
    # no impact lifts readiness above "ready"; the strongest cap is "not_ready"
    caps = set(IMPACT_READINESS_CAP.values())
    assert caps <= {"not_ready", "context_bound_only", "ready_with_limitations", "ready"}
    assert readiness_cap("blocks_reliance") == "not_ready"


def test_text_helpers():
    assert type_text(AssumptionType.TRANSFER_ASSUMED.value)
    assert impact_text(AssumptionImpact.CAPS_READINESS.value)


# ---- is_factual ------------------------------------------------------------------------------

def test_factual_domain_has_no_assumptions():
    conv = _conv(convergence_status="strongly_converged")
    assert is_factual(conv, {"gap_count": 0}, {"freshness_status": "current"}, {"is_open": False})
    assert derive_domain_assumptions("differential", conv, {"freshness_status": "current"},
                                     {"gap_count": 0}, {"is_open": False}) == ()


def test_not_factual_when_open_contradiction():
    conv = _conv(convergence_status="strongly_converged")
    assert not is_factual(conv, {"gap_count": 0}, {"freshness_status": "current"},
                          {"is_open": True})


# ---- derivation rules ------------------------------------------------------------------------

def test_single_context_generalisation():
    a = derive_domain_assumptions("differential", _conv(),
                                  {"freshness_status": "current"},
                                  _cov(track_variety="single_context_only"), {})
    assert AssumptionType.GENERALISATION_FROM_SINGLE_CONTEXT.value in _types(a)
    assert a[0]["impact"] == AssumptionImpact.NARROWS_SCOPE.value


def test_dependent_evidence_independence_assumed():
    a = derive_domain_assumptions("differential", _conv(),
                                  {"freshness_status": "current"},
                                  _cov(independent_replication="dependent_evidence_only"), {})
    assert AssumptionType.INDEPENDENCE_ASSUMED.value in _types(a)


def test_currency_assumed_when_revalidation_required():
    a = derive_domain_assumptions("differential", _conv(),
                                  {"freshness_status": "revalidation_required"}, _cov(), {})
    cur = [x for x in a if x["assumption_type"] == AssumptionType.CURRENCY_ASSUMED.value]
    assert cur and cur[0]["status"] == AssumptionStatus.AT_RISK.value


def test_confirmed_good_persists_assumed():
    a = derive_domain_assumptions("differential", _conv(confirmed_good=True),
                                  {"freshness_status": "revalidation_advised"}, _cov(), {})
    assert AssumptionType.CONFIRMED_GOOD_PERSISTS_ASSUMED.value in _types(a)


def test_version_stability_assumed():
    a = derive_domain_assumptions("differential",
                                  _conv(transfer_limitations=["depends on gt7_version"]),
                                  {"freshness_status": "revalidation_advised"}, _cov(), {})
    assert AssumptionType.VERSION_STABILITY_ASSUMED.value in _types(a)


def test_contradiction_side_assumed_when_open_with_standing():
    a = derive_domain_assumptions("differential", _conv(),
                                  {"freshness_status": "current"}, _cov(),
                                  {"is_open": True,
                                   "standing_conclusion": "the confirming conclusion"})
    side = [x for x in a if x["assumption_type"] == AssumptionType.CONTRADICTION_SIDE_ASSUMED.value]
    assert side and side[0]["impact"] == AssumptionImpact.BLOCKS_RELIANCE.value


def test_open_contradiction_without_standing_is_not_a_side_assumption():
    a = derive_domain_assumptions("differential", _conv(),
                                  {"freshness_status": "current"}, _cov(),
                                  {"is_open": True, "standing_conclusion": ""})
    assert AssumptionType.CONTRADICTION_SIDE_ASSUMED.value not in _types(a)


def test_every_assumption_caps_never_lifts():
    a = derive_domain_assumptions("differential", _conv(confirmed_good=True),
                                  {"freshness_status": "revalidation_required"},
                                  _cov(track_variety="single_context_only",
                                       independent_replication="dependent_evidence_only"), {})
    assert a  # some assumptions surfaced
    for x in a:
        assert x["readiness_cap"] in ("not_ready", "context_bound_only", "ready_with_limitations",
                                      "ready")
        # nothing here is allowed to assert "more ready than ready"
        assert x["impact"] in ASSUMPTION_IMPACT_PRIORITY
