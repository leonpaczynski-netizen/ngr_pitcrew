"""Canonical Assurance-Chain Serialization — the ONE serializer shared by Phases 33-35.

A single canonical serialization + digest + fingerprint authority for the assurance-chain export
(Phase 33), snapshot comparison (Phase 34) and external review package (Phase 35). It accepts
already-built immutable domain products and produces byte-identical canonical output across restart,
shuffled input row order and repeated builds.

Determinism guarantees:
- explicit schema/version identifiers;
- deterministic field ordering (canonical JSON with sorted keys);
- deterministic list ordering (list order is preserved verbatim - callers order deterministically);
- NO unordered dict output, NO object identity, NO memory addresses, NO timestamps in semantic
  fingerprints, NO locale-sensitive number formatting, NO machine-specific paths, NO implicit
  dataclass repr, NO reliance on Python hash randomisation;
- explicit float normalisation (fixed decimals) and rejection of non-finite numbers (inf / nan);
- deterministic enum-value normalisation (str-enums serialise to their value);
- ASCII-clean output.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
raises only on a genuine canonicalisation violation (non-finite number).
"""
from __future__ import annotations

import hashlib
import json
import math
from enum import Enum
from typing import Any, Mapping, Sequence

ASSURANCE_CHAIN_SERIALIZATION_VERSION = "assurance_chain_serialization_v1"
CANONICAL_SCHEMA = 1

# fixed decimal precision for float normalisation (prevents platform repr drift).
FLOAT_DECIMALS = 6

# the assurance chain, in deterministic phase order (used by export + comparison + package).
CHAIN_PHASE_ORDER = (
    ("phase26_revalidation", "Freshness & re-validation"),
    ("phase27_coverage", "Evidence coverage & blind spots"),
    ("phase28_readiness", "Knowledge readiness"),
    ("phase29_contradiction", "Contradiction detection & resolution"),
    ("phase30_assumptions", "Assumption register"),
    ("phase31_assurance", "Assurance findings & grade"),
    ("phase32_priority", "Engineering evidence priorities"),
)
CHAIN_PHASE_KEYS = tuple(k for k, _ in CHAIN_PHASE_ORDER)


class CanonicalSerializationError(ValueError):
    """Raised only on a genuine canonicalisation violation (e.g. a non-finite number)."""


def _normalize(o: Any) -> Any:
    """Recursively normalise a value into a canonical, JSON-safe, deterministic form. Never emits
    object identity/addresses; rejects non-finite floats; normalises enums to their value."""
    if o is None or isinstance(o, (str, bool)):
        return o
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, int):
        return o
    if isinstance(o, float):
        if not math.isfinite(o):
            raise CanonicalSerializationError("non-finite number is not allowed in canonical output")
        return round(o, FLOAT_DECIMALS)
    if isinstance(o, Mapping):
        # keys coerced to str; ordering handled by sort_keys at dump time.
        return {str(k): _normalize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_normalize(v) for v in o]
    # deterministic fallback for any other scalar (e.g. Decimal) - stringify.
    return str(o)


def canonical_obj(o: Any) -> Any:
    """Return the normalised canonical object (pure data; no identity/addresses)."""
    return _normalize(o)


def canonical_json(o: Any) -> str:
    """Deterministic canonical JSON string: sorted keys, compact separators, ASCII-only, no NaN."""
    return json.dumps(_normalize(o), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def canonical_bytes(o: Any) -> bytes:
    return canonical_json(o).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_digest(o: Any) -> str:
    """Full sha256 hex digest over the canonical bytes of an object (used for integrity/manifest)."""
    return sha256_hex(canonical_bytes(o))


def short_fingerprint(prefix: str, o: Any) -> str:
    """A prefixed, timestamp-free short fingerprint over the canonical bytes of an object."""
    return f"{prefix}:" + sha256_hex(canonical_bytes(o))[:24]


def subordinate_fingerprint(report: Mapping) -> str:
    """Return a report's own self-declared content fingerprint (retained, not trusted blindly)."""
    return str((report or {}).get("content_fingerprint") or "")


def recomputed_content_digest(report: Mapping) -> str:
    """Recompute a digest over the report's ACTUAL canonical content (excluding its self-declared
    fingerprint), so tampering is detectable independent of the claimed label."""
    r = dict(report or {})
    r.pop("content_fingerprint", None)
    return content_digest(r)


def serialization_versions() -> dict:
    return {"assurance_chain_serialization": ASSURANCE_CHAIN_SERIALIZATION_VERSION,
            "canonical_schema": CANONICAL_SCHEMA}


def is_safe_relative_name(name: str) -> bool:
    """A conservative artifact-name check: no path separators, no drive/absolute markers, no parent
    traversal, no leading dot-dot, ASCII printable only. Shared by the writer + the loader."""
    n = str(name or "")
    if not n or n in (".", ".."):
        return False
    if "/" in n or "\\" in n or ":" in n or "\x00" in n:
        return False
    if n.startswith((".", "~")) or ".." in n:
        return False
    return all(32 <= ord(c) < 127 for c in n)
