"""Legacy Evidence Trust (Program 2, Phase 42).

Applies the material-context trust to every historical (legacy) record for the CURRENT context, per
knowledge domain. Legacy records carry only the Phase-8 memory context (driver/car/track/layout/
discipline/gt7/compound); the event-condition material fields (BoP, tuning, multipliers, restrictions,
weather, objective) are genuinely unknown for them. This layer keeps those records VISIBLE, states per
domain whether each can be used exactly / equivalently / only as reference / etc., and NEVER upgrades a
record by assuming a missing field, nor discards it for missing new fields.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.material_context import (
    build_material_context_trust, MATERIAL_CONTEXT_VERSION, DOMAIN_REQUIRED, ContextTrust,
)

LEGACY_EVIDENCE_TRUST_VERSION = "legacy_evidence_trust_v1"
LEGACY_EVIDENCE_TRUST_SCHEMA = 1

# the record's memory-context fields map straight onto these material fields; everything else is unknown.
_RECORD_MATERIAL = ("driver", "car", "track", "layout_id", "discipline", "compound", "gt7_version")

_EXACT = (ContextTrust.EXACT_VERIFIED.value, ContextTrust.EQUIVALENT_VERIFIED.value)


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{LEGACY_EVIDENCE_TRUST_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


def _record_material(record: Mapping) -> dict:
    ctx = record.get("context") or {}
    return {f: _lc(ctx.get(f)) for f in _RECORD_MATERIAL if _lc(ctx.get(f))}


@dataclass(frozen=True)
class RecordDomainTrust:
    record_key: str
    domain_trust: dict          # domain -> overall_trust
    exact_domains: Tuple[str, ...]
    limitations: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {"record_key": self.record_key, "domain_trust": dict(self.domain_trust),
                "exact_domains": list(self.exact_domains), "limitations": list(self.limitations)}


@dataclass(frozen=True)
class LegacyEvidenceTrust:
    domains: Tuple[str, ...]
    records: Tuple[dict, ...]
    domain_exact_counts: dict
    visible_record_count: int
    discarded_record_count: int
    doctrine: str
    content_fingerprint: str
    schema_version: int = LEGACY_EVIDENCE_TRUST_SCHEMA
    eval_version: str = LEGACY_EVIDENCE_TRUST_VERSION

    def to_dict(self) -> dict:
        return {"domains": list(self.domains), "records": [dict(r) for r in self.records],
                "domain_exact_counts": dict(self.domain_exact_counts),
                "visible_record_count": self.visible_record_count,
                "discarded_record_count": self.discarded_record_count, "doctrine": self.doctrine,
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


_DOCTRINE = ("Legacy records stay visible; a missing material field caps (never blocks visibility). No "
             "record is discarded for missing new fields and none is upgraded by assuming an unknown "
             "value. Records are never dropped merely because event-condition fields were not recorded.")


def build_legacy_evidence_trust(current_material: Optional[Mapping],
                                records: Optional[Sequence[Mapping]],
                                domains: Optional[Sequence[str]] = None) -> LegacyEvidenceTrust:
    """For each legacy record, classify its per-domain trust vs the current material context.
    Deterministic; order-independent; never raises. No record is ever discarded."""
    try:
        cur = current_material if isinstance(current_material, Mapping) else {}
        recs = [r for r in (records or []) if isinstance(r, Mapping)]
        doms = tuple(domains) if domains else tuple(DOMAIN_REQUIRED.keys())
        out_records: List[RecordDomainTrust] = []
        exact_counts: Dict[str, int] = {d: 0 for d in doms}
        for rec in sorted(recs, key=lambda r: (_norm(r.get("recorded_at")), _norm(r.get("record_key")))):
            mat = _record_material(rec)
            domain_trust: Dict[str, str] = {}
            exact_domains: List[str] = []
            limitations: List[str] = []
            for d in doms:
                t = build_material_context_trust(cur, mat, d)
                domain_trust[d] = t.overall_trust
                if t.overall_trust in _EXACT:
                    exact_domains.append(d)
                    exact_counts[d] = exact_counts.get(d, 0) + 1
                elif t.limiting_fields:
                    limitations.append(f"{d}: " + ", ".join(f["field"] for f in t.limiting_fields))
            out_records.append(RecordDomainTrust(
                record_key=_norm(rec.get("record_key")), domain_trust=domain_trust,
                exact_domains=tuple(exact_domains), limitations=tuple(limitations)))
        fp = _fp({"cur": {k: _lc(cur.get(k)) for k in sorted(cur)} if isinstance(cur, dict) else {},
                  "domains": list(doms),
                  "records": [(r.record_key, sorted(r.domain_trust.items())) for r in out_records]})
        return LegacyEvidenceTrust(
            domains=doms, records=tuple(r.to_dict() for r in out_records),
            domain_exact_counts=exact_counts, visible_record_count=len(out_records),
            discarded_record_count=0, doctrine=_DOCTRINE, content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return LegacyEvidenceTrust(domains=(), records=(), domain_exact_counts={},
                                   visible_record_count=0, discarded_record_count=0, doctrine=_DOCTRINE,
                                   content_fingerprint=_fp({"e": 1}))


def legacy_trust_versions() -> dict:
    return {"legacy_evidence_trust": LEGACY_EVIDENCE_TRUST_VERSION,
            "material_context": MATERIAL_CONTEXT_VERSION, "schema": LEGACY_EVIDENCE_TRUST_SCHEMA}
