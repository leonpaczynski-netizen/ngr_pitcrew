"""Immutable Engineering Context Snapshot (Program 2, Phase 45).

The canonical immutable record of the exact SEMANTIC engineering context that existed when new evidence
was created. A reference to a mutable Event Planner record is NOT sufficient historical provenance - a
later event edit must not alter what an old snapshot means. This module owns the pure snapshot content,
its deterministic canonical serialization, its full semantic digest and short display fingerprint, and
its validation. Persistence + references live in SessionDB (an additive v27 table); this module writes
nothing.

Semantic identity EXCLUDES: database row id, insertion order, machine identity, filesystem paths, UI
state, wall-clock capture time, and non-authoritative display metadata (event name). A separate audit
timestamp may be stored operationally but never enters the semantic digest.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Fabricates NO absent value - unknown stays unknown.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Tuple

from strategy.assurance_chain_serialization import canonical_json, sha256_hex

ENGINEERING_CONTEXT_SNAPSHOT_VERSION = "engineering_context_snapshot_v1"
ENGINEERING_CONTEXT_SNAPSHOT_SCHEMA = 1

# semantic material fields (canonical order). event_name is display-only and is NOT in this set.
SNAPSHOT_SEMANTIC_FIELDS: Tuple[str, ...] = (
    "driver", "car", "car_variant", "track", "layout_id", "event_id", "discipline", "compound",
    "compound_policy", "bop_state", "tuning_permitted", "power_restriction", "weight_restriction",
    "tyre_multiplier", "fuel_multiplier", "refuel_rate", "race_type", "race_duration",
    "race_lap_objective", "weather", "grip_state", "assist_policy", "gt7_version",
    "rule_engine_version", "data_schema_version", "applied_setup_id", "applied_setup_fingerprint",
    "parent_setup_id", "run_plan_fingerprint", "experiment_id")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


class SnapshotValidationState(str, Enum):
    VALID = "valid"
    INCOMPLETE = "incomplete"      # missing one or more core identity fields (still storable)
    INVALID = "invalid"


# the core identity a snapshot should carry to be materially useful (missing => INCOMPLETE, not INVALID).
_CORE = ("driver", "car", "track", "layout_id", "discipline", "gt7_version")


@dataclass(frozen=True)
class EngineeringContextSnapshotContent:
    """Immutable semantic content. Unknown fields are empty strings (explicitly unknown, never
    fabricated). ``event_name`` is non-authoritative display metadata (excluded from the digest)."""
    driver: str = ""
    car: str = ""
    car_variant: str = ""
    track: str = ""
    layout_id: str = ""
    event_id: str = ""
    event_name: str = ""            # display only - NOT semantic
    discipline: str = ""
    compound: str = ""
    compound_policy: str = ""
    bop_state: str = ""
    tuning_permitted: str = ""
    power_restriction: str = ""
    weight_restriction: str = ""
    tyre_multiplier: str = ""
    fuel_multiplier: str = ""
    refuel_rate: str = ""
    race_type: str = ""
    race_duration: str = ""
    race_lap_objective: str = ""
    weather: str = ""
    grip_state: str = ""
    assist_policy: str = ""
    gt7_version: str = ""
    rule_engine_version: str = ""
    data_schema_version: str = ""
    applied_setup_id: str = ""
    applied_setup_fingerprint: str = ""
    parent_setup_id: str = ""
    run_plan_fingerprint: str = ""
    experiment_id: str = ""

    def semantic_dict(self) -> dict:
        """The canonical semantic content (event_name excluded). Values normalised; unknown = ''."""
        return {f: _norm(getattr(self, f)) for f in SNAPSHOT_SEMANTIC_FIELDS}

    def display_dict(self) -> dict:
        d = self.semantic_dict()
        d["event_name"] = _norm(self.event_name)
        return d

    @classmethod
    def from_dict(cls, d: Optional[Mapping]) -> "EngineeringContextSnapshotContent":
        d = d if isinstance(d, Mapping) else {}
        allowed = set(SNAPSHOT_SEMANTIC_FIELDS) | {"event_name"}
        return cls(**{k: _norm(v) for k, v in d.items() if k in allowed})


@dataclass(frozen=True)
class EngineeringContextSnapshot:
    content: dict                 # display dict (semantic + event_name)
    semantic_digest: str          # full sha256 over canonical semantic content
    short_fingerprint: str        # prefixed short display fingerprint
    validation_state: str
    missing_core: Tuple[str, ...]
    schema_version: int = ENGINEERING_CONTEXT_SNAPSHOT_SCHEMA
    eval_version: str = ENGINEERING_CONTEXT_SNAPSHOT_VERSION

    def to_dict(self) -> dict:
        return {"content": dict(self.content), "semantic_digest": self.semantic_digest,
                "short_fingerprint": self.short_fingerprint,
                "validation_state": self.validation_state, "missing_core": list(self.missing_core),
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def _digest(semantic: Mapping) -> str:
    # canonical, sorted-key, ASCII, allow_nan=False JSON over the semantic content + schema id.
    return sha256_hex(canonical_json({"schema": ENGINEERING_CONTEXT_SNAPSHOT_SCHEMA,
                                      "v": ENGINEERING_CONTEXT_SNAPSHOT_VERSION,
                                      "content": dict(semantic)}).encode("utf-8"))


def build_context_snapshot(content) -> EngineeringContextSnapshot:
    """Build an immutable snapshot from content (an ``EngineeringContextSnapshotContent`` or a mapping).
    Deterministic; never raises. The digest excludes event_name / wall-clock / row id / paths."""
    try:
        c = content if isinstance(content, EngineeringContextSnapshotContent) \
            else EngineeringContextSnapshotContent.from_dict(content)
        semantic = c.semantic_dict()
        digest = _digest(semantic)
        short_fp = f"{ENGINEERING_CONTEXT_SNAPSHOT_VERSION}:snap:" + digest[:24]
        missing = tuple(f for f in _CORE if not _norm(semantic.get(f)))
        state = (SnapshotValidationState.VALID if not missing
                 else SnapshotValidationState.INCOMPLETE)
        return EngineeringContextSnapshot(
            content=c.display_dict(), semantic_digest=digest, short_fingerprint=short_fp,
            validation_state=state.value, missing_core=missing)
    except Exception:  # pragma: no cover - defensive
        return EngineeringContextSnapshot(content={}, semantic_digest=_digest({}),
                                          short_fingerprint=f"{ENGINEERING_CONTEXT_SNAPSHOT_VERSION}:snap:err",
                                          validation_state=SnapshotValidationState.INVALID.value,
                                          missing_core=tuple(_CORE))


def snapshot_semantic_digest(content) -> str:
    """Return only the semantic digest of some content (mapping or dataclass). Deterministic."""
    c = content if isinstance(content, EngineeringContextSnapshotContent) \
        else EngineeringContextSnapshotContent.from_dict(content)
    return _digest(c.semantic_dict())


def snapshots_semantically_equal(a, b) -> bool:
    """True iff two contents have identical semantic content (event_name / audit time ignored)."""
    return snapshot_semantic_digest(a) == snapshot_semantic_digest(b)


def context_snapshot_versions() -> dict:
    return {"engineering_context_snapshot": ENGINEERING_CONTEXT_SNAPSHOT_VERSION,
            "schema": ENGINEERING_CONTEXT_SNAPSHOT_SCHEMA}
