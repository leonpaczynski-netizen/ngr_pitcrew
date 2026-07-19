"""Deterministic renderer for the Programme Knowledge Timeline (Program 2, Phase 25).

Renders the temporal knowledge layer as structured sections: historical sequence, current
convergence per domain (independent vs dependent evidence), confirmed-good preservation,
regressions & retired directions, unresolved conflicts, superseded conclusions, context & transfer
limitations, unknowns, and why each status was assigned.

It renders STRINGS only, performs zero DB access, and never renders setup field values, suggested
setup numbers, Apply language, optimiser output, scheduling instructions, automatic next actions
or invented certainty. Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _prog(p) -> str:
    p = p if isinstance(p, dict) else {}
    return f"{p.get('car')} / {_t(p.get('discipline'))} / v{p.get('gt7_version')} / {p.get('driver')}"


def render_timeline_sections(report) -> List[Tuple[str, List[str]]]:
    r = report if isinstance(report, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    src = r.get("source_programme") or {}
    ind = r.get("evidence_independence_summary") or {}
    pts = r.get("timeline_points") or []
    header = [f"Programme: {_prog(src)}.",
              f"Timeline points: {len(pts)}.  Evidence lineage: {ind.get('independent_groups')} "
              f"independent line(s), {ind.get('partially_independent')} partially-independent, "
              f"{ind.get('same_session')} same-session, {ind.get('same_source_record')} same-record "
              "repeat(s).",
              f"  {ind.get('note')}"]
    if r.get("empty_state"):
        header.append(r.get("empty_state"))
    out.append(("Engineering knowledge timeline", header))

    # historical sequence
    seq_lines: List[str] = []
    for p in pts:
        unk = f"  [unknown: {', '.join(p.get('unknown_fields'))}]" if p.get("unknown_fields") else ""
        neg = "  [negative learning]" if p.get("negative_learning") else ""
        seq_lines.append(f"  - {p.get('evidence_date')} (seq {p.get('sequence_key')}) "
                         f"{_t(p.get('knowledge_domain'))}: {_t(p.get('transition_type'))} "
                         f"[{_t(p.get('evidence_independence'))}] {p.get('prior_state')} -> "
                         f"{p.get('resulting_state')} - {p.get('rationale')}{neg}{unk}")
    out.append(("Historical sequence", seq_lines or ["No evidence transitions recorded."]))

    # convergence by domain
    clines: List[str] = []
    for c in r.get("convergence_summaries") or []:
        aid = "  (investigation aid only)" if c.get("suitable_only_as_investigation_aid") else ""
        clines.append(f"  - {_t(c.get('domain'))}: {_t(c.get('convergence_status'))} - "
                      f"{c.get('independent_support_count')} independent / "
                      f"{c.get('dependent_support_count')} dependent support, "
                      f"{c.get('regression_count')} regression(s); maturity "
                      f"{_t(c.get('current_maturity'))}, confidence {_t(c.get('current_confidence'))}."
                      f"{aid}")
        clines.append(f"      why: {c.get('rationale')}")
        clines.append(f"      lineage: {c.get('evidence_lineage_summary')}")
        for lim in c.get("transfer_limitations") or []:
            clines.append(f"      transfer limit: {lim}")
    out.append(("Convergence by domain", clines or ["No domains to assess."]))

    # confirmed-good preservation
    cg = r.get("stable_confirmed_good") or []
    out.append(("Confirmed-good preservation", [
        f"  - {_t(c.get('domain'))}: preserved as confirmed-good ({_t(c.get('convergence_status'))}); "
        f"protect it during any related investigation." for c in cg] or ["None recorded."]))

    # conflicts and regressions
    conf_lines = [f"  - {_t(c.get('domain'))}: {c.get('rationale')}"
                  for c in r.get("unresolved_conflicts") or []]
    reg_lines = []
    for c in r.get("regressions_and_retired") or []:
        reg_lines.append(f"  - {_t(c.get('domain'))}: {c.get('regression_count')} regression(s)"
                         + (f"; retired: {'; '.join(c.get('retired_directions'))}"
                            if c.get("retired_directions") else ""))
    out.append(("Unresolved conflicts", conf_lines or ["None."]))
    out.append(("Regressions and retired directions", reg_lines or ["None."]))

    # superseded conclusions
    out.append(("Superseded conclusions", [
        f"  - {_t(c.get('domain'))}: an earlier conclusion was superseded by later stronger "
        "independent evidence; the history is retained above."
        for c in r.get("superseded_conclusions") or []] or ["None."]))

    # context & transfer limitations
    blines = [f"  - {_t(b.get('boundary_type'))} ({_t(b.get('domain'))}"
              + (f" -> {b.get('target_car')}" if b.get("target_car") else "") + f"): {b.get('reason')}"
              for b in r.get("knowledge_boundaries") or []]
    out.append(("Context and transfer limitations", blines or ["None."]))

    out.append(("Notes", [_DATES_NOTE, str(r.get("safety_statement") or "")]))
    return out


_DATES_NOTE = ("Dates are evidence data, not authority: a newer observation never automatically "
               "overrides an older stronger finding, and repeated dependent evidence is not a new "
               "independent confirmation. No setup values are shown.")


def render_timeline_text(report) -> str:
    out: List[str] = []
    for title, lines in render_timeline_sections(report):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
