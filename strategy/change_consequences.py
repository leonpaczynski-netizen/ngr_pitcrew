"""Deterministic change consequences (Engineering Brain Phase 10).

For the EXACT Phase-5 selected experiment, this READ-ONLY module lists the deterministic
expected engineering effects of the proposed change — its primary effect, its coupled
side effects, what history showed, whether the working window remains valid, and which
other fields it interacts with. Every consequence references engineering evidence
(the Phase-5 candidate's own interaction-graph effects, the Phase-9 transfers, and the
canonical ``PARAMETER_INTERACTIONS`` coupling graph).

It re-selects nothing, changes no value, and derives no new physics — it re-projects
already-canonical outputs into driver-facing consequences.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock; no prediction/inference — deterministic re-projection only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.setup_synthesis import PARAMETER_INTERACTIONS

CHANGE_CONSEQUENCES_VERSION = "change_consequences_v1"


class ConsequenceKind(str, Enum):
    PRIMARY_EFFECT = "primary_effect"
    SIDE_EFFECT = "side_effect"
    HISTORICAL = "historical"
    WORKING_WINDOW = "working_window"
    INTERACTION = "interaction"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


# --------------------------------------------------------------------------- #
# Coupled fields (shared handling axis) — from the canonical interaction graph
# --------------------------------------------------------------------------- #
def coupled_fields(field: str, interactions: Optional[Mapping] = None
                   ) -> Tuple[Tuple[str, str], ...]:
    """Return (other_field, shared_handling_axis) pairs that couple with ``field``
    through the canonical ``PARAMETER_INTERACTIONS`` graph. Deterministic order."""
    graph = interactions if interactions is not None else PARAMETER_INTERACTIONS
    mine = graph.get(_norm(field), {}) or {}
    if not mine:
        return ()
    my_axes = set(mine)
    out = []
    for other, axes in graph.items():
        if other == _norm(field):
            continue
        shared = sorted(my_axes & set(axes or {}))
        for axis in shared:
            out.append((other, axis))
    return tuple(sorted(out))


@dataclass(frozen=True)
class ChangeConsequence:
    kind: str                           # ConsequenceKind value
    field: str
    direction: str
    text: str
    evidence_source: str
    supporting_sessions: Tuple[str, ...]
    confidence: str
    eval_version: str = CHANGE_CONSEQUENCES_VERSION

    def to_dict(self) -> dict:
        return {"kind": self.kind, "field": self.field, "direction": self.direction,
                "text": self.text, "evidence_source": self.evidence_source,
                "supporting_sessions": list(self.supporting_sessions),
                "confidence": self.confidence, "eval_version": self.eval_version}


def _transfers_for_field(context: Mapping, field: str, kind: str) -> list:
    field = _lc(field)
    return [t for t in (context or {}).get("transfers") or []
            if _lc(t.get("field")) == field and t.get("kind") == kind]


def derive_consequences(
    candidate: Mapping, *, context: Optional[Mapping] = None,
    interactions: Optional[Mapping] = None,
) -> Tuple[ChangeConsequence, ...]:
    """Deterministic expected engineering effects for the proposed change. Consumes the
    Phase-5 candidate's own interaction-graph effects + the Phase-9 context; adds no new
    physics. ``candidate`` is the exact Phase-5 selection dict (never modified)."""
    context = context or {}
    field = _norm(candidate.get("field"))
    direction = _norm(candidate.get("direction"))
    out: List[ChangeConsequence] = []

    def _mk(kind, text, source, sessions=(), confidence=""):
        out.append(ChangeConsequence(
            kind=kind.value, field=field, direction=direction, text=_norm(text),
            evidence_source=_norm(source),
            supporting_sessions=tuple(sorted({_norm(s) for s in sessions if _norm(s)})),
            confidence=_norm(confidence)))

    # 1) primary effect — the Phase-5 candidate's own expected positive effect.
    pos = _norm(candidate.get("expected_positive_effect"))
    if pos:
        _mk(ConsequenceKind.PRIMARY_EFFECT, pos, "phase5 interaction graph",
            confidence=_norm(candidate.get("evidence_grade")))

    # 2) side effects — the candidate's coupled negative effects.
    for neg in (candidate.get("expected_negative_effects") or ()):
        if _norm(neg):
            _mk(ConsequenceKind.SIDE_EFFECT, neg, "phase5 interaction graph")

    # 3) historical — what prior sessions in compatible contexts showed.
    for t in _transfers_for_field(context, field, "successful_experiment"):
        _mk(ConsequenceKind.HISTORICAL,
            f"previously improved: {t.get('detail') or 'a target issue'}",
            f"{t.get('strength', '')} match", t.get("supporting_sessions") or (),
            "confirmed" if t.get("confirmed") else "provisional")
    for t in _transfers_for_field(context, field, "failed_experiment"):
        _mk(ConsequenceKind.HISTORICAL,
            f"previously regressed: {t.get('detail') or 'a behaviour'}",
            f"{t.get('strength', '')} match", t.get("supporting_sessions") or (),
            "confirmed" if t.get("confirmed") else "provisional")

    # 4) working window — whether the proposed value stays inside the learned window.
    wr = _norm(candidate.get("window_relationship"))
    if wr:
        inside = "inside" in _lc(wr) or _lc(wr) in ("within_window", "in_window")
        text = ("proposed value stays inside the learned working window"
                if inside else f"working-window relationship: {wr}")
        _mk(ConsequenceKind.WORKING_WINDOW, text, "phase5 working window")

    # 5) interactions — coupled fields via the canonical interaction graph.
    for other, axis in coupled_fields(field, interactions):
        _mk(ConsequenceKind.INTERACTION,
            f"known interaction with {other} (shared {axis.replace('_', ' ')})",
            "parameter interaction graph")

    return tuple(out)


def consequences_fingerprint(consequences: Sequence[ChangeConsequence]) -> str:
    raw = json.dumps([c.to_dict() for c in consequences], sort_keys=True,
                     separators=(",", ":"))
    return f"{CHANGE_CONSEQUENCES_VERSION}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"
