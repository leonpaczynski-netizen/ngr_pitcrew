"""Adaptive Per-Gear Shift Strategy — pure view model (Phase 1).

Turns a ShiftStrategyResult into display-ready data for the Garage tab.
PURE: no Qt import anywhere in this file — it must stay importable by the
test suite without a running Qt application.

DESIGN
  GearDecisionRow   — one row per gear pair; every display field is a
                      pre-formatted string so the widget is a dumb renderer.
  ShiftStrategyVM   — the full surface: rows + summary + stepper state +
                      banner + current engine data.

CONFIDENCE KEY → UI TONE mapping (the widget maps these keys to colours)
  HIGH                → success
  MEDIUM              → info
  LOW                 → warn
  PROVISIONAL         → advisory
  INSUFFICIENT_EVIDENCE → neutral  (displayed as "NEEDS DATA")
  STALE               → warn

BANNER PRECEDENCE  EMPTY > STALE > PROVISIONAL
  (EMPTY is the highest-priority override: nothing to show)

NEVER SHOWS BARE "0"
  A genuine zero delta is shown as "0 (no change)".  Missing / unavailable
  values show a next-action string, never a blank or a raw zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from strategy.shift_strategy_engine import ShiftConfidence, ShiftStrategyResult


# ---------------------------------------------------------------------------
# Confidence key → UI tone
# ---------------------------------------------------------------------------

_TONE_MAP: dict[str, str] = {
    ShiftConfidence.HIGH.value:                 "success",
    ShiftConfidence.MEDIUM.value:               "info",
    ShiftConfidence.LOW.value:                  "warn",
    ShiftConfidence.PROVISIONAL.value:          "advisory",
    ShiftConfidence.INSUFFICIENT_EVIDENCE.value: "neutral",
    ShiftConfidence.STALE.value:                "warn",
}

_CONF_DISPLAY: dict[str, str] = {
    ShiftConfidence.HIGH.value:                 "High",
    ShiftConfidence.MEDIUM.value:               "Medium",
    ShiftConfidence.LOW.value:                  "Low",
    ShiftConfidence.PROVISIONAL.value:          "Provisional",
    ShiftConfidence.INSUFFICIENT_EVIDENCE.value: "NEEDS DATA",
    ShiftConfidence.STALE.value:                "Stale",
}

_NEXT_ACTION_MISSING_ENGINE = (
    "Enter peak power RPM, peak torque RPM, and redline in the Shift Strategy panel"
)
_NEXT_ACTION_MISSING_RATIOS = (
    "Enter gear ratios in the Transmission sheet to enable shift strategy"
)


def confidence_tone(confidence_key: str) -> str:
    """Map a ShiftConfidence.value string to its UI tone name."""
    return _TONE_MAP.get(confidence_key, "neutral")


# ---------------------------------------------------------------------------
# GearDecisionRow
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GearDecisionRow:
    """Display data for one gear pair (e.g. gear 2 → gear 3).

    All fields are pre-formatted strings; the widget never decides blank vs value.
    ``has_data`` is False when the pair cannot be computed (below powerband, etc.)
    so the widget can style or dim the row without parsing the text.
    """

    label: str                  # e.g. "2 → 3"
    qualifying_rpm: str         # e.g. "7 400" or next-action text
    race_rpm: str               # e.g. "6 900" or "same as qualifying"
    rpm_delta: str              # e.g. "−500 rpm" or "0 (no change)"
    post_shift_rpm: str         # e.g. "5 100" or next-action text
    time_cost: str              # e.g. "+0.08 s/lap" or "—"
    fuel_saving: str            # e.g. "3.2 % (PROVISIONAL)" or "—"
    confidence_key: str         # ShiftConfidence.value string
    confidence_label: str       # human-readable label
    evidence_tone: str          # UI tone key
    has_data: bool              # True when the pair has a valid computed value


def _fmt_rpm(rpm: Optional[int]) -> str:
    if rpm is None:
        return _NEXT_ACTION_MISSING_ENGINE
    return f"{rpm:,}".replace(",", " ")  # narrow no-break space thousands sep


def _fmt_delta(delta: Optional[int]) -> str:
    """Never returns bare '0'."""
    if delta is None:
        return "—"
    if delta == 0:
        return "0 (no change)"
    sign = "−" if delta < 0 else "+"
    return f"{sign}{abs(delta):,}".replace(",", " ") + " rpm"


def _fmt_time_cost(tc: Optional[float]) -> str:
    if tc is None:
        return "—"
    if tc == 0.0:
        return "0 (no change)"
    return f"+{tc:.3f} s/lap"


def _fmt_fuel_saving(fs: Optional[float], provisional: bool) -> str:
    if fs is None:
        return "—"
    if fs == 0.0:
        return "0 (no change)"
    badge = " (PROVISIONAL)" if provisional else ""
    return f"{fs * 100:.1f}%{badge}"


def _row_from_decision(d) -> GearDecisionRow:
    """Build one GearDecisionRow from a PerGearShiftDecision."""
    conf_key = d.confidence.value if hasattr(d.confidence, "value") else str(d.confidence)
    tone = _TONE_MAP.get(conf_key, "neutral")
    conf_label = _CONF_DISPLAY.get(conf_key, conf_key)
    provisional = conf_key == ShiftConfidence.PROVISIONAL.value

    if not d.valid:
        return GearDecisionRow(
            label=f"{d.from_gear} → {d.to_gear}",
            qualifying_rpm=d.rationale or _NEXT_ACTION_MISSING_ENGINE,
            race_rpm="—",
            rpm_delta="—",
            post_shift_rpm=(
                _fmt_rpm(d.expected_post_shift_rpm)
                if d.expected_post_shift_rpm is not None
                else "—"
            ),
            time_cost="—",
            fuel_saving="—",
            confidence_key=conf_key,
            confidence_label=conf_label,
            evidence_tone=tone,
            has_data=False,
        )

    return GearDecisionRow(
        label=f"{d.from_gear} → {d.to_gear}",
        qualifying_rpm=_fmt_rpm(d.qualifying_target_rpm),
        race_rpm=_fmt_rpm(d.race_target_rpm),
        rpm_delta=_fmt_delta(d.rpm_delta_from_qualifying),
        post_shift_rpm=_fmt_rpm(d.expected_post_shift_rpm),
        time_cost=_fmt_time_cost(d.predicted_time_cost),
        fuel_saving=_fmt_fuel_saving(d.predicted_fuel_saving, provisional),
        confidence_key=conf_key,
        confidence_label=conf_label,
        evidence_tone=tone,
        has_data=True,
    )


# ---------------------------------------------------------------------------
# ShiftStrategyVM
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ShiftStrategyVM:
    """Full view model for the Shift Strategy surface in the Garage tab."""

    # Table rows (one per gear pair)
    rows: Tuple[GearDecisionRow, ...]

    # Summary fields
    active_profile: str             # "qualifying" or "race"
    required_saving_text: str       # e.g. "5.0%" or "None (qualifying mode)"
    predicted_saving_text: str      # e.g. "4.8% (PROVISIONAL)" or "—"
    time_cost_text: str             # e.g. "+0.32 s/lap" or "—"
    config_status_text: str         # e.g. "Up to date" or "Configuration changed"
    config_is_stale: bool
    stale_field_text: str           # explanation when stale

    # Confidence
    overall_confidence_key: str     # ShiftConfidence.value
    evidence_readiness_text: str    # human-readable summary

    # Stepper (4-stage workflow)
    stepper_stage: int              # 0=gear-ratios, 1=engine-data, 2=review, 3=done
    stepper_blocker_text: str       # why the stepper is stuck (empty when not stuck)
    stepper_go_to_tab: str          # tab name the "fix it" CTA navigates to

    # Banner
    banner_text: str
    banner_tone: str                # "warn" | "advisory" | "neutral" | ""

    # Engine data currently in use (for the data-entry fields)
    engine_peak_power_rpm: Optional[int]
    engine_peak_torque_rpm: Optional[int]
    engine_redline: Optional[int]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_shift_strategy_vm(
    result: Optional[ShiftStrategyResult],
    profile: str = "qualifying",
    stored_fingerprint: Optional[str] = None,
    stale_field_text: str = "",
) -> ShiftStrategyVM:
    """Map a ShiftStrategyResult to a ShiftStrategyVM.

    ``result``             — None when no computation has been run yet.
    ``profile``            — "qualifying" or "race".
    ``stored_fingerprint`` — fingerprint of the last stored result; when it
                             differs from result.configuration_fingerprint the
                             result is stale.
    ``stale_field_text``   — caller-supplied description of exactly which field
                             changed (e.g. "Final drive changed (4.10 -> 3.90)").
                             When non-empty and the result is stale, this
                             overrides the generic fallback text.

    Never raises.
    """
    try:
        _profile = "race" if str(profile or "").lower() == "race" else "qualifying"

        # --- No result yet ---
        if result is None:
            return ShiftStrategyVM(
                rows=(),
                active_profile=_profile,
                required_saving_text="None (not computed)",
                predicted_saving_text=_NEXT_ACTION_MISSING_RATIOS,
                time_cost_text="—",
                config_status_text="Not computed",
                config_is_stale=False,
                stale_field_text="",
                overall_confidence_key=ShiftConfidence.INSUFFICIENT_EVIDENCE.value,
                evidence_readiness_text=_NEXT_ACTION_MISSING_RATIOS,
                stepper_stage=0,
                stepper_blocker_text=_NEXT_ACTION_MISSING_RATIOS,
                stepper_go_to_tab="Transmission",
                banner_text=_NEXT_ACTION_MISSING_RATIOS,
                banner_tone="neutral",
                engine_peak_power_rpm=None,
                engine_peak_torque_rpm=None,
                engine_redline=None,
            )

        # --- Staleness check ---
        is_stale = (
            stored_fingerprint is not None
            and stored_fingerprint != ""
            and stored_fingerprint != result.configuration_fingerprint
        )

        # --- Build rows from the active profile ---
        active_prof = (
            result.race_profile if _profile == "race" else result.qualifying_profile
        )
        rows: Tuple[GearDecisionRow, ...] = tuple(
            _row_from_decision(d) for d in active_prof.decisions
        )

        # --- Confidence ---
        overall_key = (
            result.overall_confidence.value
            if hasattr(result.overall_confidence, "value")
            else str(result.overall_confidence)
        )
        if is_stale:
            overall_key = ShiftConfidence.STALE.value

        # --- Summary texts ---
        req_pct = result.required_fuel_saving_pct
        if req_pct == 0.0:
            # FIX E: Phase 3 deferred — race == qualifying always in Phase 1.
            # Make this explicit so the panel reads honestly rather than looking
            # broken when Race targets equal qualifying targets.
            if _profile == "race":
                req_text = "Race targets match qualifying (short-shift activates in Phase 3)"
            else:
                req_text = "None (qualifying mode)"
        else:
            req_text = f"{req_pct:.1f}%"

        pred_pct = result.predicted_fuel_saving_pct
        is_provisional = overall_key == ShiftConfidence.PROVISIONAL.value
        if rows and all(not r.has_data for r in rows):
            pred_text = _NEXT_ACTION_MISSING_ENGINE
        elif pred_pct == 0.0:
            pred_text = "0 (no change)"
        else:
            badge = " (PROVISIONAL)" if is_provisional else ""
            pred_text = f"{pred_pct:.1f}%{badge}"

        tc = result.predicted_time_cost_per_lap
        if tc is None:
            time_cost_text = "—"
        elif tc == 0.0:
            time_cost_text = "0 (no change)"
        else:
            time_cost_text = f"+{tc:.3f} s/lap"

        # --- Config status + stale field text ---
        _GENERIC_STALE = (
            "The gear ratios or engine data have changed since the last "
            "computation. Recompute to get up-to-date shift targets."
        )
        if is_stale:
            config_status_text = "Configuration changed — recompute to update"
            # FIX A.3: use caller-supplied specific text when available;
            # fall back to the generic description only when nothing was given.
            resolved_stale_text = (
                str(stale_field_text).strip() if stale_field_text else _GENERIC_STALE
            )
        else:
            config_status_text = "Up to date"
            resolved_stale_text = ""

        # --- Evidence readiness ---
        missing = result.missing_evidence
        if missing:
            evidence_text = missing[0]  # show the first next-action
        else:
            evidence_text = result.evidence_summary

        # --- Stepper stage ---
        # Use the public structured fields on the result rather than inspecting
        # decisions (which are empty for ANY insufficient result) or parsing
        # missing_evidence text (fragile).  gear_ratio_count >= 2 means the
        # driver has entered at least two ratios — a prerequisite for the engine
        # to produce decisions.  engine_peak_power_rpm being non-None means all
        # required engine data was supplied.
        has_ratios = getattr(result, "gear_ratio_count", 0) >= 2
        has_engine_data = getattr(result, "engine_peak_power_rpm", None) is not None

        if not has_ratios:
            stepper_stage = 0
            stepper_blocker = _NEXT_ACTION_MISSING_RATIOS
            stepper_tab = "Transmission"
        elif not has_engine_data:
            # Ratios present but engine data (peak power RPM etc.) not yet entered.
            stepper_stage = 1
            stepper_blocker = (
                missing[0] if missing
                else "Enter peak power RPM, peak torque RPM, and redline "
                     "in the Shift Strategy panel"
            )
            stepper_tab = "Shift Strategy"
        elif is_stale:
            stepper_stage = 2
            stepper_blocker = "Recompute the shift strategy to confirm current targets."
            stepper_tab = "Shift Strategy"
        else:
            stepper_stage = 3
            stepper_blocker = ""
            stepper_tab = ""

        # --- Banner (EMPTY > STALE > PROVISIONAL precedence) ---
        # FIX D: simplify dead branch `not has_ratios or (not has_ratios and …)`
        if not has_ratios:
            banner_text = _NEXT_ACTION_MISSING_RATIOS
            banner_tone = "neutral"
        elif is_stale:
            # FIX A.3: include the specific field in the banner when available.
            if resolved_stale_text and resolved_stale_text != _GENERIC_STALE:
                banner_text = (
                    f"Shift strategy is stale — {resolved_stale_text}. Recompute."
                )
            else:
                banner_text = "Shift strategy is stale — configuration has changed. Recompute."
            banner_tone = "warn"
        elif is_provisional:
            banner_text = (
                "Shift targets are PROVISIONAL — based on manually entered engine data. "
                "Fuel saving estimates are unvalidated proxies."
            )
            banner_tone = "advisory"
        elif overall_key == ShiftConfidence.INSUFFICIENT_EVIDENCE.value:
            banner_text = evidence_text
            banner_tone = "neutral"
        else:
            banner_text = ""
            banner_tone = ""

        return ShiftStrategyVM(
            rows=rows,
            active_profile=_profile,
            required_saving_text=req_text,
            predicted_saving_text=pred_text,
            time_cost_text=time_cost_text,
            config_status_text=config_status_text,
            config_is_stale=is_stale,
            stale_field_text=resolved_stale_text,
            overall_confidence_key=overall_key,
            evidence_readiness_text=evidence_text,
            stepper_stage=stepper_stage,
            stepper_blocker_text=stepper_blocker,
            stepper_go_to_tab=stepper_tab,
            banner_text=banner_text,
            banner_tone=banner_tone,
            # Read public fields — no private attr crawl.
            engine_peak_power_rpm=getattr(result, "engine_peak_power_rpm", None),
            engine_peak_torque_rpm=getattr(result, "engine_peak_torque_rpm", None),
            engine_redline=getattr(result, "engine_redline", None),
        )

    except Exception:  # pragma: no cover - defensive
        return ShiftStrategyVM(
            rows=(),
            active_profile="qualifying",
            required_saving_text="—",
            predicted_saving_text="Error — see logs",
            time_cost_text="—",
            config_status_text="Error",
            config_is_stale=False,
            stale_field_text="",
            overall_confidence_key=ShiftConfidence.INSUFFICIENT_EVIDENCE.value,
            evidence_readiness_text="An error occurred building the view model.",
            stepper_stage=0,
            stepper_blocker_text="An error occurred. Check the application log.",
            stepper_go_to_tab="",
            banner_text="An error occurred building the shift strategy view.",
            banner_tone="warn",
            engine_peak_power_rpm=None,
            engine_peak_torque_rpm=None,
            engine_redline=None,
        )
