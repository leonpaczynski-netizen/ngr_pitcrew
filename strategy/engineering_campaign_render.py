"""Deterministic renderer for the Engineering Campaign programme (Phase 18).

Renders the read-only multi-session development programme as structured sections: the
programme summary, the campaign list (objective / status / progress / next action), and a
selected campaign's detail (engineering question, completion criteria, stages, experiments,
knowledge gained, remaining uncertainty, roadmap). It renders STRINGS only, shows no Apply
control wording, and never implies the setup was applied. Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v or "").replace("_", " ").strip()


def render_programme_sections(programme) -> List[Tuple[str, List[str]]]:
    p = programme if isinstance(programme, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    ctx = p.get("context_summary") or {}
    out.append(("Programme summary", [
        f"Context: {ctx.get('car')} / {ctx.get('track')} / {ctx.get('layout')} / "
        f"{_t(ctx.get('discipline'))}.",
        f"Active: {p.get('active_count')}   Blocked: {p.get('blocked_count')}   "
        f"Ready to freeze: {p.get('ready_to_freeze_count')}   Completed: "
        f"{p.get('completed_count')}   Stale: {p.get('stale_count')}.",
        (f"Recommended focus: {(p.get('recommended_focus') or {}).get('title')} "
         f"({(p.get('recommended_focus') or {}).get('next_action')})"
         if p.get("recommended_focus") else "No campaign can progress now."),
    ] + ([f"Programme blocker: {b}" for b in (p.get("programme_blockers") or [])])))

    for c in p.get("campaigns") or []:
        obj = c.get("objective") or {}
        prog = c.get("progress") or {}
        out.append((f"Campaign: {obj.get('title')}", [
            f"Status: {_t(c.get('status'))}   Progress: {prog.get('progress_pct')}% "
            f"({prog.get('criteria_satisfied')}/{prog.get('criteria_total')} criteria; "
            f"maturity {_t(prog.get('maturity'))}).",
            f"Engineering question: {obj.get('engineering_question')}",
            f"Source diagnoses: {', '.join(obj.get('source_diagnoses') or []) or '-'}.",
            (f"Protects confirmed-good: {', '.join(obj.get('protected_good_behaviours') or [])}."
             if obj.get("protected_good_behaviours") else ""),
            f"Uncertainty: {obj.get('current_uncertainty')}.",
            f"Next action: {c.get('next_action')}",
        ] + ([f"Blocker: {b}" for b in (c.get("blockers") or [])])
            + _campaign_detail(c)))

    out.append(("Programme roadmap (advisory)", [
        f"{s.get('order')}. {s.get('objective')} - {_t(s.get('status'))}: {s.get('next_action')}"
        + (f"  [{'; '.join(s.get('blockers') or [])}]" if s.get("blockers") else "")
        for s in (p.get("programme_roadmap") or [])]))

    out.append(("Safety", [str(p.get("safety_statement") or "")]))
    return out


def _campaign_detail(c: dict) -> List[str]:
    lines = ["  Completion criteria:"]
    for cr in (c.get("objective") or {}).get("completion_criteria") or []:
        mark = "OK" if cr.get("satisfied") else "--"
        lines.append(f"    [{mark}] {cr.get('description')}"
                     + (f" (blocked: {cr.get('blocker_reason')})" if cr.get("blocker_reason")
                        else ""))
    lines.append("  Stages:")
    for s in c.get("stages") or []:
        mark = "OK" if s.get("completion_state") == "complete" else ".."
        lines.append(f"    [{mark}] {_t(s.get('stage_type'))}: {s.get('purpose')} "
                     f"-> {s.get('advisory_next_action')}")
    exps = c.get("experiments") or []
    if exps:
        lines.append("  Experiments (ranking owned by Phase 17):")
        for e in exps:
            tag = _t(e.get("retirement_state") and "retired" or e.get("outcome_state"))
            lines.append(f"    - {_t(e.get('direction'))} {e.get('field')} "
                         f"[{_t(e.get('campaign_role'))}, rank {e.get('phase17_rank')}, "
                         f"value {round(float(e.get('engineering_value') or 0), 3)}] "
                         f"- {tag}; knowledge: {e.get('knowledge_gained')}")
    return lines


def render_programme_text(programme) -> str:
    out: List[str] = []
    for title, lines in render_programme_sections(programme):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
