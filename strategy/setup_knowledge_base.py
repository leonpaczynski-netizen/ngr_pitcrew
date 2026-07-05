"""Setup rule knowledge base — Group 42: Rule-First Setup Brain.

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

Deferred
--------
- Remaining per-setting Pack C rules for every diagnosis key (only a starter
  set is defined here; the architecture supports unlimited growth).
- Per-car DrivetrainType / CarClass scoping (currently all rules default to
  'any' for those axes — add specificity once more data is in).
"""
from __future__ import annotations

from enum import Enum
from typing import NamedTuple


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
    """Increase front aero by 1 step."""
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
        preconditions={
            "__any__": [
                "rear_instability_evidence",
                "snap_exit_evidence",
                "high_speed_oversteer_evidence",
            ]
        },
        contraindications={},
        field="aero_rear",
        delta_fn="decrease_rear_aero",
        title="Rear downforce cut — blocked under rear instability",
        symptom="Cutting rear aero during rear instability / snap exit / high-speed oversteer.",
        rationale=(
            "Rear aero is a traction and stability tool first. Cutting it while "
            "rear instability, snap exit, or high-speed oversteer is present "
            "is a hard safety invariant."
        ),
        risk=RiskLevel.high,
        base_confidence=ConfidenceLevel.high,
        driver_style_tags=["protects_downforce", "dislikes_snap_exit"],
    ),
    SetupRule(
        rule_id="A3",
        pack="A",
        phase=RulePhase.safety,
        preconditions={"bottoming_band": "minor"},
        contraindications={
            "__any__": [
                "bottoming_evidence",
                "kerb_evidence",
                "compression_evidence",
                "aero_platform_evidence",
            ]
        },
        field="ride_height_front",
        delta_fn="raise_front_rh",
        title="Front ride-height raise — blocked without evidence",
        symptom="Raising front ride-height without bottoming/kerb/compression/aero-platform evidence.",
        rationale=(
            "Minor bottoming does not justify a ride-height increase. "
            "Raising ride-height without evidence increases CoG and reduces "
            "aero efficiency unnecessarily."
        ),
        risk=RiskLevel.med,
        base_confidence=ConfidenceLevel.high,
        driver_style_tags=[],
    ),
    SetupRule(
        rule_id="A4",
        pack="A",
        phase=RulePhase.safety,
        preconditions={"bottoming_band": "minor"},
        contraindications={
            "__any__": [
                "bottoming_evidence",
                "kerb_evidence",
                "compression_evidence",
                "aero_platform_evidence",
            ]
        },
        field="ride_height_rear",
        delta_fn="raise_rear_rh",
        title="Rear ride-height raise — blocked without evidence",
        symptom="Raising rear ride-height without bottoming/kerb/compression/aero-platform evidence.",
        rationale=(
            "Same principle as A3 applied to the rear. "
            "Premature rear ride-height increases upset rear aero platform."
        ),
        risk=RiskLevel.med,
        base_confidence=ConfidenceLevel.high,
        driver_style_tags=[],
    ),
    SetupRule(
        rule_id="A5",
        pack="A",
        phase=RulePhase.safety,
        preconditions={
            "__any__": [
                "entry_oversteer_evidence",
                "rear_brake_instability_evidence",
                "lockup_evidence",
            ]
        },
        contraindications={},
        field="brake_bias",
        delta_fn="brake_bias_rear",
        title="Brake bias rearward — blocked under entry oversteer / rear instability",
        symptom="Moving brake bias rearward during entry oversteer, rear brake instability, or lock-ups.",
        rationale=(
            "Rearward brake bias during rear instability/entry oversteer amplifies "
            "the problem. This is an absolute safety invariant."
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
        preconditions={
            "gearbox_flag": "too_short",
        },
        contraindications={},
        field="final_drive",
        delta_fn="decrease_rear_aero",  # delta_fn used as proxy; engine applies negative
        title="Lengthen gearing — too short on straights",
        symptom="Rev limiter hit on straights — gearing too short.",
        rationale=(
            "Driver values lap speed over raw acceleration. "
            "Lengthening the final drive extracts more top-end speed "
            "when the car is bouncing off the rev limiter."
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
        },
        field="arb_rear",
        delta_fn="decrease_rear_arb",
        title="Reduce rear ARB — mid-corner understeer",
        symptom="Mid-corner understeer — softening rear ARB transfers load to front.",
        rationale=(
            "Reducing rear ARB softens the rear platform, transferring more "
            "mid-corner lateral load to the front axle for better rotation. "
            "Contraindicated when rear is loose or wheelspin is present."
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
# Register all built-in packs at import time
# ---------------------------------------------------------------------------

register_pack("A", _PACK_A)
register_pack("B", _PACK_B)
register_pack("CD", _PACK_CD)
