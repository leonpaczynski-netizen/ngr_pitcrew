"""Phase 61 — restart recovery + event-switch protection (task items 24-25)."""
from __future__ import annotations

from strategy.live_activity import LiveActivityState as L
from strategy.live_restart_recovery import resolve_live_restart, is_stale_snapshot


# --- restart recovery ------------------------------------------------------

def test_restart_never_starts_a_live_run():
    r = resolve_live_restart(selected_event="c1", selected_activity="exp")
    assert r.nav.active_event_id == "c1" and r.nav.selected_activity_id == "exp"
    assert r.nav.started is False and r.nav.entered_live is False  # restart never auto-enters/starts


def test_restart_never_restores_interrupted_as_complete():
    r = resolve_live_restart(selected_event="c1", interrupted_activity_id="exp",
                             interrupted_state=L.COMPLETED)
    assert r.resume.interrupted_state == L.INTERRUPTED  # downgraded — no fabricated completion


def test_restart_preserves_pending_binding():
    r = resolve_live_restart(selected_event="c1", selected_activity="exp", pending_binding=True)
    assert r.resume.pending_binding is True and "binding" in r.note


def test_restart_preserves_pending_debrief():
    r = resolve_live_restart(selected_event="c1", selected_activity="exp", pending_debrief=True)
    assert r.resume.pending_debrief is True and "debrief" in r.note


def test_restart_deterministic():
    a = resolve_live_restart(selected_event="c1", selected_activity="exp")
    b = resolve_live_restart(selected_event="c1", selected_activity="exp")
    assert a.fingerprint == b.fingerprint


# --- event-switch protection -----------------------------------------------

def test_stale_snapshot_for_switched_event_is_rejected():
    # a snapshot for event A cannot update event B
    assert is_stale_snapshot(snapshot_event="A", snapshot_activity="x",
                             current_event="B", current_activity="x") is True
    assert is_stale_snapshot(snapshot_event="A", snapshot_activity="x",
                             current_event="A", current_activity="y") is True   # activity switched
    assert is_stale_snapshot(snapshot_event="A", snapshot_activity="x",
                             current_event="A", current_activity="x") is False  # current -> accepted
