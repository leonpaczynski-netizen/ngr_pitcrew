"""Deterministic renderer for the Programme Knowledge Readiness Report (Program 2, Phase 28).

Renders the executive-summary readiness view as structured sections. Strings only; zero DB access;
never renders setup values, scheduling instructions, reminders, future dates or automatic next
actions. Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _prog(p) -> str:
    p = p if isinstance(p, dict) else {}
    return f"{p.get('car')} / {_t(p.get('discipline'))} / v{p.get('gt7_version')} / {p.get('driver')}"


def _item_line(i) -> str:
    factors = "; ".join(i.get("limiting_factors") or []) or "-"
    raise_hint = i.get("what_would_raise_readiness") or ""
    return (f"  - {_t(i.get('domain'))}: {_t(i.get('readiness_status'))} (usable as "
            f"{i.get('usable_as')}) - maturity {_t(i.get('current_maturity'))}, confidence "
            f"{_t(i.get('current_confidence'))}, {i.get('coverage_gap_count')} coverage gap(s)"
            + ("  [confirmed-good]" if i.get("confirmed_good") else "") + f". Factors: {factors}."
            + (f" To raise: {raise_hint}." if raise_hint else ""))


def render_readiness_sections(report) -> List[Tuple[str, List[str]]]:
    r = report if isinstance(report, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    src = r.get("source_programme") or {}
    gd = r.get("grade_detail") or {}
    exec_lines = [f"Programme: {_prog(src)}.",
                  r.get("executive_summary") or "",
                  f"Grade rule: {_t(gd.get('rule'))}; assessable {gd.get('assessable')}, relyable "
                  f"{gd.get('relyable')}, blocking {gd.get('blocking')}, unassessable "
                  f"{gd.get('unassessable')}."]
    if r.get("empty_state"):
        exec_lines.append(r.get("empty_state"))
    out.append((f"Executive summary - grade {_t(r.get('programme_grade')).upper()}", exec_lines))

    sections = [
        ("Ready to rely on", "ready"),
        ("Ready within limits", "ready_with_limitations"),
        ("Blocked (conflict / regression / superseded)", "blocked"),
        ("Not yet ready", "not_yet_ready"),
    ]
    for title, key in sections:
        items = r.get(key) or []
        out.append((title, [_item_line(i) for i in items] or ["None."]))

    out.append(("Notes", [_DOCTRINE, str(r.get("safety_statement") or "")]))
    return out


_DOCTRINE = ("'Ready' means the evidence supports relying on this knowledge for a decision - it "
             "never means 'apply this setup'. The grade is rule-based over visible counts, not an "
             "opaque score; a recorded conflict or regression prevents a HIGH grade; unvalidated "
             "knowledge is never marked ready. No action is scheduled or applied; no setup values "
             "are shown.")


def render_readiness_text(report) -> str:
    out: List[str] = []
    for title, lines in render_readiness_sections(report):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
