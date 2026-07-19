"""Assurance-Chain Export — deterministic on-demand export of the Phase 26-32 chain (Phase 33).

Assembles the complete assurance chain needed to explain the programme's current assurance state:
Phase 26 freshness, Phase 27 coverage, Phase 28 readiness, Phase 29 contradictions, Phase 30
assumptions, Phase 31 assurance findings & grade, Phase 32 evidence priorities - plus enough
provenance to identify the programme/context, knowledge domains, source-chain identity, GT7/rule
version context, chain schema versions, subordinate fingerprints and derivation order.

It consumes ALREADY-BUILT immutable domain products (it does not rebuild lower phases through
separate SessionDB entry points) and writes NO files. Advisory only; setup-value-free; read-only.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises into the caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

from strategy.assurance_chain_serialization import (
    ASSURANCE_CHAIN_SERIALIZATION_VERSION, CHAIN_PHASE_ORDER, CHAIN_PHASE_KEYS,
    canonical_obj, content_digest, recomputed_content_digest, subordinate_fingerprint,
    short_fingerprint, serialization_versions,
)

ASSURANCE_CHAIN_EXPORT_VERSION = "assurance_chain_export_v1"
ASSURANCE_CHAIN_EXPORT_SCHEMA = 1

_ADVISORY = ("Read-only, advisory-only assurance-chain export. It records the programme's current "
             "assurance state and the deterministic evidence behind it - it is NOT an independent "
             "certification, NOT an approval, NOT a setup recommendation and NOT permission to "
             "Apply. It creates no experiment/campaign/schedule, allocates no resources, carries no "
             "setup values, and changes no knowledge.")

_LIMITATIONS = (
    "An export reflects the recorded evidence and deterministic rules at build time; it does not "
    "prove real-world correctness.",
    "It is not an external certification and confers no approval.",
    "A missing section means that product was not available, not that the underlying knowledge is "
    "absent.",
    "Fingerprints prove content integrity and determinism, not engineering truth.",
)


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class ProvenanceEntry:
    phase_key: str
    title: str
    derivation_order: int
    present: bool
    schema_version: str
    eval_version: str
    subordinate_fingerprint: str
    recomputed_content_digest: str

    def to_dict(self) -> dict:
        return {"phase_key": self.phase_key, "title": self.title,
                "derivation_order": self.derivation_order, "present": self.present,
                "schema_version": self.schema_version, "eval_version": self.eval_version,
                "subordinate_fingerprint": self.subordinate_fingerprint,
                "recomputed_content_digest": self.recomputed_content_digest}


@dataclass(frozen=True)
class IntegrityEntry:
    section_key: str
    subordinate_fingerprint: str
    content_digest: str

    def to_dict(self) -> dict:
        return {"section_key": self.section_key,
                "subordinate_fingerprint": self.subordinate_fingerprint,
                "content_digest": self.content_digest}


@dataclass(frozen=True)
class AssuranceChainSection:
    phase_key: str
    title: str
    order: int
    present: bool
    content: dict
    subordinate_fingerprint: str
    content_digest: str

    def to_dict(self) -> dict:
        return {"phase_key": self.phase_key, "title": self.title, "order": self.order,
                "present": self.present, "content": dict(self.content),
                "subordinate_fingerprint": self.subordinate_fingerprint,
                "content_digest": self.content_digest}


@dataclass(frozen=True)
class ExportValidationResult:
    status: str            # valid / valid_empty / invalid
    errors: Tuple[str, ...]
    warnings: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {"status": self.status, "errors": list(self.errors),
                "warnings": list(self.warnings)}


@dataclass(frozen=True)
class AssuranceChainManifest:
    schema_version: int
    programme_identity: dict
    context_identity: dict
    source_chain_identity: dict
    db_schema_version: int
    rule_engine_version: str
    included_phase_versions: dict
    section_order: Tuple[str, ...]
    subordinate_fingerprints: dict
    assurance_grade: str
    assurance_chain_fingerprint: str
    canonical_manifest_fingerprint: str
    ordering: dict

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version,
                "programme_identity": dict(self.programme_identity),
                "context_identity": dict(self.context_identity),
                "source_chain_identity": dict(self.source_chain_identity),
                "db_schema_version": self.db_schema_version,
                "rule_engine_version": self.rule_engine_version,
                "included_phase_versions": dict(self.included_phase_versions),
                "section_order": list(self.section_order),
                "subordinate_fingerprints": dict(self.subordinate_fingerprints),
                "assurance_grade": self.assurance_grade,
                "assurance_chain_fingerprint": self.assurance_chain_fingerprint,
                "canonical_manifest_fingerprint": self.canonical_manifest_fingerprint,
                "ordering": dict(self.ordering)}


@dataclass(frozen=True)
class AssuranceChainExport:
    schema_version: int
    manifest: dict
    sections: Tuple[dict, ...]
    provenance: Tuple[dict, ...]
    integrity: Tuple[dict, ...]
    assurance_grade: str
    empty_state: str
    advisory_statement: str
    limitations: Tuple[str, ...]
    validation: dict
    chain_versions: dict
    content_fingerprint: str
    eval_version: str = ASSURANCE_CHAIN_EXPORT_VERSION

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version, "manifest": dict(self.manifest),
                "sections": [dict(s) for s in self.sections],
                "provenance": [dict(p) for p in self.provenance],
                "integrity": [dict(i) for i in self.integrity],
                "assurance_grade": self.assurance_grade, "empty_state": self.empty_state,
                "advisory_statement": self.advisory_statement, "limitations": list(self.limitations),
                "validation": dict(self.validation), "chain_versions": dict(self.chain_versions),
                "content_fingerprint": self.content_fingerprint, "eval_version": self.eval_version}


_ORDERING = {"phases": list(CHAIN_PHASE_KEYS),
             "note": "sections in fixed CHAIN_PHASE_ORDER; within each product, lists keep their "
                     "own deterministic order; canonical JSON sorts object keys; no timestamp affects "
                     "ordering or any fingerprint"}


def _phase_versions(report: Mapping) -> Tuple[str, str]:
    kv = report.get("knowledge_versions") if isinstance(report, Mapping) else None
    schema = ""
    if isinstance(kv, Mapping):
        schema = str(kv.get("schema") or "")
    return schema, str((report or {}).get("eval_version") or "")


def build_assurance_chain_export(chain_products: Optional[Mapping],
                                 context: Optional[Mapping]) -> AssuranceChainExport:
    """Build the assurance-chain export from already-built Phase-26..32 report dicts + a context
    (programme/domains/db+rule versions/source-chain identity). Deterministic; never raises."""
    try:
        return _build(chain_products or {}, context or {})
    except Exception as exc:   # never raise into the caller
        cv = chain_versions()
        empty = f"Export unavailable ({type(exc).__name__})."
        return AssuranceChainExport(
            schema_version=ASSURANCE_CHAIN_EXPORT_SCHEMA, manifest={}, sections=(), provenance=(),
            integrity=(), assurance_grade="insufficient_evidence", empty_state=empty,
            advisory_statement=_ADVISORY, limitations=_LIMITATIONS,
            validation=ExportValidationResult("invalid", (empty,), ()).to_dict(),
            chain_versions=cv, content_fingerprint=short_fingerprint(
                ASSURANCE_CHAIN_EXPORT_VERSION, {"error": type(exc).__name__, "cv": cv}))


def _build(chain_products: Mapping, context: Mapping) -> AssuranceChainExport:
    prog = dict(context.get("programme") or {})
    programme_identity = {k: str(prog.get(k, "") or "")
                          for k in ("car", "discipline", "gt7_version", "driver")}
    context_identity = {"layout_id": str(context.get("layout_id", "") or ""),
                        "compound": str(context.get("compound", "") or ""),
                        "domains": sorted(_lc(d) for d in (context.get("domains") or []))}
    db_schema_version = int(context.get("db_schema_version") or 0)
    rule_engine_version = str(context.get("rule_engine_version") or "")
    source_chain_identity = {k: _lc(v) for k, v in (context.get("source_chain") or {}).items()}

    sections: List[AssuranceChainSection] = []
    provenance: List[ProvenanceEntry] = []
    integrity: List[IntegrityEntry] = []
    subordinate_fps: dict = {}
    included_versions: dict = {}
    present_count = 0

    for order, (phase_key, title) in enumerate(CHAIN_PHASE_ORDER):
        report = chain_products.get(phase_key)
        present = isinstance(report, Mapping) and bool(report)
        content = canonical_obj(dict(report)) if present else {}
        sub_fp = subordinate_fingerprint(report) if present else ""
        digest = recomputed_content_digest(report) if present else content_digest({})
        if present:
            present_count += 1
        schema_v, eval_v = _phase_versions(report if present else {})
        sections.append(AssuranceChainSection(phase_key=phase_key, title=title, order=order,
                                              present=present, content=content,
                                              subordinate_fingerprint=sub_fp, content_digest=digest))
        provenance.append(ProvenanceEntry(phase_key=phase_key, title=title, derivation_order=order,
                                          present=present, schema_version=schema_v,
                                          eval_version=eval_v, subordinate_fingerprint=sub_fp,
                                          recomputed_content_digest=digest))
        integrity.append(IntegrityEntry(section_key=phase_key, subordinate_fingerprint=sub_fp,
                                        content_digest=digest))
        subordinate_fps[phase_key] = sub_fp
        if present:
            included_versions[phase_key] = {"schema": schema_v, "eval_version": eval_v}

    assurance = chain_products.get("phase31_assurance") or {}
    grade = _lc(assurance.get("assurance_grade")) or "insufficient_evidence"

    # assurance-chain fingerprint over the ACTUAL recomputed content digests (not the self-labels),
    # plus identity + versions + fixed section order -> changes on any material subordinate change.
    chain_fp = short_fingerprint(ASSURANCE_CHAIN_EXPORT_VERSION, {
        "prog": programme_identity, "ctx": context_identity,
        "db": db_schema_version, "rule": rule_engine_version, "src": source_chain_identity,
        "sections": [(s.phase_key, s.order, s.present, s.content_digest) for s in sections],
        "grade": grade, "cv": chain_versions()})

    manifest_core = {
        "schema_version": ASSURANCE_CHAIN_EXPORT_SCHEMA, "programme_identity": programme_identity,
        "context_identity": context_identity, "source_chain_identity": source_chain_identity,
        "db_schema_version": db_schema_version, "rule_engine_version": rule_engine_version,
        "included_phase_versions": included_versions, "section_order": list(CHAIN_PHASE_KEYS),
        "subordinate_fingerprints": subordinate_fps, "assurance_grade": grade,
        "assurance_chain_fingerprint": chain_fp, "ordering": _ORDERING}
    manifest_fp = short_fingerprint(ASSURANCE_CHAIN_EXPORT_VERSION, manifest_core)

    manifest = AssuranceChainManifest(
        schema_version=ASSURANCE_CHAIN_EXPORT_SCHEMA, programme_identity=programme_identity,
        context_identity=context_identity, source_chain_identity=source_chain_identity,
        db_schema_version=db_schema_version, rule_engine_version=rule_engine_version,
        included_phase_versions=included_versions, section_order=CHAIN_PHASE_KEYS,
        subordinate_fingerprints=subordinate_fps, assurance_grade=grade,
        assurance_chain_fingerprint=chain_fp, canonical_manifest_fingerprint=manifest_fp,
        ordering=_ORDERING)

    errors: List[str] = []
    warnings: List[str] = []
    if present_count == 0:
        status = "valid_empty"
        warnings.append("no assurance products present - the programme has no established knowledge "
                        "to export yet")
    else:
        status = "valid"
        for key in ("phase31_assurance",):
            if not subordinate_fps.get(key):
                warnings.append(f"{key} present without a self-declared fingerprint")
    validation = ExportValidationResult(status=status, errors=tuple(errors), warnings=tuple(warnings))

    empty = "" if present_count else ("Nothing to export yet - the programme has recorded no "
                                      "established assurance knowledge.")

    export_fp = short_fingerprint(ASSURANCE_CHAIN_EXPORT_VERSION, {
        "manifest": manifest.to_dict(),
        "sections": [(s.phase_key, s.order, s.present, s.content_digest) for s in sections],
        "grade": grade, "status": status})

    return AssuranceChainExport(
        schema_version=ASSURANCE_CHAIN_EXPORT_SCHEMA, manifest=manifest.to_dict(),
        sections=tuple(s.to_dict() for s in sections),
        provenance=tuple(p.to_dict() for p in provenance),
        integrity=tuple(i.to_dict() for i in integrity), assurance_grade=grade, empty_state=empty,
        advisory_statement=_ADVISORY, limitations=_LIMITATIONS, validation=validation.to_dict(),
        chain_versions=chain_versions(), content_fingerprint=export_fp)


def _recomputed_section_digests(export: Mapping) -> Dict[str, Tuple[bool, str]]:
    """Return {phase_key: (present, recomputed_content_digest)} recomputed from the section CONTENT
    (never trusting the claimed digest). Used for independent integrity verification."""
    out: Dict[str, Tuple[bool, str]] = {}
    by_key = {_lc(s.get("phase_key")): s for s in (export.get("sections") or [])
              if isinstance(s, Mapping)}
    for _order, (phase_key, _title) in enumerate(CHAIN_PHASE_ORDER):
        s = by_key.get(phase_key) or {}
        present = bool(s.get("present"))
        content = s.get("content") if isinstance(s.get("content"), Mapping) else {}
        digest = recomputed_content_digest(content) if present else content_digest({})
        out[phase_key] = (present, digest)
    return out


def recompute_chain_fingerprint(export: Mapping) -> str:
    """Independently recompute the assurance-chain fingerprint from an export dict, recomputing each
    section's content digest from its content (so tampered content is detected). Deterministic."""
    m = export.get("manifest") or {}
    digests = _recomputed_section_digests(export)
    sections = [(phase_key, order, digests[phase_key][0], digests[phase_key][1])
                for order, (phase_key, _t) in enumerate(CHAIN_PHASE_ORDER)]
    return short_fingerprint(ASSURANCE_CHAIN_EXPORT_VERSION, {
        "prog": m.get("programme_identity") or {}, "ctx": m.get("context_identity") or {},
        "db": m.get("db_schema_version"), "rule": m.get("rule_engine_version"),
        "src": m.get("source_chain_identity") or {}, "sections": sections,
        "grade": _lc(m.get("assurance_grade")), "cv": chain_versions()})


def verify_export_integrity(export: Mapping) -> dict:
    """Independently verify an export dict: recompute each section digest and the chain fingerprint,
    compare to the claimed values. Returns {ok, section_mismatches, chain_fingerprint_ok,
    claimed_chain_fingerprint, recomputed_chain_fingerprint}. Never raises."""
    try:
        m = export.get("manifest") or {}
        by_key = {_lc(s.get("phase_key")): s for s in (export.get("sections") or [])
                  if isinstance(s, Mapping)}
        recomputed = _recomputed_section_digests(export)
        mismatches = []
        for phase_key, (_present, digest) in recomputed.items():
            claimed = _lc((by_key.get(phase_key) or {}).get("content_digest"))
            if claimed and claimed != digest:
                mismatches.append(phase_key)
        claimed_fp = str(m.get("assurance_chain_fingerprint") or "")
        recomputed_fp = recompute_chain_fingerprint(export)
        chain_ok = (claimed_fp == recomputed_fp) if claimed_fp else False
        return {"ok": (not mismatches) and chain_ok, "section_mismatches": mismatches,
                "chain_fingerprint_ok": chain_ok, "claimed_chain_fingerprint": claimed_fp,
                "recomputed_chain_fingerprint": recomputed_fp}
    except Exception as exc:
        return {"ok": False, "section_mismatches": ["error"], "chain_fingerprint_ok": False,
                "claimed_chain_fingerprint": "", "recomputed_chain_fingerprint": "",
                "error": type(exc).__name__}


def chain_versions() -> dict:
    return {"assurance_chain_export": ASSURANCE_CHAIN_EXPORT_VERSION,
            "assurance_chain_serialization": ASSURANCE_CHAIN_SERIALIZATION_VERSION,
            "schema": ASSURANCE_CHAIN_EXPORT_SCHEMA,
            **serialization_versions()}
