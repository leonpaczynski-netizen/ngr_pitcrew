"""Phase 25 — evidence-independence domain tests.

Same record does not double-count; same session is dependent; same campaign is partially
independent; separate compatible sessions are independent; unknown lineage stays unknown.
"""
import inspect

import pytest

from strategy.evidence_independence import (
    EvidenceIndependence, assess_independence, independence_summary,
    EVIDENCE_INDEPENDENCE_VERSION,
)


def rec(ref, session, scope):
    return {"record_ref": ref, "session_id": session, "scope_fingerprint": scope}


def test_first_record_independent():
    a = assess_independence([rec("r1", "s1", "sc1")])
    assert a[0].independence == EvidenceIndependence.INDEPENDENT.value


def test_same_record_not_double_counted():
    a = assess_independence([rec("r1", "s1", "sc1"), rec("r1", "s1", "sc1")])
    assert a[1].independence == EvidenceIndependence.SAME_SOURCE_RECORD.value


def test_same_session_is_dependent():
    a = assess_independence([rec("r1", "s1", "sc1"), rec("r2", "s1", "sc2")])
    assert a[1].independence == EvidenceIndependence.SAME_SESSION.value


def test_same_campaign_partially_independent():
    # same scope, different session -> partially independent
    a = assess_independence([rec("r1", "s1", "sc1"), rec("r2", "s2", "sc1")])
    assert a[1].independence == EvidenceIndependence.SAME_CAMPAIGN.value


def test_separate_sessions_and_scopes_independent():
    a = assess_independence([rec("r1", "s1", "sc1"), rec("r2", "s2", "sc2")])
    assert a[1].independence == EvidenceIndependence.INDEPENDENT.value


def test_no_session_no_scope_unknown():
    a = assess_independence([rec("r1", "", ""), rec("r2", "", "")])
    assert a[0].independence == EvidenceIndependence.UNKNOWN.value


def test_session_without_scope_partial():
    a = assess_independence([rec("r1", "s1", ""), rec("r2", "s2", "")])
    assert a[1].independence == EvidenceIndependence.PARTIALLY_INDEPENDENT.value


def test_summary_counts_independent_lines():
    a = [x.to_dict() for x in assess_independence([
        rec("r1", "s1", "sc1"), rec("r2", "s2", "sc2"), rec("r3", "s3", "sc3")])]
    s = independence_summary(a)
    assert s["independent_groups"] == 3 and s["total"] == 3


def test_summary_dependent_repeats_do_not_inflate():
    a = [x.to_dict() for x in assess_independence([
        rec("r1", "s1", "sc1"), rec("r2", "s1", "sc1"), rec("r3", "s1", "sc1")])]
    s = independence_summary(a)
    # one scope -> one independent group despite three records
    assert s["independent_groups"] == 1


def test_enum_complete():
    vals = {e.value for e in EvidenceIndependence}
    assert vals == {"independent", "partially_independent", "same_session", "same_campaign",
                    "same_source_record", "derived_from_existing_conclusion", "unknown"}


def test_deterministic():
    recs = [rec("r1", "s1", "sc1"), rec("r2", "s2", "sc1")]
    assert [x.to_dict() for x in assess_independence(recs)] == \
        [x.to_dict() for x in assess_independence(recs)]


def test_never_raises_on_garbage():
    for junk in (None, [None, 5], [{"record_ref": None}]):
        a = assess_independence(junk)
        assert isinstance(a, tuple)


def test_no_forbidden_imports():
    src = inspect.getsource(__import__("strategy.evidence_independence", fromlist=["x"]))
    for banned in ("import sqlite3", "PyQt6", "import random", "random.", "datetime.now",
                   "date.today", "time.time", "from data.session_db", "sklearn", "numpy"):
        assert banned not in src
    assert EVIDENCE_INDEPENDENCE_VERSION == "evidence_independence_v1"
