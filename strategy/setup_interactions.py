"""Deterministic setup-interaction knowledge (Engineering Brain Program 2, Phase 12).

Explains the physical INTERACTIONS between setup elements — spring↔damper, damper↔ARB,
ride-height↔aero, camber↔tyre, toe↔stability, and the differential↔suspension couplings —
plus the detailed LSD and aero interaction models. It composes the component knowledge in
`vehicle_dynamics`; it defines no new sign data and makes no decisions.

READ-ONLY authority: explains only. It ranks nothing, recommends nothing, mutates nothing.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

from strategy.vehicle_dynamics import Component

SETUP_INTERACTIONS_VERSION = "setup_interactions_v1"


class InteractionType(str, Enum):
    REINFORCING = "reinforcing"         # the two amplify each other's effect
    OPPOSING = "opposing"               # they counteract each other
    ENABLING = "enabling"               # one only works if the other is set right
    LIMITING = "limiting"               # one caps or gates the other's usefulness


@dataclass(frozen=True)
class ComponentInteraction:
    a: Component
    b: Component
    interaction_type: InteractionType
    mechanism: str
    gt7_note: str

    def key(self) -> Tuple[str, str]:
        return tuple(sorted((self.a.value, self.b.value)))

    def to_dict(self) -> dict:
        return {"a": self.a.value, "b": self.b.value,
                "interaction_type": self.interaction_type.value,
                "mechanism": self.mechanism, "gt7_note": self.gt7_note}


_INTERACTIONS: Tuple[ComponentInteraction, ...] = (
    # spring ↔ damper: the spring sets how much, the damper sets how fast.
    ComponentInteraction(
        Component.SPRINGS_FRONT, Component.DAMPER_BUMP_FRONT, InteractionType.ENABLING,
        mechanism=(
            "The front spring sets the steady-state front load; the front bump damper only "
            "controls the RATE at which that load builds. A damper change is meaningful only "
            "relative to its spring — the same damper feels different on a stiffer spring."),
        gt7_note="GT7's coarse damper model means damper tuning matters most as a ratio to the spring."),
    ComponentInteraction(
        Component.SPRINGS_REAR, Component.DAMPER_REBOUND_REAR, InteractionType.ENABLING,
        mechanism=(
            "The rear spring sets squat resistance; the rear rebound damper controls how the "
            "rear returns after squat. Together they set exit platform behaviour; a soft spring "
            "with high rebound holds the rear down, then releases it."),
        gt7_note="GT7 exit instability often traces to rear rebound set outside its stable range for the rear spring."),
    # damper ↔ ARB: both resist roll transient, but ARB only in roll.
    ComponentInteraction(
        Component.DAMPER_BUMP_FRONT, Component.ARB_FRONT, InteractionType.REINFORCING,
        mechanism=(
            "During turn-in both the front bump damper and the front ARB resist the transient "
            "roll/compression at the front. They stack: a stiff ARB plus stiff bump damping makes "
            "turn-in very sharp but harsh, and over-loads the outer-front quickly."),
        gt7_note="In GT7 stacking stiff front ARB and bump damping can make turn-in nervous over bumps."),
    # ride height ↔ aero: rake and platform set aero balance and floor effect.
    ComponentInteraction(
        Component.RIDE_HEIGHT_FRONT, Component.AERO_FRONT, InteractionType.ENABLING,
        mechanism=(
            "Front downforce depends on the front platform height: front aero only delivers its "
            "grip if the front ride height keeps the floor in its working window. Lowering the "
            "front raises aero effect until bottoming, which then destroys it."),
        gt7_note="GT7 front aero is strongly ride-height gated — too high a front and the wing under-delivers."),
    ComponentInteraction(
        Component.RIDE_HEIGHT_REAR, Component.AERO_REAR, InteractionType.ENABLING,
        mechanism=(
            "Rear ride height sets rake, which couples directly to rear aero balance and floor "
            "behaviour. A small positive rake enhances the floor; too low a rear reduces platform "
            "stability and the effective rear aero."),
        gt7_note="GT7 rewards a small positive rake; changing rear ride height re-balances aero more than the wing number implies."),
    # camber ↔ tyre: camber shapes the contact patch and wear.
    ComponentInteraction(
        Component.CAMBER_FRONT, Component.TYRES, InteractionType.LIMITING,
        mechanism=(
            "Front camber optimises the tyre contact patch in roll but concentrates load on the "
            "inner shoulder in a straight line. Too much camber for the tyre raises inner-edge "
            "temperature and wear and reduces braking grip — the tyre limits usable camber."),
        gt7_note="GT7's milder camber model tolerates more camber than real life but still adds inner-shoulder wear."),
    ComponentInteraction(
        Component.CAMBER_REAR, Component.TYRES, InteractionType.LIMITING,
        mechanism=(
            "Rear camber trades cornering contact against straight-line traction contact; the "
            "tyre's temperature spread and wear cap how much rear camber is useful before "
            "traction and life suffer."),
        gt7_note="GT7 rear camber beyond a modest range slightly hurts exit traction and adds wear."),
    # toe ↔ stability
    ComponentInteraction(
        Component.TOE_REAR, Component.LSD_ACCEL, InteractionType.REINFORCING,
        mechanism=(
            "Rear toe-in and LSD accel lock both stabilise the rear under power: toe-in keeps the "
            "axle pointing forward while the diff ties the wheels together. Together they add "
            "strong exit stability but can also add corner-exit understeer if both are high."),
        gt7_note="GT7 exit stability from rear toe-in + LSD accel is effective but stacks into understeer and tyre wear."),
    ComponentInteraction(
        Component.TOE_FRONT, Component.ARB_FRONT, InteractionType.REINFORCING,
        mechanism=(
            "Front toe-out and a softer front ARB both increase turn-in response and initial "
            "rotation; combined they sharpen entry but reduce straight-line stability and can "
            "make the front nervous over bumps."),
        gt7_note="GT7 aggressive front toe-out plus soft front ARB gives eager turn-in at a tyre-wear cost."),
    # differential ↔ suspension
    ComponentInteraction(
        Component.LSD_ACCEL, Component.SPRINGS_REAR, InteractionType.ENABLING,
        mechanism=(
            "The LSD can only put down the torque the rear tyres can hold; the rear spring sets "
            "how the rear is loaded on exit. A soft rear that squats and loads the tyres lets a "
            "given LSD lock find more traction; a stiff rear needs less lock."),
        gt7_note="In GT7 a compliant rear spring plus moderate LSD accel usually out-tractions a stiff rear with high lock."),
    ComponentInteraction(
        Component.LSD_DECEL, Component.BRAKE_BIAS, InteractionType.REINFORCING,
        mechanism=(
            "Under trail-braking, LSD decel lock and brake bias jointly set rear stability: more "
            "decel lock and a more forward bias both settle the rear on entry, while a rearward "
            "bias with low decel lock frees — or snaps — the rear."),
        gt7_note="GT7 entry stability is best tuned by LSD decel first, then brake bias, in that order."),
    ComponentInteraction(
        Component.ARB_REAR, Component.LSD_ACCEL, InteractionType.OPPOSING,
        mechanism=(
            "A stiffer rear ARB reduces rear grip (adding rotation), while more LSD accel lock "
            "adds exit stability. They pull exit balance in opposite directions, so they are "
            "often traded against each other to tune power-on rotation."),
        gt7_note="GT7 power-on balance is frequently dialled with the rear ARB vs LSD accel trade."),
)


# --------------------------------------------------------------------------- #
# Detailed differential (LSD) interaction model
# --------------------------------------------------------------------------- #
_LSD_MODEL: Tuple[dict, ...] = (
    {"parameter": "initial_torque", "phase": "corner entry / apex (neutral throttle)",
     "mechanism": "Preload sets the always-on baseline lock; it governs how the diff behaves "
                  "around neutral throttle, trading apex stability for low-throttle agility.",
     "gt7_note": "GT7 preload is subtle vs the ramps; very high preload feels locked and reluctant to rotate."},
    {"parameter": "acceleration_locking", "phase": "corner exit (on throttle)",
     "mechanism": "Accel ramp sets how hard the diff locks under power, tying the rear wheels "
                  "for traction; too much causes exit understeer and inside-wheel scrub.",
     "gt7_note": "GT7 exit wheelspin is cured with accel lock; over-locking then scrubs the fronts."},
    {"parameter": "deceleration_locking", "phase": "corner entry / trail-braking (off throttle)",
     "mechanism": "Decel ramp sets how hard the diff locks off-throttle, stabilising the rear on "
                  "entry; too little frees the rear into lift-off oversteer.",
     "gt7_note": "GT7 lift-off/trail-braking snap is the classic symptom of too little decel lock."},
)

# --------------------------------------------------------------------------- #
# Detailed aerodynamic model
# --------------------------------------------------------------------------- #
_AERO_MODEL: Tuple[dict, ...] = (
    {"aspect": "front_balance", "mechanism": "Front downforce adds front grip that grows with "
     "speed, sharpening high-speed turn-in and apex support; it does little in slow corners.",
     "gt7_note": "GT7 front aero is ride-height gated and speed-dependent."},
    {"aspect": "rear_balance", "mechanism": "Rear downforce adds rear grip that grows with speed, "
     "improving high-speed traction and stability; it costs drag and top speed.",
     "gt7_note": "GT7 rear aero drag penalty on long straights is significant."},
    {"aspect": "ride_height_sensitivity", "mechanism": "Aero effectiveness depends on the "
     "platform height and rake; too low bottoms and destroys downforce, too high under-delivers.",
     "gt7_note": "GT7 is strongly ride-height sensitive — the platform window is narrow."},
    {"aspect": "platform_dependence", "mechanism": "Aero grip is only as steady as the sprung "
     "platform; spring/damper/ride-height must keep the floor in its window for consistent aero.",
     "gt7_note": "GT7 platform bobbing or bottoming makes aero grip come and go."},
    {"aspect": "high_speed_behaviour", "mechanism": "As speed rises, aero load dominates over "
     "mechanical grip, so aero balance increasingly sets high-speed handling balance.",
     "gt7_note": "GT7 high-speed balance is aero-led; low-speed balance is mechanical-led."},
)


def all_interactions() -> Tuple[ComponentInteraction, ...]:
    return _INTERACTIONS


def interactions_for(component) -> Tuple[ComponentInteraction, ...]:
    """Every interaction that involves ``component``. Deterministic order."""
    try:
        comp = component if isinstance(component, Component) else Component(str(component))
    except (ValueError, TypeError):
        return ()
    return tuple(i for i in _INTERACTIONS if i.a == comp or i.b == comp)


def explain_interaction(a, b) -> Optional[ComponentInteraction]:
    """The interaction between two components (order-independent), or None."""
    try:
        ca = a if isinstance(a, Component) else Component(str(a))
        cb = b if isinstance(b, Component) else Component(str(b))
    except (ValueError, TypeError):
        return None
    want = tuple(sorted((ca.value, cb.value)))
    for i in _INTERACTIONS:
        if i.key() == want:
            return i
    return None


def lsd_model() -> Tuple[dict, ...]:
    return _LSD_MODEL


def aero_model() -> Tuple[dict, ...]:
    return _AERO_MODEL


def build_interactions_report() -> dict:
    """The full interaction knowledge (pairwise + LSD + aero models). Deterministic +
    regenerable."""
    interactions = [i.to_dict() for i in _INTERACTIONS]
    payload = {"v": SETUP_INTERACTIONS_VERSION, "interactions": interactions,
               "lsd_model": list(_LSD_MODEL), "aero_model": list(_AERO_MODEL)}
    fp = (f"{SETUP_INTERACTIONS_VERSION}:"
          + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()[:24])
    return {"ok": True, "version": SETUP_INTERACTIONS_VERSION,
            "interactions": interactions, "lsd_model": list(_LSD_MODEL),
            "aero_model": list(_AERO_MODEL), "content_fingerprint": fp}
