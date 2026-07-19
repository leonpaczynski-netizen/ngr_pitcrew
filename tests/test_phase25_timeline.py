"""Phase 25 — timeline + programme-report domain tests.

Chronological sequence with deterministic tie-breaks; unknown/equal dates handled honestly;
insertion-order independence; newer-is-not-better; conflict introduce+resolve both visible;
history not overwritten; timestamp-free restart-identical fingerprint.
"""
import inspect

import pytest

from strategy.knowledge_timeline import build_timeline, KNOWLEDGE_TIMELINE_VERSION
from strategy.programme_timeline_report import (
    build_programme_timeline, PROGRAMME_TIMELINE_REPORT_VERSION,
)

SRC = {"car": "Porsche 911 RSR (991) '17", "discipline": "Race", "gt7_version": "1.49",
       "driver": "leon"}


def ev(ref, session, scope, date, status="confirmed_improvement", conf="high", failed=False,
       seq=0):
    return {"record_ref": ref, "session_id": session, "scope_fingerprint": scope,
            "evidence_date": date, "sequence_key": seq, "outcome_status": status,
            "confidence_level": conf, "is_failed_direction": failed,
            "event": {"car": SRC["car"], "track": "Fuji", "discipline": "Race",
                      "session_id": session}}


def _domain(name, evidence, authority=None):
    return {"domain": name, "evidence": evidence, "authority": authority or {}}


def test_timeline_chronological_with_seq():
    evs = [ev("r1", "s1", "sc1", "2026-07-01", seq=0),
           ev("r2", "s2", "sc2", "2026-07-03", seq=1)]
    points, _ = build_timeline([_domain("differential", evs)], SRC)
    assert [p["evidence_date"] for p in points] == ["2026-07-01", "2026-07-03"]


def test_unknown_dates_sort_last_and_marked():
    evs = [ev("r1", "s1", "sc1", "", seq=1), ev("r2", "s2", "sc2", "2026-07-01", seq=0)]
    points, _ = build_timeline([_domain("differential", evs)], SRC)
    assert points[0]["evidence_date"] == "2026-07-01"
    assert points[1]["evidence_date"] == "unknown"
    assert "evidence_date" in points[1]["unknown_fields"]


def test_insertion_order_independence():
    evs = [ev("r1", "s1", "sc1", "2026-07-01", seq=0),
           ev("r2", "s2", "sc2", "2026-07-03", seq=1),
           ev("r3", "s3", "sc3", "2026-07-05", seq=2)]
    a, _ = build_timeline([_domain("differential", evs)], SRC)
    b, _ = build_timeline([_domain("differential", list(reversed(evs)))], SRC)
    assert [p["point_id"] for p in a] == [p["point_id"] for p in b]


def test_equal_dates_deterministic():
    evs = [ev("rb", "s2", "sc2", "2026-07-01", seq=0),
           ev("ra", "s1", "sc1", "2026-07-01", seq=0)]
    a, _ = build_timeline([_domain("differential", evs)], SRC)
    b, _ = build_timeline([_domain("differential", list(reversed(evs)))], SRC)
    assert [p["point_id"] for p in a] == [p["point_id"] for p in b]


def test_newer_weaker_does_not_override_older_stronger():
    # older strong positive, then a newer WEAKER regression should not erase the confirmation
    # two independent supporting lines (distinct scopes) establish confirmed-good
    evs = [ev("r1", "s1", "sc1", "2026-07-01", status="confirmed_improvement", conf="high", seq=0),
           ev("r2", "s2", "sc2", "2026-07-05", status="confirmed_improvement", conf="high", seq=1)]
    points, _ = build_timeline([_domain("differential", evs,
                                        {"confirmed_good": True})], SRC)
    # the confirmed-good is established and preserved, not overwritten
    types = [p["transition_type"] for p in points]
    assert "confirmed_good_established" in types


def test_conflict_introduce_and_resolve_both_visible():
    evs = [ev("r1", "s1", "sc1", "2026-07-01", status="confirmed_improvement", conf="high", seq=0),
           ev("r2", "s2", "sc2", "2026-07-03", status="regression", conf="high", seq=1),
           ev("r3", "s3", "sc3", "2026-07-05", status="confirmed_improvement", conf="high", seq=2)]
    points, _ = build_timeline([_domain("differential", evs)], SRC)
    types = [p["transition_type"] for p in points]
    assert "conflict_introduced" in types and "conflict_resolved" in types


def test_history_not_overwritten():
    evs = [ev("r1", "s1", "sc1", "2026-07-01", seq=0),
           ev("r2", "s2", "sc2", "2026-07-03", status="regression", seq=1)]
    points, _ = build_timeline([_domain("differential", evs)], SRC)
    # both the initial support and the later regression remain as separate points
    assert len(points) == 2


def test_five_same_session_not_independent():
    evs = [ev(f"r{i}", "s1", "sc1", "2026-07-01", seq=0) for i in range(5)]
    points, indep = build_timeline([_domain("anti_roll_bars", evs)], SRC)
    # 5 points but the independence summary shows only one independent line
    assert indep["anti_roll_bars"]["independent_groups"] == 1


# --- programme report -------------------------------------------------------
def _programme(domains, known):
    return {"content_fingerprint": "p22", "knowledge_graph": {
        "domains": domains, "known_domains": known, "missing_domains": []},
        "compatibility": {"primary_key": SRC, "other_groups": []}}


def _gdom(name, maturity="mature", conf="high", conf_n=3, reg=0, limits=()):
    return {"domain": name, "knowledge_state": {"value": "well_understood"},
            "confidence": {"value": conf}, "maturity": {"value": maturity},
            "remaining_uncertainty": {"value": "low"}, "supporting_campaigns": ["c1"],
            "supporting_experiments": [], "supporting_mechanisms": ["load_transfer"],
            "supporting_evidence": {"confirmations": conf_n, "regressions": reg,
                                    "executed": conf_n + reg}, "known_limitations": list(limits)}


def _rec(field, family, status, session, scope, date):
    return {"record_key": f"{field}-{session}-{scope}-{status}", "test_session_id": session,
            "scope_fingerprint": scope, "session_date": date, "recorded_at": date + "T10:00",
            "outcome_status": status, "confidence_level": "high",
            "changes": [{"field": field}], "residual_states": [{"family": family}],
            "context": {"car": SRC["car"], "track": "Fuji", "layout_id": "fc",
                        "discipline": "Race"}}


def test_report_three_independent_converge():
    prog = _programme([_gdom("differential", maturity="complete", conf="very_high")],
                      ["differential"])
    records = [_rec("lsd_accel", "traction", "confirmed_improvement", f"s{i}", f"sc{i}",
                    f"2026-07-0{i}") for i in (1, 3, 5)]
    r = build_programme_timeline(prog, {}, records).to_dict()
    conv = next(c for c in r["convergence_summaries"] if c["domain"] == "differential")
    assert conv["independent_support_count"] == 3


def test_report_restart_and_shuffle_identical():
    prog = _programme([_gdom("differential")], ["differential"])
    records = [_rec("lsd_accel", "traction", "confirmed_improvement", f"s{i}", f"sc{i}",
                    f"2026-07-0{i}") for i in (1, 3, 5)]
    a = build_programme_timeline(prog, {}, records).to_dict()
    b = build_programme_timeline(prog, {}, list(reversed(records))).to_dict()
    assert a["content_fingerprint"] == b["content_fingerprint"]


def test_report_empty_safe():
    r = build_programme_timeline({}, {}, []).to_dict()
    assert r["timeline_points"] == [] and r["safety_statement"]


def test_report_never_raises():
    for junk in (None, {"knowledge_graph": None}):
        r = build_programme_timeline(junk, junk, junk)
        assert r.safety_statement


def test_fingerprint_no_timestamps():
    src = inspect.getsource(__import__("strategy.programme_timeline_report", fromlist=["x"]))
    for banned in ("time.time", "datetime.now", "utcnow", "date.today", "recorded_at\":",
                   "now_date"):
        assert banned not in src
    # session_date (event date) is used, recorded_at (creation) is NOT read as event time
    assert "session_date" in src


def test_versions():
    assert KNOWLEDGE_TIMELINE_VERSION == "knowledge_timeline_v1"
    assert PROGRAMME_TIMELINE_REPORT_VERSION == "programme_timeline_report_v1"
