"""Historical Context Resolution (Program 2, Phase 45).

Recovers the historical engineering context for a record, preferring a directly-persisted immutable
snapshot. A legacy record without a snapshot resolves to UNKNOWN fields - values are NEVER back-filled
from the current (mutable) event. Each field is marked with how it was obtained:

  * ``directly_persisted``          - present in the record's immutable snapshot;
  * ``resolved_through_reference``  - obtained via an immutable reference chain;
  * ``inferred_with_limitations``   - inferred from other immutable evidence (flagged);
  * ``unknown``                     - genuinely unknown (legacy / never captured).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Fabricates NOTHING.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

from strategy.engineering_context_snapshot import (
    SNAPSHOT_SEMANTIC_FIELDS, ENGINEERING_CONTEXT_SNAPSHOT_VERSION,
)

HISTORICAL_CONTEXT_RESOLUTION_VERSION = "historical_context_resolution_v1"
HISTORICAL_CONTEXT_RESOLUTION_SCHEMA = 1

_CORE = ("driver", "car", "track", "layout_id", "discipline", "gt7_version")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{HISTORICAL_CONTEXT_RESOLUTION_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class FieldSource(str, Enum):
    DIRECTLY_PERSISTED = "directly_persisted"
    RESOLVED_THROUGH_REFERENCE = "resolved_through_reference"
    INFERRED_WITH_LIMITATIONS = "inferred_with_limitations"
    UNKNOWN = "unknown"


class ResolutionConfidence(str, Enum):
    EXACT = "exact"                    # snapshot present, all core fields known
    PARTIAL = "partial"               # snapshot present with gaps
    LEGACY_PARTIAL = "legacy_partial"  # no snapshot - visible but unverifiable/unknown
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True)
class FieldResolution:
    field: str
    value: str
    source: str

    def to_dict(self) -> dict:
        return {"field": self.field, "value": self.value, "source": self.source}


@dataclass(frozen=True)
class HistoricalContextResolution:
    has_snapshot: bool
    ref_kind: str
    ref_key: str
    semantic_digest: str
    fields: Tuple[dict, ...]
    known_count: int
    unknown_count: int
    confidence_cap: str
    reason: str
    content_fingerprint: str
    schema_version: int = HISTORICAL_CONTEXT_RESOLUTION_SCHEMA
    eval_version: str = HISTORICAL_CONTEXT_RESOLUTION_VERSION

    def to_dict(self) -> dict:
        return {"has_snapshot": self.has_snapshot, "ref_kind": self.ref_kind, "ref_key": self.ref_key,
                "semantic_digest": self.semantic_digest, "fields": [dict(f) for f in self.fields],
                "known_count": self.known_count, "unknown_count": self.unknown_count,
                "confidence_cap": self.confidence_cap, "reason": self.reason,
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def resolve_historical_context(snapshot: Optional[Mapping], *, ref_kind: str = "", ref_key: str = "",
                               inferred_fields: Optional[Sequence[str]] = None
                               ) -> HistoricalContextResolution:
    """Resolve the historical context from an immutable snapshot dict (or None for a legacy record).
    Deterministic; never fabricates; never raises. Values are never back-filled from the current event."""
    try:
        has_snap = bool(snapshot) and isinstance(snapshot, Mapping)
        content = (snapshot.get("content") if has_snap and isinstance(snapshot.get("content"), Mapping)
                   else {})
        digest = _norm(snapshot.get("semantic_digest")) if has_snap else ""
        inferred = {str(f).strip().lower() for f in (inferred_fields or [])}

        fields = []
        known = 0
        for f in SNAPSHOT_SEMANTIC_FIELDS:
            val = _norm(content.get(f)) if has_snap else ""
            if not has_snap:
                source = FieldSource.UNKNOWN
            elif f in inferred and val:
                source = FieldSource.INFERRED_WITH_LIMITATIONS
            elif val:
                source = FieldSource.DIRECTLY_PERSISTED
                known += 1
            else:
                source = FieldSource.UNKNOWN
            fields.append(FieldResolution(field=f, value=val, source=source.value))
        unknown = len(SNAPSHOT_SEMANTIC_FIELDS) - known

        if not has_snap:
            conf = ResolutionConfidence.LEGACY_PARTIAL
            reason = ("no immutable snapshot for this record - legacy partial context; values are "
                      "unknown and never back-filled from the current event.")
        elif all(_norm(content.get(c)) for c in _CORE):
            conf = ResolutionConfidence.EXACT
            reason = "immutable snapshot present with all core identity fields directly persisted."
        else:
            conf = ResolutionConfidence.PARTIAL
            reason = "immutable snapshot present but missing some core identity fields."

        fp = _fp({"digest": digest, "has": has_snap,
                  "fields": [(f.field, f.value, f.source) for f in fields]})
        return HistoricalContextResolution(
            has_snapshot=has_snap, ref_kind=_norm(ref_kind), ref_key=_norm(ref_key),
            semantic_digest=digest, fields=tuple(f.to_dict() for f in fields), known_count=known,
            unknown_count=unknown, confidence_cap=conf.value, reason=reason, content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return HistoricalContextResolution(
            has_snapshot=False, ref_kind=_norm(ref_kind), ref_key=_norm(ref_key), semantic_digest="",
            fields=(), known_count=0, unknown_count=len(SNAPSHOT_SEMANTIC_FIELDS),
            confidence_cap=ResolutionConfidence.UNVERIFIABLE.value, reason="unavailable.",
            content_fingerprint=_fp({"e": 1}))


def resolution_versions() -> dict:
    return {"historical_context_resolution": HISTORICAL_CONTEXT_RESOLUTION_VERSION,
            "engineering_context_snapshot": ENGINEERING_CONTEXT_SNAPSHOT_VERSION,
            "schema": HISTORICAL_CONTEXT_RESOLUTION_SCHEMA}
