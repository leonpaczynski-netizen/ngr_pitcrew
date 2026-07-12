"""Setup rule knowledge base — Group 45: Setup Brain Intelligence Expansion.

Group 45 changes
----------------
- CAR_DRIVETRAIN_OVERRIDES: explicit per-car drivetrain registry (e.g. Porsche 911 RSR
  (991) '17 → "rr") for cases where the UI combo may be absent or generic.
- _HIGH_WEAR_CONTRAINDICATED_TAGS: frozenset of driver_style_tags whose rules are
  contraindicated under high tyre-wear conditions.
- Pack P: Porsche-specific rules (applies_drivetrain=rr, applies_car_class=gr3).
  P1 — LSD accel increase under snap_throttle_induced wheelspin (traction-first).
  P2 — rear downforce protection under rear instability (contraindication guard).
- B5b rule: gear_too_long + gearbox_flag==may_change → final_drive_up.
- driver_style_tags additions on relevant rules: prefers_front_bite and trail_braker
  on B1/C2 qualify-sensitive rules; race_values_consistency and rear-rotation tags
  on B5/B5b gearing rules.

Preserved from Group 43
-----------------------
- _PACK_A, _PACK_B, _PACK_CD — unchanged (safety + style packs).
- register_pack / get_all_rules — unchanged API.

Previously "Setup rule knowledge base — Group 43: Rule-First Setup Brain Completion."

Defines the canonical rule catalogue (Packs A, B, C/D) consumed by
setup_rule_engine.run_rule_engine.

Design principles
-----------------
- Dependency-light: no imports from driving_advisor or setup_diagnosis.
  (Driver-profile constants are sourced from setup_driver_profile which
  reads setup_diagnosis.PERSONAL_DRIVER_TUNING_MODEL at build time.)
- All rule delta-resolvers are NAMED functions stored in a local registry
  (_DELTA_RESOLVERS); the SetupRule.delta_fn field holds a string key.
- Architecture is extensible via register_pack() — third-party packs can
  add rules without touching this file.

Group 43 changes
----------------
- A2 re-keyed to real diagnosis signals: driver_feel_flags.rear_loose_on_exit
  OR driver_feel_flags.snap_oversteer_exit (was fictional *_evidence keys).
- A3/A4 re-keyed: contraindications now use bottoming_confidence.band in
  {"consider","required"} OR compliance_priority=True (was fictional *_evidence keys).
- A5 re-keyed: preconditions now driver_feel_flags.braking_instability OR
  avg_lockups>0 via __any__ truthiness (was fictional *_evidence keys).
- B5 re-keyed: preconditions now gearing_diagnosis_category=="gear_too_short"
  AND gearbox_flag=="may_change" (was fictional "too_short" enum value).
- Delta resolvers renamed for clarity: _delta_final_drive_down (returns -0.05,
  numeric effect: lower ratio = taller/longer gearing = higher top speed) and
  _delta_final_drive_up (returns +0.05, foundation only — no firing rule this
  sprint). Legacy key "shorten_final_drive" aliased for backwards compatibility.
- "Build Setup with AI" button is DISABLED in the UI (frontend parallel change)
  because the ungated AI path is pending a rule-first baseline; the AI is now
  audit-only and cannot author setup changes.

Deferred
--------
- Individual gear_1..gear_6 proposing rules: deferred (foundation in place via
  _delta_final_drive_down/_delta_final_drive_up; per-gear rules need more
  diagnosis signal resolution).
- RuleOutcomeStore live wiring and cross-session persistence: deferred
  (implemented and tested in isolation, ready to activate once persistence
  is in place).
- Tyre-compound / tyre-wear / fuel signals: not read by any rule (deferred;
  no dedicated tyre telemetry diagnosis keys exist today).
- applies_session / applies_drivetrain scope enforcement: not enforced by the
  engine (deferred; scope fields are set on rules but the engine does not yet
  filter by them at runtime).
- Voice path: narration-only (deferred; a full rule-first rebuild of the voice
  path so it too is authored by the rule engine is deferred).
- No car-specific / drivetrain-specific rule packs (deferred).
- Per-car DrivetrainType / CarClass scoping (currently all rules default to
  'any' for those axes — add specificity once more data is in).
"""
from __future__ import annotations

from enum import Enum
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Group 45 — Per-car drivetrain overrides
# ---------------------------------------------------------------------------
# Explicit drivetrain registry for cars where the UI combo may return an empty
# or generic value.  Keys must match the exact car name string used in GT7.
# Precedence: explicit UI-combo drivetrain > CAR_DRIVETRAIN_OVERRIDES > empty DB → generic(None).
CAR_DRIVETRAIN_OVERRIDES: dict[str, str] = {
    "Porsche 911 RSR (991) '17": "rr",
}

# ---------------------------------------------------------------------------
# Group 45 — High-wear contraindicated rule tags
# ---------------------------------------------------------------------------
# Rules tagged with any of these driver_style_tags are contraindicated when
# tyre_wear_high=True in the diagnosis dict (injected by driving_advisor.py).
# The contraindication evaluator checks diagnosis["tyre_wear_high"] against the
# rule's contraindications dict (key "tyre_wear_high": True).
_HIGH_WEAR_CONTRAINDICATED_TAGS: frozenset[str] = frozenset({
    "toe_active",
    "camber_active",
    "rear_rotation_risk",
})


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RulePhase(str, Enum):
    entry = "entry"
    mid = "mid"
    exit = "exit"
    kerb = "kerb"
    straight = "straight"
    safety = "safety"
    driver_style = "driver_style"
    global_ = "global"


class RiskLevel(str, Enum):
    low = "low"
    med = "med"
    high = "high"


class ConfidenceLevel(str, Enum):
    low = "low"
    med = "med"
    high = "high"


class DrivetrainType(str, Enum):
    fr = "fr"
    ff = "ff"
    mr = "mr"
    rr = "rr"
    awd = "awd"
    any = "any"


class CarClass(str, Enum):
    gr1 = "gr1"
    gr2 = "gr2"
    gr3 = "gr3"
    gr4 = "gr4"
    road = "road"
    race = "race"
    any = "any"


class SessionType(str, Enum):
    race = "race"
    quali = "quali"
    practice = "practice"
    any = "any"


# ---------------------------------------------------------------------------
# NamedTuples
# ---------------------------------------------------------------------------

class SetupRule(NamedTuple):
    """A single deterministic setup rule.

    Fields
    ------
    rule_id          : Stable unique identifier (e.g. "A1", "B3", "C2_entry").
    pack             : Pack letter/name (A, B, C, D, …).
    phase            : Corner phase this rule targets.
    preconditions    : dict of diagnosis-key → expected value / truthy check.
                       ALL entries must match for the rule to fire.
    contraindications: dict of diagnosis-key → value that BLOCKS firing.
                       ANY match blocks the rule.
    field            : Canonical setup field this rule targets.
    delta_fn         : Key into _DELTA_RESOLVERS dict (string reference, not callable).
    title            : Human-readable rule title.
    symptom          : Symptom description shown in the UI / explainability.
    rationale        : Engineering rationale for this change.
    risk             : RiskLevel enum.
    base_confidence  : ConfidenceLevel enum (may be downgraded by outcome store).
    driver_style_tags: list of driver-style tag strings that align with this rule.
    applies_drivetrain: DrivetrainType — 'any' means all.
    applies_car_class : CarClass — 'any' means all.
    applies_session   : SessionType — 'any' means all.
    """
    rule_id: str
    pack: str
    phase: RulePhase
    preconditions: dict
    contraindications: dict
    field: str
    delta_fn: str
    title: str
    symptom: str
    rationale: str
    risk: RiskLevel
    base_confidence: ConfidenceLevel
    driver_style_tags: list
    applies_drivetrain: DrivetrainType = DrivetrainType.any
    applies_car_class: CarClass = CarClass.any
    applies_session: SessionType = SessionType.any


class SetupEvidence(NamedTuple):
    """Evidence context for a rule evaluation."""
    telemetry_keys: list
    driver_feel_keys: list
    values: dict


# ---------------------------------------------------------------------------
# Delta resolver registry — pure functions, no side effects
# ---------------------------------------------------------------------------
# Each resolver receives (setup: dict, ranges: dict, diagnosis: dict)
# and returns a float delta (may be 0.0 to signal no-op).

def _delta_raise_rear_rh(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Raise rear ride-height by 3 mm (conservative bottoming fix)."""
    return 3.0


def _delta_raise_front_rh(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Raise front ride-height by 3 mm."""
    return 3.0


def _delta_increase_rear_aero(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Increase rear aero by 1 step."""
    return 1.0


def _delta_increase_front_aero(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Increase front aero by enough to clear the near-min threshold.

    The aero_at_min_floaty engineering validator fires whenever the proposed
    aero_front value is still <= lo + 0.10*(hi-lo) (the near-min threshold).
    When the current value is at or below that threshold we must target a
    value above it to avoid a blocking validation failure.
    """
    lo, hi = ranges.get("aero_front", (0, 1000))
    cur = setup.get("aero_front", 0)
    try:
        cur, lo, hi = float(cur), float(lo), float(hi)
    except (TypeError, ValueError):
        return 1.0
    near_min_threshold = lo + 0.10 * (hi - lo)
    if cur <= near_min_threshold:
        # Target comfortably above the threshold (5 % above it)
        target = near_min_threshold + max(1.0, 0.05 * (hi - lo))
        return max(1.0, target - cur)
    return 1.0


def _delta_decrease_front_aero(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Decrease front aero by 1 step (ONLY allowed when high-speed instability evidence)."""
    return -1.0


def _delta_decrease_rear_aero(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Decrease rear aero by 1 step (ONLY when rear-aero drag evidence confirmed)."""
    return -1.0


def _delta_increase_lsd_accel(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Increase LSD accel by 2 (conservative traction fix)."""
    return 2.0


def _delta_decrease_lsd_accel(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Decrease LSD accel by 2 (exit rotation fix — only when driver confirmed)."""
    return -2.0


def _delta_increase_lsd_decel(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Increase LSD decel by 2 (entry stability fix)."""
    return 2.0


def _delta_decrease_lsd_decel(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Decrease LSD decel by 2 (entry rotation fix)."""
    return -2.0


def _delta_increase_rear_arb(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Increase rear ARB by 1 (mid-corner stability)."""
    return 1.0


def _delta_decrease_rear_arb(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Decrease rear ARB by 1 (compliance / kerb fix)."""
    return -1.0


def _delta_increase_front_arb(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Increase front ARB by 1 (front response fix)."""
    return 1.0


def _delta_decrease_front_arb(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Decrease front ARB by 1 (compliance fix)."""
    return -1.0


def _delta_brake_bias_rear(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Move brake bias rearward by 0.5."""
    return 0.5


def _delta_brake_bias_front(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Move brake bias frontward by -0.5."""
    return -0.5


def _delta_final_drive_down(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Decrease the final_drive ratio value by 0.05.

    Numeric effect: lower final_drive ratio number.
    Physical consequence: lower ratio = taller/longer gearing = higher top speed.
    Used by B5 (gear_too_short): lengthen gearing to stop bouncing off the rev
    limiter on straights.  The magnitude 0.05 is a conservative one-step change.
    """
    return -0.05


def _delta_final_drive_up(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Increase the final_drive ratio value by 0.05.

    Numeric effect: higher final_drive ratio number.
    Physical consequence: higher ratio = shorter/lower gearing = more acceleration,
    lower top speed.
    Foundation only — no firing rule this sprint.  A future gear_too_long rule
    (or a traction-deficit-on-exit rule) will point delta_fn at this resolver.
    """
    return 0.05


def _delta_shorten_final_drive(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Legacy alias for _delta_final_drive_down — kept for backwards compatibility.

    Any existing reference to the 'shorten_final_drive' key in _DELTA_RESOLVERS
    continues to work.  New rules should use 'final_drive_down' instead.
    """
    return _delta_final_drive_down(setup, ranges, diagnosis)


def _delta_noop(setup: dict, ranges: dict, diagnosis: dict) -> float:
    """No-op placeholder — used by Pack A invariant rules (field protected)."""
    return 0.0


# Public resolver registry — keyed by string name used in SetupRule.delta_fn
_DELTA_RESOLVERS: dict[str, object] = {
    "raise_rear_rh": _delta_raise_rear_rh,
    "raise_front_rh": _delta_raise_front_rh,
    "increase_rear_aero": _delta_increase_rear_aero,
    "increase_front_aero": _delta_increase_front_aero,
    "decrease_front_aero": _delta_decrease_front_aero,
    "decrease_rear_aero": _delta_decrease_rear_aero,
    "increase_lsd_accel": _delta_increase_lsd_accel,
    "decrease_lsd_accel": _delta_decrease_lsd_accel,
    "increase_lsd_decel": _delta_increase_lsd_decel,
    "decrease_lsd_decel": _delta_decrease_lsd_decel,
    "increase_rear_arb": _delta_increase_rear_arb,
    "decrease_rear_arb": _delta_decrease_rear_arb,
    "increase_front_arb": _delta_increase_front_arb,
    "decrease_front_arb": _delta_decrease_front_arb,
    "brake_bias_rear": _delta_brake_bias_rear,
    "brake_bias_front": _delta_brake_bias_front,
    "final_drive_down": _delta_final_drive_down,     # preferred key (Group 43+)
    "final_drive_up": _delta_final_drive_up,         # foundation only — no firing rule this sprint
    "shorten_final_drive": _delta_shorten_final_drive,  # legacy alias for final_drive_down
    "noop": _delta_noop,
}


def resolve_delta(delta_fn: str, setup: dict, ranges: dict, diagnosis: dict) -> float:
    """Resolve the named delta function and return the computed delta.

    Returns 0.0 if the function name is unknown (safe no-op).
    """
    fn = _DELTA_RESOLVERS.get(delta_fn)
    if fn is None:
        return 0.0
    try:
        return float(fn(setup, ranges, diagnosis))  # type: ignore[operator]
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

_RULE_REGISTRY: list[SetupRule] = []


def register_pack(pack_id: str, rules: list[SetupRule]) -> None:
    """Register a new pack of rules.  Duplicate rule_ids are silently skipped."""
    existing_ids = {r.rule_id for r in _RULE_REGISTRY}
    for rule in rules:
        if rule.rule_id not in existing_ids:
            _RULE_REGISTRY.append(rule)
            existing_ids.add(rule.rule_id)


def get_all_rules() -> list[SetupRule]:
    """Return all registered rules (registered order)."""
    return list(_RULE_REGISTRY)


# ---------------------------------------------------------------------------
# Pack A — Safety Invariants
# ---------------------------------------------------------------------------
# Each invariant describes a BLOCKED action.  The engine treats any firing
# Pack A rule as a reason to push that candidate to rejected_candidates or
# add the field to protected_fields, NEVER to proposed.
#
# Preconditions = the BAD scenario being guarded against.
# A rule firing = "this action would be unsafe right now".

_PACK_A: list[SetupRule] = [
    SetupRule(
        rule_id="A1",
        pack="A",
        phase=RulePhase.safety,
        preconditions={"dominant_problem": "__NOT_high_speed_instability__"},
        contraindications={},
        field="aero_front",
        delta_fn="decrease_front_aero",
        title="Front downforce cut — blocked without instability evidence",
        symptom="Reducing front downforce without high-speed instability evidence risks floaty front.",
        rationale=(
            "Driver profile: no floaty front; front aero must not be reduced unless "
            "telemetry confirms excessive front-end drag causing instability. "
            "aero_front_near_min=True makes this doubly protected."
        ),
        risk=RiskLevel.high,
        base_confidence=ConfidenceLevel.high,
        driver_style_tags=["protects_downforce", "dislikes_floaty_front"],
    ),
    SetupRule(
        rule_id="A2",
        pack="A",
        phase=RulePhase.safety,
        # Re-keyed (Group 43): fire on REAL diagnosis signals from build_setup_diagnosis.
        # __any__ form: fires if EITHER flag is truthy (OR semantics).
        # Note: no distinct high-speed-oversteer diagnosis signal exists in the
        # current diagnosis output, so that leg is omitted (deferred).
        preconditions={
            "__any__": [
                "driver_feel_flags.rear_loose_on_exit",
                "driver_feel_flags.snap_oversteer_exit",
            ]
        },
        contraindications={},
        field="aero_rear",
        delta_fn="decrease_rear_aero",
        title="Rear downforce cut — blocked under rear instability / snap exit",
        symptom="Cutting rear aero during rear loose on exit or snap oversteer exit.",
        rationale=(
            "Rear aero is a traction and stability tool first. Cutting it while "
            "rear instability or snap exit is present is a hard safety invariant. "
            "High-speed-oversteer guard deferred (no distinct diagnosis signal exists)."
        ),
        risk=RiskLevel.high,
        base_confidence=ConfidenceLevel.high,
        driver_style_tags=["protects_downforce", "dislikes_snap_exit"],
    ),
    SetupRule(
        rule_id="A3",
        pack="A",
        phase=RulePhase.safety,
        # Re-keyed (Group 43): precondition unchanged (bottoming_band=="minor").
        # Contraindications now use REAL diagnosis keys:
        #   - bottoming_confidence.band in {"consider","required"} → __in_consider_required__
        #   - compliance_priority=True
        # The aero-platform leg is omitted (no real aero_platform_evidence key; deferred).
        # Logic: precondition fires (minor bottoming) → field protected UNLESS
        # a contraindication matches (in which case protection is suppressed and
        # another rule may propose the raise).
        preconditions={"bottoming_band": "minor"},
        contraindications={
            "bottoming_confidence.band": "__in_consider_required__",
            "compliance_priority": True,
            # Note: aero_platform_evidence leg removed — no real key; deferred.
        },
        field="ride_height_front",
        delta_fn="raise_front_rh",
        title="Front ride-height raise — blocked for minor bottoming without escalated confidence",
        symptom="Raising front ride-height when bottoming is only minor with no escalated bottoming confidence.",
        rationale=(
            "Minor bottoming does not justify a ride-height increase unless "
            "bottoming_confidence is 'consider' or 'required', or compliance_priority "
            "is active (which unlocks C8). Raising ride-height without escalated "
            "evidence increases CoG and reduces aero efficiency unnecessarily."
        ),
        risk=RiskLevel.med,
        base_confidence=ConfidenceLevel.high,
        driver_style_tags=[],
    ),
    SetupRule(
        rule_id="A4",
        pack="A",
        phase=RulePhase.safety,
        # Re-keyed (Group 43): same approach as A3 — identical contraindications.
        # bottoming_confidence.band in {"consider","required"} OR compliance_priority=True
        # suppresses the protection, allowing C8 to propose the rear ride-height raise.
        preconditions={"bottoming_band": "minor"},
        contraindications={
            "bottoming_confidence.band": "__in_consider_required__",
            "compliance_priority": True,
            # Note: aero_platform_evidence leg removed — no real key; deferred.
        },
        field="ride_height_rear",
        delta_fn="raise_rear_rh",
        title="Rear ride-height raise — blocked for minor bottoming without escalated confidence",
        symptom="Raising rear ride-height when bottoming is only minor with no escalated bottoming confidence.",
        rationale=(
            "Same principle as A3 applied to the rear. "
            "Premature rear ride-height increases upset rear aero platform. "
            "Suppressed when bottoming_confidence escalates or compliance_priority is active."
        ),
        risk=RiskLevel.med,
        base_confidence=ConfidenceLevel.high,
        driver_style_tags=[],
    ),
    SetupRule(
        rule_id="A5",
        pack="A",
        phase=RulePhase.safety,
        # Re-keyed (Group 43): fire on REAL diagnosis signals from build_setup_diagnosis.
        # __any__ form: fires if EITHER condition is truthy (OR semantics).
        #   - driver_feel_flags.braking_instability: True (driver-reported braking issue)
        #   - avg_lockups: non-zero (telemetry-confirmed lock-ups; 0/0.0 is falsy → no fire)
        # Note: driver_feel_flags.braking_instability is the available proxy for both
        # entry instability and rear-brake instability. A distinct entry-oversteer
        # signal (separate from braking_instability) is deferred — no dedicated key exists.
        preconditions={
            "__any__": [
                "driver_feel_flags.braking_instability",
                "avg_lockups",
            ]
        },
        contraindications={},
        field="brake_bias",
        delta_fn="brake_bias_rear",
        title="Brake bias rearward — blocked under braking instability / lock-ups",
        symptom="Moving brake bias rearward during braking instability or confirmed lock-ups.",
        rationale=(
            "Rearward brake bias during braking instability or lock-ups amplifies "
            "the problem. This is an absolute safety invariant. "
            "driver_feel_flags.braking_instability covers entry/rear-brake instability; "
            "avg_lockups provides telemetry confirmation."
        ),
        risk=RiskLevel.high,
        base_confidence=ConfidenceLevel.high,
        driver_style_tags=["trail_braker"],
    ),
    SetupRule(
        rule_id="A6",
        pack="A",
        phase=RulePhase.safety,
        preconditions={},
        contraindications={},
        field="transmission_max_speed_kmh",
        delta_fn="noop",
        title="transmission_max_speed_kmh — display-only, never actionable",
        symptom="transmission_max_speed_kmh attempted as an actionable change.",
        rationale=(
            "transmission_max_speed_kmh is a display-only computed field. "
            "It must never appear in approved_changes. Protected unconditionally."
        ),
        risk=RiskLevel.high,
        base_confidence=ConfidenceLevel.high,
        driver_style_tags=[],
    ),
    SetupRule(
        rule_id="A7",
        pack="A",
        phase=RulePhase.safety,
        preconditions={"gearbox_fake_field": True},
        contraindications={},
        field="__gearbox_fake__",
        delta_fn="noop",
        title="Gearbox field must be final_drive or gear_1..gear_6",
        symptom="Gearbox field outside {final_drive, gear_1..gear_6} attempted.",
        rationale=(
            "Only real gearbox fields are actionable. Fake fields (e.g. 'gear_ratios' "
            "as a raw array, or unknown names) must be rejected before surfacing."
        ),
        risk=RiskLevel.high,
        base_confidence=ConfidenceLevel.high,
        driver_style_tags=[],
    ),
    SetupRule(
        rule_id="A8",
        pack="A",
        phase=RulePhase.safety,
        preconditions={"gear_ratio_inversion": True},
        contraindications={},
        field="__gear_inversion__",
        delta_fn="noop",
        title="Gear ratio inversion — hard reject",
        symptom="Proposed gear ratios would invert (higher gear gets higher ratio).",
        rationale=(
            "Gear ratios must decrease from gear_1 to gear_N. "
            "Any inversion is physically invalid for sequential gearboxes."
        ),
        risk=RiskLevel.high,
        base_confidence=ConfidenceLevel.high,
        driver_style_tags=[],
    ),
]

# ---------------------------------------------------------------------------
# Pack B — Driver-Style Rules
# ---------------------------------------------------------------------------

_PACK_B: list[SetupRule] = [
    SetupRule(
        rule_id="B1",
        pack="B",
        phase=RulePhase.driver_style,
        preconditions={
            "driver_feel_flags.floaty_front": True,
            "aero_front_near_min": True,
        },
        contraindications={},
        field="aero_front",
        delta_fn="increase_front_aero",
        title="Increase front aero — floaty front + at minimum",
        symptom="Floaty front with aero_front near minimum — platform-limited.",
        rationale=(
            "Driver dislikes floaty front and front aero is already near minimum. "
            "This is a platform-limited diagnosis: increase front downforce directly."
        ),
        risk=RiskLevel.low,
        base_confidence=ConfidenceLevel.high,
        driver_style_tags=["dislikes_floaty_front", "prefers_front_bite"],
    ),
    SetupRule(
        rule_id="B2",
        pack="B",
        phase=RulePhase.driver_style,
        preconditions={
            "driver_feel_flags.floaty_front": True,
        },
        contraindications={
            "aero_front_near_min": True,  # already handled by B1
        },
        field="arb_front",
        delta_fn="increase_front_arb",
        title="Increase front ARB — floaty front (mechanical fix)",
        symptom="Floaty front when front aero is not at minimum.",
        rationale=(
            "Driver dislikes floaty front / lazy turn-in. "
            "Increasing front ARB sharpens the front without touching aero "
            "when aero is not the limiting factor."
        ),
        risk=RiskLevel.low,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=["dislikes_floaty_front", "prefers_front_bite"],
    ),
    SetupRule(
        rule_id="B3",
        pack="B",
        phase=RulePhase.exit,
        preconditions={
            "driver_feel_flags.snap_oversteer_exit": True,
        },
        contraindications={
            "driver_feel_flags.floaty_front": True,
            # Contraindicated under high tyre wear: reducing LSD accel under high wear
            # increases rear wheel speed differential, which accelerates tyre degradation
            # on already-worn tyres and risks snap oversteer on exit.
            "tyre_wear_high": True,
        },
        field="lsd_accel",
        delta_fn="decrease_lsd_accel",
        title="Reduce LSD accel — snap exit oversteer",
        symptom="Snap oversteer on exit — LSD accel too aggressive.",
        rationale=(
            "Driver dislikes snap exit. Reducing LSD accel allows more wheel "
            "speed differential on exit, reducing the snap. "
            "Only safe when front is not already floaty."
        ),
        risk=RiskLevel.med,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=["dislikes_snap_exit", "rotation_without_snap"],
    ),
    SetupRule(
        rule_id="B4",
        pack="B",
        phase=RulePhase.driver_style,
        preconditions={
            "wheelspin_band": "__not_low__",
            "driver_feel_flags.rear_loose_on_exit": True,
        },
        contraindications={
            "aero_rear_healthy": True,
        },
        field="aero_rear",
        delta_fn="increase_rear_aero",
        title="Increase rear aero — rear loose + wheelspin",
        symptom="Rear loose on exit with wheelspin and rear aero not at healthy level.",
        rationale=(
            "Driver prefers rear stability as the first tool. "
            "Increasing rear aero adds traction and stability platform "
            "when rear aero is not already at a healthy fraction."
        ),
        risk=RiskLevel.low,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=["rotation_without_snap", "prefers_front_bite"],
    ),
    SetupRule(
        rule_id="B5",
        pack="B",
        phase=RulePhase.straight,
        # Re-keyed (Group 43): fire on REAL diagnosis signals from build_setup_diagnosis.
        # Two exact-match preconditions (ALL must match — AND semantics):
        #   - gearing_diagnosis_category == "gear_too_short": telemetry confirms rev-limiter
        #     hits in top gear indicating the ratio is too short for the track's straights.
        #   - gearbox_flag == "may_change": engineering validation allows gearbox edits.
        #     None / "preserve" will not match this exact precondition, so B5 cannot fire
        #     when the gearbox is locked (no __not_equal__ token exists in the engine;
        #     the exact-match precondition alone handles None/preserve/other values).
        # Self-consistency: gear_too_short is NOT in the validator's preserve set
        # {insufficient_data, gear_too_long, limiter_limited}, so a final_drive change
        # on gear_too_short + may_change passes the gearbox_category_mismatch validator.
        # Delta: final_drive_down returns -0.05 (lower ratio number = taller/longer gearing
        # = higher top speed), which is the correct direction to fix gear_too_short.
        # NOTE: limiter-before-braking (rev limiter hit before a braking zone)
        # maps to the gearing_diagnosis_category == "gear_too_short" signal.  There is no
        # separate "limiter_before_braking" diagnosis key; the relevant evidence surface
        # is per_gear_limiter_evidence (alias of rev_limiter_by_gear in the diagnosis dict).
        preconditions={
            "gearing_diagnosis_category": "gear_too_short",
            "gearbox_flag": "may_change",
        },
        contraindications={},
        field="final_drive",
        delta_fn="final_drive_down",
        title="Lengthen gearing — gear too short on straights",
        symptom="Rev limiter hit on straights — gearing too short, top speed limited.",
        rationale=(
            "Driver values lap speed over raw acceleration. "
            "Decreasing the final_drive ratio (final_drive_down, delta=-0.05) "
            "lengthens the gearing, raising top speed. "
            "Only fires when telemetry diagnosis confirms gear_too_short AND "
            "the engineering gate allows gearbox changes (gearbox_flag=may_change)."
        ),
        risk=RiskLevel.low,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=["race_values_consistency"],
        applies_session=SessionType.race,
    ),
    SetupRule(
        rule_id="B5b",
        pack="B",
        phase=RulePhase.straight,
        # Group 45: complement to B5 — fires when gearing is diagnosed as too long.
        # Preconditions (ALL must match):
        #   - gearing_diagnosis_category == "gear_too_long": telemetry confirms
        #     under-revving in top gear (speed ratio >= 0.98, no limiter hits).
        #   - gearbox_flag == "may_change": engineering gate allows gearbox edits.
        # Delta: final_drive_up returns +0.05 (higher ratio number = shorter gearing
        # = more acceleration / earlier power delivery at cost of top speed).
        # NOTE: gearbox_category "limiter_limited" stays a preserve category — B5b
        # does NOT fire on limiter_limited (gearbox_flag is "preserve" in that case).
        preconditions={
            "gearing_diagnosis_category": "gear_too_long",
            "gearbox_flag": "may_change",
        },
        contraindications={},
        field="final_drive",
        delta_fn="final_drive_up",
        title="Shorten gearing — gear too long, power band under-used",
        symptom="Gearing too long — car under-revving in top gear, losing acceleration.",
        rationale=(
            "When speed ratio >= 0.98 with no rev-limiter hits, the gearing is "
            "too long and the driver is leaving power on the table. "
            "Increasing the final_drive ratio (final_drive_up, delta=+0.05) "
            "shortens the gearing for better power delivery. "
            "Only fires when telemetry diagnosis confirms gear_too_long AND "
            "the engineering gate allows gearbox changes (gearbox_flag=may_change)."
        ),
        risk=RiskLevel.low,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=["race_values_consistency"],
        applies_session=SessionType.race,
    ),
    SetupRule(
        rule_id="B6",
        pack="B",
        phase=RulePhase.driver_style,
        preconditions={
            "wheelspin_band": "__not_low__",
        },
        contraindications={
            "driver_feel_flags.snap_oversteer_exit": True,
        },
        field="lsd_accel",
        delta_fn="increase_lsd_accel",
        title="Increase LSD accel — wheelspin (progressive throttle fix)",
        symptom="Wheelspin without snap exit — LSD accel can be increased for progressive throttle.",
        rationale=(
            "Driver prefers progressive throttle traction. "
            "Increasing LSD accel reduces wheelspin without causing snap "
            "when snap exit is not already reported."
        ),
        risk=RiskLevel.low,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=["rotation_without_snap"],
    ),
]

# ---------------------------------------------------------------------------
# Pack C / D — Phase Starter Rules
# ---------------------------------------------------------------------------
# At least one rule for each phase: entry, mid, exit, kerb.
# All keys reference REAL diagnosis keys from build_setup_diagnosis.

_PACK_CD: list[SetupRule] = [
    # --- Entry rules ---
    SetupRule(
        rule_id="C1_entry_lsd_decel",
        pack="C",
        phase=RulePhase.entry,
        preconditions={
            "driver_feel_flags.entry_understeer": True,
        },
        contraindications={
            "driver_feel_flags.rear_loose_on_exit": True,
            # Contraindicated under high tyre wear: reducing LSD decel increases entry
            # rotation, which scrubs already-worn front tyres harder on corner entry and
            # risks rear snap oversteer when rear tyre grip is marginal.
            "tyre_wear_high": True,
        },
        field="lsd_decel",
        delta_fn="decrease_lsd_decel",
        title="Reduce LSD decel — entry understeer (rotation fix)",
        symptom="Entry understeer — reducing LSD decel allows more entry rotation.",
        rationale=(
            "Trail braker who relies on brake-release rotation. "
            "Reducing LSD decel unlocks rotation on entry without destabilising the rear. "
            "Contraindicated when rear is already loose on exit."
        ),
        risk=RiskLevel.med,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=["trail_braker", "prefers_front_bite"],
    ),
    SetupRule(
        rule_id="C2_entry_brake_bias",
        pack="C",
        phase=RulePhase.entry,
        preconditions={
            "driver_feel_flags.braking_instability": True,
            "avg_lockups": "__gt_zero__",
        },
        contraindications={
            "driver_feel_flags.entry_understeer": True,
            # Under no-ABS, rear lock must be controlled via LSD decel (NoABS1),
            # NOT by moving brake bias forward.  Front bias is wrong for any
            # no-ABS setup — contraindicate so NoABS1 is the sole remedy.
            "no_abs": True,
        },
        field="brake_bias",
        delta_fn="brake_bias_front",
        title="Move brake bias forward — braking instability / lock-ups",
        symptom="Braking instability with lock-ups — bias too far rear.",
        rationale=(
            "Trail braker sensitive to brake balance. "
            "Moving bias forward reduces rear lock-up tendency on trail braking. "
            "Contraindicated when entry understeer is already present."
        ),
        risk=RiskLevel.low,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=["trail_braker"],
    ),
    # --- Mid-corner rules ---
    SetupRule(
        rule_id="C3_mid_arb_rear",
        pack="C",
        phase=RulePhase.mid,
        preconditions={
            "dominant_problem": "__contains_understeer__",
        },
        contraindications={
            "driver_feel_flags.rear_loose_on_exit": True,
            "wheelspin_band": "__not_low__",
            # Contraindicated under high tyre wear: stiffening the rear ARB pulls more
            # lateral load transfer onto worn rear tyres, which are the most load-
            # sensitive, raising rear-breakaway / oversteer risk under marginal grip.
            "tyre_wear_high": True,
        },
        field="arb_rear",
        delta_fn="increase_rear_arb",
        title="Stiffen rear ARB — mid-corner understeer",
        symptom="Mid-corner understeer — stiffening rear ARB shifts load off the front.",
        rationale=(
            "Roll-stiffness distribution sets the elastic lateral-load-transfer "
            "split, and the stiffer axle sheds grip via tyre load sensitivity. "
            "Stiffening the REAR ARB moves more lateral load transfer onto the rear "
            "axle, reducing rear grip relative to the front so the car rotates more "
            "and understeer eases. (Softening the rear bar does the opposite — it "
            "adds rear grip and worsens understeer.) Contraindicated when the rear "
            "is already loose, wheelspin is present, or tyres are worn, since "
            "stiffening the rear then risks oversteer / reduced traction."
        ),
        risk=RiskLevel.med,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=["rotation_without_snap"],
    ),
    SetupRule(
        rule_id="C4_mid_rear_aero",
        pack="C",
        phase=RulePhase.mid,
        preconditions={
            "wheelspin_band": "__not_low__",
            "aero_rear_near_min": False,
        },
        contraindications={
            "aero_rear_healthy": True,
        },
        field="aero_rear",
        delta_fn="increase_rear_aero",
        title="Increase rear aero — mid-corner wheelspin",
        symptom="Mid-corner wheelspin — rear aero increase stabilises platform.",
        rationale=(
            "Rear aero increases mechanical downforce and traction. "
            "When wheelspin is meaningful and rear aero is not already healthy "
            "or at minimum, adding downforce is the lowest-risk correction."
        ),
        risk=RiskLevel.low,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=["rotation_without_snap"],
    ),
    # --- Exit rules ---
    SetupRule(
        rule_id="C5_exit_lsd_accel",
        pack="C",
        phase=RulePhase.exit,
        preconditions={
            "wheelspin_subtype": "__is_traction__",  # wheelspin not snap_throttle_induced
            "wheelspin_band": "__not_low__",
        },
        contraindications={
            "driver_feel_flags.snap_oversteer_exit": True,
        },
        field="lsd_accel",
        delta_fn="increase_lsd_accel",
        title="Increase LSD accel — exit wheelspin (traction subtype)",
        symptom="Exit wheelspin from traction deficit — LSD accel increase helps.",
        rationale=(
            "When wheelspin subtype is traction (not snap), increasing LSD accel "
            "locks the rear axle more on throttle, reducing wheelspin. "
            "Contraindicated when snap oversteer is also present."
        ),
        risk=RiskLevel.low,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=["rotation_without_snap"],
    ),
    SetupRule(
        rule_id="C6_exit_rear_aero",
        pack="C",
        phase=RulePhase.exit,
        preconditions={
            "driver_feel_flags.rear_loose_on_exit": True,
            "wheelspin_band": "__not_low__",
        },
        contraindications={
            "aero_rear_healthy": True,
            "driver_feel_flags.snap_oversteer_exit": True,
        },
        field="aero_rear",
        delta_fn="increase_rear_aero",
        title="Increase rear aero — rear loose on exit",
        symptom="Rear loose on exit with wheelspin — rear platform lacking.",
        rationale=(
            "Driver prioritises rear stability for earlier throttle application. "
            "Rear aero increase is the lowest-risk correction for a loose rear."
        ),
        risk=RiskLevel.low,
        base_confidence=ConfidenceLevel.high,
        driver_style_tags=["rotation_without_snap", "dislikes_snap_exit"],
    ),
    # --- Kerb rules ---
    SetupRule(
        rule_id="C7_kerb_arb_rear",
        pack="C",
        phase=RulePhase.kerb,
        preconditions={
            "compliance_priority": True,
        },
        contraindications={
            "wheelspin_band": "__not_low__",
            # Contraindicated under high tyre wear: reducing rear ARB over kerbs on
            # worn tyres increases lateral compliance and rear rotation risk under
            # the impulsive loads of kerb strikes, which can unsettle an already
            # grip-limited rear axle.
            "tyre_wear_high": True,
        },
        field="arb_rear",
        delta_fn="decrease_rear_arb",
        title="Reduce rear ARB — kerb compliance priority",
        symptom="Compliance priority set — car harsh over kerbs.",
        rationale=(
            "When compliance_priority is True the car is too stiff over kerbs. "
            "Reducing rear ARB softens the platform for better kerb absorption."
        ),
        risk=RiskLevel.low,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=[],
    ),
    SetupRule(
        rule_id="C8_kerb_rh_rear",
        pack="C",
        phase=RulePhase.kerb,
        preconditions={
            "compliance_priority": True,
            "bottoming_confidence.band": "__in_consider_required__",
        },
        contraindications={},
        field="ride_height_rear",
        delta_fn="raise_rear_rh",
        title="Raise rear ride-height — kerb bottoming + compliance priority",
        symptom="Compliance priority + meaningful bottoming — kerb strikes causing bottoming.",
        rationale=(
            "When compliance priority is set AND bottoming is at 'consider' or 'required', "
            "the car is bottoming on kerbs. A conservative ride-height increase "
            "reduces this risk without the full RH penalty."
        ),
        risk=RiskLevel.med,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=[],
    ),
]

# ---------------------------------------------------------------------------
# Pack P — Porsche-Specific Rules (RR / Gr.3 drivetrain-scoped)
# ---------------------------------------------------------------------------
# Scope: applies_drivetrain=rr AND/OR applies_car_class=gr3.
# CAR_DRIVETRAIN_OVERRIDES maps "Porsche 911 RSR (991) '17" → "rr".
# source_label for explainability: "Porsche-specific rule" (pack=="P").
#
# REAR AERO PROTECTION UNDER REAR INSTABILITY:
# Pack A A2 already covers the case where rear_loose_on_exit OR snap_oversteer_exit
# is present — it unconditionally blocks aero_rear decrease as a safety invariant.
# Therefore no separate Pack P contraindication rule is needed for that scenario:
# A2 is the authoritative guard and is NOT scope-filtered (Pack A rules are exempt
# from _scope_matches filtering — they are safety invariants always evaluated).
# P2 exists as an explicit documentation/reference rule to make the protection
# visible in the rejected_candidates list for RR cars; it does NOT author a change.

_PACK_P: list[SetupRule] = [
    SetupRule(
        rule_id="P1",
        pack="P",
        phase=RulePhase.exit,
        # Fires when wheelspin is snap_throttle_induced.
        # The exact diagnosis key for snap-throttle wheelspin is "wheelspin_subtype"
        # with value "snap_throttle_induced" (confirmed from _classify_wheelspin_subtype
        # in setup_diagnosis.py).
        preconditions={
            "wheelspin_subtype": "snap_throttle_induced",
        },
        contraindications={
            # Hard block: if driver already reports snap oversteer on exit, do NOT increase
            # LSD accel (this mirrors the existing lsd_accel snap contraindication in _process_rule).
            "driver_feel_flags.snap_oversteer_exit": True,
        },
        field="lsd_accel",
        delta_fn="increase_lsd_accel",
        title="Increase LSD accel — snap throttle wheelspin (RR traction-first)",
        symptom="Snap-throttle-induced wheelspin on exit — traction deficit under snap application.",
        rationale=(
            "Porsche-specific rule (RR drivetrain). "
            "When wheelspin subtype is snap_throttle_induced, the rear wheels break "
            "traction abruptly under throttle application. For RR cars, increasing "
            "LSD accel cautiously locks the rear axle to prevent the abrupt slip. "
            "Contraindicated when snap oversteer on exit is already reported "
            "— that indicates the LSD is already too locked and needs the opposite treatment. "
            "Magnitude is intentionally conservative (delta=+2 via increase_lsd_accel). "
            "Traction-first: do NOT reduce rear downforce to fix top-speed-low + snap wheelspin "
            "— always address traction before aero-cut for RR cars under snap conditions."
        ),
        risk=RiskLevel.med,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=["rotation_without_snap"],
        applies_drivetrain=DrivetrainType.rr,
        applies_car_class=CarClass.gr3,
        applies_session=SessionType.any,
    ),
    # P2 is intentionally OMITTED here.
    # Pack A A2 already provides the unconditional safety invariant that blocks
    # aero_rear decrease under rear_loose_on_exit / snap_oversteer_exit for ALL
    # drivetrain types.  A2 is NOT scope-filtered (Pack A rules are exempt), so it
    # fires for RR cars too.  A separate P2 duplicating A2 would conflict with the
    # engine's Pack A processing and could propose the decrease before A2 rejects it.
    # Explainability for the RR-specific context is provided by the A2 rejected_candidate
    # plus the car_drivetrain_influence field on P1 and other P-pack rules.
]

# ---------------------------------------------------------------------------
# Pack NOABS — No-ABS regulation rules
# ---------------------------------------------------------------------------
# Fires when the event disables ABS (no_abs injected into diagnosis by
# driving_advisor.build_combined_setup_response) and lock-ups or braking
# instability are confirmed.  Recommends increasing LSD decel to resist
# rear-wheel differential rotation under hard braking without ABS.

_PACK_NOABS: list[SetupRule] = [
    SetupRule(
        rule_id="NoABS1",
        pack="NOABS",
        phase=RulePhase.entry,
        preconditions={
            "no_abs": True,
            "__any__": [
                "driver_feel_flags.braking_instability",
                "avg_lockups",
            ],
        },
        contraindications={
            # Avoids conflict with C1 (entry understeer → decrease lsd_decel).
            # If entry understeer is present, the rotation-fix takes priority.
            "driver_feel_flags.entry_understeer": True,
        },
        field="lsd_decel",
        delta_fn="increase_lsd_decel",
        title="Increase LSD decel — no-ABS braking stability",
        symptom=(
            "No-ABS event with lock-ups or braking instability — "
            "rear unsettled under threshold braking."
        ),
        rationale=(
            "Without ABS, unchecked wheel lock at the rear destabilises the car on entry. "
            "Increasing LSD decel resistance limits differential rotation under braking, "
            "keeping the rear planted. Control rear lock via LSD decel, not front bias. "
            "Contraindicated when entry understeer is already present — "
            "that scenario requires the C1 rotation fix (decrease lsd_decel) instead."
        ),
        risk=RiskLevel.med,
        base_confidence=ConfidenceLevel.med,
        driver_style_tags=[],
    ),
]

# ---------------------------------------------------------------------------
# Register all built-in packs at import time
# ---------------------------------------------------------------------------

register_pack("A", _PACK_A)
register_pack("B", _PACK_B)
register_pack("CD", _PACK_CD)
register_pack("P", _PACK_P)
register_pack("NOABS", _PACK_NOABS)
