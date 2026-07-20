"""Phase 29 — pure domain unit tests: cause detection, resolution ladder, contradiction detection.

Core doctrine: never resolve by majority/average; dependent evidence can never defeat independent;
newer evidence does not auto-win (supersession needs later AND stronger); version/context mismatch
is visible; a contradiction may stay UNRESOLVED.
"""
from strategy.contradiction_cause import (
    ContradictionCause, context_difference_causes, CONTEXT_RESOLVING_CAUSES, cause_text,
)
from strategy.contradiction_resolution_status import (
    ContradictionStatus as S, CONTRADICTION_STATUS_PRIORITY, RESOLVED_STATUSES, resolve,
)
from strategy.knowledge_contradiction import detect_contradiction


def _rec(track="Fuji", car="GT-R", driver="L", compound="RH", gt7="1", disc="race",
         session="s1", outcome="confirmed_improvement", conf="high", date="2026-07-01"):
    return {"context": {"track": track, "car": car, "driver": driver, "compound": compound,
                        "gt7_version": gt7, "discipline": disc, "layout_id": "fc"},
            "changes": [{"field": "arb_front"}], "residual_states": [{"family": "rotation"}],
            "outcome_status": outcome, "confidence_level": conf, "test_session_id": session,
            "session_date": date}


# ---- enums / constants ---------------------------------------------------------------------

def test_19_causes_and_9_statuses():
    assert len(list(ContradictionCause)) == 19
    assert len(list(ContradictionStatus_all())) == 9
    for s in ContradictionStatus_all():
        assert s.value in CONTRADICTION_STATUS_PRIORITY


def ContradictionStatus_all():
    return list(S)


# ---- cause detection -----------------------------------------------------------------------

def test_context_difference_causes_from_disjoint_values():
    pos = {"track": {"fuji"}, "car": {"gt-r"}}
    neg = {"track": {"suzuka"}, "car": {"gt-r"}}
    causes = context_difference_causes(pos, neg)
    codes = {c["cause"] for c in causes}
    assert ContradictionCause.DIFFERENT_TRACK.value in codes
    assert ContradictionCause.DIFFERENT_CAR.value not in codes  # same car


def test_version_difference_is_a_context_resolving_cause():
    assert ContradictionCause.DIFFERENT_GT7_VERSION.value in CONTEXT_RESOLVING_CAUSES
    causes = context_difference_causes({"gt7_version": {"1.0"}}, {"gt7_version": {"1.49"}})
    assert any(c["cause"] == ContradictionCause.DIFFERENT_GT7_VERSION.value for c in causes)


def test_cause_text_nonempty():
    assert cause_text(ContradictionCause.DIFFERENT_TRACK.value)
    assert cause_text("nonsense") == "nonsense"


# ---- resolution ladder ---------------------------------------------------------------------

def test_context_difference_resolves_by_context():
    r = resolve({"context_causes": ({"cause": "different_track", "text": "x"},)})
    assert r["status"] == S.RESOLVED_BY_CONTEXT.value


def test_independent_beats_dependent_never_by_count():
    r = resolve({"context_causes": (), "independent_side": "positive",
                 "pos_side": {"sessions": 3}, "neg_side": {"sessions": 9}})
    # even though the negative side has MORE records, the independent side stands
    assert r["status"] == S.RESOLVED_BY_INDEPENDENCE.value
    assert "confirming" in r["standing_conclusion"]


def test_newer_does_not_auto_win_needs_stronger():
    # later side but NOT stronger -> not supersession
    r = resolve({"context_causes": (), "independent_side": "", "later_side": "negative",
                 "later_side_stronger": False, "pos_side": {"sessions": 2},
                 "neg_side": {"sessions": 1}})
    assert r["status"] != S.RESOLVED_BY_SUPERSESSION.value


def test_later_and_stronger_supersedes():
    r = resolve({"context_causes": (), "independent_side": "", "later_side": "negative",
                 "later_side_stronger": True, "pos_side": {"sessions": 1},
                 "neg_side": {"sessions": 3}})
    assert r["status"] == S.RESOLVED_BY_SUPERSESSION.value


def test_genuine_same_context_stays_unresolved():
    r = resolve({"context_causes": (), "independent_side": "", "later_side": "",
                 "later_side_stronger": False, "both_weak": False,
                 "pos_side": {"sessions": 3}, "neg_side": {"sessions": 3}})
    assert r["status"] == S.UNRESOLVED.value


def test_both_weak_is_insufficient():
    r = resolve({"context_causes": (), "both_weak": True,
                 "pos_side": {"sessions": 1}, "neg_side": {"sessions": 1}})
    assert r["status"] == S.UNRESOLVED_INSUFFICIENT_EVIDENCE.value


def test_resolved_statuses_membership():
    assert "resolved_by_context" in RESOLVED_STATUSES
    assert "unresolved" not in RESOLVED_STATUSES


# ---- detect_contradiction (end-to-end pure) ------------------------------------------------

def test_detect_genuine_same_context():
    pos = [_rec(session="c1", date="2026-07-01"), _rec(session="c2", date="2026-07-02")]
    neg = [_rec(session="r1", outcome="regression", date="2026-07-03"),
           _rec(session="r2", outcome="regression", date="2026-07-04")]
    c = detect_contradiction("differential", pos, neg)
    assert c.status == S.UNRESOLVED.value and c.is_open is True


def test_detect_context_explained():
    pos = [_rec(track="Fuji", session="c1"), _rec(track="Fuji", session="c2")]
    neg = [_rec(track="Suzuka", session="r1", outcome="regression"),
           _rec(track="Suzuka", session="r2", outcome="regression")]
    c = detect_contradiction("differential", pos, neg)
    assert c.status == S.RESOLVED_BY_CONTEXT.value and c.is_open is False
    assert any(x["cause"] == "different_track" for x in c.causes)


def test_detect_independence_confirming_stands():
    pos = [_rec(session="c1", conf="high"), _rec(session="c2", conf="high")]
    neg = [_rec(session="r1", outcome="regression", conf="low")]  # single low-confidence
    c = detect_contradiction("differential", pos, neg)
    assert c.status == S.RESOLVED_BY_INDEPENDENCE.value
    assert "confirming" in c.standing_conclusion


def test_detect_majority_does_not_decide():
    # many low-confidence single-session regressions must NOT outvote the independent confirms
    pos = [_rec(session="c1", conf="high"), _rec(session="c2", conf="high")]
    neg = [_rec(session="r1", outcome="regression", conf="low")]
    c = detect_contradiction("differential", pos, neg)
    assert c.status != S.UNRESOLVED.value
    assert "confirming" in c.standing_conclusion   # independent side stands, not the larger count
