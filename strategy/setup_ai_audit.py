"""AI audit module — Group 42: Rule-First Setup Brain.

Provides the lightweight AI audit layer that sits AFTER the deterministic
rule engine.  The AI is asked only to CHECK the plan for contradictions and
missing evidence — NOT to generate new setup changes.

Public API
----------
build_audit_prompt(diagnosis, plan, current_setup, driver_profile,
                   validation_failures, rejected_candidates, protected_fields) -> str

parse_audit_response(response_text, canonical_params) -> AuditResult

map_audit_to_finaliser(audit, has_blocking_validation) -> tuple[str, list[str]]

Design notes
------------
- This module does NOT import driving_advisor (avoids circular import).
  canonical_params is passed in by the caller.
- parse_audit_response NEVER raises — returns a degraded NEEDS_MORE_DATA
  AuditResult on any parse failure.
- map_audit_to_finaliser never un-zeros changes blocked by engineering
  validation — that invariant is enforced by the caller.
"""
from __future__ import annotations

import json
import logging
from enum import Enum
from typing import NamedTuple

from strategy.setup_rule_engine import SetupPlan

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and NamedTuples
# ---------------------------------------------------------------------------

class AuditStatus(str, Enum):
    APPROVED = "APPROVED"
    APPROVED_WITH_WARNINGS = "APPROVED_WITH_WARNINGS"
    REJECTED = "REJECTED"
    NEEDS_MORE_DATA = "NEEDS_MORE_DATA"


class AuditResult(NamedTuple):
    """Result of the AI audit step."""
    status: AuditStatus
    warnings: list
    contradictions: list
    missing_evidence: list
    explanation_notes: str
    stripped_fields: list   # canonical setup fields found in the AI response and stripped


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_audit_prompt(
    diagnosis: dict,
    plan: SetupPlan,
    current_setup: dict,
    driver_profile: object,  # DriverProfile NamedTuple — avoid import for type
    validation_failures: list,  # list[ValidationFailure]
    rejected_candidates: list,
    protected_fields: list,
) -> str:
    """Build the AI audit prompt.

    The prompt is structured with clearly labelled sections so tests can grep
    for each section header.

    IMPORTANT CONSTRAINTS communicated to the AI
    -------------------------------------------
    - Do NOT create new setup changes.
    - Do NOT output actionable fields.
    - ONLY check for contradictions, missing context, unsafe reasoning.
    - Return strict JSON matching the schema below.
    """
    import json as _json

    # --- Section: Diagnosis Summary ---
    diag_lines = [
        "## SECTION: DIAGNOSIS SUMMARY",
        f"dominant_problem: {diagnosis.get('dominant_problem', 'unknown')}",
        f"secondary_problems: {diagnosis.get('secondary_problems', [])}",
        f"bottoming_band: {diagnosis.get('bottoming_band', 'minor')}",
        f"wheelspin_band: {diagnosis.get('wheelspin_band', 'low')}",
        f"wheelspin_subtype: {diagnosis.get('wheelspin_subtype', 'insufficient_data')}",
        f"compliance_priority: {diagnosis.get('compliance_priority', False)}",
        f"gearbox_flag: {diagnosis.get('gearbox_flag', 'preserve')}",
        f"aero_front_near_min: {diagnosis.get('aero_front_near_min', False)}",
        f"aero_rear_near_min: {diagnosis.get('aero_rear_near_min', False)}",
        f"aero_rear_healthy: {diagnosis.get('aero_rear_healthy', False)}",
        f"location_confidence: {diagnosis.get('location_confidence', 'low')}",
    ]
    feel_flags = diagnosis.get("driver_feel_flags") or {}
    active_feel = [k for k, v in feel_flags.items() if v]
    diag_lines.append(f"driver_feel_flags (active): {active_feel}")

    # --- Section: Proposed Plan ---
    proposed_lines = ["## SECTION: PROPOSED PLAN"]
    for intent in plan.proposed:
        proposed_lines.append(
            f"  field={intent.field}, delta={intent.delta:+.2f}, "
            f"from={intent.from_value}, to={intent.to_value}, "
            f"rule_id={intent.rule_id}, risk={intent.risk}, "
            f"confidence={intent.confidence}, "
            f"symptom={intent.symptom!r}"
        )
    if not plan.proposed:
        proposed_lines.append("  (no proposed changes)")

    # --- Section: Rejected Candidates ---
    rejected_lines = ["## SECTION: REJECTED CANDIDATES"]
    for rc in (rejected_candidates or []):
        if isinstance(rc, dict):
            rejected_lines.append(f"  {rc}")
        else:
            # SetupChangeIntent
            rejected_lines.append(
                f"  field={rc.field}, rule_id={rc.rule_id}, reason={rc.rationale!r}"
            )
    if not rejected_candidates:
        rejected_lines.append("  (none)")

    # --- Section: Protected Fields ---
    pf_lines = [
        "## SECTION: PROTECTED FIELDS",
        f"  {protected_fields or []}",
    ]

    # --- Section: Current Setup ---
    setup_lines = [
        "## SECTION: CURRENT SETUP",
        _json.dumps(current_setup, ensure_ascii=False, indent=2),
    ]

    # --- Section: Driver Profile ---
    profile_lines = ["## SECTION: DRIVER PROFILE"]
    try:
        if hasattr(driver_profile, "_asdict"):
            pd = driver_profile._asdict()
        else:
            pd = dict(driver_profile) if driver_profile else {}
        profile_lines.append(_json.dumps(pd, ensure_ascii=False, indent=2))
    except Exception:
        profile_lines.append("  (unavailable)")

    # --- Section: Validation Failures ---
    vf_lines = ["## SECTION: VALIDATION FAILURES"]
    for vf in (validation_failures or []):
        if hasattr(vf, "severity") and hasattr(vf, "message"):
            vf_lines.append(f"  [{vf.severity}] {vf.message}")
        else:
            vf_lines.append(f"  {vf}")
    if not validation_failures:
        vf_lines.append("  (none)")

    # --- Section: Audit Instructions ---
    instructions = [
        "## SECTION: AUDIT INSTRUCTIONS",
        "",
        "You are a senior race engineer performing a SAFETY AND COHERENCE AUDIT ONLY.",
        "",
        "STRICT CONSTRAINTS — you MUST follow all of these:",
        "1. Do NOT create new setup changes.",
        "2. Do NOT output actionable setup fields.",
        "3. Do NOT modify, remove, or re-rank the proposed changes.",
        "4. ONLY identify contradictions, missing context, or unsafe reasoning.",
        "",
        "Examine the proposed plan against the diagnosis, driver profile, and",
        "validation failures. Return ONLY the following strict JSON object",
        "(no markdown, no extra keys, no setup fields):",
        "",
        '{"status": "APPROVED" | "APPROVED_WITH_WARNINGS" | "REJECTED" | "NEEDS_MORE_DATA",',
        ' "warnings": ["..."],',
        ' "contradictions": ["..."],',
        ' "missing_evidence": ["..."],',
        ' "explanation_notes": "..."}',
        "",
        "status meanings:",
        "  APPROVED            — plan is coherent, no concerns.",
        "  APPROVED_WITH_WARNINGS — plan is acceptable but has non-blocking concerns.",
        "  REJECTED            — plan has a serious contradiction or safety issue.",
        "  NEEDS_MORE_DATA     — cannot make a confident assessment with available data.",
        "",
        "If contradictions are empty and warnings are empty: use APPROVED.",
        "If small warnings only: use APPROVED_WITH_WARNINGS.",
        "If a serious contradiction: use REJECTED.",
        "If critical data is missing to assess: use NEEDS_MORE_DATA.",
    ]

    sections = (
        diag_lines + [""]
        + proposed_lines + [""]
        + rejected_lines + [""]
        + pf_lines + [""]
        + setup_lines + [""]
        + profile_lines + [""]
        + vf_lines + [""]
        + instructions
    )
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

_KNOWN_STATUSES = {
    "APPROVED": AuditStatus.APPROVED,
    "APPROVED_WITH_WARNINGS": AuditStatus.APPROVED_WITH_WARNINGS,
    "REJECTED": AuditStatus.REJECTED,
    "NEEDS_MORE_DATA": AuditStatus.NEEDS_MORE_DATA,
}


def parse_audit_response(
    response_text: str,
    canonical_params: frozenset,
) -> AuditResult:
    """Parse the AI's audit JSON response into an AuditResult.

    Never raises — returns a degraded NEEDS_MORE_DATA AuditResult on failure.
    Strips any canonical setup field keys found in the parsed object and
    records them in stripped_fields (with a logging.warning).

    canonical_params is passed in by the caller so this module need not
    import driving_advisor.
    """
    try:
        # Find the JSON object in the response text (handle markdown fences)
        text = response_text.strip()
        if "```" in text:
            # Extract content between first ``` pair
            parts = text.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("{"):
                    text = stripped
                    break

        parsed = json.loads(text)

        # Strip any canonical setup fields from the parsed object
        stripped_fields: list[str] = []
        for field in list(parsed.keys()):
            if field in canonical_params:
                log.warning(
                    "AI audit response contained canonical setup field '%s' — stripped.", field
                )
                del parsed[field]
                stripped_fields.append(field)

        # Parse status
        raw_status = str(parsed.get("status", "")).upper().strip()
        status = _KNOWN_STATUSES.get(raw_status, AuditStatus.NEEDS_MORE_DATA)

        return AuditResult(
            status=status,
            warnings=list(parsed.get("warnings") or []),
            contradictions=list(parsed.get("contradictions") or []),
            missing_evidence=list(parsed.get("missing_evidence") or []),
            explanation_notes=str(parsed.get("explanation_notes") or ""),
            stripped_fields=stripped_fields,
        )

    except Exception as exc:
        log.warning("parse_audit_response failed: %s", exc)
        # The AI audit is advisory-only (Group 42) — it never authors changes. A
        # malformed/truncated audit response must degrade cleanly: surface an
        # honest, non-technical note rather than leaking the raw parser exception
        # (e.g. "Unterminated string at char 2178") into the driver-facing UI.
        return AuditResult(
            status=AuditStatus.NEEDS_MORE_DATA,
            warnings=[],
            contradictions=[],
            missing_evidence=[],
            explanation_notes=(
                "AI audit unavailable (the AI's review response was incomplete). "
                "This does not affect the rule-based setup changes above."
            ),
            stripped_fields=[],
        )


# ---------------------------------------------------------------------------
# Audit→finaliser mapping
# ---------------------------------------------------------------------------

def map_audit_to_finaliser(
    audit: AuditResult,
    has_blocking_validation: bool,
) -> "tuple[str, list[str]]":
    """Map audit result to a status_hint and extra_warnings for the finaliser.

    Returns (status_hint, extra_warnings).

    Blocking validation ALWAYS takes precedence — this function NEVER un-zeros
    changes zeroed by engineering validation.  The caller enforces this.

    Mapping
    -------
    REJECTED + no blocking         → ("approved_with_warnings", contradictions)
    NEEDS_MORE_DATA + no blocking  → ("approved_with_warnings", missing_evidence)
    APPROVED                       → ("approved", [])
    APPROVED_WITH_WARNINGS         → ("approved_with_warnings", warnings)
    """
    # Blocking validation dominates — hint is unused but make it safe
    if has_blocking_validation:
        # Return a neutral hint; the finaliser already zeroed changes
        warnings_out = list(audit.warnings) + list(audit.contradictions)
        return ("blocked_no_safe_recommendation", warnings_out)

    status = audit.status
    if status == AuditStatus.REJECTED:
        concerns = list(audit.contradictions) or list(audit.warnings) or ["AI audit: plan rejected."]
        return ("approved_with_warnings", concerns)

    if status == AuditStatus.NEEDS_MORE_DATA:
        missing = list(audit.missing_evidence)
        if not missing:
            # Nothing actionable from the audit (e.g. it couldn't be parsed, or it
            # had no specific gaps). The rule-based changes stand — don't raise a
            # warning banner over an advisory-only audit that stayed silent.
            return ("approved", [])
        return ("approved_with_warnings", missing)

    if status == AuditStatus.APPROVED_WITH_WARNINGS:
        return ("approved_with_warnings", list(audit.warnings))

    # APPROVED
    return ("approved", [])
