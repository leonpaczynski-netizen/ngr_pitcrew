"""Deterministic diagnosis → vehicle-dynamics mechanism map (Engineering Brain Program 2, Phase 13).

This is the STRUCTURAL bridge from Program 1's canonical diagnosis vocabulary
(``engineering_issue.IssueFamily`` / the ``issue_type`` strings folded by
``issue_family_for`` / an ``axle`` string / a handling-phase string) to Program 2's
Phase-12 vehicle-dynamics knowledge (``vehicle_dynamics.Component`` /
``handling_balance.HandlingPhase`` / ``load_transfer.TransferMode``).

It carries NO mechanism prose of its own — every physical explanation is pulled at
annotation time from the Phase-12 authority (``explain_component`` / ``explain_phase`` /
``explain_transfer`` / ``interactions_for``). It stores only *which* Phase-12 concepts a
canonical diagnosis touches, as a fixed, auditable table of templates. It defines no new
sign data and duplicates no component/interaction/LSD/aero knowledge.

Matching is STRUCTURAL (issue family / issue type / axle / handling phase), never
free-text search. Purity: Qt-free, DB-free, UI-free, network-free, AI-free; deterministic;
never raises; no random, no wall-clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from strategy.vehicle_dynamics import Component
from strategy.load_transfer import TransferMode
from strategy.handling_balance import HandlingPhase

MECHANISM_MAP_VERSION = "mechanism_map_v1"


# --------------------------------------------------------------------------- #
# Program-1 handling-phase string  ->  Phase-12 HandlingPhase
# --------------------------------------------------------------------------- #
# Program 1 uses several small phase vocabularies (corner_diagnosis PHASE_*,
# corner_evidence.CornerPhase, setup_experiment.HandlingPhase). We normalise the
# lowercased string to ONE canonical Phase-12 phase. Unknown -> None (unresolved).
_PHASE_STR_TO_P12: Dict[str, HandlingPhase] = {
    "braking": HandlingPhase.TRAIL_BRAKING,
    "brake": HandlingPhase.TRAIL_BRAKING,
    "trail_braking": HandlingPhase.TRAIL_BRAKING,
    "entry": HandlingPhase.CORNER_ENTRY,
    "corner_entry": HandlingPhase.CORNER_ENTRY,
    "turn_in": HandlingPhase.CORNER_ENTRY,
    "initial_rotation": HandlingPhase.INITIAL_ROTATION,
    "apex": HandlingPhase.MID_CORNER,
    "mid": HandlingPhase.MID_CORNER,
    "mid_corner": HandlingPhase.MID_CORNER,
    "exit": HandlingPhase.EXIT_TRACTION,
    "exit_traction": HandlingPhase.EXIT_TRACTION,
    "traction": HandlingPhase.EXIT_TRACTION,
    "power_on": HandlingPhase.POWER_ON_ROTATION,
    "power_on_rotation": HandlingPhase.POWER_ON_ROTATION,
    "straight": HandlingPhase.STRAIGHT_LINE_STABILITY,
    "straight_line_stability": HandlingPhase.STRAIGHT_LINE_STABILITY,
    "high_speed": HandlingPhase.HIGH_SPEED_STABILITY,
    "high_speed_stability": HandlingPhase.HIGH_SPEED_STABILITY,
}

# When the canonical diagnosis carries NO phase, the issue_type itself often encodes
# the phase deterministically (a physics-informed default, flagged as inferred).
_ISSUE_IMPLIED_PHASE: Dict[str, HandlingPhase] = {
    "front_lock": HandlingPhase.TRAIL_BRAKING,
    "lockup": HandlingPhase.TRAIL_BRAKING,
    "rear_loose_under_braking": HandlingPhase.TRAIL_BRAKING,
    "braking_instability": HandlingPhase.TRAIL_BRAKING,
    "entry_understeer": HandlingPhase.CORNER_ENTRY,
    "mid_corner_understeer": HandlingPhase.MID_CORNER,
    "front_push": HandlingPhase.MID_CORNER,
    "rear_loose_on_exit": HandlingPhase.EXIT_TRACTION,
    "wheelspin": HandlingPhase.EXIT_TRACTION,
    "rear_wheelspin": HandlingPhase.EXIT_TRACTION,
    "poor_traction": HandlingPhase.EXIT_TRACTION,
    "poor_drive_out": HandlingPhase.EXIT_TRACTION,
    "wrong_gear": HandlingPhase.EXIT_TRACTION,
    "gearing_too_long": HandlingPhase.STRAIGHT_LINE_STABILITY,
    "bottoming": HandlingPhase.HIGH_SPEED_STABILITY,
    "kerb": HandlingPhase.MID_CORNER,
}


def resolve_handling_phase(issue_type: str = "", phase_str: str = "",
                           speed_context: str = "") -> Optional[HandlingPhase]:
    """Resolve the Phase-12 handling phase for a canonical diagnosis. Precedence:
    an explicit phase string > the issue-type's implied phase. ``speed_context`` only
    lifts an already-resolved mid/exit understeer to the high-speed phase when the
    caller has genuine high-speed evidence. Returns None when unresolved."""
    high_speed = str(speed_context or "").strip().lower() in (
        "high_speed", "high-speed", "high")
    p = _PHASE_STR_TO_P12.get(str(phase_str or "").strip().lower())
    if p is None:
        p = _ISSUE_IMPLIED_PHASE.get(str(issue_type or "").strip().lower())
    if p is None:
        # A genuine high-speed context is itself a phase signal (Scenario F: high-speed
        # understeer). Without it, a phase-less generic symptom stays unresolved.
        return HandlingPhase.HIGH_SPEED_STABILITY if high_speed else None
    if high_speed and p in (HandlingPhase.MID_CORNER, HandlingPhase.CORNER_ENTRY,
                            HandlingPhase.EXIT_TRACTION):
        return HandlingPhase.HIGH_SPEED_STABILITY
    return p


# --------------------------------------------------------------------------- #
# Mechanism templates
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MechanismTemplate:
    """A structural pointer into the Phase-12 knowledge for one candidate mechanism.
    It holds NO mechanism prose — the annotator pulls that from Phase 12 at build time."""

    mechanism_id: str
    name: str
    handling_phase: HandlingPhase
    transfer_mode: TransferMode
    primary_component: Component
    secondary_components: Tuple[Component, ...] = ()
    interaction_pairs: Tuple[Tuple[Component, Component], ...] = ()
    role_hint: str = "competing"          # "primary" | "secondary" | "competing"
    basis: str = "physics_informed"       # "direct" | "physics_informed"
    intervention_field: str = ""          # the tunable field whose direction a lockout can veto
    requires_speed_context: bool = False  # aero primaries need high-speed evidence
    is_driver_technique: bool = False     # e.g. delayed throttle — not a setup mechanism
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "mechanism_id": self.mechanism_id, "name": self.name,
            "handling_phase": self.handling_phase.value,
            "transfer_mode": self.transfer_mode.value,
            "primary_component": self.primary_component.value,
            "secondary_components": [c.value for c in self.secondary_components],
            "interaction_pairs": [[a.value, b.value] for a, b in self.interaction_pairs],
            "role_hint": self.role_hint, "basis": self.basis,
            "intervention_field": self.intervention_field,
            "requires_speed_context": self.requires_speed_context,
            "is_driver_technique": self.is_driver_technique, "note": self.note,
        }


def _t(*args, **kw) -> MechanismTemplate:
    return MechanismTemplate(*args, **kw)


# The table: canonical issue_type -> ordered candidate mechanisms. Order is display /
# tie-break order only; it never by itself decides the primary (the annotator ranks on
# evidence). Every mechanism references ONLY Phase-12 Components / phases / transfer modes.
_TEMPLATES_BY_ISSUE: Dict[str, Tuple[MechanismTemplate, ...]] = {
    # --- braking lockup (front) -------------------------------------------- #
    "front_lock": (
        _t("brake_front_grip_demand", "Front longitudinal grip demand exceeds available "
           "front grip under forward load transfer",
           HandlingPhase.TRAIL_BRAKING, TransferMode.LONGITUDINAL, Component.BRAKE_BIAS,
           (Component.TYRES, Component.SPRINGS_FRONT, Component.CAMBER_FRONT),
           ((Component.BRAKE_BIAS, Component.LSD_DECEL),), role_hint="primary",
           basis="physics_informed", intervention_field="brake_bias"),
        _t("brake_forward_dive", "Front dive under braking overloads the front tyres, "
           "reducing usable braking grip",
           HandlingPhase.TRAIL_BRAKING, TransferMode.PITCH, Component.SPRINGS_FRONT,
           (Component.DAMPER_BUMP_FRONT,), (), role_hint="competing"),
        _t("brake_tyre_limit", "Front tyre grip / condition limiting braking",
           HandlingPhase.TRAIL_BRAKING, TransferMode.LONGITUDINAL, Component.TYRES,
           (Component.CAMBER_FRONT,), (), role_hint="competing"),
    ),
    "lockup": (
        _t("brake_front_grip_demand", "Front longitudinal grip demand exceeds available "
           "front grip under forward load transfer",
           HandlingPhase.TRAIL_BRAKING, TransferMode.LONGITUDINAL, Component.BRAKE_BIAS,
           (Component.TYRES, Component.SPRINGS_FRONT), ((Component.BRAKE_BIAS, Component.LSD_DECEL),),
           role_hint="primary", intervention_field="brake_bias"),
        _t("brake_tyre_limit", "Front tyre grip / condition limiting braking",
           HandlingPhase.TRAIL_BRAKING, TransferMode.LONGITUDINAL, Component.TYRES,
           (Component.CAMBER_FRONT,), (), role_hint="competing"),
    ),
    # --- rear instability under braking / trail braking (rear) ------------- #
    "rear_loose_under_braking": (
        _t("brake_rear_unload", "Combined braking + steering unloads the rear axle, "
           "raising rear yaw sensitivity as the rear is not tied down",
           HandlingPhase.TRAIL_BRAKING, TransferMode.COMBINED, Component.LSD_DECEL,
           (Component.TOE_REAR, Component.DAMPER_REBOUND_REAR),
           ((Component.LSD_DECEL, Component.BRAKE_BIAS),), role_hint="primary",
           intervention_field="lsd_decel"),
        _t("brake_bias_rearward", "Rearward brake distribution locking / loosening the "
           "rear under braking",
           HandlingPhase.TRAIL_BRAKING, TransferMode.LONGITUDINAL, Component.BRAKE_BIAS,
           (), ((Component.LSD_DECEL, Component.BRAKE_BIAS),), role_hint="competing",
           intervention_field="brake_bias"),
        _t("brake_rear_platform", "Rear platform recovery unsettling the rear on entry",
           HandlingPhase.TRAIL_BRAKING, TransferMode.PITCH, Component.DAMPER_REBOUND_REAR,
           (Component.SPRINGS_REAR,), (), role_hint="competing"),
    ),
    "braking_instability": (
        _t("brake_rear_unload", "Combined braking + steering unloads the rear axle, "
           "raising rear yaw sensitivity",
           HandlingPhase.TRAIL_BRAKING, TransferMode.COMBINED, Component.LSD_DECEL,
           (Component.TOE_REAR, Component.BRAKE_BIAS),
           ((Component.LSD_DECEL, Component.BRAKE_BIAS),), role_hint="primary",
           intervention_field="lsd_decel"),
        _t("brake_bias_rearward", "Brake distribution destabilising the car under braking",
           HandlingPhase.TRAIL_BRAKING, TransferMode.LONGITUDINAL, Component.BRAKE_BIAS,
           (), (), role_hint="competing", intervention_field="brake_bias"),
    ),
    # --- entry understeer (front) ------------------------------------------ #
    "entry_understeer": (
        _t("entry_front_roll_stiffness", "Front roll stiffness taking too much lateral "
           "load transfer on turn-in, limiting front grip",
           HandlingPhase.CORNER_ENTRY, TransferMode.YAW, Component.ARB_FRONT,
           (Component.TOE_FRONT, Component.ARB_REAR),
           ((Component.TOE_FRONT, Component.ARB_FRONT),), role_hint="primary",
           intervention_field="arb_front"),
        _t("entry_front_geometry", "Front toe / geometry slowing initial rotation",
           HandlingPhase.CORNER_ENTRY, TransferMode.YAW, Component.TOE_FRONT,
           (), (), role_hint="competing", intervention_field="toe_front"),
        _t("entry_brake_forward", "Forward brake bias reducing entry rotation",
           HandlingPhase.CORNER_ENTRY, TransferMode.LONGITUDINAL, Component.BRAKE_BIAS,
           (), (), role_hint="competing", intervention_field="brake_bias"),
    ),
    "entry_oversteer": (
        _t("entry_rear_free", "Rear too free off-throttle / under braking, yawing the car "
           "past the intended line",
           HandlingPhase.CORNER_ENTRY, TransferMode.YAW, Component.LSD_DECEL,
           (Component.TOE_REAR, Component.ARB_REAR), (), role_hint="primary",
           intervention_field="lsd_decel"),
        _t("entry_rear_roll_stiffness", "Rear roll stiffness reducing rear grip on entry",
           HandlingPhase.CORNER_ENTRY, TransferMode.ROLL, Component.ARB_REAR,
           (), (), role_hint="competing", intervention_field="arb_rear"),
    ),
    # --- mid-corner understeer (front) ------------------------------------- #
    "mid_corner_understeer": (
        _t("mid_front_roll_stiffness", "Front-biased roll-stiffness split takes more lateral "
           "load transfer at the front, reducing steady-state front grip",
           HandlingPhase.MID_CORNER, TransferMode.LATERAL, Component.ARB_FRONT,
           (Component.SPRINGS_FRONT, Component.ARB_REAR, Component.CAMBER_FRONT),
           ((Component.TOE_FRONT, Component.ARB_FRONT),), role_hint="primary",
           intervention_field="arb_front"),
        _t("mid_front_tyre", "Front camber / tyre contact-patch limiting mid-corner grip",
           HandlingPhase.MID_CORNER, TransferMode.LATERAL, Component.CAMBER_FRONT,
           (Component.TYRES,), ((Component.CAMBER_FRONT, Component.TYRES),),
           role_hint="competing", intervention_field="camber_front"),
        _t("mid_aero_balance", "Speed-dependent aero balance washing out the front",
           HandlingPhase.HIGH_SPEED_STABILITY, TransferMode.PLATFORM, Component.AERO_FRONT,
           (Component.RIDE_HEIGHT_FRONT,), (), role_hint="competing",
           intervention_field="aero_front", requires_speed_context=True),
    ),
    "front_push": (
        _t("mid_front_roll_stiffness", "Front-biased roll stiffness reducing front grip",
           HandlingPhase.MID_CORNER, TransferMode.LATERAL, Component.ARB_FRONT,
           (Component.SPRINGS_FRONT,), (), role_hint="primary", intervention_field="arb_front"),
    ),
    "understeer": (   # generic: phase decides; primary only when a phase resolves
        _t("mid_front_roll_stiffness", "Front-biased roll stiffness reducing front grip",
           HandlingPhase.MID_CORNER, TransferMode.LATERAL, Component.ARB_FRONT,
           (Component.SPRINGS_FRONT, Component.ARB_REAR), (), role_hint="competing",
           intervention_field="arb_front"),
        _t("mid_aero_balance", "Speed-dependent aero balance washing out the front",
           HandlingPhase.HIGH_SPEED_STABILITY, TransferMode.PLATFORM, Component.AERO_FRONT,
           (), (), role_hint="competing", intervention_field="aero_front",
           requires_speed_context=True),
    ),
    # --- mid-corner / power-on oversteer (rear) ---------------------------- #
    "oversteer": (
        _t("mid_rear_roll_stiffness", "Rear-biased roll-stiffness split takes more lateral "
           "load transfer at the rear, reducing steady-state rear grip",
           HandlingPhase.MID_CORNER, TransferMode.LATERAL, Component.ARB_REAR,
           (Component.SPRINGS_REAR, Component.CAMBER_REAR), (), role_hint="competing",
           intervention_field="arb_rear"),
        _t("power_rear_grip", "Rear grip / aero too low to resist power-on rotation",
           HandlingPhase.POWER_ON_ROTATION, TransferMode.COMBINED, Component.AERO_REAR,
           (Component.TOE_REAR,), (), role_hint="competing", intervention_field="aero_rear"),
    ),
    "snap_oversteer": (
        _t("power_rear_step", "Rear steps out under power as it nears its combined-grip limit",
           HandlingPhase.POWER_ON_ROTATION, TransferMode.COMBINED, Component.ARB_REAR,
           (Component.AERO_REAR, Component.LSD_ACCEL, Component.TOE_REAR),
           ((Component.ARB_REAR, Component.LSD_ACCEL),), role_hint="primary",
           intervention_field="arb_rear"),
    ),
    # --- exit wheelspin (rear) — LSD is NEVER the automatic explanation ----- #
    "wheelspin": (
        _t("exit_traction_demand", "Rear longitudinal traction demand exceeds available "
           "driven-tyre grip while rear load is still rebuilding on exit",
           HandlingPhase.EXIT_TRACTION, TransferMode.LONGITUDINAL, Component.TRANSMISSION,
           (Component.SPRINGS_REAR, Component.TYRES), (), role_hint="primary"),
        _t("exit_diff_locking", "Differential acceleration locking influences the "
           "inside/outside driven-wheel speed split",
           HandlingPhase.EXIT_TRACTION, TransferMode.COMBINED, Component.LSD_ACCEL,
           (), ((Component.LSD_ACCEL, Component.SPRINGS_REAR),
                (Component.ARB_REAR, Component.LSD_ACCEL)), role_hint="competing",
           intervention_field="lsd_accel"),
        _t("exit_gear_selection", "Gear selection too short multiplies wheel torque beyond "
           "available grip",
           HandlingPhase.EXIT_TRACTION, TransferMode.LONGITUDINAL, Component.TRANSMISSION,
           (), (), role_hint="competing", intervention_field="final_drive"),
        _t("exit_rear_load", "Rear normal-load state / platform on exit letting a wheel spin",
           HandlingPhase.EXIT_TRACTION, TransferMode.LONGITUDINAL, Component.SPRINGS_REAR,
           (Component.DAMPER_BUMP_REAR,), (), role_hint="competing",
           intervention_field="springs_rear"),
        _t("exit_tyre_condition", "Rear tyre condition reducing exit traction",
           HandlingPhase.EXIT_TRACTION, TransferMode.LONGITUDINAL, Component.TYRES,
           (Component.CAMBER_REAR,), (), role_hint="competing"),
    ),
    "rear_wheelspin": (
        _t("exit_traction_demand", "Rear longitudinal traction demand exceeds available "
           "driven-tyre grip while rear load is still rebuilding on exit",
           HandlingPhase.EXIT_TRACTION, TransferMode.LONGITUDINAL, Component.TRANSMISSION,
           (Component.SPRINGS_REAR, Component.TYRES), (), role_hint="primary"),
        _t("exit_diff_locking", "Differential acceleration locking influences the "
           "inside/outside driven-wheel speed split",
           HandlingPhase.EXIT_TRACTION, TransferMode.COMBINED, Component.LSD_ACCEL,
           (), ((Component.LSD_ACCEL, Component.SPRINGS_REAR),), role_hint="competing",
           intervention_field="lsd_accel"),
        _t("exit_gear_selection", "Gear selection too short multiplies wheel torque beyond "
           "available grip",
           HandlingPhase.EXIT_TRACTION, TransferMode.LONGITUDINAL, Component.TRANSMISSION,
           (), (), role_hint="competing", intervention_field="final_drive"),
        _t("exit_rear_load", "Rear normal-load state / platform on exit letting a wheel spin",
           HandlingPhase.EXIT_TRACTION, TransferMode.LONGITUDINAL, Component.SPRINGS_REAR,
           (Component.DAMPER_BUMP_REAR,), (), role_hint="competing",
           intervention_field="springs_rear"),
    ),
    "rear_loose_on_exit": (
        _t("exit_diff_locking", "Differential acceleration locking / rear grip on exit "
           "influencing power-on rotation",
           HandlingPhase.EXIT_TRACTION, TransferMode.COMBINED, Component.LSD_ACCEL,
           (Component.AERO_REAR, Component.SPRINGS_REAR),
           ((Component.ARB_REAR, Component.LSD_ACCEL),), role_hint="primary",
           intervention_field="lsd_accel"),
        _t("exit_rear_grip", "Rear grip / aero too low to hold the rear under power",
           HandlingPhase.POWER_ON_ROTATION, TransferMode.COMBINED, Component.AERO_REAR,
           (Component.TOE_REAR,), (), role_hint="competing", intervention_field="aero_rear"),
    ),
    "poor_traction": (
        _t("exit_traction_demand", "Rear traction demand exceeds available driven-tyre grip",
           HandlingPhase.EXIT_TRACTION, TransferMode.LONGITUDINAL, Component.TRANSMISSION,
           (Component.SPRINGS_REAR, Component.TYRES), (), role_hint="primary"),
        _t("exit_diff_locking", "Differential locking behaviour on exit",
           HandlingPhase.EXIT_TRACTION, TransferMode.COMBINED, Component.LSD_ACCEL,
           (), (), role_hint="competing", intervention_field="lsd_accel"),
    ),
    # --- poor drive-out (competing causes; NOT automatically LSD) ----------- #
    "poor_drive_out": (
        _t("drive_gear_torque", "Gear selection places the exit outside the usable torque "
           "band, reducing wheel torque and acceleration",
           HandlingPhase.EXIT_TRACTION, TransferMode.LONGITUDINAL, Component.TRANSMISSION,
           (), (), role_hint="primary", intervention_field="final_drive"),
        _t("drive_wheelspin", "Wheelspin bleeding drive out of the corner",
           HandlingPhase.EXIT_TRACTION, TransferMode.LONGITUDINAL, Component.SPRINGS_REAR,
           (Component.LSD_ACCEL, Component.TYRES), (), role_hint="competing",
           intervention_field="springs_rear"),
        _t("drive_diff_locking", "Differential locking behaviour shaping how torque reaches "
           "the tyres",
           HandlingPhase.EXIT_TRACTION, TransferMode.COMBINED, Component.LSD_ACCEL,
           (), (), role_hint="competing", intervention_field="lsd_accel"),
        _t("drive_exit_understeer", "Excess mid/exit understeer delaying throttle application",
           HandlingPhase.EXIT_TRACTION, TransferMode.LATERAL, Component.ARB_FRONT,
           (), (), role_hint="competing", intervention_field="arb_front"),
        _t("drive_throttle_technique", "Delayed / abrupt throttle application (driver "
           "technique, not a setup mechanism)",
           HandlingPhase.EXIT_TRACTION, TransferMode.LONGITUDINAL, Component.TRANSMISSION,
           (), (), role_hint="competing", is_driver_technique=True),
    ),
    # --- gearing --------------------------------------------------------- #
    "wrong_gear": (
        _t("gear_torque_multiplication", "Gear ratio / final drive places the corner exit "
           "outside the usable torque band",
           HandlingPhase.EXIT_TRACTION, TransferMode.LONGITUDINAL, Component.TRANSMISSION,
           (Component.LSD_ACCEL,), (), role_hint="primary", intervention_field="final_drive"),
    ),
    "gearing_too_long": (
        _t("gear_top_end", "Gearing too long — the drive falls below the usable torque band "
           "out of slow corners and down the straight",
           HandlingPhase.STRAIGHT_LINE_STABILITY, TransferMode.LONGITUDINAL,
           Component.TRANSMISSION, (), (), role_hint="primary", intervention_field="final_drive"),
    ),
    # --- platform: kerb / bump ------------------------------------------- #
    "kerb": (
        _t("kerb_transient_platform", "Transient kerb/bump loading unsettling the platform; "
           "damping and spring rate govern how the wheel recovers",
           HandlingPhase.MID_CORNER, TransferMode.PLATFORM, Component.DAMPER_BUMP_REAR,
           (Component.SPRINGS_REAR, Component.DAMPER_BUMP_FRONT, Component.RIDE_HEIGHT_REAR),
           ((Component.SPRINGS_REAR, Component.DAMPER_REBOUND_REAR),), role_hint="primary",
           intervention_field="damper_bump_rear"),
        _t("kerb_ride_height", "Ride height / bump-stop contact over the kerb",
           HandlingPhase.MID_CORNER, TransferMode.PLATFORM, Component.RIDE_HEIGHT_REAR,
           (Component.SPRINGS_REAR,), (), role_hint="competing",
           intervention_field="ride_height_rear"),
    ),
    # --- platform: bottoming (only with material evidence) ---------------- #
    "bottoming": (
        _t("bottoming_platform", "Platform bottoming spikes stiffness and destroys aero, "
           "producing abrupt understeer/instability",
           HandlingPhase.HIGH_SPEED_STABILITY, TransferMode.PLATFORM,
           Component.RIDE_HEIGHT_FRONT,
           (Component.RIDE_HEIGHT_REAR, Component.SPRINGS_FRONT),
           ((Component.RIDE_HEIGHT_FRONT, Component.AERO_FRONT),), role_hint="primary",
           intervention_field="ride_height_front"),
    ),
    # --- tyre degradation ------------------------------------------------- #
    "tyre_deg": (
        _t("tyre_alignment_load", "Alignment / load driving tyre degradation (camber, toe "
           "and load transfer shape the contact patch and wear)",
           HandlingPhase.MID_CORNER, TransferMode.LATERAL, Component.TYRES,
           (Component.CAMBER_FRONT, Component.CAMBER_REAR, Component.TOE_REAR),
           ((Component.CAMBER_FRONT, Component.TYRES),), role_hint="primary"),
    ),
    "tyre_wear": (
        _t("tyre_alignment_load", "Alignment / load driving tyre wear",
           HandlingPhase.MID_CORNER, TransferMode.LATERAL, Component.TYRES,
           (Component.CAMBER_FRONT, Component.TOE_FRONT, Component.TOE_REAR),
           ((Component.CAMBER_REAR, Component.TYRES),), role_hint="primary"),
    ),
    # --- fuel efficiency (only when a VD mechanism is genuinely relevant) --- #
    "fuel_use_high": (
        _t("fuel_aero_drag", "Aerodynamic drag raising fuel use (a vehicle-dynamics factor "
           "among many non-VD ones)",
           HandlingPhase.STRAIGHT_LINE_STABILITY, TransferMode.LONGITUDINAL,
           Component.AERO_REAR, (Component.AERO_FRONT, Component.TRANSMISSION), (),
           role_hint="competing"),
    ),
}


def candidates_for(issue_type: str = "", axle: str = "",
                   phase: Optional[HandlingPhase] = None) -> Tuple[MechanismTemplate, ...]:
    """The ordered candidate mechanism templates for a canonical issue type.

    Purely structural: matches on the exact ``issue_type`` string (the Program-1
    vocabulary folded by ``issue_family_for``). ``axle``/``phase`` are available for the
    annotator to refine relevance; the raw template set is issue-type keyed. Unknown
    issue types return an empty tuple (the annotator then reports NOT_EVALUABLE)."""
    key = str(issue_type or "").strip().lower()
    return _TEMPLATES_BY_ISSUE.get(key, ())


def has_mapping(issue_type: str = "") -> bool:
    return str(issue_type or "").strip().lower() in _TEMPLATES_BY_ISSUE


def all_issue_types() -> Tuple[str, ...]:
    return tuple(sorted(_TEMPLATES_BY_ISSUE))
