"""Explicit session binding, debrief handover & cumulative update (Program 2, Phase 52).

At session end the driver must EXPLICITLY bind a telemetry session to the activity. Candidate ranking
reuses the canonical ``strategy.session_binding.rank_candidate_sessions`` (context+setup match; recency
only a tie-breaker; auto-bind forbidden). Once bound, the activity hands over to the correct debrief
(Practice run / Qualifying review / Race debrief), reusing the canonical outcome/closed-loop authorities.
Only AFTER a confirmed valid or limited evidence classification may the activity update the cumulative
programme; invalid / mismatched / abandoned sessions remain visible but cannot strengthen confidence.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. Binds nothing itself; the
canonical binding write is explicit elsewhere (``SessionDB.bind_session_to_activity``).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

from strategy.event_preparation_cycle import PreparationActivityType
from strategy.live_activity import requires_telemetry
from strategy.preparation_evidence import _TYPE_DOMAINS
from strategy.session_binding import rank_candidate_sessions

ACTIVITY_BINDING_VERSION = "activity_binding_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{ACTIVITY_BINDING_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class DebriefKind(str, Enum):
    PRACTICE_RUN = "practice_run"
    QUALIFYING_REVIEW = "qualifying_review"
    RACE_DEBRIEF = "race_debrief"
    NONE = "none"


class EvidenceClassification(str, Enum):
    VALID = "valid"
    LIMITED = "limited"          # usable but labelled (partial/transferred context)
    INVALID = "invalid"
    MISMATCHED = "mismatched"    # wrong context — must not strengthen exact evidence
    ABANDONED = "abandoned"


def rank_activity_sessions(candidate_sessions, run_plan_context, *, expected_setup_fingerprint: str = "",
                           min_clean_laps: int = 0):
    """Thin reuse of the canonical ranker — the newest is never auto-selected; explicit selection is
    always required."""
    return rank_candidate_sessions(candidate_sessions, run_plan_context,
                                   expected_setup_fingerprint=expected_setup_fingerprint,
                                   min_clean_laps=min_clean_laps)


def debrief_kind_for(activity_type: PreparationActivityType) -> DebriefKind:
    T = PreparationActivityType
    if activity_type in (T.QUALIFYING, T.QUALIFYING_SIMULATION):
        return DebriefKind.QUALIFYING_REVIEW
    if activity_type == T.RACE:
        return DebriefKind.RACE_DEBRIEF
    if requires_telemetry(activity_type):
        return DebriefKind.PRACTICE_RUN
    return DebriefKind.NONE


@dataclass(frozen=True)
class ActivityDebriefReadiness:
    activity_type: PreparationActivityType
    debrief_kind: DebriefKind
    ready: bool
    reason: str

    def as_payload(self) -> dict:
        return {"activity_type": self.activity_type.value, "debrief_kind": self.debrief_kind.value,
                "ready": bool(self.ready), "reason": _norm(self.reason)}


def assess_debrief_readiness(activity_type: PreparationActivityType,
                             session_bound: bool) -> ActivityDebriefReadiness:
    """A debrief may begin only after an explicit binding when the activity requires telemetry."""
    kind = debrief_kind_for(activity_type)
    if requires_telemetry(activity_type) and not session_bound:
        return ActivityDebriefReadiness(activity_type, kind, False,
                                        "bind a telemetry session before the debrief")
    return ActivityDebriefReadiness(activity_type, kind, True, "ready for debrief")


@dataclass(frozen=True)
class ActivityLearningUpdate:
    can_update: bool
    classification: EvidenceClassification
    updated_domains: Tuple[str, ...]
    labelled_limited: bool
    reason: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"can_update": bool(self.can_update), "classification": self.classification.value,
                "updated_domains": sorted(self.updated_domains), "labelled_limited": bool(self.labelled_limited),
                "reason": _norm(self.reason)}


def plan_cumulative_update(activity_type: PreparationActivityType,
                           classification: EvidenceClassification) -> ActivityLearningUpdate:
    """Deterministic plan of what a bound session MAY update. Only VALID / LIMITED evidence updates the
    cumulative programme (LIMITED is labelled and caps confidence). INVALID / MISMATCHED / ABANDONED
    update nothing — they remain visible but cannot strengthen confidence."""
    domains = tuple(sorted(d.value for d in _TYPE_DOMAINS.get(activity_type, ())))
    if classification == EvidenceClassification.VALID:
        u = ActivityLearningUpdate(True, classification, domains, False,
                                   "valid evidence updates the cumulative programme")
    elif classification == EvidenceClassification.LIMITED:
        u = ActivityLearningUpdate(True, classification, domains, True,
                                   "limited evidence updates the programme but is labelled and capped")
    else:
        u = ActivityLearningUpdate(False, classification, (), False,
                                   f"{classification.value} evidence cannot strengthen confidence")
    return ActivityLearningUpdate(u.can_update, u.classification, u.updated_domains, u.labelled_limited,
                                  u.reason, _fp(u.as_payload()))
