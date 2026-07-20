"""Event-condition equivalence — visible, deterministic context compatibility (Program 2, Phase 39).

Decides how two engineering contexts relate along explicit, fingerprinted dimensions, so a different
event *ID* alone never makes otherwise-identical engineering conditions unusable, while a materially
different tyre/compound/discipline is never silently treated as exact evidence.

Dimensions:
  * identity-critical  (driver, car+variant, discipline, gt7_version) - generally incompatible if
    different;
  * track-critical     (track, layout, direction) - exact or explicitly transferred only;
  * event-condition    (compound/policy, BoP, tuning permission, power/weight, tyre & fuel
    multipliers, race objective, weather/grip) - evaluated explicitly;
  * administrative      (event_id) - a different event instance, NOT an incompatibility on its own.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Tuple

CONTEXT_EQUIVALENCE_VERSION = "context_equivalence_v1"
CONTEXT_EQUIVALENCE_SCHEMA = 1

_IDENTITY_CRITICAL = ("driver", "car", "car_variant", "discipline", "gt7_version")
_TRACK_CRITICAL = ("track", "layout_id", "track_direction")
_EVENT_CONDITION = ("compound", "compound_policy", "bop_state", "tuning_permitted",
                    "power_restriction", "weight_restriction", "tyre_multiplier", "fuel_multiplier",
                    "race_objective", "weather", "grip_state")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{CONTEXT_EQUIVALENCE_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class EquivalenceDecision(str, Enum):
    SAME_INSTANCE = "same_instance"                 # identical incl. event_id
    EQUIVALENT_CONDITIONS = "equivalent_conditions"  # all material conditions match, event_id differs
    TRANSFER_ONLY = "transfer_only"                  # track/layout differs (transfer, not exact)
    MATERIALLY_DIFFERENT = "materially_different"    # an event-condition differs materially
    INCOMPATIBLE = "incompatible"                    # an identity-critical dimension differs
    UNVERIFIABLE = "unverifiable"                    # not enough identity to decide


def _both_known_differ(a: Mapping, b: Mapping, field: str) -> bool:
    """A dimension DIFFERS only when both sides are known and unequal (an unknown never 'differs')."""
    va, vb = _lc(a.get(field)), _lc(b.get(field))
    return bool(va) and bool(vb) and va != vb


def _any_known(a: Mapping, b: Mapping, fields) -> bool:
    return any(_lc(a.get(f)) or _lc(b.get(f)) for f in fields)


@dataclass(frozen=True)
class ContextEquivalence:
    decision: str
    identity_diffs: Tuple[str, ...]
    track_diffs: Tuple[str, ...]
    event_condition_diffs: Tuple[str, ...]
    event_id_differs: bool
    reason: str
    content_fingerprint: str
    schema_version: int = CONTEXT_EQUIVALENCE_SCHEMA
    eval_version: str = CONTEXT_EQUIVALENCE_VERSION

    def to_dict(self) -> dict:
        return {"decision": self.decision, "identity_diffs": list(self.identity_diffs),
                "track_diffs": list(self.track_diffs),
                "event_condition_diffs": list(self.event_condition_diffs),
                "event_id_differs": self.event_id_differs, "reason": self.reason,
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def assess_context_equivalence(a: Optional[Mapping], b: Optional[Mapping]) -> ContextEquivalence:
    """Compare two contexts (dicts / EngineeringContextScope.to_dict()). Deterministic; never raises.
    A different event_id alone yields EQUIVALENT_CONDITIONS (a different instance, engineering-equal),
    NOT incompatibility. Materially different event conditions yield MATERIALLY_DIFFERENT."""
    try:
        a = a if isinstance(a, Mapping) else {}
        b = b if isinstance(b, Mapping) else {}
        id_diffs = tuple(f for f in _IDENTITY_CRITICAL if _both_known_differ(a, b, f))
        tr_diffs = tuple(f for f in _TRACK_CRITICAL if _both_known_differ(a, b, f))
        ec_diffs = tuple(f for f in _EVENT_CONDITION if _both_known_differ(a, b, f))
        event_id_differs = _both_known_differ(a, b, "event_id")

        if not (_any_known(a, b, ("car",)) and _any_known(a, b, ("track",))):
            decision = EquivalenceDecision.UNVERIFIABLE
            reason = "insufficient identity (car/track) to decide equivalence."
        elif id_diffs:
            decision = EquivalenceDecision.INCOMPATIBLE
            reason = "identity-critical dimension(s) differ: " + ", ".join(id_diffs) + "."
        elif tr_diffs:
            decision = EquivalenceDecision.TRANSFER_ONLY
            reason = ("track-critical dimension(s) differ (" + ", ".join(tr_diffs) + "); usable only "
                      "as explicitly transferred evidence, not exact.")
        elif ec_diffs:
            decision = EquivalenceDecision.MATERIALLY_DIFFERENT
            reason = ("event condition(s) differ materially: " + ", ".join(ec_diffs) + "; not exact "
                      "evidence.")
        elif event_id_differs:
            decision = EquivalenceDecision.EQUIVALENT_CONDITIONS
            reason = ("all material engineering conditions match; only the event ID differs - a "
                      "different event instance but engineering-equivalent (evidence eligible).")
        else:
            decision = EquivalenceDecision.SAME_INSTANCE
            reason = "same engineering conditions and same event instance."

        fp = _fp({"decision": decision.value, "id": id_diffs, "tr": tr_diffs, "ec": ec_diffs,
                  "eid": event_id_differs})
        return ContextEquivalence(decision=decision.value, identity_diffs=id_diffs,
                                  track_diffs=tr_diffs, event_condition_diffs=ec_diffs,
                                  event_id_differs=event_id_differs, reason=reason,
                                  content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return ContextEquivalence(decision=EquivalenceDecision.UNVERIFIABLE.value, identity_diffs=(),
                                  track_diffs=(), event_condition_diffs=(), event_id_differs=False,
                                  reason="equivalence unavailable.", content_fingerprint=_fp({"e": 1}))


def equivalence_versions() -> dict:
    return {"context_equivalence": CONTEXT_EQUIVALENCE_VERSION, "schema": CONTEXT_EQUIVALENCE_SCHEMA}
