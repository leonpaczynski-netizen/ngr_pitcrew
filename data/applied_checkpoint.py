"""Saved-vs-applied-in-GT7 setup state (pure, Qt-free).

Sprint 10 of the determinism rebuild. Autosaving a setup in Pit Crew and
*applying* it in GT7 are different actions, and the UAT surfaced the confusion:
fields went green on autosave and the app treated "saved" as "applied". This
module models the three honest states and the application checkpoint the
"Changes Applied in Game" button creates.

  NOT_SAVED          — no setup yet.
  CHANGED_SINCE_GT7  — saved in Pit Crew but differs from the last GT7-confirmed
                       setup (some fields are pending application). Stay green.
  CONFIRMED_IN_GT7   — matches the last applied checkpoint.

Telemetry captured after a checkpoint is associated with that checkpoint id, so
cross-lap evidence never mixes data from before and after different applied
setups. Pure: no Qt, no DB (a thin additive store wraps this at the call site).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class SetupApplyState(str, Enum):
    NOT_SAVED = "not_saved"
    CHANGED_SINCE_GT7 = "changed_since_gt7"
    CONFIRMED_IN_GT7 = "confirmed_in_gt7"


def compute_setup_hash(fields: dict) -> str:
    """Deterministic hash of a setup's numeric/string fields (order-independent)."""
    parts = []
    for k in sorted(fields or {}):
        parts.append(f"{k}={fields[k]}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class AppliedCheckpoint:
    """A record that a specific setup was confirmed applied in GT7."""
    checkpoint_id: str
    setup_id: str
    setup_hash: str
    fields: dict = field(default_factory=dict)
    changed_fields: Tuple[str, ...] = ()
    confirmed_at: str = ""


@dataclass(frozen=True)
class ApplyStatus:
    state: SetupApplyState
    pending_fields: Tuple[str, ...] = ()   # fields differing from the last checkpoint
    confirmed_at: str = ""
    checkpoint_id: str = ""
    message: str = ""

    @property
    def is_confirmed(self) -> bool:
        return self.state is SetupApplyState.CONFIRMED_IN_GT7

    @property
    def has_pending(self) -> bool:
        return bool(self.pending_fields)


def make_checkpoint(
    *, setup_id: str, fields: dict, changed_fields=(), confirmed_at: str = "",
    checkpoint_id: str = "",
) -> AppliedCheckpoint:
    """Create an application checkpoint for the currently-applied setup."""
    h = compute_setup_hash(fields)
    cid = checkpoint_id or f"cp_{setup_id}_{h}"
    return AppliedCheckpoint(
        checkpoint_id=cid, setup_id=setup_id, setup_hash=h, fields=dict(fields or {}),
        changed_fields=tuple(changed_fields or ()), confirmed_at=confirmed_at,
    )


def _pending_fields(current: dict, checkpoint: AppliedCheckpoint) -> Tuple[str, ...]:
    cur = current or {}
    base = checkpoint.fields or {}
    keys = set(cur) | set(base)
    return tuple(sorted(k for k in keys if cur.get(k) != base.get(k)))


def compute_apply_status(
    current_fields: Optional[dict],
    last_checkpoint: Optional[AppliedCheckpoint],
) -> ApplyStatus:
    """Resolve the three-state apply status for the current setup vs the last
    GT7-confirmed checkpoint."""
    if not current_fields:
        return ApplyStatus(state=SetupApplyState.NOT_SAVED,
                           message="No setup saved yet.")

    if last_checkpoint is None:
        return ApplyStatus(
            state=SetupApplyState.CHANGED_SINCE_GT7,
            pending_fields=tuple(sorted(current_fields)),
            message="Saved in Pit Crew — not yet confirmed applied in GT7.",
        )

    if compute_setup_hash(current_fields) == last_checkpoint.setup_hash:
        return ApplyStatus(
            state=SetupApplyState.CONFIRMED_IN_GT7,
            confirmed_at=last_checkpoint.confirmed_at,
            checkpoint_id=last_checkpoint.checkpoint_id,
            message=(f"Setup confirmed applied in GT7"
                     + (f" at {last_checkpoint.confirmed_at}" if last_checkpoint.confirmed_at else "")),
        )

    pending = _pending_fields(current_fields, last_checkpoint)
    return ApplyStatus(
        state=SetupApplyState.CHANGED_SINCE_GT7,
        pending_fields=pending, checkpoint_id=last_checkpoint.checkpoint_id,
        message=(f"Saved locally — {len(pending)} change(s) waiting to be applied in GT7"),
    )
