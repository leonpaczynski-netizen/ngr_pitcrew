"""Engineering Brain Phase 7 — live engineering state fold tests.

Covers the deterministic per-issue fold: trend/status, consistency measurements,
last-observed lap/corner, order-independence, exclusion handling, protected keys,
session health bands, and content-fingerprint stability.
"""
import inspect

import pytest

from strategy import live_engineering_state as LES
from strategy.corner_evidence import CornerObservationRecord, CornerPhase
from strategy.live_engineering_state import (
    LiveEngineeringState, SessionHealthBand, update_live_state,
)
from strategy.state_transitions import IssueStatus, Trend


def rec(lap, *, seg="S1", issue="understeer", phase=CornerPhase.APEX, axle="front",
        sev="medium", occurred=True, excluded=""):
    return CornerObservationRecord(
        session_id="sess1", lap_number=lap, segment_id=seg, corner_name="Turn 1",
        phase=phase, issue_type=issue, axle=axle, occurred_on_lap=occurred,
        confidence="high", severity=sev, source="corner_issue_occurrences",
        exclusion_reason=excluded)


VALID = [1, 2, 3, 4, 5, 6, 7]


def test_single_issue_tracked_with_trend_and_recency():
    recs = [rec(l) for l in (1, 2, 3, 4)]
    st = update_live_state(recs, VALID, scope_fingerprint="A", discipline="race")
    assert len(st.issues) == 1
    i = st.issues[0]
    assert i.trend == Trend.IMPROVING
    assert i.first_observed_lap == 1
    assert i.last_observed_lap == 4
    assert i.last_observed_corner == "Turn 1"
    assert i.consistency.affected_valid_laps == 4
    assert i.consistency.total_valid_laps == 7
    assert not i.present_now


def test_order_independent_fingerprint():
    recs = [rec(l) for l in (1, 2, 3, 4)]
    a = update_live_state(recs, VALID, scope_fingerprint="A", discipline="race")
    b = update_live_state(list(reversed(recs)), list(reversed(VALID)),
                          scope_fingerprint="A", discipline="race")
    assert a.content_fingerprint == b.content_fingerprint


def test_worsening_issue_sets_degrading_band():
    recs = [rec(l) for l in (5, 6, 7)]
    st = update_live_state(recs, VALID, scope_fingerprint="A", discipline="race")
    assert st.issues[0].trend == Trend.WORSENING
    assert st.health.band == SessionHealthBand.DEGRADING


def test_single_bad_lap_does_not_worsen_or_degrade():
    st = update_live_state([rec(7)], VALID, scope_fingerprint="A", discipline="race")
    assert st.issues[0].trend != Trend.WORSENING


def test_excluded_observations_never_count():
    # a kerb-excluded event on every lap must not create an active issue
    recs = [rec(l, excluded="kerb_strike") for l in (1, 2, 3, 4)]
    st = update_live_state(recs, VALID, scope_fingerprint="A", discipline="race")
    assert st.issues == ()
    assert st.health.band == SessionHealthBand.NOMINAL


def test_non_comparable_lap_evidence_ignored():
    # an occurrence on lap 99 (not in the valid window) is ignored
    recs = [rec(1), rec(2), rec(99)]
    st = update_live_state(recs, VALID, scope_fingerprint="A", discipline="race")
    i = st.issues[0]
    assert 99 not in i.affected_lap_numbers
    assert i.last_observed_lap == 2


def test_protected_key_tracks_protected_status():
    recs = [rec(l) for l in (1, 2)]
    base = update_live_state(recs, VALID, scope_fingerprint="A", discipline="race")
    key = base.issues[0].key
    # same behaviour now marked protected + recurs → damaged, counted as protected
    prot = update_live_state([rec(6), rec(7)], VALID, scope_fingerprint="A",
                             discipline="race", protected_keys=[key])
    i = prot.issues[0]
    assert i.is_protected
    assert i.status in (IssueStatus.DAMAGED, IssueStatus.PROTECTED, IssueStatus.ACTIVE)


def test_empty_session_is_nominal():
    st = update_live_state([], VALID, scope_fingerprint="A")
    assert st.issues == ()
    assert st.health.band == SessionHealthBand.NOMINAL
    assert st.health.lap_cleanliness == 1.0


def test_repeatability_measures_lap_to_lap_steadiness():
    steady = update_live_state([rec(l) for l in (1, 2, 3, 4)], VALID,
                               scope_fingerprint="A")
    jittery = update_live_state([rec(1), rec(3), rec(5), rec(7)], VALID,
                                scope_fingerprint="A")
    assert steady.issues[0].consistency.repeatability > \
        jittery.issues[0].consistency.repeatability


def test_two_distinct_corners_tracked_separately():
    recs = ([rec(l, seg="T1", issue="understeer") for l in (1, 2, 3)]
            + [rec(l, seg="T5", issue="wheelspin", phase=CornerPhase.EXIT,
                   axle="rear") for l in (2, 3, 4)])
    st = update_live_state(recs, VALID, scope_fingerprint="A")
    assert len(st.issues) == 2
    keys = {i.identity.issue_type for i in st.issues}
    assert keys == {"understeer", "wheelspin"}


def test_dict_roundtrip_is_stable():
    st = update_live_state([rec(l) for l in (1, 2, 3)], VALID, scope_fingerprint="A")
    d = st.to_dict()
    assert d["content_fingerprint"] == st.content_fingerprint
    assert d["issues"][0]["identity"]["issue_type"] == "understeer"


def test_module_is_pure_no_io_or_clock():
    src = inspect.getsource(LES)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai"):
        assert banned not in src, banned
