"""Learning proposal / decision vocabulary (Program 3 Phase I / §23-24).

Cross-event learning must never silently become permanent. A candidate learning is
raised as a PROPOSAL carrying its evidence, applicability scope and confidence; the
driver then accepts, rejects, edits or defers it; only accepted (or accepted-with-edit)
learning becomes an active prior. A rejected learning is recorded as rejected and is
never re-proposed without materially new evidence, and never influences a future
recommendation.

This module holds the model-agnostic vocabulary + the deterministic suppression key.
The STRUCTURE of ``applicability_scope`` (the 6-layer archetype model vs the existing
full-context fingerprint) is a separate, deferred decision — the workflow here does
not depend on it. Pure, never raises.
"""

from __future__ import annotations

import enum
import re


class LearningDecision(str, enum.Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    EDIT = "edit"
    DEFER = "defer"


class LearningStatus(str, enum.Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"       # accepted with an edited scope — an active prior
    DEFERRED = "deferred"


#: Statuses whose learning is an ACTIVE prior (may influence future events).
ACTIVE_PRIOR_STATUSES = (LearningStatus.ACCEPTED.value, LearningStatus.EDITED.value)


def observation_key(observation: str, applicability_scope: str = "") -> str:
    """A deterministic, normalised key for an observation+scope, used to detect a
    previously-rejected proposal so it is not re-raised without new evidence. Never
    raises."""
    try:
        parts = []
        for x in (observation, applicability_scope):
            parts.append(re.sub(r"\s+", " ", str(x or "").strip().lower()))
        return "|".join(parts)
    except Exception:
        return ""
