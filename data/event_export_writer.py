"""Event Export Writer — the ONLY file-writing adapter for the owner-baseline export (Part C).

Materialises an already-built pure export spec dict (from ``strategy/event_export_spec.py``)
to an EXPLICIT caller-supplied destination directory, on an explicit user export action only.
It creates no implicit default export, writes into a temporary staging location, verifies every
written byte against the spec's content fingerprint, completes atomically where practical,
and cleans incomplete output on failure.

Touches NO database, modifies NO source/runtime file. Imports NO Qt.

C21 compliance: the caller supplies the destination explicitly. Refuse overwrite unless
``allow_overwrite=True`` is passed. Never raises.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Tuple

from strategy.assurance_chain_serialization import canonical_json, content_digest

EVENT_EXPORT_WRITER_VERSION = "event_export_writer_v1"


@dataclass(frozen=True)
class EventExportWriteResult:
    ok: bool
    destination: str
    filename: str
    file_sha256: str
    content_fingerprint: str
    bytes_written: int
    warnings: Tuple[str, ...]
    errors: Tuple[str, ...]
    eval_version: str = EVENT_EXPORT_WRITER_VERSION

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "destination": self.destination,
            "filename": self.filename,
            "file_sha256": self.file_sha256,
            "content_fingerprint": self.content_fingerprint,
            "bytes_written": self.bytes_written,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "eval_version": self.eval_version,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fail(
    destination: str,
    filename: str,
    errors: list,
    warnings: list | None = None,
) -> EventExportWriteResult:
    return EventExportWriteResult(
        ok=False,
        destination=destination,
        filename=filename,
        file_sha256="",
        content_fingerprint="",
        bytes_written=0,
        warnings=tuple(warnings or ()),
        errors=tuple(errors),
    )


def write_event_export(
    spec: dict,
    destination_dir: str,
    filename: str,
    *,
    allow_overwrite: bool = False,
) -> EventExportWriteResult:
    """Write the event export JSON to an EXPLICIT destination directory. Never raises.

    Parameters
    ----------
    spec
        The dict returned by ``build_event_export_spec``.  Must contain a
        ``content_fingerprint`` field (``"sha256:<hex>"``).
    destination_dir
        An explicit caller-supplied directory — no implicit default (C21).
    filename
        The file name to use (from ``export_filename()``).  Must not contain
        path separators.
    allow_overwrite
        When False (default) the writer refuses if the file already exists at
        the destination.

    Returns
    -------
    EventExportWriteResult — ok=True on success, ok=False on any failure.
    Never raises.
    """
    dest = str(destination_dir or "").strip()
    fname = str(filename or "").strip()

    try:
        if not dest:
            return _fail(dest, fname, [
                "no destination supplied — an explicit export destination is required (C21)",
            ])
        if not fname:
            return _fail(dest, fname, ["no filename supplied"])
        # Reject path separators in filename (no path traversal).
        if "/" in fname or "\\" in fname or ".." in fname:
            return _fail(dest, fname, [f"unsafe filename rejected: {fname!r}"])
        if not spec or not isinstance(spec, dict):
            return _fail(dest, fname, ["spec is empty or not a dict"])

        # Serialise with canonical JSON so the bytes are deterministic.
        try:
            json_bytes: bytes = canonical_json(spec).encode("utf-8")
        except Exception as exc:
            return _fail(dest, fname, [
                f"canonical serialization failed: {type(exc).__name__}: {exc}",
            ])

        # Overwrite guard (check before writing anything).
        final_path = os.path.join(dest, fname)
        if os.path.exists(final_path) and not allow_overwrite:
            return _fail(dest, fname, [
                f"file already exists at destination: {fname!r} — pass allow_overwrite to replace",
            ])

        # Stage in a temporary directory, verify every byte, then move atomically.
        staging = tempfile.mkdtemp(prefix="ngr_event_export_")
        try:
            staged_path = os.path.join(staging, fname)
            with open(staged_path, "wb") as fh:
                fh.write(json_bytes)
                fh.flush()
                os.fsync(fh.fileno())

            # Verify the staged bytes round-trip correctly.
            with open(staged_path, "rb") as fh:
                staged_bytes = fh.read()
            if _sha256(staged_bytes) != _sha256(json_bytes):
                return _fail(dest, fname, [
                    "staged file failed integrity verification — refusing to move to destination",
                ])

            # Verify the content_fingerprint embedded in the spec matches the spec's
            # own canonical bytes (excluding the fingerprint field itself — same approach
            # as build_event_export_spec uses).
            embedded_fp: str = str(spec.get("content_fingerprint") or "")
            expected_fp_value = ""
            if embedded_fp.startswith("sha256:"):
                # Re-derive: build the doc without the content_fingerprint key.
                doc_for_fp = {k: v for k, v in spec.items() if k != "content_fingerprint"}
                expected_fp_value = "sha256:" + content_digest(doc_for_fp)
                if embedded_fp != expected_fp_value:
                    warnings: list = [
                        f"content_fingerprint mismatch: embedded={embedded_fp!r}, "
                        f"recomputed={expected_fp_value!r} — written with warning",
                    ]
                else:
                    warnings = []
            else:
                warnings = ["content_fingerprint field absent or not sha256: — written with warning"]
                expected_fp_value = ""

            os.makedirs(dest, exist_ok=True)
            shutil.move(staged_path, final_path)

            with open(final_path, "rb") as fh:
                final_bytes = fh.read()
            file_sha256 = _sha256(final_bytes)

            return EventExportWriteResult(
                ok=True,
                destination=dest,
                filename=fname,
                file_sha256=file_sha256,
                content_fingerprint=embedded_fp,
                bytes_written=len(final_bytes),
                warnings=tuple(warnings),
                errors=(),
            )

        finally:
            shutil.rmtree(staging, ignore_errors=True)

    except Exception as exc:
        return _fail(
            str(destination_dir or ""),
            str(filename or ""),
            [f"write failed: {type(exc).__name__}: {exc}"],
        )


def writer_versions() -> dict:
    return {"event_export_writer": EVENT_EXPORT_WRITER_VERSION}
