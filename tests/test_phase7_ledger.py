"""Engineering Brain Phase 7 — session development ledger tests.

Locks the append-only + determinism contract: appending snapshots one at a time is
byte-identical to a from-scratch rebuild; events are never rewritten/deleted;
sequence numbers are contiguous; the right event types fire.
"""
import inspect

import pytest

from strategy import session_development as SD
from strategy.corner_evidence import CornerObservationRecord, CornerPhase
from strategy.live_engineering_state import update_live_state
from strategy.session_development import (
    LedgerEventType, append_snapshot, build_session_ledger, empty_ledger,
)


def rec(lap, *, seg="S1", issue="understeer", phase=CornerPhase.APEX, axle="front"):
    return CornerObservationRecord(
        session_id="sess1", lap_number=lap, segment_id=seg, corner_name="Turn 1",
        phase=phase, issue_type=issue, axle=axle, occurred_on_lap=True,
        confidence="high", severity="medium", source="corner_issue_occurrences")


def _session_snapshots(affected_laps, total=7, **kw):
    all_recs = [rec(l, **kw) for l in affected_laps]
    snaps = []
    for upto in range(1, total + 1):
        valid = list(range(1, upto + 1))
        recs = [r for r in all_recs if r.lap_number <= upto]
        st = update_live_state(recs, valid, scope_fingerprint="A", discipline="race",
                               session_id="sess1")
        snaps.append((upto, st))
    return snaps


def test_append_equals_rebuild():
    snaps = _session_snapshots((1, 2, 3))
    full = build_session_ledger(snaps, session_id="sess1", scope_fingerprint="A")
    inc = empty_ledger(session_id="sess1", scope_fingerprint="A")
    prev = None
    for lap, st in snaps:
        inc = append_snapshot(inc, st, prev_state=prev, lap_number=lap)
        prev = st
    assert inc.content_fingerprint == full.content_fingerprint
    assert inc.event_count == full.event_count


def test_sequence_numbers_contiguous():
    led = build_session_ledger(_session_snapshots((1, 2, 3)))
    assert [e.sequence_no for e in led.events] == list(range(led.event_count))


def test_append_is_immutable():
    snaps = _session_snapshots((1, 2, 3))
    led = build_session_ledger(snaps)
    before = led.event_count
    before_events = led.events
    _ = append_snapshot(led, snaps[-1][1], prev_state=snaps[-1][1], lap_number=8)
    assert led.event_count == before
    assert led.events is before_events   # original tuple untouched


def test_detects_and_resolves():
    led = build_session_ledger(_session_snapshots((1, 2, 3)))
    types = {e.event_type for e in led.events}
    assert LedgerEventType.ISSUE_DETECTED in types
    assert LedgerEventType.ISSUE_RESOLVED in types


def test_regression_event_fires_when_issue_reappears():
    # affected 1,2,3 then clears then reappears strongly 6,7 → regressed at the tail
    led = build_session_ledger(_session_snapshots((1, 2, 3, 6, 7)))
    seqs = [e.event_type for e in led.events]
    assert LedgerEventType.ISSUE_REGRESSED in seqs or \
        LedgerEventType.STATUS_CHANGED in seqs


def test_empty_ledger_has_stable_fingerprint():
    a = empty_ledger(session_id="s", scope_fingerprint="A")
    b = empty_ledger(session_id="s", scope_fingerprint="A")
    assert a.content_fingerprint == b.content_fingerprint
    assert a.event_count == 0


def test_events_for_issue_filters():
    led = build_session_ledger(_session_snapshots((1, 2, 3)))
    keys = {e.issue_key for e in led.events if e.issue_key}
    assert keys
    k = next(iter(keys))
    assert all(e.issue_key == k for e in led.events_for(k))


def test_module_is_pure_no_io_or_clock():
    src = inspect.getsource(SD)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai"):
        assert banned not in src, banned
