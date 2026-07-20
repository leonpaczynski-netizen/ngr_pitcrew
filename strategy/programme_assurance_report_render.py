"""Deterministic renderer for the Programme Assurance & Audit Report (Program 2, Phase 31).

Renders the assurance audit as structured sections. Strings only; zero DB access; never renders
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


def _f_line(f) -> str:
    dom = f.get("domain") or "programme"
    return (f"  - [{_t(f.get('severity'))}] {_t(f.get('finding_type'))} ({dom}) - "
            f"{f.get('detail') or ''} [from {f.get('source_phase')}]")


def render_assurance_sections(report) -> List[Tuple[str, List[str]]]:
    r = report if isinstance(report, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    src = r.get("source_programme") or {}
    gd = r.get("grade_detail") or {}
    exec_lines = [f"Programme: {_prog(src)}.",
                  r.get("audit_summary") or "",
                  f"Grade rule: {_t(gd.get('rule'))}; severity counts "
                  f"{gd.get('counts') or {}}."]
    if r.get("empty_state"):
        exec_lines.append(r.get("empty_state"))
    out.append((f"Assurance verdict - grade {_t(r.get('assurance_grade')).upper()}", exec_lines))

    sections = [
        ("Blocking findings (prevent ASSURED)", "blocking"),
        ("Major findings", "major"),
        ("Moderate / minor findings", "moderate_minor"),
        ("Informational", "informational"),
    ]
    for title, key in sections:
        items = r.get(key) or []
        out.append((title, [_f_line(f) for f in items] or ["None."]))

    out.append(("Notes", [_DOCTRINE, str(r.get("safety_statement") or "")]))
    return out


_DOCTRINE = ("A single blocking finding prevents ASSURED; the grade is rule-based over visible "
             "severity counts, not an opaque score. Hidden assumptions, unresolved conflicts, "
             "regressions, missing transfer boundaries, non-determinism and data mutation are "
             "defects. No action is scheduled or applied; no setup values are shown.")


def render_assurance_text(report) -> str:
    out: List[str] = []
    for title, lines in render_assurance_sections(report):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
