"""Pure view-model for the Mechanism-Annotated Diagnosis panel (Qt-free, Phase 13).

Turns the read-only ``SessionDB.build_mechanism_annotations`` report into the structured
cards + sections the panel renders. It shapes DISPLAY STRINGS only — it recommends
nothing, invents no setup value, and reads the deterministic annotation exactly as built.

Deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok") or not (r.get("annotations") or [])


def header_text(result) -> str:
    r = build(result)
    n = int(r.get("count") or 0)
    sup = int(r.get("supported_count") or 0)
    if not n:
        return ("No canonical diagnoses to explain yet for this car / track / discipline. "
                "Mechanism explanations appear once a recurring issue is recorded.")
    return (f"{n} canonical diagnosis(es) annotated with vehicle-dynamics mechanisms — "
            f"{sup} with a supported primary mechanism. Read-only: this explains the "
            f"physics and changes no setup value.")


def _status_label(v: str) -> str:
    return str(v or "").replace("_", " ").title()


def annotation_cards(result) -> List[dict]:
    """Return one card per annotation, each with a title, a status chip and ordered
    (section_title, lines) pairs. Uses the deterministic renderer for the section body."""
    from strategy.mechanism_annotation_render import render_sections
    r = build(result)
    cards: List[dict] = []
    for a in r.get("annotations") or []:
        issue = a.get("canonical_issue") or {}
        itype = str(issue.get("issue_type") or "issue").replace("_", " ")
        corners = ", ".join(a.get("corners") or []) or "—"
        title = f"{itype.capitalize()} @ {corners}"
        cards.append({
            "title": title,
            "status": _status_label(a.get("overall_status")),
            "status_key": str(a.get("overall_status") or ""),
            "sections": [(t, list(lines)) for t, lines in render_sections(a)],
            "fingerprint": str(a.get("content_fingerprint") or ""),
        })
    return cards


# banner tone per overall status (for theming; purely presentational)
def banner_tone(result) -> str:
    r = build(result)
    if is_empty(r):
        return "info"
    statuses = {str(a.get("overall_status")) for a in r.get("annotations") or []}
    if statuses & {"supported"}:
        return "success"
    if statuses & {"supported_with_limitations", "competing", "plausible"}:
        return "info"
    if statuses & {"contradicted", "invalid_source_diagnosis"}:
        return "warn"
    return "info"
