"""Setup lock-in & restriction policy (Program 2, Phase 49).

A user-controlled setup-lock workflow. Locking is a PROGRAMME DECISION and a provenance marker — it is
NOT a bypass around the canonical Apply gate (``ActiveSetupAuthority.mark_applied`` remains the only
route that mutates the applied setup). Locking never applies a setup automatically and never occurs
without explicit confirmation; a dashboard refresh can neither lock nor unlock.

NGR-neutral restriction model: an event *may* define no lock deadline, an advisory lock, a mandatory
NGR setup lock, a qualifying/race lock, or post-qualifying restrictions. Parc fermé is NOT assumed
universal — it is one configurable ``SetupRestrictionState``.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. Authors no setup value.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence, Tuple

from strategy.setup_convergence import SetupConvergenceState, SetupDiscipline

SETUP_LOCK_VERSION = "setup_lock_v1"
SETUP_LOCK_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{SETUP_LOCK_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class SetupRestrictionState(str, Enum):
    OPEN = "open"                                # freely changeable
    ADVISORY_LOCK = "advisory_lock"              # a recommended lock; changes still permitted
    LOCKED = "locked"                            # locked by programme decision
    POST_QUALIFYING_RESTRICTED = "post_qualifying_restricted"
    RESTRICTED_AFTER_LOCK = "restricted_after_lock"   # parc-fermé-style, only allowed changes permitted


class AllowedPostLockChange(str, Enum):
    NONE = "none"
    TYRE_PRESSURE = "tyre_pressure"
    BRAKE_BIAS = "brake_bias"
    DIFFERENTIAL = "differential"
    ANTI_ROLL_BAR = "anti_roll_bar"
    RIDE_HEIGHT = "ride_height"
    FUEL_LOAD = "fuel_load"


@dataclass(frozen=True)
class SetupLockPolicy:
    """Configurable lock policy, typically derived from the event format profile."""
    has_lock_deadline: bool = False
    mandatory: bool = False
    lock_deadline_date: str = ""
    restriction_after_lock: bool = False
    allowed_post_lock_changes: Tuple[AllowedPostLockChange, ...] = field(default_factory=tuple)

    def as_payload(self) -> dict:
        return {"has_lock_deadline": bool(self.has_lock_deadline), "mandatory": bool(self.mandatory),
                "lock_deadline_date": _norm(self.lock_deadline_date),
                "restriction_after_lock": bool(self.restriction_after_lock),
                "allowed_post_lock_changes": sorted(c.value for c in self.allowed_post_lock_changes)}


# convergence states from which a lock is *permitted* (a human still must confirm)
_LOCK_PERMITTED_STATES = frozenset({
    SetupConvergenceState.LOCK_READY,
    SetupConvergenceState.READY_FOR_CONFIRMATION,
    SetupConvergenceState.STABLE_WITH_UNCERTAINTY,   # allowed with a visible compromise warning
})


@dataclass(frozen=True)
class SetupLockDecision:
    discipline: SetupDiscipline
    locked: bool
    restriction_state: SetupRestrictionState
    selected_fingerprint: str
    rollback_fingerprint: str
    confidence: str
    supporting_evidence: Tuple[str, ...]
    known_compromises: Tuple[str, ...]
    unresolved_risk: Tuple[str, ...]
    allowed_post_lock_changes: Tuple[AllowedPostLockChange, ...]
    event_rule_restriction: str
    reason: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {
            "discipline": self.discipline.value,
            "locked": bool(self.locked),
            "restriction_state": self.restriction_state.value,
            "selected_fingerprint": _norm(self.selected_fingerprint),
            "rollback_fingerprint": _norm(self.rollback_fingerprint),
            "confidence": _norm(self.confidence),
            "supporting_evidence": sorted(_norm(s) for s in self.supporting_evidence if _norm(s)),
            "known_compromises": sorted(_norm(s) for s in self.known_compromises if _norm(s)),
            "unresolved_risk": sorted(_norm(s) for s in self.unresolved_risk if _norm(s)),
            "allowed_post_lock_changes": sorted(c.value for c in self.allowed_post_lock_changes),
            "event_rule_restriction": _norm(self.event_rule_restriction),
            "reason": _norm(self.reason),
        }


def lock_permitted(convergence_state: SetupConvergenceState) -> bool:
    """Whether a lock is *permitted* from the current convergence state. Permission is not the lock —
    the driver must still confirm explicitly."""
    return convergence_state in _LOCK_PERMITTED_STATES


def build_lock_decision(
    discipline: SetupDiscipline,
    convergence_state: SetupConvergenceState,
    *,
    confirmed: bool,
    policy: Optional[SetupLockPolicy] = None,
    selected_fingerprint: str = "",
    rollback_fingerprint: str = "",
    confidence: str = "",
    supporting_evidence: Sequence[str] = (),
    known_compromises: Sequence[str] = (),
    unresolved_risk: Sequence[str] = (),
    event_rule_restriction: str = "",
) -> SetupLockDecision:
    """Produce a lock decision. It is LOCKED only when ``confirmed`` is True AND the convergence state
    permits a lock; otherwise it returns an unlocked decision that states exactly why (no confirmation,
    or insufficient convergence). This is a provenance record — it does NOT apply the setup; the Apply
    gate remains the sole mutation route."""
    pol = policy or SetupLockPolicy()
    permitted = lock_permitted(convergence_state)

    if not permitted:
        reason = f"lock not permitted from convergence state '{convergence_state.value}'"
        restriction = SetupRestrictionState.OPEN
        locked = False
    elif not confirmed:
        reason = "explicit driver confirmation required to lock"
        restriction = (SetupRestrictionState.ADVISORY_LOCK if pol.has_lock_deadline
                       else SetupRestrictionState.OPEN)
        locked = False
    else:
        reason = "locked by explicit driver decision"
        restriction = (SetupRestrictionState.RESTRICTED_AFTER_LOCK if pol.restriction_after_lock
                       else SetupRestrictionState.LOCKED)
        locked = True

    allowed = pol.allowed_post_lock_changes if locked else ()
    dec = SetupLockDecision(
        discipline=discipline, locked=locked, restriction_state=restriction,
        selected_fingerprint=_norm(selected_fingerprint), rollback_fingerprint=_norm(rollback_fingerprint),
        confidence=_norm(confidence), supporting_evidence=tuple(supporting_evidence),
        known_compromises=tuple(known_compromises), unresolved_risk=tuple(unresolved_risk),
        allowed_post_lock_changes=tuple(allowed), event_rule_restriction=_norm(event_rule_restriction),
        reason=reason, fingerprint="")
    return SetupLockDecision(
        discipline=dec.discipline, locked=dec.locked, restriction_state=dec.restriction_state,
        selected_fingerprint=dec.selected_fingerprint, rollback_fingerprint=dec.rollback_fingerprint,
        confidence=dec.confidence, supporting_evidence=dec.supporting_evidence,
        known_compromises=dec.known_compromises, unresolved_risk=dec.unresolved_risk,
        allowed_post_lock_changes=dec.allowed_post_lock_changes,
        event_rule_restriction=dec.event_rule_restriction, reason=dec.reason, fingerprint=_fp(dec.as_payload()))


def post_lock_change_allowed(decision: SetupLockDecision, change: AllowedPostLockChange) -> bool:
    """Whether a given change is permitted after lock under the decision's restriction state."""
    if not decision.locked:
        return True
    if decision.restriction_state == SetupRestrictionState.LOCKED:
        # a plain lock permits nothing further without reopening (a programme decision)
        return change in set(decision.allowed_post_lock_changes)
    if decision.restriction_state == SetupRestrictionState.RESTRICTED_AFTER_LOCK:
        return change in set(decision.allowed_post_lock_changes)
    return True
