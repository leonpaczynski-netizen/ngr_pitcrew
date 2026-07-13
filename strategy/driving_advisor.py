"""Driving coach and setup advisor powered by telemetry data + Claude API.

Flow (Group 42 — Rule-First Setup Brain)
-----------------------------------------
build_combined_setup_response (canonical path):
  1. build_setup_diagnosis → structured diagnosis dict.
  2. build_driver_profile  → DriverProfile from hardcoded constants.
  3. run_rule_engine       → deterministic SetupPlan (proposed + rejected candidates).
  4. plan_to_raw_data      → converts SetupPlan to raw_data dict.
  5. _normalise_changes    → resolves field keys, adds to_clamped.
  6. validate_setup_engineering_structured → engineering validation.
  7. If any BLOCKING failure → _build_deterministic_fallback (NO AI retry).
  8. If API key present and no fallback → build_audit_prompt + call_api (AI audit only).
     parse_audit_response + map_audit_to_finaliser.
  9. _finalise_recommendation → SetupRecommendationResult (single funnel).
 10. Emit JSON with standard keys + new optional: ai_audit, deterministic_plan,
     protected_fields; per-change explainability keys inside each change dict.

build_setup_advice_response (voice path — narration only):
  AI-authored actionable changes are STRIPPED before _normalise_changes via
  _strip_actionable_for_voice.  Status will be blocked_no_safe_recommendation
  or fallback_generated, NEVER approved with AI fields.
  Full rule-first rebuild of the voice path is deferred.

SetupRecommendationResult funnel:
  ANY blocking failure → zeroes approved_changes; AI audit CANNOT un-zero.
  status in APPROVED_STATUSES → surface to driver.

Rule-pack registration: strategy/setup_knowledge_base.register_pack().

Functions
---------
build_last_lap_response()         — rule-based, instant, no API.
build_coaching_response()         — Claude API, uses last 3 laps + session history.
build_setup_advice_response(setup)— voice path, narration-only pending rule-first rebuild.
build_combined_setup_response()   — canonical path: deterministic-first, AI-audit-only.
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
from strategy._setup_constants import (
    ENG_SAFETY_PREFIXES, APPROVED_STATUSES, RULE_ENGINE_VERSION,
    HIGH_TYRE_WEAR_THRESHOLD, HIGH_FUEL_MULTIPLIER_THRESHOLD,
    EVIDENCE_REQUIRED_STATUS,
)
from strategy.setup_ranges import resolve_ranges
from strategy.setup_diagnosis import (
    PERSONAL_DRIVER_TUNING_MODEL,
    DRIVER_HARD_CONSTRAINTS,
    build_setup_diagnosis,
    build_feedback_dispositions,
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

def _indicted_fields(message: str) -> "set[str]":
    """Return the canonical setup field(s) a validation-failure message names.

    Safety-rule failure messages always name the offending field explicitly
    (e.g. "lsd_blocked_driver_feel: AI increases lsd_accel (from 14.0 to 16.0)
    but ..."). Extracting those tokens lets the funnel reject ONLY the
    contradicted field instead of nuking the whole recommendation — so a bad
    LSD proposal no longer discards a valid, aligned final_drive or arb_front
    change in the same response.

    Matching is whole-token (``\\b`` boundaries) against the actionable canonical
    params; display-only fields are excluded (they are never applied anyway).
    Returns an empty set when no field can be localised — the caller treats that
    conservatively (full zero) so an un-attributable safety failure is never a
    silent partial-approve.
    """
    found: "set[str]" = set()
    for _param in _CANONICAL_SETUP_PARAMS:
        if _param in _DISPLAY_ONLY_FIELDS:
            continue
        if _re.search(r"\b" + _re.escape(_param) + r"\b", message):
            found.add(_param)
    return found


def _finalise_recommendation(
    raw_data: dict,
    structured_failures: list,
    fallback_used: bool,
    retried: bool,
    failing_changes: "list | None" = None,
    diagnosis: "dict | None" = None,
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
    #   - safety-rule failures (ENG_SAFETY_PREFIXES) name a specific field and are
    #     rejected PER-FIELD: only the contradicted change is dropped, valid
    #     aligned changes in the same response survive.
    #   - structural failures (malformed_schema, invalid_units, locked-field, …)
    #     indict the WHOLE response — it can't be trusted, so all changes are
    #     zeroed (historical behaviour).
    # EXCEPTION: out-of-range is a WARNING (not blocking) because the clamping
    # mechanism in _normalise_changes guarantees the applied value is in range.
    safety_blocking = [
        f for f in all_blocking
        if any(f.code.startswith(p) for p in ENG_SAFETY_PREFIXES)
    ]
    structural_blocking = [f for f in all_blocking if f not in safety_blocking]

    # Fields indicted by safety failures. If any safety failure cannot be
    # localised to a field, we cannot safely partial-approve → force a full zero.
    blocked_fields: "set[str]" = set()
    safety_unattributable = False
    for _sf in safety_blocking:
        _flds = _indicted_fields(_sf.message)
        if _flds:
            blocked_fields |= _flds
        else:
            safety_unattributable = True

    # A structural blocking, or a safety failure we cannot attribute to a field,
    # forces the historical zero-everything behaviour.
    force_zero_all = bool(structural_blocking) or safety_unattributable

    if force_zero_all:
        # Whole-response distrust — zero approved_changes and force a failed status.
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
    elif safety_blocking:
        # Field-attributed safety failures: drop ONLY the contradicted field(s),
        # keep every other valid, aligned change. Stops one bad field (e.g. an
        # LSD increase that contradicts 'good traction') from discarding valid
        # changes like final_drive or arb_front in the same recommendation.
        approved_changes = [
            ch for ch in raw_changes
            if ch.get("field") not in blocked_fields
            and ch.get("field") not in _DISPLAY_ONLY_FIELDS
        ]
        approved_fields = {
            k: v for k, v in raw_sf.items()
            if k not in blocked_fields and k not in _DISPLAY_ONLY_FIELDS
        }
        rejected_changes = [
            ch for ch in raw_changes if ch.get("field") in blocked_fields
        ]
        engineering_errors = [f.message for f in safety_blocking]
        validation_warnings = [f.message for f in warnings]
        if approved_changes:
            # Some valid changes survived — surface them; the driver sees which
            # field(s) were rejected via engineering_errors.
            status = "approved_with_rejections"
        else:
            # Every proposed change was the contradicted one — nothing to apply.
            status = "retry_failed" if retried else "validation_failed"
            if not analysis:
                analysis = (
                    "Engineering validation rejected every proposed change. "
                    "No changes will be applied."
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

        # ── Phase 3: dominant-problem coherence gate ──────────────────────────
        # A plan whose dominant REQUIRED problem is neither addressed by an
        # approved change nor explicitly deferred must NOT be reported as
        # approved. Surface valid non-dominant changes as partial_recommendation;
        # defer with evidence_required when nothing safe applies.
        _coherence_override = None
        _coherence_note = ""
        _dg = diagnosis or {}
        _dom_key = str(_dg.get("dominant_problem_key", "") or "")
        if _dg.get("dominant_required") and _dom_key:
            try:
                from strategy.setup_diagnosis import DOMINANT_ADDRESSING_FIELDS
                _addr_fields = DOMINANT_ADDRESSING_FIELDS.get(_dom_key, frozenset())
            except Exception:
                _addr_fields = frozenset()
            _addressed = any(ch.get("field") in _addr_fields for ch in approved_changes)
            if not _addressed:
                _dom_readable = str(_dg.get("dominant_problem", _dom_key) or _dom_key)
                _evidence_ok = bool(_dg.get("dominant_evidence_sufficient", True))
                if not _evidence_ok:
                    _coherence_note = (
                        f" Action on the dominant problem ({_dom_readable}) is DEFERRED — "
                        "event-rate and location evidence are insufficient; run more clean "
                        "laps or confirm the track model before changing it."
                    )
                else:
                    _coherence_note = (
                        f" The dominant problem ({_dom_readable}) has no safe rule-based "
                        "change yet — run a targeted test to confirm it."
                    )
                _coherence_override = (
                    "partial_recommendation" if approved_changes else EVIDENCE_REQUIRED_STATUS
                )

        if _coherence_override == EVIDENCE_REQUIRED_STATUS:
            status = EVIDENCE_REQUIRED_STATUS
            approved_changes = []
            approved_fields = {}
            analysis = (analysis or "").rstrip() + _coherence_note
        elif _coherence_override == "partial_recommendation":
            status = "partial_recommendation"
            analysis = (analysis or "").rstrip() + _coherence_note
        elif fallback_used and not approved_changes:
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
# _strip_actionable_for_voice — voice-path safety guard (Group 42)
# ---------------------------------------------------------------------------

def _strip_actionable_for_voice(data: dict) -> dict:
    """Remove all AI-authored actionable setup fields from a voice-path response.

    Voice path is narration-only pending full rule-first migration (Group 42).

    This function is a stronger, dependency-free guarantee that the voice path
    never surfaces AI-authored actionable changes.  It does NOT import or call
    setup_ai_audit — the zeroing happens unconditionally before _normalise_changes
    so it cannot be bypassed.

    The status after _finalise_recommendation will be
    blocked_no_safe_recommendation or fallback_generated, NEVER approved
    with AI-authored fields.  analysis text is preserved for narration.
    """
    stripped = dict(data)
    stripped["changes"] = []
    stripped["setup_fields"] = {}
    return stripped


# ---------------------------------------------------------------------------
# _filter_baseline_artifact_warnings — baseline-path warning suppressor
# ---------------------------------------------------------------------------

# Substrings that identify the two artifact-warning types produced by
# _validate_setup_response when validating a full-field from-scratch baseline.
# These are structural artifacts of the baseline shape, not real safety issues:
#   1. "is a no-op" — fires because gearbox from==to (baseline IS the starting point).
#   2. "too many changes" — fires because a full-field baseline has >4 fields.
# We match by substring on the .message so the filter is stable even if the
# exact error text includes variable field names / counts.
_BASELINE_ARTIFACT_SUBSTRINGS: tuple[str, ...] = (
    "is a no-op",
    "too many changes",
)


def _filter_baseline_artifact_warnings(
    failures: list,
) -> list:
    """Remove warning-severity ValidationFailure entries that are structural
    artifacts of the full-field from-scratch baseline shape.

    ONLY removes entries where BOTH conditions hold:
      - severity == "warning"   (blocking failures are NEVER removed)
      - message contains one of the _BASELINE_ARTIFACT_SUBSTRINGS

    All blocking-severity failures and all other warnings pass through unchanged,
    so every safety rule and genuine engineering check still applies.

    Parameters
    ----------
    failures:
        list[ValidationFailure] from validate_setup_engineering_structured.

    Returns
    -------
    A new filtered list.  Input is not mutated.
    """
    result = []
    for vf in failures:
        if vf.severity == "warning":
            msg_lower = vf.message.lower()
            if any(sub in msg_lower for sub in _BASELINE_ARTIFACT_SUBSTRINGS):
                continue   # drop this artifact warning
        result.append(vf)
    return result


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

        VOICE PATH — NARRATION ONLY (Group 42)
        ---------------------------------------
        AI-authored actionable changes are stripped before _normalise_changes via
        _strip_actionable_for_voice.  Status will be blocked_no_safe_recommendation
        or fallback_generated, NEVER approved with AI fields.  analysis text is
        preserved for spoken narration.

        Full rule-first rebuild of the voice path is deferred (Group 42 deferred).
        Canonical path is build_combined_setup_response.

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
                # Group 42: voice path is narration-only — strip AI-authored actionable
                # changes BEFORE _normalise_changes so they can never reach the driver.
                # Full rule-first rebuild of the voice path is deferred (Group 42 deferred).
                _data = _strip_actionable_for_voice(_data)
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
                                # Per-field salvage: keep the retry's changes whose
                                # field is NOT indicted by a safety failure. Only fall
                                # back to the deterministic response when nothing safe
                                # survives (or a failure can't be localised to a field),
                                # so a single contradicted field no longer discards
                                # valid, aligned changes.
                                _blocked_after_retry: "set[str]" = set()
                                _retry_unattributable = False
                                for _bf in _retry_blocking:
                                    _bf_fields = _indicted_fields(_bf.message)
                                    if _bf_fields:
                                        _blocked_after_retry |= _bf_fields
                                    else:
                                        _retry_unattributable = True
                                _retry_survivors = [
                                    _c for _c in (_retry_data.get("changes") or [])
                                    if _c.get("field") not in _blocked_after_retry
                                ]
                                if _retry_survivors and not _retry_unattributable:
                                    # Valid changes survive — let the funnel drop the
                                    # blocked field(s) and mark approved_with_rejections.
                                    _structured_failures = _retry_structured
                                    _fb_used = False
                                else:
                                    # Nothing safe survives — deterministic fallback.
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
                        diagnosis=diagnosis,
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
        purpose: str = "",
        car_class: str = "",
        drivetrain: str = "",
        historical_setups: "list[dict] | None" = None,
        track_name: str = "",
        fuel_multiplier: float = 1.0,
        refuel_rate_lps: float = 0.0,
        track_profile=None,
        extra_candidates: "list[dict] | None" = None,
    ) -> str:
        """Return a JSON string: {"analysis": str, "changes": [...], "setup_fields": {...}}.

        Group 42 — Rule-First Setup Brain (canonical path):
          The deterministic rule engine runs ALWAYS, even without an API key.
          The AI is called only for an optional audit step when api_key is set.
          Without an API key the rule engine still produces a valid SetupPlan
          and the response will be approved / fallback_generated as appropriate.

        Always uses full telemetry. If *feeling* is provided it is included alongside
        telemetry — never sent alone. Uses up to *n_laps* most recent laps from the recorder.

        Group 45 new optional params:
          purpose:    Session purpose string ("Race"/"Qualifying"/"Practice"/...).
          car_class:  Car class string ("Gr.1"/"Gr.3"/"Gr.4"/"Road Car"/...).
          drivetrain: Explicit drivetrain override ("FR"/"FF"/"MR"/"RR"/"AWD"/...).
                      Precedence: explicit kwarg (non-empty) > CAR_DRIVETRAIN_OVERRIDES > None.
          diagnosis: pre-computed build_setup_diagnosis dict; computed internally if None.
        engineering_validation_failed and engineering_validation_errors keys are added
        to the returned JSON.  The AI audit key (ai_audit) is only present when
        api_key is set and the rule engine did not fall back.
        """
        api_key = self._config.get("anthropic", {}).get("api_key", "")

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

        # --- Group 45: Context resolution ---
        # Tyre wear / fuel from EventContext
        _tyre_wear_multiplier: "float | None"
        try:
            _tyre_wear_raw = _event_ctx.get("tyre_wear", None)
            _tyre_wear_multiplier = float(_tyre_wear_raw) if _tyre_wear_raw is not None else None
        except (TypeError, ValueError):
            _tyre_wear_multiplier = None

        _fuel_multiplier: "float | None"
        try:
            _fuel_raw = _event_ctx.get("fuel_multiplier", None)
            _fuel_multiplier = float(_fuel_raw) if _fuel_raw is not None else None
        except (TypeError, ValueError):
            _fuel_multiplier = None

        _duration_mins: float
        try:
            _duration_mins = float(_event_ctx.get("duration_mins", 0) or 0)
        except (TypeError, ValueError):
            _duration_mins = 0.0

        # Map purpose → SessionType enum
        from strategy.setup_knowledge_base import SessionType as _SessionType, CarClass as _CarClass, DrivetrainType as _DrivetrainType, CAR_DRIVETRAIN_OVERRIDES as _CAR_DT_OVERRIDES
        from data.setup_context import normalise_purpose, SetupPurpose as _SetupPurpose

        _setup_purpose = normalise_purpose(purpose)
        _session_type_enum: "_SessionType | None"
        if _setup_purpose == _SetupPurpose.QUALIFYING:
            _session_type_enum = _SessionType.quali
        elif _setup_purpose == _SetupPurpose.RACE:
            _session_type_enum = _SessionType.race
        elif _setup_purpose == _SetupPurpose.PRACTICE:
            _session_type_enum = _SessionType.practice
        else:
            _session_type_enum = None

        # Map car_class string → CarClass enum
        _car_class_enum: "_CarClass | None"
        _car_class_lower = (car_class or "").lower()
        _cc_map = {
            "gr.1": _CarClass.gr1, "gr1": _CarClass.gr1,
            "gr.2": _CarClass.gr2, "gr2": _CarClass.gr2,
            "gr.3": _CarClass.gr3, "gr3": _CarClass.gr3,
            "gr.4": _CarClass.gr4, "gr4": _CarClass.gr4,
            "road car": _CarClass.road, "road": _CarClass.road,
            "race car": _CarClass.race, "race": _CarClass.race,
        }
        _car_class_enum = _cc_map.get(_car_class_lower.strip()) if _car_class_lower else None

        # Drivetrain precedence: explicit kwarg > CAR_DRIVETRAIN_OVERRIDES > None
        _drivetrain_str: "str | None"
        if drivetrain:
            _drivetrain_str = drivetrain.lower().strip()
        else:
            _drivetrain_str = _CAR_DT_OVERRIDES.get(car_name)

        _drivetrain_enum: "_DrivetrainType | None"
        _dt_map = {
            "fr": _DrivetrainType.fr, "ff": _DrivetrainType.ff,
            "mr": _DrivetrainType.mr, "rr": _DrivetrainType.rr,
            "awd": _DrivetrainType.awd, "4wd": _DrivetrainType.awd, "4x4": _DrivetrainType.awd,
        }
        _drivetrain_enum = _dt_map.get(_drivetrain_str or "") if _drivetrain_str else None

        # Session type string for diagnosis injection
        _session_type_str = (
            _session_type_enum.value if _session_type_enum is not None else ""
        )

        # Inject context keys into diagnosis dict (mutable, setdefault so caller-injected
        # values are not overwritten if diagnosis was pre-computed with them already set)
        if isinstance(diagnosis, dict):
            diagnosis.setdefault("session_type", _session_type_str)
            diagnosis.setdefault(
                "tyre_wear_high",
                _tyre_wear_multiplier is not None and _tyre_wear_multiplier >= HIGH_TYRE_WEAR_THRESHOLD,
            )
            diagnosis.setdefault("tyre_wear_known", _tyre_wear_multiplier is not None)
            diagnosis.setdefault(
                "fuel_known",
                _fuel_multiplier is not None and _fuel_multiplier > 0,
            )
            diagnosis.setdefault("duration_mins", _duration_mins)
            # Group 46: inject fuel_multiplier and fuel_high into diagnosis
            diagnosis.setdefault("fuel_multiplier", _fuel_multiplier)
            diagnosis.setdefault(
                "fuel_high",
                (
                    (_fuel_multiplier or 0.0) >= HIGH_FUEL_MULTIPLIER_THRESHOLD
                    if _fuel_multiplier is not None
                    else False
                ),
            )
            # Group 62: inject no_abs so NoABS1 rule can fire.
            # Event dict key "abs": absent/None → True (ABS allowed by default).
            _abs_raw = _event_ctx.get("abs")
            diagnosis.setdefault("no_abs", not bool(_abs_raw if _abs_raw is not None else True))

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
        # Build the prompt text now — used ONLY for the optional AI audit step.
        # Wrap in try/except so prompt-building failures never abort the
        # deterministic rule-engine flow.
        try:
            prompt = self._build_combined_prompt(
                recent, setup_dict, history_str,
                car_name=car_name, car_specs=car_specs or {},
                feeling=feeling,
                allowed_tuning=allowed_tuning, tuning_locked=tuning_locked,
                compound=compound,
                prior_outcomes=prior_outcomes,
                diagnosis=diagnosis,
            )
        except Exception:
            prompt = ""  # Audit step will be skipped when prompt is empty
        _track_da = self._config.get("strategy", {}).get("track", "")
        # Group 42: deterministic-first flow — rule engine generates the plan;
        # AI is called only for an audit (not to generate changes).
        _response_text = _json.dumps({
            "analysis": "Rule engine error — no response generated.",
            "changes": [],
            "setup_fields": {},
            "recommendation_status": "blocked_no_safe_recommendation",
            "engineering_validation_failed": True,
            "engineering_validation_errors": [],
            "validation_warnings": [],
            "fallback_used": False,
            "rejected_changes": [],
        }, ensure_ascii=False)
        try:
            # ------------------------------------------------------------------
            # Step 1: build DriverProfile and run the deterministic rule engine
            # ------------------------------------------------------------------
            _outcomes: list[dict] = []  # Group 46: initialized here so scope is always valid
            try:
                from strategy.setup_driver_profile import build_driver_profile
                from strategy.setup_rule_engine import run_rule_engine, RuleOutcomeStore
                from strategy.setup_plan import plan_to_raw_data, rejected_to_json
                _profile = build_driver_profile()
                _ranges = resolve_ranges(car_name)
                # Group 46: load learning outcomes from DB and populate RuleOutcomeStore.
                # car key = str(car_id) to match what _process_rule receives.
                _rule_outcome_store = RuleOutcomeStore()
                _car_id_learn = int(self._car_id_ref[0]) or 0
                _track_learn = _event_ctx.get("track") or _track_da or ""
                _layout_learn = _event_ctx.get("layout_id") or ""
                _car_key_learn = str(_car_id_learn) if _car_id_learn > 0 else ""
                _profile_ver_learn = getattr(_profile, "profile_version", "") or ""
                _outcomes: list[dict] = []
                if self._db is not None and _car_id_learn > 0:
                    try:
                        _outcomes = self._db.get_learning_outcomes(
                            _car_id_learn, _track_learn, _layout_learn
                        )
                    except Exception:
                        _outcomes = []
                # Feed outcomes into the store (scoped key)
                for _row in _outcomes:
                    _rid = _row.get("rule_id") or ""
                    if not _rid:
                        continue
                    _verdict = _row.get("verdict") or ""
                    if _verdict == "insufficient_data":
                        continue  # skip — no meaningful signal
                    _rule_outcome_store.record_fire(
                        _rid, _car_key_learn, _track_learn, _profile_ver_learn
                    )
                    if _verdict == "improved":
                        _rule_outcome_store.record_success(
                            _rid, _car_key_learn, _track_learn, _profile_ver_learn
                        )
                    # worsened / neutral → fire only (no success)

                _plan = run_rule_engine(
                    diagnosis or {},
                    setup_dict,
                    _ranges,
                    _profile,
                    allowed_tuning=allowed_tuning,
                    rule_outcome_store=_rule_outcome_store,
                    session_type=_session_type_enum,
                    car_class=_car_class_enum,
                    drivetrain=_drivetrain_enum,
                    tyre_wear_multiplier=_tyre_wear_multiplier,
                    car=_car_key_learn,
                    track=_track_learn,
                    profile_version=_profile_ver_learn,
                )
            except Exception:
                # Rule engine failure → fall through to empty plan (deterministic fallback handles)
                from strategy.setup_rule_engine import SetupPlan
                try:
                    from strategy.setup_plan import plan_to_raw_data, rejected_to_json
                except Exception:
                    plan_to_raw_data = None  # type: ignore[assignment]
                    rejected_to_json = None  # type: ignore[assignment]
                _plan = SetupPlan(proposed=[], rejected_candidates=[], protected_fields=[])
                _profile = None
                _ranges = resolve_ranges(car_name)

            # Build analysis text from prompt context (reuse the prepared prompt text)
            _analysis_text = (
                f"Deterministic rule-first analysis. "
                f"Dominant problem: {(diagnosis or {}).get('dominant_problem', 'unknown')}. "
                f"Rule engine proposed {len(_plan.proposed)} change(s)."
            )
            # Phase 8: context-aware fuel/aero reasoning. The old note ("fuel is not a
            # setup lever") was too absolute — on a fuel-heavy, drag-sensitive circuit
            # aero/gearing DO affect fuel-per-lap and total race time. When that holds,
            # recommend a comparison run (never a fabricated saving); otherwise route
            # fuel to strategy honestly.
            if (diagnosis or {}).get("driver_feel_flags", {}).get("fuel_use_high"):
                try:
                    from strategy.race_time_reasoning import assess_aero_fuel_tradeoff
                    _af_lo, _af_hi = resolve_ranges(car_name).get("aero_front", (0, 1000))
                    _rt = assess_aero_fuel_tradeoff(
                        fuel_multiplier=fuel_multiplier, refuel_rate_lps=refuel_rate_lps,
                        track_profile=track_profile,
                        aero_front_value=(diagnosis or {}).get("aero_front_value"),
                        aero_front_lo=_af_lo, aero_front_hi=_af_hi,
                        fuel_use_high=True,
                    )
                except Exception:
                    _rt = None
                if _rt is not None and _rt.fuel_relevant_to_setup:
                    _analysis_text += " " + _rt.as_note()
                else:
                    _analysis_text += (
                        " Note: you flagged higher-than-expected fuel use — on this "
                        "circuit it is primarily a driving/strategy matter (review it in "
                        "the Strategy tab); setup drag is not the limiting factor here."
                    )

            # Phase 11/12 dispositions: explain feedback that received NO setup change
            # (LSD deferred, rear lock) instead of silently omitting it.
            _dg = diagnosis or {}
            _flags = _dg.get("driver_feel_flags", {}) or {}
            _proposed_fields = {getattr(c, "field", None) for c in getattr(_plan, "proposed", [])}
            _ws_band = _dg.get("wheelspin_band", "low")
            _ws_subtype = _dg.get("wheelspin_subtype", "insufficient_data")
            if _ws_band != "low" and "lsd_accel" not in _proposed_fields:
                if _ws_subtype == "gear_too_short_spin":
                    _analysis_text += (
                        " LSD accel change DEFERRED — the wheelspin is gear-too-short; "
                        "test the gearing (final drive) change first before touching the "
                        "differential."
                    )
                elif _flags.get("rear_loose_on_exit"):
                    _analysis_text += (
                        " LSD accel change DEFERRED — you reported the rear loose on "
                        "throttle, so adding accel-locking is unsafe (it would worsen "
                        "power oversteer)."
                    )
                elif _ws_subtype in ("insufficient_data", "mixed"):
                    _analysis_text += (
                        " LSD accel change DEFERRED — confirm whether the traction loss is "
                        "isolated inside-wheel spin or whole-axle power oversteer before "
                        "changing the differential."
                    )
            if (_flags.get("braking_instability")
                    and "brake_bias" not in _proposed_fields
                    and "lsd_decel" not in _proposed_fields):
                _analysis_text += (
                    " Rear lock under braking NOTED — brake bias cannot move rearward "
                    "during braking instability (safety invariant); confirm straight-line "
                    "vs trail-braking lock (and downshift timing) before changing brake "
                    "balance or LSD braking."
                )

            # Phase 9: compare the rule-engine's proposed changes against the
            # driver's PROVEN successful setups and flag any material deviation
            # (e.g. recommending LSD accel 17 vs a proven 8). Advisory only — it
            # never changes the deterministic plan, only explains it.
            _hist_rows = []
            _prior = {}
            if historical_setups:
                try:
                    from strategy.setup_history_intelligence import (
                        find_historical_setups, build_historical_prior, compare_to_history,
                    )
                    _matches = find_historical_setups(
                        car_name, track_name, str((diagnosis or {}).get("layout_id", "") or ""),
                        purpose or "", historical_setups, car_category=car_class,
                    )
                    _prior = build_historical_prior(_matches)
                    _rec_fields = {getattr(c, "field", None): getattr(c, "to_value", None)
                                   for c in getattr(_plan, "proposed", [])}
                    _hist_rows = compare_to_history(setup_dict, _rec_fields, _prior)
                    _flagged = [r for r in _hist_rows if r.deviation_flagged]
                    if _flagged:
                        _analysis_text += (
                            " Historical check: " + "; ".join(r.note for r in _flagged) + "."
                        )
                except Exception:
                    _hist_rows = []

            # ------------------------------------------------------------------
            # Step 2: convert plan to raw_data shape
            # ------------------------------------------------------------------
            try:
                if plan_to_raw_data is None:
                    raise RuntimeError("plan_to_raw_data not available")
                _data = plan_to_raw_data(_plan, diagnosis or {}, _analysis_text)
            except Exception:
                _data = {
                    "analysis": _analysis_text,
                    "primary_issue": (diagnosis or {}).get("dominant_problem", "unknown"),
                    "changes": [],
                    "setup_fields": {},
                    "diagnosis": diagnosis or {},
                }

            # ------------------------------------------------------------------
            # Step 3: normalise changes (resolve field keys, add to_clamped)
            # ------------------------------------------------------------------
            try:
                _raw_changes = _data.get("changes") or []
                _setup_fields = _data.get("setup_fields") or {}
                if isinstance(_raw_changes, list) and _raw_changes:
                    _data["changes"] = _normalise_changes(
                        _raw_changes, _setup_fields, car_name
                    )
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
                if _locked:
                    _data["changes"] = [
                        _c for _c in (_data.get("changes") or [])
                        if _c.get("field") not in _locked
                    ]
                    _data["setup_fields"] = {
                        _k: _v for _k, _v in (_data.get("setup_fields") or {}).items()
                        if _k not in _locked
                    }
            except Exception:
                pass  # normalisation failure must not break the response path

            # ------------------------------------------------------------------
            # Step 4: engineering validation
            # ------------------------------------------------------------------
            _fb_used = False
            _failing_ai_changes: "list | None" = None
            _audit = None

            # Preserve bare try/except around validation (existing convention)
            try:
                _structured_failures = validate_setup_engineering_structured(
                    _data, diagnosis, setup_dict, _ranges, _event_ctx,
                    car_name=car_name,
                    rec_history=_rec_history_cs,
                )
                _blocking_failures = [
                    f for f in _structured_failures
                    if f.severity == "blocking"
                    and any(f.code.startswith(p) for p in ENG_SAFETY_PREFIXES)
                ]

                # Step 5: blocking → deterministic fallback (NO AI retry)
                if _blocking_failures:
                    _fb_diag = diagnosis or _build_setup_diagnosis_conservative()
                    _fb = _build_deterministic_fallback(_fb_diag, setup_dict, _ranges)
                    _fb_used = True
                    _failing_ai_changes = list(_data.get("changes") or [])
                    _data.update(_fb)

                if diagnosis:
                    _data["diagnosis"] = diagnosis

                # Step 6: optional AI audit (only when no fallback + api_key present)
                _audit_status_hint: str = ""
                _audit_extra_warnings: list = []
                if api_key and not _fb_used and prompt:
                    try:
                        from strategy.setup_ai_audit import (
                            build_audit_prompt,
                            parse_audit_response,
                            map_audit_to_finaliser,
                        )
                        _rejected_json = rejected_to_json(_plan) if rejected_to_json else []
                        _audit_prompt = build_audit_prompt(
                            diagnosis or {},
                            _plan,
                            setup_dict,
                            _profile,
                            _structured_failures,
                            _rejected_json,
                            _plan.protected_fields,
                        )
                        _audit_text = call_api(
                            # 800 tokens truncated audit JSON mid-string on richer
                            # plans (UAT: "Unterminated string"); 1500 gives headroom.
                            _audit_prompt, api_key, max_tokens=1500,
                            feature="Setup Audit",
                            structured_payload={"lap_count": len(recent),
                                                "car": car_name,
                                                "has_setup": bool(setup_dict),
                                                "has_feeling": bool(feeling),
                                                "audit": True},
                            model=self._config.get("anthropic", {}).get("model") or None,
                            car_id=self._car_id_ref[0], track=_track_da,
                        )
                        _audit = parse_audit_response(_audit_text, _CANONICAL_SETUP_PARAMS)
                        _audit_status_hint, _audit_extra_warnings = map_audit_to_finaliser(
                            _audit, has_blocking_validation=bool(_blocking_failures)
                        )
                        _data["ai_audit"] = _audit._asdict()
                    except Exception:
                        _audit = None  # Audit failure must never break the response path

                # Step 7: route through _finalise_recommendation — single funnel (unchanged)
                _final = _finalise_recommendation(
                    _data, _structured_failures, _fb_used, retried=False,
                    failing_changes=_failing_ai_changes,
                    diagnosis=diagnosis,
                )

                # Step 8: optional audit-based status upgrade
                # Blocking already zeroed changes — audit CANNOT un-zero.
                _final_status = _final.status
                _final_warnings = list(_final.validation_warnings)
                if (
                    _audit is not None
                    and _final.status in APPROVED_STATUSES
                    and not _blocking_failures
                    and _audit_status_hint == "approved_with_warnings"
                    and _final.status == "approved"
                ):
                    _final_status = "approved_with_warnings"
                    _final_warnings = list(_audit_extra_warnings) + _final_warnings

                # Attach lifecycle status to raw dict
                _data["recommendation_status"] = _final_status
                _data["changes"] = _final.approved_changes
                _data["setup_fields"] = _final.approved_fields
                _data["engineering_validation_failed"] = _final_status not in APPROVED_STATUSES
                _data["engineering_validation_errors"] = _final.engineering_errors
                _data["validation_warnings"] = _final_warnings
                _data["fallback_used"] = _final.fallback_used
                _rj_extra: list = []
                try:
                    if rejected_to_json is not None and _plan.rejected_candidates:
                        _rj_extra = rejected_to_json(_plan)
                except Exception:
                    pass
                _data["rejected_changes"] = list(_final.rejected_changes) + _rj_extra
                # Phase 4: explicit disposition for every reported feedback item.
                _data["feedback_dispositions"] = build_feedback_dispositions(
                    diagnosis, {c.get("field") for c in _final.approved_changes}
                )
                # Phase 10: cross-symptom arbitration over the FINAL proposed set —
                # flag when several changes push the front/rear balance the same way
                # (overshoot risk) or offset each other. Advisory only.
                try:
                    from strategy.setup_arbitration import analyse_change_interactions
                    _arb = analyse_change_interactions(_final.approved_changes)
                    _data["arbitration"] = {
                        "compounding": _arb.compounding,
                        "offsetting": _arb.offsetting,
                        "net_direction": _arb.net_direction,
                        "contributors": list(_arb.contributors),
                        "notes": list(_arb.notes),
                    }
                    if _arb.compounding and _arb.as_note():
                        _data["analysis"] = (str(_data.get("analysis", "")).rstrip()
                                             + " " + _arb.as_note()).strip()
                except Exception:
                    _data["arbitration"] = {}

                # Phase 13: controlled test sequence — order the approved changes into
                # a one-at-a-time programme with success criteria + rollback.
                try:
                    from strategy.setup_test_plan import (
                        build_test_sequence, test_sequence_to_json,
                    )
                    _seq = build_test_sequence(_data.get("changes") or [], diagnosis)
                    _data["test_sequence"] = test_sequence_to_json(_seq)
                except Exception:
                    _data["test_sequence"] = {"note": "", "stages": []}

                # Phase 14: candidate comparison — current vs proven-historical vs
                # rule-recommended, per field. Only candidates actually computed here
                # are shown; base/race/quali slot in when supplied. Never fabricated.
                try:
                    from strategy.setup_candidates import (
                        make_candidate, build_candidate_comparison,
                        candidate_comparison_to_json,
                    )
                    _hist_values = {f: d.get("value") for f, d in (_prior or {}).items()}
                    # Focus on fields actually under discussion (changed or with a
                    # proven prior) — not the whole current setup.
                    _focus = list(dict.fromkeys(
                        list(_final.approved_fields) + list(_hist_values)))
                    _current_focus = {f: setup_dict.get(f) for f in _focus}
                    _cands = [
                        make_candidate("current", "Current", _current_focus, source="on-car now"),
                        make_candidate("recommended", "Recommended (rules)",
                                       _final.approved_fields,
                                       source=f"rule engine {RULE_ENGINE_VERSION}"),
                        make_candidate("historical", "Proven (history)", _hist_values,
                                       source="your liked/strong-result setups"),
                    ]
                    # Caller-supplied candidate columns (e.g. base / race / quali setups
                    # from the UI). Each is {name, label, source, values}; scoped to the
                    # same focus fields so the table stays about the fields in question.
                    for _ex in (extra_candidates or []):
                        try:
                            _ex_vals = {f: (_ex.get("values") or {}).get(f) for f in _focus}
                            _cands.append(make_candidate(
                                str(_ex.get("name", "extra")),
                                str(_ex.get("label", _ex.get("name", "extra"))),
                                _ex_vals, source=str(_ex.get("source", ""))))
                        except Exception:
                            continue
                    _cmp = build_candidate_comparison(
                        [c for c in _cands if c.available], fields=_focus)
                    _data["candidate_comparison"] = candidate_comparison_to_json(_cmp)
                except Exception:
                    _data["candidate_comparison"] = {"columns": [], "rows": []}

                # Phase 7: qualifying-discipline surface — when this is a qualifying
                # session, state the one-lap objective, what it buys, what it trades
                # away, and the plain "do not race it" warning.
                try:
                    from strategy.qualifying_discipline import (
                        build_qualifying_brief, qualifying_brief_to_json,
                    )
                    from strategy.setup_baseline import _SESSION_BIAS_TABLE
                    if str(_session_type_str).lower().startswith("qual") or \
                       "qual" in str(purpose or "").lower():
                        _qb = build_qualifying_brief(
                            "qualifying", _SESSION_BIAS_TABLE.get("qualifying", {}))
                        _data["qualifying_brief"] = qualifying_brief_to_json(_qb)
                        if _qb.one_lap_warning:
                            _data["analysis"] = (str(_data.get("analysis", "")).rstrip()
                                                 + " " + _qb.one_lap_warning).strip()
                    else:
                        _data["qualifying_brief"] = {"is_qualifying": False}
                except Exception:
                    _data["qualifying_brief"] = {"is_qualifying": False}
                # Phase 9: current/historical/recommended comparison (advisory).
                _data["historical_comparison"] = [
                    {"field": r.field, "current": r.current, "historical": r.historical,
                     "recommended": r.recommended, "source": r.source, "tier": r.tier,
                     "confidence": r.confidence, "deviation_flagged": r.deviation_flagged,
                     "note": r.note}
                    for r in _hist_rows
                ]

                # Group 63: surface the bottoming IMPACT verdict (consequence, not
                # just an event count) so the driver sees why bottoming was or was
                # not prioritised.
                _bimpact = (diagnosis or {}).get("bottoming_impact")
                if isinstance(_bimpact, dict):
                    _data["bottoming_impact"] = dict(_bimpact)

                # Group 63: complete LSD triplet assessment — Initial / Acceleration /
                # Braking evaluated independently against the proven same-car prior,
                # each with an executable controlled test. Advisory: it authors no
                # values; the rule-first engine + Apply gate are unchanged.
                try:
                    from strategy.lsd_reasoning import build_lsd_triplet_assessment
                    _lsd = build_lsd_triplet_assessment(diagnosis or {}, setup_dict, _prior)
                    _data["lsd_assessment"] = _lsd.as_json()
                    if _lsd.controlled_tests:
                        _data.setdefault("_targeted_tests", []).extend(_lsd.controlled_tests)
                except Exception:
                    pass

                # New Group 42 keys
                _data["deterministic_plan"] = {
                    "proposed_count": len(_plan.proposed),
                    "rejected_candidate_count": len(_plan.rejected_candidates),
                    "protected_fields": list(_plan.protected_fields),
                    "driver_profile_version": getattr(_profile, "profile_version", None),
                    "rule_engine_version": RULE_ENGINE_VERSION,
                }
                _data["protected_fields"] = list(_plan.protected_fields)
                _data["rule_engine_version"] = RULE_ENGINE_VERSION
                # Group 46: honest learning note — reflect real outcomes loaded
                _n_outcomes = len(_outcomes)
                if _n_outcomes > 0:
                    _data["_learning_note"] = (
                        f"{_n_outcomes} learning record(s) applied — "
                        f"confidence adjusted where samples and success rate warrant"
                    )
                else:
                    _data["_learning_note"] = "no cross-session learning history available"
                # Group 47: honest outcome-verification explanation (confidence/
                # ranking/explanation only — never authors values or bypasses
                # validation).  Empty string when there is nothing to say.
                try:
                    from strategy.setup_outcome_verification import (
                        format_learning_outcome_explanation,
                    )
                    _data["_learning_outcome_explanation"] = (
                        format_learning_outcome_explanation(_outcomes)
                    )
                except Exception:
                    _data["_learning_outcome_explanation"] = ""
                # Group 45: tyre/fuel context availability note
                _tyre_fuel_note: str
                if not (diagnosis or {}).get("tyre_wear_known", False):
                    _tyre_fuel_note = "tyre/fuel context not available — conservative default applied"
                else:
                    _tyre_fuel_note = ""
                _data["_tyre_fuel_context"] = _tyre_fuel_note

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

            return _response_text
        except Exception as e:
            return f"Setup analysis failed: {e}"

    def build_baseline_setup_response(
        self,
        car_name: str,
        ranges: dict,
        drivetrain: str,
        num_gears: int,
        allowed_tuning: "list[str] | None",
        tuning_locked: bool,
        session_type: str = "Race",
        tyre_wear_multiplier: "float | None" = None,
        car_class: str = "",
        duration_mins: float = 0.0,
        track_profile=None,
        track_name: str = "",
        layout_id: str = "",
        historical_setups: "list[dict] | None" = None,
    ) -> str:
        """Return a JSON string with a from-scratch baseline setup.

        No telemetry required, no API call made.  Produces a neutral starting
        point with driver-profile mechanical nudges, routed through the SAME
        _finalise_recommendation / validate_setup_engineering_structured funnel
        as the analyse path so the JSON shape is identical.

        Parameters
        ----------
        car_name:
            Car name — passed through for validator context; ranges must already
            be resolved by the caller (pass resolve_ranges(car_name) as ranges).
        ranges:
            Per-car ranges dict from resolve_ranges(car_name).
        drivetrain:
            Drivetrain code, e.g. "FR", "FF", "MR", "AWD".
        num_gears:
            Number of gear ratios (0–6; >6 capped at 6).
        allowed_tuning:
            List of tuning category codes allowed by the event rules, or None.
        tuning_locked:
            If True, returns a valid JSON with empty changes/setup_fields.
        session_type:
            Session type string ("Race" / "Qualifying" / "Practice").
            Wired through to build_baseline_setup for session_influence labelling.
        tyre_wear_multiplier:
            Optional tyre-wear multiplier. Passed to build_baseline_setup;
            currently accepted for forward-compatibility.
        car_class:
            Car class string (e.g. "Gr.3"). Passed to build_baseline_setup;
            currently accepted for forward-compatibility.
        duration_mins:
            Session duration in minutes (e.g. 60.0 for an hour race).
            Passed to build_baseline_setup for session_type classification
            (e.g. race + duration>=60 → endurance bias). Default 0.0 = unknown.

        Returns
        -------
        JSON string with keys matching build_combined_setup_response:
            recommendation_status, changes, setup_fields, rejected_changes,
            engineering_validation_failed, engineering_validation_errors,
            validation_warnings, fallback_used, deterministic_plan,
            protected_fields, rule_engine_version, analysis, primary_issue,
            diagnosis, confidence.
        """
        # Function-local import to avoid module-level circular dependency:
        # setup_baseline imports _derive_locked_fields FROM driving_advisor at
        # function-call time, not at module import time.
        from strategy.setup_baseline import build_baseline_setup
        from strategy.setup_driver_profile import build_driver_profile

        _error_response = _json.dumps({
            "analysis": "Baseline generation failed — internal error.",
            "changes": [],
            "setup_fields": {},
            "recommendation_status": "blocked_no_safe_recommendation",
            "engineering_validation_failed": True,
            "engineering_validation_errors": [],
            "validation_warnings": [],
            "fallback_used": False,
            "rejected_changes": [],
            "deterministic_plan": {
                "proposed_count": 0,
                "rejected_candidate_count": 0,
                "protected_fields": [],
                "driver_profile_version": None,
                "rule_engine_version": RULE_ENGINE_VERSION,
            },
            "protected_fields": [],
            "rule_engine_version": RULE_ENGINE_VERSION,
        }, ensure_ascii=False)

        try:
            # Step 1: build driver profile
            _profile = build_driver_profile()

            # Step 2: build the baseline raw_data dict
            # Group 45: wire session_type, tyre_wear_multiplier, car_class through
            # Group 46: also wire duration_mins through for session bias classification
            # Phase 9 baseline lift: seed personal-fit geometry (camber/toe) from the
            # driver's STRONG proven history so the from-scratch base starts from a
            # validated value, not a neutral guess. Strong-scope only; never touches
            # safety diffs / aero / brakes / gearing.
            _seed_overrides = {}
            if historical_setups:
                try:
                    from strategy.setup_history_intelligence import (
                        find_historical_setups, build_historical_prior,
                        build_baseline_seed_overrides,
                    )
                    _bl_matches = find_historical_setups(
                        car_name, track_name, layout_id, session_type,
                        historical_setups, car_category=car_class,
                    )
                    _seed_overrides = build_baseline_seed_overrides(
                        build_historical_prior(_bl_matches))
                except Exception:
                    _seed_overrides = {}

            _raw_data = build_baseline_setup(
                car_name, ranges, drivetrain, num_gears,
                _profile, allowed_tuning, tuning_locked,
                session_type=session_type,
                tyre_wear_multiplier=tyre_wear_multiplier,
                car_class=car_class,
                duration_mins=duration_mins,
                track_profile=track_profile,
                historical_seed_overrides=_seed_overrides,
            )

            # Step 3: neutral_setup = the proposed setup_fields (no delta
            # from seed — the baseline IS the proposed setup)
            _neutral_setup = dict(_raw_data.get("setup_fields") or {})

            # Step 4: engineering validation
            # Pass empty diagnosis and event_ctx (no telemetry — by design).
            # validate_setup_engineering_structured never raises.
            _structured_failures = validate_setup_engineering_structured(
                _raw_data,
                diagnosis={},
                setup=_neutral_setup,
                ranges=ranges,
                event_ctx={},
                car_name=car_name,
                rec_history=None,
            )

            # Step 5a: filter out structural artifact warnings that are
            # meaningless for a full-field from-scratch baseline.
            # CRITICAL: only warning-severity entries matching the two known
            # artifact patterns are removed; every blocking failure passes
            # through unfiltered so safety checks still zero approved_changes.
            _filtered_failures = _filter_baseline_artifact_warnings(
                _structured_failures
            )

            # Step 5b: route through _finalise_recommendation (single funnel)
            _final = _finalise_recommendation(
                _raw_data,
                _filtered_failures,
                fallback_used=False,
                retried=False,
            )

            # Step 6: build the response dict mirroring build_combined_setup_response
            _resp: dict = dict(_raw_data)
            _resp["recommendation_status"] = _final.status
            _resp["changes"] = _final.approved_changes
            _resp["setup_fields"] = _final.approved_fields
            _resp["engineering_validation_failed"] = _final.status not in APPROVED_STATUSES
            _resp["engineering_validation_errors"] = _final.engineering_errors
            _resp["validation_warnings"] = _final.validation_warnings
            _resp["fallback_used"] = _final.fallback_used
            _resp["rejected_changes"] = list(_final.rejected_changes)
            # No AI audit for the baseline path
            _resp["ai_audit"] = None
            _resp["deterministic_plan"] = {
                "proposed_count": len(_final.approved_changes),
                "rejected_candidate_count": len(_final.rejected_changes),
                "protected_fields": [],
                "driver_profile_version": getattr(_profile, "profile_version", None),
                "rule_engine_version": RULE_ENGINE_VERSION,
            }
            _resp["protected_fields"] = []
            _resp["rule_engine_version"] = RULE_ENGINE_VERSION

            # Phase 7: qualifying-discipline surface — on a qualifying baseline the
            # applied deltas ARE the quali bias, so the brief is exactly accurate.
            try:
                from strategy.qualifying_discipline import (
                    build_qualifying_brief, qualifying_brief_to_json,
                )
                from strategy.setup_baseline import (
                    _SESSION_BIAS_TABLE, _normalise_session_for_bias,
                )
                _cat = _normalise_session_for_bias(session_type, duration_mins)
                _qb = build_qualifying_brief(
                    _cat, _SESSION_BIAS_TABLE.get(_cat, {}))
                _resp["qualifying_brief"] = qualifying_brief_to_json(_qb)
                if _qb.is_qualifying and _qb.one_lap_warning:
                    _resp["analysis"] = (str(_resp.get("analysis", "")).rstrip()
                                         + " " + _qb.one_lap_warning).strip()
            except Exception:
                _resp["qualifying_brief"] = {"is_qualifying": False}

            return _json.dumps(_resp, ensure_ascii=False)

        except Exception as _exc:
            return _error_response

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
        # Group 62: no-ABS coaching block — only when ABS is explicitly disabled.
        _abs_ctx = evt.get("abs")
        if _abs_ctx is not None and not bool(_abs_ctx):
            lines.append(
                "ABS: DISABLED — threshold braking required. "
                "Control rear lock via LSD decel, not front bias. "
                "Avoid front lock-up. "
                "Coaching intent: if locking, ease brake pressure; "
                "if clean, you have margin to add pressure or brake later."
            )
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

