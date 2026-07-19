"""Assurance Review Package Writer — the ONLY file-writing adapter for Phase 35.

Materialises an already-built pure ``AssuranceReviewPackage`` specification to an EXPLICIT
caller-supplied destination directory, on an explicit user export action only. It creates no implicit
default export, writes into a temporary staging location, verifies every written byte against the
spec's content digests, completes atomically where practical, and cleans incomplete output on
failure.

It touches NO database, modifies NO source/runtime file, includes NO database file, NO setup history,
NO settings, NO API keys, NO track-model runtime files and NO absolute source paths (it writes only
the package's own safe-named artifacts + the package manifest). The destination path never enters the
semantic package fingerprint.

This adapter performs file I/O; it performs no database access and imports no Qt.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from typing import List, Optional, Tuple

from strategy.assurance_review_package import (
    AssuranceReviewPackage, PACKAGE_MANIFEST_NAME, package_manifest_bytes, safe_artifact_names,
)
from strategy.assurance_chain_serialization import is_safe_relative_name

ASSURANCE_REVIEW_PACKAGE_WRITER_VERSION = "assurance_review_package_writer_v1"

# a fixed, timestamp-free zip entry date (1980-01-01) so archives are byte-deterministic.
_ZIP_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class ReviewPackageWriteResult:
    ok: bool
    destination: str
    files_written: Tuple[dict, ...]
    package_fingerprint: str
    archive_path: str
    archive_sha256: str
    validation: dict
    warnings: Tuple[str, ...]
    errors: Tuple[str, ...]
    eval_version: str = ASSURANCE_REVIEW_PACKAGE_WRITER_VERSION

    def to_dict(self) -> dict:
        return {"ok": self.ok, "destination": self.destination,
                "files_written": [dict(f) for f in self.files_written],
                "package_fingerprint": self.package_fingerprint, "archive_path": self.archive_path,
                "archive_sha256": self.archive_sha256, "validation": dict(self.validation),
                "warnings": list(self.warnings), "errors": list(self.errors),
                "eval_version": self.eval_version}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fail(destination: str, package_fp: str, errors: List[str],
          warnings: Optional[List[str]] = None) -> ReviewPackageWriteResult:
    return ReviewPackageWriteResult(ok=False, destination=destination, files_written=(),
                                    package_fingerprint=package_fp, archive_path="",
                                    archive_sha256="", validation={"status": "not_written"},
                                    warnings=tuple(warnings or ()), errors=tuple(errors))


def _member_bytes(pkg: AssuranceReviewPackage) -> List[Tuple[str, bytes, str]]:
    """Return [(name, bytes, expected_digest)] for every artifact + the package manifest."""
    out: List[Tuple[str, bytes, str]] = []
    for a in pkg.artifacts:
        data = pkg.artifact_bytes(a.kind)
        out.append((a.name, data, a.content_digest))
    pm = package_manifest_bytes(pkg)
    out.append((PACKAGE_MANIFEST_NAME, pm, _sha256(pm)))
    return out


def write_review_package(pkg: AssuranceReviewPackage, destination_dir: str, *,
                         allow_overwrite: bool = False, make_archive: bool = False,
                         archive_name: str = "assurance_review_package.zip"
                         ) -> ReviewPackageWriteResult:
    """Write the review package to an EXPLICIT destination directory. Never raises.

    Requires a non-empty destination (no implicit default). Refuses to overwrite existing files
    unless ``allow_overwrite`` is True. Stages all files in a temp directory, verifies every byte,
    then moves them into place. On any failure nothing is left partially written where practical, and
    the temp staging is always cleaned.
    """
    package_fp = getattr(pkg, "package_fingerprint", "") or ""
    try:
        dest = str(destination_dir or "").strip()
        if not dest:
            return _fail(dest, package_fp, ["no destination supplied - an explicit export "
                                            "destination is required (no implicit default)"])
        if not pkg.artifacts:
            return _fail(dest, package_fp, ["package is empty - nothing to write"])
        if not safe_artifact_names(pkg):
            return _fail(dest, package_fp, ["unsafe or duplicate artifact names - refusing to write"])

        members = _member_bytes(pkg)
        # never write a file whose bytes fail their own digest (defensive integrity gate).
        for name, data, expected in members:
            if not is_safe_relative_name(name):
                return _fail(dest, package_fp, [f"unsafe artifact name refused: {name!r}"])
            if name != PACKAGE_MANIFEST_NAME and _sha256(data) != expected:
                return _fail(dest, package_fp, [f"artifact {name!r} failed its own content digest - "
                                                "refusing to write"])

        # overwrite guard (check before writing anything).
        existing = [name for name, _d, _e in members if os.path.exists(os.path.join(dest, name))]
        if existing and not allow_overwrite:
            return _fail(dest, package_fp, [f"destination already contains: {', '.join(existing)} - "
                                            "pass allow_overwrite to replace"])

        # stage in a temp directory, verify, then move atomically per file.
        staging = tempfile.mkdtemp(prefix="ngr_assurance_pkg_")
        files_written: List[dict] = []
        try:
            staged_paths: List[Tuple[str, str]] = []
            for name, data, _expected in members:
                sp = os.path.join(staging, name)
                with open(sp, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                # verify the bytes actually on disk.
                with open(sp, "rb") as fh:
                    if _sha256(fh.read()) != _sha256(data):
                        raise IOError(f"staged file {name!r} did not verify")
                staged_paths.append((name, sp))

            os.makedirs(dest, exist_ok=True)
            for name, sp in staged_paths:
                final = os.path.join(dest, name)
                shutil.move(sp, final)
                with open(final, "rb") as fh:
                    digest = _sha256(fh.read())
                files_written.append({"name": name, "sha256": digest,
                                      "bytes": os.path.getsize(final)})

            archive_path = ""
            archive_sha = ""
            if make_archive:
                if not is_safe_relative_name(archive_name):
                    return _fail(dest, package_fp, [f"unsafe archive name refused: {archive_name!r}"],
                                 warnings=[f"wrote {len(files_written)} files before archive step"])
                archive_path = os.path.join(dest, archive_name)
                archive_sha = _write_deterministic_zip(archive_path, members)

            validation = {"status": "written", "files": len(files_written),
                          "all_digests_verified": True}
            return ReviewPackageWriteResult(
                ok=True, destination=dest, files_written=tuple(files_written),
                package_fingerprint=package_fp, archive_path=archive_path,
                archive_sha256=archive_sha, validation=validation, warnings=(), errors=())
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    except Exception as exc:  # never raise
        return _fail(str(destination_dir or ""), package_fp,
                     [f"write failed: {type(exc).__name__}: {exc}"])


def _write_deterministic_zip(path: str, members: List[Tuple[str, bytes, str]]) -> str:
    """Write a byte-deterministic zip: sorted members, fixed 1980-01-01 entry dates, stored (no
    compression, so no zlib-version variance), no extra metadata. Returns the archive sha256."""
    ordered = sorted(members, key=lambda m: m[0])
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, data, _expected in ordered:
            info = zipfile.ZipInfo(filename=name, date_time=_ZIP_FIXED_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (0o644 & 0xFFFF) << 16
            info.create_system = 0  # fixed (0 = MS-DOS/FAT) for cross-platform determinism
            zf.writestr(info, data)
    with open(path, "rb") as fh:
        return _sha256(fh.read())


def writer_versions() -> dict:
    return {"assurance_review_package_writer": ASSURANCE_REVIEW_PACKAGE_WRITER_VERSION}
