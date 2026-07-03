"""Setup AI Validation Gates — Gate 2: Telemetry sanity check.

Pure Python — no PyQt6, no ui/ imports.

Public API
----------
Constants: GEARBOX_CORRUPT_THRESHOLD, GEARBOX_DEGRADE_THRESHOLD
Functions:
  assess_telemetry_sanity(laps) -> SetupValidationResult
  build_telemetry_warning_block(result) -> str
  is_gearbox_corrupted(result) -> bool
  is_gearbox_degraded(result) -> bool
"""
from __future__ import annotations

from data.setup_validation_result import (
    SetupValidationIssue,
    SetupValidationResult,
    SetupValidationSeverity,
    make_validation_result,
)

# ---------------------------------------------------------------------------
# Named module constants (locked decision #2)
# ---------------------------------------------------------------------------

GEARBOX_CORRUPT_THRESHOLD: float = 1.10
"""achieved > 110 % of theoretical → CORRUPTED."""

GEARBOX_DEGRADE_THRESHOLD: float = 0.90
"""achieved < 90 % of theoretical → DEGRADED."""


# ---------------------------------------------------------------------------
# Internal gearbox state enum
# ---------------------------------------------------------------------------


class _GearboxState:
    OK = "ok"
    DEGRADED = "degraded"
    CORRUPTED = "corrupted"


def _worse_state(a: str, b: str) -> str:
    """Return the more severe of two gearbox states."""
    _rank = {_GearboxState.OK: 0, _GearboxState.DEGRADED: 1, _GearboxState.CORRUPTED: 2}
    return a if _rank.get(a, 0) >= _rank.get(b, 0) else b


# ---------------------------------------------------------------------------
# Helpers to read lap attributes from either objects or dicts
# ---------------------------------------------------------------------------


def _lap_get(lap: object, key: str, default=None):
    """Safely read a lap attribute that may be an object or a dict."""
    try:
        if isinstance(lap, dict):
            return lap.get(key, default)
        return getattr(lap, key, default)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Helper predicates (exported so wiring code and output validator can use them)
# ---------------------------------------------------------------------------


def is_gearbox_corrupted(result: SetupValidationResult) -> bool:
    """Return True when *result* contains a finding with code 'gearbox_corrupted'."""
    return any(f.code == "gearbox_corrupted" for f in result.findings)


def is_gearbox_degraded(result: SetupValidationResult) -> bool:
    """Return True when *result* contains a finding with code 'gearbox_degraded'."""
    return any(f.code == "gearbox_degraded" for f in result.findings)


# ---------------------------------------------------------------------------
# Gate 2: assess_telemetry_sanity
# ---------------------------------------------------------------------------


def assess_telemetry_sanity(laps: list) -> SetupValidationResult:
    """Validate telemetry data from recent laps for known corruption patterns.

    AC4 — Gearbox sanity: compares achieved max speed to theoretical max speed.
    AC5 — Road distance: checks for negative road_distance values in lap frames.

    Never raises. All risky arithmetic wrapped in try/except; errors become
    WARNING findings with code 'gearbox_sanity_error'.

    Parameters
    ----------
    laps:
        List of LapStats objects (or dicts). May be empty.

    Returns
    -------
    SetupValidationResult — findings include gearbox and road-distance issues.
    """
    findings: list[SetupValidationIssue] = []
    telemetry_lines: list[str] = []

    if not laps:
        return make_validation_result(
            [],
            overall_summary="No lap telemetry available for sanity check.",
            telemetry_assessment="No laps provided.",
        )

    # ----------------------------------------------------------------
    # AC4 — Gearbox sanity across all laps; take worst case
    # ----------------------------------------------------------------
    worst_state = _GearboxState.OK
    worst_achieved: float | None = None
    worst_theoretical: float | None = None
    worst_ratio: float | None = None

    for lap in laps:
        try:
            achieved = _lap_get(lap, "max_speed_kmh", None)
            theoretical = _lap_get(lap, "car_max_speed_theoretical_kmh", None)

            # Coerce to float
            if achieved is not None:
                try:
                    achieved = float(achieved)
                except (TypeError, ValueError):
                    achieved = None

            if theoretical is not None:
                try:
                    theoretical = float(theoretical)
                except (TypeError, ValueError):
                    theoretical = None

            # Classify this lap's gearbox state
            if theoretical is None or theoretical <= 0:
                lap_state = _GearboxState.DEGRADED
                ratio = None
            else:
                ratio = achieved / theoretical if achieved is not None else None
                if ratio is None:
                    lap_state = _GearboxState.DEGRADED
                elif ratio > GEARBOX_CORRUPT_THRESHOLD:
                    lap_state = _GearboxState.CORRUPTED
                elif ratio < GEARBOX_DEGRADE_THRESHOLD:
                    lap_state = _GearboxState.DEGRADED
                else:
                    lap_state = _GearboxState.OK

            prev_worst = worst_state
            worst_state = _worse_state(worst_state, lap_state)

            # Track the details from the lap that bumped the worst state
            if worst_state != prev_worst or (
                worst_state == lap_state == _GearboxState.CORRUPTED
                and ratio is not None
                and (worst_ratio is None or ratio > worst_ratio)
            ):
                worst_achieved = achieved
                worst_theoretical = theoretical
                worst_ratio = ratio

        except Exception:
            findings.append(
                SetupValidationIssue(
                    severity=SetupValidationSeverity.WARNING,
                    code="gearbox_sanity_error",
                    message=(
                        "Error reading gearbox telemetry from lap — "
                        "skipping this lap for gearbox sanity check."
                    ),
                )
            )

    # Emit gearbox finding based on worst case
    if worst_state == _GearboxState.CORRUPTED:
        pct = (worst_ratio * 100) if worst_ratio is not None else 0.0
        t_str = f"{worst_theoretical:.0f}" if worst_theoretical is not None else "N/A"
        a_str = f"{worst_achieved:.0f}" if worst_achieved is not None else "N/A"
        msg = (
            f"Gearbox telemetry appears CORRUPTED: theoretical max {t_str} km/h is "
            f"impossible against achieved {a_str} km/h "
            f"({pct:.0f}% of maximum — exceeds {GEARBOX_CORRUPT_THRESHOLD*100:.0f}% threshold). "
            f"Speed data is unreliable; gearbox changes must be suppressed."
        )
        findings.append(
            SetupValidationIssue(
                severity=SetupValidationSeverity.WARNING,
                code="gearbox_corrupted",
                message=msg,
            )
        )
        telemetry_lines.append(
            f"CORRUPTED gearbox telemetry detected "
            f"(achieved {a_str} km/h vs theoretical {t_str} km/h)."
        )

    elif worst_state == _GearboxState.DEGRADED:
        t_str = f"{worst_theoretical:.0f}" if worst_theoretical is not None else "N/A"
        a_str = f"{worst_achieved:.0f}" if worst_achieved is not None else "N/A"
        findings.append(
            SetupValidationIssue(
                severity=SetupValidationSeverity.WARNING,
                code="gearbox_degraded",
                message=(
                    f"Gearbox telemetry reliability is LOW: theoretical max {t_str} km/h, "
                    f"achieved {a_str} km/h "
                    f"(below {GEARBOX_DEGRADE_THRESHOLD*100:.0f}% threshold or theoretical unavailable). "
                    f"Avoid strong gearbox changes from this data."
                ),
            )
        )
        telemetry_lines.append(
            f"Degraded gearbox telemetry "
            f"(achieved {a_str} km/h vs theoretical {t_str} km/h)."
        )

    # ----------------------------------------------------------------
    # AC5 — Road distance sanity
    # ----------------------------------------------------------------
    for lap in laps:
        try:
            frames = _lap_get(lap, "frames", None)
            if frames is None:
                continue
            for frame in frames:
                try:
                    rd = getattr(frame, "road_distance", None)
                    if rd is not None and float(rd) < 0:
                        findings.append(
                            SetupValidationIssue(
                                severity=SetupValidationSeverity.WARNING,
                                code="road_distance_negative",
                                message=(
                                    f"Negative road_distance ({float(rd):.2f}) detected in lap frames — "
                                    f"telemetry may contain out-of-order or corrupt frame data."
                                ),
                            )
                        )
                        break  # One finding per lap is enough
                except Exception:
                    pass
        except Exception:
            pass

    telemetry_assessment = (
        "; ".join(telemetry_lines)
        if telemetry_lines
        else f"Telemetry sanity check passed ({len(laps)} lap(s) examined)."
    )

    return make_validation_result(
        findings,
        overall_summary=(
            "Telemetry sanity issues detected."
            if findings
            else "Telemetry sanity check passed."
        ),
        telemetry_assessment=telemetry_assessment,
    )


# ---------------------------------------------------------------------------
# Prompt injection helper
# ---------------------------------------------------------------------------


def build_telemetry_warning_block(result: SetupValidationResult) -> str:
    """Return a markdown warning block to inject into the AI prompt.

    Rules
    -----
    - CORRUPTED gearbox → strong "PRESERVE gearbox, make NO gearbox changes" instruction.
    - DEGRADED gearbox → lighter caution block.
    - Neither → empty string.
    """
    if is_gearbox_corrupted(result):
        return (
            "\n\n## Telemetry Warning\n"
            "Gearbox telemetry is UNRELIABLE — the recorded speed data exceeds the "
            "theoretical maximum and is therefore CORRUPTED.\n\n"
            "**MANDATORY INSTRUCTION — PRESERVE GEARBOX:**\n"
            "Do NOT change transmission_max_speed_kmh, final_drive, or gear_ratios. "
            "The gearbox telemetry cannot be trusted; any gearbox recommendation would be "
            "based on corrupt data. Preserve the current gearbox exactly as-is unless a "
            "manual engineering review is explicitly requested by the engineer.\n"
        )

    if is_gearbox_degraded(result):
        return (
            "\n\n## Telemetry Warning\n"
            "Gearbox telemetry reliability is LOW — achieved top speed is significantly "
            "below the theoretical maximum, or theoretical maximum data is unavailable.\n"
            "Do not make strong gearbox changes (transmission_max_speed_kmh, final_drive, "
            "gear_ratios) based solely on this data.\n"
        )

    return ""
