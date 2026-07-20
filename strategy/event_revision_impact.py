"""Event revision impact (Program 2, Phase 53).

When Event Planner settings change during a preparation cycle, this assesses the impact deterministically:
it detects the revision, compares the old vs new immutable event context, identifies which evidence is
affected, states whether prior evidence remains compatible, whether a setup lock must reopen and whether
strategy must be recalculated. It REWRITES NOTHING — completed session provenance is never touched; this
is an assessment only.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple

EVENT_REVISION_IMPACT_VERSION = "event_revision_impact_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{EVENT_REVISION_IMPACT_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


# fields whose change invalidates exact prior evidence compatibility
_EVIDENCE_SENSITIVE = frozenset({
    "car", "track", "layout", "bop", "tuning", "power", "weight", "tyres",
    "tyre_multiplier", "fuel_multiplier",
})
# fields whose change requires strategy recalculation
_STRATEGY_SENSITIVE = frozenset({
    "tyre_multiplier", "fuel_multiplier", "refuel_rate", "race_duration", "laps", "weather",
})


@dataclass(frozen=True)
class EventRevisionImpact:
    revision_detected: bool
    changed_fields: Tuple[str, ...]
    prior_evidence_compatible: bool
    incompatible_fields: Tuple[str, ...]
    lock_reopen_required: bool
    strategy_recalc_required: bool
    note: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"revision_detected": bool(self.revision_detected),
                "changed_fields": sorted(self.changed_fields),
                "prior_evidence_compatible": bool(self.prior_evidence_compatible),
                "incompatible_fields": sorted(self.incompatible_fields),
                "lock_reopen_required": bool(self.lock_reopen_required),
                "strategy_recalc_required": bool(self.strategy_recalc_required), "note": _norm(self.note)}


def assess_event_revision(old_context: Mapping, new_context: Mapping) -> EventRevisionImpact:
    """Compare two event contexts (same event). Deterministic. Completed history is untouched — this only
    reports what changed and its impact on prior evidence, setup locks and strategy."""
    old = old_context if isinstance(old_context, Mapping) else {}
    new = new_context if isinstance(new_context, Mapping) else {}
    keys = set(old) | set(new)
    changed = tuple(sorted(k for k in keys if _norm(old.get(k)) != _norm(new.get(k))))
    incompatible = tuple(sorted(f for f in changed if f in _EVIDENCE_SENSITIVE))
    strategy_hit = any(f in _STRATEGY_SENSITIVE for f in changed)
    prior_compatible = not incompatible
    lock_reopen = bool(incompatible)
    note = ("no revision detected" if not changed else
            ("environment change — some prior exact evidence is now incompatible" if incompatible else
             "revision changed only non-evidence fields; prior evidence remains compatible"))
    impact = EventRevisionImpact(
        revision_detected=bool(changed), changed_fields=changed, prior_evidence_compatible=prior_compatible,
        incompatible_fields=incompatible, lock_reopen_required=lock_reopen,
        strategy_recalc_required=strategy_hit, note=note, fingerprint="")
    return EventRevisionImpact(**{**impact.__dict__, "fingerprint": _fp(impact.as_payload())})
