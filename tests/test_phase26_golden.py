"""Phase 26 — golden scenarios (the 10 mandated behaviours).

1. Old but independently confirmed compatible knowledge remains CURRENT.
2. Unknown date produces INSUFFICIENT_DATE_EVIDENCE.
3. Explicit GT7 version change marks version-sensitive knowledge for re-validation.
4. Version-insensitive knowledge is not automatically invalidated.
5. Track/layout change narrows knowledge to investigation aid.
6. Conflict weakens certainty without deleting history.
7. Regression marks the tested direction weakened or retired.
8. Confirmed-good behaviour remains protected when an unrelated direction regresses.
9. Superseded knowledge remains visible but inactive.
10. Restart and shuffled input remain identical.
"""
from strategy.revalidation_status import KnowledgeFreshnessStatus as F, classify_revalidation
from strategy.programme_revalidation_report import build_revalidation_report


def _classify(**sig):
    sig.setdefault("domain", "differential")
    return classify_revalidation(sig, {"gt7_version": "1.0"})


# 1
def test_g1_old_independent_compatible_stays_current():
    st = _classify(convergence_status="strongly_converged", independent_count=3,
                   last_known_date="2018-01-01")
    assert st.freshness_status == F.CURRENT.value
    assert st.knowledge_still_usable is True


# 2
def test_g2_unknown_date_insufficient_date_evidence():
    st = _classify(all_dates_unknown=True)
    assert st.freshness_status == F.INSUFFICIENT_DATE_EVIDENCE.value
    assert st.knowledge_still_usable is True  # not deleted; still usable as an aid


# 3
def test_g3_version_change_revalidates_version_sensitive():
    st = _classify(version_sensitive=True, version_changed=True)
    assert st.freshness_status == F.INVALIDATED_BY_VERSION_CHANGE.value
    assert any(r["reason"] == "gt7_version_changed" for r in st.reasons)


# 4
def test_g4_version_insensitive_not_auto_invalidated():
    st = _classify(version_sensitive=False, version_changed=True,
                   convergence_status="strongly_converged")
    assert st.freshness_status == F.CURRENT.value


# 5
def test_g5_track_layout_change_narrows_to_aid():
    st = _classify(convergence_status="stable_but_context_bound", is_context_bound=True,
                   context_changed_fields=("track", "layout"))
    assert st.freshness_status == F.CURRENT_BUT_CONTEXT_BOUND.value
    assert st.investigation_aid_only is True
    codes = {r["reason"] for r in st.reasons}
    assert {"track_changed", "layout_changed"} <= codes


# 6
def test_g6_conflict_weakens_without_deleting():
    st = _classify(has_conflict=True, convergence_status="conflicting")
    assert st.freshness_status == F.WEAKENED_BY_CONFLICT.value
    assert st.knowledge_still_usable is True  # history retained


# 7
def test_g7_regression_weakens_or_retires():
    weakened = _classify(has_regression=True, convergence_status="regressed")
    assert weakened.freshness_status == F.WEAKENED_BY_REGRESSION.value
    retired = _classify(retired_directions=("lsd_up",), has_regression=True,
                        convergence_status="regressed")
    assert retired.freshness_status == F.RETIRED.value


# 8
def test_g8_confirmed_good_protected_when_unrelated_direction_regresses():
    st = _classify(is_confirmed_good=True, has_regression=True, retired_directions=("other",),
                   convergence_status="regressed")
    assert st.freshness_status == F.CURRENT.value
    assert st.confirmed_good is True


# 9
def test_g9_superseded_visible_but_inactive():
    st = _classify(is_superseded=True, convergence_status="superseded")
    assert st.freshness_status == F.SUPERSEDED.value
    assert st.knowledge_still_usable is False
    # still present in the report (visible), not erased
    assert st.to_dict()["domain"] == "differential"


# 10
def test_g10_restart_and_shuffle_identical():
    def conv(domain, **kw):
        base = {"domain": domain, "convergence_status": "strongly_converged",
                "independent_support_count": 3, "dependent_support_count": 0,
                "regression_count": 0, "conflict_count": 0, "transfer_limitations": [],
                "retired_directions": [], "confirmed_good": False,
                "current_maturity": "established", "current_confidence": "high",
                "compatible_contexts": 2}
        base.update(kw)
        return base
    summaries = [conv("differential"), conv("weight_transfer", convergence_status="conflicting",
                                            conflict_count=1),
                 conv("aero_balance", convergence_status="superseded")]
    tl_a = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1.0",
                                 "driver": "L"},
            "convergence_summaries": summaries,
            "timeline_points": [{"knowledge_domain": "differential", "evidence_date": "2026-01-01"}],
            "content_fingerprint": "p25:x"}
    tl_b = dict(tl_a)
    tl_b["convergence_summaries"] = list(reversed(summaries))  # shuffled input order
    prog = {"compatibility": {}, "content_fingerprint": "p22:y"}
    a = build_revalidation_report(tl_a, prog).to_dict()
    b = build_revalidation_report(tl_b, prog).to_dict()
    assert a["content_fingerprint"] == b["content_fingerprint"]
    assert [i["domain"] for i in a["items"]] == [i["domain"] for i in b["items"]]
