"""Deterministic renderer for the Assurance-Driven Engineering Priority report (Phase 32).

Renders the evidence-priority plan as concise structured sections. Strings only; zero DB access;
never renders setup values, scheduling instructions, dates, sessions, resources or Apply controls.
Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _prog(p) -> str:
    p = p if isinstance(p, dict) else {}
    return f"{p.get('car')} / {_t(p.get('discipline'))} / v{p.get('gt7_version')} / {p.get('driver')}"


def _score_breakdown(c) -> str:
    parts = []
    for d in (c.get("dimensions") or []):
        if abs(float(d.get("contribution") or 0)) < 1e-9:
            continue
        parts.append(f"{_t(d.get('name'))} {d.get('raw')}x{d.get('weight')}="
                     f"{d.get('contribution')}")
    return "; ".join(parts) or "-"


def _cand_lines(c) -> List[str]:
    doms = ", ".join(_t(d) for d in (c.get("domains") or [])) or "programme"
    deps = c.get("dependencies") or []
    dep_txt = ("; ".join(d.get("reason", "") for d in deps)) if deps else "none"
    lines = [
        f"  - [{_t(c.get('priority_band'))}] {_t(c.get('investigation_type'))} ({doms}) "
        f"- score {c.get('priority_score')}, addresses {len(c.get('linked_finding_ids') or [])} "
        f"finding(s) (max {_t(c.get('max_severity'))}).",
        f"      Evidence to collect: {c.get('evidence_requested')}.",
        f"      Why: {c.get('why_needed')}.",
    ]
    if c.get("discriminating_requirement"):
        lines.append(f"      Discriminating/independence requirement: "
                     f"{c.get('discriminating_requirement')}.")
    lines.append(f"      Current evidence: {c.get('current_evidence_state')}.")
    lines.append(f"      Expected effect: {c.get('expected_assurance_impact')} "
                 f"{c.get('impact_limitations')}")
    lines.append(f"      Dependencies: {dep_txt}.")
    lines.append(f"      Score breakdown: {_score_breakdown(c)}.")
    return lines


def render_priority_sections(report) -> List[Tuple[str, List[str]]]:
    r = report if isinstance(report, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    src = r.get("source_programme") or {}
    header = [f"Programme: {_prog(src)}.",
              f"Assurance grade: {_t(r.get('assurance_grade')).upper()}.",
              r.get("assurance_summary") or ""]
    out.append((f"Assurance priority - grade {_t(r.get('assurance_grade')).upper()}", header))

    out.append(("Why the programme is not more assured",
                [f"  - {r.get('total_findings')} assurance finding(s): "
                 f"{r.get('blocking_finding_count')} blocking, {r.get('major_finding_count')} major. "
                 "A single blocking finding prevents ASSURED (Phase 31)."]))

    prioritised = r.get("prioritised_candidates") or []
    lines: List[str] = []
    for c in prioritised:
        lines.extend(_cand_lines(c))
    out.append(("Highest-priority evidence to collect", lines or ["None."]))

    deferred = r.get("deferred_candidates") or []
    dlines: List[str] = []
    for c in deferred:
        dlines.extend(_cand_lines(c))
    out.append(("Deferred (blocked by a prerequisite or not currently collectable)",
                dlines or ["None."]))

    prereqs = r.get("unresolved_prerequisites") or []
    out.append(("Unresolved prerequisites",
                [f"  - {p.get('reason')}" for p in prereqs] or ["None."]))

    if r.get("no_action_statement"):
        out.append(("No action", [f"  {r.get('no_action_statement')}"]))

    out.append(("Notes", [_DOCTRINE, str(r.get("safety_statement") or "")]))
    return out


_DOCTRINE = ("This is the highest-priority EVIDENCE to collect, not an approved experiment, not a "
             "setup recommendation and not permission to Apply. Independent evidence outranks "
             "dependent repetition; contradictions need discriminating evidence; assumptions stay "
             "assumptions until established; missing evidence is untested, not disproven; "
             "confirmed-good knowledge is protected. Expected impact is potential, never guaranteed. "
             "No dates, sessions or resources are assigned; no setup values are shown.")


def render_priority_text(report) -> str:
    out: List[str] = []
    for title, lines in render_priority_sections(report):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
