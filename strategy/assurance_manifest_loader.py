"""Assurance Manifest Loader / Validator — strict read-only baseline import (Program 2, Phase 34/35).

A pure, strict validator for a previously-generated Phase-33 export or Phase-35 review-package
manifest supplied as a baseline. It never executes content, never imports Python objects, never uses
pickle, and never trusts a claimed fingerprint or digest without recomputation. File reading happens
in a thin adapter above this module; this module operates on JSON TEXT or an already-parsed object.

It validates schema + required fields, recomputes fingerprints and content digests, and rejects
malformed / unsupported manifests, path-traversal artifact names, duplicate artifact names,
non-finite numeric values and silent enum fallback.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises into the caller.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

from strategy.assurance_chain_serialization import (
    recomputed_content_digest, is_safe_relative_name, canonical_json,
)
from strategy.assurance_chain_export import (
    ASSURANCE_CHAIN_EXPORT_SCHEMA, verify_export_integrity, recompute_chain_fingerprint,
)
from strategy.assurance_review_package import (
    ASSURANCE_REVIEW_PACKAGE_SCHEMA, ARTIFACT_ORDER,
)

ASSURANCE_MANIFEST_LOADER_VERSION = "assurance_manifest_loader_v1"

# accepted enum-ish values (no silent fallback): assurance grades that may appear in a baseline.
_VALID_GRADES = frozenset({"insufficient_evidence", "not_assured", "partially_assured",
                           "assured_with_limitations", "assured"})


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class LoadResult:
    ok: bool
    kind: str                       # export / review_package / unknown
    errors: Tuple[str, ...]
    warnings: Tuple[str, ...]
    recomputed_fingerprints: dict
    export: Optional[dict]          # the validated export dict (for comparison), or None

    def to_dict(self) -> dict:
        return {"ok": self.ok, "kind": self.kind, "errors": list(self.errors),
                "warnings": list(self.warnings),
                "recomputed_fingerprints": dict(self.recomputed_fingerprints),
                "has_export": self.export is not None}


def _reject_non_finite(_s, *_a, **_k):
    raise ValueError("non-finite number is not allowed in a baseline manifest")


def parse_canonical_json(text) -> Tuple[Optional[object], Optional[str]]:
    """Parse JSON text with strict rejection of non-finite constants (Infinity/-Infinity/NaN) and of
    non-JSON input. Returns (obj, None) or (None, error). Never executes content; no pickle."""
    if isinstance(text, (bytes, bytearray)):
        try:
            text = text.decode("utf-8")
        except Exception:
            return None, "manifest is not valid UTF-8"
    if not isinstance(text, str):
        return None, "manifest text must be a string"
    try:
        obj = json.loads(text, parse_constant=_reject_non_finite)
    except ValueError as exc:
        return None, f"malformed or unsupported JSON: {exc}"
    return obj, None


def _detect_kind(obj: Mapping) -> str:
    if not isinstance(obj, Mapping):
        return "unknown"
    if "artifacts" in obj and "package_fingerprint" in obj:
        return "review_package"
    if "sections" in obj and "manifest" in obj:
        return "export"
    # a review-package member could be the chain manifest wrapper (has 'manifest' + 'sections')
    if isinstance(obj.get("manifest"), Mapping) and "sections" in obj:
        return "export"
    return "unknown"


def validate_baseline(obj: Optional[Mapping]) -> LoadResult:
    """Validate an already-parsed baseline object (export or review-package manifest). Deterministic;
    never raises."""
    try:
        return _validate(obj if isinstance(obj, Mapping) else {})
    except Exception as exc:
        return LoadResult(ok=False, kind="unknown", errors=(f"validation error: {type(exc).__name__}",),
                          warnings=(), recomputed_fingerprints={}, export=None)


def load_and_validate_baseline(text) -> LoadResult:
    """Parse JSON text then validate. Never raises."""
    obj, err = parse_canonical_json(text)
    if err:
        return LoadResult(ok=False, kind="unknown", errors=(err,), warnings=(),
                          recomputed_fingerprints={}, export=None)
    return validate_baseline(obj)


def _validate(obj: Mapping) -> LoadResult:
    kind = _detect_kind(obj)
    if kind == "export":
        return _validate_export(obj)
    if kind == "review_package":
        return _validate_review_package(obj)
    return LoadResult(ok=False, kind="unknown",
                      errors=("unrecognised manifest: not an assurance export or review package",),
                      warnings=(), recomputed_fingerprints={}, export=None)


def _validate_export(export: Mapping) -> LoadResult:
    errors: List[str] = []
    warnings: List[str] = []
    m = export.get("manifest")
    if not isinstance(m, Mapping):
        return LoadResult(False, "export", ("export has no manifest",), (), {}, None)
    if export.get("schema_version") != ASSURANCE_CHAIN_EXPORT_SCHEMA:
        errors.append(f"unsupported export schema_version {export.get('schema_version')}")
    for f in ("programme_identity", "assurance_chain_fingerprint", "section_order"):
        if not m.get(f):
            errors.append(f"manifest missing required field: {f}")
    grade = _lc(m.get("assurance_grade"))
    if grade and grade not in _VALID_GRADES:
        errors.append(f"unknown assurance grade (no silent fallback): {grade}")
    if not isinstance(export.get("sections"), list):
        errors.append("export sections missing or not a list")

    integ = verify_export_integrity(export)
    recomputed = {"assurance_chain_fingerprint": integ.get("recomputed_chain_fingerprint", "")}
    if integ.get("section_mismatches"):
        errors.append("section content digest mismatch: "
                      + ", ".join(integ["section_mismatches"]))
    claimed_fp = _lc(m.get("assurance_chain_fingerprint"))
    if claimed_fp and not integ.get("chain_fingerprint_ok"):
        errors.append("assurance-chain fingerprint does not match the recomputed value (tampered "
                      "or corrupted)")

    ok = not errors
    export_out = dict(export) if ok else None
    return LoadResult(ok=ok, kind="export", errors=tuple(errors), warnings=tuple(warnings),
                      recomputed_fingerprints=recomputed, export=export_out)


def _validate_review_package(pm: Mapping) -> LoadResult:
    """Validate a review-package MANIFEST (the package_manifest.json object). It validates structure,
    artifact-name safety, duplicate names and (when the embedded chain manifest is present) the chain
    fingerprint. Full artifact-byte digest verification is done by the writer/caller which holds the
    bytes; here we validate the manifest self-consistency."""
    errors: List[str] = []
    warnings: List[str] = []
    if pm.get("schema_version") != ASSURANCE_REVIEW_PACKAGE_SCHEMA:
        errors.append(f"unsupported package schema_version {pm.get('schema_version')}")
    arts = pm.get("artifacts")
    if not isinstance(arts, list) or not arts:
        errors.append("package manifest has no artifacts")
        arts = []
    names = []
    for a in arts:
        if not isinstance(a, Mapping):
            errors.append("artifact entry is not an object")
            continue
        name = str(a.get("name") or "")
        kind = _lc(a.get("kind"))
        if not is_safe_relative_name(name):
            errors.append(f"unsafe or path-traversing artifact name rejected: {name!r}")
        if kind and kind not in ARTIFACT_ORDER:
            errors.append(f"unknown artifact kind (no silent fallback): {kind}")
        if not _lc(a.get("content_digest")):
            errors.append(f"artifact {name!r} has no content_digest")
        names.append(name)
    if len(names) != len(set(names)):
        errors.append("duplicate artifact names in package manifest")
    if not _lc(pm.get("package_fingerprint")):
        errors.append("package manifest has no package_fingerprint")

    recomputed: dict = {}
    ok = not errors
    return LoadResult(ok=ok, kind="review_package", errors=tuple(errors), warnings=tuple(warnings),
                      recomputed_fingerprints=recomputed, export=None)


def verify_review_package_artifacts(package_manifest: Mapping,
                                    artifact_bytes_by_name: Mapping) -> dict:
    """Independently verify the actual artifact bytes against a package manifest: recompute each
    artifact's sha256 and compare to the recorded content_digest. Rejects duplicate/unsafe names and
    missing artifacts. Returns {ok, mismatches, missing, unexpected, checked}. Never raises."""
    import hashlib
    try:
        pm = package_manifest if isinstance(package_manifest, Mapping) else {}
        provided = {str(k): v for k, v in dict(artifact_bytes_by_name or {}).items()}
        mismatches: List[str] = []
        missing: List[str] = []
        checked = 0
        expected_names = set()
        for a in (pm.get("artifacts") or []):
            if not isinstance(a, Mapping):
                continue
            name = str(a.get("name") or "")
            expected_names.add(name)
            if not is_safe_relative_name(name):
                mismatches.append(f"unsafe name {name!r}")
                continue
            if name not in provided:
                missing.append(name)
                continue
            data = provided[name]
            if isinstance(data, str):
                data = data.encode("utf-8")
            digest = hashlib.sha256(data).hexdigest()
            checked += 1
            if _lc(digest) != _lc(a.get("content_digest")):
                mismatches.append(name)
        unexpected = [n for n in provided if n not in expected_names]
        ok = not mismatches and not missing
        return {"ok": ok, "mismatches": mismatches, "missing": missing, "unexpected": unexpected,
                "checked": checked}
    except Exception as exc:
        return {"ok": False, "mismatches": [f"error:{type(exc).__name__}"], "missing": [],
                "unexpected": [], "checked": 0}


def loader_versions() -> dict:
    return {"assurance_manifest_loader": ASSURANCE_MANIFEST_LOADER_VERSION}
