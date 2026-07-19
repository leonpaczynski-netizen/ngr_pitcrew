"""Deterministic renderer for a Mechanism-Annotated Diagnosis (Program 2, Phase 13).

Turns the immutable ``MechanismAnnotatedDiagnosis`` (dict form) into ordered, driver-
readable sections that keep the three layers visibly separate:

  * What the app OBSERVED  (Program-1 direct observation)
  * The most-SUPPORTED mechanism  (physics-informed, from Phase 12)
  * Secondary interactions
  * Competing mechanisms + why we are not certain
  * GT7 limitations (what the app cannot claim)
  * The experiment / prediction relationship
  * The evidence that would distinguish the mechanisms

It renders STRINGS only. It invents no setup value, proposes no Apply, and never
presents a physics-informed interpretation as raw telemetry. Pure: Qt-free, DB-free,
deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v or "").replace("_", " ").strip()


def _title(v) -> str:
    return _t(v).title()


def render_sections(annotation) -> List[Tuple[str, List[str]]]:
    """Return ordered (section_title, lines) pairs. ``annotation`` is a dict from
    ``MechanismAnnotatedDiagnosis.to_dict()``. Deterministic; never raises."""
    a = annotation if isinstance(annotation, dict) else {}
    sections: List[Tuple[str, List[str]]] = []

    # --- What the app observed (Program 1) --------------------------------- #
    issue = a.get("canonical_issue") or {}
    corners = ", ".join(a.get("corners") or []) or "the corner(s) on record"
    phases = ", ".join(_t(p) for p in (a.get("handling_phases") or [])) or "the recorded phase"
    obs = []
    residual = _t(issue.get("residual_state") or issue.get("latest_state"))
    itype = _t(issue.get("issue_type")) or "an issue"
    axle = _t(issue.get("axle"))
    valid = issue.get("valid_laps") or issue.get("sample_count")
    line = f"{itype.capitalize()}"
    if axle:
        line += f" ({axle})"
    line += f" was observed at {corners} during {phases}"
    if valid:
        line += f", on {valid} valid lap(s)"
    if residual:
        line += f"; canonical state: {residual}"
    obs.append(line + ".")
    obs.append("This is a direct Program-1 observation — the mechanism annotation below "
               "does not change whether it occurred.")
    sections.append(("What the app observed", obs))

    status = _t(a.get("overall_status"))
    # --- Ineligible: explain why no mechanism is asserted ------------------ #
    if a.get("ineligibility_reason"):
        sections.append(("Mechanism annotation unavailable", [
            f"No supported physical mechanism is asserted ({status}).",
            f"Reason: {a.get('ineligibility_reason')}.",
            "Vehicle-dynamics knowledge does not override missing or invalid evidence.",
        ]))
        return sections

    # --- Most supported mechanism ------------------------------------------ #
    pm = a.get("primary_mechanism")
    if pm:
        lines = [
            f"Most supported mechanism ({_t(pm.get('status'))}, "
            f"evidence grade: {_t(pm.get('evidence_grade'))}): {pm.get('name')}.",
            f"Physical basis: {pm.get('primary_physical_cause')}",
            f"Handling phase: {_t(pm.get('handling_phase'))}; "
            f"load transfer: {_t(pm.get('load_transfer_mode'))}.",
            "This is a physics-informed interpretation, not a direct measurement.",
        ]
        sections.append(("Most supported mechanism", lines))
    else:
        sections.append(("Most supported mechanism", [
            f"No single mechanism is best-supported ({status}); the plausible causes are "
            "kept as competing explanations below."]))

    # --- Load transfer ----------------------------------------------------- #
    lt = a.get("load_transfer_explanation")
    if lt:
        sections.append(("Load transfer", [
            f"{_title(lt.get('mode'))}: {lt.get('direction')}",
            lt.get("balance_effect") or "",
            lt.get("note") or "",
        ]))

    # --- Secondary interactions -------------------------------------------- #
    inter = a.get("interactions") or []
    if inter:
        lines = [f"{_title(i.get('a'))} + {_title(i.get('b'))} - {i.get('role')}: "
                 f"{i.get('mechanism')}" for i in inter]
        sections.append(("Secondary interactions", lines))

    # --- Competing mechanisms + why not certain ---------------------------- #
    competing = a.get("competing_mechanisms") or []
    if competing:
        lines = []
        for c in competing:
            tag = _t(c.get("status"))
            line = f"{c.get('name')} ({tag})"
            if c.get("intervention_direction_contradicted"):
                line += " — a prior intervention in this direction failed (kept as a "
                line += "possible mechanism, not a cure)"
            lines.append(line + ".")
        sections.append(("Competing mechanisms", lines))

    # --- Contradicted mechanisms ------------------------------------------- #
    contra = a.get("contradicted_mechanisms") or []
    if contra:
        sections.append(("Contradicted mechanisms", [
            f"{c.get('name')} — contradicted by the evidence." for c in contra]))

    # --- Why we are not certain / GT7 limitations -------------------------- #
    gt7 = a.get("gt7_limitations") or []
    if gt7:
        sections.append(("Why the app is not certain (GT7 limitations)",
                         [str(g) for g in gt7]))

    # --- Experiment + prediction relationship ------------------------------ #
    rel_lines = []
    if a.get("outcome_consistency"):
        rel_lines.append(a.get("outcome_consistency") + ".")
    pr = a.get("prediction_relationship") or {}
    if pr.get("has_prediction"):
        rel_lines.append(f"Pre-flight predicted: {pr.get('predicted')}")
        rel_lines.append(f"Observed: {pr.get('observed')}")
        rel_lines.append(f"Reconciliation: {pr.get('verdict')} "
                         f"({_t(pr.get('reconciliation_status'))}).")
        rel_lines.append("Prediction calibration is owned by Phase 11 and is not changed "
                         "here.")
    if rel_lines:
        sections.append(("Experiment & prediction relationship", rel_lines))

    # --- Evidence needed --------------------------------------------------- #
    need = list(a.get("required_discriminating_evidence") or [])
    gaps = list(a.get("evidence_gaps") or [])
    if need or gaps:
        lines = []
        if gaps:
            lines.append("Gaps: " + "; ".join(gaps) + ".")
        for n in need:
            lines.append(f"• {n}")
        sections.append(("Evidence that would distinguish the mechanisms", lines))

    return sections


def render_text(annotation) -> str:
    """Flatten the sections into a single deterministic block of text."""
    out: List[str] = []
    for title, lines in render_sections(annotation):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
