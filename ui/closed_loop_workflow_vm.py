"""Pure view-model for the Closed-Loop Engineering workflow (Qt-free, Program 2, Phases 39-41).

Turns the read-only ``SessionDB.build_closed_loop_workflow_report`` result into a banner + a set of
cards for the three-step workflow: Evidence Readiness, Practice Run Plan, Outcome Review. Each card
carries a semantic tone AND an explicit text status tag (meaning is never carried by colour alone).
Display strings only; never raises; no setup values.
"""
from __future__ import annotations

from typing import List, Tuple


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok") or not (r.get("run_plan") or r.get("evidence_readiness"))


def completeness_label(result) -> str:
    return str(build(result).get("completeness") or "").replace("_", " ").upper() or "-"


def _posture_tag(result) -> Tuple[str, str]:
    r = build(result)
    posture = str(r.get("posture") or "")
    if posture == "protect":
        return ("PROTECT SETUP", "warn")
    if posture == "collect":
        return ("COLLECT EVIDENCE", "advisory")
    if r.get("closed_loop"):
        promo = str((r.get("closed_loop") or {}).get("promotion_eligibility") or "")
        if "rollback" in promo:
            return ("ROLLBACK", "warn")
        if promo == "best_known_eligible":
            return ("BEST-KNOWN ELIGIBLE", "success")
    return ("EXPERIMENT READY", "info")


def header_text(result) -> str:
    r = build(result)
    if is_empty(result):
        return ("No closed-loop workflow yet. Read-only, advisory-only - context-safe evidence, an "
                "existing candidate's practice-run plan, and outcome review. It creates no experiment, "
                "applies no setup, promotes nothing, and is not permission to Apply. No setup values.")
    tag, _tone = _posture_tag(result)
    parts = [f"[{tag}]  Context readiness {completeness_label(result)}.",
             f"{r.get('exact_evidence_count', 0)} exact-context record(s)."]
    cl = r.get("closed_loop")
    if cl:
        parts.append("Outcome: " + str(cl.get("outcome_state") or "-").replace("_", " ").upper()
                     + "; next: " + str((cl.get("primary_next_action") or {}).get("kind") or "-")
                     .replace("_", " ").upper() + ".")
    else:
        parts.append("Outcome review appears once a completed run is supplied.")
    return " ".join(parts)


def banner_tone(result) -> str:
    if is_empty(result):
        return "advisory"
    return _posture_tag(result)[1]


def workflow_cards(result) -> List[dict]:
    from strategy.contextual_knowledge_activation_render import render_scope_sections
    from strategy.engineering_run_plan_render import render_run_plan_sections
    from strategy.closed_loop_report_render import render_closed_loop_sections
    r = build(result)
    if is_empty(result):
        return []
    cards: List[dict] = []

    # Step 1 — Evidence Readiness
    ev = r.get("evidence_readiness") or {}
    scoped = ev.get("scoped_chain") or {}
    val = ev.get("validation") or {}
    lines: List[str] = []
    for _t, ls in render_scope_sections(scoped.get("scope") or {}):
        lines.extend(ls)
    counts = scoped.get("counts") or {}
    lines.append("Evidence scope: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + ".")
    for d in (scoped.get("exact_domain_summary") or []):
        lines.append(f"  - {d.get('domain')}: {d.get('evidence_count')} record(s), "
                     f"{d.get('independent_sessions')} independent, {d.get('convergence')}.")
    contam = int(counts.get("excluded", 0) or 0) + int(counts.get("reference_only", 0) or 0)
    if contam:
        lines.append(f"Contamination guard: {contam} incompatible/reference record(s) excluded from "
                     f"exact conclusions.")
    for flag in ("ambiguous_multi_field_regressions", "contradictory_outcomes", "unsafe_attribution",
                 "orphan_setup_references", "missing_context_fields"):
        vv = val.get(flag) or []
        if vv:
            lines.append(f"Validation - {flag.replace('_', ' ')}: {len(vv)}.")
    tag = "CONTAMINATION EXCLUDED" if contam else "CLEAN SCOPE"
    cards.append({"title": "1. Evidence Readiness", "status_tag": tag,
                  "tone": "info" if contam else "success", "lines": lines})

    # Step 2 — Practice Run Plan
    plan_lines: List[str] = []
    for _t, ls in render_run_plan_sections(r.get("run_plan") or {}):
        plan_lines.append(f"[{_t}]")
        plan_lines.extend(ls)
    sel = r.get("candidate_selection") or {}
    ptag, ptone = _posture_tag(result)
    plan_lines.insert(0, "Candidate: " + str((sel.get("selected") or {}).get("id") or "(none)")
                      + " - " + str(sel.get("reason") or ""))
    cards.append({"title": "2. Practice Run Plan", "status_tag": ptag, "tone": ptone,
                  "lines": plan_lines})

    # Step 3 — Outcome Review
    cl = r.get("closed_loop")
    if cl:
        out_lines: List[str] = []
        for _t, ls in render_closed_loop_sections(cl):
            out_lines.append(f"[{_t}]")
            out_lines.extend(ls)
        promo = str(cl.get("promotion_eligibility") or "")
        otag = ("ROLLBACK" if "rollback" in promo else
                "ELIGIBLE" if promo == "best_known_eligible" else
                "CONFIRM" if promo in ("provisional", "requires_confirmation") else "NOT ELIGIBLE")
        otone = ("warn" if "rollback" in promo else "success" if promo == "best_known_eligible"
                 else "info")
        cards.append({"title": "3. Outcome Review", "status_tag": otag, "tone": otone,
                      "lines": out_lines})
    else:
        cards.append({"title": "3. Outcome Review", "status_tag": "AWAITING RUN", "tone": "advisory",
                      "lines": ["No completed run supplied yet. After a controlled practice run, the "
                                "outcome review shows run validity, expected-vs-observed, promotion "
                                "eligibility and the next engineering action.",
                                "Recording an outcome stays in the existing explicit experiment "
                                "workflow; nothing is written here."]})
    return cards
