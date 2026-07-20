"""Live session-transition hardening — pure (Program 2, Phase 69).

WHY IT EXISTS
  A new session / event / activity must never inherit the previous session's stale race advice, rolling
  fuel/pace evidence, pit-transition history, last recommendation, spoken-message cooldown or pending voice
  recognition. This module is the ONE canonical, testable description of exactly which live-runtime state is
  TRANSIENT (must be cleared on a session boundary) versus PERSISTENT (legitimately event-scoped engineering
  knowledge that must be PRESERVED — DB records, the Event Preparation Cycle, applied setup, user config).

DOCTRINE
  Pure, deterministic, no Qt, no DB, no wall clock; never raises. It CLEARS transient keys on a supplied
  mutable state mapping (or any object's attributes) and NEVER touches a preserved key. The two key sets are
  disjoint by construction (asserted in tests) so a reset can never erase persistent knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, MutableMapping, Tuple

LIVE_SESSION_LIFECYCLE_VERSION = "live_session_lifecycle_v1"


# --------------------------------------------------------------------------- #
# The canonical transient / preserved key sets
# --------------------------------------------------------------------------- #
# TRANSIENT live-runtime keys — cleared on every session/event/activity boundary. These are the caches and
# rolling evidence the Phase 66-69 live strategy / audio / PTT runtime reads; a fresh session must start
# from a clean slate so no stale advice, cooldown or pending recognition carries over.
TRANSIENT_LIVE_RUNTIME_KEYS: Tuple[str, ...] = (
    # canonical live race-state inputs (rolling / injected)
    "_live_race_elapsed_s",
    "_live_fuel_samples",
    "_live_clean_lap_times",
    "_live_fuel_plan",
    "_live_pace_plan_s",
    "_live_pit_loss_s",
    "_live_driver_reports",
    "_live_last_packet_monotonic",
    "_live_session_state",
    # strategy cadence + last recommendation + spoken-message cooldown
    "_live_eval_cadence",
    "_live_strategy_monitor",
    "_live_last_recommendation_fp",
    "_live_last_spoken_mono",
    "_live_last_pit_stops",
    # pending voice recognition / confirmation / driver-report candidate
    "_ptt_pending_intent",
    "_ptt_pending_readback",
    "_ptt_pending_confirmation",
    "_ptt_driver_report_candidate",
    "_ptt_last_lifecycle_state",
    # per-session certification runtime observations (never the persisted evidence)
    "_live_uat_runtime_observations",
)

# PERSISTENT keys — legitimately event-scoped or global; a session reset must NEVER clear these. Listed
# explicitly so the disjointness invariant is testable and a future edit cannot accidentally erase them.
PRESERVED_KEYS: Tuple[str, ...] = (
    "_db",                          # SessionDB — cross-session engineering knowledge
    "_config",                      # user configuration (PTT binding, voice prefs, event)
    "_event_preparation_cycle",     # Event Preparation Cycle (DB-backed)
    "_live_applied_setup_fingerprint",  # the applied setup baseline (event-scoped)
    "_live_context_digest",         # resolved event/setup context digest
    "_manual_uat_store",            # Phase 71 manual UAT evidence (explicit, auditable)
    "_active_cycle_id",             # active event cycle
    "engineering_development_records",  # immutable DB records
    "event_preparation_cycles",     # DB table
)


@dataclass(frozen=True)
class SessionResetPlan:
    """The transient keys to clear and the persistent keys to preserve on a session boundary."""
    transient_keys: Tuple[str, ...] = TRANSIENT_LIVE_RUNTIME_KEYS
    preserved_keys: Tuple[str, ...] = PRESERVED_KEYS

    def is_transient(self, key: str) -> bool:
        return key in self.transient_keys

    def is_preserved(self, key: str) -> bool:
        return key in self.preserved_keys

    def disjoint(self) -> bool:
        """True iff no key is both transient and preserved (the safety invariant)."""
        return not (set(self.transient_keys) & set(self.preserved_keys))


SESSION_RESET_PLAN = SessionResetPlan()


def reset_live_runtime_state(state: MutableMapping, plan: SessionResetPlan = SESSION_RESET_PLAN) -> Dict[str, Any]:
    """Clear every TRANSIENT key present in ``state`` (set to None), preserving all other keys. Returns the
    map of {key: prior_value} that were cleared (for diagnostics/tests). A preserved key is never touched
    even if — through a caller bug — it also appeared transient (the plan is disjoint by construction, and
    this double-guards it). Never raises."""
    cleared: Dict[str, Any] = {}
    try:
        if not hasattr(state, "get"):
            return cleared
        for key in plan.transient_keys:
            if plan.is_preserved(key):
                continue  # double-guard: never clear a preserved key
            if key in state:
                cleared[key] = state.get(key)
                state[key] = None
    except Exception:  # pragma: no cover - defensive
        return cleared
    return cleared


def reset_live_runtime_attrs(target: Any, plan: SessionResetPlan = SESSION_RESET_PLAN) -> Tuple[str, ...]:
    """Clear every TRANSIENT attribute present on ``target`` (set to None), preserving persistent attrs.
    Returns the tuple of attribute names actually cleared. Used by the dashboard's session-reset seam.
    Never raises."""
    cleared = []
    try:
        for key in plan.transient_keys:
            if plan.is_preserved(key):
                continue
            if hasattr(target, key):
                try:
                    setattr(target, key, None)
                    cleared.append(key)
                except Exception:
                    continue
    except Exception:  # pragma: no cover - defensive
        return tuple(cleared)
    return tuple(cleared)


def live_session_lifecycle_versions() -> dict:
    return {"live_session_lifecycle": LIVE_SESSION_LIFECYCLE_VERSION}
