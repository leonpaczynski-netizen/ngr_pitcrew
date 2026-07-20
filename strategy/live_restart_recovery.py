"""Live restart, recovery & event-switch protection (Program 2, Phase 61).

Restores the production live workflow predictably after an application restart (reusing the canonical
Phase-53 ``programme_resume``) and provides the pure stale-snapshot rule that prevents a stale worker
from one event/activity updating a newly-selected one. No state is silently completed on restart.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Tuple

from strategy.live_activity import LiveActivityState
from strategy.programme_resume import build_resume_state, ProgrammeResumeState
from strategy.live_pit_wall_controller import LivePitWallNavigationContext

LIVE_RESTART_RECOVERY_VERSION = "live_restart_recovery_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _fp(payload) -> str:
    return (f"{LIVE_RESTART_RECOVERY_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


@dataclass(frozen=True)
class LiveRestartResolution:
    resume: ProgrammeResumeState
    nav: LivePitWallNavigationContext        # restored operational nav (never started from restore)
    note: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"resume": self.resume.as_payload(),
                "nav_event": _norm(self.nav.active_event_id), "nav_activity": _norm(self.nav.selected_activity_id),
                "nav_started": bool(self.nav.started), "note": _norm(self.note)}


def resolve_live_restart(*, selected_event: str = "", selected_activity: str = "", current_phase: str = "",
                         interrupted_activity_id: str = "",
                         interrupted_state: LiveActivityState = LiveActivityState.PLANNED,
                         pending_binding: bool = False, pending_debrief: bool = False) -> LiveRestartResolution:
    """Restore the live workflow after restart. Reuses ``build_resume_state`` (an interrupted activity is
    never restored COMPLETED). The restored nav is NEVER ``started`` — the driver must explicitly re-start
    a live run; the pending binding/debrief workflow is preserved."""
    resume = build_resume_state(
        selected_cycle_id=selected_event, current_phase=current_phase,
        next_activity_id=selected_activity, interrupted_activity_id=interrupted_activity_id,
        interrupted_state=interrupted_state, pending_binding=pending_binding, pending_debrief=pending_debrief,
        voice_preserved=False)
    nav = LivePitWallNavigationContext(
        active_event_id=_norm(selected_event), selected_activity_id=_norm(selected_activity),
        entered_live=False, started=False)   # restart never auto-enters or auto-starts a live run
    note = ("pending binding restored" if pending_binding else
            "pending debrief restored" if pending_debrief else
            "interrupted activity restored (not completed)" if _norm(interrupted_activity_id) else
            "workflow restored")
    r = LiveRestartResolution(resume, nav, note, "")
    return LiveRestartResolution(r.resume, r.nav, r.note, _fp(r.as_payload()))


def is_stale_snapshot(*, snapshot_event: str, snapshot_activity: str,
                      current_event: str, current_activity: str) -> bool:
    """Pure stale-snapshot rule: a snapshot/worker built for one (event, activity) must NOT update a
    different current (event, activity). Mirrors the dashboard stale guard."""
    return (_norm(snapshot_event), _norm(snapshot_activity)) != (_norm(current_event), _norm(current_activity))
