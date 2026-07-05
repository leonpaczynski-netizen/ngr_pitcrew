"""Setup diagnosis module for NGR Pit Crew / GT7 Pit Crew app.

Pure Python — no Qt, no network imports.
All functions are safe to call in plain pytest without any running Qt app.

Public API
----------
build_setup_diagnosis(laps, setup, car_name, event_ctx, feeling) -> dict
    Aggregates LapStats telemetry + driver feel into a structured diagnosis dict.

validate_setup_engineering(parsed_ai_response, diagnosis, setup, ranges, event_ctx) -> list[str]
    Post-processes an AI JSON response dict against the diagnosis to detect
    engineering-rule violations.  Returns a list of human-readable reason strings
    with stable prefixes so tests can substring-match.

_parse_driver_feel(feeling) -> dict[str, bool]
    Case-insensitive substring classifier for driver feeling text.

Module-level constants (imported by driving_advisor.py and ai_planner.py)
--------------------------------------------------------------------------
PERSONAL_DRIVER_TUNING_MODEL  — compact block describing the driver's tuning style
DRIVER_HARD_CONSTRAINTS       — 8 verbatim hard constraints for the AI
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telemetry.recorder import LapStats

# ---------------------------------------------------------------------------
# Tunable module-level constants
# ---------------------------------------------------------------------------

_ACCEL_FADE_THROTTLE_HIGH_PCT = 0.85   # throttle threshold for "wide open" frames
_ACCEL_FADE_MIN_SAMPLES       = 5      # minimum WOT frames needed to analyse fade
_PEAK_POWER_RPM_FRACTION      = 0.90   # unused directly; reserved for future engine-map work
_ACCEL_FADE_SPEED_DROP_PCT    = 0.05   # speed must fall ≥5% from a local peak to count as fade
_KERB_PROXIMITY_WINDOW_M      = 50.0   # distance window (m) for kerb-proximity wheelspin cluster
_COMPLIANCE_KERB_THRESHOLD    = 2      # avg kerb events/lap above which compliance is a priority
_COMPLIANCE_FEEL_TERMS: list[str] = [
    "stiff", "harsh", "jarring", "kerb upset", "kerb bump",
    "undulation", "bouncy", "bounces", "skips", "jolts",
    "crash", "crashing over",
]

# ---------------------------------------------------------------------------
# Module-level prompt constants (single source of truth — import into
# driving_advisor.py and ai_planner.py; do NOT duplicate here).
# ---------------------------------------------------------------------------

PERSONAL_DRIVER_TUNING_MODEL: str = (
    "## Driver Tuning Model (personal style — apply to every recommendation)\n"
    "Trail-braker who relies on brake-release rotation to point the car; "
    "wants immediate nose response and a stable, planted rear on entry; "
    "prefers predictable exits over extra rotation; "
    "prizes front bite without rear instability; "
    "dislikes a floaty front / lazy turn-in / loose throttle exits; "
    "prefers increasing rear aero to stabilise the platform first, then uses "
    "mechanical grip (LSD, ARB, springs) for rotation; "
    "race-car target: 'less spiky, not dull' — composed and confidence-inspiring "
    "over a stint, not nervous or edgy.\n"
)

DRIVER_HARD_CONSTRAINTS: str = (
    "## Driver Hard Constraints (MUST NOT violate)\n"
    "1. No floaty front — never reduce front downforce or stiffen front to the point "
    "the nose lifts or washes wide.\n"
    "2. No excessive ride-height increase unless telemetry proves bottoming at a rate "
    "that warrants it (>1.0 events/lap); minor bottoming does not justify raising height.\n"
    "3. No low-downforce default — do not recommend minimum aero as a starting point "
    "unless the track genuinely demands it and the driver's feel confirms no instability.\n"
    "4. Don't fix understeer by destabilising the rear — adding rear toe-out, removing "
    "rear ARB, or cutting rear aero to rotate the car is forbidden when the driver "
    "reports rear instability or when wheelspin is above 'low' band.\n"
    "5. Don't fix exit oversteer by killing front response — softening front ARB/springs "
    "or adding front toe-out as the primary exit-oversteer cure masks the real cause.\n"
    "6. Don't remove rear aero when wheelspin, exit looseness, or rear instability is "
    "present — rear aero is a traction and stability tool first.\n"
    "7. Don't ignore driver feel when telemetry supports it — if the driver reports "
    "floaty front and aero_front is near its minimum, that is a platform-limited "
    "diagnosis and must be addressed directly.\n"
    "8. Treat 'feels bad' as first-class input — subjective driver confidence is a "
    "performance variable; a setup the driver cannot trust is not a fast setup.\n"
)

# ---------------------------------------------------------------------------
# Driver-feel keyword vocabulary
# ---------------------------------------------------------------------------

# Each key maps to a list of substrings (lower-case) that identify that flag.
_FEEL_VOCABULARY: dict[str, list[str]] = {
    "floaty_front": [
        "floaty", "floats", "understeer", "push", "washes",
        "won't turn", "front doesn't bite", "no front", "lazy turn",
    ],
    "entry_understeer": [
        "entry understeer", "pushes on entry", "braking understeer",
        "front tucks", "can't trail",
    ],
    "rear_loose_on_exit": [
        "rear loose", "rear steps", "oversteer on exit", "rear kicks",
        "rear slides", "loose on exit", "tail slides", "loose on throttle",
        "rear loose on exit",
    ],
    "gearbox_good": [
        "gearbox fine", "gears fine", "gearing ok", "gearing good",
        "happy with gears", "transmission ok", "gearbox good",
        "gearbox is good", "gearbox spot on",
    ],
    "snap_oversteer_exit": [
        "snap", "snappy", "rear snaps", "kicks on throttle",
    ],
    "braking_instability": [
        "locks", "lock-up", "dances on braking",
        "nervous under braking", "tail wags",
    ],
    "bottoming": [
        "bottoming", "grounds out", "scrapes", "bottoms",
    ],
}


def _parse_driver_feel(feeling: str | None) -> dict[str, bool]:
    """Return a dict of bool flags derived from a free-text driver feeling string.

    Case-insensitive substring match against the vocabulary above.
    feeling=None returns all False with no exception.
    """
    result: dict[str, bool] = {key: False for key in _FEEL_VOCABULARY}
    if not feeling:
        return result
    text = feeling.lower()
    for flag, keywords in _FEEL_VOCABULARY.items():
        for kw in keywords:
            if kw in text:
                result[flag] = True
                break
    return result


# ---------------------------------------------------------------------------
# Bottoming band thresholds
# ---------------------------------------------------------------------------

def _bottoming_band(avg: float) -> str:
    """Classify average bottoming events per lap into a named band.

    SPEC:
      < 0.5          -> "minor"
      0.5 to <= 1.0  -> "moderate"
      > 1.0 to <= 2.0 -> "consider"
      > 2.0          -> "required"
    """
    if avg < 0.5:
        return "minor"
    if avg <= 1.0:
        return "moderate"
    if avg <= 2.0:
        return "consider"
    return "required"


# ---------------------------------------------------------------------------
# Wheelspin band thresholds
# ---------------------------------------------------------------------------

def _wheelspin_band(avg: float) -> str:
    """Classify average wheelspin events per lap into a named band.

    SPEC:
      <= 5           -> "low"
      > 5 to <= 10   -> "meaningful"
      > 10 to <= 15  -> "major"
      > 15           -> "severe"
    """
    if avg <= 5:
        return "low"
    if avg <= 10:
        return "meaningful"
    if avg <= 15:
        return "major"
    return "severe"


# ---------------------------------------------------------------------------
# Aero near-min detection
# ---------------------------------------------------------------------------

def _aero_near_min(value: float | None, lo: float, hi: float) -> bool:
    """Return True when value <= lo + 10% of the (hi - lo) span."""
    if value is None:
        return False
    span = hi - lo
    if span <= 0:
        return False
    return value <= lo + 0.10 * span


# ---------------------------------------------------------------------------
# Dominant-problem derivation helpers
# ---------------------------------------------------------------------------

def _derive_dominant_problem(
    driver_feel_flags: dict[str, bool],
    bottoming_band: str,
    wheelspin_band: str,
    aero_front_near_min: bool,
    aero_rear_near_min: bool,
) -> tuple[str, list[str]]:
    """Return (dominant_problem, secondary_problems) as plain-English strings."""
    issues: list[str] = []

    # Front aero / platform limited
    if (
        (driver_feel_flags.get("floaty_front") or driver_feel_flags.get("entry_understeer"))
        and aero_front_near_min
    ):
        issues.append("front_aero_platform_limited")

    # Bottoming — only escalate to dominant when significant.
    # A9: when bottoming_band == "consider" AND wheelspin is in the severe-ish
    # set ("major" or "severe"), bottoming does NOT take precedence — rear-traction
    # issues should dominate.  Bottoming at "consider" is dominant only when
    # wheelspin is "low"/"meaningful" OR the driver explicitly mentions bottoming.
    _wheelspin_severe_ish = wheelspin_band in ("major", "severe")
    _driver_mentions_bottoming = driver_feel_flags.get("bottoming", False)
    if bottoming_band == "required":
        issues.append("bottoming")
    elif bottoming_band == "consider":
        if not _wheelspin_severe_ish or _driver_mentions_bottoming:
            issues.append("bottoming")

    # Rear traction / aero
    if (
        wheelspin_band in ("major", "severe")
        or (driver_feel_flags.get("rear_loose_on_exit") and aero_rear_near_min)
    ):
        issues.append("rear_traction_aero")

    # Snap oversteer exit
    if driver_feel_flags.get("snap_oversteer_exit"):
        issues.append("snap_oversteer_exit")

    # Braking instability / lockups
    if driver_feel_flags.get("braking_instability"):
        issues.append("braking_instability")

    # Wheelspin (any meaningful+)
    if wheelspin_band in ("meaningful", "major", "severe"):
        if "rear_traction_aero" not in issues:
            issues.append("wheelspin")

    if not issues:
        if bottoming_band == "minor":
            dominant = "minor bottoming — no primary structural issue"
        else:
            dominant = "no dominant issue identified from available data"
        return dominant, []

    dominant = issues[0]
    secondary = issues[1:]

    # Map to readable strings
    _readable: dict[str, str] = {
        "front_aero_platform_limited": (
            "front aero / platform limited — near minimum front downforce with floaty / understeer feel"
        ),
        "bottoming": f"bottoming ({bottoming_band} — {_bottoming_band_readable(bottoming_band)})",
        "rear_traction_aero": "rear traction / aero — wheelspin or rear instability with low rear downforce",
        "snap_oversteer_exit": "snap oversteer on exit — abrupt rear rotation at throttle application",
        "braking_instability": "braking instability — lockups or rear wag under braking",
        "wheelspin": f"wheelspin ({wheelspin_band})",
    }

    dominant_str = _readable.get(dominant, dominant)
    secondary_strs = [_readable.get(s, s) for s in secondary]
    return dominant_str, secondary_strs


def _bottoming_band_readable(band: str) -> str:
    return {
        "minor": "no action needed",
        "moderate": "monitor; address other issues first",
        "consider": "ride height / spring rate change should be considered",
        "required": "ride height / spring rate change is required",
    }.get(band, band)


def _derive_tuning_priority(
    driver_feel_flags: dict[str, bool],
    bottoming_band: str,
    wheelspin_band: str,
    aero_front_near_min: bool,
    aero_rear_near_min: bool,
    location_evidence_usable: bool = True,
    compliance_priority: bool = False,
) -> list[str]:
    """Return ordered list of tuning areas to address.

    When location_evidence_usable is False, ride_height is never placed near
    the top of the priority list, even for "required" bottoming — because
    the bottoming location data is unverified low-confidence track geometry.

    When compliance_priority is True, "natural frequency / damping (compliance — kerb
    and surface sensitivity)" is inserted at position 0 or 1 (after front aero if
    present) so that suspension compliance work appears near the top.
    """
    priority: list[str] = []

    # Front aero takes highest priority when flagged
    if (
        (driver_feel_flags.get("floaty_front") or driver_feel_flags.get("entry_understeer"))
        and aero_front_near_min
    ):
        priority.append("aero (front — increase front downforce; platform limited)")

    # Rear aero / traction high priority when wheelspin severe or rear loose + low rear aero
    if wheelspin_band in ("major", "severe") or (
        driver_feel_flags.get("rear_loose_on_exit") and aero_rear_near_min
    ):
        if "aero (rear — increase rear downforce for traction and stability)" not in priority:
            priority.append("aero (rear — increase rear downforce for traction and stability)")

    # Snap oversteer
    if driver_feel_flags.get("snap_oversteer_exit"):
        priority.append("LSD accel / rear springs (reduce exit snap)")

    # Braking
    if driver_feel_flags.get("braking_instability"):
        priority.append("brake_bias / LSD decel (stabilise braking)")

    # Wheelspin (meaningful but not already covered by rear aero)
    if wheelspin_band in ("meaningful",) and "aero (rear" not in " ".join(priority):
        priority.append("LSD accel / traction (wheelspin meaningful)")

    # Bottoming — ride height entry position depends on location confidence.
    # When location_evidence_usable is False: never put ride height near top
    # because we cannot trust the bottoming location data.
    if bottoming_band == "required":
        if location_evidence_usable:
            # High confidence: escalate ride height near the top
            priority.insert(0 if not priority else min(1, len(priority)),
                            "ride height / springs (severe bottoming)")
        else:
            # Low confidence: append to end and flag uncertainty
            priority.append(
                "springs / dampers (bottoming — ride height change deferred: "
                "low track model confidence, location data unverified)"
            )
    elif bottoming_band == "consider":
        if location_evidence_usable:
            priority.append("ride height / springs (bottoming — consider change)")
        else:
            priority.append(
                "springs / dampers (bottoming — ride height deferred: "
                "low track model confidence)"
            )

    # A10: compliance priority — insert at position 0 or 1 (after front aero if present)
    if compliance_priority:
        _compliance_entry = "natural frequency / damping (compliance — kerb and surface sensitivity)"
        _insert_pos = 1 if priority and "aero (front" in priority[0] else 0
        priority.insert(_insert_pos, _compliance_entry)

    # Fallback
    if not priority:
        priority.append("balance / aero (no dominant issue — refine overall balance)")

    return priority


def _driver_feel_supported_by_telemetry(
    driver_feel_flags: dict[str, bool],
    wheelspin_band: str,
    aero_front_near_min: bool,
    aero_rear_near_min: bool,
    avg_lockups: float,
) -> bool:
    """Return True when at least one driver feel flag is corroborated by telemetry."""
    # floaty front + front aero near min
    if driver_feel_flags.get("floaty_front") and aero_front_near_min:
        return True
    # entry understeer + front aero near min
    if driver_feel_flags.get("entry_understeer") and aero_front_near_min:
        return True
    # rear loose on exit + wheelspin meaningful+
    if driver_feel_flags.get("rear_loose_on_exit") and wheelspin_band in ("meaningful", "major", "severe"):
        return True
    # rear loose on exit + rear aero near min
    if driver_feel_flags.get("rear_loose_on_exit") and aero_rear_near_min:
        return True
    # snap oversteer exit + wheelspin meaningful+
    if driver_feel_flags.get("snap_oversteer_exit") and wheelspin_band in ("meaningful", "major", "severe"):
        return True
    # braking instability + lockups > 0.3/lap
    if driver_feel_flags.get("braking_instability") and avg_lockups > 0.3:
        return True
    return False


# ---------------------------------------------------------------------------
# Gearing / acceleration-fade helpers  (A2, A3, A4, A5)
# ---------------------------------------------------------------------------

def _derive_top_gear_frame_signals(frames: list, top_gear: int) -> dict:
    """Analyse TelemetryFrame data for top-gear power-band signals.

    Returns {"accel_fade_detected": bool, "peak_power_early": bool,
             "top_gear_wot_sample": int}.

    Algorithm:
      1. Filter frames where gear == top_gear AND throttle >= _ACCEL_FADE_THROTTLE_HIGH_PCT.
         throttle on TelemetryFrame is 0.0–1.0 (confirmed from recorder.py:24).
      2. Fewer than _ACCEL_FADE_MIN_SAMPLES → all False / sample 0.
      3. peak_power_early: the frame with max_rpm occurs in the first 40% of the sequence.
      4. accel_fade_detected: speed drops ≥ _ACCEL_FADE_SPEED_DROP_PCT from a local
         peak within the WOT sequence with no braking (brake < 0.05) intervening.
    Degrades to all-False when frames is empty or top_gear is invalid.
    """
    if not frames or top_gear <= 0:
        return {"accel_fade_detected": False, "peak_power_early": False,
                "top_gear_wot_sample": 0}

    # Filter to top-gear, high-throttle frames (defensive getattr for SimpleNamespace)
    wot_frames = [
        f for f in frames
        if getattr(f, "gear", 0) == top_gear
        and getattr(f, "throttle", 0.0) >= _ACCEL_FADE_THROTTLE_HIGH_PCT
    ]

    if len(wot_frames) < _ACCEL_FADE_MIN_SAMPLES:
        return {"accel_fade_detected": False, "peak_power_early": False,
                "top_gear_wot_sample": len(wot_frames)}

    # peak_power_early: frame index of max RPM in the first 40% of the sequence
    max_rpm_idx = max(range(len(wot_frames)),
                      key=lambda i: getattr(wot_frames[i], "rpm", 0.0))
    peak_power_early = max_rpm_idx < 0.40 * len(wot_frames)

    # accel_fade_detected: speed falls ≥ _ACCEL_FADE_SPEED_DROP_PCT from a
    # local peak with no braking (brake < 0.05) in between.
    accel_fade_detected = False
    local_peak_speed: float | None = None
    for f in wot_frames:
        spd = getattr(f, "speed_kmh", 0.0)
        brk = getattr(f, "brake", 0.0)
        if brk >= 0.05:
            # Braking event — reset peak tracking; this is not an uninterrupted fade
            local_peak_speed = None
            continue
        if local_peak_speed is None or spd > local_peak_speed:
            local_peak_speed = spd
        elif local_peak_speed > 0 and (local_peak_speed - spd) / local_peak_speed >= _ACCEL_FADE_SPEED_DROP_PCT:
            accel_fade_detected = True
            break

    return {
        "accel_fade_detected": accel_fade_detected,
        "peak_power_early":    peak_power_early,
        "top_gear_wot_sample": len(wot_frames),
    }


def _classify_gearing(
    frames: list,
    rev_limiter_by_gear: "dict | None",
    avg_top_speed_kmh: float,
    top_speed_target_kmh: float,
    wheelspin_band: str,
) -> str:
    """Classify the gearing situation from telemetry signals.

    Returns one of: gear_too_short | gear_too_long | top_gear_power_band_limited |
    traction_limited_acceleration | drag_or_power_limited | limiter_limited |
    insufficient_data.

    Decision table (first match wins):
      1. top_gear_limiter_hits > 0 AND speed_ratio < 0.93 → gear_too_short
      2. top_gear_limiter_hits > 0 AND speed_ratio >= 0.93 → limiter_limited
      3. speed_ratio < 0.93 AND wheelspin severe-ish AND no top-gear limiter
         → traction_limited_acceleration
      4. speed_ratio < 0.93 AND peak_power_early AND accel_fade_detected
         → top_gear_power_band_limited
      5. speed_ratio < 0.93 (uncovered) → drag_or_power_limited
      6. speed_ratio >= 0.98 AND no top-gear limiter → gear_too_long
      7. target 0 / no limiter data / frames empty AND no speed → insufficient_data

    "severe-ish" wheelspin: "major" or "severe" (from _wheelspin_band).
    """
    _SEVERE_ISH = ("major", "severe")

    # Resolve top gear
    top_gear = 0
    rlbg = rev_limiter_by_gear or {}
    if rlbg:
        top_gear = max(int(g) for g in rlbg)
    if top_gear <= 0 and frames:
        # Fallback: highest gear seen in frames
        for f in frames:
            g = getattr(f, "gear", 0)
            if g > top_gear:
                top_gear = g

    top_gear_limiter_hits = float(rlbg.get(top_gear, 0)) if top_gear > 0 else 0.0

    # Speed ratio — guard divide-by-zero
    if top_speed_target_kmh <= 0:
        # Cannot compute ratio — fall through to insufficient_data
        speed_ratio: float | None = None
    elif avg_top_speed_kmh <= 0:
        speed_ratio = None
    else:
        speed_ratio = avg_top_speed_kmh / top_speed_target_kmh

    # Derive acceleration-fade signals from frame data
    _tgfs = _derive_top_gear_frame_signals(frames, top_gear)
    peak_power_early  = _tgfs["peak_power_early"]
    accel_fade_detected = _tgfs["accel_fade_detected"]

    # Decision table (first match wins)
    if speed_ratio is not None:
        if top_gear_limiter_hits > 0 and speed_ratio < 0.93:
            return "gear_too_short"
        if top_gear_limiter_hits > 0 and speed_ratio >= 0.93:
            return "limiter_limited"
        if speed_ratio < 0.93 and wheelspin_band in _SEVERE_ISH and top_gear_limiter_hits == 0:
            return "traction_limited_acceleration"
        if speed_ratio < 0.93 and peak_power_early and accel_fade_detected:
            return "top_gear_power_band_limited"
        if speed_ratio < 0.93:
            return "drag_or_power_limited"
        if speed_ratio >= 0.98 and top_gear_limiter_hits == 0:
            return "gear_too_long"
    else:
        # No speed target — can still classify from limiter signals alone.
        # Top-gear limiter hits with no speed target = can't confirm gearing is good;
        # treat as a "may_change" signal (gear_too_short is the most conservative
        # classification when the driver might be hitting the limiter prematurely).
        if top_gear_limiter_hits > 0:
            return "gear_too_short"

    return "insufficient_data"


def _classify_wheelspin_subtype(
    frames: list,
    rev_limiter_by_gear: "dict | None",
    wheelspin_band: str,
    avg_snap: float,
    aero_rear_near_min: bool,
    laps: list,
) -> str:
    """Classify the wheelspin mechanism from available telemetry signals.

    Returns one of: both_rear_spin | snap_throttle_induced | kerb_unload_spin |
    gear_too_short_spin | aero_instability | mixed | insufficient_data.

    NOTE: inside_wheel_spin is NEVER emitted — per-wheel slip data is not
    available in GT7 telemetry at this level; the signal would require individual
    wheel-slip deltas which are not in TelemetryFrame.

    NOTE: rear_platform_stiffness requires a spring/damper baseline comparison
    that the app does not currently track.  We emit "mixed" as a safe placeholder
    and leave this as a future extension when spring data is captured.
    # future extension: rear_platform_stiffness needs spring/damper baseline delta
    """
    _SEVERE_ISH = ("major", "severe")

    # Insufficient data guard — only return early for low wheelspin;
    # even with empty frames/laps we may still classify from avg_snap or aero signals.
    if wheelspin_band in ("low",):
        return "insufficient_data"

    rlbg = rev_limiter_by_gear or {}
    top_gear = max((int(g) for g in rlbg), default=0)

    # Compute kerb_count across laps (no positional data — kerb proximity check
    # simplified to: any kerb events present at all)
    kerb_count = sum(getattr(l, "kerb_count", 0) for l in laps)

    # Oversteer throttle-on counts
    total_oversteer = sum(getattr(l, "oversteer_count", 0) for l in laps)
    throttle_on_oversteer = sum(getattr(l, "oversteer_throttle_on_count", 0) for l in laps)

    # gear_too_short_spin: limiter hits in gears strictly below top gear + severe-ish wheelspin
    if wheelspin_band in _SEVERE_ISH and top_gear > 0:
        lower_gear_hits = sum(
            int(cnt) for g, cnt in rlbg.items() if int(g) < top_gear
        )
        if lower_gear_hits > 0:
            return "gear_too_short_spin"

    # snap_throttle_induced: high snap count + severe-ish wheelspin
    if avg_snap > 5 and wheelspin_band in _SEVERE_ISH:
        return "snap_throttle_induced"

    # aero_instability: rear aero near min + wheelspin severe
    if aero_rear_near_min and wheelspin_band == "severe":
        return "aero_instability"

    # kerb_unload_spin: kerb events present + wheelspin meaningful+.
    # Full spatial proximity check requires kerb_positions which are not yet
    # stored on LapStats; we use kerb count as a proxy for now.
    # future extension: use _KERB_PROXIMITY_WINDOW_M once kerb_positions are tracked.
    if kerb_count > 0 and wheelspin_band in ("meaningful",) + _SEVERE_ISH:
        return "kerb_unload_spin"

    # both_rear_spin: wheelspin severe-ish AND throttle-on oversteer dominant (>60%)
    if wheelspin_band in _SEVERE_ISH and total_oversteer > 0:
        throttle_fraction = throttle_on_oversteer / total_oversteer
        if throttle_fraction > 0.60:
            return "both_rear_spin"

    # mixed: meaningful+ wheelspin but signals don't point to one cause
    if wheelspin_band in ("meaningful",) + _SEVERE_ISH:
        return "mixed"

    return "insufficient_data"


def _detect_compliance_priority(feeling: "str | None", avg_kerb: float) -> bool:
    """Return True when the driver's feeling text contains compliance-related terms
    AND average kerb events per lap exceed _COMPLIANCE_KERB_THRESHOLD.

    Case-insensitive substring match against _COMPLIANCE_FEEL_TERMS.
    """
    if not feeling or avg_kerb <= _COMPLIANCE_KERB_THRESHOLD:
        return False
    text = feeling.lower()
    return any(term in text for term in _COMPLIANCE_FEEL_TERMS)


# ---------------------------------------------------------------------------
# Location confidence helpers
# ---------------------------------------------------------------------------

def _derive_location_confidence(
    loc_id: str,
    lay_id: str,
    event_ctx: dict,
    explicit: "str | None",
) -> str:
    """Return "high" or "low" for the track model's location confidence.

    Resolution order:
    1. explicit param ("high" | "low") if provided.
    2. event_ctx["location_confidence"] if present.
    3. Lazy import from data.track_model_resolver — "high" only for
       REVIEWED_MODEL / AI_READY_REVIEWED_MODEL / ENGINEER_VALIDATED_MODEL.
       Any import failure, missing IDs, or SEED_ONLY/SEED_ONLY_FALLBACK/MISSING
       yields "low".
    4. Also checks event_ctx["corner_issues"] for confidence < 0.6 which
       overrides to "low" even if the model source is reviewed.
    Default when uncertain: "low" (conservative).
    """
    # 1. Explicit caller param
    if explicit is not None:
        return "high" if str(explicit).lower() == "high" else "low"

    # 2. event_ctx stash
    ctx_conf = event_ctx.get("location_confidence")
    if ctx_conf is not None:
        return "high" if str(ctx_conf).lower() == "high" else "low"

    # 3. Lazy resolver lookup — everything guarded by try/except
    if loc_id and lay_id:
        try:
            from data.track_model_resolver import (
                resolve_best_track_model,
                TrackModelSourceType,
            )
            result = resolve_best_track_model(loc_id, lay_id)
            _HIGH_SOURCES = {
                TrackModelSourceType.REVIEWED_MODEL,
                TrackModelSourceType.AI_READY_REVIEWED_MODEL,
                TrackModelSourceType.ENGINEER_VALIDATED_MODEL,
            }
            if result.source_type in _HIGH_SOURCES:
                # Double-check: if caller supplies corner_issues with low confidence, downgrade
                corner_issues = event_ctx.get("corner_issues") or []
                if corner_issues:
                    try:
                        min_conf = min(
                            float(ci.confidence) if hasattr(ci, "confidence")
                            else float(ci.get("confidence", 1.0))
                            for ci in corner_issues
                        )
                        if min_conf < 0.6:
                            return "low"
                    except Exception:
                        pass
                return "high"
        except Exception:
            pass  # Any import or lookup failure -> conservative "low"

    return "low"


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def _build_setup_diagnosis_conservative() -> dict:
    """Return a fully-keyed conservative diagnosis dict for use when
    build_setup_diagnosis encounters an unexpected exception.

    All numeric fields are 0.0 / False / None so that validation rules
    default to their most permissive safe state (bands are 'minor'/'low',
    no aero-near-min, gearbox preserved), rather than an empty dict that
    makes every rule silently pass with undefined data.
    """
    return {
        "avg_bottoming":              0.0,
        "bottoming_band":             "minor",
        "avg_wheelspin":              0.0,
        "wheelspin_band":             "low",
        "avg_snap":                   0.0,
        "avg_lockups":                0.0,
        "avg_rev_limiter_total":      0.0,
        "rev_limiter_by_gear":        None,
        "avg_top_speed_kmh":          0.0,
        "top_speed_target_kmh":       0.0,
        "gearbox_flag":               "preserve",
        "aero_front_value":           None,
        "aero_front_near_min":        False,
        "aero_rear_value":            0.0,
        "aero_rear_near_min":         False,
        "driver_feel_flags":          {},
        "wheelspin_by_gear":          None,
        "lockups_by_gear":            None,
        "event_type":                 "unknown",
        "is_timed_race":              False,
        "dominant_problem":           "unknown",
        "secondary_problems":         [],
        "driver_feel_supported_by_telemetry": False,
        "recommended_tuning_priority": [],
        "location_confidence":        "low",
        "location_evidence_usable":   False,
        # A7: new keys — safe defaults (conservative / no data)
        "gearing_diagnosis_category": "insufficient_data",
        "wheelspin_subtype":          "insufficient_data",
        "compliance_priority":        False,
    }


def build_setup_diagnosis(
    laps: "list[LapStats]",
    setup: dict,
    car_name: str,
    event_ctx: dict,
    feeling: str | None,
    location_confidence: "str | None" = None,
) -> dict:
    """Build a structured setup diagnosis from laps, setup, and driver feel.

    Parameters
    ----------
    laps:
        list[LapStats] — may be empty; all averages default to 0.0 when empty.
    setup:
        Current car setup dict (canonical keys).
    car_name:
        Used to resolve per-car aero ranges.
    event_ctx:
        Event context dict (same schema as DrivingAdvisor._event_ctx).
    feeling:
        Free-text driver feeling string, or None.
    location_confidence:
        Optional explicit override: "high" | "low" | None.
        When None, derived from event_ctx["location_confidence"] or the track
        model resolver (lazy import, guarded by try/except). Defaults to "low"
        (conservative) when no signal is available.

    Returns
    -------
    dict with all documented keys including "location_confidence" and
    "location_evidence_usable".

    This function is exception-safe: any unexpected error during aggregation
    returns a conservative fully-keyed dict (via _build_setup_diagnosis_conservative)
    rather than raising or returning {}.
    """
    try:
        return _build_setup_diagnosis_inner(
            laps, setup, car_name, event_ctx, feeling, location_confidence
        )
    except Exception:
        return _build_setup_diagnosis_conservative()


def _build_setup_diagnosis_inner(
    laps: "list[LapStats]",
    setup: dict,
    car_name: str,
    event_ctx: dict,
    feeling: str | None,
    location_confidence: "str | None",
) -> dict:
    """Inner implementation of build_setup_diagnosis — not exception-safe.

    Called exclusively by build_setup_diagnosis which wraps it in a
    try/except to ensure callers always receive a fully-keyed dict.
    """
    from strategy.setup_ranges import resolve_ranges

    ranges = resolve_ranges(car_name)

    # ------------------------------------------------------------------
    # Location confidence
    # ------------------------------------------------------------------
    _loc_id = event_ctx.get("track_location_id") or event_ctx.get("loc_id") or ""
    _lay_id = event_ctx.get("layout_id") or event_ctx.get("lay_id") or ""
    loc_conf = _derive_location_confidence(_loc_id, _lay_id, event_ctx, location_confidence)
    loc_evidence_usable = (loc_conf == "high")

    # ------------------------------------------------------------------
    # Aggregate per-lap counters
    # ------------------------------------------------------------------
    if laps:
        avg_bottoming = sum(getattr(l, "bottoming_count", 0) for l in laps) / len(laps)
        avg_wheelspin = sum(getattr(l, "wheelspin_count", 0) for l in laps) / len(laps)
        avg_snap      = sum(getattr(l, "snap_throttle_count", 0) for l in laps) / len(laps)
        avg_lockups   = sum(getattr(l, "lock_up_count", 0) for l in laps) / len(laps)

        # Rev limiter total across all laps
        avg_rev_limiter_total = sum(getattr(l, "rev_limiter_count", 0) for l in laps) / len(laps)

        # Rev limiter by gear — aggregate across all laps
        _gear_totals: dict[int, int] = {}
        for lap in laps:
            for g, cnt in getattr(lap, "rev_limiter_by_gear", {}).items():
                _gear_totals[g] = _gear_totals.get(g, 0) + cnt
        # Average per gear over the lap sample
        rev_limiter_by_gear: dict | None = (
            {g: cnt / len(laps) for g, cnt in _gear_totals.items()}
            if _gear_totals else None
        )

        avg_top_speed_kmh = sum(getattr(l, "max_speed_kmh", 0.0) for l in laps) / len(laps)
    else:
        avg_bottoming         = 0.0
        avg_wheelspin         = 0.0
        avg_snap              = 0.0
        avg_lockups           = 0.0
        avg_rev_limiter_total = 0.0
        rev_limiter_by_gear   = None
        avg_top_speed_kmh     = 0.0

    # ------------------------------------------------------------------
    # Bands
    # ------------------------------------------------------------------
    b_band = _bottoming_band(avg_bottoming)
    w_band = _wheelspin_band(avg_wheelspin)

    # ------------------------------------------------------------------
    # Aero values from setup
    # ------------------------------------------------------------------
    _aero_f_raw = setup.get("aero_front")
    _aero_r_raw = setup.get("aero_rear")

    try:
        aero_front_value: float | None = float(_aero_f_raw) if _aero_f_raw is not None else None
    except (TypeError, ValueError):
        aero_front_value = None

    try:
        aero_rear_value: float = float(_aero_r_raw) if _aero_r_raw is not None else 0.0
    except (TypeError, ValueError):
        aero_rear_value = 0.0

    # Near-min check using per-car ranges
    _af_lo, _af_hi = ranges.get("aero_front", (0, 1000))
    _ar_lo, _ar_hi = ranges.get("aero_rear", (0, 1000))
    aero_front_near_min = _aero_near_min(aero_front_value, float(_af_lo), float(_af_hi))
    aero_rear_near_min  = _aero_near_min(aero_rear_value if _aero_r_raw is not None else None,
                                          float(_ar_lo), float(_ar_hi))

    # ------------------------------------------------------------------
    # Top speed target from setup
    # ------------------------------------------------------------------
    _ts_raw = setup.get("transmission_max_speed_kmh")
    try:
        top_speed_target_kmh = float(_ts_raw) if _ts_raw else 0.0
    except (TypeError, ValueError):
        top_speed_target_kmh = 0.0

    # ------------------------------------------------------------------
    # Gearbox flag and advanced gearing / wheelspin / compliance diagnosis
    # ------------------------------------------------------------------
    driver_feel_flags = _parse_driver_feel(feeling)

    # A6: Collect all frames across laps for top-gear signal analysis
    all_frames: list = []
    for lap in laps:
        all_frames.extend(getattr(lap, "frames", []))

    avg_kerb = sum(getattr(l, "kerb_count", 0) for l in laps) / len(laps) if laps else 0.0

    # Gearing diagnosis category (replaces the flat 93%-threshold logic)
    gearing_diagnosis_category = _classify_gearing(
        all_frames,
        rev_limiter_by_gear,
        avg_top_speed_kmh,
        top_speed_target_kmh,
        w_band,
    )

    # Wheelspin subtype
    wheelspin_subtype = _classify_wheelspin_subtype(
        all_frames,
        rev_limiter_by_gear,
        w_band,
        avg_snap,
        aero_rear_near_min,
        laps,
    )

    # Compliance priority
    compliance_priority = _detect_compliance_priority(feeling, avg_kerb)

    # Gearbox flag: derived from the gearing_diagnosis_category rather than
    # the old flat 93%/limiter heuristic, so the AI block and the validation
    # rule are consistent.
    # "preserve" categories: insufficient_data, gear_too_long, limiter_limited
    #   (limiter_limited = hitting the limiter at the right speed — gearbox correct)
    # "may_change" categories: gear_too_short, top_gear_power_band_limited,
    #   traction_limited_acceleration, drag_or_power_limited
    _PRESERVE_CATEGORIES = {"insufficient_data", "gear_too_long", "limiter_limited"}
    gearbox_flag = (
        "preserve"
        if gearing_diagnosis_category in _PRESERVE_CATEGORIES
        else "may_change"
    )

    # Driver override: if driver says gearbox is good, always force preserve
    if driver_feel_flags.get("gearbox_good"):
        gearbox_flag = "preserve"

    # ------------------------------------------------------------------
    # Event classification
    # ------------------------------------------------------------------
    race_type = event_ctx.get("race_type", "")
    if race_type in ("lap", "timed"):
        event_type = race_type
    else:
        event_type = "unknown"

    # Timed race: race_type == "timed", or laps_in_race == 0 for online timed
    is_timed_race = (
        race_type == "timed"
        or int(event_ctx.get("laps", 0) or 0) == 0 and race_type not in ("lap",)
    )

    # ------------------------------------------------------------------
    # Dominant problem and tuning priority
    # ------------------------------------------------------------------
    dominant_problem, secondary_problems = _derive_dominant_problem(
        driver_feel_flags, b_band, w_band, aero_front_near_min, aero_rear_near_min
    )
    recommended_tuning_priority = _derive_tuning_priority(
        driver_feel_flags, b_band, w_band, aero_front_near_min, aero_rear_near_min,
        location_evidence_usable=loc_evidence_usable,
        compliance_priority=compliance_priority,
    )
    feel_supported = _driver_feel_supported_by_telemetry(
        driver_feel_flags, w_band, aero_front_near_min, aero_rear_near_min, avg_lockups
    )

    return {
        # Averaged telemetry counters
        "avg_bottoming":              avg_bottoming,
        "bottoming_band":             b_band,
        "avg_wheelspin":              avg_wheelspin,
        "wheelspin_band":             w_band,
        "avg_snap":                   avg_snap,
        "avg_lockups":                avg_lockups,
        "avg_rev_limiter_total":      avg_rev_limiter_total,
        "rev_limiter_by_gear":        rev_limiter_by_gear,
        # Speed
        "avg_top_speed_kmh":          avg_top_speed_kmh,
        "top_speed_target_kmh":       top_speed_target_kmh,
        # Gearbox
        "gearbox_flag":               gearbox_flag,
        # Aero
        "aero_front_value":           aero_front_value,
        "aero_front_near_min":        aero_front_near_min,
        "aero_rear_value":            aero_rear_value,
        "aero_rear_near_min":         aero_rear_near_min,
        # Driver feel
        "driver_feel_flags":          driver_feel_flags,
        # Fields not on LapStats
        "wheelspin_by_gear":          None,
        "lockups_by_gear":            None,
        # Event
        "event_type":                 event_type,
        "is_timed_race":              is_timed_race,
        # Derived diagnosis
        "dominant_problem":           dominant_problem,
        "secondary_problems":         secondary_problems,
        "driver_feel_supported_by_telemetry": feel_supported,
        "recommended_tuning_priority": recommended_tuning_priority,
        # Location confidence (new — addendum requirement)
        "location_confidence":        loc_conf,
        "location_evidence_usable":   loc_evidence_usable,
        # A6: advanced gearing / wheelspin / compliance diagnosis
        "gearing_diagnosis_category": gearing_diagnosis_category,
        "wheelspin_subtype":          wheelspin_subtype,
        "compliance_priority":        compliance_priority,
    }


# ---------------------------------------------------------------------------
# Engineering validation
# ---------------------------------------------------------------------------

def validate_setup_engineering(
    parsed_ai_response: dict,
    diagnosis: dict,
    setup: dict,
    ranges: dict,
    event_ctx: dict,
    car_name: str = "",
    rec_history: "dict | None" = None,
) -> list[str]:
    """Validate an AI response dict against engineering rules derived from diagnosis.

    Composes with _validate_setup_response (range/locked/no-op/too-many-changes)
    by calling it and merging its list.

    Parameters
    ----------
    parsed_ai_response:
        Already-parsed (and normalised) AI response dict.
    diagnosis:
        Output of build_setup_diagnosis for the same session.
    setup:
        Current car setup dict (canonical keys).
    ranges:
        Resolved per-car ranges dict from resolve_ranges().
    event_ctx:
        Event context dict.
    rec_history:
        Optional dict with shape:
          {"lsd_accel": {"prior_value": float|None, "prior_direction": str|None,
                         "worsened_verdict_exists": bool}}
        When None, the lsd_reversal_without_evidence rule is skipped.

    Returns
    -------
    list[str] — human-readable failure reasons; empty when all rules pass.
    Each reason string begins with a stable code prefix (e.g. "rh_for_minor_bottoming: ").
    """
    reasons: list[str] = []

    bottoming_band              = diagnosis.get("bottoming_band", "minor")
    wheelspin_band_v            = diagnosis.get("wheelspin_band", "low")
    feel_flags                  = diagnosis.get("driver_feel_flags") or {}
    aero_front_nm               = diagnosis.get("aero_front_near_min", False)
    gearbox_flag                = diagnosis.get("gearbox_flag", "preserve")
    gearing_diagnosis_category  = diagnosis.get("gearing_diagnosis_category", "insufficient_data")
    # Location confidence — default to False (conservative) when key absent
    loc_evidence_usable         = diagnosis.get("location_evidence_usable", False)

    # Read AI-recommended setup_fields and changes
    ai_sf     = parsed_ai_response.get("setup_fields") or {}
    ai_changes = parsed_ai_response.get("changes") or []

    # ----------------------------------------------------------------
    # Helpers: detect AI change direction from setup_fields vs current setup
    # ----------------------------------------------------------------
    def _ai_value(key: str):
        """Return the AI's recommended numeric value for a canonical key, or None."""
        if key in ai_sf:
            try:
                return float(ai_sf[key])
            except (TypeError, ValueError):
                pass
        # Fall back to scanning changes[]
        for ch in ai_changes:
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

    def _current_value(key: str):
        """Return the current numeric setup value for key, or None."""
        v = setup.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def _ai_changes_field(key: str) -> bool:
        """Return True if the AI response changes the given canonical key."""
        if key in ai_sf:
            return True
        for ch in ai_changes:
            if ch.get("field") == key:
                return True
        return False

    # ----------------------------------------------------------------
    # RULE: rh_for_minor_bottoming
    # ----------------------------------------------------------------
    # AI recommends ANY ride-height increase AND bottoming_band in {"minor", "moderate"}
    for rh_key in ("ride_height_front", "ride_height_rear"):
        ai_rh = _ai_value(rh_key)
        cur_rh = _current_value(rh_key)
        if ai_rh is not None and cur_rh is not None:
            if ai_rh > cur_rh and bottoming_band in ("minor", "moderate"):
                reasons.append(
                    f"rh_for_minor_bottoming: AI increases {rh_key} ({cur_rh} -> {ai_rh}) "
                    f"but bottoming is only '{bottoming_band}' ({diagnosis.get('avg_bottoming', 0):.2f}/lap) "
                    f"— ride height increase is not warranted below the 'consider' threshold (>1.0/lap)."
                )

    # ----------------------------------------------------------------
    # RULE: rh_low_confidence_location
    # ----------------------------------------------------------------
    # AI increases ride height AND location evidence is not usable (low track
    # model confidence) AND bottoming is not "required".
    # This catches cases where the only justification could be low-confidence
    # location data — we cannot trust corner-specific bottoming attribution.
    if not loc_evidence_usable and bottoming_band != "required":
        for rh_key in ("ride_height_front", "ride_height_rear"):
            ai_rh = _ai_value(rh_key)
            cur_rh = _current_value(rh_key)
            if ai_rh is not None and cur_rh is not None:
                if ai_rh > cur_rh:
                    # Only add this reason if not already caught by rh_for_minor_bottoming
                    # (avoid duplicate reasons for the minor/moderate case)
                    if bottoming_band not in ("minor", "moderate"):
                        reasons.append(
                            f"rh_low_confidence_location: AI increases {rh_key} ({cur_rh} -> {ai_rh}) "
                            f"but track model confidence is LOW (location_evidence_usable=False) "
                            f"and bottoming is '{bottoming_band}' — not severe enough to override "
                            f"the low-confidence location guard. Justify ride-height changes from "
                            f"average count per lap, not unverified corner-location data."
                        )

    # ----------------------------------------------------------------
    # RULE: aero_cut_with_wheelspin
    # ----------------------------------------------------------------
    ai_ar = _ai_value("aero_rear")
    cur_ar = _current_value("aero_rear")
    if ai_ar is not None and cur_ar is not None:
        if ai_ar < cur_ar and wheelspin_band_v in ("meaningful", "major", "severe"):
            reasons.append(
                f"aero_cut_with_wheelspin: AI reduces aero_rear ({cur_ar} -> {ai_ar}) "
                f"but wheelspin band is '{wheelspin_band_v}' — removing rear downforce "
                f"worsens traction instability."
            )

    # ----------------------------------------------------------------
    # RULE: aero_at_min_floaty
    # ----------------------------------------------------------------
    floaty_or_entry_us = (
        feel_flags.get("floaty_front") or feel_flags.get("entry_understeer")
    )
    if floaty_or_entry_us and aero_front_nm:
        ai_af = _ai_value("aero_front")
        cur_af = _current_value("aero_front")
        _af_lo, _af_hi = ranges.get("aero_front", (0, 1000))
        _near_min_threshold = float(_af_lo) + 0.10 * (float(_af_hi) - float(_af_lo))

        # Reject when:
        # a) AI reduces aero_front to <= near-min threshold
        if ai_af is not None and ai_af <= _near_min_threshold:
            reasons.append(
                f"aero_at_min_floaty: AI sets aero_front to {ai_af} which is at or below "
                f"the near-minimum threshold ({_near_min_threshold:.1f}) while driver reports "
                f"floaty/understeer feel AND front aero is already platform-limited."
            )
        # b) AI does not address front aero at all while front aero is near-min
        elif not _ai_changes_field("aero_front"):
            reasons.append(
                f"aero_at_min_floaty: AI does not address aero_front (currently near minimum) "
                f"while driver reports floaty/understeer feel and diagnosis is front aero / "
                f"platform limited. Front downforce must be increased or explicitly defended."
            )

    # ----------------------------------------------------------------
    # RULE: gearbox_category_mismatch (replaces gearbox_edit_when_preserve)
    # ----------------------------------------------------------------
    # Only block gear changes when the gearing diagnosis indicates no change is
    # needed (insufficient_data or preserve categories) AND the driver has not
    # flagged gearbox as good already.  For "may_change" categories the AI is
    # allowed to adjust gearing — this is the primary difference from the old rule.
    _PRESERVE_GEARBOX_CATEGORIES = {"insufficient_data", "gear_too_long", "limiter_limited"}
    _gearbox_blocked = (
        gearing_diagnosis_category in _PRESERVE_GEARBOX_CATEGORIES
        or feel_flags.get("gearbox_good")
    )
    if _gearbox_blocked:
        if _ai_changes_field("transmission_max_speed_kmh"):
            ai_ts = _ai_value("transmission_max_speed_kmh")
            cur_ts = _current_value("transmission_max_speed_kmh")
            if ai_ts is not None and cur_ts is not None and ai_ts != cur_ts:
                reasons.append(
                    f"gearbox_category_mismatch: AI changes transmission_max_speed_kmh "
                    f"({cur_ts} -> {ai_ts}) but gearing_diagnosis_category is "
                    f"'{gearing_diagnosis_category}' (gearbox should be preserved)."
                )
        for ch in ai_changes:
            if ch.get("field") == "gear_ratios" or "gear_ratio" in str(ch.get("field", "")).lower():
                reasons.append(
                    f"gearbox_category_mismatch: AI recommends gear ratio change but "
                    f"gearing_diagnosis_category is '{gearing_diagnosis_category}' "
                    "(gearbox should be preserved)."
                )
                break

    # ----------------------------------------------------------------
    # RULE: lsd_reversal_without_evidence
    # ----------------------------------------------------------------
    # If rec_history provides prior lsd_accel direction, and the AI now
    # reverses that direction without a worsened verdict justifying it,
    # flag the reversal.
    if rec_history is not None:
        _lsd_hist = rec_history.get("lsd_accel") or {}
        _prior_value = _lsd_hist.get("prior_value")
        _prior_direction = _lsd_hist.get("prior_direction")
        _worsened = _lsd_hist.get("worsened_verdict_exists", False)
        # Skip when prior data or worsened justification is missing
        if _prior_value is not None and _prior_direction is not None and not _worsened:
            _ai_lsd = _ai_value("lsd_accel")
            _cur_lsd = _current_value("lsd_accel")
            if _ai_lsd is not None and _cur_lsd is not None and _ai_lsd != _cur_lsd:
                _new_direction = "increase" if _ai_lsd > _cur_lsd else "decrease"
                if _new_direction != _prior_direction:
                    reasons.append(
                        f"lsd_reversal_without_evidence: AI reverses lsd_accel direction "
                        f"(prior_value={_prior_value}, prior_direction='{_prior_direction}', "
                        f"current={_cur_lsd}, new={_ai_lsd}, new_direction='{_new_direction}'). "
                        f"reversal_reason: no worsened verdict on record — prior direction "
                        f"has not been proven counterproductive."
                    )

    # ----------------------------------------------------------------
    # RULE: malformed_schema
    # ----------------------------------------------------------------
    _REQUIRED_KEYS = {"analysis", "primary_issue", "changes", "setup_fields",
                      "validation_targets", "confidence"}
    missing = _REQUIRED_KEYS - set(parsed_ai_response.keys())
    if missing:
        reasons.append(
            f"malformed_schema: AI response missing required keys: {sorted(missing)}."
        )

    # ----------------------------------------------------------------
    # RULE: invalid_units
    # ----------------------------------------------------------------
    # Springs values expressed in N/mm scale (> 20.0) are a units error.
    for ch in ai_changes:
        field = ch.get("field", "")
        if field in ("springs_front", "springs_rear"):
            tc = ch.get("to_clamped")
            if tc is not None:
                try:
                    val = float(tc)
                    if val > 20.0:
                        reasons.append(
                            f"invalid_units: {field} to_clamped={val} exceeds 20.0 — "
                            f"value appears to be in N/mm scale, not Hz. "
                            f"GT7 springs are expressed in natural frequency (Hz), range 1.00–20.00."
                        )
                except (TypeError, ValueError):
                    pass

    # ----------------------------------------------------------------
    # Merge _validate_setup_response errors
    # ----------------------------------------------------------------
    # Lazy import here to avoid circular import at module level
    # (driving_advisor imports this module).  Only the IMPORT is guarded —
    # if the function is available and raises, we let that propagate so
    # locked-field / range errors are never silently dropped.
    _base_validator = None
    _derive_locked = None
    try:
        from strategy.driving_advisor import _validate_setup_response as _base_validator  # noqa: F401
        from strategy.driving_advisor import _derive_locked_fields as _derive_locked  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pass  # Circular-import guard: base validator unavailable at this import stage

    if _base_validator is not None:
        allowed_tuning = event_ctx.get("allowed_tuning") or None
        locked = _derive_locked(allowed_tuning) if (_derive_locked and allowed_tuning) else None
        _parsed_copy = dict(parsed_ai_response)
        _parsed_copy = _base_validator(_parsed_copy, car_name, allowed_tuning, locked, setup)
        _base_errors = _parsed_copy.get("validation_errors") or []
        reasons.extend(_base_errors)

    return reasons


# ---------------------------------------------------------------------------
# Prompt injection helper — build the diagnosis section for prompt injection
# ---------------------------------------------------------------------------

def format_diagnosis_for_prompt(diagnosis: dict) -> str:
    """Return a markdown section describing the pre-computed diagnosis.

    Injected into _build_combined_prompt and _build_setup_prompt BEFORE
    the AI is asked for changes.

    When location_confidence is "low", emits zone/lap-percentage language
    for location-sensitive metrics and a hard caveat that ride-height changes
    must NOT be justified from low-confidence location data.
    """
    if not diagnosis:
        return ""

    loc_conf = diagnosis.get("location_confidence", "low")
    loc_usable = diagnosis.get("location_evidence_usable", False)

    lines = ["## Setup Diagnosis (prepared by the app)"]

    # Location confidence header — emit caveat before other data so the AI
    # sees it before any bottoming/wheelspin numbers.
    if not loc_usable:
        lines.append(
            "Track model confidence is LOW — corner identities are not verified. "
            "Treat locations as approximate zones (lap %), not exact corners. "
            "Do NOT justify ride-height changes from low-confidence location data."
        )
    else:
        lines.append("Track model confidence: HIGH — corner-level location data is verified.")

    lines.append(
        f"Bottoming: avg {diagnosis.get('avg_bottoming', 0):.2f}/lap "
        f"(band: {diagnosis.get('bottoming_band', 'n/a')})"
        + (" — locations: approximate zones only (lap %) — not verified corners" if not loc_usable else "")
    )
    lines.append(
        f"Wheelspin: avg {diagnosis.get('avg_wheelspin', 0):.2f}/lap "
        f"(band: {diagnosis.get('wheelspin_band', 'n/a')})"
        + (" — locations: approximate zones only (lap %)" if not loc_usable else "")
    )
    lines.append(
        f"Lockups: avg {diagnosis.get('avg_lockups', 0):.2f}/lap"
        + (" — locations: approximate zones only (lap %)" if not loc_usable else "")
    )
    lines.append(
        f"Rev limiter: avg {diagnosis.get('avg_rev_limiter_total', 0):.2f}/lap"
    )
    ts = diagnosis.get("avg_top_speed_kmh", 0)
    ts_target = diagnosis.get("top_speed_target_kmh", 0)
    if ts > 0:
        lines.append(
            f"Top speed: {ts:.0f} km/h"
            + (f" vs target {ts_target:.0f} km/h" if ts_target > 0 else "")
        )
    lines.append(
        f"Aero front: {diagnosis.get('aero_front_value', 'n/a')} "
        f"(near min: {diagnosis.get('aero_front_near_min', False)})"
    )
    lines.append(
        f"Aero rear: {diagnosis.get('aero_rear_value', 'n/a')} "
        f"(near min: {diagnosis.get('aero_rear_near_min', False)})"
    )
    lines.append(
        f"Gearbox flag: {diagnosis.get('gearbox_flag', 'preserve')}"
    )
    # A11: emit new gearing / wheelspin diagnosis fields
    gearing_cat = diagnosis.get("gearing_diagnosis_category", "")
    if gearing_cat:
        lines.append(f"Gearing diagnosis: {gearing_cat}")
    ws_subtype = diagnosis.get("wheelspin_subtype", "")
    if ws_subtype:
        lines.append(f"Wheelspin subtype: {ws_subtype}")

    feel_flags = diagnosis.get("driver_feel_flags") or {}
    active_flags = [k for k, v in feel_flags.items() if v]
    if active_flags:
        lines.append(f"Driver feel flags: {', '.join(active_flags)}")
    lines.append(
        f"Feel supported by telemetry: {diagnosis.get('driver_feel_supported_by_telemetry', False)}"
    )
    lines.append(f"Dominant problem: {diagnosis.get('dominant_problem', 'unknown')}")
    secondary = diagnosis.get("secondary_problems") or []
    if secondary:
        lines.append(f"Secondary problems: {'; '.join(secondary)}")
    priority = diagnosis.get("recommended_tuning_priority") or []
    if priority:
        lines.append(f"Recommended tuning priority: {' → '.join(priority[:3])}")

    # A11: compliance priority directive
    if diagnosis.get("compliance_priority"):
        lines.append(
            "Compliance priority: TRUE — natural frequency and damping must appear first "
            "or second in tuning priority. Address kerb and surface compliance before "
            "stability tuning."
        )

    # Reiterate low-confidence ride-height constraint at the end so it frames the ask
    if not loc_usable:
        lines.append(
            "CONSTRAINT: Do NOT recommend a ride-height increase based on corner-location "
            "evidence — location data is approximate (lap %) only. Base any ride-height "
            "decision solely on the avg bottoming count per lap shown above."
        )

    return "\n".join(lines)
