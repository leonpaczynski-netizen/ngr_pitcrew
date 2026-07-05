"""Driving coach and setup advisor powered by telemetry data + Claude API.

build_last_lap_response()  — rule-based, instant, no API.
build_coaching_response()  — Claude API, uses last 3 laps + session history from DB.
build_setup_advice_response(setup) — Claude API, maps telemetry + DB history to setup changes.
"""
from __future__ import annotations

import json as _json
import re as _re
from dataclasses import dataclass
from statistics import mean
from typing import Optional, TYPE_CHECKING

from data.session_db import ms_to_str
from strategy._ai_client import call_api, format_setup_for_prompt, load_gt7_reference
from strategy._rec_parser import parse_recommendations_from_response
from strategy._setup_constants import ENG_SAFETY_PREFIXES, APPROVED_STATUSES
from strategy.setup_ranges import resolve_ranges
from strategy.setup_diagnosis import (
    PERSONAL_DRIVER_TUNING_MODEL,
    DRIVER_HARD_CONSTRAINTS,
    build_setup_diagnosis,
    validate_setup_engineering,
    validate_setup_engineering_structured,
    format_diagnosis_for_prompt,
    _build_deterministic_fallback,
    _build_setup_diagnosis_conservative,
)
from ui.gt7_data import build_track_context

# ---------------------------------------------------------------------------
# SetupRecommendationResult — the single lifecycle container for a setup rec
# ---------------------------------------------------------------------------

# The 8 valid status strings:
#   generated               — AI responded but not yet validated
#   validation_failed       — first-pass validation failed (no retry attempted)
#   retry_requested         — retry has been sent
#   retry_failed            — retry still has blocking failures
#   approved                — all rules pass, no warnings
#   approved_with_warnings  — rules pass but non-blocking warnings present
#   fallback_generated      — deterministic fallback used (has changes)
#   blocked_no_safe_recommendation — fallback produced zero changes

@dataclass(frozen=True)
class SetupRecommendationResult:
    """Immutable lifecycle container for a single setup recommendation.

    Frontend contract
    -----------------
    - status in APPROVED_STATUSES         → surface approved_changes to the driver
    - status not in APPROVED_STATUSES     → show error banner; rejected_changes for debug
    - approved_changes / approved_fields  → these are safe to apply
    - rejected_changes                    → collapsed debug section only
    - engineering_errors                  → list of blocking failure messages
    - validation_warnings                 → list of warning messages (non-blocking)
    - raw_json                            → the full AI response as a JSON string
    - fallback_used                       → True when deterministic fallback was triggered
    """
    status: str
    approved_changes: list
    approved_fields: dict
    rejected_changes: list
    analysis: str
    primary_issue: str
    engineering_errors: list
    validation_warnings: list
    fallback_used: bool
    raw_json: str

# Fields that are DISPLAY-ONLY and must never appear in approved_changes / approved_fields.
# Keep in _CANONICAL_SETUP_PARAMS so they are still recognised/diagnostic.
_DISPLAY_ONLY_FIELDS: frozenset[str] = frozenset({"transmission_max_speed_kmh"})

# Setup-tuning categories that can be locked by event rules. Must match the
# selectable checkboxes in DashboardWindow._TUNING_CATEGORIES — "tyres" is NOT a
# setup-tuning field (compound choice is a strategy decision handled elsewhere),
# so it must not appear here or it is always reported as LOCKED.
_ALL_TUNING_CATS = [
    "brake_balance", "suspension", "differential",
    "aero", "transmission", "power", "ballast", "steering", "nitrous",
]


def _tuning_constraint_block(
    allowed_tuning: "list[str] | None",
    tuning_locked: bool,
) -> str:
    if tuning_locked:
        return (
            "\n## EVENT RULES — TUNING LOCKED\n"
            "Do NOT suggest any setup changes. Focus on driving technique and tyre choices only.\n\n"
        )
    if allowed_tuning:
        locked = [c for c in _ALL_TUNING_CATS if c not in allowed_tuning]
        return (
            f"\n## EVENT TUNING RESTRICTIONS\n"
            f"Allowed to modify: {', '.join(allowed_tuning)}\n"
            f"LOCKED (do not recommend changes): {', '.join(locked)}\n"
            f"Only recommend changes to ALLOWED areas.\n\n"
        )
    return ""


# Fields shown in the per-car valid-ranges block, in display order, with units.
# Front/rear are listed separately because per-car ranges can differ per side.
_RANGE_BLOCK_FIELDS: list[tuple[str, str]] = [
    ("ride_height_front", "mm"), ("ride_height_rear", "mm"),
    ("springs_front", "Hz"), ("springs_rear", "Hz"),
    ("dampers_front_comp", "%"), ("dampers_front_ext", "%"),
    ("dampers_rear_comp", "%"), ("dampers_rear_ext", "%"),
    ("arb_front", ""), ("arb_rear", ""),
    ("camber_front", "° (positive 0–6)"), ("camber_rear", "° (positive 0–6)"),
    ("toe_front", "°"), ("toe_rear", "°"),
    ("aero_front", "downforce"), ("aero_rear", "downforce"),
    ("lsd_initial", ""), ("lsd_accel", ""), ("lsd_decel", ""),
    ("brake_bias", ""), ("ballast_kg", "kg"), ("ballast_position", ""),
    ("power_restrictor", "%"),
]


def _fmt_bound(lo, hi) -> str:
    if isinstance(lo, float) or isinstance(hi, float):
        return f"{lo:.2f}–{hi:.2f}"
    return f"{lo}–{hi}"


def _valid_ranges_block(car_name: str) -> str:
    """Per-car min–max for every adjustable field, so the AI suggests values
    within the car's real limits and knows which parts ARE adjustable.

    Without this block the analysis prompts list only field NAMES, so the AI
    has no idea of the car's bounds and conservatively declines to touch
    parts like aero. Built from the same resolve_ranges() data the parser
    clamps against, so the advice and the applied values agree.
    """
    r = resolve_ranges(car_name)
    lines = []
    for field, unit in _RANGE_BLOCK_FIELDS:
        if field not in r:
            continue
        lo, hi = r[field]
        suffix = f" {unit}" if unit else ""
        lines.append(f"  {field}: {_fmt_bound(lo, hi)}{suffix}")
    body = "\n".join(lines)
    return (
        "## Valid setup ranges for THIS car — stay within these (the game rejects "
        "out-of-range values). A non-zero range means the part IS adjustable on this "
        "car, including aero (aero_front / aero_rear downforce) — recommend aero "
        "changes when they help:\n"
        f"{body}\n"
        "  brake_bias sign convention: negative = more front braking, "
        "positive = more rear braking (GT7 scale −5 … +5).\n"
    )

# ---------------------------------------------------------------------------
# Canonical param keys recognised by the combined-setup response normaliser.
# Must match the setup_fields key list given in _build_combined_prompt and the
# keys used by setup_ranges.GENERIC_DEFAULTS / _parse_setup_recommendation.
# ---------------------------------------------------------------------------
_CANONICAL_SETUP_PARAMS: frozenset[str] = frozenset({
    "ride_height_front", "ride_height_rear",
    "springs_front", "springs_rear",
    "dampers_front_comp", "dampers_front_ext",
    "dampers_rear_comp", "dampers_rear_ext",
    "arb_front", "arb_rear",
    "camber_front", "camber_rear",
    "toe_front", "toe_rear",
    "aero_front", "aero_rear",
    "lsd_initial", "lsd_accel", "lsd_decel",
    "lsd_front_initial", "lsd_front_accel", "lsd_front_decel",
    "brake_bias",
    "ballast_kg", "ballast_position",
    "power_restrictor",
    # Gearbox real fields — actionable (except transmission_max_speed_kmh which is display-only)
    "final_drive",
    "gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6",
    # Display-only (stays in canonical so it's recognised; stripped by _DISPLAY_ONLY_FIELDS)
    "transmission_max_speed_kmh",
})

# Aliases: legacy/alternate names the AI may produce → canonical key
_PARAM_ALIASES: dict[str, str] = {
    "brake_bias_front": "brake_bias",
}


def _slug(text: str) -> str:
    """Strip all non-alphanumeric characters and lowercase — for fuzzy matching."""
    return _re.sub(r"[^a-z0-9]", "", text.lower())


# Pre-built slug → canonical key map for fast matching
_SLUG_TO_CANONICAL: dict[str, str] = {
    _slug(k): k for k in _CANONICAL_SETUP_PARAMS
}


def _resolve_field_key(field: str, setting: str) -> str | None:
    """Return the canonical param key for a change item, or None if unresolvable.

    Resolution order:
    1. ``field`` is already a recognised canonical key — return as-is.
    2. ``field`` is a known alias — return the canonical key.
    3. Slug-match ``field`` against all canonical keys.
    4. Slug-match ``setting`` (the human label) against all canonical keys.
    """
    if field and field in _CANONICAL_SETUP_PARAMS:
        return field
    if field and field in _PARAM_ALIASES:
        return _PARAM_ALIASES[field]
    # Slug-match field value
    if field:
        s = _slug(field)
        if s in _SLUG_TO_CANONICAL:
            return _SLUG_TO_CANONICAL[s]
        for k_slug, k in _SLUG_TO_CANONICAL.items():
            if k_slug in s or s in k_slug:
                return k
    # Slug-match the human-readable setting label
    if setting:
        s = _slug(str(setting))
        if s in _SLUG_TO_CANONICAL:
            return _SLUG_TO_CANONICAL[s]
        for k_slug, k in _SLUG_TO_CANONICAL.items():
            if k_slug in s or s in k_slug:
                return k
    return None


def _expand_gear_ratios(changes: list[dict], setup_fields: dict[str, object]) -> tuple[list[dict], dict[str, object]]:
    """Expand a ``gear_ratios: [v1..v6]`` change/field into individual gear_1..gear_6 keys.

    When the AI returns a single change with field="gear_ratios" and a list value,
    or a setup_fields key "gear_ratios" with a list, this expands them into the
    individual canonical gear_1..gear_6 keys so the rest of the pipeline (validation,
    clamping, apply-button) works uniformly.

    Returns (expanded_changes, expanded_setup_fields).  If no gear_ratios key is
    present the inputs are returned unchanged.
    """
    _GEAR_KEYS = ("gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6")

    # Expand setup_fields
    sf_out: dict[str, object] = {}
    for k, v in setup_fields.items():
        if k == "gear_ratios" and isinstance(v, list):
            for _i, _ratio in enumerate(v[:6]):
                sf_out[_GEAR_KEYS[_i]] = _ratio
        else:
            sf_out[k] = v

    # Expand changes
    ch_out: list[dict] = []
    for ch in changes:
        raw_field = str(ch.get("field", "")).strip()
        if raw_field == "gear_ratios":
            ratios = ch.get("to")
            if isinstance(ratios, list):
                for _i, _ratio in enumerate(ratios[:6]):
                    _new_ch = dict(ch)
                    _new_ch["field"] = _GEAR_KEYS[_i]
                    _new_ch["setting"] = f"Gear {_i + 1} Ratio"
                    _new_ch["to"] = str(_ratio)
                    ch_out.append(_new_ch)
                continue  # skip original gear_ratios entry
        ch_out.append(ch)

    return ch_out, sf_out


def _normalise_changes(
    changes: list[dict],
    setup_fields: dict[str, object],
    car_name: str,
) -> list[dict]:
    """Enrich each change item with resolved ``field`` and ``to_clamped`` keys.

    Parameters
    ----------
    changes:
        Raw list of change dicts from the AI JSON (mutated in-place copies).
    setup_fields:
        The ``setup_fields`` dict from the same AI response (already clamped
        by the prompt's numeric-value constraint, used as preferred source).
    car_name:
        Used with resolve_ranges to obtain per-car bounds for ``to_clamped``.

    Returns
    -------
    A new list of dicts with ``field`` (str | None) and ``to_clamped`` added.
    Every other key is preserved unchanged.

    Contract for the frontend
    -------------------------
    - ``ch["field"]``      — canonical param key (str) or None if unresolvable.
    - ``ch["to"]``         — raw AI recommended value (string or number, unchanged).
    - ``ch["to_clamped"]`` — numeric value clamped to per-car range, or the raw
                             ``to`` value if the field is unresolvable or non-numeric.

    Gear-ratio expansion
    --------------------
    If any change has field="gear_ratios" with a list "to" value, it is expanded
    into individual gear_1..gear_6 changes.  Likewise for setup_fields.
    """
    # Expand gear_ratios before processing
    changes, setup_fields = _expand_gear_ratios(changes, setup_fields)

    ranges = resolve_ranges(car_name)
    result: list[dict] = []
    for ch in changes:
        ch = dict(ch)  # copy; never mutate caller's data
        raw_field   = str(ch.get("field", "")).strip()
        raw_setting = str(ch.get("setting", "")).strip()
        resolved    = _resolve_field_key(raw_field, raw_setting)
        ch["field"] = resolved

        # Derive to_clamped: prefer the value from setup_fields (already
        # instructed to be numeric and in-range); fall back to clamping
        # ch["to"] against the resolved range.
        raw_to = ch.get("to")
        to_clamped: object = raw_to
        if resolved is not None:
            # If setup_fields carries this param, use that numeric value
            # (it matches what the apply-button path will use).
            if resolved in setup_fields:
                to_clamped = setup_fields[resolved]
            elif raw_to is not None and resolved in ranges:
                try:
                    num = float(raw_to)
                    lo, hi = ranges[resolved]
                    to_clamped = max(lo, min(hi, num))
                    # Preserve int type for integer params
                    if isinstance(lo, int) and isinstance(hi, int):
                        to_clamped = int(to_clamped)
                except (TypeError, ValueError):
                    pass  # non-numeric "to" — leave as-is
        ch["to_clamped"] = to_clamped

        # Drop no-ops: if the clamped target equals the current value, this
        # change does nothing (e.g. ride-height already at its valid maximum).
        # Skip only when "from" parses as a float; leave unparseable from-values
        # in place so the AI's text is still surfaced.
        try:
            from_val = float(ch.get("from", ""))
            if isinstance(to_clamped, (int, float)) and float(to_clamped) == from_val:
                continue  # no-op: drop this change
        except (TypeError, ValueError):
            pass  # unparseable from-value — keep the change

        result.append(ch)
    return result


def _derive_locked_fields(allowed_tuning: "list[str] | None") -> "set[str]":
    """Return the set of canonical field keys that are locked given allowed_tuning.

    Maps tuning category codes to canonical parameter keys.  Fields whose
    categories are NOT in allowed_tuning are considered locked.
    """
    if not allowed_tuning:
        return set()

    # Map tuning category codes to the canonical field keys they cover.
    # NOTE: "steering" and "nitrous" categories from _ALL_TUNING_CATS have no
    # mapped setup params yet.  If only those categories are allowed, this
    # function returns an empty locked set (no params to lock), which is the
    # correct safe fallback — the validator then has nothing to flag.
    _CAT_FIELDS: dict[str, list[str]] = {
        "suspension": [
            "ride_height_front", "ride_height_rear",
            "springs_front", "springs_rear",
            "dampers_front_comp", "dampers_front_ext",
            "dampers_rear_comp", "dampers_rear_ext",
            "arb_front", "arb_rear",
            "camber_front", "camber_rear",
            "toe_front", "toe_rear",
        ],
        "aero": ["aero_front", "aero_rear"],
        "differential": ["lsd_initial", "lsd_accel", "lsd_decel",
                         "lsd_front_initial", "lsd_front_accel", "lsd_front_decel"],
        "brake_balance": ["brake_bias"],
        "transmission": [
            "final_drive",
            "gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6",
            "transmission_max_speed_kmh",  # display-only; included so lock check covers it
        ],
        "power": ["power_restrictor"],
        "ballast": ["ballast_kg", "ballast_position"],
        # "steering": []   — no canonical setup params mapped yet
        # "nitrous": []    — no canonical setup params mapped yet
    }

    allowed_fields: set[str] = set()
    for cat in allowed_tuning:
        for f in _CAT_FIELDS.get(cat, []):
            allowed_fields.add(f)

    locked: set[str] = set()
    for fields_list in _CAT_FIELDS.values():
        for f in fields_list:
            if f not in allowed_fields:
                locked.add(f)
    return locked


# ---------------------------------------------------------------------------
# _finalise_recommendation — SINGLE funnel for all AI paths
# ---------------------------------------------------------------------------

def _finalise_recommendation(
    raw_data: dict,
    structured_failures: list,
    fallback_used: bool,
    retried: bool,
    failing_changes: "list | None" = None,
) -> "SetupRecommendationResult":
    """Compute the final lifecycle status and approved changes for a recommendation.

    Parameters
    ----------
    raw_data:
        The parsed (and normalised) AI response dict.
    structured_failures:
        list[ValidationFailure] from validate_setup_engineering_structured.
    fallback_used:
        True when the deterministic fallback was used instead of the AI output.
    retried:
        True when this is already a retry attempt.
    failing_changes:
        Optional explicit list of the AI's failing changes.  When the retry path
        triggers a fallback, ``raw_data["changes"]`` is overwritten by the
        fallback's empty list before this function runs.  Pass the original
        failing changes here so that ``rejected_changes`` is populated correctly.

    Returns
    -------
    SetupRecommendationResult with all fields populated.

    Logic
    -----
    1. Split failures into blocking vs warning/info.
    2. If any blocking failure:
         status = retry_failed (if retried) else validation_failed
         approved_changes = []
         approved_fields = {}
         rejected_changes = raw_data's changes (collapsed debug)
         engineering_errors = blocking messages
    3. Elif fallback_used AND changes are empty:
         status = blocked_no_safe_recommendation
    4. Elif fallback_used:
         status = fallback_generated
    5. Elif warnings present:
         status = approved_with_warnings
    6. Else:
         status = approved

    Always strips _DISPLAY_ONLY_FIELDS from approved_changes/approved_fields.
    """
    all_blocking = [f for f in structured_failures if f.severity == "blocking"]
    warnings = [f for f in structured_failures if f.severity == "warning"]

    raw_changes = raw_data.get("changes") or []
    raw_sf = raw_data.get("setup_fields") or {}
    analysis = raw_data.get("analysis", "")
    primary_issue = raw_data.get("primary_issue", "")

    raw_json = _json.dumps(raw_data, ensure_ascii=False)

    # Classify blocking failures into safety-rule vs structural/schema categories.
    # BOTH categories force validation_failed + zeroed changes — the distinction only
    # affects message routing (engineering_errors vs validation_warnings for banner text).
    # EXCEPTION: out-of-range is now a WARNING (not blocking) because the clamping
    # mechanism in _normalise_changes guarantees the applied value is always in range.
    safety_blocking = [
        f for f in all_blocking
        if any(f.code.startswith(p) for p in ENG_SAFETY_PREFIXES)
    ]
    structural_blocking = [f for f in all_blocking if f not in safety_blocking]

    if all_blocking:
        # Any blocking failure — safety-rule OR structural (malformed_schema, invalid_units,
        # locked-field, etc.) — zeroes approved_changes and forces a failed status.
        # This ensures locked/malformed/invalid-unit changes are never applyable.
        status = "retry_failed" if retried else "validation_failed"
        approved_changes: list = []
        approved_fields: dict = {}
        # Use the explicitly supplied failing changes when provided — the retry→fallback
        # path overwrites raw_data["changes"] with [] before _finalise_recommendation runs,
        # so raw_changes would be empty without this.
        rejected_changes: list = (
            failing_changes if failing_changes is not None else list(raw_changes)
        )
        # Safety-rule failures go to engineering_errors (shown as "rejected by safety rule")
        # Structural failures go to validation_warnings (shown as "structural/schema error")
        engineering_errors = [f.message for f in safety_blocking]
        validation_warnings = [f.message for f in structural_blocking + warnings]

        if not analysis:
            analysis = (
                "Engineering validation failed — the AI's recommended changes "
                "were rejected. No changes will be applied."
            )
    else:
        # No blocking failures: approved_changes survive (out-of-range warnings are visible
        # but the applied value is always the clamped safe value per _normalise_changes).
        engineering_errors = []
        validation_warnings = [f.message for f in warnings]
        rejected_changes = []

        # Strip display-only fields from changes and setup_fields
        approved_changes = [
            ch for ch in raw_changes
            if ch.get("field") not in _DISPLAY_ONLY_FIELDS
        ]
        approved_fields = {
            k: v for k, v in raw_sf.items()
            if k not in _DISPLAY_ONLY_FIELDS
        }

        if fallback_used and not approved_changes:
            status = "blocked_no_safe_recommendation"
            analysis = (
                analysis or
                "Not enough session data to generate a safe recommendation — run more laps."
            )
        elif fallback_used:
            status = "fallback_generated"
        elif validation_warnings:
            status = "approved_with_warnings"
        else:
            status = "approved"

    return SetupRecommendationResult(
        status=status,
        approved_changes=approved_changes,
        approved_fields=approved_fields,
        rejected_changes=rejected_changes,
        analysis=analysis,
        primary_issue=primary_issue,
        engineering_errors=engineering_errors,
        validation_warnings=validation_warnings,
        fallback_used=fallback_used,
        raw_json=raw_json,
    )


# ---------------------------------------------------------------------------
# _build_retry_prompt — strict retry contract
# ---------------------------------------------------------------------------

def _build_retry_prompt(
    original_prompt: str,
    blocking_failures: list,
    current_setup: dict,
    ranges: dict,
) -> str:
    """Build a retry prompt that explicitly lists each blocking failure.

    Forbids repeating any rejected change, demands fresh valid JSON,
    and includes the max allowed delta for each affected field.

    Parameters
    ----------
    original_prompt:
        The original prompt sent to the AI.
    blocking_failures:
        list[ValidationFailure] (only blocking severity items).
    current_setup:
        The current car setup dict for context.
    ranges:
        Resolved per-car ranges dict (for max delta info).
    """
    if not blocking_failures:
        return original_prompt

    lines = [
        "",
        "",
        "## Engineering Validation Failure — Retry Required",
        "Your previous response was REJECTED. The following rules were violated:",
    ]

    rejected_fields: set[str] = set()
    for vf in blocking_failures:
        lines.append(f"- [{vf.code}] {vf.message}")
        # Extract the field from the code if possible
        # e.g. "rh_for_minor_bottoming" maps to ride_height_*
        # We capture any canonical field name mentioned in the message
        for _canon_key in _CANONICAL_SETUP_PARAMS:
            if _canon_key in vf.message:
                rejected_fields.add(_canon_key)

    lines.append("")
    lines.append("## MANDATORY CORRECTIONS")
    lines.append("1. Do NOT repeat any of the rejected changes listed above.")
    lines.append("2. Do NOT include these fields in your new response:")
    for _rf in sorted(rejected_fields):
        _lo_hi = ranges.get(_rf)
        if _lo_hi:
            lines.append(f"   - {_rf} (current: {current_setup.get(_rf, 'unknown')}, valid: {_lo_hi[0]}–{_lo_hi[1]})")
        else:
            lines.append(f"   - {_rf} (current: {current_setup.get(_rf, 'unknown')})")
    lines.append("3. Produce a FRESH recommendation that corrects ALL listed issues.")
    lines.append("4. Return ONLY valid JSON — no markdown, no extra text.")

    return original_prompt + "\n".join(lines)


def _validate_setup_response(
    parsed: dict,
    car_name: str,
    allowed_tuning: "list[str] | None",
    locked_fields: "set[str] | None",
    setup: dict,
) -> dict:
    """Validate an already-parsed + already-normalised AI response dict.

    Appends a top-level ``validation_errors`` key listing all detected
    problems.  Changes are NOT dropped — callers decide what to do with
    invalid items.

    Parameters
    ----------
    parsed:
        Already-parsed (and normalised) AI response dict.
    car_name:
        Used to obtain per-car ranges via resolve_ranges.
    allowed_tuning:
        List of allowed tuning category codes (e.g. ["suspension", "aero"]).
        When None, no locked-field checks are performed.
    locked_fields:
        Explicit set of canonical field keys that must not be changed.
        May be None (no locked checks).
    setup:
        Current setup dict — used to derive the set of known setup_fields keys.
    """
    errors: list[str] = []
    ranges = resolve_ranges(car_name)
    changes = parsed.get("changes") or []
    sf = parsed.get("setup_fields") or {}

    # Collect canonical keys touched by changes
    change_fields: set[str] = set()
    for ch in changes:
        f = ch.get("field")
        if f is not None:
            change_fields.add(f)

    # 1. Every change field must be a recognised canonical key
    for ch in changes:
        f = ch.get("field")
        if f is None:
            errors.append(
                f"change '{ch.get('setting', '?')}' has no recognisable canonical field key"
            )
        elif f not in _CANONICAL_SETUP_PARAMS:
            errors.append(f"change field '{f}' is not a known canonical setup key")

    # 2. Every to_clamped must be within resolved ranges (for known fields)
    for ch in changes:
        f = ch.get("field")
        tc = ch.get("to_clamped")
        if f and f in ranges and isinstance(tc, (int, float)):
            lo, hi = ranges[f]
            if not (lo <= tc <= hi):
                errors.append(
                    f"change field '{f}' to_clamped={tc} is outside valid range [{lo}, {hi}]"
                )

    # 3. No change targets a locked field
    if locked_fields:
        for ch in changes:
            f = ch.get("field")
            if f and f in locked_fields:
                errors.append(f"change field '{f}' targets a locked field")

    # 4. No remaining no-ops (from == to_clamped)
    for ch in changes:
        tc = ch.get("to_clamped")
        try:
            from_val = float(ch.get("from", ""))
            if isinstance(tc, (int, float)) and float(tc) == from_val:
                errors.append(
                    f"change field '{ch.get('field', '?')}' is a no-op (from == to_clamped == {tc})"
                )
        except (TypeError, ValueError):
            pass

    # 5. Every numeric to_clamped must be a number, not a string
    for ch in changes:
        tc = ch.get("to_clamped")
        f = ch.get("field")
        if f and f in ranges and isinstance(tc, str):
            errors.append(
                f"change field '{f}' to_clamped is a string ({tc!r}), expected numeric"
            )

    # 5b. rh_rake_risk structural check (AC10)
    # Rear ride-height increase > 3mm (i.e. >= 4mm) with no front change => rake risk
    def _val_ai_value(key: str):
        """Helper to get AI numeric value for rh_rake_risk check."""
        if key in sf:
            try:
                return float(sf[key])
            except (TypeError, ValueError):
                pass
        for ch in changes:
            if ch.get("field") == key:
                tc = ch.get("to_clamped")
                if tc is not None:
                    try:
                        return float(tc)
                    except (TypeError, ValueError):
                        pass
                raw_to = ch.get("to")
                if raw_to is not None:
                    try:
                        return float(raw_to)
                    except (TypeError, ValueError):
                        pass
        return None

    def _val_current_value(key: str):
        """Helper to get current setup value for rh_rake_risk check."""
        v = setup.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    _v_ai_rhf = _val_ai_value("ride_height_front")
    _v_cur_rhf = _val_current_value("ride_height_front")
    _v_ai_rhr = _val_ai_value("ride_height_rear")
    _v_cur_rhr = _val_current_value("ride_height_rear")
    if _v_ai_rhr is not None and _v_cur_rhr is not None:
        _v_rear_delta = _v_ai_rhr - _v_cur_rhr
        _v_front_changed = (_v_ai_rhf is not None and _v_ai_rhf != _v_cur_rhf)
        if _v_rear_delta >= 4 and not _v_front_changed:
            errors.append(
                f"rh_rake_risk: AI increases ride_height_rear by {_v_rear_delta:.0f}mm "
                f"(from {_v_cur_rhr} to {_v_ai_rhr}) with no ride_height_front change — "
                f"rake risk (high). Use smaller increment or pair with front change."
            )

    # 6. Too many changes
    if len(changes) > 4:
        errors.append(
            f"too many changes (>4): {len(changes)} changes recommended — prefer 2–4 targeted changes"
        )

    # 7. setup_fields / changes consistency
    sf_keys = set(sf.keys())
    for f in change_fields:
        if f and f not in sf_keys:
            errors.append(
                f"change field '{f}' is in changes but missing from setup_fields"
            )
    for f in sf_keys:
        if f not in change_fields:
            errors.append(
                f"setup_fields key '{f}' has no corresponding change entry"
            )

    parsed["validation_errors"] = errors
    return parsed


def _classify_bottoming_location(
    bottoming_positions: list,
    loc_id: str,
    lay_id: str,
) -> str:
    """Classify the most likely track context for recorded bottoming events.

    Returns one of:
      "braking zone" | "kerb strike" | "banking compression" |
      "infield bump" | "throttle-exit squat" | "unknown"

    Uses enrich_telemetry_issues to map bottoming positions to reviewed
    segments and their phases.  Falls back to "unknown" gracefully when
    loc_id/lay_id are empty, positions are empty, or enrichment raises
    or returns nothing.
    """
    if not bottoming_positions or not loc_id or not lay_id:
        return "unknown"

    # Phase/segment-type → vocabulary mapping
    _PHASE_TO_CATEGORY = {
        "braking":   "braking zone",
        "entry":     "braking zone",
        "traction":  "throttle-exit squat",
        "exit":      "throttle-exit squat",
        "straight":  "infield bump",
        "apex":      "banking compression",
    }
    _SEG_TYPE_TO_CATEGORY = {
        "braking_zone":   "braking zone",
        "corner_entry":   "braking zone",
        "corner_exit":    "throttle-exit squat",
        "traction_zone":  "throttle-exit squat",
        "kerb_zone":      "kerb strike",
        "banking_zone":   "banking compression",
        "straight":       "infield bump",
    }

    try:
        from data.track_issue_enrichment import (
            RawTelemetryIssue,
            TrackIssueType,
            TrackIssuePhase,
            enrich_telemetry_issues,
        )
        raw_issues = []
        for pos in bottoming_positions:
            if len(pos) >= 3:
                raw_issues.append(RawTelemetryIssue(
                    issue_type=TrackIssueType.UNKNOWN,
                    phase=TrackIssuePhase.UNKNOWN,
                    lap_num=0,
                    pos_x=float(pos[0]),
                    pos_y=float(pos[1]),
                    pos_z=float(pos[2]),
                    evidence="bottoming event",
                ))
        if not raw_issues:
            return "unknown"

        result = enrich_telemetry_issues(raw_issues, loc_id, lay_id)
        if not result or not result.enriched_issues:
            return "unknown"

        # Vote on category across resolved issues
        votes: dict[str, int] = {}
        for ei in result.enriched_issues:
            cat = None
            # Try segment type first
            seg_type = ei.matched_segment_type or ""
            if seg_type in _SEG_TYPE_TO_CATEGORY:
                cat = _SEG_TYPE_TO_CATEGORY[seg_type]
            else:
                # Fall back to phase of raw issue
                phase_val = ei.raw.phase.value if hasattr(ei.raw.phase, "value") else str(ei.raw.phase)
                cat = _PHASE_TO_CATEGORY.get(phase_val)
            if cat:
                votes[cat] = votes.get(cat, 0) + 1

        if not votes:
            return "unknown"
        return max(votes, key=votes.__getitem__)
    except Exception:
        return "unknown"


if TYPE_CHECKING:
    from telemetry.recorder import LapTelemetryRecorder, LapStats
    from data.session_db import SessionDB


def _delta_str(ms: int, best_ms: int) -> str:
    if best_ms <= 0:
        return ""
    d = (ms - best_ms) / 1000.0
    return f" ({d:+.3f}s from best)" if d != 0 else " (best lap)"


def _race_engineer_directives(
    avg_lockups: float,
    avg_consist: float,
    avg_snap: float,
    avg_os_ton: float,
    avg_bottom: float,
    car_name: str,
    laps_sample_len: int,
    event_ctx: dict,
    wheelspin_positions: list,
    snap_throttle_positions: list,
    oversteer_positions: list,
    bottoming_positions: list,
    loc_id: str,
    lay_id: str,
    setup: "dict | None" = None,
) -> str:
    """Return shared race-engineer directive text for injection into both
    setup prompt builders (_build_setup_prompt and _build_combined_prompt).

    Covers AC1–AC13 directives.

    Parameters
    ----------
    setup:
        The current car setup dict.  When supplied, AC3 checks whether
        ride_height_front/rear are at the per-car maximum and emits an
        explicit, targeted instruction — do NOT recommend raising a value
        that is already at its valid maximum.
    """
    ranges = resolve_ranges(car_name)
    directives: list[str] = []
    setup = setup or {}

    # AC1 — range authority
    directives.append(
        "## Race Engineer Directives\n"
        "AC1 RANGE AUTHORITY: The per-car valid ranges shown above are the FINAL AUTHORITY "
        "and override any generic range in the knowledge base. If the knowledge base says ARB 1–7 "
        "but this car allows 1–10, use the car range."
    )

    # AC2 — units
    directives.append(
        "AC2 UNITS: Springs/natural frequency MUST be expressed in GT7 natural frequency (Hz), "
        "never N/mm. Camber values are POSITIVE GT7 menu values (0.00–6.00) — "
        "NEVER output a negative camber value."
    )

    # AC3 — ride-height escalation
    rh_front_max = ranges.get("ride_height_front", (60, 200))[1]
    rh_rear_max  = ranges.get("ride_height_rear",  (60, 200))[1]

    # Determine whether current ride-height values are at their per-car maximum.
    _rh_front_at_max = False
    _rh_rear_at_max  = False
    try:
        _rhf_cur = float(setup.get("ride_height_front", -1))
        if _rhf_cur >= 0:
            _rh_front_at_max = (_rhf_cur >= rh_front_max)
    except (TypeError, ValueError):
        pass
    try:
        _rhr_cur = float(setup.get("ride_height_rear", -1))
        if _rhr_cur >= 0:
            _rh_rear_at_max = (_rhr_cur >= rh_rear_max)
    except (TypeError, ValueError):
        pass

    directives.append(
        f"AC3 RIDE-HEIGHT ESCALATION: If bottoming is high but ride height is already at its "
        f"valid maximum (front max={rh_front_max} mm, rear max={rh_rear_max} mm), do NOT "
        f"recommend a ride-height change — classify it as a platform-control issue and escalate "
        f"to springs/natural frequency, compression/extension damping, aero platform, ARB and "
        f"LSD traction. Never output a no-op change (e.g. 70→70). If a setting is already at "
        f"its limit, state that only in analysis or do_not_change_reasoning."
    )
    if avg_bottom > 0:
        # Explicit, targeted instruction when we know the current setup value.
        _at_max_parts = []
        if _rh_front_at_max:
            _rhf_val = setup.get("ride_height_front", rh_front_max)
            _at_max_parts.append(
                f"ride_height_front is currently {_rhf_val} mm, which equals its valid maximum "
                f"({rh_front_max} mm) — do NOT recommend raising it"
            )
        if _rh_rear_at_max:
            _rhr_val = setup.get("ride_height_rear", rh_rear_max)
            _at_max_parts.append(
                f"ride_height_rear is currently {_rhr_val} mm, which equals its valid maximum "
                f"({rh_rear_max} mm) — do NOT recommend raising it"
            )
        if _at_max_parts:
            directives.append(
                f"  ↳ Bottoming detected (avg={avg_bottom:.1f}/lap) AND ride height is already "
                f"at its maximum: {'; '.join(_at_max_parts)}. "
                f"Escalate to springs/natural frequency, compression/extension damping, "
                f"aero platform, ARB and LSD traction instead. "
                f"already at limit — do not output a no-op change."
            )
        else:
            directives.append(
                f"  ↳ Bottoming is detected (avg={avg_bottom:.1f}/lap). "
                f"Ride-height front max={rh_front_max} mm, rear max={rh_rear_max} mm. "
                f"Ride height is currently BELOW its maximum — a ride-height change IS "
                f"permissible if it addresses the bottoming."
            )

    # AC4 — stable braking
    if avg_lockups < 0.5 and 0 <= avg_consist < 15:
        directives.append(
            "AC4 STABLE BRAKING: Braking is stable with no lock-up pattern — do NOT change "
            "brake_bias or lsd_decel unless another strong signal requires it; preserve "
            "existing strengths (entry, mid-corner) without telemetry justification."
        )

    # AC5 — issue classification
    directives.append(
        "AC5 ISSUE CLASSIFICATION: For each major issue, classify it as exactly one of: "
        "setup-limited | driver-input-limited | mixed | insufficient-data | not-present. "
        "Use these exact strings in the issue_classification JSON key."
    )

    # AC6 — snap throttle driver input
    if avg_snap > 0 and avg_os_ton > 0:
        directives.append(
            "AC6 SNAP-THROTTLE DRIVER INPUT: Snap-throttle-correlated wheelspin is partly driver "
            "input. Setup can reduce sensitivity (LSD accel, springs, gearing) but cannot fully "
            "fix driver-input-triggered wheelspin. Recommend legal setup changes if the car is "
            "too unstable, but do not claim setup alone solves snap throttle."
        )

    # AC9 — corner/phase context zones
    all_positions = (
        list(wheelspin_positions or []) +
        list(snap_throttle_positions or []) +
        list(oversteer_positions or [])
    )
    if all_positions:
        directives.append(
            "AC9 ZONE CONTEXT: Position clusters for wheelspin/snap-throttle/oversteer events "
            "are provided in the telemetry intelligence section above. When referencing these, "
            "label clusters as 'Zone A', 'Zone B', etc., or by lap-distance % — do NOT invent "
            "corner names (e.g. 'Turn 3' or 'T3') unless they come from validated track "
            "intelligence. Add caveat: 'low confidence — positional estimate only'."
        )

    # AC10 — bottoming location
    if avg_bottom > 0:
        _all_btm = list(bottoming_positions or [])
        btm_cat = _classify_bottoming_location(_all_btm, loc_id, lay_id)
        directives.append(
            f"AC10 BOTTOMING LOCATION (low confidence): {btm_cat}"
        )

    # AC11 — race objective
    race_type = event_ctx.get("race_type", "")
    if race_type in ("lap", "timed"):
        directives.append(
            "AC11 RACE OBJECTIVE: This is a TOTAL RACE performance target. The setup must "
            "preserve stability over a full stint, protect tyre life, reduce wheelspin to "
            "minimise tyre stress, reduce bottoming to protect the platform, maintain the fuel "
            "target, avoid a spiky or nervous car over the stint duration, and preserve driver "
            "confidence throughout. Do not optimise for single-lap pace at the expense of tyre "
            "and fuel performance over the stint."
        )

    # AC12 — short-sample warning
    event_laps = event_ctx.get("laps", 0)
    try:
        event_laps = int(event_laps)
    except (TypeError, ValueError):
        event_laps = 0
    if event_laps > 0 and laps_sample_len < max(1, round(event_laps * 0.2)):
        directives.append(
            f"AC12 SHORT SAMPLE WARNING: Telemetry covers only {laps_sample_len} lap(s) "
            f"out of {event_laps} event laps (<20%). Tyre wear, fuel load, and thermal "
            f"degradation effects are NOT captured in this sample. The setup must still be "
            f"designed for the full race distance."
        )

    # AC13 — smallest effective change
    directives.append(
        "AC13 SMALLEST EFFECTIVE CHANGE: Use the smallest effective change. Prefer 2–4 targeted "
        "changes. Avoid changing multiple settings that solve the same problem unless severity is "
        "high. Do not mask the diagnosis by changing too many things at once."
    )

    return "\n\n".join(directives)


class DrivingAdvisor:
    """Builds PTT driving coach responses from lap telemetry recordings."""

    def __init__(self, recorder, tracker, config, db=None, car_id_ref=None, session_id_getter=None) -> None:
        self._recorder    = recorder
        self._tracker     = tracker
        self._config      = config
        self._db: Optional["SessionDB"] = db
        self._car_id_ref  = car_id_ref or [0]
        self._event_ctx: dict = {}
        self._session_id_getter = session_id_getter if callable(session_id_getter) else (lambda: 0)

    # ------------------------------------------------------------------
    # Rule-based (instant)
    # ------------------------------------------------------------------

    def build_last_lap_response(self) -> str:
        lap = self._recorder.last_lap()
        if lap is None:
            return ("No lap data recorded yet. "
                    "Complete a lap with the car on track first.")

        best = self._recorder.best_lap()
        best_ms = best.lap_time_ms if best and best.lap_num != lap.lap_num else 0

        time_str  = ms_to_str(lap.lap_time_ms)
        delta_str = _delta_str(lap.lap_time_ms, best_ms)

        if lap.lock_up_count == 0:
            lock_str = "No lock-ups"
        elif lap.lock_up_count == 1:
            lock_str = "1 lock-up detected"
        else:
            lock_str = f"{lap.lock_up_count} lock-ups detected"

        if lap.wheelspin_count == 0:
            spin_str = "no wheelspin"
        elif lap.wheelspin_count == 1:
            spin_str = "1 wheelspin event"
        else:
            spin_str = f"{lap.wheelspin_count} wheelspin events"

        if lap.brake_consistency_m < 0:
            consist_str = "braking consistency could not be measured"
        elif lap.brake_consistency_m < 10:
            consist_str = f"braking very consistent ({lap.brake_consistency_m:.0f}m variation)"
        elif lap.brake_consistency_m < 25:
            consist_str = f"braking reasonably consistent ({lap.brake_consistency_m:.0f}m variation)"
        else:
            consist_str = f"braking inconsistent ({lap.brake_consistency_m:.0f}m variation — focus on reference points)"

        # Oversteer summary
        os_total = lap.oversteer_count
        os_ton   = lap.oversteer_throttle_on_count
        if os_total == 0:
            os_str = "no snap oversteer events"
        else:
            os_entry = os_total - os_ton
            os_str = (f"{os_total} oversteer event{'s' if os_total != 1 else ''} "
                      f"({os_ton} throttle-on, {os_entry} entry)")

        extras = []
        if lap.kerb_count:
            extras.append(f"{lap.kerb_count} hard kerb hit{'s' if lap.kerb_count != 1 else ''}")
        if lap.bottoming_count:
            extras.append(f"{lap.bottoming_count} bottoming event{'s' if lap.bottoming_count != 1 else ''}")
        if lap.snap_throttle_count:
            extras.append(f"{lap.snap_throttle_count} snap throttle application{'s' if lap.snap_throttle_count != 1 else ''}")
        extra_str = (". " + ", ".join(extras)) if extras else ""

        return (
            f"Lap {lap.lap_num}: {time_str}{delta_str}. "
            f"{lock_str}, {spin_str}, {os_str}. "
            f"{consist_str.capitalize()}. "
            f"Top speed {lap.max_speed_kmh:.0f} km/h, peak lateral G {lap.max_lat_g:.2f}. "
            f"Average throttle {lap.avg_throttle_pct:.0f}%, brake {lap.avg_brake_pct:.0f}%"
            f"{extra_str}."
        )

    # ------------------------------------------------------------------
    # Claude API responses
    # ------------------------------------------------------------------

    def build_coaching_response(
        self, car_name: str = "", car_specs: dict | None = None,
        allowed_tuning: "list[str] | None" = None, tuning_locked: bool = False,
        compound: str = "", corner_issues_summary: str = "",
        live_position=None,
    ) -> str:
        api_key = self._config.get("anthropic", {}).get("api_key", "")
        if not api_key.strip():
            return ("No Anthropic API key set. "
                    "Add your key in the Strategy tab to enable AI coaching.")

        recent = self._recorder.recent_laps(3)
        if not recent:
            return "Not enough laps recorded yet to give coaching advice."

        history_str = self._get_history_context()
        prompt = self._build_coaching_prompt(recent, history_str,
                                             car_name=car_name, car_specs=car_specs or {},
                                             allowed_tuning=allowed_tuning,
                                             tuning_locked=tuning_locked,
                                             compound=compound,
                                             corner_issues_summary=corner_issues_summary,
                                             live_position=live_position)
        _track_da = self._config.get("strategy", {}).get("track", "")
        try:
            _response_text = call_api(prompt, api_key, max_tokens=600,
                                      feature="Driver Coaching",
                                      structured_payload={"lap_count": len(recent),
                                                          "car": car_name,
                                                          "has_setup": False},
                                      model=self._config.get("anthropic", {}).get("model") or None,
                                      car_id=self._car_id_ref[0], track=_track_da)
            if self._db is not None:
                _session_id = self._session_id_getter()
                try:
                    _ai_id = self._db._conn.execute(
                        "SELECT MAX(id) FROM ai_interactions"
                    ).fetchone()[0]
                except Exception:
                    _ai_id = None
                _recs = parse_recommendations_from_response(
                    _response_text, "Driver Coaching",
                    self._car_id_ref[0], _track_da, "",
                    session_id=_session_id, ai_interaction_id=_ai_id,
                )
                if _recs:
                    self._db.insert_setup_recommendations(_recs)
            return _response_text
        except Exception as e:
            return f"Coaching analysis failed: {e}"

    def build_setup_advice_response(
        self, setup_dict: dict, car_name: str = "", car_specs: dict | None = None,
        allowed_tuning: "list[str] | None" = None, tuning_locked: bool = False,
        compound: str = "", corner_issues_summary: str = "",
        prior_outcomes: "list[dict] | None" = None,
        diagnosis: "dict | None" = None,
    ) -> str:
        """Return a JSON string: {"analysis": str, "changes": [{setting,from,to,why}]}.

        New optional param:
          diagnosis: pre-computed build_setup_diagnosis dict; computed internally if None.
        engineering_validation_failed and engineering_validation_errors keys are added
        to the returned JSON when the engineering validator fires after a single retry.
        """
        api_key = self._config.get("anthropic", {}).get("api_key", "")
        if not api_key.strip():
            return ("No Anthropic API key set. "
                    "Add your key in the Strategy tab to enable setup advice.")

        recent = self._recorder.recent_laps(5)
        if not recent:
            return "Not enough laps recorded yet. Drive a few laps first."

        # Pre-compute diagnosis so it can be injected into the prompt and reused
        # for engineering validation without re-deriving twice.
        _event_ctx = getattr(self, "_event_ctx", {})
        if diagnosis is None:
            try:
                diagnosis = build_setup_diagnosis(recent, setup_dict, car_name, _event_ctx, None)
            except Exception:
                diagnosis = {}

        # B4: resolve rec_history for lsd_reversal_without_evidence validation.
        # config_id is read from _event_ctx (which is already set from the strategy
        # dict upstream — no new config["strategy"] read here).
        _rec_history_sa: dict | None = None
        try:
            import data.setup_history as _sh
            import json as _json_inner
            _config_id_sa = _event_ctx.get("config_id", "") or ""
            _lsd_prior_value: float | None = None
            _lsd_prior_direction: str | None = None
            _lsd_worsened = False
            if _config_id_sa:
                _history_entries = _sh.load_history(_config_id_sa)
                if _history_entries:
                    _latest = _history_entries[-1]
                    for _ch in (_latest.get("changes") or []):
                        if _ch.get("field") == "lsd_accel":
                            try:
                                _to_v = float(_ch.get("to", 0))
                                _from_v = float(_ch.get("from", 0))
                                _lsd_prior_value = _to_v
                                _lsd_prior_direction = "increase" if _to_v > _from_v else "decrease"
                            except (TypeError, ValueError):
                                pass
                            break
            # worsened verdict: look at scored_recs for lsd_accel
            if self._db is not None:
                try:
                    _car_id_sa = int(self._car_id_ref[0]) or 0
                    _track_sa = _event_ctx.get("track") or ""
                    _scored = self._db.get_scored_recs_for_prompt(_car_id_sa, _track_sa, "")
                    for _srec in _scored:
                        _rec_text = _srec.get("recommendation_text") or ""
                        try:
                            _rec_data = _json_inner.loads(_rec_text)
                            for _sch in (_rec_data.get("changes") or []):
                                if _sch.get("field") == "lsd_accel":
                                    if _srec.get("score_verdict") == "worsened":
                                        _lsd_worsened = True
                                    break
                        except Exception:
                            pass
                        if _lsd_worsened:
                            break
                except Exception:
                    pass
            _rec_history_sa = {
                "lsd_accel": {
                    "prior_value":            _lsd_prior_value,
                    "prior_direction":        _lsd_prior_direction,
                    "worsened_verdict_exists": _lsd_worsened,
                }
            }
        except Exception:
            _rec_history_sa = None  # History failure must never break the response path

        history_str = self._get_history_context()
        prompt = self._build_setup_prompt(recent, setup_dict, history_str,
                                          car_name=car_name, car_specs=car_specs or {},
                                          allowed_tuning=allowed_tuning,
                                          tuning_locked=tuning_locked,
                                          compound=compound,
                                          corner_issues_summary=corner_issues_summary,
                                          prior_outcomes=prior_outcomes,
                                          diagnosis=diagnosis)
        _track_da = self._config.get("strategy", {}).get("track", "")
        try:
            _response_text = call_api(prompt, api_key, max_tokens=1500,
                                      feature="Setup Advice",
                                      structured_payload={"lap_count": len(recent),
                                                          "car": car_name,
                                                          "has_setup": bool(setup_dict)},
                                      model=self._config.get("anthropic", {}).get("model") or None,
                                      car_id=self._car_id_ref[0], track=_track_da)
            # Normalise changes and run validation — persistence happens AFTER finalisation
            try:
                _data = _json.loads(_response_text)
                _raw_changes = _data.get("changes") or []
                _setup_fields = _data.get("setup_fields") or {}
                if isinstance(_raw_changes, list) and _raw_changes:
                    _data["changes"] = _normalise_changes(
                        _raw_changes, _setup_fields, car_name
                    )
                    # Rebuild setup_fields from normalised changes
                    _normalised_sf: dict = {}
                    for _ch in _data["changes"]:
                        _f = _ch.get("field")
                        _tc = _ch.get("to_clamped")
                        if _f and isinstance(_tc, (int, float)):
                            _normalised_sf[_f] = _tc
                    _data["setup_fields"] = _normalised_sf
                _locked = _derive_locked_fields(allowed_tuning) if allowed_tuning else None
                _data = _validate_setup_response(
                    _data, car_name, allowed_tuning, _locked, setup_dict
                )
                # C3a: strip locked-field changes from changes + setup_fields so the
                # Apply button can never write a locked value.
                if _locked:
                    _data["changes"] = [
                        _c for _c in (_data.get("changes") or [])
                        if _c.get("field") not in _locked
                    ]
                    _data["setup_fields"] = {
                        _k: _v for _k, _v in (_data.get("setup_fields") or {}).items()
                        if _k not in _locked
                    }

                # Engineering validation + single retry using the strict retry contract
                try:
                    _ranges = resolve_ranges(car_name)
                    _structured_failures = validate_setup_engineering_structured(
                        _data, diagnosis, setup_dict, _ranges, _event_ctx,
                        car_name=car_name,
                        rec_history=_rec_history_sa,
                    )
                    # Only safety-rule failures trigger a retry and zero changes.
                    # Structural/schema/range errors are cosmetic and leave changes visible.
                    _blocking_failures = [
                        f for f in _structured_failures
                        if f.severity == "blocking"
                        and any(f.code.startswith(p) for p in ENG_SAFETY_PREFIXES)
                    ]
                    _fb_used = False
                    _retried = False
                    _failing_ai_changes: "list | None" = None

                    if _blocking_failures:
                        # Build strict retry prompt and attempt one correction
                        _retry_prompt = _build_retry_prompt(
                            prompt, _blocking_failures, setup_dict, _ranges
                        )
                        try:
                            _retry_text = call_api(
                                _retry_prompt, api_key, max_tokens=1500,
                                feature="Setup Advice (retry)",
                                structured_payload={"lap_count": len(recent),
                                                    "car": car_name,
                                                    "has_setup": bool(setup_dict),
                                                    "retry": True},
                                model=self._config.get("anthropic", {}).get("model") or None,
                                car_id=self._car_id_ref[0], track=_track_da,
                            )
                            _retried = True
                            _retry_data = _json.loads(_retry_text)
                            # Re-normalise
                            _rr_ch = _retry_data.get("changes") or []
                            _rr_sf = _retry_data.get("setup_fields") or {}
                            if isinstance(_rr_ch, list) and _rr_ch:
                                _retry_data["changes"] = _normalise_changes(_rr_ch, _rr_sf, car_name)
                                _rr_nsf: dict = {}
                                for _ch2 in _retry_data["changes"]:
                                    _f2 = _ch2.get("field")
                                    _tc2 = _ch2.get("to_clamped")
                                    if _f2 and isinstance(_tc2, (int, float)):
                                        _rr_nsf[_f2] = _tc2
                                _retry_data["setup_fields"] = _rr_nsf
                            _retry_data = _validate_setup_response(
                                _retry_data, car_name, allowed_tuning, _locked, setup_dict
                            )
                            if _locked:
                                _retry_data["changes"] = [
                                    _c for _c in (_retry_data.get("changes") or [])
                                    if _c.get("field") not in _locked
                                ]
                                _retry_data["setup_fields"] = {
                                    _k: _v for _k, _v in (_retry_data.get("setup_fields") or {}).items()
                                    if _k not in _locked
                                }
                            # Re-validate engineering on retry result
                            _retry_structured = validate_setup_engineering_structured(
                                _retry_data, diagnosis, setup_dict, _ranges, _event_ctx,
                                car_name=car_name,
                                rec_history=_rec_history_sa,
                            )
                            _retry_blocking = [
                                f for f in _retry_structured
                                if f.severity == "blocking"
                                and any(f.code.startswith(p) for p in ENG_SAFETY_PREFIXES)
                            ]
                            if _retry_blocking:
                                # Still failing after retry — build deterministic fallback
                                _fb_diag = diagnosis or _build_setup_diagnosis_conservative()
                                _fb = _build_deterministic_fallback(_fb_diag, setup_dict, _ranges)
                                _fb_used = True
                                # Capture failing changes before the fallback zeros them out
                                _failing_ai_changes = list(_retry_data.get("changes") or [])
                                _retry_data.update(_fb)
                                _structured_failures = _retry_structured
                            else:
                                _structured_failures = _retry_structured
                                _fb_used = False
                            if diagnosis:
                                _retry_data["diagnosis"] = diagnosis
                            _data = _retry_data
                        except Exception:
                            # Retry API/parse error — fallback to deterministic
                            _fb_diag = diagnosis or _build_setup_diagnosis_conservative()
                            _fb = _build_deterministic_fallback(_fb_diag, setup_dict, _ranges)
                            _fb_used = True
                            # Capture failing changes before the fallback zeros them out
                            _failing_ai_changes = list(_data.get("changes") or [])
                            _data.update(_fb)
                            _retried = True  # We attempted a retry

                    if diagnosis:
                        _data["diagnosis"] = diagnosis

                    # Route through _finalise_recommendation — the single funnel
                    _final = _finalise_recommendation(
                        _data, _structured_failures, _fb_used, _retried,
                        failing_changes=_failing_ai_changes,
                    )
                    # Attach lifecycle status to raw dict for callers that read the JSON
                    _data["recommendation_status"] = _final.status
                    _data["changes"] = _final.approved_changes
                    _data["setup_fields"] = _final.approved_fields
                    _data["engineering_validation_failed"] = _final.status not in APPROVED_STATUSES
                    _data["engineering_validation_errors"] = _final.engineering_errors
                    _data["validation_warnings"] = _final.validation_warnings
                    _data["fallback_used"] = _final.fallback_used
                    _data["rejected_changes"] = _final.rejected_changes

                except Exception:
                    pass  # Engineering validation must not break the response path

                _response_text = _json.dumps(_data, ensure_ascii=False)

                # Persistence after validation — write FINAL status to DB
                if self._db is not None:
                    _session_id = self._session_id_getter()
                    try:
                        _ai_id = self._db._conn.execute(
                            "SELECT MAX(id) FROM ai_interactions"
                        ).fetchone()[0]
                    except Exception:
                        _ai_id = None
                    _recs = parse_recommendations_from_response(
                        _response_text, "Setup Advice",
                        self._car_id_ref[0], _track_da, "",
                        session_id=_session_id, ai_interaction_id=_ai_id,
                    )
                    if _recs:
                        self._db.insert_setup_recommendations(_recs)

            except Exception:
                pass  # If normalisation/validation fails, return the original text unchanged
            return _response_text
        except Exception as e:
            return f"Setup analysis failed: {e}"

    def build_combined_setup_response(
        self, setup_dict: dict, n_laps: int = 5,
        car_name: str = "", car_specs: dict | None = None,
        feeling: str | None = None,
        allowed_tuning: "list[str] | None" = None, tuning_locked: bool = False,
        compound: str = "",
        prior_outcomes: "list[dict] | None" = None,
        diagnosis: "dict | None" = None,
    ) -> str:
        """Return a JSON string: {"analysis": str, "changes": [...], "setup_fields": {...}}.

        Always uses full telemetry. If *feeling* is provided it is included alongside
        telemetry — never sent alone. Uses up to *n_laps* most recent laps from the recorder.

        New optional param:
          diagnosis: pre-computed build_setup_diagnosis dict; computed internally if None.
        engineering_validation_failed and engineering_validation_errors keys are added
        to the returned JSON when the engineering validator fires after a single retry.
        """
        api_key = self._config.get("anthropic", {}).get("api_key", "")
        if not api_key.strip():
            return ("No Anthropic API key set. "
                    "Add your key in the Strategy tab to enable setup advice.")

        recent = self._recorder.recent_laps(n_laps)
        if not recent:
            return "Not enough laps recorded yet. Drive a few laps first."

        # Pre-compute diagnosis so it can be injected into the prompt and reused
        # for engineering validation without re-deriving twice.
        _event_ctx = getattr(self, "_event_ctx", {})
        if diagnosis is None:
            try:
                diagnosis = build_setup_diagnosis(recent, setup_dict, car_name, _event_ctx, feeling)
            except Exception:
                diagnosis = {}

        # B4: resolve rec_history for lsd_reversal_without_evidence validation.
        _rec_history_cs: dict | None = None
        try:
            import data.setup_history as _sh_cs
            import json as _json_cs
            _config_id_cs = _event_ctx.get("config_id", "") or ""
            _lsd_pv_cs: float | None = None
            _lsd_pd_cs: str | None = None
            _lsd_worsened_cs = False
            if _config_id_cs:
                _hist_cs = _sh_cs.load_history(_config_id_cs)
                if _hist_cs:
                    _latest_cs = _hist_cs[-1]
                    for _ch_cs in (_latest_cs.get("changes") or []):
                        if _ch_cs.get("field") == "lsd_accel":
                            try:
                                _to_cs = float(_ch_cs.get("to", 0))
                                _from_cs = float(_ch_cs.get("from", 0))
                                _lsd_pv_cs = _to_cs
                                _lsd_pd_cs = "increase" if _to_cs > _from_cs else "decrease"
                            except (TypeError, ValueError):
                                pass
                            break
            if self._db is not None:
                try:
                    _car_id_cs = int(self._car_id_ref[0]) or 0
                    _track_cs = _event_ctx.get("track") or ""
                    _scored_cs = self._db.get_scored_recs_for_prompt(_car_id_cs, _track_cs, "")
                    for _srec_cs in _scored_cs:
                        _rt_cs = _srec_cs.get("recommendation_text") or ""
                        try:
                            _rd_cs = _json_cs.loads(_rt_cs)
                            for _sch_cs in (_rd_cs.get("changes") or []):
                                if _sch_cs.get("field") == "lsd_accel":
                                    if _srec_cs.get("score_verdict") == "worsened":
                                        _lsd_worsened_cs = True
                                    break
                        except Exception:
                            pass
                        if _lsd_worsened_cs:
                            break
                except Exception:
                    pass
            _rec_history_cs = {
                "lsd_accel": {
                    "prior_value":            _lsd_pv_cs,
                    "prior_direction":        _lsd_pd_cs,
                    "worsened_verdict_exists": _lsd_worsened_cs,
                }
            }
        except Exception:
            _rec_history_cs = None

        history_str = self._get_history_context()
        prompt = self._build_combined_prompt(
            recent, setup_dict, history_str,
            car_name=car_name, car_specs=car_specs or {},
            feeling=feeling,
            allowed_tuning=allowed_tuning, tuning_locked=tuning_locked,
            compound=compound,
            prior_outcomes=prior_outcomes,
            diagnosis=diagnosis,
        )
        _track_da = self._config.get("strategy", {}).get("track", "")
        try:
            _response_text = call_api(prompt, api_key, max_tokens=2500,
                                      feature="Combined Setup",
                                      structured_payload={"lap_count": len(recent),
                                                          "car": car_name,
                                                          "has_setup": bool(setup_dict),
                                                          "has_feeling": bool(feeling)},
                                      model=self._config.get("anthropic", {}).get("model") or None,
                                      car_id=self._car_id_ref[0], track=_track_da)
            # Normalise changes server-side: resolve 'field' key and add
            # 'to_clamped' so the frontend never needs to slug-guess or
            # re-clamp raw AI values; then validate.  Persistence moved AFTER finalisation.
            try:
                _data = _json.loads(_response_text)
                _raw_changes = _data.get("changes") or []
                _setup_fields = _data.get("setup_fields") or {}
                if isinstance(_raw_changes, list) and _raw_changes:
                    _data["changes"] = _normalise_changes(
                        _raw_changes, _setup_fields, car_name
                    )
                # Rebuild setup_fields from surviving normalised changes so stale
                # keys from stripped no-ops never reach the validator or Apply button.
                _normalised_sf: dict = {}
                for _ch in _data.get("changes") or []:
                    _f = _ch.get("field")
                    _tc = _ch.get("to_clamped")
                    if _f and isinstance(_tc, (int, float)):
                        _normalised_sf[_f] = _tc
                _data["setup_fields"] = _normalised_sf
                _locked = _derive_locked_fields(allowed_tuning) if allowed_tuning else None
                _data = _validate_setup_response(
                    _data, car_name, allowed_tuning, _locked, setup_dict
                )
                # C3a: strip locked-field changes from changes + setup_fields so the
                # Apply button can never write a locked value.
                if _locked:
                    _data["changes"] = [
                        _c for _c in (_data.get("changes") or [])
                        if _c.get("field") not in _locked
                    ]
                    _data["setup_fields"] = {
                        _k: _v for _k, _v in (_data.get("setup_fields") or {}).items()
                        if _k not in _locked
                    }

                # Engineering validation + single retry using the strict retry contract
                try:
                    _ranges = resolve_ranges(car_name)
                    _structured_failures = validate_setup_engineering_structured(
                        _data, diagnosis, setup_dict, _ranges, _event_ctx,
                        car_name=car_name,
                        rec_history=_rec_history_cs,
                    )
                    # Only safety-rule failures trigger a retry and zero changes.
                    # Structural/schema/range errors are cosmetic and leave changes visible.
                    _blocking_failures = [
                        f for f in _structured_failures
                        if f.severity == "blocking"
                        and any(f.code.startswith(p) for p in ENG_SAFETY_PREFIXES)
                    ]
                    _fb_used = False
                    _retried = False
                    _failing_ai_changes: "list | None" = None

                    if _blocking_failures:
                        # Build strict retry prompt and attempt one correction
                        _retry_prompt = _build_retry_prompt(
                            prompt, _blocking_failures, setup_dict, _ranges
                        )
                        try:
                            _retry_text = call_api(
                                _retry_prompt, api_key, max_tokens=1500,
                                feature="Combined Setup (retry)",
                                structured_payload={"lap_count": len(recent),
                                                    "car": car_name,
                                                    "has_setup": bool(setup_dict),
                                                    "has_feeling": bool(feeling),
                                                    "retry": True},
                                model=self._config.get("anthropic", {}).get("model") or None,
                                car_id=self._car_id_ref[0], track=_track_da,
                            )
                            _retried = True
                            _retry_data = _json.loads(_retry_text)
                            _rr_ch = _retry_data.get("changes") or []
                            _rr_sf = _retry_data.get("setup_fields") or {}
                            if isinstance(_rr_ch, list) and _rr_ch:
                                _retry_data["changes"] = _normalise_changes(_rr_ch, _rr_sf, car_name)
                                _rr_nsf: dict = {}
                                for _ch2 in _retry_data["changes"]:
                                    _f2 = _ch2.get("field")
                                    _tc2 = _ch2.get("to_clamped")
                                    if _f2 and isinstance(_tc2, (int, float)):
                                        _rr_nsf[_f2] = _tc2
                                _retry_data["setup_fields"] = _rr_nsf
                            _retry_data = _validate_setup_response(
                                _retry_data, car_name, allowed_tuning, _locked, setup_dict
                            )
                            if _locked:
                                _retry_data["changes"] = [
                                    _c for _c in (_retry_data.get("changes") or [])
                                    if _c.get("field") not in _locked
                                ]
                                _retry_data["setup_fields"] = {
                                    _k: _v for _k, _v in (_retry_data.get("setup_fields") or {}).items()
                                    if _k not in _locked
                                }
                            _retry_structured = validate_setup_engineering_structured(
                                _retry_data, diagnosis, setup_dict, _ranges, _event_ctx,
                                car_name=car_name,
                                rec_history=_rec_history_cs,
                            )
                            _retry_blocking = [
                                f for f in _retry_structured
                                if f.severity == "blocking"
                                and any(f.code.startswith(p) for p in ENG_SAFETY_PREFIXES)
                            ]
                            if _retry_blocking:
                                # Still failing after retry — build deterministic fallback
                                _fb_diag = diagnosis or _build_setup_diagnosis_conservative()
                                _fb = _build_deterministic_fallback(_fb_diag, setup_dict, _ranges)
                                _fb_used = True
                                # Capture failing changes before the fallback zeros them out
                                _failing_ai_changes = list(_retry_data.get("changes") or [])
                                _retry_data.update(_fb)
                                _structured_failures = _retry_structured
                            else:
                                _structured_failures = _retry_structured
                                _fb_used = False
                            if diagnosis:
                                _retry_data["diagnosis"] = diagnosis
                            _data = _retry_data
                        except Exception:
                            # Retry API/parse error — fallback to deterministic
                            _fb_diag = diagnosis or _build_setup_diagnosis_conservative()
                            _fb = _build_deterministic_fallback(_fb_diag, setup_dict, _ranges)
                            _fb_used = True
                            # Capture failing changes before the fallback zeros them out
                            _failing_ai_changes = list(_data.get("changes") or [])
                            _data.update(_fb)
                            _retried = True  # We attempted a retry

                    if diagnosis:
                        _data["diagnosis"] = diagnosis

                    # Route through _finalise_recommendation — the single funnel
                    _final = _finalise_recommendation(
                        _data, _structured_failures, _fb_used, _retried,
                        failing_changes=_failing_ai_changes,
                    )
                    # Attach lifecycle status to raw dict for callers that read the JSON
                    _data["recommendation_status"] = _final.status
                    _data["changes"] = _final.approved_changes
                    _data["setup_fields"] = _final.approved_fields
                    _data["engineering_validation_failed"] = _final.status not in APPROVED_STATUSES
                    _data["engineering_validation_errors"] = _final.engineering_errors
                    _data["validation_warnings"] = _final.validation_warnings
                    _data["fallback_used"] = _final.fallback_used
                    _data["rejected_changes"] = _final.rejected_changes

                except Exception:
                    pass  # Engineering validation must not break the response path

                _response_text = _json.dumps(_data, ensure_ascii=False)

                # Persistence after validation — write FINAL status to DB
                if self._db is not None:
                    _session_id = self._session_id_getter()
                    try:
                        _ai_id = self._db._conn.execute(
                            "SELECT MAX(id) FROM ai_interactions"
                        ).fetchone()[0]
                    except Exception:
                        _ai_id = None
                    _recs = parse_recommendations_from_response(
                        _response_text, "Combined Setup",
                        self._car_id_ref[0], _track_da, "",
                        session_id=_session_id, ai_interaction_id=_ai_id,
                    )
                    if _recs:
                        self._db.insert_setup_recommendations(_recs)

            except Exception:
                pass  # If normalisation/validation fails, return the original text unchanged
            return _response_text
        except Exception as e:
            return f"Setup analysis failed: {e}"

    def build_driver_feeling_response(
        self, feeling_text: str, setup_dict: dict,
        car_name: str = "", car_specs: dict | None = None
    ) -> str:
        """Return a JSON string: {"analysis": str, "changes": [{setting,from,to,why}]}."""
        api_key = self._config.get("anthropic", {}).get("api_key", "")
        if not api_key.strip():
            return ("No Anthropic API key set. "
                    "Add your key in the Strategy tab to enable setup advice.")
        if not feeling_text.strip():
            return "Please describe how the car feels first."

        history_str = self._get_history_context()
        prompt = self._build_feeling_prompt(feeling_text.strip(), setup_dict, history_str,
                                            car_name=car_name, car_specs=car_specs or {})
        _track_da = self._config.get("strategy", {}).get("track", "")
        try:
            _response_text = call_api(prompt, api_key, max_tokens=1000,
                                      feature="Handling Analysis",
                                      structured_payload={"car": car_name,
                                                          "has_setup": bool(setup_dict),
                                                          "feeling_length": len(feeling_text)},
                                      model=self._config.get("anthropic", {}).get("model") or None,
                                      car_id=self._car_id_ref[0], track=_track_da)
            if self._db is not None:
                _session_id = self._session_id_getter()
                try:
                    _ai_id = self._db._conn.execute(
                        "SELECT MAX(id) FROM ai_interactions"
                    ).fetchone()[0]
                except Exception:
                    _ai_id = None
                _recs = parse_recommendations_from_response(
                    _response_text, "Handling Analysis",
                    self._car_id_ref[0], _track_da, "",
                    session_id=_session_id, ai_interaction_id=_ai_id,
                )
                if _recs:
                    self._db.insert_setup_recommendations(_recs)
            # Normalise changes server-side: resolve 'field' key and add
            # 'to_clamped'. The feeling path has no setup_fields dict, so
            # _normalise_changes falls back to range-clamping ch["to"] directly.
            try:
                _data = _json.loads(_response_text)
                _raw_changes = _data.get("changes") or []
                if isinstance(_raw_changes, list) and _raw_changes:
                    _data["changes"] = _normalise_changes(
                        _raw_changes, {}, car_name
                    )
                    _response_text = _json.dumps(_data, ensure_ascii=False)
            except Exception:
                pass  # If normalisation fails, return the original text unchanged
            return _response_text
        except Exception as e:
            return f"Setup advice failed: {e}"

    # ------------------------------------------------------------------
    # History context
    # ------------------------------------------------------------------

    def _get_history_context(self) -> str:
        """Return a formatted history string from the session DB, or empty note."""
        if self._db is None:
            return "(Session database not available — no historical context.)"
        try:
            car_id = int(self._car_id_ref[0]) or 0
            track  = self._config.get("strategy", {}).get("track", "") or ""
            return self._db.format_history_for_prompt(car_id, track)
        except Exception as e:
            return f"(History unavailable: {e})"

    def set_event_context(self, event_dict: dict) -> None:
        self._event_ctx = event_dict or {}

    def _get_event_context_block(self) -> str:
        evt = self._event_ctx
        if not evt:
            return ""
        lines = ["## Event Rules"]
        if evt.get("name"):
            lines.append(f"Event: {evt['name']}")
        track = evt.get("track") or self._config.get("strategy", {}).get("track", "")
        if track:
            lines.append(f"Track: {track}")
        race_type = evt.get("race_type", "")
        laps = evt.get("laps", 0)
        duration = evt.get("duration_mins", 0)
        # Favour timed representation: a timed race may also carry a laps value
        # (e.g. when laps_in_race was estimated), but race_type=="timed" takes priority.
        if race_type == "timed":
            lines.append(f"Race: {duration} minutes, Timed Race")
        elif laps:
            lap_word = "lap" if int(laps) == 1 else "laps"
            lines.append(f"Race: {laps} {lap_word}, Lap Race")
        tyre_wear = float(evt.get("tyre_wear", 1.0))
        fuel_mult = float(evt.get("fuel_mult", 1.0))
        if tyre_wear != 1.0 or fuel_mult != 1.0:
            lines.append(f"Tyre wear: {tyre_wear}x | Fuel: {fuel_mult}x")
        bop    = evt.get("bop", False)
        tuning = evt.get("tuning", True)
        lines.append(f"BoP: {'ON' if bop else 'OFF'} | Tuning: {'Allowed' if tuning else 'Locked'}")
        weather = evt.get("weather", "")
        damage  = evt.get("damage", "")
        if weather or damage:
            lines.append(f"Weather: {weather or 'N/A'} | Damage: {damage or 'None'}")
        req_tyres = evt.get("req_tyres", [])
        if isinstance(req_tyres, list) and req_tyres:
            lines.append(f"Required compounds: {', '.join(req_tyres)}")
        elif isinstance(req_tyres, str) and req_tyres:
            lines.append(f"Required compound: {req_tyres}")
        notes = evt.get("notes", "")
        if notes:
            lines.append(f"Notes: {notes}")
        return "\n".join(lines)

    # Keywords that indicate positive progress / relief in a driver feedback field.
    # Substring-matched case-insensitively, consistent with _FEEL_VOCABULARY style.
    _IMPROVING_KEYWORDS: frozenset[str] = frozenset({
        "better", "improved", "improving", "improves", "less", "reduced",
        "more stable", "good", "gone", "fixed", "settling", "hooking up",
    })

    @staticmethod
    def _feedback_trend_tag(rows: list[dict], field: str) -> str:
        """Return a trend label for a single feedback field across multiple rows.

        rows are newest-first (as returned by get_recent_feedback).
        Labels: current | improving | worsening | resolved

        Precedence (checked in order):
          1. resolved  — newest value is neutral/absent AND at least one older
                         value was non-neutral.
          2. improving — newest value is non-empty AND contains positive/relief
                         language (see _IMPROVING_KEYWORDS) AND at least one
                         older value was a non-neutral complaint.
          3. worsening — newest value is non-neutral AND all older values were
                         neutral/absent (i.e. a fresh / escalating complaint).
          4. current   — single entry, unchanged, or none of the above.

        "neutral", "" and None are treated as absence of an issue.
        """
        _NEUTRAL = {"", "neutral", None}
        if not rows or len(rows) == 0:
            return "current"
        vals = [r.get(field) for r in rows]
        if len(rows) == 1:
            return "current"

        newest = vals[0]    # rows[0] is newest (newest-first order)
        older_vals = vals[1:]

        newest_is_neutral = newest in _NEUTRAL
        any_older_non_neutral = any(v not in _NEUTRAL for v in older_vals)

        # 1. Resolved: newest is neutral but something older was a complaint
        if newest_is_neutral and any_older_non_neutral:
            return "resolved"

        # Newest is non-neutral from here on
        if newest_is_neutral:
            # All values are neutral — no issue to track
            return "current"

        # 2. Improving: newest has positive/relief language over a prior complaint
        newest_lower = (newest or "").lower()
        has_positive = any(kw in newest_lower for kw in DrivingAdvisor._IMPROVING_KEYWORDS)
        if has_positive and any_older_non_neutral:
            return "improving"

        # 3. Worsening: newest is a (non-neutral, non-positive) complaint and
        #    all older entries were neutral/absent
        all_older_neutral = not any_older_non_neutral
        if all_older_neutral:
            return "worsening"

        # 4. Current — unchanged value, or mixed non-neutral without positive language
        return "current"

    def _get_driver_feedback_context(self) -> str:
        if self._db is None:
            return ""
        try:
            car_id = int(self._car_id_ref[0]) or 0
            track  = self._config.get("strategy", {}).get("track", "") or ""
            # get_recent_feedback returns newest-first (ORDER BY submitted_at DESC)
            rows   = self._db.get_recent_feedback(car_id, track, limit=5)
            if not rows:
                return ""

            _FEEDBACK_FIELDS = (
                "corner_entry", "mid_corner", "exit_stability",
                "rear_braking", "tyre_condition", "fuel_use",
            )

            def _format_row(row: dict) -> list[str]:
                """Format a single feedback row into a list of parts."""
                parts: list[str] = []
                for field in _FEEDBACK_FIELDS:
                    val = row.get(field, "")
                    if val and val != "neutral":
                        trend = self._feedback_trend_tag(rows, field)
                        parts.append(f"{field.replace('_', ' ')}: {val} [{trend}]")
                notes = (row.get("notes") or "").strip()
                if notes:
                    parts.append(f'"{notes}"')
                rating = (row.get("rating") or "").strip().lower()
                if rating in ("liked", "hated"):
                    setup_id = int(row.get("setup_id") or 0)
                    applied_note = ""
                    if setup_id:
                        try:
                            n = self._db.get_lap_count_for_setup(setup_id)
                        except Exception:
                            n = 0
                        if n > 0:
                            applied_note = f" (applied — driven {n} lap{'s' if n != 1 else ''})"
                    if rating == "liked":
                        parts.append(
                            f"DRIVER LIKED this setup{applied_note} — prefer keeping changes like these.")
                    else:
                        parts.append(
                            f"DRIVER HATED this setup{applied_note} — do not repeat these changes.")
                return parts

            lines: list[str] = ["## Driver Feedback"]

            # B3: split into "Latest feedback" (index 0 = newest) and "Earlier feedback"
            latest_parts = _format_row(rows[0])
            if latest_parts:
                lines.append("### Latest feedback (weight highest)")
                lines.append("- " + ", ".join(latest_parts))

            if len(rows) > 1:
                earlier_lines: list[str] = []
                for row in rows[1:]:
                    ep = _format_row(row)
                    if ep:
                        earlier_lines.append("- " + ", ".join(ep))
                if earlier_lines:
                    lines.append("### Earlier feedback")
                    lines.extend(earlier_lines)

            return "\n".join(lines) if len(lines) > 1 else ""
        except Exception:
            return ""

    def _get_track_intelligence_context(self) -> str:
        """Return Track Intelligence prompt context for this session's selected track/layout."""
        from strategy.track_context_prompt import get_track_context_for_ai
        sc = self._config.get("strategy", {})
        return get_track_context_for_ai(
            sc.get("track_location_id") or "",
            sc.get("layout_id") or "",
            car_name="",  # no car name available in this scope; callers pass it via build_*_response
        )

    def _get_enriched_issue_context(self, laps: list) -> str:
        """Convert recent LapStats to enriched segment-located issue summary.

        Returns "" if no track/layout IDs are set, no issues detected, or
        enrichment produces no resolved matches (warnings still included).
        Never raises.
        """
        try:
            sc = self._config.get("strategy", {})
            loc_id = sc.get("track_location_id") or ""
            lay_id = sc.get("layout_id") or ""
            if not loc_id or not lay_id:
                return ""
            from data.track_issue_enrichment import (
                issues_from_lap_stats,
                enrich_telemetry_issues,
                summarise_enriched_issues_for_prompt,
            )
            raw_issues = issues_from_lap_stats(laps)
            if not raw_issues:
                return ""
            result = enrich_telemetry_issues(raw_issues, loc_id, lay_id)
            return summarise_enriched_issues_for_prompt(result.enriched_issues)
        except Exception:
            return ""

    def _get_live_segment_context(self, live_position=None) -> str:
        """Return a compact live segment prompt block for the current track position.

        live_position: a LivePosition object (from data.live_segment_resolver),
        or None.  When None, returns "" — live segment context is deferred and
        callers must supply the position explicitly.

        Why deferred at analysis time: coaching/setup prompts are triggered by
        user action (pressing "Analyse"), not by a continuous telemetry frame.
        The caller is responsible for supplying the most recent LivePosition if
        live context is desired.  Absence of a position is not an error.
        """
        try:
            sc = self._config.get("strategy", {})
            loc_id = sc.get("track_location_id") or ""
            lay_id = sc.get("layout_id") or ""
            if not loc_id or not lay_id or live_position is None:
                return ""
            from data.live_segment_resolver import get_live_segment_context_for_prompt
            return get_live_segment_context_for_prompt(loc_id, lay_id, live_position)
        except Exception:
            return ""

    def _get_live_coaching_context(self, live_position=None, laps=None) -> str:
        """Return a compact live coaching cue prompt block.

        live_position: LivePosition — required for segment resolution.
        laps: recent LapStats list — used to build enriched issue history.
        Returns "" when no cue fires or position unavailable.
        Never raises.

        Deferred: voice announcement integration.
        """
        try:
            sc = self._config.get("strategy", {})
            loc_id = sc.get("track_location_id") or ""
            lay_id = sc.get("layout_id") or ""
            if not loc_id or not lay_id or live_position is None:
                return ""
            from data.live_segment_resolver import resolve_live_segment
            from data.live_segment_coaching import (
                build_live_coaching_decision,
                format_live_coaching_for_prompt,
            )
            live_result = resolve_live_segment(loc_id, lay_id, live_position)
            enriched_issues = []
            if laps:
                try:
                    from data.track_issue_enrichment import (
                        issues_from_lap_stats,
                        enrich_telemetry_issues,
                    )
                    raw = issues_from_lap_stats(laps)
                    if raw:
                        er = enrich_telemetry_issues(raw, loc_id, lay_id)
                        enriched_issues = er.enriched_issues
                except Exception:
                    pass
            decision = build_live_coaching_decision(live_result, enriched_issues=enriched_issues)
            return format_live_coaching_for_prompt(decision)
        except Exception:
            return ""

    def _get_previous_ai_context(
        self,
        feature: str,
        prior_outcomes: "list[dict] | None" = None,
    ) -> str:
        """Return prior AI context block for injection into prompts.

        When *prior_outcomes* is supplied (list of dicts with keys: setting,
        from_value, to_value, applied (True/False/"unknown"), result
        ("improved"/"worse"/"no_change"/"unknown")), a structured block is
        rendered that instructs the AI not to repeat a prior recommendation
        unless: it was not applied, it improved and needs a further step,
        telemetry still supports the direction, or outcome is unknown.

        When *prior_outcomes* is not supplied, the free-text DB path is used
        unchanged (backward-compatible).
        """
        if prior_outcomes is not None:
            if not prior_outcomes:
                return ""
            lines = ["## Prior Recommended Changes and Outcomes"]
            for po in prior_outcomes:
                setting   = po.get("setting", "?")
                from_val  = po.get("from_value", "?")
                to_val    = po.get("to_value", "?")
                applied   = po.get("applied", "unknown")
                result_   = po.get("result", "unknown")
                applied_s = (
                    "applied" if applied is True
                    else "not applied" if applied is False
                    else "unknown whether applied"
                )
                lines.append(
                    f"  - {setting}: {from_val} → {to_val} | {applied_s} | outcome: {result_}"
                )
            lines.append(
                "\nDo NOT repeat a prior recommendation unless: "
                "(a) it was not applied, "
                "(b) it improved the car and a further step is needed, "
                "(c) current telemetry still strongly supports the same direction, "
                "or (d) the outcome is unknown."
            )
            return "\n".join(lines)

        # Free-text DB path — try OFR-1 scored block first (§6.4), fall back to
        # free-text get_recommendations_for_context on any exception.
        if self._db is None:
            return ""
        try:
            car_id   = int(self._car_id_ref[0]) or 0
            track    = self._config.get("strategy", {}).get("track", "") or ""
            # Recs are stored with empty layout_id; the cross-layout guard matches
            # ''-to-''; no config['strategy'] read permitted here.
            layout_id = ""
            from data.recommendation_scoring import (
                format_performance_block as _fmt_perf,
            )
            scored = self._db.get_scored_recs_for_prompt(car_id, track, layout_id)
            perf_block = _fmt_perf(scored)
            if perf_block:
                return perf_block
        except Exception:
            pass
        try:
            car_id = int(self._car_id_ref[0]) or 0
            track  = self._config.get("strategy", {}).get("track", "") or ""
            joined = self._db.get_recommendations_for_context(car_id, track, limit=2)
            if not joined:
                return ""
            return "## Previous AI Recommendations\n" + joined
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _car_track_header(self, car_name: str, car_specs: dict) -> str:
        """Return a compact car + track line for injection into prompts."""
        track = self._config.get("strategy", {}).get("track", "")
        parts = [car_name] if car_name else []
        if car_specs.get("category"):   parts.append(car_specs["category"])
        if car_specs.get("pp_rating"):  parts.append(f"PP {car_specs['pp_rating']:.0f}")
        if car_specs.get("drivetrain"): parts.append(car_specs["drivetrain"])
        if car_specs.get("aspiration"): parts.append(car_specs["aspiration"])
        if car_specs.get("power_hp"):   parts.append(f"{car_specs['power_hp']} hp")
        if car_specs.get("weight_kg"):  parts.append(f"{car_specs['weight_kg']} kg")
        car_line = "Car: " + " | ".join(parts) if parts else ""
        track_line = build_track_context(track)
        return "\n".join(x for x in [car_line, track_line] if x)

    @staticmethod
    def _cluster_positions(positions: list, threshold_m: float = 15.0) -> list:
        """Group XYZ positions within threshold_m of each other; return [(x,y,z,count)]."""
        clusters: list = []
        for pos in positions:
            for i, (cx, cy, cz, cnt) in enumerate(clusters):
                dist = ((pos[0]-cx)**2 + (pos[1]-cy)**2 + (pos[2]-cz)**2) ** 0.5
                if dist <= threshold_m:
                    # merge into cluster (running centroid)
                    clusters[i] = (
                        (cx*cnt + pos[0]) / (cnt+1),
                        (cy*cnt + pos[1]) / (cnt+1),
                        (cz*cnt + pos[2]) / (cnt+1),
                        cnt + 1,
                    )
                    break
            else:
                clusters.append((pos[0], pos[1], pos[2], 1))
        return clusters

    def _summarize_location_patterns(self, laps: "list[LapStats]") -> str:
        """Return a human-readable string of repeated-location event clusters."""
        if len(laps) < 3:
            return ""
        agg: dict = {
            "lock-up":     [],
            "wheelspin":   [],
            "oversteer":   [],
            "snap-throttle": [],
            "over-braking": [],
        }
        for lap in laps:
            agg["lock-up"].extend(getattr(lap, "lock_up_positions", []))
            agg["wheelspin"].extend(getattr(lap, "wheelspin_positions", []))
            agg["oversteer"].extend(getattr(lap, "oversteer_positions", []))
            agg["snap-throttle"].extend(getattr(lap, "snap_throttle_positions", []))
            agg["over-braking"].extend(getattr(lap, "over_braking_positions", []))

        lines: list[str] = []
        for event_name, positions in agg.items():
            if not positions:
                continue
            clusters = self._cluster_positions(positions)
            total = len(positions)
            n_clusters = len(clusters)
            max_count = max(c[3] for c in clusters)
            lines.append(
                f"  {event_name}: {total} total events concentrated at "
                f"{n_clusters} location{'s' if n_clusters > 1 else ''} "
                f"(hotspot: {max_count} hits)"
            )
        if not lines:
            return ""
        return "Location-based patterns across {} laps:\n{}".format(
            len(laps), "\n".join(lines)
        )

    def _summarize_new_telemetry(self, laps: "list[LapStats]") -> str:
        """Build a compact summary of B1-B6 metrics for prompt injection."""
        if not laps:
            return ""
        lines: list[str] = []

        # B1 — rev limiter
        total_rl = sum(getattr(l, "rev_limiter_count", 0) for l in laps)
        if total_rl > 0:
            # aggregate by gear across all laps
            gear_totals: dict = {}
            for l in laps:
                for g, cnt in getattr(l, "rev_limiter_by_gear", {}).items():
                    gear_totals[g] = gear_totals.get(g, 0) + cnt
            gear_str = ", ".join(
                f"G{g}: {c}" for g, c in sorted(gear_totals.items()) if g > 0
            )
            lines.append(
                f"Rev limiter hits: {total_rl} total across {len(laps)} laps"
                + (f" ({gear_str})" if gear_str else "")
            )

        # B2 — location clustering
        loc_summary = self._summarize_location_patterns(laps)
        if loc_summary:
            lines.append(loc_summary)

        # B3 — over-braking
        total_ob = sum(getattr(l, "over_braking_count", 0) for l in laps)
        total_ar = sum(getattr(l, "abrupt_release_count", 0) for l in laps)
        if total_ob > 0 or total_ar > 0:
            lines.append(
                f"Over-braking events: {total_ob} (100% brake into slow corner); "
                f"abrupt brake releases: {total_ar}"
            )

        # B4 — theoretical max speed
        theoretical_speeds = [
            getattr(l, "car_max_speed_theoretical_kmh", 0.0) for l in laps
            if getattr(l, "car_max_speed_theoretical_kmh", 0.0) > 50
        ]
        if theoretical_speeds:
            theoretical = max(theoretical_speeds)
            actual_max = max((l.max_speed_kmh for l in laps), default=0.0)
            pct = (actual_max / theoretical * 100) if theoretical > 0 else 0
            lines.append(
                f"Theoretical max speed (inferred): {theoretical:.0f} km/h | "
                f"Actual top speed: {actual_max:.0f} km/h ({pct:.0f}% of theoretical)"
            )

        # B5 — tyre radius trend
        radius_laps = [l for l in laps if getattr(l, "avg_tyre_radius", {})]
        if len(radius_laps) >= 2:
            first = radius_laps[0].avg_tyre_radius
            last  = radius_laps[-1].avg_tyre_radius
            trend_parts: list[str] = []
            for corner in ("fl", "fr", "rl", "rr"):
                r0 = first.get(corner, 0.0)
                r1 = last.get(corner, 0.0)
                if r0 > 0.1 and r1 > 0.1:
                    delta_pct = (r1 - r0) / r0 * 100
                    trend_parts.append(f"{corner.upper()}: {r0:.4f}→{r1:.4f} ({delta_pct:+.1f}%)")
            if trend_parts:
                lines.append(
                    "Tyre radius trend (inferred wear proxy — do not over-rely): "
                    + ", ".join(trend_parts)
                )

        # B6 — off-track
        total_ot = sum(getattr(l, "off_track_count", 0) for l in laps)
        if total_ot > 0:
            lines.append(
                f"Road surface deviation events: {total_ot} "
                f"(possible kerb / grass contact — inferred from road normal)"
            )

        return "\n".join(lines) if lines else ""

    _DATA_QUALITY_NOTE = (
        "## Data Quality Note\n"
        "Measured = direct GT7 packet values (fuel, speed, position).\n"
        "Calculated = derived via physics formulas (lock-up/wheelspin = wheel slip threshold; "
        "braking consistency = std-dev of brake points).\n"
        "Estimated = inferred proxies with uncertainty (lateral G = angvel_z × speed / 9.81; "
        "off-track = road normal Y < threshold; tyre wear = radius trend).\n"
        "Do not state estimated values as fact. Qualify with 'may indicate' or 'suggests'."
    )

    def _build_coaching_prompt(
        self, laps: "list[LapStats]", history_str: str,
        car_name: str = "", car_specs: dict | None = None,
        allowed_tuning: "list[str] | None" = None, tuning_locked: bool = False,
        compound: str = "", corner_issues_summary: str = "",
        live_position=None,
    ) -> str:
        car_specs = car_specs or {}
        best = self._recorder.best_lap()
        best_ms = best.lap_time_ms if best else 0

        lap_lines: list[str] = []
        for lap in laps:
            delta = (lap.lap_time_ms - best_ms) / 1000.0 if best_ms else 0
            os_entry = lap.oversteer_count - lap.oversteer_throttle_on_count
            consist_note = (
                "(good)" if 0 <= lap.brake_consistency_m < 15
                else "(needs work)" if lap.brake_consistency_m >= 15
                else "(unmeasured)"
            )
            lap_lines.append(
                f"  Lap {lap.lap_num}: {ms_to_str(lap.lap_time_ms)} ({delta:+.3f}s from best)\n"
                f"    lock-ups [calculated]: {lap.lock_up_count}, "
                f"wheelspin [calculated]: {lap.wheelspin_count}\n"
                f"    snap oversteer [calculated]: {lap.oversteer_count} "
                f"({lap.oversteer_throttle_on_count} throttle-on, {os_entry} entry)\n"
                f"    kerb events [measured]: {lap.kerb_count}, "
                f"bottoming [measured]: {lap.bottoming_count}, "
                f"snap throttle [calculated]: {lap.snap_throttle_count}\n"
                f"    braking consistency [calculated]: "
                f"{'n/a' if lap.brake_consistency_m < 0 else f'{lap.brake_consistency_m:.1f}m'} "
                f"{consist_note}\n"
                f"    top speed [measured]: {lap.max_speed_kmh:.0f} km/h, "
                f"peak lateral G [estimated]: {lap.max_lat_g:.2f}\n"
                f"    avg throttle [measured]: {lap.avg_throttle_pct:.0f}%, "
                f"avg brake [measured]: {lap.avg_brake_pct:.0f}%"
            )

        gt7_ref = load_gt7_reference()
        header = self._car_track_header(car_name, car_specs)
        tuning_block = _tuning_constraint_block(allowed_tuning, tuning_locked)
        event_block  = self._get_event_context_block()
        feedback_block   = self._get_driver_feedback_context()
        prev_ai_block    = self._get_previous_ai_context("Driver Coaching")
        track_intel_block = self._get_track_intelligence_context()
        enriched_issues_block = self._get_enriched_issue_context(laps)
        live_segment_block = self._get_live_segment_context(live_position)
        live_coaching_block = self._get_live_coaching_context(live_position, laps)
        compound_line    = f"Current tyre compound: {compound}" if compound else ""

        extra_sections = "\n\n".join(
            s for s in [track_intel_block, live_segment_block, live_coaching_block,
                        event_block, feedback_block, prev_ai_block,
                        enriched_issues_block or corner_issues_summary] if s
        )

        return f"""You are an elite motorsport driving coach for Gran Turismo 7.

## GT7 Knowledge Base (includes driver's personal style and preferences)
{gt7_ref}

---
{chr(10) + header + chr(10) if header else ""}{chr(10) + compound_line + chr(10) if compound_line else ""}{tuning_block}Analyse the following lap data and give the driver 2–3 specific, actionable coaching points.
Tailor your advice to the driver's known style from the knowledge base above.
Be direct, concise, and practical. Respond in plain spoken English (no markdown, no bullet points).
Keep your response under 5 sentences.

Metric definitions:
- snap oversteer throttle-on = rear broke loose during acceleration (exit technique / LSD / rear ARB)
- snap oversteer entry = rear broke loose on corner entry (too fast in / trail braking issue)
- kerb events = hard suspension hits from aggressive kerb riding (may help or hurt lap time)
- bottoming = chassis hit the ground (ride height / spring rate issue)
- snap throttle = abrupt 100% throttle stab < 100 ms (triggers wheelspin; smoothness needed)
- peak lateral G [estimated] = angvel_z × speed / 9.81 — proxy, may not reflect true G loading

## Recent laps
{chr(10).join(lap_lines)}

## Best lap on record
{ms_to_str(best_ms)}

## Advanced telemetry intelligence
{self._summarize_new_telemetry(laps) or "(insufficient data)"}

## Historical context for this car and track
{history_str}
{chr(10) + extra_sections if extra_sections else ""}
{self._DATA_QUALITY_NOTE}

Focus on the most significant pattern. Reference specific numbers.
Use the driver's vocabulary where appropriate (e.g. "tail is skaty" if rear lock-ups are detected).
If history shows a recurring pattern (e.g. consistently high lock-ups), mention it.
If location-based patterns show clustering, name the type of corner (braking/fast/slow)."""

    def _build_setup_prompt(
        self,
        laps: "list[LapStats]",
        setup: dict,
        history_str: str,
        car_name: str = "",
        car_specs: dict | None = None,
        allowed_tuning: "list[str] | None" = None,
        tuning_locked: bool = False,
        compound: str = "",
        corner_issues_summary: str = "",
        live_position=None,
        prior_outcomes: "list[dict] | None" = None,
        diagnosis: "dict | None" = None,
    ) -> str:
        car_specs = car_specs or {}
        avg_lockups  = mean(l.lock_up_count   for l in laps)
        avg_spins    = mean(l.wheelspin_count  for l in laps)
        avg_consist  = mean(l.brake_consistency_m for l in laps if l.brake_consistency_m >= 0) or -1
        avg_os_total = mean(l.oversteer_count               for l in laps)
        avg_os_ton   = mean(l.oversteer_throttle_on_count   for l in laps)
        avg_os_entry = avg_os_total - avg_os_ton
        avg_kerb     = mean(l.kerb_count        for l in laps)
        avg_bottom   = mean(l.bottoming_count   for l in laps)
        avg_snap     = mean(l.snap_throttle_count for l in laps)
        avg_lat_g    = mean(l.max_lat_g         for l in laps)
        avg_top_spd  = mean(l.max_speed_kmh     for l in laps)

        consist_note = (
            "(good)" if 0 <= avg_consist < 15
            else "(needs work)" if avg_consist >= 15
            else "(unmeasured)"
        )

        # Aggregate position lists across all laps for directives
        _wsp_all = [p for l in laps for p in getattr(l, "wheelspin_positions", [])]
        _stp_all = [p for l in laps for p in getattr(l, "snap_throttle_positions", [])]
        _osp_all = [p for l in laps for p in getattr(l, "oversteer_positions", [])]
        _btp_all = [p for l in laps for p in getattr(l, "bottoming_positions", [])]

        _cfg = getattr(self, "_config", {})
        sc = _cfg.get("strategy", {}) if isinstance(_cfg, dict) else {}
        loc_id = sc.get("track_location_id") or ""
        lay_id = sc.get("layout_id") or ""

        directives_block = _race_engineer_directives(
            avg_lockups=avg_lockups,
            avg_consist=avg_consist,
            avg_snap=avg_snap,
            avg_os_ton=avg_os_ton,
            avg_bottom=avg_bottom,
            car_name=car_name,
            laps_sample_len=len(laps),
            event_ctx=getattr(self, "_event_ctx", {}),
            wheelspin_positions=_wsp_all,
            snap_throttle_positions=_stp_all,
            oversteer_positions=_osp_all,
            bottoming_positions=_btp_all,
            loc_id=loc_id,
            lay_id=lay_id,
            setup=setup,
        )

        # Compute diagnosis if not supplied
        _event_ctx = getattr(self, "_event_ctx", {})
        if diagnosis is None:
            try:
                diagnosis = build_setup_diagnosis(laps, setup, car_name, _event_ctx, None)
            except Exception:
                diagnosis = {}
        diagnosis_block = format_diagnosis_for_prompt(diagnosis) if diagnosis else ""

        setup_block    = format_setup_for_prompt(setup)
        gt7_ref        = load_gt7_reference()
        header         = self._car_track_header(car_name, car_specs)
        tuning_block   = _tuning_constraint_block(allowed_tuning, tuning_locked)
        ranges_block   = _valid_ranges_block(car_name)
        event_block    = self._get_event_context_block()
        feedback_block = self._get_driver_feedback_context()
        prev_ai_block  = self._get_previous_ai_context("Setup Advice", prior_outcomes)
        track_intel_block = self._get_track_intelligence_context()
        enriched_issues_block = self._get_enriched_issue_context(laps)
        live_segment_block = self._get_live_segment_context(live_position)
        compound_line  = f"Current tyre compound: {compound}" if compound else ""
        extra_sections = "\n\n".join(
            s for s in [track_intel_block, live_segment_block, event_block,
                        feedback_block, prev_ai_block,
                        enriched_issues_block or corner_issues_summary] if s
        )

        return f"""You are an expert Gran Turismo 7 car setup engineer.

## GT7 Knowledge Base (includes driver's personal tuning philosophy)
{gt7_ref}

---
{PERSONAL_DRIVER_TUNING_MODEL}
{DRIVER_HARD_CONSTRAINTS}
{chr(10) + header + chr(10) if header else ""}{chr(10) + compound_line + chr(10) if compound_line else ""}{tuning_block}Analyse the driver's telemetry and current car setup. Give 2–4 specific setup changes
tailored to the driver's known style from the knowledge base above.
Use the driver's personal setup order (stabilise braking first, then front response, etc.)
Give EXACT values for every change (e.g. "ARB Front: 5 → 4", not "soften front ARB").
If gearing is relevant (over-revving, under-revving, wrong gear at key corners), include it.

Metric definitions:
- snap oversteer throttle-on [calculated]: rear breaks loose during acceleration (exit phase)
- snap oversteer entry [calculated]: rear breaks loose on entry / trail braking phase
- kerb events [measured]: hard suspension compression from kerb riding
- bottoming events [measured]: chassis ground contact — indicates ride height or spring rate issue
- snap throttle [calculated]: abrupt 0→100% throttle in < 100 ms — triggers wheelspin and yaw
- peak lateral G [estimated]: speed × yaw_rate / 9.81 — proxy for cornering intensity

{diagnosis_block + chr(10) if diagnosis_block else ""}## Telemetry summary ({len(laps)} laps)
Average lock-ups per lap [calculated]:           {avg_lockups:.1f}
Average wheelspin events per lap [calculated]:   {avg_spins:.1f}
Average oversteer events per lap [calculated]:   {avg_os_total:.1f}  ({avg_os_ton:.1f} throttle-on, {avg_os_entry:.1f} entry)
Kerb events per lap [measured]:                  {avg_kerb:.1f}
Bottoming events per lap [measured]:             {avg_bottom:.1f}
Snap throttle applications per lap [calculated]: {avg_snap:.1f}
Peak lateral G (avg best per lap) [estimated]:   {avg_lat_g:.2f} G
Average top speed per lap [measured]:            {avg_top_spd:.0f} km/h
Braking consistency (std-dev) [calculated]:      {'n/a' if avg_consist < 0 else f'{avg_consist:.1f}m'} {consist_note}

## Advanced telemetry intelligence
{self._summarize_new_telemetry(laps) or "(insufficient data)"}

## Current car setup
{setup_block}

## Historical context for this car and track
{history_str}
{chr(10) + extra_sections if extra_sections else ""}
{self._DATA_QUALITY_NOTE}

{ranges_block}
{directives_block}

## Valid setup_fields keys (numeric values only — use ONLY keys for fields you are changing)
arb_front, arb_rear, ride_height_front, ride_height_rear,
springs_front, springs_rear, dampers_front_comp, dampers_front_ext,
dampers_rear_comp, dampers_rear_ext, camber_front, camber_rear,
toe_front, toe_rear, aero_front, aero_rear,
lsd_initial, lsd_accel, lsd_decel, brake_bias,
power_restrictor, ballast_kg, ballast_position,
final_drive, gear_1, gear_2, gear_3, gear_4, gear_5, gear_6

DISPLAY-ONLY (do NOT include in setup_fields or changes):
transmission_max_speed_kmh — shows calculated top speed only; use final_drive / gear_N for real gearbox changes.

Gearbox fields valid ranges: final_drive 2.5–6.0; gear_1..gear_6 each 0.5–4.0 (must strictly decrease gear_1 > gear_2 > … > gear_6).
Optional gearbox advisory (when exact ratios are unknown): include a "gearbox_advice" object:
  {{"action": "shorten|lengthen|preserve", "reason": "one sentence", "suggested_direction": "shorter/taller ratios or preserve"}}

Reply ONLY with valid JSON — no markdown fences, no extra text.
issue_classification values MUST be one of: setup-limited | driver-input-limited | mixed | insufficient-data | not-present
{{
  "analysis": "2–3 sentence plain-English summary of what the telemetry shows and the primary issue.",
  "primary_issue": "single dominant problem in one phrase",
  "issue_classification": {{"bottoming": "setup-limited", "wheelspin": "mixed", "braking_instability": "not-present"}},
  "changes": [
    {{"setting": "Rear Natural Frequency", "field": "springs_rear", "from": "3.50", "to": "3.75", "why": "one-sentence reason", "expected_validation": "bottoming events reduce without making exit traction worse"}}
  ],
  "setup_fields": {{"springs_rear": 3.75}},
  "validation_targets": {{"bottoming_events_per_lap": "reduce by 25-30%", "wheelspin_events_per_lap": "reduce or become less concentrated", "braking_stability": "must remain stable", "driver_feedback": "rear should feel calmer"}},
  "do_not_change_reasoning": ["No brake bias change because braking is stable", "No ride height change because ride height is already at the valid maximum"],
  "confidence": {{"overall": "medium", "reason": "Issues are clear but track model is seed-only"}},
  "driver_feel_match": {{"supported_by_telemetry": true, "explanation": "Driver reports floaty front; aero_front is near minimum — telemetry-supported."}},
  "engineering_diagnosis": {{"aero_platform": "front near-min with floaty feel", "ride_height": "not primary issue", "traction": "wheelspin low", "gearbox": "preserve", "braking": "stable"}},
  "preserve_settings": ["brake_bias"]
}}
In setup_fields include ONLY the fields being changed, with numeric values (not strings).
In changes, "field" MUST be the exact canonical key from the setup_fields list above.
NEVER include transmission_max_speed_kmh in setup_fields or changes."""

    def _build_feeling_prompt(
        self,
        feeling_text: str,
        setup: dict,
        history_str: str,
        car_name: str = "",
        car_specs: dict | None = None,
    ) -> str:
        car_specs = car_specs or {}
        setup_block = format_setup_for_prompt(setup)
        gt7_ref = load_gt7_reference()
        header = self._car_track_header(car_name, car_specs)
        ranges_block = _valid_ranges_block(car_name)

        # Attach recent telemetry snapshot to cross-check driver description
        recent = self._recorder.recent_laps(3)
        if recent:
            avg_os_total = mean(l.oversteer_count             for l in recent)
            avg_os_ton   = mean(l.oversteer_throttle_on_count for l in recent)
            avg_lockups  = mean(l.lock_up_count               for l in recent)
            avg_spins    = mean(l.wheelspin_count              for l in recent)
            avg_kerb     = mean(l.kerb_count                  for l in recent)
            avg_bottom   = mean(l.bottoming_count             for l in recent)
            avg_snap     = mean(l.snap_throttle_count         for l in recent)
            avg_lat_g    = mean(l.max_lat_g                   for l in recent)
            new_telem = self._summarize_new_telemetry(recent)
            telemetry_block = (
                f"Lock-ups per lap: {avg_lockups:.1f}\n"
                f"Wheelspin per lap: {avg_spins:.1f}\n"
                f"Snap oversteer per lap: {avg_os_total:.1f} "
                f"({avg_os_ton:.1f} throttle-on, {avg_os_total - avg_os_ton:.1f} entry)\n"
                f"Kerb events per lap: {avg_kerb:.1f}\n"
                f"Bottoming events per lap: {avg_bottom:.1f}\n"
                f"Snap throttle applications per lap: {avg_snap:.1f}\n"
                f"Peak lateral G (avg): {avg_lat_g:.2f} G"
                + (f"\n{new_telem}" if new_telem else "")
            )
        else:
            telemetry_block = "(No recent lap telemetry available.)"

        prev_ai_block = self._get_previous_ai_context("Handling Analysis")

        return f"""You are an expert Gran Turismo 7 car setup engineer.

## GT7 Knowledge Base (includes driver's personal tuning philosophy and preferences)
{gt7_ref}

---
{chr(10) + header + chr(10) if header else ""}
The driver has described a specific handling problem. Give 2–4 concrete setup changes to fix it.

Rules:
- Address the EXACT complaint — don't give generic advice
- Give EXACT values for every change (e.g. "Rear ARB: 4 → 3", not just "soften rear ARB")
- Use the driver's setup priority order from the knowledge base
- Cross-reference the telemetry — if the data contradicts the feeling (e.g. driver says oversteer
  but lock-ups dominate), call it out and target the telemetry-confirmed issue
- If a corner number is mentioned (T3, T6, etc.) target that type of corner (slow/fast/braking)
- If gearing is relevant to the complaint, include a specific gear ratio or top speed target

## Driver's description of how the car feels
"{feeling_text}"

## Recent telemetry (last 3 laps)
{telemetry_block}

## Current car setup
{setup_block}

{ranges_block}
## Historical context for this car and track
{history_str}
{chr(10) + prev_ai_block if prev_ai_block else ""}
Reply ONLY with valid JSON — no markdown fences, no extra text:
{{
  "analysis": "2–3 sentence plain-English explanation of what is causing the handling problem.",
  "changes": [
    {{"setting": "Setting Name", "field": "arb_rear", "from": "current value", "to": "recommended value", "why": "one-sentence reason"}},
    {{"setting": "Setting Name", "field": "camber_front", "from": "current value", "to": "recommended value", "why": "one-sentence reason"}}
  ]
}}
In changes, "field" MUST be the exact canonical param key (e.g. arb_front, camber_rear, springs_front, lsd_accel, brake_bias, ride_height_front, toe_rear, etc.)."""

    def _build_combined_prompt(
        self,
        laps: "list[LapStats]",
        setup: dict,
        history_str: str,
        car_name: str = "",
        car_specs: dict | None = None,
        feeling: str | None = None,
        allowed_tuning: "list[str] | None" = None,
        tuning_locked: bool = False,
        compound: str = "",
        corner_issues_summary: str = "",
        live_position=None,
        prior_outcomes: "list[dict] | None" = None,
        diagnosis: "dict | None" = None,
    ) -> str:
        """Unified setup-analysis prompt: always includes telemetry; optionally adds feeling."""
        car_specs = car_specs or {}
        avg_lockups  = mean(l.lock_up_count   for l in laps)
        avg_spins    = mean(l.wheelspin_count  for l in laps)
        avg_consist  = mean(l.brake_consistency_m for l in laps if l.brake_consistency_m >= 0) or -1
        avg_os_total = mean(l.oversteer_count               for l in laps)
        avg_os_ton   = mean(l.oversteer_throttle_on_count   for l in laps)
        avg_os_entry = avg_os_total - avg_os_ton
        avg_kerb     = mean(l.kerb_count        for l in laps)
        avg_bottom   = mean(l.bottoming_count   for l in laps)
        avg_snap     = mean(l.snap_throttle_count for l in laps)
        avg_lat_g    = mean(l.max_lat_g         for l in laps)
        avg_top_spd  = mean(l.max_speed_kmh     for l in laps)

        consist_note = (
            "(good)" if 0 <= avg_consist < 15
            else "(needs work)" if avg_consist >= 15
            else "(unmeasured)"
        )

        # B1: gear_note block removed — gearing diagnosis is now handled by
        # _classify_gearing in setup_diagnosis.py and emitted via format_diagnosis_for_prompt.

        # Aggregate position lists across all laps for directives
        _wsp_all = [p for l in laps for p in getattr(l, "wheelspin_positions", [])]
        _stp_all = [p for l in laps for p in getattr(l, "snap_throttle_positions", [])]
        _osp_all = [p for l in laps for p in getattr(l, "oversteer_positions", [])]
        _btp_all = [p for l in laps for p in getattr(l, "bottoming_positions", [])]

        _cfg = getattr(self, "_config", {})
        sc = _cfg.get("strategy", {}) if isinstance(_cfg, dict) else {}
        loc_id = sc.get("track_location_id") or ""
        lay_id = sc.get("layout_id") or ""

        directives_block = _race_engineer_directives(
            avg_lockups=avg_lockups,
            avg_consist=avg_consist,
            avg_snap=avg_snap,
            avg_os_ton=avg_os_ton,
            avg_bottom=avg_bottom,
            car_name=car_name,
            laps_sample_len=len(laps),
            event_ctx=getattr(self, "_event_ctx", {}),
            wheelspin_positions=_wsp_all,
            snap_throttle_positions=_stp_all,
            oversteer_positions=_osp_all,
            bottoming_positions=_btp_all,
            loc_id=loc_id,
            lay_id=lay_id,
            setup=setup,
        )

        feeling_section = ""
        if feeling:
            feeling_section = f"""

## Driver's description of how the car feels
"{feeling}"

Cross-reference the telemetry — if data contradicts the feeling (e.g. driver says oversteer
but lock-ups dominate), call it out and target the telemetry-confirmed issue.
If a corner number is mentioned, target that type of corner (slow/fast/braking zone)."""

        # Compute diagnosis if not supplied (use feeling for driver feel parsing)
        _event_ctx = getattr(self, "_event_ctx", {})
        if diagnosis is None:
            try:
                diagnosis = build_setup_diagnosis(laps, setup, car_name, _event_ctx, feeling)
            except Exception:
                diagnosis = {}
        diagnosis_block = format_diagnosis_for_prompt(diagnosis) if diagnosis else ""

        setup_block    = format_setup_for_prompt(setup)
        gt7_ref        = load_gt7_reference()
        header         = self._car_track_header(car_name, car_specs)
        tuning_block   = _tuning_constraint_block(allowed_tuning, tuning_locked)
        ranges_block   = _valid_ranges_block(car_name)
        event_block    = self._get_event_context_block()
        feedback_block = self._get_driver_feedback_context()
        prev_ai_block  = self._get_previous_ai_context("Setup Advice", prior_outcomes)
        track_intel_block = self._get_track_intelligence_context()
        enriched_issues_block = self._get_enriched_issue_context(laps)
        live_segment_block = self._get_live_segment_context(live_position)
        compound_line  = f"Current tyre compound: {compound}" if compound else ""
        extra_sections = "\n\n".join(
            s for s in [track_intel_block, live_segment_block, event_block,
                        feedback_block, prev_ai_block,
                        enriched_issues_block or corner_issues_summary] if s
        )

        return f"""You are an expert Gran Turismo 7 car setup engineer.

## GT7 Knowledge Base (includes driver's personal tuning philosophy)
{gt7_ref}

---
{PERSONAL_DRIVER_TUNING_MODEL}
{DRIVER_HARD_CONSTRAINTS}
{chr(10) + header + chr(10) if header else ""}{chr(10) + compound_line + chr(10) if compound_line else ""}{tuning_block}Analyse the driver's telemetry and current car setup. Give 2–4 specific setup changes
tailored to the driver's known style from the knowledge base above.
Use the driver's personal setup priority order (stabilise braking first, then front response, etc.)
Give EXACT values for every change (e.g. "ARB Front: 5 → 4", not "soften front ARB").{feeling_section}

Metric definitions:
- snap oversteer throttle-on [calculated]: rear breaks loose during acceleration (exit phase)
- snap oversteer entry [calculated]: rear breaks loose on entry / trail braking phase
- kerb events [measured]: hard suspension compression from kerb riding
- bottoming events [measured]: chassis ground contact — indicates ride height or spring rate issue
- snap throttle [calculated]: abrupt 0→100% throttle in < 100 ms — triggers wheelspin and yaw
- peak lateral G [estimated]: speed × yaw_rate / 9.81 — proxy for cornering intensity

{diagnosis_block + chr(10) if diagnosis_block else ""}## Telemetry summary ({len(laps)} laps)
Average lock-ups per lap [calculated]:           {avg_lockups:.1f}
Average wheelspin events per lap [calculated]:   {avg_spins:.1f}
Average oversteer events per lap [calculated]:   {avg_os_total:.1f}  ({avg_os_ton:.1f} throttle-on, {avg_os_entry:.1f} entry)
Kerb events per lap [measured]:                  {avg_kerb:.1f}
Bottoming events per lap [measured]:             {avg_bottom:.1f}
Snap throttle applications per lap [calculated]: {avg_snap:.1f}
Peak lateral G (avg best per lap) [estimated]:   {avg_lat_g:.2f} G
Average top speed per lap [measured]:            {avg_top_spd:.0f} km/h
Braking consistency (std-dev) [calculated]:      {'n/a' if avg_consist < 0 else f'{avg_consist:.1f}m'} {consist_note}

## Advanced telemetry intelligence
{self._summarize_new_telemetry(laps) or "(insufficient data)"}

## Current car setup
{setup_block}

## Historical context for this car and track
{history_str}
{chr(10) + extra_sections if extra_sections else ""}
{self._DATA_QUALITY_NOTE}

{ranges_block}
{directives_block}

## Valid setup_fields keys (numeric values only — use ONLY keys for fields you are changing)
arb_front, arb_rear, ride_height_front, ride_height_rear,
springs_front, springs_rear, dampers_front_comp, dampers_front_ext,
dampers_rear_comp, dampers_rear_ext, camber_front, camber_rear,
toe_front, toe_rear, aero_front, aero_rear,
lsd_initial, lsd_accel, lsd_decel, brake_bias,
power_restrictor, ballast_kg, ballast_position,
final_drive, gear_1, gear_2, gear_3, gear_4, gear_5, gear_6

DISPLAY-ONLY (do NOT include in setup_fields or changes):
transmission_max_speed_kmh — shows calculated top speed only; use final_drive / gear_N for real gearbox changes.

Gearbox fields valid ranges: final_drive 2.5–6.0; gear_1..gear_6 each 0.5–4.0 (must strictly decrease gear_1 > gear_2 > … > gear_6).
Optional gearbox advisory (when exact ratios are unknown): include a "gearbox_advice" object:
  {{"action": "shorten|lengthen|preserve", "reason": "one sentence", "suggested_direction": "shorter/taller ratios or preserve"}}

Reply ONLY with valid JSON — no markdown fences, no extra text.
issue_classification values MUST be one of: setup-limited | driver-input-limited | mixed | insufficient-data | not-present
{{
  "analysis": "2–3 sentence plain-English summary of what the telemetry shows and the primary issue.",
  "primary_issue": "single dominant problem in one phrase",
  "issue_classification": {{"bottoming": "setup-limited", "wheelspin": "mixed", "braking_instability": "not-present"}},
  "changes": [
    {{"setting": "Rear Natural Frequency", "field": "springs_rear", "from": "3.50", "to": "3.75", "why": "one-sentence reason", "expected_validation": "bottoming events reduce without making exit traction worse"}}
  ],
  "setup_fields": {{"springs_rear": 3.75}},
  "validation_targets": {{"bottoming_events_per_lap": "reduce by 25-30%", "wheelspin_events_per_lap": "reduce or become less concentrated", "braking_stability": "must remain stable", "driver_feedback": "rear should feel calmer"}},
  "do_not_change_reasoning": ["No brake bias change because braking is stable", "No ride height change because ride height is already at the valid maximum"],
  "confidence": {{"overall": "medium", "reason": "Issues are clear but track model is seed-only"}},
  "driver_feel_match": {{"supported_by_telemetry": true, "explanation": "Driver reports floaty front; aero_front is near minimum — telemetry-supported."}},
  "engineering_diagnosis": {{"aero_platform": "front near-min with floaty feel", "ride_height": "not primary issue", "traction": "wheelspin low", "gearbox": "preserve", "braking": "stable"}},
  "preserve_settings": ["brake_bias"]
}}
In setup_fields include ONLY the fields being changed, with numeric values (not strings).
In changes, "field" MUST be the exact canonical key from the setup_fields list above.
NEVER include transmission_max_speed_kmh in setup_fields or changes."""

