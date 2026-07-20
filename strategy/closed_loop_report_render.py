"""Deterministic renderer for the Closed-Loop Engineering Report (Program 2, Phase 41).

Renders the run outcome, knowledge-update proposal and next action as concise labelled sections.
Strings only; zero DB access; timestamp-free; never renders setup values or Apply controls. Pure;
deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def render_closed_loop_sections(report) -> List[Tuple[str, List[str]]]:
    r = report if isinstance(report, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    head = [f"Run validity: {_t(r.get('validity')).upper() or '-'}.",
            f"Outcome: {_t(r.get('outcome_state')).upper() or '-'}.",
            f"Promotion eligibility: {_t(r.get('promotion_eligibility')).upper() or '-'}.",
            f"Context fingerprint: {r.get('context_fingerprint') or '-'}.",
            f"Report fingerprint: {r.get('content_fingerprint') or '-'}."]
    if r.get("empty_state"):
        head.append(r.get("empty_state"))
    out.append(("Closed-loop outcome", head))

    prim = r.get("primary_next_action") or {}
    out.append(("Primary next action (exactly one)",
                [f"  -> {_t(prim.get('kind')).upper()}: {prim.get('detail') or '-'}"]))

    sec = r.get("secondary_actions") or []
    out.append(("Secondary actions (non-conflicting)",
                [f"  - {_t(a.get('kind'))}: {a.get('detail')}" for a in sec] or ["  None."]))

    ku = r.get("knowledge_update_proposal") or []
    lines = []
    for k in ku:
        gate = " (only if explicitly recorded)" if k.get("applies_only_if_recorded") else ""
        lines.append(f"  - {_t(k.get('kind'))}: {k.get('detail')}{gate}")
    out.append(("Knowledge-update PROPOSAL (read-only - nothing is written)", lines or ["  None."]))

    out.append(("Advisory", [f"  {r.get('advisory_statement') or ''}"]))
    return out


def render_closed_loop_text(report) -> str:
    out: List[str] = []
    for title, lines in render_closed_loop_sections(report):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
