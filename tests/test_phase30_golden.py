"""Phase 30 — golden scenarios (10 mandated behaviours).

1.  A directly-evidenced (factual) domain produces NO assumptions.
2.  A single-context result is registered as a generalisation assumption (narrows scope).
3.  Dependent-only evidence is registered as an independence assumption (caps readiness).
4.  Knowledge relied on without re-validation is a currency assumption.
5.  A confirmed-good behaviour not re-observed is a persistence assumption.
6.  Version-sensitive knowledge not re-confirmed is a version-stability assumption.
7.  An assumption can only CAP readiness, never create it (no positive impact).
8.  A conservative bound (unknown attribute / unverified proxy) is labelled as such.
9.  Facts are not listed as assumptions.
10. No fabricated domains; restart + shuffled input identical.
"""
from strategy.assumption_classification import AssumptionType as T, AssumptionStatus as St
from strategy.assumption_impact import AssumptionImpact as I
from strategy.engineering_assumption import derive_domain_assumptions
from strategy.programme_assumption_register import build_programme_assumption_register


def _conv(domain="differential", **kw):
    base = {"domain": domain, "convergence_status": "converging", "confirmed_good": False,
            "transfer_limitations": []}
    base.update(kw)
    return base


def _cov(domain="differential", gap=1, **dims):
    return {"domain": domain, "gap_count": gap,
            "dimensions": [{"dimension": k, "status": v} for k, v in dims.items()]}


def _types(a):
    return {x["assumption_type"] for x in a}


# 1
def test_g1_factual_no_assumptions():
    a = derive_domain_assumptions("differential", _conv(convergence_status="strongly_converged"),
                                  {"freshness_status": "current"}, {"gap_count": 0}, {})
    assert a == ()


# 2
def test_g2_single_context_generalisation():
    a = derive_domain_assumptions("differential", _conv(),
                                  {"freshness_status": "current"},
                                  _cov(track_variety="single_context_only"), {})
    assert T.GENERALISATION_FROM_SINGLE_CONTEXT.value in _types(a)


# 3
def test_g3_dependent_independence_assumption():
    a = derive_domain_assumptions("differential", _conv(),
                                  {"freshness_status": "current"},
                                  _cov(independent_replication="dependent_evidence_only"), {})
    assert T.INDEPENDENCE_ASSUMED.value in _types(a)


# 4
def test_g4_currency_assumption():
    a = derive_domain_assumptions("differential", _conv(),
                                  {"freshness_status": "revalidation_advised"}, _cov(), {})
    assert T.CURRENCY_ASSUMED.value in _types(a)


# 5
def test_g5_confirmed_good_persistence():
    a = derive_domain_assumptions("differential", _conv(confirmed_good=True),
                                  {"freshness_status": "revalidation_required"}, _cov(), {})
    assert T.CONFIRMED_GOOD_PERSISTS_ASSUMED.value in _types(a)


# 6
def test_g6_version_stability():
    a = derive_domain_assumptions("differential",
                                  _conv(transfer_limitations=["gt7_version specific"]),
                                  {"freshness_status": "revalidation_advised"}, _cov(), {})
    assert T.VERSION_STABILITY_ASSUMED.value in _types(a)


# 7
def test_g7_assumptions_only_cap_never_create():
    a = derive_domain_assumptions("differential", _conv(confirmed_good=True),
                                  {"freshness_status": "revalidation_required"},
                                  _cov(track_variety="single_context_only"), {})
    assert a
    for x in a:
        assert x["impact"] in ("blocks_reliance", "caps_readiness", "narrows_scope",
                               "weakens_confidence", "informational", "unknown")
        assert x["readiness_cap"] != "high"   # no impact yields anything above "ready"


# 8
def test_g8_conservative_bound_labelled():
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"}, "convergence_summaries": [], "content_fingerprint": "p25"}
    pb = {"knowledge_boundaries": [{"boundary_type": "unknown_vehicle_attribute",
                                    "domain": "differential", "target_car": "", "reason": "mass unknown"}]}
    r = build_programme_assumption_register(tl, {"items": []}, {"domain_coverage": []},
                                            {"contradictions": []}, pb).to_dict()
    assert r["conservative_bounds"]
    b = r["conservative_bounds"][0]
    assert b["assumption_type"] == T.UNKNOWN_VEHICLE_ATTRIBUTE_ASSUMED.value
    assert b["is_conservative_bound"] and b["status"] == St.EXPLICIT_AND_LABELLED.value


# 9
def test_g9_facts_not_listed():
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"},
          "convergence_summaries": [_conv("differential", convergence_status="strongly_converged",
                                          confirmed_good=True)],
          "content_fingerprint": "p25"}
    reval = {"items": [{"domain": "differential", "freshness_status": "current"}]}
    cov = {"domain_coverage": [{"domain": "differential", "gap_count": 0, "dimensions": []}]}
    r = build_programme_assumption_register(tl, reval, cov, {"contradictions": []},
                                            {"knowledge_boundaries": []}).to_dict()
    assert r["assumptions"] == []


# 10
def test_g10_no_fabricated_domains_restart_shuffle_identical():
    summaries = [_conv("differential", convergence_status="stable_but_context_bound"),
                 _conv("weight_transfer", convergence_status="converging"),
                 _conv("aero_balance", confirmed_good=True)]
    tl_a = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                                 "driver": "L"}, "convergence_summaries": summaries,
            "content_fingerprint": "p25"}
    tl_b = dict(tl_a); tl_b["convergence_summaries"] = list(reversed(summaries))
    reval = {"items": [{"domain": d, "freshness_status": "revalidation_advised"}
                       for d in ("differential", "weight_transfer", "aero_balance")]}
    cov = {"domain_coverage": [_cov(d, track_variety="single_context_only")
                               for d in ("differential", "weight_transfer", "aero_balance")]}
    a = build_programme_assumption_register(tl_a, reval, cov, {"contradictions": []},
                                            {"knowledge_boundaries": []}).to_dict()
    b = build_programme_assumption_register(tl_b, reval, cov, {"contradictions": []},
                                            {"knowledge_boundaries": []}).to_dict()
    assert a["content_fingerprint"] == b["content_fingerprint"]
    assert {x["domain"] for x in a["assumptions"]} <= {"differential", "weight_transfer",
                                                       "aero_balance"}
