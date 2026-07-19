"""Deterministic renderer for the Programme Evidence Coverage Report (Program 2, Phase 27).

Renders the coverage & blind-spot view as structured sections. Strings only; zero DB access; never
renders setup values, scheduling instructions, reminders, future dates or automatic next actions.
Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _prog(p) -> str:
    p = p if isinstance(p, dict) else {}
    return f"{p.get('car')} / {_t(p.get('discipline'))} / v{p.get('gt7_version')} / {p.get('driver')}"


def _blind_line(b) -> str:
    gaps = ", ".join(f"{_t(g.get('dimension'))} [{_t(g.get('status'))}]"
                     for g in (b.get("gap_dimensions") or [])[:6]) or "-"
    rec = b.get("recommended_evidence") or ""
    return (f"  - {_t(b.get('domain'))}: {_t(b.get('severity'))} blind spot - reliance "
            f"{_t(b.get('reliance'))}, evidence {_t(b.get('evidence_robustness'))}. "
            f"Gaps: {gaps}. {b.get('rationale') or ''} {('To strengthen: ' + rec) if rec else ''}")


def _coverage_line(cov) -> str:
    dims = cov.get("dimensions") or []
    covered = cov.get("covered_count")
    gaps = cov.get("gap_count")
    return (f"  - {_t(cov.get('domain'))}: {covered}/{len(dims)} dimension(s) covered, {gaps} gap(s); "
            f"maturity {_t(cov.get('current_maturity'))}, confidence "
            f"{_t(cov.get('current_confidence'))}"
            + ("  [confirmed-good]" if cov.get("confirmed_good") else "") + ".")


def render_coverage_sections(report) -> List[Tuple[str, List[str]]]:
    r = report if isinstance(report, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    src = r.get("source_programme") or {}
    tot = r.get("totals") or {}
    header = [f"Programme: {_prog(src)}.",
              f"Domains assessed: {tot.get('domains_assessed')}. Blind spots raised "
              f"{tot.get('blind_spots_raised')} (critical {tot.get('critical')}, material "
              f"{tot.get('material')}, moderate {tot.get('moderate')}); early-stage gaps "
              f"{tot.get('early_stage_gaps')}; well-covered {tot.get('well_covered')}; "
              f"unassessable {tot.get('unassessable')}."]
    if r.get("empty_state"):
        header.append(r.get("empty_state"))
    out.append(("Coverage summary", header))

    out.append(("Blind spots (more evidence would strengthen these)",
                [_blind_line(b) for b in (r.get("blind_spots") or [])] or ["None raised."]))
    out.append(("Early-stage gaps (expected; not a concern)",
                [_blind_line(b) for b in (r.get("early_stage_gaps") or [])] or ["None."]))
    out.append(("Well-covered domains",
                ["  - " + _t(d) for d in (r.get("well_covered_domains") or [])] or ["None yet."]))
    out.append(("Per-domain coverage",
                [_coverage_line(c) for c in (r.get("domain_coverage") or [])] or ["None."]))
    if r.get("unassessable"):
        out.append(("Unassessable (unknown reliance)",
                    [_blind_line(b) for b in r.get("unassessable")]))

    out.append(("Notes", [_DOCTRINE, str(r.get("safety_statement") or "")]))
    return out


_DOCTRINE = ("A blind spot marks where more evidence would strengthen confidence - it is NOT a "
             "fault or a negative result. Missing coverage means untested, never wrong; a large "
             "dependent-evidence count is not strong coverage; one track / car / driver / compound / "
             "format is a single context, not multi-context coverage. No action is scheduled or "
             "applied; no setup values are shown.")


def render_coverage_text(report) -> str:
    out: List[str] = []
    for title, lines in render_coverage_sections(report):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
