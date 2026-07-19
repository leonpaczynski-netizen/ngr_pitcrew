"""Deterministic handling-balance knowledge (Engineering Brain Program 2, Phase 12).

Explains the dominant physical mechanisms in each phase of a corner — corner entry, trail
braking, initial rotation, mid-corner balance, exit traction, power-on rotation, straight-
line stability and high-speed stability — and which setup elements and load-transfer modes
govern each. It composes the component knowledge (`vehicle_dynamics`) and the load-transfer
knowledge (`load_transfer`); it defines no new sign data.

READ-ONLY authority: explains only. It ranks nothing, recommends nothing, mutates nothing.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

from strategy.load_transfer import TransferMode
from strategy.vehicle_dynamics import Component, explain_component

HANDLING_BALANCE_VERSION = "handling_balance_v1"


class HandlingPhase(str, Enum):
    CORNER_ENTRY = "corner_entry"
    TRAIL_BRAKING = "trail_braking"
    INITIAL_ROTATION = "initial_rotation"
    MID_CORNER = "mid_corner"
    EXIT_TRACTION = "exit_traction"
    POWER_ON_ROTATION = "power_on_rotation"
    STRAIGHT_LINE_STABILITY = "straight_line_stability"
    HIGH_SPEED_STABILITY = "high_speed_stability"


@dataclass(frozen=True)
class PhaseExplanation:
    phase: HandlingPhase
    dominant_mechanism: str
    key_components: Tuple[Component, ...]   # the components that most govern this phase
    load_transfer_modes: Tuple[TransferMode, ...]
    understeer_if: str                      # what tends to CAUSE understeer here
    oversteer_if: str                       # what tends to CAUSE oversteer here
    gt7_note: str

    def to_dict(self) -> dict:
        return {"phase": self.phase.value, "dominant_mechanism": self.dominant_mechanism,
                "key_components": [c.value for c in self.key_components],
                "load_transfer_modes": [m.value for m in self.load_transfer_modes],
                "understeer_if": self.understeer_if, "oversteer_if": self.oversteer_if,
                "gt7_note": self.gt7_note}


_PHASES: Dict[HandlingPhase, PhaseExplanation] = {
    HandlingPhase.CORNER_ENTRY: PhaseExplanation(
        HandlingPhase.CORNER_ENTRY,
        dominant_mechanism=(
            "On entry the car is braking and beginning to turn: longitudinal transfer loads the "
            "front for grip while the rear lightens. Front geometry and brake balance decide how "
            "willingly the car takes the initial steer."),
        key_components=(Component.BRAKE_BIAS, Component.TOE_FRONT, Component.LSD_DECEL,
                        Component.ARB_FRONT),
        load_transfer_modes=(TransferMode.LONGITUDINAL, TransferMode.COMBINED),
        understeer_if="front bias too forward, front toe-in, stiff front, front pushing under braking.",
        oversteer_if="brake bias too rearward, low LSD decel, rear too light under braking.",
        gt7_note="GT7 entry snap is most often cured by adding LSD decel lock and/or a touch of rear toe-in."),

    HandlingPhase.TRAIL_BRAKING: PhaseExplanation(
        HandlingPhase.TRAIL_BRAKING,
        dominant_mechanism=(
            "Trailing the brake into the corner keeps combined load on the outer-front tyre, "
            "using front grip to rotate the car. Stability depends on how much the rear is "
            "tied down as it unloads."),
        key_components=(Component.BRAKE_BIAS, Component.LSD_DECEL, Component.DAMPER_REBOUND_REAR,
                        Component.TOE_REAR),
        load_transfer_modes=(TransferMode.COMBINED, TransferMode.LONGITUDINAL, TransferMode.YAW),
        understeer_if="too much forward brake bias or LSD decel over-stabilising the rear.",
        oversteer_if="rear unloads faster than the diff/toe can control it (snap on the brakes).",
        gt7_note="GT7 trail-braking stability is dominated by LSD decel; too little is the classic GT7 lift-off snap."),

    HandlingPhase.INITIAL_ROTATION: PhaseExplanation(
        HandlingPhase.INITIAL_ROTATION,
        dominant_mechanism=(
            "Initial rotation is how quickly the car yaws to the apex once turned in. It is set "
            "by front grip relative to rear grip and by yaw inertia: free the front or load the "
            "rear and the car rotates."),
        key_components=(Component.TOE_FRONT, Component.ARB_REAR, Component.AERO_FRONT,
                        Component.LSD_INITIAL),
        load_transfer_modes=(TransferMode.YAW, TransferMode.LATERAL),
        understeer_if="stiff front / soft rear, high LSD preload, forward weight bias, low front aero.",
        oversteer_if="stiff rear / soft front, low LSD preload, rearward weight bias.",
        gt7_note="GT7 low-polar-moment cars rotate eagerly; over-freeing the front here causes mid-corner snap."),

    HandlingPhase.MID_CORNER: PhaseExplanation(
        HandlingPhase.MID_CORNER,
        dominant_mechanism=(
            "At the apex the car is in steady lateral load transfer with little braking or "
            "power. Balance is set by the front/rear roll-stiffness split and the steady-state "
            "grip of each axle."),
        key_components=(Component.ARB_FRONT, Component.ARB_REAR, Component.SPRINGS_FRONT,
                        Component.CAMBER_FRONT),
        load_transfer_modes=(TransferMode.LATERAL, TransferMode.ROLL),
        understeer_if="front-biased roll stiffness (stiff front ARB/spring) taking more lateral transfer.",
        oversteer_if="rear-biased roll stiffness taking more lateral transfer.",
        gt7_note="GT7 mid-corner balance responds cleanly to the ARB ratio — the primary balance tool."),

    HandlingPhase.EXIT_TRACTION: PhaseExplanation(
        HandlingPhase.EXIT_TRACTION,
        dominant_mechanism=(
            "On exit, power transfers load rearward and the rear tyres must convert torque to "
            "drive. Traction depends on how evenly the diff shares torque and how well the rear "
            "platform and tyres are loaded."),
        key_components=(Component.LSD_ACCEL, Component.SPRINGS_REAR, Component.AERO_REAR,
                        Component.CAMBER_REAR),
        load_transfer_modes=(TransferMode.LONGITUDINAL, TransferMode.COMBINED),
        understeer_if="excessive LSD accel lock scrubbing the fronts (corner-exit understeer).",
        oversteer_if="too little LSD lock / soft rear letting the inside wheel spin (wheelspin).",
        gt7_note="GT7 exit wheelspin is usually LSD-accel or gearing; over-locking then causes exit understeer."),

    HandlingPhase.POWER_ON_ROTATION: PhaseExplanation(
        HandlingPhase.POWER_ON_ROTATION,
        dominant_mechanism=(
            "Applying power while still turning can rotate the car further (throttle-on yaw) as "
            "the rear approaches its combined-grip limit. How much it rotates versus grips is set "
            "by LSD accel, rear grip and aero."),
        key_components=(Component.LSD_ACCEL, Component.ARB_REAR, Component.AERO_REAR,
                        Component.TOE_REAR),
        load_transfer_modes=(TransferMode.COMBINED, TransferMode.YAW),
        understeer_if="high LSD accel lock and high rear grip resisting rotation (safe but slow).",
        oversteer_if="low rear grip / low aero letting the rear step out under power.",
        gt7_note="GT7 rear ARB + LSD accel together decide power-on rotation; the combination can snap if both are aggressive."),

    HandlingPhase.STRAIGHT_LINE_STABILITY: PhaseExplanation(
        HandlingPhase.STRAIGHT_LINE_STABILITY,
        dominant_mechanism=(
            "In a straight line the car should track true under braking and acceleration. "
            "Stability comes from rear toe-in, forward-enough weight bias and consistent braking "
            "balance keeping the rear settled."),
        key_components=(Component.TOE_REAR, Component.BRAKE_BIAS, Component.WEIGHT_DISTRIBUTION,
                        Component.LSD_DECEL),
        load_transfer_modes=(TransferMode.LONGITUDINAL,),
        understeer_if="not applicable in a straight line (this is about directional stability).",
        oversteer_if="rear toe-out or rearward brake bias making the rear wander/lock under braking.",
        gt7_note="GT7 straight-line stability under braking is helped by rear toe-in and a slightly forward brake bias."),

    HandlingPhase.HIGH_SPEED_STABILITY: PhaseExplanation(
        HandlingPhase.HIGH_SPEED_STABILITY,
        dominant_mechanism=(
            "At high speed aerodynamic load dominates and the platform must stay stable. Rear "
            "downforce, a stable ride-height/spring platform and rear toe-in keep the car planted "
            "as aero grip rises with speed."),
        key_components=(Component.AERO_REAR, Component.RIDE_HEIGHT_REAR, Component.SPRINGS_REAR,
                        Component.TOE_REAR),
        load_transfer_modes=(TransferMode.PLATFORM, TransferMode.LATERAL),
        understeer_if="front aero too low relative to rear (front washes out at speed).",
        oversteer_if="rear aero too low or platform unstable (rear light/nervous at speed).",
        gt7_note="GT7 high-speed nervousness is often a platform/bottoming issue as much as an aero-balance one."),
}


def all_phases() -> Tuple[HandlingPhase, ...]:
    return tuple(_PHASES)


def explain_phase(phase) -> Optional[PhaseExplanation]:
    """Return the deterministic knowledge for a handling phase, or None."""
    try:
        p = phase if isinstance(phase, HandlingPhase) else HandlingPhase(str(phase))
    except (ValueError, TypeError):
        return None
    return _PHASES.get(p)


def phase_components(phase) -> Tuple[dict, ...]:
    """The key components of a phase with their component-level explanations attached."""
    exp = explain_phase(phase)
    if exp is None:
        return ()
    out = []
    for c in exp.key_components:
        ce = explain_component(c)
        if ce is not None:
            out.append({"component": c.value, "primary_mechanism": ce.primary_mechanism})
    return tuple(out)


def build_handling_report() -> dict:
    """The full handling-balance knowledge across all phases. Deterministic + regenerable."""
    phases = [_PHASES[p].to_dict() for p in HandlingPhase if p in _PHASES]
    payload = {"v": HANDLING_BALANCE_VERSION, "phases": phases}
    fp = (f"{HANDLING_BALANCE_VERSION}:"
          + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()[:24])
    return {"ok": True, "version": HANDLING_BALANCE_VERSION, "phases": phases,
            "content_fingerprint": fp}
