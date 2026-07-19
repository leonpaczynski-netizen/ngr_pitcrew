"""Deterministic load-transfer knowledge (Engineering Brain Program 2, Phase 12).

Explains the physical mechanisms of weight/load transfer — longitudinal, lateral, combined,
pitch, roll, yaw influence and platform stability — and which setup elements increase or
decrease each. It is explanatory knowledge, not a numeric simulator: relationships are
represented deterministically as contributing factors + directions + mechanism text.

READ-ONLY authority: explains only. It creates no experiment, ranks nothing, and mutates
nothing.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

LOAD_TRANSFER_VERSION = "load_transfer_v1"


class TransferMode(str, Enum):
    LONGITUDINAL = "longitudinal"       # braking/acceleration (front↔rear)
    LATERAL = "lateral"                 # cornering (inside↔outside)
    COMBINED = "combined"               # braking+cornering / power+cornering
    PITCH = "pitch"                     # dive/squat rotation about lateral axis
    ROLL = "roll"                       # body roll about longitudinal axis
    YAW = "yaw"                         # rotation about vertical axis (rotation/stability)
    PLATFORM = "platform"               # ride-height / aero platform stability


@dataclass(frozen=True)
class LoadTransferRelation:
    mode: TransferMode
    mechanism: str
    increased_by: Tuple[str, ...]       # what makes this transfer larger / faster
    decreased_by: Tuple[str, ...]       # what makes it smaller / slower
    balance_effect: str                 # how it shows up in handling
    gt7_note: str

    def to_dict(self) -> dict:
        return {"mode": self.mode.value, "mechanism": self.mechanism,
                "increased_by": list(self.increased_by),
                "decreased_by": list(self.decreased_by),
                "balance_effect": self.balance_effect, "gt7_note": self.gt7_note}


_RELATIONS: Dict[TransferMode, LoadTransferRelation] = {
    TransferMode.LONGITUDINAL: LoadTransferRelation(
        TransferMode.LONGITUDINAL,
        mechanism=(
            "Under braking, load transfers from the rear to the front axle; under acceleration "
            "it transfers rearward. The magnitude is proportional to the centre-of-gravity "
            "height, the deceleration/acceleration and the total mass, divided by the wheelbase."),
        increased_by=("higher centre of gravity", "more total mass / ballast / fuel",
                      "harder braking or acceleration", "longer weight arm (short wheelbase)"),
        decreased_by=("lower centre of gravity", "less mass", "gentler pedal application"),
        balance_effect=(
            "Front-loading under braking gives front grip for entry but unloads the rear "
            "(instability); rear-loading under power gives traction but lightens the front."),
        gt7_note=(
            "GT7 models longitudinal transfer clearly: trail-braking loads the front for "
            "rotation, and too much rear lift under braking is a common entry-instability cause."),
    ),
    TransferMode.LATERAL: LoadTransferRelation(
        TransferMode.LATERAL,
        mechanism=(
            "In a corner, lateral acceleration transfers load from the inside to the outside "
            "tyres. The total is set by CoG height, track width and lateral g; how it SPLITS "
            "front-to-rear is set by the relative front/rear roll stiffness (springs + ARB)."),
        increased_by=("higher centre of gravity", "narrower track", "more lateral grip/speed",
                      "more total mass"),
        decreased_by=("lower centre of gravity", "wider track", "less mass"),
        balance_effect=(
            "The axle taking the larger share of lateral transfer loses relative grip: a stiffer "
            "front pushes (understeer), a stiffer rear loosens (oversteer). This is the core "
            "mechanical-balance lever."),
        gt7_note=(
            "GT7's front/rear ARB and spring split is the most reliable way to move lateral "
            "transfer split and therefore mechanical balance."),
    ),
    TransferMode.COMBINED: LoadTransferRelation(
        TransferMode.COMBINED,
        mechanism=(
            "When braking or accelerating WHILE cornering, longitudinal and lateral transfer "
            "add vectorially, concentrating load on one corner (e.g. the outer-front under "
            "trail-braking). Each tyre's grip is limited by its instantaneous vertical load."),
        increased_by=("simultaneous braking/power and cornering", "high CoG", "more mass"),
        decreased_by=("separating braking from turning", "lower CoG", "smoother inputs"),
        balance_effect=(
            "Overloading one corner saturates that tyre first: trail-braking loads the outer-"
            "front (rotation but front-limited); power-on loads the outer-rear (traction but "
            "oversteer-prone)."),
        gt7_note=(
            "GT7 rewards managing combined load: LSD decel + brake bias shape trail-braking, "
            "LSD accel + rear aero shape power-on combined load."),
    ),
    TransferMode.PITCH: LoadTransferRelation(
        TransferMode.PITCH,
        mechanism=(
            "Pitch is the body's rotation about the lateral axis — dive under braking, squat "
            "under power. It is controlled by front/rear spring rate and damping and is the "
            "transient form of longitudinal load transfer."),
        increased_by=("softer springs", "softer bump/rebound damping", "higher CoG"),
        decreased_by=("stiffer springs", "firmer damping", "lower CoG"),
        balance_effect=(
            "Excess dive over-loads the front and hurts braking stability; excess squat lightens "
            "the front on exit (understeer) while loading the rear (traction)."),
        gt7_note=(
            "In GT7 pitch control via springs/dampers also changes the aero platform, so pitch "
            "and aero balance are coupled more than the numbers suggest."),
    ),
    TransferMode.ROLL: LoadTransferRelation(
        TransferMode.ROLL,
        mechanism=(
            "Roll is the body's rotation about the longitudinal axis in a corner. It is resisted "
            "by springs and — specifically in roll — by the anti-roll bars. The front/rear roll-"
            "stiffness split sets how lateral transfer divides between the axles."),
        increased_by=("softer springs", "softer/absent ARBs", "higher CoG"),
        decreased_by=("stiffer springs", "stiffer ARBs", "lower CoG", "wider track"),
        balance_effect=(
            "More roll stiffness at one end sends more lateral load transfer there and reduces "
            "that end's grip: front-biased roll stiffness → understeer; rear-biased → oversteer."),
        gt7_note=(
            "GT7 ARBs act cleanly in roll only (not pitch/heave), making the ARB ratio the "
            "cleanest roll-balance tool available."),
    ),
    TransferMode.YAW: LoadTransferRelation(
        TransferMode.YAW,
        mechanism=(
            "Yaw is rotation about the vertical axis — the car turning into and out of the "
            "corner. It is driven by the front/rear grip balance and the yaw inertia (polar "
            "moment): rear grip loss or a rearward mass bias increases rotation; front grip loss "
            "or forward bias reduces it."),
        increased_by=("rearward weight bias", "stiffer rear (less rear grip)", "toe-out front",
                      "lower LSD decel (free entry)"),
        decreased_by=("forward weight bias", "stiffer front", "rear toe-in", "more LSD lock",
                      "more rear aero"),
        balance_effect=(
            "Controlled yaw is rotation/agility; excess yaw is oversteer/snap; too little yaw is "
            "understeer. Yaw inertia (mass far from centre) makes rotation slower to start AND "
            "slower to stop."),
        gt7_note=(
            "GT7 mid-engine and low-polar-moment cars rotate eagerly; managing yaw with rear toe, "
            "LSD and aero is central to a stable GT7 setup."),
    ),
    TransferMode.PLATFORM: LoadTransferRelation(
        TransferMode.PLATFORM,
        mechanism=(
            "Platform stability is how steadily the sprung mass — and therefore the aero floor "
            "and ride height — is held through load changes. It is a product of spring rate, "
            "damping and ride height working together to keep the aero platform in its window."),
        increased_by=("stiffer springs", "well-matched damping", "adequate ride height",
                      "small positive rake"),
        decreased_by=("too-soft springs (platform bobs)", "too-low ride height (bottoming)",
                      "mismatched damping"),
        balance_effect=(
            "An unstable platform makes aero grip come and go, producing inconsistent balance; a "
            "stable platform makes the car predictable, especially at high speed."),
        gt7_note=(
            "GT7 is unusually platform-sensitive: bottoming spikes stiffness and grip abruptly, "
            "so ride-height/spring choices that keep the platform off the bump stops matter a lot."),
    ),
}


def all_modes() -> Tuple[TransferMode, ...]:
    return tuple(_RELATIONS)


def explain_transfer(mode) -> Optional[LoadTransferRelation]:
    """Return the deterministic knowledge for a transfer mode, or None."""
    try:
        m = mode if isinstance(mode, TransferMode) else TransferMode(str(mode))
    except (ValueError, TypeError):
        return None
    return _RELATIONS.get(m)


def build_load_transfer_report() -> dict:
    """The full load-transfer knowledge. Deterministic + regenerable."""
    modes = [_RELATIONS[m].to_dict() for m in TransferMode if m in _RELATIONS]
    payload = {"v": LOAD_TRANSFER_VERSION, "modes": modes}
    fp = (f"{LOAD_TRANSFER_VERSION}:"
          + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()[:24])
    return {"ok": True, "version": LOAD_TRANSFER_VERSION, "modes": modes,
            "content_fingerprint": fp}
