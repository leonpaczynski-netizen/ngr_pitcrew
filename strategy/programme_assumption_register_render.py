"""Deterministic renderer for the Programme Assumption Register (Program 2, Phase 30).

Renders the assumption register as structured sections. Strings only; zero DB access; never renders
setup values, scheduling instructions, reminders, future dates or automatic next actions. Pure;
deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _prog(p) -> str:
    p = p if isinstance(p, dict) else {}
    return f"{p.get('car')} / {_t(p.get('discipline'))} / v{p.get('gt7_version')} / {p.get('driver')}"


def _a_line(a) -> str:
    cb = "  [conservative bound]" if a.get("is_conservative_bound") else ""
    return (f"  - {_t(a.get('domain'))}: {_t(a.get('assumption_type'))} - {_t(a.get('status'))}, "
            f"impact {_t(a.get('impact'))} (caps readiness at {_t(a.get('readiness_cap'))}){cb}. "
            f"{a.get('rationale') or ''} To resolve: {a.get('what_would_resolve') or '-'}.")


def render_assumption_sections(report) -> List[Tuple[str, List[str]]]:
    r = report if isinstance(report, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    src = r.get("source_programme") or {}
    tot = r.get("totals") or {}
    header = [f"Programme: {_prog(src)}.",
              f"Assumptions: {tot.get('assumptions')} across {tot.get('domains_with_assumptions')} "
              f"domain(s) - blocking {tot.get('blocking')}, capping {tot.get('capping')}, "
              f"narrowing/weakening {tot.get('narrowing_or_weakening')}, informational "
              f"{tot.get('informational')}; at-risk/contradicted "
              f"{tot.get('at_risk_or_contradicted')}; conservative bounds "
              f"{tot.get('conservative_bounds')}.",
              str(r.get("readiness_cap_note") or "")]
    if r.get("empty_state"):
        header.append(r.get("empty_state"))
    out.append(("Assumption summary", header))

    sections = [
        ("Blocking assumptions (conclusion unusable if wrong)", "blocking"),
        ("Readiness-capping assumptions", "capping"),
        ("Scope-narrowing / confidence-weakening assumptions", "narrowing_or_weakening"),
        ("Informational assumptions", "informational"),
        ("Conservative bounds (deliberate cautions, labelled)", "conservative_bounds"),
    ]
    for title, key in sections:
        items = r.get(key) or []
        out.append((title, [_a_line(a) for a in items] or ["None."]))

    out.append(("Notes", [_DOCTRINE, str(r.get("safety_statement") or "")]))
    return out


_DOCTRINE = ("Facts are not listed here - only what the knowledge relies on but has not established. "
             "An assumption can only CAP how ready knowledge may be, never create readiness; a "
             "conservative bound is a deliberate caution, labelled as such, not a defect. No action "
             "is scheduled or applied; no setup values are shown.")


def render_assumption_text(report) -> str:
    out: List[str] = []
    for title, lines in render_assumption_sections(report):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
