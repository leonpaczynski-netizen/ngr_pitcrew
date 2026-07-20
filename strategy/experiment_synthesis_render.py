"""Deterministic renderer for a Minimum-Effective Experiment Synthesis result (Phase 15).

Phase 15 IS allowed to render numeric setup values (its purpose is a bounded numeric
experiment). But: values come only from canonical data + legal semantics; baseline and
candidate are always distinguished; display rounding never changes the stored value; no
value is presented as a final tune or "optimal"; nothing is applied. Pure; deterministic;
never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v or "").replace("_", " ").strip()


def _num(v) -> str:
    """Render a numeric value exactly (no rounding that would change the stored value)."""
    if isinstance(v, bool) or v is None:
        return str(v)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def render_result_sections(result) -> List[Tuple[str, List[str]]]:
    r = result if isinstance(result, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    hset = r.get("source_hypothesis_set") or {}
    issue = hset.get("canonical_issue") or {}
    ann = hset.get("source_annotation") or {}
    pm = ann.get("primary_mechanism") or {}
    out.append(("Source diagnosis & mechanism", [
        f"{_t(issue.get('issue_type')).capitalize() or 'Issue'} - canonical Program-1 "
        f"diagnosis (unchanged).",
        (f"Most supported mechanism: {pm.get('name')}." if pm else "No single supported mechanism."),
        f"Overall synthesis status: {_t(r.get('overall_status'))}.",
    ]))

    base = r.get("baseline") or {}
    out.append(("Canonical applied baseline", [
        f"Baseline setup: {base.get('name') or base.get('setup_id') or '-'} "
        f"(rev {base.get('revision')}), hash {str(base.get('setup_hash'))[:12]}.",
        f"Car/track/layout: {base.get('car')} / {base.get('track')} / {base.get('layout_id')}.",
        f"Confirmed applied on car: {base.get('is_active_on_car')}; complete: "
        f"{base.get('is_complete')}; identity matches session: {base.get('identity_matches')}.",
        f"Valid baseline: {base.get('is_valid_baseline')}." +
        (f" Blocked: {_t(base.get('block_reason'))} - {base.get('message')}"
         if not base.get('is_valid_baseline') else ""),
    ]))

    sel = r.get("selected_candidate")
    if sel:
        out.append(("Proposed bounded experiment (candidate controlled test)",
                    _render_candidate(sel)))
    alts = r.get("alternative_candidates") or []
    if alts:
        lines = []
        if r.get("unresolved_conflicts"):
            lines.append("Tie - manual choice required before preflight: "
                         + "; ".join(r["unresolved_conflicts"]))
        for c in alts:
            lines.extend(_render_candidate(c))
            lines.append("")
        out.append(("Alternative candidates", lines))

    rej = r.get("rejected") or []
    if rej:
        out.append(("Rejected hypotheses", [
            f"{x.get('component')}: {_t(x.get('status'))} - {x.get('reason')}" for x in rej]))

    out.append(("Safety", [str(r.get("safety_statement") or "")]))
    return out


def _render_candidate(c: dict) -> List[str]:
    lines = [f"* {c.get('explanation')}"]
    for d in c.get("deltas") or []:
        step_note = ("one legal step" if d.get("is_exactly_one_step")
                     else f"larger step ({_t(d.get('larger_step_reason'))})")
        lines.append(
            f"  Field: {d.get('field')} ({_t(d.get('subsystem'))}, role {_t(d.get('role'))}) - "
            f"{_t(d.get('direction'))}. BASELINE {_num(d.get('baseline_value'))} -> "
            f"CANDIDATE {_num(d.get('candidate_value'))} "
            f"(delta {_num(d.get('delta'))}, {step_note}; legal [{_num(d.get('legal_low'))}, "
            f"{_num(d.get('legal_high'))}], step {_num(d.get('legal_step'))}).")
        if d.get("expected_trade_offs"):
            lines.append(f"    Trade-offs: {', '.join(d['expected_trade_offs'])}.")
    if c.get("protected_good_behaviours"):
        lines.append(f"  Protect (confirmed-good): {', '.join(c['protected_good_behaviours'])}.")
    lines.append(f"  Unchanged fields preserved: {c.get('unchanged_field_count')} "
                 f"(fp {str(c.get('preserved_fields_fingerprint'))[:10]}).")
    lines.append(f"  Attribution: {_t(c.get('attribution_scope'))}; "
                 f"status: {_t(c.get('status'))} (grade {_t(c.get('evidence_grade'))}).")
    if c.get("rejection_criteria"):
        lines.append("  Reject if: " + "; ".join(c["rejection_criteria"]) + ".")
    lines.append(f"  Reversal: {c.get('reversal_instructions')}.")
    lines.append("  Not applied - route through the canonical Apply gate manually.")
    return lines


def render_result_text(result) -> str:
    out: List[str] = []
    for title, lines in render_result_sections(result):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
