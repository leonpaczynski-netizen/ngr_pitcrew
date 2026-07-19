"""Pure view-model for the Assurance Review Pack section (Qt-free, Phases 33-35).

Turns the read-only ``SessionDB.build_assurance_review_package_report`` result (a pure package spec,
optionally with a baseline comparison) into a structured card + banner. Display strings only; never
raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _package(result) -> dict:
    r = build(result)
    v = r.get("package")
    return v if isinstance(v, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok") or not _package(result)


def grade_label(result) -> str:
    return str(_package(result).get("assurance_grade") or "").replace("_", " ").upper() or "-"


def header_text(result) -> str:
    r = build(result)
    pkg = _package(result)
    if not pkg:
        return ("No assurance review to preview yet. Read-only, advisory-only - a review package is "
                "generated only on an explicit export action; it is not a certification, not an "
                "experiment, not a setup, and not permission to Apply. No setup values.")
    parts = [f"Assurance grade {grade_label(result)}.",
             f"{len(pkg.get('artifacts') or [])} artifact(s).",
             f"Package fingerprint {pkg.get('package_fingerprint')}."]
    if pkg.get("has_comparison"):
        parts.append("Baseline comparison included.")
    elif r.get("baseline_valid") is False:
        parts.append("Baseline invalid - comparison not shown.")
    parts.append("Advisory only - preview; export writes files only when you choose a destination.")
    return " ".join(parts)


def banner_tone(result) -> str:
    r = build(result)
    if is_empty(result):
        return "info"
    if r.get("baseline_valid") is False:
        return "warn"
    return "info"


def review_cards(result) -> List[dict]:
    from strategy.assurance_review_package_render import render_package_sections
    from strategy.assurance_chain_export_render import render_export_sections
    pkg = _package(result)
    if not pkg:
        return []
    sections = [(t, list(lines)) for t, lines in render_package_sections(pkg)]
    # include the chain-manifest section content preview via the export render, if available.
    chain_art = None
    for a in (pkg.get("artifacts") or []):
        if a.get("kind") == "assurance_chain_manifest":
            chain_art = a
            break
    return [{
        "title": "Assurance Review Pack (preview)",
        "status": f"grade {grade_label(result)}"
                  + (" + baseline" if pkg.get("has_comparison") else ""),
        "sections": sections,
        "fingerprint": str(pkg.get("package_fingerprint") or ""),
    }]


def export_status_text(write_result) -> str:
    """Format a write-result (from the writer adapter) for the OUT-OF-REPORT status line."""
    w = write_result if isinstance(write_result, dict) else {}
    if not w:
        return ""
    if w.get("ok"):
        n = len(w.get("files_written") or [])
        arch = f", archive {w.get('archive_path')}" if w.get("archive_path") else ""
        return f"Exported {n} file(s) to: {w.get('destination')}{arch}"
    errs = "; ".join(w.get("errors") or []) or "unknown error"
    return f"Export failed: {errs}"
