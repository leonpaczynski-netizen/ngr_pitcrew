"""Phase 58 — voice status, single advisory, garage return (task items 19-20, 23, 27-28)."""
from __future__ import annotations

from strategy.shadow_advisory import LiveValidationReadiness as LR
from strategy.ngr_live_pit_wall import VoiceStatus as VS
from strategy.activity_binding import DebriefKind
from strategy.live_runtime_authority import (
    LiveRuntimeTransition as TR, LiveRuntimeTransitionResult)
from strategy.live_session_detection import SessionEndDetection, SessionEndState
from strategy.live_pit_wall_integration import (
    derive_voice_status, coordinate_single_advisory, resolve_garage_return, GarageReturnChoice as GC,
)


# --- voice status ----------------------------------------------------------

def test_voice_disabled_by_default():
    assert derive_voice_status(enabled=False, readiness_value=LR.VOICE_ELIGIBLE.value) == VS.DISABLED


def test_voice_gated_below_eligible():
    assert derive_voice_status(enabled=True, readiness_value=LR.NOT_READY.value) == VS.GATED


def test_voice_eligible_only_via_gate():
    assert derive_voice_status(enabled=True, readiness_value=LR.VOICE_ELIGIBLE.value) == VS.ELIGIBLE
    # a UI cannot manufacture ELIGIBLE without the gate readiness
    assert derive_voice_status(enabled=True, readiness_value="anything_else") == VS.GATED


def test_voice_active_and_muted_and_failure():
    assert derive_voice_status(enabled=True, readiness_value=LR.VOICE_ELIGIBLE.value, speaking=True) == VS.ACTIVE
    assert derive_voice_status(enabled=True, readiness_value=LR.VOICE_ELIGIBLE.value, muted=True) == VS.MUTED
    assert derive_voice_status(enabled=True, adapter_health="failed") == VS.ADAPTER_FAILURE


# --- single advisory -------------------------------------------------------

def test_single_advisory_picks_highest_priority_delivered():
    decisions = [{"delivered": True, "priority": 1, "message": "keep it tidy"},
                 {"delivered": True, "priority": 5, "message": "brake earlier T1"},
                 {"delivered": False, "priority": 9, "message": "not delivered"}]
    assert coordinate_single_advisory(decisions, suppressed=False) == "brake earlier T1"


def test_single_advisory_empty_when_suppressed():
    decisions = [{"delivered": True, "priority": 5, "message": "x"}]
    assert coordinate_single_advisory(decisions, suppressed=True) == ""


def test_single_advisory_empty_when_none_delivered():
    assert coordinate_single_advisory([{"delivered": False, "message": "x"}], suppressed=False) == ""


# --- garage return ---------------------------------------------------------

def _tr(transition):
    return LiveRuntimeTransitionResult(transition, False, None, "fp", False, "", "f")


def test_garage_return_binding_required():
    d = resolve_garage_return(_tr(TR.ENDED_BINDING_REQUIRED), DebriefKind.PRACTICE_RUN)
    assert d.active is True and d.primary_choice == GC.BIND_SESSION
    assert GC.BIND_SESSION in d.choices and GC.ABANDON in d.choices


def test_garage_return_insufficient():
    d = resolve_garage_return(_tr(TR.ENDED_INSUFFICIENT))
    assert d.primary_choice == GC.REVIEW_WITH_LIMITATIONS
    assert GC.MARK_INVALID in d.choices


def test_garage_return_stale_offers_recovery():
    d = resolve_garage_return(_tr(TR.STALE))
    assert d.primary_choice == GC.RESUME
    assert set(d.choices) >= {GC.RESUME, GC.BIND_SESSION, GC.REPLACEMENT_RUN, GC.ABANDON}


def test_garage_return_inactive_while_running():
    d = resolve_garage_return(_tr(TR.RUNNING))
    assert d.active is False and d.primary_choice is None
