"""Deterministic renderer for the Engineering Run Plan (Program 2, Phase 40).

Renders the practice-run plan as concise, labelled sections. Strings only; zero DB access;
timestamp-free; never renders raw applied setup values as an instruction or any Apply control. Pure;
deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v if v is not None else "").replace("_", " ").strip()


def render_run_plan_sections(plan) -> List[Tuple[str, List[str]]]:
    p = plan if isinstance(plan, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    c = p.get("context") or {}
    ctx = [f"Driver {c.get('driver') or '-'} / car {c.get('car') or '-'} / {c.get('track') or '-'}"
           f" {c.get('layout_id') or '-'} / {_t(c.get('discipline')).upper() or '-'}.",
           f"Event {c.get('event_id') or '-'}; compound {c.get('compound') or '-'}; "
           f"tyre x{c.get('tyre_multiplier') or '-'}, fuel x{c.get('fuel_multiplier') or '-'}.",
           f"Applied setup: {c.get('applied_setup') or '-'}; parent: {c.get('parent_setup') or '-'}.",
           f"Context fingerprint: {c.get('context_fingerprint') or '-'}."]
    if p.get("deadline_posture"):
        ctx.append("DEADLINE: " + p.get("deadline_posture"))
    if p.get("empty_state"):
        ctx.append(p.get("empty_state"))
    out.append(("Practice-run context", ctx))

    o = p.get("objective") or {}
    out.append((f"Objective ({_t(o.get('discipline')).upper() or '-'})",
                [f"  Goal: {o.get('primary_goal') or '-'}",
                 "  Optimise: " + (", ".join(o.get("optimise") or []) or "-"),
                 "  Avoid: " + (", ".join(o.get("avoid") or []) or "-")]))

    cl = p.get("candidate_link") or {}
    out.append(("Candidate (existing - referenced, never created)",
                [f"  Candidate: {cl.get('candidate_id') or '(none)'} (source {cl.get('source') or '-'}).",
                 f"  Existing: {cl.get('is_existing')}; preflight required: {cl.get('preflight_required')}.",
                 f"  {cl.get('note') or ''}"]))

    cc = p.get("controlled_change") or {}
    lines = [f"  Causal confidence: {_t(cc.get('causal_confidence'))}."]
    if cc.get("is_bundle"):
        lines.append("  BUNDLE: " + str(cc.get("bundle_reason") or ""))
    for ch in (cc.get("changes") or []):
        lines.append(f"  - {ch.get('field')}: {_t(ch.get('proposed_direction')) or 'adjust'} "
                     f"(current {ch.get('current_value') or '-'}); why: {ch.get('why') or '-'}; "
                     f"rollback -> {ch.get('rollback_value') or '-'}.")
    if not (cc.get("changes") or []):
        lines.append("  (no controlled change - collection run)")
    lines.append("  " + str(cc.get("note") or ""))
    out.append(("Controlled change", lines))

    hc = p.get("held_constant") or {}
    out.append(("Held constant",
                ["  Setup fields held: " + (", ".join(hc.get("setup_fields_held") or []) or "-"),
                 "  Technique: " + (", ".join(hc.get("technique_variables") or []) or "-"),
                 f"  Compound {hc.get('compound')}; {hc.get('fuel_load_window')}; "
                 f"{hc.get('tyre_age_window')}; {hc.get('weather_track_state')}.",
                 f"  Assists {hc.get('assists')}; brake balance/fuel map: {hc.get('brake_balance_fuel_map')}.",
                 f"  {hc.get('note') or ''}"]))

    rs = p.get("run_structure") or {}
    out.append(("Run structure",
                [f"  Warm-up {rs.get('warm_up_laps')}; measurement {rs.get('valid_measurement_laps')}; "
                 f"min clean {rs.get('minimum_clean_laps')}; max {rs.get('maximum_run_laps')} laps.",
                 "  Target corners: " + (", ".join(rs.get("target_corners") or []) or "-"),
                 "  Metrics: " + (", ".join(rs.get("target_metrics") or []) or "-"),
                 "  Feedback: " + (", ".join(rs.get("required_driver_feedback") or []) or "-"),
                 f"  Baseline: {rs.get('comparison_baseline') or '-'}"]))

    er = p.get("expected_result") or {}
    out.append(("Expected result & falsification",
                [f"  Primary: {er.get('primary_expected_outcome') or '-'}",
                 "  Protect: " + (", ".join(er.get("protected_behaviours") or []) or "-"),
                 "  Unacceptable: " + (", ".join(er.get("unacceptable_regressions") or []) or "-"),
                 f"  Success: {er.get('success_threshold') or '-'}",
                 f"  Failure: {er.get('failure_threshold') or '-'}",
                 f"  Falsifier: {er.get('falsifying_observation') or '-'}"]))

    out.append(("Run-validity gate (all must hold for the run to count)",
                ["  - " + str(g) for g in (p.get("validity_gate") or [])] or ["  -"]))

    sc = p.get("stop_conditions") or {}
    out.append(("Stop conditions",
                ["  Immediate stop: " + (", ".join(sc.get("immediate_stop") or []) or "-"),
                 "  Review: " + (", ".join(sc.get("review_rather_than_continue") or []) or "-"),
                 "  Disposition: " + (", ".join(sc.get("disposition_options") or []) or "-")]))

    sr = p.get("safety_rollback") or {}
    out.append(("Safety & rollback",
                [f"  Rollback target: {sr.get('rollback_target') or '-'}",
                 f"  Disposition: {sr.get('recommended_disposition') or '-'}"]))

    out.append(("Advisory", [f"  {p.get('advisory_statement') or ''}"]))
    return out


def render_run_plan_text(plan) -> str:
    out: List[str] = []
    for title, lines in render_run_plan_sections(plan):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
