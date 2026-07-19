"""Phase 29 — golden scenarios (10 mandated behaviours).

1.  A genuine same-context disagreement stays UNRESOLVED (the report says we don't know).
2.  A context difference resolves the disagreement (both hold in their own contexts).
3.  A GT7 version mismatch is surfaced as a visible cause, not hidden.
4.  Independent evidence outweighs dependent evidence.
5.  A larger count of dependent observations never defeats an independent conclusion (no majority).
6.  Newer evidence does not automatically win (supersession needs later AND stronger).
7.  Later AND stronger evidence supersedes the earlier conclusion.
8.  Both-weak sides yield insufficient-evidence, not a false resolution.
9.  A contradiction requires BOTH a confirming and a regressing record (no fabrication).
10. No fabricated domains; restart + shuffled input identical.
"""
from strategy.contradiction_resolution_status import ContradictionStatus as S
from strategy.knowledge_contradiction import detect_contradiction
from strategy.programme_contradiction_report import build_programme_contradiction_report


def _rec(track="Fuji", gt7="1", session="s1", outcome="confirmed_improvement", conf="high",
         date="2026-07-01", field="arb_front", family="rotation"):
    return {"context": {"track": track, "car": "GT-R", "driver": "L", "compound": "RH",
                        "gt7_version": gt7, "discipline": "race", "layout_id": "fc"},
            "changes": [{"field": field}], "residual_states": [{"family": family}],
            "outcome_status": outcome, "confidence_level": conf, "test_session_id": session,
            "session_date": date}


# 1
def test_g1_genuine_stays_unresolved():
    c = detect_contradiction("differential",
                             [_rec(session="c1"), _rec(session="c2")],
                             [_rec(session="r1", outcome="regression"),
                              _rec(session="r2", outcome="regression")])
    assert c.status == S.UNRESOLVED.value and c.is_open


# 2
def test_g2_context_resolves():
    c = detect_contradiction("differential",
                             [_rec(track="Fuji", session="c1"), _rec(track="Fuji", session="c2")],
                             [_rec(track="Suzuka", session="r1", outcome="regression"),
                              _rec(track="Suzuka", session="r2", outcome="regression")])
    assert c.status == S.RESOLVED_BY_CONTEXT.value and not c.is_open


# 3
def test_g3_version_mismatch_surfaced():
    c = detect_contradiction("differential",
                             [_rec(gt7="1.0", session="c1"), _rec(gt7="1.0", session="c2")],
                             [_rec(gt7="1.49", session="r1", outcome="regression"),
                              _rec(gt7="1.49", session="r2", outcome="regression")])
    assert any(x["cause"] == "different_gt7_version" for x in c.causes)


# 4
def test_g4_independent_beats_dependent():
    c = detect_contradiction("differential",
                             [_rec(session="c1", conf="high"), _rec(session="c2", conf="high")],
                             [_rec(session="r1", outcome="regression", conf="low")])
    assert c.status == S.RESOLVED_BY_INDEPENDENCE.value


# 5
def test_g5_majority_never_decides():
    # 5 dependent regressions in ONE low-confidence session vs 2 independent confirms
    neg = [_rec(session="r1", outcome="regression", conf="low", date=f"2026-07-0{i}")
           for i in range(1, 6)]
    c = detect_contradiction("differential",
                             [_rec(session="c1", conf="high"), _rec(session="c2", conf="high")], neg)
    assert c.status == S.RESOLVED_BY_INDEPENDENCE.value
    assert "confirming" in c.standing_conclusion


# 6
def test_g6_newer_does_not_auto_win():
    # later regression but same strength (single session each) -> not superseded
    c = detect_contradiction("differential",
                             [_rec(session="c1", conf="low", date="2026-07-01")],
                             [_rec(session="r1", outcome="regression", conf="low",
                                   date="2026-07-09")])
    assert c.status != S.RESOLVED_BY_SUPERSESSION.value


# 7
def test_g7_later_and_stronger_supersedes():
    c = detect_contradiction("differential",
                             [_rec(session="c1", conf="low", date="2026-07-01")],
                             [_rec(session="r1", outcome="regression", conf="high",
                                   date="2026-07-08"),
                              _rec(session="r2", outcome="regression", conf="high",
                                   date="2026-07-09")])
    assert c.status == S.RESOLVED_BY_SUPERSESSION.value
    assert "regressing" in c.standing_conclusion


# 8
def test_g8_both_weak_insufficient():
    c = detect_contradiction("differential",
                             [_rec(session="c1", conf="low")],
                             [_rec(session="r1", outcome="regression", conf="low")])
    assert c.status == S.UNRESOLVED_INSUFFICIENT_EVIDENCE.value


# 9
def test_g9_requires_both_sides():
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"}, "content_fingerprint": "p25"}
    # only confirmations -> no contradiction
    recs = [_rec(session=f"c{i}") for i in range(3)]
    r = build_programme_contradiction_report(tl, {"content_fingerprint": "p22"}, recs).to_dict()
    assert r["contradictions"] == []


# 10
def test_g10_no_fabricated_domains_restart_shuffle_identical():
    tl = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1",
                               "driver": "L"}, "content_fingerprint": "p25"}
    recs = [_rec(session="c1"), _rec(session="c2"),
            _rec(session="r1", outcome="regression"), _rec(session="r2", outcome="regression"),
            _rec(field="lsd_accel", family="traction", session="lc1"),
            _rec(field="lsd_accel", family="traction", session="lr1", outcome="regression")]
    a = build_programme_contradiction_report(tl, {"content_fingerprint": "p22"}, recs).to_dict()
    b = build_programme_contradiction_report(tl, {"content_fingerprint": "p22"},
                                             list(reversed(recs))).to_dict()
    assert a["content_fingerprint"] == b["content_fingerprint"]
    assert [c["domain"] for c in a["contradictions"]] == [c["domain"] for c in b["contradictions"]]
    # only domains with BOTH a confirm and a regression appear
    assert all(c["positive_summary"]["record_count"] > 0 and c["negative_summary"]["record_count"] > 0
               for c in a["contradictions"])
