"""Setup AI Validation Gates — Gate 3: Post-AI output validation.

Pure Python — no PyQt6, no ui/ imports.

Public API
----------
validate_setup_output(parsed_ai, effective_ranges, diagnosis, locked_fields,
                      event_ctx, current_setup, car_name, telemetry_result)
    -> SetupValidationResult
"""
from __future__ import annotations

from data.setup_validation_result import (
    RecommendedAction,
    SetupValidationIssue,
    SetupValidationResult,
    SetupValidationSeverity,
    make_validation_result,
)
from data.setup_telemetry_validation import is_gearbox_corrupted

# ---------------------------------------------------------------------------
# Required top-level output fields (AC6)
# ---------------------------------------------------------------------------

_REQUIRED_OUTPUT_FIELDS: frozenset[str] = frozenset({
    "ride_height_front",
    "ride_height_rear",
    "springs_front",
    "springs_rear",
    "dampers_front_comp",
    "dampers_front_ext",
    "dampers_rear_comp",
    "dampers_rear_ext",
    "arb_front",
    "arb_rear",
    "camber_front",
    "camber_rear",
    "toe_front",
    "toe_rear",
    "aero_front",
    "aero_rear",
    "lsd_initial",
    "lsd_accel",
    "lsd_decel",
    "brake_bias",
    "ballast_kg",
    "ballast_position",
    "power_restrictor",
    "ecu_recommendation",
    "shift_rpm_qual",
    "shift_rpm_race",
    "final_drive",
    "transmission_max_speed_kmh",
    "gear_ratios",
    "reasoning",
})

# Gearbox fields examined for corruption check (locked decision #3)
_GEARBOX_FIELDS = ("transmission_max_speed_kmh", "final_drive", "gear_ratios")

# Severity mapping for engineering-validation reason prefixes
_ENG_PREFIX_SEVERITY: dict[str, SetupValidationSeverity] = {
    "rh_for_minor_bottoming":    SetupValidationSeverity.BLOCKER,
    "aero_at_min_floaty":        SetupValidationSeverity.BLOCKER,
    "aero_cut_with_wheelspin":   SetupValidationSeverity.BLOCKER,
    "malformed_schema":          SetupValidationSeverity.BLOCKER,
    "gearbox_edit_when_preserve": SetupValidationSeverity.WARNING,
    "invalid_units":             SetupValidationSeverity.WARNING,
    "rh_low_confidence_location": SetupValidationSeverity.WARNING,
}


# ---------------------------------------------------------------------------
# Private helper — driver hard constraints (AC8)
# ---------------------------------------------------------------------------


def _check_driver_hard_constraints(
    parsed_ai: dict,
    effective_ranges: dict[str, tuple],
    diagnosis: dict,
    locked_fields: set[str] | None,
) -> list[SetupValidationIssue]:
    """Check driver hard constraints and return any BLOCKER findings."""
    issues: list[SetupValidationIssue] = []
    locked = locked_fields or set()

    # Setup fields — prefer setup_fields sub-dict if present
    sf = parsed_ai.get("setup_fields", parsed_ai)

    def _ai_val(key: str) -> float | None:
        """Return the AI's numeric value for key, or None."""
        v = sf.get(key)
        if v is None:
            # Fall back to changes[]
            for ch in (parsed_ai.get("changes") or []):
                if ch.get("field") == key:
                    tc = ch.get("to_clamped")
                    if tc is not None:
                        try:
                            return float(tc)
                        except (TypeError, ValueError):
                            pass
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    # ----------------------------------------------------------------
    # Constraint: no floaty front
    # ----------------------------------------------------------------
    if "aero_front" not in locked:
        feel_flags = diagnosis.get("driver_feel_flags") or {}
        floaty_front = feel_flags.get("floaty_front", False)
        aero_front_near_min = diagnosis.get("aero_front_near_min", False)

        if floaty_front or aero_front_near_min:
            ai_af = _ai_val("aero_front")
            if ai_af is not None:
                _af_range = effective_ranges.get("aero_front")
                if _af_range is not None:
                    try:
                        lo = float(_af_range[0])
                        hi = float(_af_range[1])
                        span = hi - lo
                        near_min_threshold = lo + 0.10 * span if span > 0 else lo
                        if ai_af <= near_min_threshold:
                            issues.append(
                                SetupValidationIssue(
                                    severity=SetupValidationSeverity.BLOCKER,
                                    code="driver_constraint_no_floaty_front",
                                    field="aero_front",
                                    message=(
                                        f"Driver constraint violated: aero_front={ai_af} is at/below "
                                        f"near-minimum threshold ({near_min_threshold:.1f}) "
                                        f"while floaty_front flag is active or aero_front is near-min. "
                                        f"Front downforce must not be reduced when the driver reports "
                                        f"front instability or float."
                                    ),
                                )
                            )
                    except Exception:
                        pass

    # ----------------------------------------------------------------
    # Constraint: no rear aero reduction with meaningful wheelspin
    # ----------------------------------------------------------------
    if "aero_rear" not in locked:
        wheelspin_band = diagnosis.get("wheelspin_band", "low")
        if wheelspin_band in ("meaningful", "major", "severe"):
            ai_ar = _ai_val("aero_rear")
            if ai_ar is not None:
                # Compare to effective range min to detect a relative reduction
                # We need the current setup value from the diagnosis context.
                # The diagnosis contains aero_rear_value which is the current setup value.
                cur_ar = diagnosis.get("aero_rear_value")
                if cur_ar is not None:
                    try:
                        if float(ai_ar) < float(cur_ar):
                            issues.append(
                                SetupValidationIssue(
                                    severity=SetupValidationSeverity.BLOCKER,
                                    code="driver_constraint_rear_aero_removed",
                                    field="aero_rear",
                                    message=(
                                        f"Driver constraint violated: aero_rear reduced "
                                        f"({cur_ar} → {ai_ar}) while wheelspin band is "
                                        f"'{wheelspin_band}'. Removing rear downforce worsens "
                                        f"traction instability."
                                    ),
                                )
                            )
                    except Exception:
                        pass

    return issues


# ---------------------------------------------------------------------------
# Main gate
# ---------------------------------------------------------------------------


def validate_setup_output(
    parsed_ai: dict,
    effective_ranges: dict[str, tuple],
    diagnosis: dict,
    locked_fields: set[str] | None,
    event_ctx: dict,
    current_setup: dict | None = None,
    car_name: str = "",
    telemetry_result: SetupValidationResult | None = None,
) -> SetupValidationResult:
    """Post-AI output validation gate.

    Checks
    ------
    AC6  Schema completeness — required top-level fields present.
    AC7  Effective-range compliance — numeric fields within (min, max).
    AC8  Driver hard constraints — floaty front / rear aero / wheelspin.
    AC9  Ride-height proof — top-10% height without bottoming evidence.
    Gearbox consistency (locked decision #3) — no changes on corrupt telemetry.
    Engineering rules — reuse validate_setup_engineering from setup_diagnosis.

    Never raises.

    Parameters
    ----------
    parsed_ai:
        Parsed (normalised) AI response dict.
    effective_ranges:
        {field: (min, max)} — from resolve_effective_ranges.
    diagnosis:
        build_setup_diagnosis result dict.
    locked_fields:
        Fields locked by event rules (not checked for range/schema violations).
        Pass None for no locked fields.
    event_ctx:
        Event context dict.
    current_setup:
        Current car setup dict (for gearbox comparison).
    car_name:
        Car name string.
    telemetry_result:
        Result from assess_telemetry_sanity (for gearbox corruption check).

    Returns
    -------
    SetupValidationResult
    """
    findings: list[SetupValidationIssue] = []
    field_validation: dict[str, dict] = {}
    locked = locked_fields or set()
    setup = current_setup or {}

    # ----------------------------------------------------------------
    # AC6 — Schema completeness
    # ----------------------------------------------------------------
    present_keys = set(parsed_ai.keys())
    missing_fields = _REQUIRED_OUTPUT_FIELDS - present_keys
    for name in sorted(missing_fields):
        findings.append(
            SetupValidationIssue(
                severity=SetupValidationSeverity.BLOCKER,
                code="missing_output_field",
                field=name,
                message=f"Required output field '{name}' is missing from the AI response.",
            )
        )
        field_validation[name] = {"status": "missing", "reason": "Field absent from AI response."}

    # ----------------------------------------------------------------
    # AC7 — Effective range compliance
    # ----------------------------------------------------------------
    # Numeric setup fields live in setup_fields sub-dict if present, else top-level
    sf = parsed_ai.get("setup_fields", parsed_ai)

    for field_name, range_tuple in effective_ranges.items():
        if field_name in locked:
            continue
        if field_name not in sf:
            continue
        raw_val = sf[field_name]
        try:
            val = float(raw_val)
        except (TypeError, ValueError):
            # Non-numeric value for a ranged field
            field_validation[field_name] = {
                "status": "not_numeric",
                "reason": f"Value '{raw_val}' is not numeric.",
            }
            findings.append(
                SetupValidationIssue(
                    severity=SetupValidationSeverity.INFO,
                    code="field_not_numeric",
                    field=field_name,
                    message=(
                        f"Field '{field_name}' has non-numeric value '{raw_val}'. "
                        f"Expected a number in range {range_tuple}."
                    ),
                )
            )
            continue

        try:
            lo = float(range_tuple[0])
            hi = float(range_tuple[1])
        except (TypeError, ValueError, IndexError):
            continue

        if val < lo or val > hi:
            # AC7 aero-zero rule: aero at exactly 0 when effective min > 0 → BLOCKER
            field_validation[field_name] = {
                "status": "out_of_range",
                "reason": f"Value {val} is outside effective range ({lo}, {hi}).",
            }
            findings.append(
                SetupValidationIssue(
                    severity=SetupValidationSeverity.BLOCKER,
                    code="field_out_of_range",
                    field=field_name,
                    message=(
                        f"Field '{field_name}' value {val} is outside effective range "
                        f"({lo}, {hi})."
                    ),
                )
            )
        else:
            field_validation[field_name] = {
                "status": "ok",
                "reason": f"Value {val} is within range ({lo}, {hi}).",
            }

    # ----------------------------------------------------------------
    # AC8 — Driver hard constraints
    # ----------------------------------------------------------------
    driver_issues = _check_driver_hard_constraints(
        parsed_ai, effective_ranges, diagnosis, locked_fields
    )
    findings.extend(driver_issues)

    # ----------------------------------------------------------------
    # AC9 — Ride-height proof
    # ----------------------------------------------------------------
    bottoming_band = diagnosis.get("bottoming_band", "minor")
    for rh_key in ("ride_height_front", "ride_height_rear"):
        if rh_key in locked:
            continue
        rh_range = effective_ranges.get(rh_key)
        if rh_range is None:
            continue
        rh_val_raw = sf.get(rh_key)
        if rh_val_raw is None:
            continue
        try:
            rh_val = float(rh_val_raw)
            lo = float(rh_range[0])
            hi = float(rh_range[1])
            span = hi - lo
            if span <= 0:
                continue
            top_10pct_threshold = lo + 0.90 * span
            if rh_val >= top_10pct_threshold and bottoming_band not in ("consider", "required"):
                findings.append(
                    SetupValidationIssue(
                        severity=SetupValidationSeverity.BLOCKER,
                        code="ride_height_without_proof",
                        field=rh_key,
                        message=(
                            f"'{rh_key}' is set to {rh_val} (top 10% of effective range "
                            f"{lo}–{hi}) but bottoming band is '{bottoming_band}' — "
                            f"no evidence of severe bottoming to justify this height."
                        ),
                    )
                )
        except (TypeError, ValueError):
            pass

    # ----------------------------------------------------------------
    # Gearbox consistency (locked decision #3)
    # ----------------------------------------------------------------
    if telemetry_result is not None and is_gearbox_corrupted(telemetry_result):
        gearbox_changed = False
        changed_fields: list[str] = []

        for gb_key in _GEARBOX_FIELDS:
            # Check setup_fields for numeric gearbox keys
            ai_val = sf.get(gb_key)
            if ai_val is None:
                # Also check top-level parsed_ai for gear_ratios (may be list)
                ai_val = parsed_ai.get(gb_key)
            cur_val = setup.get(gb_key)

            if ai_val is None and cur_val is None:
                continue
            if ai_val is None or cur_val is None:
                # One is present and the other isn't → changed
                gearbox_changed = True
                changed_fields.append(gb_key)
                continue

            try:
                # For numeric fields, compare as float
                if float(ai_val) != float(cur_val):
                    gearbox_changed = True
                    changed_fields.append(gb_key)
            except (TypeError, ValueError):
                # Non-numeric (e.g. gear_ratios list) — compare as repr
                if str(ai_val) != str(cur_val):
                    gearbox_changed = True
                    changed_fields.append(gb_key)

        if gearbox_changed:
            findings.append(
                SetupValidationIssue(
                    severity=SetupValidationSeverity.BLOCKER,
                    code="gearbox_changed_on_corrupt_telemetry",
                    message=(
                        f"Gearbox field(s) changed ({', '.join(changed_fields)}) "
                        f"despite CORRUPTED gearbox telemetry. "
                        f"The AI must preserve the current gearbox when telemetry is corrupted."
                    ),
                )
            )
        else:
            # AI preserved gearbox — emit WARNING only (locked decision #3c)
            findings.append(
                SetupValidationIssue(
                    severity=SetupValidationSeverity.WARNING,
                    code="gearbox_corrupt_preserved",
                    message=(
                        "Gearbox telemetry is CORRUPTED but the AI correctly preserved "
                        "the current gearbox. The rest of the setup can proceed."
                    ),
                )
            )

    # ----------------------------------------------------------------
    # Engineering rules — reuse validate_setup_engineering (AC-reuse)
    # ----------------------------------------------------------------
    try:
        from strategy.setup_diagnosis import validate_setup_engineering  # lazy import

        eng_errors: list[str] = validate_setup_engineering(
            parsed_ai,
            diagnosis,
            setup,
            effective_ranges,
            event_ctx,
            car_name=car_name,
        )

        # Map each error string to a SetupValidationIssue
        seen_keys: set[tuple[str, str | None]] = {(f.code, f.field) for f in findings}
        for reason in eng_errors:
            # Extract prefix (text before first ":")
            if ":" in reason:
                code = reason.split(":", 1)[0].strip()
            else:
                code = "engineering_rule"
            severity = _ENG_PREFIX_SEVERITY.get(code, SetupValidationSeverity.WARNING)
            key = (code, None)
            if key not in seen_keys:
                seen_keys.add(key)
                findings.append(
                    SetupValidationIssue(
                        severity=severity,
                        code=code,
                        message=reason,
                    )
                )
    except Exception:
        pass  # Engineering validation must never break the output gate

    # ----------------------------------------------------------------
    # Build result
    # ----------------------------------------------------------------
    has_blockers = any(f.severity == SetupValidationSeverity.BLOCKER for f in findings)
    overall_summary = (
        "Output validation failed — setup has blockers that must be resolved."
        if has_blockers
        else (
            "Output validation passed with warnings."
            if findings
            else "Output validation passed."
        )
    )

    result = make_validation_result(
        findings,
        recommended_action=(
            RecommendedAction.REGENERATE_SETUP if has_blockers else None
        ),
        overall_summary=overall_summary,
    )
    result.field_validation = field_validation
    return result
