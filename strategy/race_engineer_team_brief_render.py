"""Deterministic renderer for the Integrated Race-Engineer Team Brief (Program 2, Phase 38).

Renders the coordinated crew brief as concise, role-labelled sections. Strings only; zero DB access;
timestamp-free (recorded evidence dates are data, shown as-is); never renders setup values, machine
paths or Apply controls. Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _lines(items, empty="None.") -> List[str]:
    out = [f"  - {x}" for x in (items or []) if str(x).strip()]
    return out or [f"  {empty}"]


def render_brief_sections(brief) -> List[Tuple[str, List[str]]]:
    b = brief if isinstance(brief, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    scope = b.get("scope") or {}
    head = [f"Context: {scope.get('label') or 'unknown'} (completeness {_t(b.get('completeness')).upper()}).",
            f"Context fingerprint: {b.get('context_fingerprint') or '-'}.",
            f"Brief fingerprint: {b.get('content_fingerprint') or '-'}."]
    if b.get("empty_state"):
        head.append(b.get("empty_state"))
    out.append(("Integrated race-engineer brief", head))

    ce = b.get("chief_engineer") or {}
    out.append(("Chief Engineer", [
        f"  Objective: {ce.get('objective') or '-'}",
        f"  Context readiness: {_t(ce.get('context_readiness')).upper()}",
        f"  Highest-priority problem: {ce.get('highest_priority_problem') or '-'}",
    ] + ["  Conflict: " + str(c) for c in (ce.get("conflicts") or [])]
        + ["  Next actions:"] + [f"    {a}" for a in (ce.get("ordered_actions") or ["(none)"])]
        + ["  Stop/defer: " + str(s) for s in (ce.get("stop_defer_conditions") or [])]))

    se = b.get("setup_engineer") or {}
    ww = se.get("working_windows") or []
    out.append(("Setup Engineer", [
        f"  Current best-known (proven, not ultimate): {se.get('current_best_known_setup') or '-'}",
        "  Protect: " + (", ".join(se.get("confirmed_good_to_protect") or []) or "-"),
        "  Working windows:"]
        + [f"    - {w.get('field')}: {_t(w.get('status'))} [{w.get('window')}] conf {w.get('confidence') or '-'}"
           for w in ww] or ["    (none)"]))
    se_lines = out[-1][1]
    se_lines.append(f"  Latest outcome: {_t((se.get('latest_outcome') or {}).get('verdict')) or '-'}")
    se_lines.append(f"  Next experiment: {se.get('next_experiment') or '-'}")
    rb = se.get("rollback_plan") or {}
    se_lines.append("  Rollback: " + ("needed -> " + str(rb.get("target"))
                                      if rb.get("needed") else "not required"))
    se_lines.append(f"  Success: {se.get('success_criteria') or '-'}")
    se_lines.append(f"  Failure: {se.get('failure_criteria') or '-'}")

    pe = b.get("performance_engineer") or {}
    out.append(("Performance / Data Engineer", [
        "  Repeatable findings: " + (", ".join(
            f"{r.get('dimension')}({r.get('trend')})" for r in (pe.get("repeatable_findings") or []))
            or "-"),
        "  Corner losses: " + (", ".join(pe.get("corner_losses") or []) or "-"),
        "  Corner strengths: " + (", ".join(pe.get("corner_strengths") or []) or "-"),
        "  Gear / drive-out: " + (", ".join(
            str(g.get("corner") or "-") for g in (pe.get("gear_drive_out_findings") or [])) or "-"),
    ] + ["  Missing evidence: " + m for m in (pe.get("missing_evidence") or ["-"])]
        + ["  Collect: " + c for c in (pe.get("recommended_collection") or [])]))

    dc = b.get("driver_coach") or {}
    coach_lines: List[str] = []
    for p in (dc.get("priorities") or []):
        coach_lines.append(f"  - {_t(p.get('dimension'))}"
                           + (f" @ {p.get('corner')}" if p.get("corner") else "") + ": "
                           + str(p.get("technique_focus") or "-"))
        coach_lines.append(f"      success: {p.get('success_criterion') or '-'}")
        coach_lines.append(f"      verify: {p.get('verification') or '-'}; falsify: {p.get('falsifier') or '-'}"
                           + ("; hold setup constant" if p.get("hold_setup_constant") else ""))
    out.append(("Driver Coach", coach_lines or ["  No driver-attributable coaching priority yet."]))

    st = b.get("strategy_engineer") or {}
    out.append(("Strategy Engineer",
                ["  Implication: " + str(i) for i in (st.get("race_plan_implications") or [])]
                + [f"  Experiment risk: {st.get('experiment_risk_to_race_prep') or '-'}"]
                + ["  Evidence required: " + e for e in (st.get("evidence_required") or ["-"])]))

    contradictions = b.get("contradictions") or []
    out.append(("Resolved contradictions",
                [f"  - {_t(c.get('kind'))}: {c.get('resolution')}" for c in contradictions]
                or ["  None - no opposing advice."]))

    plan = b.get("ordered_development_plan") or []
    out.append(("One coherent development plan (ordered)",
                [f"  {a.get('step')}. {a.get('action')}"
                 + (f"  [hold {a.get('hold_constant')} constant]" if a.get("hold_constant") else "")
                 for a in plan] or ["  (collect a first baseline)"]))

    out.append(("Advisory", [f"  {b.get('advisory_statement') or ''}"]))
    return out


def render_brief_text(brief) -> str:
    out: List[str] = []
    for title, lines in render_brief_sections(brief):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
