"""Setup plan translator — Group 42: Rule-First Setup Brain.

Converts a SetupPlan (rule-engine output) into the raw_data dict shape that
_finalise_recommendation and _normalise_changes expect.

Public API
----------
plan_to_raw_data(plan, diagnosis, analysis_text) -> dict
rejected_to_json(plan) -> list[dict]
"""
from __future__ import annotations

from strategy.setup_rule_engine import SetupPlan, SetupChangeIntent

# Fields that must never appear in setup_fields (display-only).
# Mirrors _DISPLAY_ONLY_FIELDS in driving_advisor but redefined here so this
# module does not import driving_advisor (no cycle).
_DISPLAY_ONLY = frozenset({"transmission_max_speed_kmh"})


def plan_to_raw_data(
    plan: SetupPlan,
    diagnosis: dict,
    analysis_text: str,
) -> dict:
    """Convert a SetupPlan into the raw_data dict shape expected by _finalise_recommendation.

    The returned dict has the same keys the AI response would have, plus
    explainability keys inside each change dict:
      setting, field, from, to, to_clamped, why,
      symptom, evidence, rule_id, rationale, rejected_alternatives,
      risk_level, confidence_level, driver_style_alignment.

    setup_fields contains {field: to_value} for proposed changes (display-only
    fields are excluded so they never reach _finalise_recommendation's approval).

    diagnosis is passed through so downstream validators and the finaliser can
    access it.
    """
    changes: list[dict] = []
    setup_fields: dict = {}

    for intent in plan.proposed:
        field = intent.field
        from_val = intent.from_value
        to_val = intent.to_value

        # Build the change dict in AI-response shape
        change: dict = {
            "setting": field.replace("_", " ").title(),
            "field": field,
            "from": str(from_val) if from_val is not None else "",
            "to": str(to_val) if to_val is not None else "",
            # to_clamped: use to_value (already clamped by the engine)
            "to_clamped": to_val,
            "why": intent.rationale,
            # Explainability keys
            "symptom": intent.symptom,
            "evidence": list(intent.evidence),
            "rule_id": intent.rule_id,
            "rationale": intent.rationale,
            "rejected_alternatives": list(intent.rejected_alternatives),
            "risk_level": intent.risk.value if hasattr(intent.risk, "value") else str(intent.risk),
            "confidence_level": (
                intent.confidence.value if hasattr(intent.confidence, "value") else str(intent.confidence)
            ),
            "driver_style_alignment": (
                intent.driver_style_alignment.value
                if hasattr(intent.driver_style_alignment, "value")
                else str(intent.driver_style_alignment)
            ),
        }
        changes.append(change)

        # Populate setup_fields (excluding display-only)
        if field not in _DISPLAY_ONLY and to_val is not None:
            try:
                setup_fields[field] = float(to_val)
            except (TypeError, ValueError):
                setup_fields[field] = to_val

    # primary_issue: derive from diagnosis
    primary_issue = diagnosis.get("dominant_problem", "")
    if not primary_issue:
        secondary = diagnosis.get("secondary_problems") or []
        primary_issue = secondary[0] if secondary else "unknown"

    return {
        "analysis": analysis_text,
        "primary_issue": primary_issue,
        "changes": changes,
        "setup_fields": setup_fields,
        "diagnosis": diagnosis,
    }


def rejected_to_json(plan: SetupPlan) -> list[dict]:
    """Format plan.rejected_candidates for the rejected_changes response key.

    Each item includes: field, rule_id, reason, risk_level, confidence_level,
    symptom, driver_style_alignment.
    """
    result: list[dict] = []
    for intent in plan.rejected_candidates:
        result.append({
            "field": intent.field,
            "rule_id": intent.rule_id,
            "reason": intent.rationale,
            "symptom": intent.symptom,
            "risk_level": (
                intent.risk.value if hasattr(intent.risk, "value") else str(intent.risk)
            ),
            "confidence_level": (
                intent.confidence.value
                if hasattr(intent.confidence, "value")
                else str(intent.confidence)
            ),
            "driver_style_alignment": (
                intent.driver_style_alignment.value
                if hasattr(intent.driver_style_alignment, "value")
                else str(intent.driver_style_alignment)
            ),
        })
    return result
