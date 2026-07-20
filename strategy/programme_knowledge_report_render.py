"""Deterministic renderer for the Programme Knowledge Report (Program 2, Phase 22).

Renders the Engineering Knowledge Graph as structured sections: the programme/compatibility
summary (which events merged and why others did not), the per-domain knowledge (maturity,
confidence, evidence, remaining uncertainty, supporting campaigns/experiments/mechanisms,
limitations), and the domains where knowledge is still missing. It renders STRINGS only, shows
NO Apply / freeze / complete / execute / schedule wording, and never implies work was done.
Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def render_report_sections(report) -> List[Tuple[str, List[str]]]:
    r = report if isinstance(report, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    ctx = r.get("context_summary") or {}
    comp = r.get("compatibility") or {}
    tot = r.get("totals") or {}
    lines = [
        f"Programme: {ctx.get('car')} / {_t(ctx.get('discipline'))} / v{ctx.get('gt7_version')} "
        f"/ {ctx.get('driver')}.",
        f"Events merged: {comp.get('events_merged')} (tracks: "
        f"{', '.join(comp.get('primary_tracks') or []) or '-'}). {comp.get('merge_reason')}",
        f"Domains: {tot.get('known_domains')} known, {tot.get('missing_domains')} still missing. "
        f"Maturity: {tot.get('domain_maturity_counts') or {}}.",
    ]
    for e in comp.get("excluded_reasons") or []:
        key = e.get("compatibility_key") or {}
        lines.append(f"  - separate programme (not merged): {key.get('car')}/"
                     f"{_t(key.get('discipline'))}/v{key.get('gt7_version')}/{key.get('driver')} "
                     f"- {e.get('reason')}")
    out.append(("Programme knowledge summary", lines))

    graph = r.get("knowledge_graph") or {}
    for d in graph.get("domains") or []:
        if not (d.get("supporting_campaigns") or []):
            continue
        out.append((f"Domain: {_t(d.get('domain'))}", _domain_lines(d)))

    missing = graph.get("missing_domains") or []
    if missing:
        out.append(("Knowledge still missing", [
            "No campaign has produced evidence yet in these domains:",
            "  - " + ", ".join(_t(m) for m in missing)]))

    out.append(("Safety", [str(r.get("safety_statement") or "")]))
    return out


def _domain_lines(d: dict) -> List[str]:
    mat = d.get("maturity") or {}
    conf = d.get("confidence") or {}
    state = d.get("knowledge_state") or {}
    unc = d.get("remaining_uncertainty") or {}
    ev = d.get("supporting_evidence") or {}
    lines = [
        f"Maturity: {_t(mat.get('value'))} - {mat.get('reason')} [{mat.get('source')}]",
        f"Knowledge state: {_t(state.get('value'))} - {state.get('reason')} [{state.get('source')}]",
        f"Confidence: {_t(conf.get('value'))} - {conf.get('reason')} "
        f"[{conf.get('source')}; {conf.get('calculation')}]",
        f"Remaining uncertainty: {_t(unc.get('value'))} - {unc.get('reason')} [{unc.get('source')}]",
        f"Evidence: {ev.get('contributing_campaigns')} campaign(s), {ev.get('confirmations')} "
        f"confirmed, {ev.get('regressions')} regressed, {ev.get('executed')} executed "
        f"[{ev.get('source')}].",
        f"Supporting campaigns: {', '.join(d.get('supporting_campaigns') or []) or '-'}.",
        f"Supporting experiments (fields): {', '.join(d.get('supporting_experiments') or []) or '-'}.",
        f"Supporting mechanisms: {', '.join(d.get('supporting_mechanisms') or []) or '-'}.",
    ]
    for lim in d.get("known_limitations") or []:
        lines.append(f"  - limitation: {lim}")
    return lines


def render_report_text(report) -> str:
    out: List[str] = []
    for title, lines in render_report_sections(report):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
