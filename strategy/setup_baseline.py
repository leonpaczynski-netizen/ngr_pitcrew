"""From-scratch baseline setup generator — Group 44.

Produces a neutral starting-point setup with driver-profile mechanical nudges
when no telemetry data exists. This is the server-side half of the "Build
from scratch" feature; the UI is a separate follow-up agent.

Design
------
- NEUTRAL_SEEDS is the single source of truth for all non-gearbox fields.
  Values were verified against ui/setup_form_widget.py lines ~229-282 and
  strategy/ai_planner.py lines ~2162-2202 on 2026-07-06.
- build_baseline_setup() produces a raw_data dict in the same shape as
  setup_plan.plan_to_raw_data() so it can be routed through the SAME
  _finalise_recommendation / validate_setup_engineering_structured funnel
  as the analyse path.
- build_baseline_setup_response() on DrivingAdvisor is the method the UI
  handler should call; it returns a JSON string with the same keys as
  build_combined_setup_response.

Import contract
---------------
setup_baseline imports FROM driving_advisor (via function-local import inside
build_baseline_setup_response on DrivingAdvisor — no module-level cycle).
setup_baseline imports FROM setup_diagnosis and setup_driver_profile only
(no cycle).
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Neutral seed values — single source of truth (Group 44)
# ---------------------------------------------------------------------------
# Values verified against:
#   ui/setup_form_widget.py lines ~229-282  (form widget defaults)
#   strategy/ai_planner.py lines ~2162-2202 (parser fallbacks)
#
# DISCREPANCIES found and resolved per brief (use form-seed value):
#   lsd_front_initial: form=10, ai_planner=0 → using 10 (form seed)
#   lsd_front_accel:   form=15, ai_planner=0 → using 15 (form seed)
#   lsd_front_decel:   form= 5, ai_planner=0 → using  5 (form seed)
#
# Gearbox fields (final_drive, gear_1..gear_N) are NOT listed here — they
# are computed algorithmically in _build_gearbox_changes().
NEUTRAL_SEEDS: dict[str, float] = {
    "ride_height_front":    80,
    "ride_height_rear":     80,
    "springs_front":        3.50,
    "springs_rear":         3.00,
    "dampers_front_comp":   30,
    "dampers_front_ext":    40,
    "dampers_rear_comp":    25,
    "dampers_rear_ext":     35,
    "arb_front":            5,
    "arb_rear":             4,
    "camber_front":         1.0,
    "camber_rear":          1.5,
    "toe_front":            0.00,
    "toe_rear":             0.05,
    "aero_front":           400,
    "aero_rear":            600,
    "lsd_initial":          10,
    "lsd_accel":            15,
    "lsd_decel":            5,
    # Front-differential (AWD/4WD cars only; zero = no front LSD fitted)
    # Form seed: 10/15/5; ai_planner fallback: 0/0/0 — using form seed (discrepancy noted above)
    "lsd_front_initial":    10,
    "lsd_front_accel":      15,
    "lsd_front_decel":      5,
    "brake_bias":           0,
    "ballast_kg":           0.0,
    "ballast_position":     0,
    "power_restrictor":     100.0,
}

# ---------------------------------------------------------------------------
# Gearbox range constants
# These are function-local-imported from strategy/setup_diagnosis.py inside
# _build_gearbox_changes() to avoid any module-level circular import risk.
# The module-level fallback constants below are used ONLY if setup_diagnosis
# cannot be imported (which should never happen in practice).  They are tested
# against the source of truth by tests/test_group44_baseline_generator.py.
# ---------------------------------------------------------------------------
_GEAR_RATIO_RANGE: tuple[float, float] = (0.5, 4.0)   # fallback; real value from setup_diagnosis
_FINAL_DRIVE_RANGE: tuple[float, float] = (2.5, 6.0)  # fallback; real value from setup_diagnosis

# Source label constants used in change dicts
_LABEL_NEUTRAL    = "neutral default"
_LABEL_MIDPOINT   = "range midpoint"
_LABEL_BIASED     = "driver-profile biased"
_LABEL_CONSERV    = "conservative default, not diagnosed"

# Fields that always receive the "conservative default, not diagnosed" label
# (they lack the telemetry evidence needed to diagnose them from scratch)
_CONSERVATIVE_FIELDS: frozenset[str] = frozenset({
    "camber_front", "camber_rear",
    "toe_front", "toe_rear",
    "dampers_front_comp", "dampers_front_ext",
    "dampers_rear_comp", "dampers_rear_ext",
    "springs_front", "springs_rear",
    "lsd_initial",
    "lsd_front_initial",
})


# ---------------------------------------------------------------------------
# Driver-profile bias table
# ---------------------------------------------------------------------------
# Maps DriverProfile boolean flags → {field: delta} adjustments.
# Applied AFTER the neutral seed; clamped to per-car range.
# A biased field receives label=_LABEL_BIASED and alignment="aligned".
_PROFILE_BIAS_TABLE: list[tuple[str, dict[str, float]]] = [
    # flag name                → {field: delta}
    ("prefers_rear_stability", {"arb_rear": -1,    "toe_rear": +0.05}),
    ("dislikes_snap_exit",     {"lsd_accel": -2}),
    ("prefers_front_bite",     {"arb_front": +1,   "toe_front": -0.02}),
    ("dislikes_floaty_front",  {"aero_front": +50}),
    ("protects_downforce",     {"aero_rear": +50}),
    ("race_values_consistency", {"lsd_decel": +2}),
    # Group 45: trail_braker → move brake bias forward (front); same delta convention as existing entries
    ("trail_braker",           {"brake_bias": -0.5}),
    # Group 45: rotation_without_snap → reduce LSD decel for entry rotation
    ("rotation_without_snap",  {"lsd_decel": -2}),
]


def _round_for_field(field: str, value: float) -> float:
    """Round a value to the natural precision expected by the form/plan pipeline.

    Integers: arb_*, dampers_*, ride_height_*, lsd_*, brake_bias, ballast_position,
              aero_* (stored as int in form but may come as float).
    One decimal: springs_*, camber_*, power_restrictor.
    Two decimals: toe_*.
    Three decimals: gear_1..gear_6.
    No rounding: final_drive (4 sig figs via round(v, 4)).
    """
    int_fields = {
        "arb_front", "arb_rear",
        "dampers_front_comp", "dampers_front_ext",
        "dampers_rear_comp", "dampers_rear_ext",
        "ride_height_front", "ride_height_rear",
        "lsd_initial", "lsd_accel", "lsd_decel",
        "lsd_front_initial", "lsd_front_accel", "lsd_front_decel",
        "brake_bias", "ballast_position",
        "aero_front", "aero_rear",
    }
    if field in int_fields:
        return int(round(value))
    if field in ("toe_front", "toe_rear"):
        return round(value, 2)
    if field in ("springs_front", "springs_rear",
                 "camber_front", "camber_rear",
                 "power_restrictor", "ballast_kg"):
        return round(value, 1)
    if field.startswith("gear_") and field != "gear_ratios":
        return round(value, 3)
    if field == "final_drive":
        return round(value, 4)
    return value


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value into [lo, hi]."""
    return max(lo, min(hi, value))


def _build_gearbox_changes(
    ranges: dict,
    num_gears: int,
    locked_fields: set,
) -> list[dict]:
    """Build change dicts for gearbox fields (final_drive + gear_1..gear_N).

    For a from-scratch baseline there is no prior setup, so all computed
    gearbox values are always authored (``from`` is set to the computed value
    itself, which is the baseline starting point — not a no-op).

    Algorithm:
    - final_drive = midpoint of _FINAL_DRIVE_RANGE clamped to ranges; label "range midpoint".
    - gear_1..gear_N: strictly-decreasing geometric sequence from
        high = _GEAR_RATIO_RANGE[1] * 0.95  down to
        low  = _GEAR_RATIO_RANGE[0] * 1.05
      ratio_n = high * (low/high)**((n-1)/(N-1)) for n=1..N.
      Each is clamped into _GEAR_RATIO_RANGE, rounded to 3 dp, and then
      strict monotonicity is enforced by nudging any tied value down by 0.001.
    - num_gears <= 1: single gear_1 at midpoint of _GEAR_RATIO_RANGE.
    - num_gears == 0: no gear fields authored.
    - num_gears > 6: capped at 6 (canonical set only has gear_1..gear_6).
    - transmission_max_speed_kmh is NEVER authored.
    """
    # Function-local import: avoids module-level circular import while ensuring
    # we always use the same range constants as the validator in setup_diagnosis.
    try:
        from strategy.setup_diagnosis import (
            _GEAR_RATIO_RANGE as _GRR,  # type: ignore[attr-defined]
            _FINAL_DRIVE_RANGE as _FDR,  # type: ignore[attr-defined]
        )
    except (ImportError, AttributeError):
        _GRR = _GEAR_RATIO_RANGE   # module-level fallback
        _FDR = _FINAL_DRIVE_RANGE  # module-level fallback

    changes: list[dict] = []
    _gear_lo, _gear_hi = _GRR
    _fd_lo, _fd_hi = _FDR

    # final_drive (only if not locked)
    if "final_drive" not in locked_fields:
        _fd_range = ranges.get("final_drive", (_fd_lo, _fd_hi))
        _fd_mid = (_fd_range[0] + _fd_range[1]) / 2.0
        _fd_val = _round_for_field("final_drive", _clamp(_fd_mid, _fd_range[0], _fd_range[1]))
        changes.append(_make_change_dict(
            field="final_drive",
            from_val=_fd_val,   # from-scratch: "from" == "to" (starting point)
            to_val=_fd_val,
            label=_LABEL_MIDPOINT,
            alignment="neutral",
        ))

    # gear ratios
    effective_n = max(0, min(6, num_gears))
    if effective_n == 0:
        return changes

    _high = _gear_hi * 0.95
    _low  = _gear_lo * 1.05

    if effective_n == 1:
        _ratio = round((_gear_lo + _gear_hi) / 2.0, 3)
        _ratio = _clamp(_ratio, _gear_lo, _gear_hi)
        _gear_key = "gear_1"
        if _gear_key not in locked_fields:
            changes.append(_make_change_dict(
                field=_gear_key,
                from_val=_ratio,
                to_val=_ratio,
                label=_LABEL_MIDPOINT,
                alignment="neutral",
            ))
        return changes

    # N >= 2: geometric sequence
    raw_ratios: list[float] = []
    for n in range(1, effective_n + 1):
        t = (n - 1) / (effective_n - 1)   # 0.0 .. 1.0
        ratio = _high * (_low / _high) ** t
        ratio = round(_clamp(ratio, _gear_lo, _gear_hi), 3)
        raw_ratios.append(ratio)

    # Enforce strict monotonic decrease (rounding can cause ties)
    for i in range(1, len(raw_ratios)):
        if raw_ratios[i] >= raw_ratios[i - 1]:
            raw_ratios[i] = round(raw_ratios[i - 1] - 0.001, 3)
            # Ensure we stay within range
            raw_ratios[i] = max(_gear_lo, raw_ratios[i])

    for idx, ratio in enumerate(raw_ratios):
        _gear_key = f"gear_{idx + 1}"
        if _gear_key in locked_fields:
            continue
        changes.append(_make_change_dict(
            field=_gear_key,
            from_val=ratio,   # from-scratch: "from" == "to" (starting point)
            to_val=ratio,
            label=_LABEL_MIDPOINT,
            alignment="neutral",
        ))

    return changes


def _make_change_dict(
    field: str,
    from_val: object,
    to_val: object,
    label: str,
    alignment: str,
    session_influence: str = "",
    car_drivetrain_influence: str = "",
) -> dict:
    """Build a change dict in plan_to_raw_data / AI-response shape.

    Group 45: added session_influence and car_drivetrain_influence keys.
    Both are "" unless a session_type was passed AND changed output (populated
    by build_baseline_setup when applicable).
    source_label is derived from label: "driver-profile biased" → label itself;
    other labels map to themselves per _LABEL_* constants.
    """
    return {
        "setting": field.replace("_", " ").title(),
        "field": field,
        "from": str(from_val) if from_val is not None else "",
        "to": str(to_val),
        "to_clamped": to_val,
        # Explainability keys — mirrors plan_to_raw_data / SetupChangeIntent shape
        "symptom": "no telemetry baseline",
        "evidence": [],
        "rule_id": "baseline_seed",
        "rationale": label,
        "why": label,
        "rejected_alternatives": [],
        "risk_level": "low",
        "confidence_level": "low",
        "driver_style_alignment": alignment,
        # Group 45 explainability fields
        "source_label": label,          # label IS the source description for baseline changes
        "session_influence": session_influence,
        "car_drivetrain_influence": car_drivetrain_influence,
        "pack": "",                     # baseline changes have no rule pack
    }


# ---------------------------------------------------------------------------
# Group 46 — Session baseline bias table
# ---------------------------------------------------------------------------
# Small, safe, explainable per-field deltas keyed by normalised session category.
# Applied AFTER the driver-profile bias (same `bias` dict), so the combined total
# is clamped and rounded by the existing pipeline unchanged.
#
# Scale notes (from NEUTRAL_SEEDS / typical ranges):
#   aero_front/rear:  0-1000 range → ±25 = ~2.5% meaningful but conservative
#   lsd_accel/decel:  integer 0-60 → ±1 or ±2 = one "click"
#   brake_bias:       integer range, ±1 = one step forward/rearward
#
# "qualifying" bias: sharper response, less trailing-edge heat build, lighter
#   rear/rotation setup so the car changes direction more crisply.
#   brake_bias: -1 → one step forward (more front braking = bite / trail rotation)
#   lsd_decel:  -1 → easier decel diff → freer rotation on entry
#   aero_front: +25 → more front downforce for mid-corner stability at speed
#
# "sprint" bias (race, duration unknown/short, < 60 mins):
#   lsd_accel: +1 → mild traction nudge (race starts matter, but no long wear concerns)
#
# "endurance" bias (race, duration >= 60 mins):
#   lsd_accel: +2 → more consistent traction over a long stint
#   lsd_decel: +1 → less rotation wear / more predictable entry over many laps
#   aero_rear:  +25 → more rear stability for high-fuel early stints
#
# "practice" / "unknown" → no session-specific deltas (safe default)
_SESSION_BIAS_TABLE: dict[str, dict[str, float]] = {
    "qualifying":  {"brake_bias": -1.0, "lsd_decel": -1.0, "aero_front": +25.0},
    "sprint":      {"lsd_accel": +1.0},
    "endurance":   {"lsd_accel": +2.0, "lsd_decel": +1.0, "aero_rear": +25.0},
    "practice":    {},
    "unknown":     {},
}


def _normalise_session_for_bias(session_type: str, duration_mins: float) -> str:
    """Classify the session into a bias-table key.

    Returns one of: qualifying | sprint | endurance | practice | unknown.

    Rules
    -----
    - session_type contains "qual" (case-insensitive) → "qualifying"
    - session_type contains "practice" → "practice"
    - session_type contains "race":
        - duration_mins >= 60 → "endurance"
        - duration_mins > 0 AND < 60 → "sprint"
        - duration_mins <= 0 (unknown duration) → "sprint"
          IMPORTANT: duration <= 0 must NOT classify as endurance (brief contract).
    - anything else (empty / unrecognised) → "unknown"
    """
    st = (session_type or "").strip().lower()
    if "qual" in st:
        return "qualifying"
    if "practice" in st:
        return "practice"
    if "race" in st or "sprint" in st:
        if duration_mins >= 60.0:
            return "endurance"
        # duration <= 0 (unknown) → sprint (NOT endurance)
        return "sprint"
    return "unknown"


def build_baseline_setup(
    car: str,
    ranges: dict,
    drivetrain: str,
    num_gears: int,
    profile,
    allowed_tuning: "list[str] | None",
    tuning_locked: bool,
    session_type: str = "",
    tyre_wear_multiplier: "float | None" = None,
    car_class: str = "",
    duration_mins: float = 0.0,
) -> dict:
    """Build a from-scratch baseline raw_data dict.

    Parameters
    ----------
    car:
        Car name (used for range clamping label only; ranges already resolved
        by the caller — pass resolve_ranges(car) as `ranges`).
    ranges:
        Resolved per-car ranges dict from resolve_ranges().
    drivetrain:
        Drivetrain string, e.g. "FR", "FF", "MR", "AWD".  Used to decide
        whether front-differential fields are included.
    num_gears:
        Number of gears (0-6; >6 capped at 6).
    profile:
        DriverProfile from build_driver_profile().
    allowed_tuning:
        List of tuning category codes allowed by the event rules, or None
        (= no restrictions).
    tuning_locked:
        If True, return a valid raw_data with empty changes/setup_fields
        (UI should have disabled the button — this is a defensive guard).
    session_type:
        Session type string ("Race" / "Qualifying" / "Practice" / "").
        Used to populate session_influence on change dicts when it changes output.
        Scalar param only — no EventContext injected here (by design).
    tyre_wear_multiplier:
        Optional tyre-wear multiplier for future tyre-aware baseline differentiation.
        Currently accepted and forwarded but not used to author changes (deferred).
    car_class:
        Car class string (e.g. "Gr.3", "Gr.4").  Accepted for forward-compatibility;
        not currently used to author changes in the baseline path.
    duration_mins:
        Session duration in minutes.  Used with session_type to determine session
        bias category (e.g. race + duration>=60 → endurance).  Default 0.0 = unknown.
        duration_mins <= 0 must NOT classify as endurance (brief contract).

    Returns
    -------
    dict with keys matching plan_to_raw_data output:
        analysis, primary_issue, changes, setup_fields,
        diagnosis, validation_targets, confidence.
    """
    # Defensive guard: tuning completely locked
    if tuning_locked:
        return {
            "analysis": (
                "Tuning is locked for this event. No setup changes can be made. "
                "Focus on driving technique and tyre management."
            ),
            "primary_issue": "tuning_locked",
            "changes": [],
            "setup_fields": {},
            "diagnosis": {},
            "validation_targets": {},
            "confidence": {"overall": "low", "reason": "tuning locked"},
        }

    # Resolve locked fields from allowed_tuning
    # Import here (function-local) to avoid any module-level cycle risk;
    # setup_baseline is imported by driving_advisor, not the other way round.
    from strategy.driving_advisor import (
        _derive_locked_fields,
        _CANONICAL_SETUP_PARAMS,
        _DISPLAY_ONLY_FIELDS,
    )

    locked_fields: set[str] = _derive_locked_fields(allowed_tuning) if allowed_tuning else set()
    # Always exclude display-only fields
    locked_fields = locked_fields | _DISPLAY_ONLY_FIELDS

    # Determine which fields are front-differential (AWD/4WD only)
    _is_awd = (drivetrain or "").upper() in {"AWD", "4WD", "4X4"}
    _front_diff_fields: frozenset[str] = frozenset({
        "lsd_front_initial", "lsd_front_accel", "lsd_front_decel",
    })

    # Compute driver-profile biases: field -> delta
    bias: dict[str, float] = {}
    if profile is not None:
        for flag_name, deltas in _PROFILE_BIAS_TABLE:
            if getattr(profile, flag_name, False):
                for field, delta in deltas.items():
                    bias[field] = bias.get(field, 0.0) + delta

    # Group 46: compute session bias and accumulate into the SAME bias dict.
    # _normalise_session_for_bias → one of qualifying/sprint/endurance/practice/unknown.
    # The session deltas ADD on top of existing profile deltas; the combined total is
    # clamped and rounded by the existing pipeline — no special handling needed.
    _session_bias_category = _normalise_session_for_bias(session_type, duration_mins)
    _session_bias_deltas: dict[str, float] = _SESSION_BIAS_TABLE.get(
        _session_bias_category, {}
    )
    for _sb_field, _sb_delta in _session_bias_deltas.items():
        bias[_sb_field] = bias.get(_sb_field, 0.0) + _sb_delta

    # Derive locked CATEGORY names for the analysis text (human-readable).
    # If allowed_tuning is set, locked categories = all categories minus allowed.
    # Import _ALL_TUNING_CATS from driving_advisor (already imported above at call site).
    from strategy.driving_advisor import _ALL_TUNING_CATS as _TUNING_CATS
    if allowed_tuning is not None:
        _locked_cats: list[str] = sorted(
            cat for cat in _TUNING_CATS if cat not in allowed_tuning
        )
    else:
        _locked_cats = []

    changes: list[dict] = []
    setup_fields: dict = {}

    # Actionable canonical fields (excluding display-only and gearbox)
    _GEARBOX_FIELDS: frozenset[str] = frozenset({
        "final_drive",
        "gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6",
        "transmission_max_speed_kmh",
    })
    _non_gearbox_params = (
        _CANONICAL_SETUP_PARAMS
        - _DISPLAY_ONLY_FIELDS
        - _GEARBOX_FIELDS
    )

    for field in sorted(_non_gearbox_params):
        # Skip if not in NEUTRAL_SEEDS (shouldn't happen with canonical set)
        if field not in NEUTRAL_SEEDS:
            continue

        # Skip front-diff fields for non-AWD cars
        if field in _front_diff_fields and not _is_awd:
            continue

        # Skip locked fields
        if field in locked_fields:
            continue

        seed = NEUTRAL_SEEDS[field]

        # Compute value WITH combined bias (profile + session)
        to_val = float(seed)
        is_biased = False
        if field in bias:
            to_val += bias[field]
            is_biased = True

        # Clamp to per-car range
        if field in ranges:
            lo, hi = ranges[field]
            to_val = _clamp(to_val, lo, hi)

        # Round to natural precision
        to_val = _round_for_field(field, to_val)
        seed_rounded = _round_for_field(field, float(seed))

        # Group 46: compute value WITHOUT session bias to detect session_changed.
        # session_changed = True only when session bias actually changed the output.
        _profile_only_bias = bias.get(field, 0.0) - _session_bias_deltas.get(field, 0.0)
        _val_without_session = float(seed) + _profile_only_bias
        if field in ranges:
            lo, hi = ranges[field]
            _val_without_session = _clamp(_val_without_session, lo, hi)
        _val_without_session_rounded = _round_for_field(field, _val_without_session)
        _session_changed = (to_val != _val_without_session_rounded)

        # Determine source label and alignment
        if is_biased:
            label = _LABEL_BIASED
            alignment = "aligned"
        elif field in _CONSERVATIVE_FIELDS:
            label = _LABEL_CONSERV
            alignment = "neutral"
        else:
            label = _LABEL_NEUTRAL
            alignment = "neutral"

        # Group 46: honest session_influence per change (brief contract):
        # - session known + field changed numerically by session bias → real session text
        # - session known, field is profile-biased but session did not change it numerically →
        #     for sessions with non-empty bias tables: "session noted — no numerical change for this field"
        #     for sessions with empty bias tables (practice/unknown): preserve the old per-session label
        # - non-biased + session has no delta for this field → ""
        # - session unknown → ""
        if _session_bias_category in ("qualifying", "sprint", "endurance"):
            # Sessions with actual deltas in _SESSION_BIAS_TABLE
            if _session_changed:
                _ch_session_influence = (
                    f"{_session_bias_category} session bias applied"
                )
            elif field in _session_bias_deltas:
                # Field IS in the session bias table but delta was zero after clamp
                _ch_session_influence = "session noted — no numerical change for this field"
            else:
                # Field not in this session's bias table — no session claim
                _ch_session_influence = ""
        elif _session_bias_category == "practice":
            # Practice has no session deltas: only profile-biased fields get the label
            _ch_session_influence = "practice session — no special bias applied" if is_biased else ""
        else:
            # "unknown" session category → no claim
            _ch_session_influence = ""

        change = _make_change_dict(
            field=field,
            from_val=seed_rounded,
            to_val=to_val,
            label=label,
            alignment=alignment,
            session_influence=_ch_session_influence,
            car_drivetrain_influence="",
        )
        changes.append(change)

        if field not in _DISPLAY_ONLY_FIELDS:
            try:
                setup_fields[field] = float(to_val)
            except (TypeError, ValueError):
                setup_fields[field] = to_val

    # Gearbox fields — always authored (from-scratch baseline, no prior setup)
    gb_changes = _build_gearbox_changes(ranges, num_gears, locked_fields)
    for ch in gb_changes:
        changes.append(ch)
        f = ch.get("field")
        v = ch.get("to_clamped")
        if f and f not in _DISPLAY_ONLY_FIELDS and v is not None:
            try:
                setup_fields[f] = float(v)
            except (TypeError, ValueError):
                setup_fields[f] = v

    # Build analysis text
    locked_text = (
        f" The following tuning categories are locked by event rules: "
        f"{', '.join(c.replace('_', ' ').title() for c in _locked_cats)}."
        if _locked_cats else ""
    )
    awd_text = " Front differential fields included (AWD drivetrain)." if _is_awd else ""
    gear_text = (
        f" Gearbox: geometric sequence for {min(6, max(0, num_gears))} gears."
        if num_gears > 0 else ""
    )
    analysis = (
        f"From-scratch baseline setup generated using neutral physics defaults "
        f"and driver-profile mechanical nudges. No telemetry data available — "
        f"all values are conservative starting points requiring on-track validation."
        f"{awd_text}{gear_text}{locked_text}"
    )

    return {
        "analysis": analysis,
        "primary_issue": "no_telemetry_baseline",
        "changes": changes,
        "setup_fields": setup_fields,
        "diagnosis": {},
        # validation_targets: required by malformed_schema validator (presence check only)
        "validation_targets": {},
        "confidence": {
            "overall": "low",
            "reason": "no telemetry — neutral baseline",
        },
    }
