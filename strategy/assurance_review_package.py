"""Assurance Review Package — pure package specification (Program 2, Phase 35).

A pure, deterministic SPECIFICATION of the artifacts that make up an external assurance review
package. It computes every artifact's content + content digest, the package manifest, and the
package fingerprint - but writes NOTHING. Only the separate writer adapter
(``data/assurance_review_package_writer.py``) may materialise these artifacts to disk, and only on an
explicit user export action.

The package answers, for an external reviewer without the application: "does this assurance verdict
genuinely follow from the recorded evidence and deterministic rules?" - via a human-readable report,
a machine-readable manifest, content digests, fingerprints, provenance and verification instructions
that do not require trusting filenames or timestamps.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises into the caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

from strategy.assurance_chain_serialization import (
    ASSURANCE_CHAIN_SERIALIZATION_VERSION, canonical_json, canonical_obj, content_digest,
    short_fingerprint, serialization_versions, is_safe_relative_name,
)
from strategy.assurance_chain_export_render import render_export_text
from strategy.assurance_snapshot_comparison_render import render_comparison_text

ASSURANCE_REVIEW_PACKAGE_VERSION = "assurance_review_package_v1"
ASSURANCE_REVIEW_PACKAGE_SCHEMA = 1

# artifact kinds in deterministic membership order.
ARTIFACT_ORDER = ("assurance_review_report", "assurance_chain_manifest", "comparison_report",
                  "comparison_manifest")

_ARTIFACT_NAME = {
    "assurance_review_report": "assurance_review_report.md",
    "assurance_chain_manifest": "assurance_chain_manifest.json",
    "comparison_report": "assurance_comparison_report.md",
    "comparison_manifest": "assurance_comparison_manifest.json",
}
_ARTIFACT_MEDIA = {
    "assurance_review_report": "text/markdown",
    "assurance_chain_manifest": "application/json",
    "comparison_report": "text/markdown",
    "comparison_manifest": "application/json",
}
# the package manifest file is written but is NOT one of the digest-listed member artifacts.
PACKAGE_MANIFEST_NAME = "package_manifest.json"

_ADVISORY = ("Read-only, advisory-only external review package. It records the programme's current "
             "assurance state, the deterministic evidence behind it and (optionally) a comparison - "
             "it is NOT an independent certification, NOT an approval, NOT a setup recommendation and "
             "NOT permission to Apply. It contains no database, no setup history, no settings and no "
             "secrets. Generated only on an explicit export action.")

_LIMITATIONS = (
    "The package reflects recorded evidence and deterministic rules at build time; it does not prove "
    "real-world correctness and is not a certification.",
    "Fingerprints and digests prove content integrity and determinism, not engineering truth.",
    "A comparison is only meaningful when the two snapshots are compatible.",
    "Trust the recomputed digests and fingerprints, not the filenames or file timestamps.",
)

_VERIFICATION_INSTRUCTIONS = (
    "1. For each member artifact, read its raw UTF-8 bytes and compute sha256; confirm it matches the "
    "content_digest recorded for that artifact in package_manifest.json - match by 'kind', never by "
    "filename.",
    "2. Recompute the package_fingerprint as a sha256 (first 24 hex) over the canonical JSON of the "
    "sorted list of (kind, content_digest) pairs plus the package identity; confirm it matches "
    "package_manifest.json.",
    "3. Recompute the assurance_chain_fingerprint from the chain manifest's per-section content "
    "digests (recompute each section digest from its content); confirm it matches.",
    "4. Do not trust filenames, directory names, archive metadata or file modification times - they "
    "are not part of any fingerprint.",
    "5. A different rule-engine or GT7 version, or a mismatched programme identity, makes a baseline "
    "comparison partially compatible or incompatible; an incompatible comparison shows no trend.",
)


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class ReviewArtifact:
    kind: str
    name: str
    media_type: str
    text: str               # for text artifacts (report); "" for json artifacts
    obj: dict               # for json artifacts ({} for text artifacts)
    is_text: bool
    content_digest: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "name": self.name, "media_type": self.media_type,
                "is_text": self.is_text, "content_digest": self.content_digest}


@dataclass(frozen=True)
class AssuranceReviewPackage:
    schema_version: int
    package_schema_version: int
    identity: dict
    assurance_grade: str
    assurance_chain_fingerprint: str
    comparison_fingerprint: str
    has_comparison: bool
    artifacts: Tuple[ReviewArtifact, ...]
    package_manifest: dict
    package_fingerprint: str
    advisory_statement: str
    limitations: Tuple[str, ...]
    verification_instructions: Tuple[str, ...]
    package_versions: dict
    eval_version: str = ASSURANCE_REVIEW_PACKAGE_VERSION

    def artifact(self, kind: str) -> Optional[ReviewArtifact]:
        for a in self.artifacts:
            if a.kind == kind:
                return a
        return None

    def artifact_bytes(self, kind: str) -> bytes:
        a = self.artifact(kind)
        if a is None:
            return b""
        return (a.text.encode("utf-8") if a.is_text else canonical_json(a.obj).encode("utf-8"))

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version,
                "package_schema_version": self.package_schema_version, "identity": dict(self.identity),
                "assurance_grade": self.assurance_grade,
                "assurance_chain_fingerprint": self.assurance_chain_fingerprint,
                "comparison_fingerprint": self.comparison_fingerprint,
                "has_comparison": self.has_comparison,
                "artifacts": [a.to_dict() for a in self.artifacts],
                "package_manifest": dict(self.package_manifest),
                "package_fingerprint": self.package_fingerprint,
                "advisory_statement": self.advisory_statement, "limitations": list(self.limitations),
                "verification_instructions": list(self.verification_instructions),
                "package_versions": dict(self.package_versions), "eval_version": self.eval_version}


def _chain_manifest_obj(export: Mapping) -> dict:
    """The machine-readable chain manifest: the export manifest + per-section integrity summary +
    limitations/advisory - sufficient for independent validation without the full section bodies."""
    m = export.get("manifest") or {}
    return canonical_obj({
        "schema_version": export.get("schema_version"),
        "manifest": m,
        "sections": [{"phase_key": s.get("phase_key"), "order": s.get("order"),
                      "present": s.get("present"), "title": s.get("title"),
                      "subordinate_fingerprint": s.get("subordinate_fingerprint"),
                      "content_digest": s.get("content_digest"),
                      "content": s.get("content")} for s in (export.get("sections") or [])],
        "provenance": export.get("provenance") or [],
        "integrity": export.get("integrity") or [],
        "validation": export.get("validation") or {},
        "advisory_statement": export.get("advisory_statement"),
        "limitations": export.get("limitations") or [],
        "content_fingerprint": export.get("content_fingerprint"),
        "chain_versions": export.get("chain_versions") or {},
    })


def build_review_package_spec(export: Optional[Mapping], comparison: Optional[Mapping] = None,
                              identity_hint: Optional[Mapping] = None) -> AssuranceReviewPackage:
    """Build the pure package specification from an already-built export (and optional comparison).
    Writes nothing. Deterministic; never raises."""
    try:
        return _build(export or {}, comparison, identity_hint or {})
    except Exception as exc:   # never raise into the caller
        pv = package_versions()
        return AssuranceReviewPackage(
            schema_version=ASSURANCE_REVIEW_PACKAGE_SCHEMA,
            package_schema_version=ASSURANCE_REVIEW_PACKAGE_SCHEMA, identity={},
            assurance_grade="insufficient_evidence", assurance_chain_fingerprint="",
            comparison_fingerprint="", has_comparison=False, artifacts=(),
            package_manifest={"error": type(exc).__name__}, package_fingerprint=short_fingerprint(
                ASSURANCE_REVIEW_PACKAGE_VERSION, {"error": type(exc).__name__}),
            advisory_statement=_ADVISORY, limitations=_LIMITATIONS,
            verification_instructions=_VERIFICATION_INSTRUCTIONS, package_versions=pv)


def _build(export: Mapping, comparison: Optional[Mapping],
           identity_hint: Mapping) -> AssuranceReviewPackage:
    m = export.get("manifest") or {}
    identity = {"programme": m.get("programme_identity") or identity_hint.get("programme") or {},
                "context": m.get("context_identity") or {},
                "db_schema_version": m.get("db_schema_version"),
                "rule_engine_version": m.get("rule_engine_version")}
    grade = _lc(m.get("assurance_grade")) or _lc(export.get("assurance_grade")) or "insufficient_evidence"
    chain_fp = str(m.get("assurance_chain_fingerprint") or "")
    has_comparison = bool(comparison)
    comparison_fp = str((comparison or {}).get("content_fingerprint") or "") if has_comparison else ""

    # build artifacts (deterministic order).
    artifacts: List[ReviewArtifact] = []

    report_text = render_export_text(export)
    if has_comparison:
        report_text = report_text.rstrip() + "\n\n" + render_comparison_text(comparison)
    artifacts.append(_text_artifact("assurance_review_report", report_text))

    artifacts.append(_json_artifact("assurance_chain_manifest", _chain_manifest_obj(export)))

    if has_comparison:
        artifacts.append(_text_artifact("comparison_report", render_comparison_text(comparison)))
        artifacts.append(_json_artifact("comparison_manifest", canonical_obj(dict(comparison))))

    # keep deterministic membership order.
    artifacts.sort(key=lambda a: ARTIFACT_ORDER.index(a.kind) if a.kind in ARTIFACT_ORDER else 99)

    member_list = [{"kind": a.kind, "name": a.name, "media_type": a.media_type,
                    "content_digest": a.content_digest, "is_text": a.is_text} for a in artifacts]

    package_manifest_core = {
        "schema_version": ASSURANCE_REVIEW_PACKAGE_SCHEMA,
        "package_schema_version": ASSURANCE_REVIEW_PACKAGE_SCHEMA,
        "identity": canonical_obj(identity), "assurance_grade": grade,
        "assurance_chain_fingerprint": chain_fp, "has_comparison": has_comparison,
        "comparison_fingerprint": comparison_fp, "artifacts": member_list,
        "artifact_order": list(ARTIFACT_ORDER),
        "verification_instructions": list(_VERIFICATION_INSTRUCTIONS),
        "limitations": list(_LIMITATIONS), "advisory_statement": _ADVISORY,
        "package_versions": package_versions()}

    # package fingerprint over the SORTED (kind, content_digest) pairs + identity + grade + chain fp
    # + comparison fp. The destination path / filenames / timestamps are NOT part of it.
    package_fp = short_fingerprint(ASSURANCE_REVIEW_PACKAGE_VERSION, {
        "identity": canonical_obj(identity), "grade": grade, "chain_fp": chain_fp,
        "comparison_fp": comparison_fp,
        "members": sorted((a.kind, a.content_digest) for a in artifacts),
        "pv": package_versions()})

    package_manifest = dict(package_manifest_core)
    package_manifest["package_fingerprint"] = package_fp

    return AssuranceReviewPackage(
        schema_version=ASSURANCE_REVIEW_PACKAGE_SCHEMA,
        package_schema_version=ASSURANCE_REVIEW_PACKAGE_SCHEMA, identity=identity,
        assurance_grade=grade, assurance_chain_fingerprint=chain_fp,
        comparison_fingerprint=comparison_fp, has_comparison=has_comparison,
        artifacts=tuple(artifacts), package_manifest=package_manifest, package_fingerprint=package_fp,
        advisory_statement=_ADVISORY, limitations=_LIMITATIONS,
        verification_instructions=_VERIFICATION_INSTRUCTIONS, package_versions=package_versions())


def _text_artifact(kind: str, text: str) -> ReviewArtifact:
    name = _ARTIFACT_NAME[kind]
    data = text.encode("utf-8")
    return ReviewArtifact(kind=kind, name=name, media_type=_ARTIFACT_MEDIA[kind], text=text, obj={},
                          is_text=True, content_digest=content_digest_bytes(data))


def _json_artifact(kind: str, obj: dict) -> ReviewArtifact:
    name = _ARTIFACT_NAME[kind]
    data = canonical_json(obj).encode("utf-8")
    return ReviewArtifact(kind=kind, name=name, media_type=_ARTIFACT_MEDIA[kind], text="", obj=obj,
                          is_text=False, content_digest=content_digest_bytes(data))


def content_digest_bytes(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def package_manifest_bytes(pkg: AssuranceReviewPackage) -> bytes:
    return canonical_json(pkg.package_manifest).encode("utf-8")


def safe_artifact_names(pkg: AssuranceReviewPackage) -> bool:
    names = [a.name for a in pkg.artifacts] + [PACKAGE_MANIFEST_NAME]
    return len(names) == len(set(names)) and all(is_safe_relative_name(n) for n in names)


def package_versions() -> dict:
    return {"assurance_review_package": ASSURANCE_REVIEW_PACKAGE_VERSION,
            "schema": ASSURANCE_REVIEW_PACKAGE_SCHEMA, **serialization_versions()}
