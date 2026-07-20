"""Deterministic renderer for the guarded experiment lifecycle (Phase 16).

Renders the read-only closed-loop chain — diagnosis -> mechanism -> hypothesis -> synthesis
-> experiment -> preflight -> (manual) apply -> outcome -> reconciliation -> prediction
calibration — as ordered stage rows. It renders STRINGS only, shows no Apply control wording,
and states plainly that nothing is applied here. Pure; deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple


def _t(v) -> str:
    return str(v or "").replace("_", " ").strip()


_STAGE_ORDER = [
    ("diagnosis", "Diagnosis"),
    ("mechanism", "Mechanism"),
    ("hypothesis", "Hypothesis"),
    ("synthesis", "Bounded experiment (synthesis)"),
    ("experiment", "Canonical experiment"),
    ("preflight", "Preflight"),
    ("apply", "Manual Apply (existing gate only)"),
    ("outcome", "Outcome"),
    ("reconciliation", "Reconciliation"),
    ("calibration", "Prediction calibration"),
]


def render_summary_sections(summary) -> List[Tuple[str, List[str]]]:
    s = summary if isinstance(summary, dict) else {}
    out: List[Tuple[str, List[str]]] = []

    issue = s.get("diagnosis") or {}
    out.append(("Engineering lifecycle", [
        f"{_t(issue.get('issue_type')).capitalize() or 'Issue'} - overall state: "
        f"{_t(s.get('lifecycle_state'))}.",
        "Read-only: nothing is applied here; the frozen Apply gate remains the sole route "
        "to the car.",
    ]))

    stages = s.get("stage_states") or {}
    lines = []
    for key, label in _STAGE_ORDER:
        st = stages.get(key, "absent")
        marker = "OK" if str(st) not in ("absent", "n/a", "") else "--"
        lines.append(f"[{marker}] {label}: {_t(st) or 'absent'}")
    out.append(("Loop stages", lines))

    trace = s.get("trace") or {}
    out.append(("Traceability", [
        f"diagnosis: {trace.get('diagnosis_key') or '-'}",
        f"mechanism: {', '.join(trace.get('mechanism_ids') or []) or '-'}",
        f"hypothesis: {', '.join(trace.get('hypothesis_ids') or []) or '-'}",
        f"synthesis candidate: {trace.get('synthesis_candidate_id') or '-'}",
        f"experiment: {trace.get('experiment_id') or trace.get('experiment_idempotency_key') or '-'}",
        f"outcome: {trace.get('outcome_id') or '-'}",
        f"reconciliation: {trace.get('reconciliation_record_key') or '-'}",
        f"prediction fp: {str(trace.get('prediction_fingerprint') or '-')[:12]}",
    ]))

    calib = s.get("calibration") or {}
    if calib.get("reconciliations"):
        out.append(("Prediction calibration (aggregate)", [
            f"reconciliations folded: {calib.get('reconciliations')}",
            f"overall accuracy: {calib.get('overall_accuracy')}",
        ]))

    out.append(("Safety", [str(s.get("safety_statement") or "")]))
    return out


def render_summary_text(summary) -> str:
    out: List[str] = []
    for title, lines in render_summary_sections(summary):
        out.append(title)
        out.extend(f"  {ln}" for ln in lines if str(ln).strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"
