"""Deterministic renderer for the Programme Transfer Report (Program 2, Phase 23).

Renders the knowledge-transfer view as structured sections: the source programme, the transfer
candidates (per target: domain, level, reason, evidence, limitations), the reuse summary
(reusable / not reusable / additional-evidence-required), the isolated target contexts, and the
visible transfer-rule catalogue. It renders STRINGS only, shows NO Apply / import / copy-setup /
execute wording, and never implies knowledge or a setup was applied. Pure; deterministic; never
raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def _car(ctx) -> str:
    c = ctx if isinstance(ctx, dict) else {}
    return f"{c.get('car')} / {_t(c.get('discipline'))} / v{c.get('gt7_version')}"


def render_report_sections(report) -> List[Tuple[str, List[str]]]:
    r = report if isinstance(report, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    src = r.get("source_context") or {}
    tot = r.get("totals") or {}
    out.append(("Knowledge transfer summary", [
        f"Source programme: {_car(src)} / {src.get('driver')}.",
        f"Established source domains: {tot.get('established_source_domains')}; "
        f"target contexts: {tot.get('target_contexts')}; candidates evaluated: "
        f"{tot.get('candidates')}.",
        f"Transfer levels: {tot.get('transfer_level_counts') or {}}.",
        f"Reusable: {tot.get('reusable')}   Needs more evidence: "
        f"{tot.get('needs_more_evidence')}   Not reusable: {tot.get('not_reusable')}   "
        f"Isolated targets: {tot.get('isolated_targets')}.",
    ]))

    summary = r.get("reuse_summary") or {}
    if summary.get("reusable"):
        out.append(("Reusable engineering knowledge", [
            f"  - [{_t(e.get('transfer_level'))}] {e.get('statement')} "
            f"(target: {_car(e.get('target_context'))})"
            for e in summary.get("reusable") or []]))
    if summary.get("needs_more_evidence"):
        lines = []
        for e in summary.get("needs_more_evidence") or []:
            lines.append(f"  - [{_t(e.get('transfer_level'))}] {e.get('statement')} "
                         f"(target: {_car(e.get('target_context'))})")
            for req in e.get("evidence_required") or []:
                lines.append(f"      needs: {req}")
        out.append(("Additional evidence still required", lines))
    if summary.get("not_reusable"):
        out.append(("Not reusable", [
            f"  - {e.get('statement')} (target: {_car(e.get('target_context'))})"
            for e in summary.get("not_reusable") or []]))
    if summary.get("isolated_targets"):
        out.append(("Contexts that remain isolated", [
            "No established knowledge is reusable in these contexts:",
            "  - " + "; ".join(_car(t) for t in summary.get("isolated_targets") or [])]))

    out.append(("Transfer rules (visible)", [
        f"  - {rule.get('id')}: {rule.get('why')} [{rule.get('authority')}]"
        for rule in r.get("rule_catalogue") or []]))

    out.append(("Safety", [str(r.get("safety_statement") or "")]))
    return out


def render_report_text(report) -> str:
    out: List[str] = []
    for title, lines in render_report_sections(report):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
