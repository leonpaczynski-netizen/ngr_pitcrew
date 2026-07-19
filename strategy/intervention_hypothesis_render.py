"""Deterministic renderer for a Mechanism-Constrained Intervention Hypothesis set (Phase 14).

Turns an ``InterventionHypothesisSet`` (dict form) into ordered, driver- and engineer-
readable sections. It renders STRINGS only: it never emits a numeric setup value, an
"Apply"/"approve" instruction, wording implying certainty where mechanisms compete, or
wording implying a hypothesis is a confirmed fix. Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v or "").replace("_", " ").strip()


def render_set_sections(hset) -> List[Tuple[str, List[str]]]:
    """Ordered (section_title, lines) for one hypothesis set. ``hset`` is a dict from
    ``InterventionHypothesisSet.to_dict()``."""
    s = hset if isinstance(hset, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    issue = s.get("canonical_issue") or {}
    itype = _t(issue.get("issue_type")) or "an issue"
    corners = ", ".join(s.get("source_annotation", {}).get("corners") or []) or "the corner(s) on record"
    out.append(("Source observation", [
        f"{itype.capitalize()} at {corners} - canonical Program-1 diagnosis (unchanged).",
        f"Overall intervention status: {_t(s.get('overall_status'))}.",
    ]))

    ann = s.get("source_annotation") or {}
    pm = ann.get("primary_mechanism")
    mech_lines = []
    if pm:
        mech_lines.append(f"Most supported mechanism: {pm.get('name')} ({_t(pm.get('status'))}).")
    for c in ann.get("competing_mechanisms") or []:
        mech_lines.append(f"Competing: {c.get('name')} ({_t(c.get('status'))}).")
    if mech_lines:
        out.append(("Supported / competing physical mechanisms", mech_lines))

    for bucket, title in (("testable", "Proposed controlled-test hypotheses (testable)"),
                          ("conditional", "Conditional hypotheses (require discrimination)"),
                          ("competing", "Competing hypotheses (discriminate first)"),
                          ("preserve_and_observe", "Preserve current setting / collect evidence"),
                          ("blocked", "Blocked hypotheses")):
        hyps = s.get(bucket) or []
        if not hyps:
            continue
        lines: List[str] = []
        for h in hyps:
            lines.extend(_render_hypothesis(h))
            lines.append("")
        out.append((title, lines))

    gaps = s.get("evidence_gaps") or []
    if gaps:
        out.append(("Missing evidence", [f"- {g}" for g in gaps]))

    out.append(("Safety", list(s.get("safety_statements") or [])))
    return out


def _render_hypothesis(h: dict) -> List[str]:
    tgt = h.get("target") or {}
    er = h.get("expected_response") or {}
    td = h.get("test_design") or {}
    lines = [
        f"* {h.get('explanation')}",
        f"  Mechanism-constrained direction: {_t(h.get('direction'))} "
        f"{tgt.get('component')} ({_t(tgt.get('parameter_group'))}, {_t(tgt.get('axle')) or 'n/a'}, "
        f"{_t(tgt.get('handling_phase'))}).",
        f"  Why plausible: {er.get('primary_effect')}",
        f"  Expected benefit: {er.get('predicted_benefit')} (timing: {_t(er.get('response_timing'))}).",
    ]
    if h.get("protected_good_at_risk"):
        lines.append(f"  Protect (confirmed-good): {', '.join(h['protected_good_at_risk'])}.")
    if h.get("predicted_trade_offs"):
        lines.append(f"  Trade-offs: {', '.join(h['predicted_trade_offs'])}.")
    if h.get("interaction_constraints"):
        for ic in h["interaction_constraints"]:
            lines.append(f"  Coupling: {ic}")
    if h.get("required_evidence"):
        lines.append("  Missing evidence: " + "; ".join(h["required_evidence"]) + ".")
    lines.append(f"  Controlled test: {_t(td.get('test_kind'))} ({td.get('ab_structure')}); "
                 f"variable = {td.get('variable_under_test')}; "
                 f"min {td.get('min_clean_laps')} clean laps; "
                 f"attributable to one field: {td.get('attributable_to_single_field')}.")
    if h.get("rejection_criteria"):
        lines.append("  Reject if: " + "; ".join(h["rejection_criteria"]) + ".")
    lines.append(f"  Working window: {_t(h.get('working_window_state'))}; "
                 f"prior outcome: {h.get('prior_outcome_relationship')}.")
    lines.append(f"  Status: {_t(h.get('status'))} (evidence grade: {_t(h.get('evidence_grade'))}).")
    return lines


def render_set_text(hset) -> str:
    out: List[str] = []
    for title, lines in render_set_sections(hset):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
