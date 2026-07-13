"""Setup diagnosis module for NGR Pit Crew / GT7 Pit Crew app.

Pure Python — no Qt, no network imports.
All functions are safe to call in plain pytest without any running Qt app.

Group 42 — Rule-First Setup Brain
----------------------------------
This module produces the diagnosis dict consumed by the rule engine
(strategy/setup_rule_engine.py).  The AI is NO LONGER called to generate
setup changes directly — it is called only for an audit step after the
deterministic rule engine has produced a plan.

Flow (canonical path — build_combined_setup_response in driving_advisor.py):
  1. build_setup_diagnosis → structured diagnosis dict (this module).
  2. build_driver_profile  → DriverProfile (setup_driver_profile.py).
  3. run_rule_engine       → SetupPlan (setup_rule_engine.py).
  4. plan_to_raw_data      → raw_data dict (setup_plan.py).
  5. _normalise_changes + validate_setup_engineering_structured → validation.
  6. Blocking failure → _build_deterministic_fallback (no AI retry).
  7. api_key + no fallback → build_audit_prompt + call_api (audit only).
  8. _finalise_recommendation → SetupRecommendationResult.

Rule-pack registration: strategy/setup_knowledge_base.register_pack().

Public API
----------
build_setup_diagnosis(laps, setup, car_name, event_ctx, feeling) -> dict
    Aggregates LapStats telemetry + driver feel into a structured diagnosis dict.

validate_setup_engineering(parsed_ai_response, diagnosis, setup, ranges, event_ctx) -> list[str]
    Post-processes a response dict against the diagnosis to detect engineering-rule
    violations.  Returns human-readable reason strings with stable prefixes.

_parse_driver_feel(feeling) -> dict[str, bool]
    Case-insensitive substring classifier for driver feeling text.

Module-level constants (imported by driving_advisor.py and ai_planner.py)
--------------------------------------------------------------------------
PERSONAL_DRIVER_TUNING_MODEL  — compact block describing the driver's tuning style
DRIVER_HARD_CONSTRAINTS       — 8 verbatim hard constraints for the AI
"""
from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from telemetry.recorder import LapStats

# ENG_SAFETY_PREFIXES is defined in _setup_constants to avoid a circular import
# (driving_advisor imports setup_diagnosis; setup_diagnosis back-imports
# driving_advisor inside validate_setup_engineering).
from strategy._setup_constants import ENG_SAFETY_PREFIXES  # noqa: F401 — re-exported

# ---------------------------------------------------------------------------
# ValidationFailure — structured result for the new validate_setup_engineering_structured
# ---------------------------------------------------------------------------

class ValidationFailure(NamedTuple):
    """A single engineering-validation failure with severity.

    severity ∈ {"info", "warning", "blocking"}
    code     — stable prefix string (e.g. "rh_for_minor_bottoming")
    message  — human-readable explanation including current values
    """
    code: str
    message: str
    severity: str

# ---------------------------------------------------------------------------
# Gearbox range constants — documented so validators stay in sync with prompts
# ---------------------------------------------------------------------------
_FINAL_DRIVE_RANGE: tuple[float, float] = (2.5, 6.0)
_GEAR_RATIO_RANGE: tuple[float, float] = (0.5, 4.0)

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
    # Floaty / vague TURN-IN only. "understeer" / "push" / "washes" were removed
    # here (UAT): "Pushes wide" is mid-corner understeer, a distinct problem whose
    # fix is the OPPOSITE of the floaty-front turn-in fix. They now route to
    # mid_corner_understeer below.
    "floaty_front": [
        "floaty", "floats",
        "won't turn", "front doesn't bite", "no front bite", "lazy turn",
        "vague front", "front feels light",
    ],
    # Mid-corner / apex understeer — the front lacks grip THROUGH the corner
    # (car "pushes wide" / "runs wide"). Fixed by ADDING front grip (soften front
    # ARB / add front aero), never by stiffening the front.
    "mid_corner_understeer": [
        "pushes wide", "push wide", "pushing wide", "runs wide", "running wide",
        "washes wide", "washes out", "won't rotate", "mid understeer",
        "mid-corner understeer", "apex understeer", "understeer mid",
    ],
    # Driver is happy with turn-in / entry balance — suppress turn-in changes.
    "entry_balance_good": [
        "good balance", "balance is good", "good turn-in", "good turn in",
        "turn-in good", "turn in good", "happy with turn", "entry good",
    ],
    "entry_understeer": [
        "entry understeer", "pushes on entry", "braking understeer",
        "front tucks", "can't trail",
        # Structured "Corner Entry" dropdown phrasing (ui/dashboard.py feedback form).
        "corner entry: too much understeer", "too much understeer on entry",
        "understeer on entry",
    ],
    "rear_loose_on_exit": [
        "rear loose", "rear steps", "oversteer on exit", "rear kicks",
        "rear slides", "loose on exit", "tail slides", "loose on throttle",
        "rear loose on exit",
    ],
    # Rear instability specifically UNDER BRAKING / on entry — a distinct problem
    # from throttle-exit looseness. Its fix lives on the coast/brake side
    # (lsd_decel / brake bias), NOT the accel side. Group 63: previously "rear
    # steps out under braking" was swallowed by the rear_loose_on_exit substring
    # "rear steps" and never reached lsd_decel. These phrases are braking-qualified
    # so they only fire with genuine braking context; the parser then re-attributes
    # a braking-only mention away from the exit flag.
    "rear_loose_under_braking": [
        "steps out under brak", "rear steps out under", "loose under brak",
        "rear loose under brak", "steps under brak", "unstable under brak",
        "rear wag under brak", "steps out on the brake", "steps out braking",
        "rear steps out under braking", "rear under braking: steps",
        "rear steps out on entry", "loose on the brakes", "rear light under brak",
    ],
    # Driver reports the DIFFERENTIAL itself feels wrong / the car will not connect
    # to the apex under power. This is the driver's direct LSD evidence and must
    # trigger evaluation of the full LSD triplet (initial / accel / decel), not be
    # misfiled as a front-aero "floaty" problem. Group 63.
    "lsd_feel_wrong": [
        "lsd is not", "lsd not set", "lsd isn't", "lsd feels", "lsd doesn't",
        "diff is not", "diff feels", "diff isn't", "differential feels",
        "not hooking up", "won't hook up", "doesn't hook up", "not hooking",
        "won't connect", "not connecting", "not driving off the apex",
        "won't drive off the apex", "not hooked up", "lsd is not set how i like",
    ],
    # Driver reports the gearing is too LONG — top gear is not fully used / the
    # car is not reaching the limiter on the main straight. This directly
    # contradicts a telemetry "gear too short" call and must be able to veto a
    # lengthening (final-drive-down) recommendation. Group 63.
    "gearing_too_long": [
        "not using all of sixth", "not using all of 6th", "sixth not fully used",
        "6th not fully used", "not using all of top gear", "gearing too long",
        "gear too long", "sixth gear not fully used", "6th gear not fully used",
        "not reaching the limiter", "never hits the limiter", "top gear too long",
        "not using sixth", "sixth is too long", "runs out of revs before",
        "not using full sixth", "not using all of the top gear",
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
    # Driver flagged high fuel use. Not a setup lever (driving/strategy owns fuel);
    # captured only so the analysis can acknowledge it instead of silently ignoring.
    "fuel_use_high": [
        "fuel use: higher", "higher than expected", "using too much fuel",
        "burning too much fuel", "fuel too high",
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
    # Group 63 — phase disambiguation for rear instability. A rear-instability
    # complaint qualified only by a BRAKING context is an entry/braking problem,
    # NOT a throttle-exit problem, even though "rear steps"/"rear loose" overlap
    # the exit vocabulary by substring. Re-attribute it: clear the exit flag when
    # the braking flag fired and there is no independent throttle/exit cue (when
    # BOTH are reported — as in the UAT — both flags legitimately remain).
    if result.get("rear_loose_under_braking") and not _has_throttle_exit_context(text):
        result["rear_loose_on_exit"] = False
    return result


# Throttle / corner-exit context cues — used to decide whether a rear-instability
# mention belongs to the exit phase (throttle) or the braking phase (coast).
_THROTTLE_EXIT_CUES: tuple[str, ...] = (
    "on throttle", "on the throttle", "on exit", "exit stability", "on the power",
    "power on", "corner exit", "getting on the power", "on power", "throttle exit",
    "off the apex", "on the gas", "loose on throttle", "rear loose on exit",
)


def _has_throttle_exit_context(text: str) -> bool:
    """True when the feedback contains an explicit throttle/corner-exit cue.

    Used to keep the exit flag alive when the driver reports BOTH throttle-exit
    looseness and braking looseness; a braking-only report clears the exit flag.
    """
    t = (text or "").lower()
    return any(cue in t for cue in _THROTTLE_EXIT_CUES)


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
# Bottoming impact model (Group 63) — severity by CONSEQUENCE, not by frequency
# ---------------------------------------------------------------------------
# The old model made a bottoming EVENT COUNT (> 2.0/lap) automatically "required"
# and dominant, with no measured performance consequence. A high count of expected
# kerb contact then buried the driver's real handling complaints. This model grades
# the same event count by whether a CONSEQUENCE is demonstrated.
BOTTOMING_NORMAL_OR_EXPECTED = "NORMAL_OR_EXPECTED"   # e.g. expected kerb contact
BOTTOMING_ADVISORY           = "ADVISORY"             # noticed, no measured effect
BOTTOMING_PERFORMANCE        = "PERFORMANCE_RELEVANT"  # a measured consequence exists
BOTTOMING_REQUIRED           = "REQUIRED"             # relevant AND well-evidenced
BOTTOMING_UNKNOWN            = "UNKNOWN"              # count-only, impact unmeasured


def _classify_bottoming_impact(
    b_band: str,
    subtype: str,
    confidence: str,
    driver_mentions_bottoming: bool,
    accel_fade_detected: bool,
    location_trustworthy: bool,
) -> dict:
    """Grade bottoming by demonstrated CONSEQUENCE, returning
    ``{"impact": <class>, "performance_relevant": bool, "reason": str}``.

    A high event count alone never yields REQUIRED. A measurable consequence is a
    driver-confirmed complaint OR a measured accel-fade (throttle held but speed not
    building — the closest available proxy for a real speed loss). Expected kerb
    contact is classified separately and never dominates on its own. When the count
    is high but no consequence can be measured, the honest verdict is UNKNOWN — a
    targeted test, not a ride-height change.
    """
    sub = str(subtype or "")
    has_consequence = bool(driver_mentions_bottoming or accel_fade_detected)

    # Expected kerb contact is normal race-craft, not a ride-height failure.
    if sub == "kerb_strike":
        if driver_mentions_bottoming:
            return {"impact": BOTTOMING_ADVISORY, "performance_relevant": False,
                    "reason": "kerb contact the driver noticed — expected on kerbs, monitor only"}
        return {"impact": BOTTOMING_NORMAL_OR_EXPECTED, "performance_relevant": False,
                "reason": "kerb contact — expected behaviour, no measured performance effect"}

    if b_band in ("minor", "moderate"):
        return {"impact": BOTTOMING_ADVISORY, "performance_relevant": False,
                "reason": f"{b_band} contact rate — below the action threshold, advisory only"}

    # consider / required bands
    if has_consequence:
        well_evidenced = b_band == "required" and (location_trustworthy or driver_mentions_bottoming)
        if well_evidenced:
            return {"impact": BOTTOMING_REQUIRED, "performance_relevant": True,
                    "reason": "frequent contact WITH a demonstrated consequence "
                              "(driver report / accel-fade) at a trustworthy location"}
        return {"impact": BOTTOMING_PERFORMANCE, "performance_relevant": True,
                "reason": "contact with a measured consequence (driver report / accel-fade) — "
                          "performance-relevant, confirm before a large ride-height change"}

    # High count, no measured consequence — honest UNKNOWN, never dominant.
    return {"impact": BOTTOMING_UNKNOWN, "performance_relevant": False,
            "reason": f"{b_band} contact RATE only — no measured speed/stability loss and no "
                      "driver mention; run a targeted test before treating it as dominant"}


# Group 64 — ONE canonical bottoming truth state for EVERY surface.
# Before Group 64 the UI header printed the raw count-based band ("required" when
# events/lap > 2.0) while a separate panel printed the consequence-graded impact
# ("NORMAL_OR_EXPECTED"), so the same run could read as *required* AND *normal* at
# once. This reconciles the two: the CONSEQUENCE (impact) governs urgency, and the
# raw count band is demoted to a supporting detail. No surface may render "required"
# unless the impact is genuinely performance-relevant.
_BOTTOMING_DISPLAY_BY_IMPACT: dict[str, dict] = {
    BOTTOMING_REQUIRED:           {"state": "address",     "severity": 4,
                                   "label": "address — frequent contact with a measured consequence"},
    BOTTOMING_PERFORMANCE:        {"state": "confirm",     "severity": 3,
                                   "label": "performance-relevant — confirm before a large ride-height change"},
    BOTTOMING_ADVISORY:           {"state": "advisory",    "severity": 2,
                                   "label": "advisory — noticed, no measured performance effect"},
    BOTTOMING_UNKNOWN:            {"state": "unconfirmed", "severity": 1,
                                   "label": "high contact rate, impact unconfirmed — run a targeted test"},
    BOTTOMING_NORMAL_OR_EXPECTED: {"state": "normal",      "severity": 0,
                                   "label": "normal / expected contact — no action"},
}


def _bottoming_display_state(b_band: str, bottoming_impact: dict) -> dict:
    """Return the single canonical bottoming state every surface must render.

    ``{"state", "label", "severity", "impact", "band", "performance_relevant"}``.
    ``state`` is derived from the CONSEQUENCE-graded impact, never the raw count
    band, so "required" can only appear when the impact is performance-relevant.
    The raw ``band`` is carried through for context but never governs the headline.
    """
    impact_cls = str((bottoming_impact or {}).get("impact") or BOTTOMING_UNKNOWN)
    perf = bool((bottoming_impact or {}).get("performance_relevant", False))
    disp = _BOTTOMING_DISPLAY_BY_IMPACT.get(
        impact_cls,
        {"state": "unconfirmed", "severity": 1, "label": "impact unconfirmed"},
    )
    return {
        "state": disp["state"],
        "label": disp["label"],
        "severity": disp["severity"],
        "impact": impact_cls,
        "band": str(b_band or ""),
        "performance_relevant": perf,
        "reason": str((bottoming_impact or {}).get("reason", "")),
    }


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
    """Return True when value <= lo + 10% of the (hi - lo) span.

    Hard integrity invariant (Phase 2): a value at or above the range maximum can
    NEVER be near-min. This blocks the class of defect where a stale/zeroed aero
    value or a wrong (placeholder) range made a car running MAX front aero read as
    ``near_min`` and cascaded into a nonsensical "increase front downforce"
    diagnosis. See tests/test_setup_snapshot_integrity.py.
    """
    if value is None:
        return False
    span = hi - lo
    if span <= 0:
        return False
    if value >= hi:
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
    aero_rear_healthy: bool = False,
    bottoming_evidence_insufficient: bool = False,
) -> tuple[str, list[str]]:
    """Return (dominant_problem, secondary_problems) as plain-English strings.

    ``bottoming_evidence_insufficient`` (Phase 3): when True, a telemetry-only
    "required" bottoming (low confidence + unusable location) is DEMOTED — it is
    appended last so it cannot outrank confirmed driver-feedback issues. If it is
    the only issue it still surfaces (and the coherence gate defers it).
    """
    issues: list[str] = []
    _defer_bottoming = False

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
        if bottoming_evidence_insufficient:
            # Thin-data required bottoming: defer to the end so confirmed feedback
            # (understeer, rear-loose, lockups) dominates instead.
            _defer_bottoming = True
        else:
            issues.append("bottoming")
    elif bottoming_band == "consider":
        if not _wheelspin_severe_ish or _driver_mentions_bottoming:
            issues.append("bottoming")

    # Group 63: mid-corner understeer ("pushes wide") is a confirmed front-grip
    # complaint. It was previously invisible to dominance selection (it could never
    # be dominant), so count-only bottoming buried it. It ranks above rear-traction
    # noise because a car that cannot rotate cannot use its rear grip.
    if driver_feel_flags.get("mid_corner_understeer"):
        issues.append("mid_corner_understeer")

    # Rear traction / aero
    # When aero_rear_healthy, skip the rear-aero/low-downforce issue
    if (
        wheelspin_band in ("major", "severe")
        or (driver_feel_flags.get("rear_loose_on_exit") and aero_rear_near_min)
    ):
        if not aero_rear_healthy:
            issues.append("rear_traction_aero")
        else:
            # Aero is healthy; still track wheelspin but don't blame rear aero
            if wheelspin_band in ("major", "severe"):
                issues.append("wheelspin")

    # Snap oversteer exit
    if driver_feel_flags.get("snap_oversteer_exit"):
        issues.append("snap_oversteer_exit")

    # Group 63: rear instability specifically UNDER BRAKING is a distinct confirmed
    # complaint (coast/brake side — lsd_decel / brake bias), not the same as
    # throttle-exit looseness. Previously it was swallowed by the exit flag.
    if driver_feel_flags.get("rear_loose_under_braking"):
        issues.append("rear_loose_under_braking")

    # Group 63: the driver's direct LSD complaint ("not hooking up at the apex /
    # LSD not how I like") is confirmed differential feedback that must be a
    # first-class issue rather than being misfiled as front-aero.
    if driver_feel_flags.get("lsd_feel_wrong"):
        issues.append("lsd_connection")

    # Braking instability / lockups
    if driver_feel_flags.get("braking_instability"):
        issues.append("braking_instability")

    # Wheelspin (any meaningful+)
    if wheelspin_band in ("meaningful", "major", "severe"):
        if "rear_traction_aero" not in issues and "wheelspin" not in issues:
            issues.append("wheelspin")

    # Deferred thin-data bottoming lands last — never outranks confirmed feedback.
    if _defer_bottoming:
        issues.append("bottoming")

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
        "mid_corner_understeer": "mid-corner understeer — the car pushes wide through the corner (front grip)",
        "rear_traction_aero": "rear traction / aero — wheelspin or rear instability with low rear downforce",
        "snap_oversteer_exit": "snap oversteer on exit — abrupt rear rotation at throttle application",
        "rear_loose_under_braking": "rear instability under braking — the rear steps out on the brakes (coast/brake side)",
        "lsd_connection": "differential connection — LSD does not hook up the car through the apex under power",
        "braking_instability": "braking instability — lockups or rear wag under braking",
        "wheelspin": f"wheelspin ({wheelspin_band})",
    }

    dominant_str = _readable.get(dominant, dominant)
    secondary_strs = [_readable.get(s, s) for s in secondary]
    return dominant_str, secondary_strs


_DOMINANT_KEYS: tuple[str, ...] = (
    "front_aero_platform_limited", "bottoming", "mid_corner_understeer",
    "rear_traction_aero", "snap_oversteer_exit", "rear_loose_under_braking",
    "lsd_connection", "braking_instability", "wheelspin",
)

# Fields that materially "address" each dominant problem — used by the Phase 3
# coherence gate to check that a plan actually treats its dominant problem.
# Group 63: a bare final_drive change must NOT count as "addressing" wheelspin —
# gearing is not a differential/traction fix and was the exact false-address defect.
DOMINANT_ADDRESSING_FIELDS: dict[str, frozenset] = {
    "bottoming":                   frozenset({"ride_height_front", "ride_height_rear",
                                              "springs_front", "springs_rear"}),
    "front_aero_platform_limited": frozenset({"aero_front", "arb_front"}),
    "mid_corner_understeer":       frozenset({"arb_front", "aero_front", "toe_front"}),
    "rear_traction_aero":          frozenset({"aero_rear", "lsd_accel", "lsd_initial"}),
    "snap_oversteer_exit":         frozenset({"lsd_accel", "lsd_decel", "aero_rear"}),
    "rear_loose_under_braking":    frozenset({"lsd_decel", "brake_bias"}),
    "lsd_connection":              frozenset({"lsd_initial", "lsd_accel", "lsd_decel"}),
    "braking_instability":         frozenset({"brake_bias", "lsd_decel", "ride_height_front",
                                              "ride_height_rear", "springs_front"}),
    "wheelspin":                   frozenset({"lsd_accel", "aero_rear",
                                              "gear_1", "gear_2", "gear_3", "gear_4",
                                              "gear_5", "gear_6"}),
}


# Phase 4 — every driver-feedback item must receive an explicit disposition.
_FEEDBACK_LABELS: dict[str, str] = {
    "entry_balance_good":    "Entry balance good",
    "mid_corner_understeer": "Mid-corner understeer (pushes wide)",
    "floaty_front":          "Floaty / vague front (turn-in)",
    "entry_understeer":      "Entry understeer",
    "rear_loose_on_exit":    "Rear loose on throttle",
    "rear_loose_under_braking": "Rear steps out under braking",
    "snap_oversteer_exit":   "Snap oversteer on exit",
    "braking_instability":   "Rear lock / instability under braking",
    "lsd_feel_wrong":        "LSD feels wrong / not hooking up at the apex",
    "gearing_too_long":      "Sixth gear not fully used (gearing too long)",
    "fuel_use_high":         "High fuel use",
}
_FEEDBACK_ADDRESSING_FIELDS: dict[str, frozenset] = {
    "mid_corner_understeer": frozenset({"arb_front", "aero_front", "toe_front"}),
    "floaty_front":          frozenset({"arb_front", "aero_front"}),
    "entry_understeer":      frozenset({"lsd_decel", "aero_front", "arb_front"}),
    "rear_loose_on_exit":    frozenset({"lsd_accel", "aero_rear", "arb_rear"}),
    "rear_loose_under_braking": frozenset({"lsd_decel", "brake_bias"}),
    "snap_oversteer_exit":   frozenset({"lsd_accel", "lsd_decel"}),
    "braking_instability":   frozenset({"brake_bias", "lsd_decel"}),
    # The driver's direct LSD complaint must evaluate the whole triplet.
    "lsd_feel_wrong":        frozenset({"lsd_initial", "lsd_accel", "lsd_decel"}),
    # Gearing-too-long is addressed by shortening the final drive (up) or the
    # upper indexed gears; never by lengthening (final_drive_down).
    "gearing_too_long":      frozenset({"final_drive", "gear_5", "gear_6"}),
}

# Handling-critical problems that must EACH be treated (addressed by a change,
# safely preserved, or converted into an explicit targeted test) before a plan may
# be called complete. `fuel_use_high` and `entry_balance_good` are excluded (fuel is
# a Strategy-Brain concern; entry_balance_good is a "leave it" report, not a problem).
_COMPLETENESS_FEEDBACK_PROBLEMS: frozenset = frozenset(_FEEDBACK_ADDRESSING_FIELDS)

# ---------------------------------------------------------------------------
# Group 64 — one canonical recommendation-completeness vocabulary.
# A change being *safe* is not the same as the setup being *complete*. These
# states let every surface (status banner, AI-audit, Apply gate label) agree on
# whether the plan is a finished setup, an incremental test, or still partial.
# ---------------------------------------------------------------------------
RECO_APPROVED_COMPLETE     = "approved_complete"
RECO_APPROVED_INCREMENTAL  = "approved_incremental_test"
RECO_PARTIAL               = "partial_recommendation"
RECO_TARGETED_TEST         = "targeted_test_required"
RECO_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
RECO_CONFLICTING_EVIDENCE  = "conflicting_evidence"
RECO_BLOCKED_UNSAFE        = "blocked_unsafe"
RECO_REJECTED_INCOHERENT   = "rejected_incoherent"


def _active_confirmed_problems(diagnosis: dict) -> "list[str]":
    """Return the handling-critical problems the driver actually reported, plus a
    synthetic ``wheelspin`` problem when telemetry shows major/severe wheelspin.

    These are the problems a *complete* setup must each treat. Telemetry-only
    wheelspin is included because the UAT setup left severe wheelspin untreated
    while claiming completeness.
    """
    flags = (diagnosis or {}).get("driver_feel_flags", {}) or {}
    problems = [p for p in _COMPLETENESS_FEEDBACK_PROBLEMS if flags.get(p)]
    ws_band = str((diagnosis or {}).get("wheelspin_band", "low"))
    if ws_band in ("major", "severe") and "wheelspin" not in problems:
        problems.append("wheelspin")
    return problems


def _problem_addressing_fields(problem: str) -> frozenset:
    """Fields that materially treat a problem (feedback set, falling back to the
    dominant-addressing set for the synthetic ``wheelspin`` problem)."""
    return _FEEDBACK_ADDRESSING_FIELDS.get(
        problem, DOMINANT_ADDRESSING_FIELDS.get(problem, frozenset()))


def assess_recommendation_completeness(
    diagnosis: dict,
    approved_fields,
    tested_fields=None,
    *,
    base_status: str = "approved",
    has_conflicting_evidence: bool = False,
) -> dict:
    """Decide whether an APPROVED plan is genuinely COMPLETE (Group 64).

    A plan is complete only when every active confirmed handling problem is either
    addressed by an approved change or covered by an explicit targeted test. A plan
    that treats only the dominant while leaving confirmed secondaries untreated is
    a ``partial_recommendation`` — never "approved (complete)".

    Returns ``{state, complete, is_partial, treated, untreated,
    treated_by_test_only, note}``. It NEVER authors values and NEVER makes an
    unsafe/blocked plan apply-eligible — it only distinguishes complete from
    incomplete within the approved family.
    """
    approved = {f for f in (approved_fields or ())}
    tested = {f for f in (tested_fields or ())}
    problems = _active_confirmed_problems(diagnosis)

    treated: list[str] = []
    untreated: list[str] = []
    treated_by_test_only: list[str] = []
    for p in problems:
        addr = _problem_addressing_fields(p)
        if addr & approved:
            treated.append(p)
        elif addr & tested:
            treated.append(p)
            treated_by_test_only.append(p)
        else:
            untreated.append(p)

    # Non-approved base statuses keep their meaning; completeness is not asserted.
    _APPROVED_FAMILY = {"approved", "approved_with_warnings", "approved_with_rejections",
                        "partial_recommendation", "fallback_generated"}
    if base_status not in _APPROVED_FAMILY:
        if base_status in ("blocked_no_safe_recommendation", "validation_failed", "retry_failed"):
            state = RECO_BLOCKED_UNSAFE
        else:
            state = RECO_INSUFFICIENT_EVIDENCE
        return {"state": state, "complete": False, "is_partial": False,
                "treated": treated, "untreated": untreated,
                "treated_by_test_only": treated_by_test_only,
                "note": ""}

    if has_conflicting_evidence and not approved:
        return {"state": RECO_CONFLICTING_EVIDENCE, "complete": False, "is_partial": True,
                "treated": treated, "untreated": untreated,
                "treated_by_test_only": treated_by_test_only,
                "note": "Evidence conflicts on at least one field — settle it with a "
                        "controlled test before applying."}

    if untreated:
        _readable = ", ".join(_FEEDBACK_LABELS.get(p, p) for p in untreated)
        note = (f"Partial: this plan does not yet treat {len(untreated)} confirmed "
                f"problem(s) — {_readable}. Run the targeted tests before treating the "
                "setup as race-ready.")
        return {"state": RECO_PARTIAL, "complete": False, "is_partial": True,
                "treated": treated, "untreated": untreated,
                "treated_by_test_only": treated_by_test_only, "note": note}

    # Everything treated. If the ONLY treatment for every problem was a test (no
    # applied change), this is a "go and test" plan, not a finished setup.
    if problems and not approved:
        return {"state": RECO_TARGETED_TEST, "complete": False, "is_partial": True,
                "treated": treated, "untreated": untreated,
                "treated_by_test_only": treated_by_test_only,
                "note": "Every confirmed problem needs a controlled test before a value "
                        "can be applied — this is a test plan, not a finished setup."}

    return {"state": RECO_APPROVED_COMPLETE, "complete": True, "is_partial": False,
            "treated": treated, "untreated": untreated,
            "treated_by_test_only": treated_by_test_only,
            "note": ""}


def build_feedback_dispositions(diagnosis: dict, proposed_fields) -> "list[dict]":
    """Return one disposition per reported driver-feedback item (Phase 4).

    Each entry: {feedback, state, detail}. state ∈ {addressed, deferred,
    strategy, preserved}. Nothing the driver reported disappears silently.
    """
    flags = (diagnosis or {}).get("driver_feel_flags", {}) or {}
    proposed = set(proposed_fields or ())
    ws_band = (diagnosis or {}).get("wheelspin_band", "low")
    out: "list[dict]" = []
    for flag, label in _FEEDBACK_LABELS.items():
        if not flags.get(flag):
            continue
        if flag == "entry_balance_good":
            out.append({"feedback": label, "state": "preserved",
                        "detail": "Turn-in is fine — intentionally left unchanged."})
            continue
        if flag == "fuel_use_high":
            out.append({"feedback": label, "state": "strategy",
                        "detail": "Fuel economy is a driving/strategy matter; review in the Strategy tab."})
            continue
        addr = _FEEDBACK_ADDRESSING_FIELDS.get(flag, frozenset())
        if addr & proposed:
            applied = sorted(addr & proposed)
            out.append({"feedback": label, "state": "addressed",
                        "detail": f"Change(s) applied: {', '.join(applied)}."})
        else:
            if flag == "braking_instability":
                detail = ("Brake bias cannot move rearward during instability (safety "
                          "invariant); confirm straight-line vs trail-braking lock first.")
            elif flag == "rear_loose_on_exit" and ws_band != "low":
                detail = ("LSD accel not increased (would worsen power oversteer); "
                          "confirm inside-wheel spin vs whole-axle oversteer.")
            elif flag == "lsd_feel_wrong":
                detail = ("LSD evaluated across Initial / Acceleration / Braking against your "
                          "proven same-car values — run a controlled Initial-Torque A/B to "
                          "confirm the apex-connection preference before committing.")
            elif flag == "rear_loose_under_braking":
                detail = ("Braking-phase rear instability routes to LSD braking sensitivity / "
                          "brake bias (not throttle-side LSD) — confirm trail-braking vs "
                          "straight-line lock.")
            elif flag == "gearing_too_long":
                detail = ("Sixth not fully used means the gearing is too LONG — any "
                          "lengthening (final-drive-down) change is rejected; record terminal "
                          "sixth-gear RPM and limiter activation on the main straight.")
            else:
                detail = "No safe rule-based change from the current evidence — run a targeted test."
            out.append({"feedback": label, "state": "deferred", "detail": detail})
    return out


# Distinctive readable-string prefixes → machine dominant key. Ordered most-
# specific first so overlapping heads (e.g. two "rear …" issues) resolve
# unambiguously. Kept in lock-step with ``_derive_dominant_problem``'s _readable.
_DOMINANT_READABLE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("front aero / platform limited", "front_aero_platform_limited"),
    ("mid-corner understeer",         "mid_corner_understeer"),
    ("rear traction / aero",          "rear_traction_aero"),
    ("rear instability under braking", "rear_loose_under_braking"),
    ("snap oversteer on exit",        "snap_oversteer_exit"),
    ("differential connection",       "lsd_connection"),
    ("braking instability",           "braking_instability"),
    ("bottoming",                     "bottoming"),
    ("wheelspin",                     "wheelspin"),
)


def _dominant_problem_key(dominant_readable: str) -> str:
    """Recover the machine-readable dominant-problem key from its readable string.

    Uses distinctive, ordered readable prefixes (not the fragile first-word head,
    which collided for the two "rear …" issues). Returns "" when no structural
    issue dominates.
    """
    s = (dominant_readable or "").strip().lower()
    if not s or s.startswith("no dominant") or s.startswith("minor bottoming"):
        return ""
    for prefix, key in _DOMINANT_READABLE_PREFIXES:
        if s.startswith(prefix):
            return key
    return ""


def _bottoming_band_readable(band: str) -> str:
    # AC10 wording: "required" band now says "may need attention" rather than
    # asserting ride-height is automatically required — the engineer decides.
    return {
        "minor": "no action needed",
        "moderate": "monitor; address other issues first",
        "consider": "ride height / spring rate change may be worth considering",
        "required": "bottoming needs attention — ride height or spring rate change may be appropriate",
    }.get(band, band)


def _derive_tuning_priority(
    driver_feel_flags: dict[str, bool],
    bottoming_band: str,
    wheelspin_band: str,
    aero_front_near_min: bool,
    aero_rear_near_min: bool,
    location_evidence_usable: bool = True,
    compliance_priority: bool = False,
    aero_rear_healthy: bool = False,
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
    # Skip when aero_rear_healthy: rear downforce is already near-max, fall back to LSD/mechanical
    if not aero_rear_healthy:
        if wheelspin_band in ("major", "severe") or (
            driver_feel_flags.get("rear_loose_on_exit") and aero_rear_near_min
        ):
            if "aero (rear — increase rear downforce for traction and stability)" not in priority:
                priority.append("aero (rear — increase rear downforce for traction and stability)")

    # When rear aero is healthy but wheelspin is still major/severe, fall back to LSD/mechanical
    if aero_rear_healthy and wheelspin_band in ("major", "severe"):
        priority.append("LSD accel / traction (wheelspin — rear aero healthy, use mechanical grip)")

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
    num_gears: int = 0,
    location_trustworthy: bool = True,
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
      7. no valid speed target / no limiter data / frames empty → insufficient_data

    Group 63 fixes (the "Final Drive 4.25 -> 4.20 for an unused sixth" defect):
      * ``top_gear`` is the car's ACTUAL top gear (``num_gears`` or the highest gear
        SEEN in frames), NOT ``max(rev_limiter_by_gear)`` — otherwise a too-long,
        never-limited sixth is invisible and a limiter tap in an intermediate gear
        is misread as a top-gear hit → false ``gear_too_short``.
      * a missing/zero top-speed target (``transmission_max_speed_kmh`` = 0) yields
        ``insufficient_data`` (UNKNOWN), never a ``gear_too_short`` default — an
        uncaptured value is not evidence.
      * ``gear_too_short`` is a straight-specific claim; when the track location is
        not trustworthy it is downgraded to ``insufficient_data`` (we cannot confirm
        the limiter contact happened on a straight rather than a slow-corner exit).

    "severe-ish" wheelspin: "major" or "severe" (from _wheelspin_band).
    """
    _SEVERE_ISH = ("major", "severe")

    # Resolve the car's ACTUAL top gear — prefer the declared gear count, else the
    # highest gear actually driven; only fall back to limiter-hit keys when nothing
    # else is known. (Using limiter-hit keys alone is the root-cause defect.)
    rlbg = rev_limiter_by_gear or {}
    top_gear = int(num_gears) if isinstance(num_gears, (int, float)) and num_gears > 0 else 0
    if top_gear <= 0 and frames:
        for f in frames:
            g = getattr(f, "gear", 0)
            if g > top_gear:
                top_gear = g
    if top_gear <= 0 and rlbg:
        top_gear = max(int(g) for g in rlbg)

    top_gear_limiter_hits = float(rlbg.get(top_gear, 0)) if top_gear > 0 else 0.0

    # Speed ratio — guard divide-by-zero. A missing/zero target is UNKNOWN, not a
    # licence to guess.
    if top_speed_target_kmh <= 0:
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
            # gear_too_short asserts "limiter on a straight" — only trust it when the
            # track location is trustworthy; otherwise the limiter contact may be a
            # slow-corner-exit tap, not a straight-line top-speed limit.
            return "gear_too_short" if location_trustworthy else "insufficient_data"
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

    # No valid speed target (e.g. transmission_max_speed_kmh = 0) — an uncaptured
    # target is NOT evidence. Return UNKNOWN rather than defaulting to gear_too_short.
    return "insufficient_data"


def _classify_wheelspin_subtype(
    frames: list,
    rev_limiter_by_gear: "dict | None",
    wheelspin_band: str,
    avg_snap: float,
    aero_rear_near_min: bool,
    laps: list,
    location_trustworthy: bool = False,
    driver_says_gearing_too_long: bool = False,
) -> str:
    """Classify the wheelspin mechanism from available telemetry signals.

    Returns one of: both_rear_spin | snap_throttle_induced | kerb_unload_spin |
    gear_too_short_spin | aero_instability | mixed | unknown |
    conflicting_evidence | insufficient_data.

    NOTE: inside_wheel_spin is NEVER emitted — per-wheel slip data is not
    available in GT7 telemetry at this level; the signal would require individual
    wheel-slip deltas which are not in TelemetryFrame.

    NOTE: rear_platform_stiffness requires a spring/damper baseline comparison
    that the app does not currently track.  We emit "mixed" as a safe placeholder
    and leave this as a future extension when spring data is captured.
    # future extension: rear_platform_stiffness needs spring/damper baseline delta

    Group 64 — ``gear_too_short_spin`` is a STRONG, load-bearing claim (it defers
    all LSD-Acceleration reasoning downstream). A single intermediate-gear limiter
    tap must NOT be enough to commit to it. It is only returned when the limiter
    evidence is location-trustworthy (``location_trustworthy=True``) AND the driver
    does not contradict it. A limiter-in-lower-gear signal that cannot be proven to
    come from the straight resolves to ``unknown`` (→ controlled test), never a
    speculative gearing certainty; a driver "sixth not used / too long" report over
    the same telemetry resolves to ``conflicting_evidence``.
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

    # gear_too_short_spin: limiter hits in gears strictly below top gear + severe-ish
    # wheelspin — but only committed to on TRUSTWORTHY, non-contradicted evidence
    # (Group 64). Otherwise the weak signal is remembered and either resolves to a
    # controlled test ("unknown") or a driver contradiction ("conflicting_evidence").
    _weak_gear_signal = False
    if wheelspin_band in _SEVERE_ISH and top_gear > 0:
        lower_gear_hits = sum(
            int(cnt) for g, cnt in rlbg.items() if int(g) < top_gear
        )
        if lower_gear_hits > 0:
            if driver_says_gearing_too_long:
                # Telemetry hints short, driver reports the top gear is unused / too
                # long — a genuine contradiction. Never author a gearing certainty.
                return "conflicting_evidence"
            if location_trustworthy:
                return "gear_too_short_spin"
            # Limiter hit in a lower gear but we cannot prove it happened on the
            # straight (location evidence not usable). Defer the gearing claim and
            # try the other detectors; if none commit, this becomes "unknown".
            _weak_gear_signal = True

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

    # A severe-ish spin whose ONLY structured signal was an unprovable lower-gear
    # limiter hit resolves to "unknown" — a controlled test, not a gearing guess.
    if _weak_gear_signal:
        return "unknown"

    # mixed: meaningful+ wheelspin but signals don't point to one cause
    if wheelspin_band in ("meaningful",) + _SEVERE_ISH:
        return "mixed"

    return "insufficient_data"


def _classify_bottoming_confidence(
    laps: list,
    avg_bottoming: float,
    b_band: str,
    driver_feel_flags: dict,
    all_frames: list,
    setup_history_entries: list,
) -> dict:
    """Classify bottoming confidence level and subtype.

    Returns {"band": str, "subtype": str, "confidence": str}.
    confidence ∈ low | medium | high
    subtype ∈ floor_contact | suspension_compression | kerb_strike |
              throttle_squat | insufficient_data

    Deferred subtypes (no distinguishing telemetry signal exists):
      undulation — track-undulation response is indistinguishable from
                   floor_contact without track-surface metadata.
      noise      — packet-noise artefacts cannot be separated from genuine
                   bottoming events without a reference-silence window.
    Consistent with the project's honest-deferral pattern for
    inside_wheel_spin and rear_platform_stiffness.
    """
    _BAND_ORDER = {"minor": 0, "moderate": 1, "consider": 2, "required": 3}

    def _band_gte(band: str, threshold: str) -> bool:
        return _BAND_ORDER.get(band, 0) >= _BAND_ORDER.get(threshold, 0)

    try:
        # Immediate return for minor band
        if b_band == "minor":
            return {"band": b_band, "subtype": "insufficient_data", "confidence": "low"}

        # Count corroborating signals (HIGH requires >= 2)
        signals = 0

        # Signal 1: repeated events across >= 4 laps
        if len(laps) >= 4:
            signals += 1

        # Signal 2: accel_fade_detected in WOT frames
        try:
            if all_frames:
                # Determine top gear from frames
                top_gear = 0
                for f in all_frames:
                    g = getattr(f, "gear", 0)
                    if g > top_gear:
                        top_gear = g
                if top_gear > 0:
                    _tgfs = _derive_top_gear_frame_signals(all_frames, top_gear)
                    if _tgfs.get("accel_fade_detected"):
                        signals += 1
        except Exception:
            pass

        # Signal 3: driver reports bottoming
        if driver_feel_flags.get("bottoming"):
            signals += 1

        # Signal 4: prior ride-height OR damper change in history AND current b_band >= "moderate"
        if _band_gte(b_band, "moderate") and setup_history_entries:
            try:
                for entry in setup_history_entries:
                    for ch in (entry.get("changes") or []):
                        field = ch.get("field", "")
                        if field in ("ride_height_front", "ride_height_rear",
                                     "dampers_front_comp", "dampers_front_ext",
                                     "dampers_rear_comp", "dampers_rear_ext"):
                            signals += 1
                            break
                    else:
                        continue
                    break
            except Exception:
                pass

        # Map signals to confidence
        if signals == 0:
            confidence = "low"
        elif signals == 1:
            confidence = "medium"
        else:
            confidence = "high"

        # Subtype — meaningful at medium+; low with band in {minor,moderate} => insufficient_data
        if confidence == "low" and b_band in ("minor", "moderate"):
            subtype = "insufficient_data"
        else:
            # Compute avg_kerb across laps
            avg_kerb = (
                sum(getattr(l, "kerb_count", 0) for l in laps) / len(laps)
                if laps else 0.0
            )
            # Determine wheelspin band from laps
            avg_ws = (
                sum(getattr(l, "wheelspin_count", 0) for l in laps) / len(laps)
                if laps else 0.0
            )
            ws_band = _wheelspin_band(avg_ws)

            # kerb_strike: avg_kerb >= 1.0/lap AND bottoming present
            if avg_kerb >= 1.0 and avg_bottoming > 0:
                subtype = "kerb_strike"
            # throttle_squat: wheelspin meaningful/major/severe AND bottoming present
            elif ws_band in ("meaningful", "major", "severe") and avg_bottoming > 0:
                subtype = "throttle_squat"
            # suspension_compression: compliance_priority True AND bottoming present
            elif driver_feel_flags.get("_compliance_priority") and avg_bottoming > 0:
                subtype = "suspension_compression"
            # floor_contact: b_band >= "consider" AND no dominant kerb-proximity signal
            elif _band_gte(b_band, "consider") and avg_kerb < 1.0:
                subtype = "floor_contact"
            else:
                subtype = "insufficient_data"

        return {"band": b_band, "subtype": subtype, "confidence": confidence}

    except Exception:
        return {"band": b_band, "subtype": "insufficient_data", "confidence": "low"}


def _rh_permitted_increment(bottoming_confidence: dict, loc_usable: bool) -> int:
    """Return the permitted ride-height increase increment (mm) given confidence.

    confidence low  => 0
    confidence medium => 2
    confidence high & subtype floor_contact & loc_usable => 6
    confidence high & subtype floor_contact & not loc_usable => 4
    confidence high & other subtype => 4
    """
    confidence = bottoming_confidence.get("confidence", "low") if bottoming_confidence else "low"
    subtype = bottoming_confidence.get("subtype", "insufficient_data") if bottoming_confidence else "insufficient_data"

    if confidence == "low":
        return 0
    if confidence == "medium":
        return 2
    # confidence == "high"
    if subtype == "floor_contact":
        return 6 if loc_usable else 4
    return 4


def _derive_driver_feel_traction_status(feeling_history: list) -> str:
    """Derive traction status from a chronological list of feeling strings (latest LAST).

    Returns "good" | "degraded" | "unknown".

    Positive-traction vocab check on LATEST entry -> "good".
    Rear-loose vocab check on LATEST entry -> "degraded".
    Otherwise "unknown".
    """
    _POSITIVE_TRACTION_VOCAB = [
        "traction feels good", "good traction", "traction good",
        "traction is fine", "traction improved",
    ]
    _REAR_LOOSE_VOCAB = _FEEL_VOCABULARY.get("rear_loose_on_exit", [])

    if not feeling_history:
        return "unknown"

    latest = feeling_history[-1]
    if not latest:
        return "unknown"

    latest_lower = latest.lower()

    # Check positive traction vocab first (latest supersedes rear-loose complaints)
    for term in _POSITIVE_TRACTION_VOCAB:
        if term in latest_lower:
            return "good"

    # Check rear-loose vocab
    for term in _REAR_LOOSE_VOCAB:
        if term in latest_lower:
            return "degraded"

    return "unknown"


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

def _build_deterministic_fallback(
    diagnosis: dict,
    setup: "dict | None" = None,
    ranges: "dict | None" = None,
) -> dict:
    """Build a deterministic fallback response from a diagnosis dict.

    Returns a dict satisfying the required AI response schema.
    When setup + ranges are provided, attempts to generate 1–3 REAL conservative
    changes by walking recommended_tuning_priority and proposing the smallest
    safe increment for the top non-blocked field.

    Each candidate is run through validate_setup_engineering_structured;
    only candidates with ZERO blocking failures are kept.

    When NO candidate passes (or setup/ranges are not provided) the response has
    changes=[] and fallback_used=True.  The finaliser maps this to
    blocked_no_safe_recommendation with the standard analysis message.

    Re-validating the returned output always passes because either:
    - changes=[] and setup_fields={} have no field violations, or
    - each included change was pre-validated above.
    """
    bottoming_confidence = diagnosis.get("bottoming_confidence") or {"band": "minor", "subtype": "insufficient_data", "confidence": "low"}
    wheelspin_subtype = diagnosis.get("wheelspin_subtype", "insufficient_data")
    dominant_problem = diagnosis.get("dominant_problem", "unknown")
    tuning_priority = diagnosis.get("recommended_tuning_priority") or []
    traction_status = diagnosis.get("driver_feel_traction_status", "unknown")

    b_conf = bottoming_confidence.get("confidence", "low")
    b_subtype = bottoming_confidence.get("subtype", "insufficient_data")
    b_band = bottoming_confidence.get("band", "minor")
    loc_evidence_usable = diagnosis.get("location_evidence_usable", False)

    # Build plain-English analysis from diagnosis
    analysis_parts = [
        "Engineering validation failed after retry — returning a safe conservative response.",
        f"Dominant problem: {dominant_problem}.",
    ]
    if b_band != "minor":
        analysis_parts.append(
            f"Bottoming: {b_band} band (confidence: {b_conf}, subtype: {b_subtype})."
        )
    if wheelspin_subtype != "insufficient_data":
        analysis_parts.append(f"Wheelspin subtype: {wheelspin_subtype}.")
    if traction_status == "good":
        analysis_parts.append("Driver reports good traction.")
    elif traction_status == "degraded":
        analysis_parts.append("Driver reports degraded traction.")
    if tuning_priority:
        analysis_parts.append(
            f"Recommended priority: {tuning_priority[0] if tuning_priority else 'unknown'}."
        )

    approved_changes: list[dict] = []
    approved_sf: dict = {}

    # ------------------------------------------------------------------
    # Attempt to generate real conservative changes from diagnosis
    # ------------------------------------------------------------------
    if setup is not None and ranges is not None:
        # Walk tuning priority; try the top non-blocked field
        _tried: set[str] = set()

        for _priority_entry in tuning_priority[:5]:
            # Map priority label to candidate field + conservative delta
            _priority_lower = _priority_entry.lower()
            _candidates: list[tuple[str, float]] = []

            if "ride height" in _priority_lower or "springs" in _priority_lower:
                # Ride-height — only if increment is permitted
                _perm = _rh_permitted_increment(bottoming_confidence, loc_evidence_usable)
                if _perm > 0:
                    for _rh_f in ("ride_height_rear", "ride_height_front"):
                        if _rh_f not in _tried:
                            _candidates.append((_rh_f, float(_perm)))

            elif "lsd" in _priority_lower or "traction" in _priority_lower:
                # LSD accel — only if subtype allows (not snap_throttle with delta > 4)
                if wheelspin_subtype != "snap_throttle_induced" and "lsd_accel" not in _tried:
                    _lsd_delta = 2.0  # conservative
                    _candidates.append(("lsd_accel", _lsd_delta))

            elif "aero" in _priority_lower:
                # Aero rear — increase by 1 step if wheelspin present
                if "aero_rear" not in _tried:
                    _candidates.append(("aero_rear", 1.0))

            for _field, _delta in _candidates:
                if _field in _tried:
                    continue
                _tried.add(_field)
                _cur_raw = setup.get(_field)
                if _cur_raw is None:
                    continue
                try:
                    _cur_val = float(_cur_raw)
                except (TypeError, ValueError):
                    continue
                _new_val = _cur_val + _delta
                # Clamp to range
                if _field in ranges:
                    _lo, _hi = ranges[_field]
                    _new_val = max(float(_lo), min(float(_hi), _new_val))
                    # Preserve int type
                    if isinstance(_lo, int) and isinstance(_hi, int):
                        _new_val = int(_new_val)
                # Skip no-op
                if _new_val == _cur_val:
                    continue
                # Build a minimal AI-response-shaped dict for validation
                _test_sf = {_field: _new_val}
                _test_ch = [{
                    "setting": _field.replace("_", " ").title(),
                    "field": _field,
                    "from": str(_cur_val),
                    "to": str(_new_val),
                    "to_clamped": _new_val,
                    "why": f"Fallback conservative change: +{_delta} for {_priority_entry[:40]}",
                }]
                _test_resp = {
                    "analysis": "fallback",
                    "primary_issue": dominant_problem,
                    "changes": _test_ch,
                    "setup_fields": _test_sf,
                    "validation_targets": {},
                    "confidence": {"overall": "low", "reason": "fallback"},
                }
                try:
                    _failures = validate_setup_engineering_structured(
                        _test_resp, diagnosis, setup, ranges, {},
                    )
                    _blocking = [f for f in _failures if f.severity == "blocking"]
                    if not _blocking:
                        _ch_out = dict(_test_ch[0])
                        _ch_out["why"] = (
                            f"{_ch_out['why']} — safer than rejected AI output: "
                            f"uses minimum permitted increment, validated against all rules."
                        )
                        approved_changes.append(_ch_out)
                        approved_sf[_field] = _new_val
                        if len(approved_changes) >= 3:
                            break
                except Exception:
                    pass  # Validation error → skip this candidate

            if len(approved_changes) >= 3:
                break

    if approved_changes:
        analysis_parts.append(
            f"Conservative fallback: {len(approved_changes)} safe change(s) generated from diagnosis."
        )
    else:
        analysis_parts.append(
            "Not enough session data to generate a safe recommendation — run more laps."
        )

    return {
        "analysis": " ".join(analysis_parts),
        "primary_issue": dominant_problem,
        "changes": approved_changes,
        "setup_fields": approved_sf,
        "validation_targets": [],
        "confidence": "low",
        "engineering_validation_failed": True,
        "fallback_used": True,
    }


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
        # Group 45: alias of rev_limiter_by_gear (conservative = None)
        "per_gear_limiter_evidence":  None,
        "avg_top_speed_kmh":          0.0,
        "top_speed_target_kmh":       0.0,
        "gearbox_flag":               "preserve",
        "aero_front_value":           None,
        "aero_front_near_min":        False,
        "aero_rear_value":            0.0,
        "aero_rear_near_min":         False,
        "driver_feel_flags":          {},
        "wheelspin_by_gear":          None,
        "bog_by_gear":                None,  # Group 46: conservative = None
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
        "gearing_state":              "unknown",
        "gearing_raw_category":       "insufficient_data",
        "gearing_location_confident": False,
        "wheelspin_subtype":          "insufficient_data",
        "compliance_priority":        False,
        # Group 40: new keys — conservative defaults
        "bottoming_confidence":       {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
        "bottoming_impact":           {"impact": "ADVISORY", "performance_relevant": False,
                                       "reason": "no session data"},
        # Group 64: canonical bottoming state (conservative = advisory / no action)
        "bottoming_display_state":    {"state": "advisory", "label": "advisory — no session data",
                                       "severity": 2, "impact": "ADVISORY", "band": "minor",
                                       "performance_relevant": False, "reason": "no session data"},
        "driver_feel_traction_status": "unknown",
        "aero_rear_healthy":          False,
        # Phase 3 coherence gate inputs — conservative defaults
        "dominant_problem_key":       "",
        "dominant_required":          False,
        "dominant_evidence_sufficient": True,
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

        # Group 46: per-gear wheelspin detection.
        # Mirrors the wheelspin detection in telemetry/recorder.py (_compute_stats)
        # but buckets events by the gear active at each wheelspin frame.
        # Signal: throttle > 0.7 AND rear wheel speed > car speed * 1.3 AND speed > 2 m/s.
        # We count total wheelspin frame events per gear across ALL laps.
        # Returns None when no frame data is available (honest — no fabrication).
        _ws_gear_totals: dict[int, int] = {}
        _any_frames_for_ws = False
        for lap in laps:
            lap_frames = getattr(lap, "frames", [])
            if not lap_frames:
                continue
            _any_frames_for_ws = True
            for f in lap_frames:
                _gear_f = getattr(f, "gear", 0)
                if _gear_f <= 0:
                    continue
                _throttle = getattr(f, "throttle", 0.0)
                if _throttle <= 0.7:
                    continue
                _speed_kmh = getattr(f, "speed_kmh", 0.0)
                _speed_ms = _speed_kmh / 3.6
                if _speed_ms < 2.0:
                    continue
                # Compute rear wheel speed using wheel_rps and tyre_radius
                # (mirrors _wheel_speed_ms logic from recorder.py)
                _wheel_rps = getattr(f, "wheel_rps", None)
                _tyre_radius = getattr(f, "tyre_radius", None)
                if _wheel_rps is None or _tyre_radius is None:
                    continue
                try:
                    import math as _math
                    # Use rear wheels only (indices 2 and 3: RL, RR)
                    _rl_ms = abs(_wheel_rps[2]) * _tyre_radius[2] * 2.0 * _math.pi
                    _rr_ms = abs(_wheel_rps[3]) * _tyre_radius[3] * 2.0 * _math.pi
                    _rear_wheel_ms = (_rl_ms + _rr_ms) / 2.0
                    if _rear_wheel_ms > _speed_ms * 1.3:
                        _ws_gear_totals[_gear_f] = _ws_gear_totals.get(_gear_f, 0) + 1
                except (TypeError, ValueError, IndexError, ZeroDivisionError):
                    continue
        # Normalise to PER-LAP average — mirrors exactly how rev_limiter_by_gear is
        # averaged (~line 1253: {g: cnt / len(laps) for g, cnt in _gear_totals.items()}).
        # Guard len(laps) > 0 is already guaranteed by the outer `if laps:` branch, but
        # we keep the explicit guard for clarity and defensive safety.
        wheelspin_by_gear: dict | None = (
            {g: cnt / len(laps) for g, cnt in _ws_gear_totals.items()}
            if _any_frames_for_ws and len(laps) > 0
            else None
        )

        # Group 46: bog_by_gear detection.
        # A genuine bog signal requires: low-rpm + high-throttle + low longitudinal
        # acceleration in a gear. GT7 telemetry does NOT expose longitudinal acceleration
        # directly (no accel_x/accel_z field on TelemetryFrame). We could estimate it from
        # velocity deltas between frames, but the 10 Hz sample rate (one frame per ~100 ms)
        # makes velocity-delta acceleration estimates noisy and unreliable. A proxy using
        # speed_drop with high throttle is possible but would conflate cornering deceleration
        # with true bog. To avoid fabricating signals, bog_by_gear is left as None.
        # Deferred: genuine bog detection requires either a higher sample rate, direct accel
        # signal from the packet, or a more sophisticated multi-frame filter. When a real
        # signal becomes available, populate this dict {gear: event_count} analogously to
        # wheelspin_by_gear above.
        bog_by_gear: "dict | None" = None  # deliberately absent — signal not derivable

    else:
        avg_bottoming         = 0.0
        avg_wheelspin         = 0.0
        avg_snap              = 0.0
        avg_lockups           = 0.0
        avg_rev_limiter_total = 0.0
        rev_limiter_by_gear   = None
        avg_top_speed_kmh     = 0.0
        wheelspin_by_gear     = None
        bog_by_gear           = None

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

    # Near-min check using per-car ranges. Phase 2 integrity: the range is now
    # resolved by tolerant (normalised) car-name matching in resolve_ranges, so a
    # name variant no longer falls back to the generic (0,1000) placeholder that
    # mis-scaled position. The hard invariant that a value at/above the range MAX
    # can never be near-min lives in _aero_near_min itself.
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

    # Number of gears the car actually has — used so a too-long, never-limited top
    # gear is not invisible to the gearing classifier (Group 63). Prefer an explicit
    # num_gears, else the count of populated indexed-gear fields in the setup.
    _num_gears = 0
    try:
        _ng_raw = setup.get("num_gears")
        if isinstance(_ng_raw, (int, float)) and _ng_raw > 0:
            _num_gears = int(_ng_raw)
        else:
            _num_gears = sum(
                1 for _gi in range(1, 9)
                if isinstance(setup.get(f"gear_{_gi}"), (int, float)) and setup.get(f"gear_{_gi}")
            )
    except Exception:
        _num_gears = 0

    # Gearing diagnosis category (replaces the flat 93%-threshold logic)
    _raw_gearing_category = _classify_gearing(
        all_frames,
        rev_limiter_by_gear,
        avg_top_speed_kmh,
        top_speed_target_kmh,
        w_band,
        num_gears=_num_gears,
        location_trustworthy=loc_evidence_usable,
    )
    # Fold the telemetry category + the driver's own report into the canonical
    # five-state gearing model, then map back to the category the rules consume so
    # a driver "sixth not fully used" report can VETO a lengthening recommendation.
    from strategy.gearbox_evidence import (
        derive_gearing_state, GEARING_CONFLICTING, GEARING_TOO_LONG,
    )
    gearing_state = derive_gearing_state(
        _raw_gearing_category,
        driver_says_too_long=bool(driver_feel_flags.get("gearing_too_long")),
        driver_says_gearbox_good=bool(driver_feel_flags.get("gearbox_good")),
    )
    if gearing_state == GEARING_CONFLICTING:
        # Telemetry says short but the driver reports an unused top gear — a
        # conflicting result must lead to a targeted test, never an applyable change.
        gearing_diagnosis_category = "conflicting_evidence"
    elif gearing_state == GEARING_TOO_LONG and _raw_gearing_category == "gear_too_long":
        gearing_diagnosis_category = "gear_too_long"
    else:
        gearing_diagnosis_category = _raw_gearing_category

    # Wheelspin subtype — Group 64: pass location trustworthiness and the driver's
    # own gearing report so a speculative gear_too_short_spin cannot be committed to
    # on weak, unlocated evidence (it would otherwise block all LSD-accel reasoning).
    wheelspin_subtype = _classify_wheelspin_subtype(
        all_frames,
        rev_limiter_by_gear,
        w_band,
        avg_snap,
        aero_rear_near_min,
        laps,
        location_trustworthy=loc_evidence_usable,
        driver_says_gearing_too_long=bool(driver_feel_flags.get("gearing_too_long")),
    )

    # Compliance priority
    compliance_priority = _detect_compliance_priority(feeling, avg_kerb)

    # Gearbox flag: derived from the gearing_diagnosis_category rather than
    # the old flat 93%/limiter heuristic, so the AI block and the validation
    # rule are consistent.
    # "preserve" categories: insufficient_data, gear_too_long, limiter_limited,
    #   conflicting_evidence
    #   (limiter_limited = hitting the limiter at the right speed — gearbox correct;
    #    conflicting_evidence = telemetry vs driver disagree → targeted test, no change)
    # "may_change" categories: gear_too_short, top_gear_power_band_limited,
    #   traction_limited_acceleration, drag_or_power_limited
    _PRESERVE_CATEGORIES = {"insufficient_data", "gear_too_long", "limiter_limited",
                            "conflicting_evidence"}
    gearbox_flag = (
        "preserve"
        if gearing_diagnosis_category in _PRESERVE_CATEGORIES
        else "may_change"
    )

    # Driver override: if driver says gearbox is good, always force preserve
    if driver_feel_flags.get("gearbox_good"):
        gearbox_flag = "preserve"

    # ------------------------------------------------------------------
    # Group 40: new diagnosis keys
    # ------------------------------------------------------------------

    # Pass compliance_priority flag into bottoming confidence classifier via feel flags
    _feel_flags_for_bottoming = dict(driver_feel_flags)
    _feel_flags_for_bottoming["_compliance_priority"] = compliance_priority

    # Build feeling_history for driver_feel_traction_status
    _feeling_history: list[str] = []
    try:
        import data.setup_history as _setup_history_mod
        _config_id_inner = event_ctx.get("config_id") or ""
        if _config_id_inner:
            _hist_entries = _setup_history_mod.load_history(_config_id_inner)
            for _entry in _hist_entries:
                _feel_val = _entry.get("feeling")
                if _feel_val:
                    _feeling_history.append(str(_feel_val))
    except Exception:
        _hist_entries = []

    if feeling is not None:
        _feeling_history.append(feeling)

    # Setup history entries for bottoming confidence signal 4
    _setup_hist_entries: list = []
    try:
        _config_id_inner2 = event_ctx.get("config_id") or ""
        if _config_id_inner2:
            import data.setup_history as _sh2
            _setup_hist_entries = _sh2.load_history(_config_id_inner2)
    except Exception:
        pass

    # Classify bottoming confidence
    bottoming_confidence = _classify_bottoming_confidence(
        laps=laps,
        avg_bottoming=avg_bottoming,
        b_band=b_band,
        driver_feel_flags=_feel_flags_for_bottoming,
        all_frames=all_frames,
        setup_history_entries=_setup_hist_entries,
    )

    # Derive driver feel traction status
    driver_feel_traction_status = _derive_driver_feel_traction_status(_feeling_history)

    # Compute aero_rear_healthy (amendment: fraction-of-max threshold)
    # Use resolve_ranges for per-car aero_rear range; only True when aero_rear has valid range
    _ar_lo_h, _ar_hi_h = ranges.get("aero_rear", (0, 1000))
    _ar_lo_h = float(_ar_lo_h)
    _ar_hi_h = float(_ar_hi_h)
    # Guard: only fire when we actually have a useful aero range (hi > lo and hi != 1000 default)
    # If range is the GENERIC_DEFAULT (0, 1000), the car may have no aero — don't fire false positives
    _aero_range_is_generic = (_ar_lo_h == 0 and _ar_hi_h == 1000)
    if (
        _aero_r_raw is not None
        and _ar_hi_h > 0
        and not _aero_range_is_generic
        and aero_rear_value >= 0.80 * _ar_hi_h
    ):
        aero_rear_healthy = True
    else:
        aero_rear_healthy = False

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
    # Group 63: grade bottoming by demonstrated CONSEQUENCE, not by event count.
    # A "required" (>2.0/lap) rate is EVIDENCE-insufficient — demoted so confirmed
    # handling feedback dominates — unless it is performance-relevant (driver report
    # or measured accel-fade). This replaces the Phase-3 gate whose `confidence=="low"`
    # precondition was disarmed by the `len(laps)>=4 ⇒ medium` rule, so any multi-lap
    # session let count-only bottoming become dominant.
    _bconf = (bottoming_confidence or {}).get("confidence", "low")
    _bsub = (bottoming_confidence or {}).get("subtype", "insufficient_data")
    _accel_fade = False
    try:
        _tg_for_fade = _num_gears if _num_gears > 0 else 0
        if _tg_for_fade <= 0 and all_frames:
            for _f in all_frames:
                _g = getattr(_f, "gear", 0)
                if _g > _tg_for_fade:
                    _tg_for_fade = _g
        if _tg_for_fade > 0 and all_frames:
            _accel_fade = bool(_derive_top_gear_frame_signals(
                all_frames, _tg_for_fade).get("accel_fade_detected"))
    except Exception:
        _accel_fade = False
    bottoming_impact = _classify_bottoming_impact(
        b_band, _bsub, _bconf,
        driver_mentions_bottoming=bool(driver_feel_flags.get("bottoming")),
        accel_fade_detected=_accel_fade,
        location_trustworthy=loc_evidence_usable,
    )
    # Group 64: reconcile the raw count band and the consequence impact into ONE
    # canonical state so no surface can render "required" + "normal" simultaneously.
    bottoming_display = _bottoming_display_state(b_band, bottoming_impact)
    _bottoming_evidence_insufficient = (
        b_band == "required" and not bottoming_impact["performance_relevant"]
    )
    dominant_problem, secondary_problems = _derive_dominant_problem(
        driver_feel_flags, b_band, w_band, aero_front_near_min, aero_rear_near_min,
        aero_rear_healthy=aero_rear_healthy,
        bottoming_evidence_insufficient=_bottoming_evidence_insufficient,
    )
    # Machine-readable dominant key + severity/evidence flags so the recommendation
    # funnel can guarantee the dominant *required* problem is either addressed or
    # explicitly deferred (never silently approved untreated).
    dominant_problem_key = _dominant_problem_key(dominant_problem)
    # Group 63: the coherence gate previously armed ONLY for "required" bottoming, so
    # a lone weakly-supported change (e.g. final_drive) was returned as plain
    # "approved" while a confirmed dominant HANDLING complaint went untreated. Arm it
    # for confirmed driver-feedback dominants too — the plan must address the dominant
    # problem or explicitly defer it (partial_recommendation / targeted test).
    _CONFIRMED_FEEDBACK_DOMINANTS = {
        "mid_corner_understeer", "lsd_connection", "rear_loose_under_braking",
        "front_aero_platform_limited", "snap_oversteer_exit", "braking_instability",
    }
    # Group 64 — wheelspin (a telemetry dominant) previously never armed the gate,
    # so a lone bare change could be "approved" while severe wheelspin went untreated.
    # Arm it only when the wheelspin is genuinely major/severe (its dominance
    # threshold), so a low/meaningful band never forces a partial.
    _wheelspin_confirmed = (dominant_problem_key == "wheelspin"
                            and w_band in ("major", "severe"))
    dominant_required = (
        (dominant_problem_key == "bottoming" and b_band == "required")
        or (dominant_problem_key in _CONFIRMED_FEEDBACK_DOMINANTS)
        or _wheelspin_confirmed
    )
    dominant_evidence_sufficient = not (
        dominant_problem_key == "bottoming" and _bottoming_evidence_insufficient
    )
    recommended_tuning_priority = _derive_tuning_priority(
        driver_feel_flags, b_band, w_band, aero_front_near_min, aero_rear_near_min,
        location_evidence_usable=loc_evidence_usable,
        compliance_priority=compliance_priority,
        aero_rear_healthy=aero_rear_healthy,
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
        # Group 45: per_gear_limiter_evidence — alias of rev_limiter_by_gear.
        # Used by the gearbox per-gear rule gating: only propose a gear_N change
        # when per_gear_limiter_evidence.get(N, 0) > 0 for that specific gear.
        # No separate computation needed — the value IS rev_limiter_by_gear.
        # Note: limiter-before-braking evidence maps to the gear_too_short category
        # (gearing_diagnosis_category) and surfaces here as per-gear hit counts.
        "per_gear_limiter_evidence":  rev_limiter_by_gear,
        # Speed
        "avg_top_speed_kmh":          avg_top_speed_kmh,
        "top_speed_target_kmh":       top_speed_target_kmh,
        # Gearbox
        "gearbox_flag":               gearbox_flag,
        # Phase 3 coherence gate inputs
        "dominant_problem_key":       dominant_problem_key,
        "dominant_required":          dominant_required,
        "dominant_evidence_sufficient": dominant_evidence_sufficient,
        # Aero
        "aero_front_value":           aero_front_value,
        "aero_front_near_min":        aero_front_near_min,
        "aero_rear_value":            aero_rear_value,
        "aero_rear_near_min":         aero_rear_near_min,
        # Driver feel
        "driver_feel_flags":          driver_feel_flags,
        # Group 46: per-gear telemetry signals (real detection — see above comments)
        "wheelspin_by_gear":          wheelspin_by_gear,
        "bog_by_gear":                bog_by_gear,  # None — signal not derivable (deferred)
        "lockups_by_gear":            None,  # lockups_by_gear: no per-gear bucketing yet (deferred)
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
        # Group 63: canonical five-state gearing model + whether the straight-
        # specific claim is location-trustworthy + the raw telemetry category.
        "gearing_state":              gearing_state,
        "gearing_raw_category":       _raw_gearing_category,
        "gearing_location_confident": loc_evidence_usable,
        "wheelspin_subtype":          wheelspin_subtype,
        "compliance_priority":        compliance_priority,
        # Group 40: bottoming confidence, traction status, rear aero health
        "bottoming_confidence":       bottoming_confidence,
        # Group 63: bottoming graded by demonstrated consequence, not event count.
        "bottoming_impact":           bottoming_impact,
        # Group 64: the ONE canonical bottoming state every surface renders — derived
        # from the consequence impact, never the raw count band. No panel may show
        # "required" unless this state's impact is performance-relevant.
        "bottoming_display_state":    bottoming_display,
        "driver_feel_traction_status": driver_feel_traction_status,
        "aero_rear_healthy":          aero_rear_healthy,
    }


# ---------------------------------------------------------------------------
# Engineering validation — severity map for structured validator
# ---------------------------------------------------------------------------

# Maps stable code prefixes to their severity.
# Unlisted prefixes default to "blocking" (conservative).
_VALIDATION_SEVERITY_MAP: dict[str, str] = {
    # Blocking rules
    "rh_for_minor_bottoming":          "blocking",
    "rh_low_confidence_location":      "blocking",
    "rh_increment_exceeds_confidence": "blocking",
    "rh_rake_risk":                    "blocking",
    "aero_cut_with_wheelspin":         "blocking",
    "aero_at_min_floaty":              "blocking",
    "gearbox_category_mismatch":       "blocking",
    "lsd_large_change_gated":          "blocking",
    "lsd_blocked_driver_feel":         "blocking",
    "lsd_reversal_without_evidence":   "blocking",
    "malformed_schema":                "blocking",
    "invalid_units":                   "blocking",
    "locked-field":                    "blocking",
    # out-of-range is a WARNING, not blocking: the clamping mechanism (to_clamped) already
    # forces the applied value back into range.  The clamp guarantee: _normalise_changes
    # always sets to_clamped before validation, so approved_changes only ever carry the
    # clamped in-range value.  If clamping did not occur the value is unchanged/out-of-range,
    # but the applied path reads to_clamped, not to — so the user is never exposed to the
    # raw out-of-range value.
    "out-of-range":                    "warning",
    "snap_throttle_lsd_accel_gate":    "blocking",
    "kerb_strike_rh_over_increment":   "blocking",
    "gearbox_fake_field":              "blocking",
    "gearbox_ratio_inversion":         "blocking",
    # Warning-only rules
    "gearbox_out_of_range":            "warning",
    # Generic/cosmetic errors from _validate_setup_response
    "too many changes":                "warning",
}

# Prefixes of _validate_setup_response cosmetic errors that are warnings.
# "outside valid range": the _validate_setup_response range check fires when to_clamped is
#   out of range.  Per the I1 spec, out-of-range is a WARNING (not blocking) because the
#   clamping mechanism in _normalise_changes guarantees the applied value is safe — the UI
#   reads to_clamped and that value is already within range or was clamped to range max/min.
_WARNING_SUBSTRINGS: tuple[str, ...] = (
    "too many changes",
    "is a no-op",
    "outside valid range",
)


def _severity_for_reason(reason: str) -> str:
    """Derive severity for a legacy reason string using the severity map.

    Checks code prefix first (up to first ':'), then scans warning substrings.
    Default is "blocking" (conservative).
    """
    code = reason.split(":")[0].strip() if ":" in reason else reason.strip()
    if code in _VALIDATION_SEVERITY_MAP:
        return _VALIDATION_SEVERITY_MAP[code]
    # Substring scan for warning patterns
    lower = reason.lower()
    for ws in _WARNING_SUBSTRINGS:
        if ws in lower:
            return "warning"
    return "blocking"


def validate_setup_engineering_structured(
    parsed_ai_response: dict,
    diagnosis: dict,
    setup: dict,
    ranges: dict,
    event_ctx: dict,
    car_name: str = "",
    rec_history: "dict | None" = None,
) -> "list[ValidationFailure]":
    """Return a list of ValidationFailure namedtuples, each with code, message, severity.

    Inputs are IDENTICAL to validate_setup_engineering.  This is the primary
    implementation; validate_setup_engineering delegates here and re-serialises
    to the legacy prefixed-string format for backward compatibility.

    The legacy string format ``validate_setup_engineering`` returns is byte-identical
    to today's output so all 5000+ existing tests and ENG_SAFETY_PREFIXES substring
    matching continue to pass.
    """
    raw_reasons = validate_setup_engineering(
        parsed_ai_response, diagnosis, setup, ranges, event_ctx,
        car_name=car_name, rec_history=rec_history,
    )
    results: list[ValidationFailure] = []
    for reason in raw_reasons:
        code = reason.split(":")[0].strip() if ":" in reason else reason.strip()
        severity = _severity_for_reason(reason)
        results.append(ValidationFailure(code=code, message=reason, severity=severity))
    return results


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
    _PRESERVE_GEARBOX_CATEGORIES = {"insufficient_data", "gear_too_long", "limiter_limited",
                                    "conflicting_evidence"}
    _gearbox_blocked = (
        gearing_diagnosis_category in _PRESERVE_GEARBOX_CATEGORIES
        or feel_flags.get("gearbox_good")
        # A driver "sixth not fully used" report means the gearing is too LONG —
        # never author a lengthening (final-drive-down) change against it.
        or feel_flags.get("gearing_too_long")
    )
    # Canonical gearbox fields that must never be changed when gearbox is in a preserve category.
    # Includes legacy display-only field, old gear_ratios blob, and AC6 individual gear fields.
    _CANONICAL_GEARBOX_FIELDS = frozenset({
        "transmission_max_speed_kmh",
        "gear_ratios",
        "final_drive",
        "gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6",
    })
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
            field = ch.get("field", "")
            if field == "gear_ratios" or "gear_ratio" in str(field).lower():
                reasons.append(
                    f"gearbox_category_mismatch: AI recommends gear ratio change but "
                    f"gearing_diagnosis_category is '{gearing_diagnosis_category}' "
                    "(gearbox should be preserved)."
                )
                break
        # Also check the AC6 canonical fields: final_drive and individual gear slots.
        # These are additive checks — legacy detection above is preserved byte-identical.
        for ch in ai_changes:
            field = ch.get("field", "")
            if field in ("final_drive", "gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6"):
                ai_v = ch.get("to_clamped") if ch.get("to_clamped") is not None else ch.get("to")
                cur_v = _current_value(field)
                if ai_v is not None and (cur_v is None or ai_v != cur_v):
                    reasons.append(
                        f"gearbox_category_mismatch: AI changes {field} "
                        f"but gearing_diagnosis_category is "
                        f"'{gearing_diagnosis_category}' (gearbox should be preserved)."
                    )
                    break

    # ----------------------------------------------------------------
    # RULE: rh_increment_exceeds_confidence
    # ----------------------------------------------------------------
    # Ride-height increase must not exceed permitted increment for bottoming confidence.
    # Composes with rh_for_minor_bottoming (both may fire).
    _bottoming_confidence = diagnosis.get("bottoming_confidence") or {"confidence": "low", "subtype": "insufficient_data"}
    for rh_key in ("ride_height_front", "ride_height_rear"):
        ai_rh_inc = _ai_value(rh_key)
        cur_rh_inc = _current_value(rh_key)
        if ai_rh_inc is not None and cur_rh_inc is not None:
            delta_rh = ai_rh_inc - cur_rh_inc
            if delta_rh > 0:
                permitted = _rh_permitted_increment(_bottoming_confidence, loc_evidence_usable)
                if delta_rh > permitted:
                    reasons.append(
                        f"rh_increment_exceeds_confidence: AI increases {rh_key} by {delta_rh:.0f}mm "
                        f"(from {cur_rh_inc} to {ai_rh_inc}) but bottoming_confidence is "
                        f"'{_bottoming_confidence.get('confidence', 'low')}' (subtype: "
                        f"{_bottoming_confidence.get('subtype', 'insufficient_data')}) — "
                        f"permitted increment is {permitted}mm. "
                        f"Use a smaller increment or wait for more laps to confirm bottoming pattern."
                    )

    # ----------------------------------------------------------------
    # RULE: rh_rake_risk
    # ----------------------------------------------------------------
    # Rear ride-height increase >= 4mm with no front change => rake risk
    _ai_rhf_rake = _ai_value("ride_height_front")
    _cur_rhf_rake = _current_value("ride_height_front")
    _ai_rhr_rake = _ai_value("ride_height_rear")
    _cur_rhr_rake = _current_value("ride_height_rear")
    if _ai_rhr_rake is not None and _cur_rhr_rake is not None:
        _rear_delta_rake = _ai_rhr_rake - _cur_rhr_rake
        _front_changed_rake = (_ai_rhf_rake is not None and _ai_rhf_rake != _cur_rhf_rake)
        if _rear_delta_rake >= 4 and not _front_changed_rake:
            reasons.append(
                f"rh_rake_risk: AI increases ride_height_rear by {_rear_delta_rake:.0f}mm "
                f"(from {_cur_rhr_rake} to {_ai_rhr_rake}) with no ride_height_front change — "
                f"rake risk (high). Use smaller increment or pair with front change."
            )

    # ----------------------------------------------------------------
    # RULE: lsd_large_change_gated
    # ----------------------------------------------------------------
    # Large LSD accel increases gated by wheelspin subtype
    _ws_subtype_v = diagnosis.get("wheelspin_subtype", "insufficient_data")
    _ai_lsd_v = _ai_value("lsd_accel")
    _cur_lsd_v = _current_value("lsd_accel")
    if _ai_lsd_v is not None and _cur_lsd_v is not None and _ai_lsd_v > _cur_lsd_v:
        _lsd_delta_v = _ai_lsd_v - _cur_lsd_v
        _fire_lsd_gate = False
        if _ws_subtype_v in ("snap_throttle_induced", "mixed") and _lsd_delta_v >= 5:
            _fire_lsd_gate = True
        elif _ws_subtype_v == "both_rear_spin" and _lsd_delta_v > 4:
            _fire_lsd_gate = True
        elif _ws_subtype_v == "inside_wheel_spin" and _lsd_delta_v > 4:
            _fire_lsd_gate = True
        if _fire_lsd_gate:
            reasons.append(
                f"lsd_large_change_gated: AI increases lsd_accel by {_lsd_delta_v:.0f} "
                f"(from {_cur_lsd_v} to {_ai_lsd_v}) — wheelspin_subtype is '{_ws_subtype_v}' "
                f"which requires conservative increments. Large LSD changes can cause oscillation; "
                f"limit to <=4 for this subtype or use smaller incremental steps."
            )

    # ----------------------------------------------------------------
    # RULE: lsd_blocked_driver_feel
    # ----------------------------------------------------------------
    # When driver reports good traction, don't increase LSD accel on snap throttle
    _traction_status_v = diagnosis.get("driver_feel_traction_status", "unknown")
    if (
        _ws_subtype_v == "snap_throttle_induced"
        and _traction_status_v == "good"
        and _ai_lsd_v is not None and _cur_lsd_v is not None
        and _ai_lsd_v > _cur_lsd_v
    ):
        reasons.append(
            f"lsd_blocked_driver_feel: AI increases lsd_accel "
            f"(from {_cur_lsd_v} to {_ai_lsd_v}) but driver_feel_traction_status is 'good' — "
            f"latest driver report indicates good traction. "
            f"An LSD accel increase is not warranted when the driver confirms traction is fine."
        )

    # ----------------------------------------------------------------
    # RULE: lsd_reversal_without_evidence
    # ----------------------------------------------------------------
    # If rec_history provides prior lsd_accel direction, and the AI now
    # reverses that direction without a worsened verdict justifying it,
    # flag the reversal.
    # HARDENED: only fire when abs(ai_lsd - cur_lsd) >= 5 (meaningful change).
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
                _lsd_reversal_delta = abs(_ai_lsd - _cur_lsd)
                _new_direction = "increase" if _ai_lsd > _cur_lsd else "decrease"
                if _new_direction != _prior_direction and _lsd_reversal_delta >= 5:
                    reasons.append(
                        f"lsd_reversal_without_evidence: AI reverses lsd_accel direction "
                        f"(prior_value={_prior_value}, prior_direction='{_prior_direction}', "
                        f"current={_cur_lsd}, new={_ai_lsd}, new_direction='{_new_direction}', "
                        f"delta={_lsd_reversal_delta:.0f}). "
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
    # NEW RULE: snap_throttle_lsd_accel_gate (BLOCKING)
    # ----------------------------------------------------------------
    # wheelspin_subtype == snap_throttle_induced AND lsd_accel increase > 4
    _ws_subtype_snap = diagnosis.get("wheelspin_subtype", "insufficient_data")
    if _ws_subtype_snap == "snap_throttle_induced":
        _ai_lsd_snap = _ai_value("lsd_accel")
        _cur_lsd_snap = _current_value("lsd_accel")
        if _ai_lsd_snap is not None and _cur_lsd_snap is not None:
            _snap_delta = _ai_lsd_snap - _cur_lsd_snap
            if _snap_delta > 4:
                reasons.append(
                    f"snap_throttle_lsd_accel_gate: AI increases lsd_accel by {_snap_delta:.0f} "
                    f"(from {_cur_lsd_snap} to {_ai_lsd_snap}) but wheelspin_subtype is "
                    f"'snap_throttle_induced' — maximum permitted increase is 4. "
                    f"Large LSD accel changes for snap-throttle wheelspin can cause rear oscillation; "
                    f"use small steps (<=4) and re-assess after each session."
                )

    # ----------------------------------------------------------------
    # NEW RULE: kerb_strike_rh_over_increment (BLOCKING)
    # ----------------------------------------------------------------
    # bottoming subtype == kerb_strike AND rear ride-height increase > 3mm
    _btm_conf_new = diagnosis.get("bottoming_confidence") or {}
    if _btm_conf_new.get("subtype") == "kerb_strike":
        _ai_rhr_ks = _ai_value("ride_height_rear")
        _cur_rhr_ks = _current_value("ride_height_rear")
        if _ai_rhr_ks is not None and _cur_rhr_ks is not None:
            _ks_delta = _ai_rhr_ks - _cur_rhr_ks
            if _ks_delta > 3:
                reasons.append(
                    f"kerb_strike_rh_over_increment: AI increases ride_height_rear by "
                    f"{_ks_delta:.0f}mm (from {_cur_rhr_ks} to {_ai_rhr_ks}) but bottoming "
                    f"subtype is 'kerb_strike' — maximum permitted rear ride-height increase "
                    f"for kerb-strike bottoming is 3mm. Address kerb compliance via damping "
                    f"or spring rate before raising ride height further."
                )

    # ----------------------------------------------------------------
    # NEW RULE: gearbox_fake_field (BLOCKING)
    # ----------------------------------------------------------------
    # transmission_max_speed_kmh present as an actionable field in setup_fields/changes
    _ai_sf_new = parsed_ai_response.get("setup_fields") or {}
    _ai_ch_new = parsed_ai_response.get("changes") or []
    if "transmission_max_speed_kmh" in _ai_sf_new:
        reasons.append(
            "gearbox_fake_field: transmission_max_speed_kmh appears in setup_fields — "
            "this field is DISPLAY-ONLY (it shows the current calculated top speed) and "
            "must never be included in actionable setup changes. Remove it from setup_fields."
        )
    for _ch_gf in _ai_ch_new:
        if _ch_gf.get("field") == "transmission_max_speed_kmh":
            reasons.append(
                "gearbox_fake_field: transmission_max_speed_kmh appears in changes — "
                "this field is DISPLAY-ONLY and must never be a change target. "
                "Use final_drive or gear_1..gear_6 for real gearbox changes."
            )
            break

    # ----------------------------------------------------------------
    # NEW RULE: gearbox_out_of_range (WARNING)
    # ----------------------------------------------------------------
    # final_drive outside 2.5–6.0 or any gear outside 0.5–4.0
    # Severity is WARNING (not blocking) — bounds are conservative constants,
    # must not false-block real setups near the edges of their actual range.
    _GEAR_FIELDS = ("gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6")
    _fd_ai = _ai_value("final_drive")
    if _fd_ai is not None:
        if not (_FINAL_DRIVE_RANGE[0] <= _fd_ai <= _FINAL_DRIVE_RANGE[1]):
            reasons.append(
                f"gearbox_out_of_range: AI sets final_drive to {_fd_ai} which is outside "
                f"the expected range {_FINAL_DRIVE_RANGE[0]}–{_FINAL_DRIVE_RANGE[1]}. "
                f"Verify this is a valid GT7 final drive ratio. (WARNING — not blocking)"
            )
    for _gf in _GEAR_FIELDS:
        _gv_ai = _ai_value(_gf)
        if _gv_ai is not None:
            if not (_GEAR_RATIO_RANGE[0] <= _gv_ai <= _GEAR_RATIO_RANGE[1]):
                reasons.append(
                    f"gearbox_out_of_range: AI sets {_gf} to {_gv_ai} which is outside "
                    f"the expected range {_GEAR_RATIO_RANGE[0]}–{_GEAR_RATIO_RANGE[1]}. "
                    f"Verify this is a valid GT7 gear ratio. (WARNING — not blocking)"
                )

    # ----------------------------------------------------------------
    # NEW RULE: gearbox_ratio_inversion (BLOCKING)
    # ----------------------------------------------------------------
    # Group 45: changed from >= to > (strict inversion only).
    # Equal adjacent gear ratios are ALLOWED (non-standard but not physically
    # invalid for GT7's sequential model).  This aligns the validator with the
    # engine's monotonic check in setup_rule_engine._process_rule which also
    # uses strict > since Group 45.
    # A higher gear must have a STRICTLY LOWER ratio; equal is now permitted.
    _gear_values: dict[int, float] = {}
    for _n, _gfk in enumerate(("gear_1", "gear_2", "gear_3", "gear_4", "gear_5", "gear_6"), start=1):
        _gv = _ai_value(_gfk)
        if _gv is not None:
            _gear_values[_n] = _gv
    _sorted_gear_nums = sorted(_gear_values.keys())
    for _i in range(1, len(_sorted_gear_nums)):
        _prev_n = _sorted_gear_nums[_i - 1]
        _curr_n = _sorted_gear_nums[_i]
        _prev_v = _gear_values[_prev_n]
        _curr_v = _gear_values[_curr_n]
        if _curr_v > _prev_v:
            reasons.append(
                f"gearbox_ratio_inversion: gear_{_curr_n} ratio {_curr_v} is NOT lower than "
                f"gear_{_prev_n} ratio {_prev_v} — gear ratios must strictly decrease from "
                f"1st to top gear (each higher gear must have a lower ratio). "
                f"Fix the ratio sequence before applying."
            )
            break  # one inversion message is sufficient

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
        _ts_line = (
            f"Top speed: {ts:.0f} km/h"
            + (f" vs target {ts_target:.0f} km/h" if ts_target > 0 else "")
        )
        # AC12 wording: transmission_max_speed_kmh is display-only — add caveat
        # so the AI never uses this number as a reason to add/remove a gearing change.
        # Gearing changes are permitted when justified by power-band / driver evidence;
        # the top-speed gap alone does NOT block gearing changes (removed that leakage).
        if ts_target > 0:
            _ts_line += (
                " [Note: transmission_max_speed_kmh is DISPLAY-ONLY — "
                "do NOT include it in setup_fields or changes; "
                "gearing changes may still be recommended on power-band or driver evidence]"
            )
        lines.append(_ts_line)
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
        # AC12 wording: snap_throttle_induced must NOT assert inside-wheel-spin;
        # frame it as mixed (driver input + setup) with no inside-wheel-spin claim.
        # kerb_strike is described distinctly from floor_contact.
        _ws_note = ""
        if ws_subtype == "snap_throttle_induced":
            _ws_note = (
                " [mixed cause: snap throttle application pattern suggests driver-input component"
                " alongside possible setup instability — do NOT claim inside rear spins specifically"
                " as no per-wheel telemetry is available]"
            )
        elif ws_subtype == "kerb_strike":
            _ws_note = (
                " [kerb-strike wheelspin: unloading over kerbs — distinct from floor-contact"
                " bottoming; address kerb compliance / damping rather than ride height alone]"
            )
        lines.append(f"Wheelspin subtype: {ws_subtype}{_ws_note}")

    # Group 40: bottoming confidence, driver feel traction status, aero rear health
    _btm_conf = diagnosis.get("bottoming_confidence")
    if _btm_conf and isinstance(_btm_conf, dict):
        _bc_conf = _btm_conf.get("confidence", "")
        _bc_sub = _btm_conf.get("subtype", "")
        if _bc_conf:
            lines.append(f"Bottoming confidence: {_bc_conf} (subtype: {_bc_sub})")

    _traction_status = diagnosis.get("driver_feel_traction_status", "")
    if _traction_status == "good":
        lines.append(
            "Driver traction status: GOOD — latest driver report confirms good traction. "
            "Do NOT state the driver currently reports rear looseness or wheelspin complaints. "
            "Telemetry wheelspin count is reported separately as an objective metric."
        )
    elif _traction_status == "degraded":
        lines.append(
            "Driver traction status: DEGRADED — latest driver report indicates rear looseness or traction issues."
        )

    _aero_rear_healthy = diagnosis.get("aero_rear_healthy", False)
    if _aero_rear_healthy:
        lines.append(
            "Rear aero status: HEALTHY (near top of valid range) — "
            "do NOT describe rear downforce as low; "
            "do NOT list rear aero as primary priority."
        )

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
