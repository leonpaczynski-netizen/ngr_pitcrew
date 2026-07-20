"""DB-free production pit-wall build (Program 2, Phase 60).

The single deterministic, DB-FREE composition the production Live worker runs OFF the UI thread each
evaluation cadence: tracker snapshot + resolved activity context + navigation → runtime evaluation →
transition → production Live state → pit-wall view dict. It performs NO database query and NO write — the
activity context is resolved once (on invalidation) by the caller, not here.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

from typing import Optional

from strategy.gt7_live_adapter import (
    TrackerRuntimeSnapshot, SelectedActivityContext, evaluate_live_runtime)
from strategy.live_runtime_authority import evaluate_runtime_transition
from strategy.live_pit_wall_controller import (
    LivePitWallNavigationContext, reduce_live_state)
from strategy.ngr_live_pit_wall import build_ngr_live_pit_wall, pit_wall_to_dict, VoiceStatus


def build_live_pit_wall_view(
    tracker: TrackerRuntimeSnapshot,
    ctx: SelectedActivityContext,
    nav: LivePitWallNavigationContext,
    *,
    was_running: bool = False,
    now_monotonic: Optional[float] = None,
    event_line: str = "",
    voice_status: VoiceStatus = VoiceStatus.DISABLED,
    advisory_text: str = "",
) -> dict:
    """Build the production pit-wall view dict off the UI thread. DB-free and deterministic. Returns the
    pit-wall dict enriched with the production Live state + match + running flag."""
    evaluation = evaluate_live_runtime(tracker, ctx, now_monotonic=now_monotonic)
    transition = evaluate_runtime_transition(evaluation, was_running=bool(was_running))
    state = reduce_live_state(nav, evaluation, transition)
    pw = build_ngr_live_pit_wall(evaluation, transition, event_line=event_line,
                                 voice_status=voice_status, advisory_text=advisory_text)
    view = pit_wall_to_dict(pw)
    view.update({
        "production_state": state.state.value,
        "production_note": state.note,
        "now_running": bool(transition.now_running),
        "match": evaluation.match.match.value,
        "activity_completed": False,
        "state_fingerprint": state.fingerprint,
    })
    return view
