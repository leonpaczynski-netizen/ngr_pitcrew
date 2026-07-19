"""Phase 32 — scoring & ranking tests: transparent dimensions, exact contribution maths, determinism.

Every dimension exposes raw/weight/contribution; contribution maths is exact; the final score is the
signed sum; ranking + tie-break are deterministic; penalties and drivers (blocker/leverage/info-gain)
affect ranking; infeasible evidence cannot rank as immediately actionable.
"""
from strategy.assurance_engineering_priority import (
    InvestigationType as T, InvestigationPriorityBand as B,
    VALUE_DIMENSION_WEIGHTS, PENALTY_DIMENSION_WEIGHTS, DIMENSION_WEIGHTS,
    build_investigation_candidates, build_assurance_engineering_priority,
)


SRC = {"car": "GT-R", "discipline": "race", "gt7_version": "1", "driver": "L"}


def _f(ftype, severity, domain):
    return {"finding_type": ftype, "severity": severity, "domain": domain, "source_phase": "P31"}


def _assurance(findings):
    return {"source_programme": SRC, "assurance_grade": "not_assured",
            "totals": {"blocking": sum(1 for f in findings if f["severity"] == "blocking"),
                       "major": sum(1 for f in findings if f["severity"] == "major")},
            "findings": findings, "content_fingerprint": "p31"}


def _cov(domain, independent=1, dependent=0, record_count=1):
    return {"domain_coverage": [{"domain": domain, "gap_count": 1,
                                 "evidence_totals": {"independent": independent,
                                                     "dependent": dependent,
                                                     "record_count": record_count}}],
            "content_fingerprint": "p27"}


def _cands(a, cov=None):
    return list(build_investigation_candidates(a, {}, cov or {}, {}, {}))


# ---- transparency ---------------------------------------------------------------------------

def test_information_gain_weighted_highest():
    assert DIMENSION_WEIGHTS["information_gain"] == 3.0
    assert DIMENSION_WEIGHTS["information_gain"] == max(VALUE_DIMENSION_WEIGHTS.values())


def test_every_dimension_visible_with_raw_weight_contribution():
    c = _cands(_assurance([_f("open_contradiction", "blocking", "d")]),
              _cov("d", independent=3, record_count=3))[0]
    names = {d["name"] for d in c.dimensions}
    assert names == set(DIMENSION_WEIGHTS)
    for d in c.dimensions:
        assert "raw" in d and "weight" in d and "contribution" in d and "rationale" in d


def test_contribution_maths_is_exact():
    c = _cands(_assurance([_f("open_contradiction", "blocking", "d")]),
              _cov("d", independent=3, record_count=3))[0]
    for d in c.dimensions:
        if d["name"] in VALUE_DIMENSION_WEIGHTS:
            assert abs(d["contribution"] - round(d["raw"] * d["weight"], 6)) < 1e-9
        else:  # penalty -> negative
            assert abs(d["contribution"] + round(d["raw"] * d["weight"], 6)) < 1e-9


def test_priority_score_is_sum_of_contributions():
    c = _cands(_assurance([_f("open_contradiction", "blocking", "d")]),
              _cov("d", independent=3, record_count=3))[0]
    assert abs(c.priority_score - round(sum(d["contribution"] for d in c.dimensions), 6)) < 1e-9


def test_penalty_weights_are_positive_but_contributions_negative():
    for name, w in PENALTY_DIMENSION_WEIGHTS.items():
        assert w > 0
    c = _cands(_assurance([_f("readiness_without_coverage", "major", "d")]),
              _cov("d", independent=3, record_count=3))[0]  # repeated_confirmation w/ dup penalty
    dup = c.dimension("duplication_penalty")
    assert dup["raw"] > 0 and dup["contribution"] < 0


# ---- ranking drivers ------------------------------------------------------------------------

def test_blocker_clearance_affects_ranking():
    # same investigation type, one linked to a blocking finding, one to a minor finding
    a = _assurance([_f("dependent_evidence_reliance", "blocking", "d1"),
                    _f("dependent_evidence_reliance", "minor", "d2")])
    cov = {"domain_coverage": [
        {"domain": "d1", "gap_count": 1, "evidence_totals": {"independent": 1, "dependent": 3,
                                                             "record_count": 4}},
        {"domain": "d2", "gap_count": 1, "evidence_totals": {"independent": 1, "dependent": 3,
                                                             "record_count": 4}}],
        "content_fingerprint": "p27"}
    c = _cands(a, cov)
    d1 = next(x for x in c if x.domains == ("d1",))
    d2 = next(x for x in c if x.domains == ("d2",))
    assert d1.dimension("blocker_clearance")["contribution"] > \
        d2.dimension("blocker_clearance")["contribution"]
    assert d1.priority_score > d2.priority_score


def test_cross_finding_leverage_affects_ranking():
    one = _cands(_assurance([_f("dependent_evidence_reliance", "major", "d")]),
                _cov("d", independent=1, dependent=3, record_count=4))[0]
    multi = _cands(_assurance([_f("dependent_evidence_reliance", "major", "d"),
                               _f("unresolved_regression", "major", "d"),
                               _f("confirmed_good_unverified", "major", "d")]),
                  _cov("d", independent=1, dependent=3, record_count=4))[0]
    assert multi.dimension("cross_finding_leverage")["contribution"] > \
        one.dimension("cross_finding_leverage")["contribution"]
    assert multi.priority_score > one.priority_score


def test_information_gain_affects_ranking():
    disc = _cands(_assurance([_f("open_contradiction", "major", "d")]),
                 _cov("d", independent=3, record_count=3))[0]
    prov = _cands(_assurance([_f("missing_transfer_boundary", "major", "d")]),
                 _cov("d", independent=3, record_count=3))[0]
    assert disc.dimension("information_gain")["contribution"] > \
        prov.dimension("information_gain")["contribution"]


def test_effort_penalty_reduces_score():
    c = _cands(_assurance([_f("open_contradiction", "blocking", "d")]),
              _cov("d", independent=3, record_count=3))[0]
    cost = c.dimension("collection_cost")
    assert cost["contribution"] < 0


def test_dependency_penalty_applied_when_prerequisite_present():
    a = _assurance([_f("open_contradiction", "blocking", "d"),
                    _f("dependent_evidence_reliance", "moderate", "d")])
    c = _cands(a, _cov("d", independent=1, dependent=5, record_count=6))
    disc = next(x for x in c if x.investigation_type == T.CONTRADICTION_DISCRIMINATION.value)
    dep = disc.dimension("dependency_penalty")
    assert dep["raw"] > 0 and dep["contribution"] < 0 and disc.dependencies


def test_infeasible_cannot_rank_actionable():
    c = _cands(_assurance([_f("dependent_evidence_reliance", "blocking", "d")]),
              _cov("d", independent=0, dependent=0, record_count=0))[0]
    assert c.dimension("evidence_availability")["raw"] < 0.5
    assert c.priority_band not in ("blocking", "high", "medium", "low")  # deferred despite blocking


# ---- determinism ----------------------------------------------------------------------------

def test_ranking_deterministic_across_finding_shuffle():
    findings = [_f("open_contradiction", "blocking", "differential"),
                _f("single_context_reliance", "major", "springs"),
                _f("stale_knowledge", "major", "aero_balance"),
                _f("dependent_evidence_reliance", "moderate", "differential")]
    cov = {"domain_coverage": [
        {"domain": "differential", "gap_count": 1, "evidence_totals": {"independent": 3,
         "dependent": 0, "record_count": 3}},
        {"domain": "springs", "gap_count": 1, "evidence_totals": {"independent": 2, "dependent": 0,
         "record_count": 2}},
        {"domain": "aero_balance", "gap_count": 1, "evidence_totals": {"independent": 2,
         "dependent": 0, "record_count": 2}}], "content_fingerprint": "p27"}
    a1 = _assurance(findings)
    a2 = _assurance(list(reversed(findings)))
    r1 = build_assurance_engineering_priority(a1, {}, cov, {}, {}).to_dict()
    r2 = build_assurance_engineering_priority(a2, {}, cov, {}, {}).to_dict()
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    order1 = [c["candidate_id"] for c in r1["prioritised_candidates"] + r1["deferred_candidates"]]
    order2 = [c["candidate_id"] for c in r2["prioritised_candidates"] + r2["deferred_candidates"]]
    assert order1 == order2


def test_equal_score_tie_break_is_stable():
    # two structurally identical candidates in different (canonically ordered) domains
    a = _assurance([_f("single_context_reliance", "major", "springs"),
                    _f("single_context_reliance", "major", "anti_roll_bars")])
    cov = {"domain_coverage": [
        {"domain": "springs", "gap_count": 1, "evidence_totals": {"independent": 2, "dependent": 0,
         "record_count": 2}},
        {"domain": "anti_roll_bars", "gap_count": 1, "evidence_totals": {"independent": 2,
         "dependent": 0, "record_count": 2}}], "content_fingerprint": "p27"}
    from strategy.assurance_engineering_priority import _DOMAIN_ORDER
    c = _cands(a, cov)
    springs = next(x for x in c if x.domains == ("springs",))
    arb = next(x for x in c if x.domains == ("anti_roll_bars",))
    assert abs(springs.priority_score - arb.priority_score) < 1e-9  # equal score
    # the canonical domain order (whatever it is) breaks the tie deterministically
    order = [x.candidate_id for x in c]
    earlier = arb if _DOMAIN_ORDER.index("anti_roll_bars") < _DOMAIN_ORDER.index("springs") else springs
    later = springs if earlier is arb else arb
    assert order.index(earlier.candidate_id) < order.index(later.candidate_id)
