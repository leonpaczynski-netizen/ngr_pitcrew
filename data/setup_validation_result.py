"""Setup AI Validation Gates — shared result types.

Pure Python — no PyQt6, no strategy/, no ui/ imports at module level.

Public API
----------
Enums: SetupValidationStatus, SetupValidationSeverity, RecommendedAction
Dataclasses: SetupValidationIssue, SetupValidationResult
Factories: make_validation_result, merge_results
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SetupValidationStatus(str, Enum):
    PASS = "pass"
    PASS_WITH_WARNINGS = "pass_with_warnings"
    FAIL = "fail"


class SetupValidationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class RecommendedAction(str, Enum):
    USE_SETUP = "use_setup"
    USE_WITH_CAUTION = "use_with_caution"
    REGENERATE_SETUP = "regenerate_setup"
    FIX_PROMPT_THEN_REGENERATE = "fix_prompt_then_regenerate"
    MANUAL_ENGINEER_REVIEW_REQUIRED = "manual_engineer_review_required"


# ---------------------------------------------------------------------------
# Issue dataclass
# ---------------------------------------------------------------------------


@dataclass
class SetupValidationIssue:
    """A single validation finding."""

    severity: SetupValidationSeverity
    code: str
    message: str
    field: str | None = None


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class SetupValidationResult:
    """Aggregated result of one validation gate."""

    validation_status: SetupValidationStatus
    safe_to_show_driver: bool
    safe_to_apply_in_gt7: bool
    overall_summary: str
    findings: list[SetupValidationIssue] = field(default_factory=list)
    recommended_action: RecommendedAction = RecommendedAction.USE_SETUP
    field_validation: dict[str, dict] = field(default_factory=dict)
    driver_style_assessment: str = ""
    telemetry_assessment: str = ""
    track_context_assessment: str = ""
    minimum_required_prompt_fixes_before_regeneration: list[str] = field(
        default_factory=list
    )

    @property
    def blockers(self) -> list[str]:
        """Messages of all BLOCKER findings."""
        return [
            f.message
            for f in self.findings
            if f.severity == SetupValidationSeverity.BLOCKER
        ]

    @property
    def warnings(self) -> list[str]:
        """Messages of all WARNING findings."""
        return [
            f.message
            for f in self.findings
            if f.severity == SetupValidationSeverity.WARNING
        ]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict suitable for embedding in the API response."""
        return {
            "validation_status": self.validation_status.value,
            "safe_to_show_driver": self.safe_to_show_driver,
            "safe_to_apply_in_gt7": self.safe_to_apply_in_gt7,
            "overall_summary": self.overall_summary,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "field_validation": self.field_validation,
            "driver_style_assessment": self.driver_style_assessment,
            "telemetry_assessment": self.telemetry_assessment,
            "track_context_assessment": self.track_context_assessment,
            "recommended_action": self.recommended_action.value,
            "minimum_required_prompt_fixes_before_regeneration": (
                self.minimum_required_prompt_fixes_before_regeneration
            ),
        }


# ---------------------------------------------------------------------------
# Prompt/context/track code prefixes that indicate a prompt-fix is needed
# ---------------------------------------------------------------------------

_PROMPT_FIX_CODE_PREFIXES = {
    "track_mismatch",
    "layout_mismatch",
    "car_mismatch",
    "track_model_not_ready",
}


def _needs_prompt_fix(findings: list[SetupValidationIssue]) -> bool:
    """Return True when any BLOCKER finding has a prompt/context code prefix."""
    for f in findings:
        if f.severity == SetupValidationSeverity.BLOCKER:
            for prefix in _PROMPT_FIX_CODE_PREFIXES:
                if f.code.startswith(prefix):
                    return True
    return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_validation_result(
    findings: list[SetupValidationIssue],
    recommended_action: RecommendedAction | None = None,
    overall_summary: str = "",
    **assessment_kwargs: str,
) -> SetupValidationResult:
    """Build a SetupValidationResult from a flat list of findings.

    Parameters
    ----------
    findings:
        All SetupValidationIssue objects from this gate.
    recommended_action:
        Override auto-selection when supplied.  When None, derived from status.
    overall_summary:
        Human-readable summary string.
    **assessment_kwargs:
        Named assessment strings:
        - driver_style_assessment
        - telemetry_assessment
        - track_context_assessment

    Status derivation
    -----------------
    - FAIL if any BLOCKER.
    - PASS_WITH_WARNINGS if any WARNING or INFO but no BLOCKER.
    - PASS otherwise.

    Safe_to_show_driver = (status != FAIL).
    Safe_to_apply_in_gt7 = (no BLOCKER present).
    """
    has_blocker = any(
        f.severity == SetupValidationSeverity.BLOCKER for f in findings
    )
    has_warning_or_info = any(
        f.severity in (SetupValidationSeverity.WARNING, SetupValidationSeverity.INFO)
        for f in findings
    )

    if has_blocker:
        status = SetupValidationStatus.FAIL
    elif has_warning_or_info:
        status = SetupValidationStatus.PASS_WITH_WARNINGS
    else:
        status = SetupValidationStatus.PASS

    safe_to_show = status != SetupValidationStatus.FAIL
    safe_to_apply = not has_blocker

    # Auto recommended_action
    if recommended_action is None:
        if status == SetupValidationStatus.FAIL:
            if _needs_prompt_fix(findings):
                recommended_action = RecommendedAction.FIX_PROMPT_THEN_REGENERATE
            else:
                recommended_action = RecommendedAction.REGENERATE_SETUP
        elif status == SetupValidationStatus.PASS_WITH_WARNINGS:
            recommended_action = RecommendedAction.USE_WITH_CAUTION
        else:
            recommended_action = RecommendedAction.USE_SETUP

    return SetupValidationResult(
        validation_status=status,
        safe_to_show_driver=safe_to_show,
        safe_to_apply_in_gt7=safe_to_apply,
        overall_summary=overall_summary,
        findings=list(findings),
        recommended_action=recommended_action,
        driver_style_assessment=assessment_kwargs.get("driver_style_assessment", ""),
        telemetry_assessment=assessment_kwargs.get("telemetry_assessment", ""),
        track_context_assessment=assessment_kwargs.get("track_context_assessment", ""),
    )


# ---------------------------------------------------------------------------
# Merge helper
# ---------------------------------------------------------------------------


def merge_results(*results: SetupValidationResult) -> SetupValidationResult:
    """Merge multiple gate results into one by concatenating findings.

    Status is re-derived from the combined finding list.
    Assessment strings are taken from the first non-empty result for each key.
    recommended_action is auto-derived from the merged findings (never overridden).
    field_validation dicts are shallow-merged (later gate wins on conflicts).
    minimum_required_prompt_fixes_before_regeneration lists are concatenated and deduped.
    """
    all_findings: list[SetupValidationIssue] = []
    merged_field_validation: dict[str, dict] = {}
    merged_driver_style = ""
    merged_telemetry = ""
    merged_track_context = ""
    merged_prompt_fixes: list[str] = []
    seen_prompt_fixes: set[str] = set()

    for r in results:
        all_findings.extend(r.findings)
        merged_field_validation.update(r.field_validation)
        if not merged_driver_style and r.driver_style_assessment:
            merged_driver_style = r.driver_style_assessment
        if not merged_telemetry and r.telemetry_assessment:
            merged_telemetry = r.telemetry_assessment
        if not merged_track_context and r.track_context_assessment:
            merged_track_context = r.track_context_assessment
        for fix in r.minimum_required_prompt_fixes_before_regeneration:
            if fix not in seen_prompt_fixes:
                seen_prompt_fixes.add(fix)
                merged_prompt_fixes.append(fix)

    # Deduplicate findings by (code, field) — keep first occurrence
    seen_keys: set[tuple[str, str | None]] = set()
    deduped: list[SetupValidationIssue] = []
    for f in all_findings:
        key = (f.code, f.field)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(f)

    result = make_validation_result(
        deduped,
        overall_summary="",
        driver_style_assessment=merged_driver_style,
        telemetry_assessment=merged_telemetry,
        track_context_assessment=merged_track_context,
    )
    result.field_validation = merged_field_validation
    result.minimum_required_prompt_fixes_before_regeneration = merged_prompt_fixes
    return result
