"""Setup AI Validation Gates — Gate 1: Prompt / context pre-flight check.

Pure Python — no PyQt6, no network, no ui/ imports.

Public API
----------
validate_setup_prompt_context(event_ctx, track_location_id, layout_id, car_name,
                              track_model_result, track_truth_result)
    -> SetupValidationResult
"""
from __future__ import annotations

from data.setup_validation_result import (
    RecommendedAction,
    SetupValidationIssue,
    SetupValidationSeverity,
    make_validation_result,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norm(s: object) -> str:
    """Lowercase + strip for case-insensitive identity comparison."""
    return str(s).strip().lower() if s else ""


def _resolution_status_str(track_model_result: object) -> str:
    """Return the resolution_status as a plain lower-case string."""
    try:
        rs = getattr(track_model_result, "resolution_status", None)
        if rs is None:
            return ""
        # Handle both Enum (has .value) and plain string
        return (rs.value if hasattr(rs, "value") else str(rs)).lower()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Main gate
# ---------------------------------------------------------------------------


def validate_setup_prompt_context(
    event_ctx: dict,
    track_location_id: str,
    layout_id: str,
    car_name: str,
    track_model_result: object = None,
    track_truth_result: object = None,
) -> "SetupValidationResult":
    """Pre-flight validation of setup-request context before calling the AI.

    Checks
    ------
    AC1  Track identity — event_ctx track_location_id vs resolved track_location_id.
    AC1b Layout identity — event_ctx layout_id vs resolved layout_id (when both present).
    AC2  Car identity — event_ctx car_name vs car_name param.
    AC3  Track-model confidence — seed_only_fallback → WARNING; not_ai_ready / missing
         / error → BLOCKER.

    Never raises.

    Parameters
    ----------
    event_ctx:
        The event context dict stored on DrivingAdvisor._event_ctx.
    track_location_id:
        Resolved track location ID from the caller (authoritative).
    layout_id:
        Resolved layout ID from the caller (authoritative).
    car_name:
        Car name resolved by the caller (authoritative).
    track_model_result:
        Optional TrackModelResolverResult (data.track_model_resolver).
    track_truth_result:
        Optional result for corner-geometry guard (passed to
        data.track_truth.can_use_track_truth_for_ai_corner_context).

    Returns
    -------
    SetupValidationResult — FAIL if any BLOCKER, PASS_WITH_WARNINGS if warnings only.
    """
    findings: list[SetupValidationIssue] = []
    prompt_fixes: list[str] = []

    # ----------------------------------------------------------------
    # AC1 — track identity
    # ----------------------------------------------------------------
    ctx_track = _norm(event_ctx.get("track_location_id"))
    req_track = _norm(track_location_id)
    if ctx_track and req_track and ctx_track != req_track:
        findings.append(
            SetupValidationIssue(
                severity=SetupValidationSeverity.BLOCKER,
                code="track_mismatch",
                message=(
                    f"Setup request track does not match resolved track context. "
                    f"Requested '{track_location_id}' but resolved '{event_ctx.get('track_location_id')}'."
                ),
            )
        )
        prompt_fixes.append(
            f"Correct event track identity to match '{track_location_id}'"
        )

    # AC1b — layout identity
    ctx_layout = _norm(event_ctx.get("layout_id"))
    req_layout = _norm(layout_id)
    if ctx_layout and req_layout and ctx_layout != req_layout:
        findings.append(
            SetupValidationIssue(
                severity=SetupValidationSeverity.BLOCKER,
                code="layout_mismatch",
                message=(
                    f"Setup request layout does not match resolved layout context. "
                    f"Requested '{layout_id}' but resolved '{event_ctx.get('layout_id')}'."
                ),
            )
        )
        prompt_fixes.append(
            f"Correct event layout identity to match '{layout_id}'"
        )

    # ----------------------------------------------------------------
    # AC2 — car identity
    # ----------------------------------------------------------------
    ctx_car = _norm(event_ctx.get("car_name", ""))
    req_car = _norm(car_name)
    if ctx_car and req_car and ctx_car != req_car:
        findings.append(
            SetupValidationIssue(
                severity=SetupValidationSeverity.BLOCKER,
                code="car_mismatch",
                message=(
                    f"Setup request car does not match event context. "
                    f"Event has '{event_ctx.get('car_name')}' but car_name is '{car_name}'."
                ),
            )
        )
        prompt_fixes.append(
            f"Correct event car identity to match '{car_name}'"
        )

    # ----------------------------------------------------------------
    # AC3 — track-model confidence
    # ----------------------------------------------------------------
    resolution_str = _resolution_status_str(track_model_result)
    track_context_lines: list[str] = []

    if resolution_str:
        track_context_lines.append(f"Track model resolution status: {resolution_str}")

    if resolution_str in ("not_ai_ready", "missing", "error"):
        findings.append(
            SetupValidationIssue(
                severity=SetupValidationSeverity.BLOCKER,
                code="track_model_not_ready",
                message=(
                    f"Track model is not ready for AI setup generation "
                    f"(resolution_status='{resolution_str}'). "
                    f"A reviewed, AI-ready model is required."
                ),
            )
        )
        prompt_fixes.append(
            "Resolve track model to a reviewed/AI-ready state before generating a setup"
        )

    elif resolution_str == "seed_only_fallback":
        findings.append(
            SetupValidationIssue(
                severity=SetupValidationSeverity.WARNING,
                code="track_model_seed_only",
                message=(
                    "Track model is seed-only fallback. Setup generation will proceed "
                    "but corner-geometry-specific claims may be unreliable."
                ),
            )
        )
        track_context_lines.append(
            "Seed-only fallback active — corner geometry suppressed."
        )

        # Optionally check track truth availability for corner context
        if track_truth_result is not None:
            try:
                from data.track_truth import can_use_track_truth_for_ai_corner_context

                if not can_use_track_truth_for_ai_corner_context(track_truth_result):
                    findings.append(
                        SetupValidationIssue(
                            severity=SetupValidationSeverity.INFO,
                            code="corner_geometry_suppressed",
                            message=(
                                "Corner geometry context is suppressed: "
                                "track truth model is not accepted for AI corner context."
                            ),
                        )
                    )
            except Exception:
                pass  # Never raise — degrade silently

    # Build track context assessment
    track_context_assessment = "; ".join(track_context_lines) if track_context_lines else ""

    result = make_validation_result(
        findings,
        recommended_action=(
            RecommendedAction.FIX_PROMPT_THEN_REGENERATE
            if any(
                f.severity == SetupValidationSeverity.BLOCKER for f in findings
            )
            else None
        ),
        overall_summary=(
            "Prompt/context validation failed — correct the issues before generating a setup."
            if any(f.severity == SetupValidationSeverity.BLOCKER for f in findings)
            else (
                "Prompt/context validation passed with warnings."
                if findings
                else "Prompt/context validation passed."
            )
        ),
        track_context_assessment=track_context_assessment,
    )
    result.minimum_required_prompt_fixes_before_regeneration = prompt_fixes
    return result
