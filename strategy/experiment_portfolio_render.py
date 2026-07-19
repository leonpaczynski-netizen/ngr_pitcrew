"""Deterministic renderer for the engineering experiment portfolio (Phase 17).

Renders the read-only engineering PLAN: the highest-value next experiment and why, the
individually-visible value dimensions (no black box), alternatives, deferred / blocked /
obsolete / redundant experiments, the dependency graph and the advisory roadmap. It renders
STRINGS only, shows no Apply control wording, and states that it optimises engineering
learning, not lap time. Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v or "").replace("_", " ").strip()


def _pct(v) -> str:
    try:
        return f"{round(float(v) * 100)}%"
    except (TypeError, ValueError):
        return "-"


def render_portfolio_sections(portfolio) -> List[Tuple[str, List[str]]]:
    p = portfolio if isinstance(portfolio, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    out.append(("Engineering plan", [
        "Experiments ranked by ENGINEERING VALUE (information gain first) - not lap time.",
        f"Session suitability: {_t(p.get('session_suitability'))}.",
    ]))

    hv = p.get("highest_value")
    if hv:
        lines = [
            f"Next experiment: {_t(hv.get('direction'))} {hv.get('field')} - "
            f"engineering value {_pct(hv.get('engineering_value'))}.",
            f"Diagnosis: {_t(hv.get('issue_type'))}; mechanism: {hv.get('mechanism_id') or '-'}.",
            f"Expected learning: {hv.get('expected_learning')}",
            f"Attribution: {_t(hv.get('attribution_scope'))}.",
        ]
        if hv.get("protected_good_at_risk"):
            lines.append(f"Protects (confirmed-good): {', '.join(hv['protected_good_at_risk'])}.")
        out.append(("Highest-value next experiment", lines))
        # visible dimensions — no hidden weighted black box
        out.append(("Why (engineering value dimensions)", [
            f"{_t(d.get('name'))}: {_pct(d.get('score'))} x weight {d.get('weight')} "
            f"= {round(float(d.get('weighted') or 0), 3)}  ({d.get('rationale')})"
            for d in (hv.get("dimensions") or [])]))
    else:
        out.append(("Highest-value next experiment", [
            "No single highest-value experiment (a genuine tie or none) - see alternatives; "
            "manual choice required."]))

    for bucket, title in (("alternatives", "Alternative experiments"),
                          ("deferred", "Deferred (need conditions / coupling first)"),
                          ("blocked", "Blocked experiments"),
                          ("redundant", "Redundant (superseded)"),
                          ("obsolete", "Obsolete (retired - no remaining value)")):
        rows = p.get(bucket) or []
        if not rows:
            continue
        lines = []
        for v in rows:
            tag = _pct(v.get("engineering_value"))
            line = f"{_t(v.get('direction'))} {v.get('field')} ({_t(v.get('issue_type'))}) - value {tag}"
            if v.get("retirement_reason"):
                line += f" - {v['retirement_reason']}"
            if v.get("depends_on"):
                line += " - depends on a discriminating test first"
            lines.append(line)
        out.append((title, lines))

    deps = p.get("dependencies") or []
    if deps:
        out.append(("Dependencies", [
            f"{_t(d.get('kind'))}: {d.get('from_id', '')[:18]} -> {d.get('to_id', '')[:18]} "
            f"({d.get('reason')})" for d in deps]))

    road = p.get("roadmap") or []
    if road:
        out.append(("Engineering roadmap (advisory)", [
            f"{s.get('order')}. {_t(s.get('kind'))}: {s.get('detail')}" for s in road]))

    out.append(("Safety", [str(p.get("safety_statement") or "")]))
    return out


def render_portfolio_text(portfolio) -> str:
    out: List[str] = []
    for title, lines in render_portfolio_sections(portfolio):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
