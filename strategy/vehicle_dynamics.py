"""Deterministic Vehicle Dynamics Knowledge Engine (Engineering Brain Program 2, Phase 12).

A NEW read-only authority that explains the PHYSICAL MECHANISM behind each setup element —
"what physical mechanism is creating this behaviour?" — as a curated, deterministic
knowledge base. It is NOT a replacement for Program 1: it adds an explanatory authority.

It NEVER creates experiments, ranks candidates, changes outcomes/evidence/memory/working
windows, or authors setup values. It only explains deterministic engineering relationships.

The DIRECTIONAL sign graph is owned by Program 1 (`setup_synthesis.PARAMETER_INTERACTIONS`);
this engine CONSUMES it (never duplicates the signs) and layers the mechanism + GT7-specific
knowledge on top. GT7-specific behaviour is modelled separately from generic race-car theory.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no ML, no statistics, no black-box
scoring; deterministic; never raises; no random, no wall-clock.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Mapping, Optional, Sequence, Tuple

from strategy.setup_synthesis import PARAMETER_INTERACTIONS

VEHICLE_DYNAMICS_VERSION = "vehicle_dynamics_v1"


class ComponentGroup(str, Enum):
    SUSPENSION = "suspension"
    DIFFERENTIAL = "differential"
    AERO = "aero"
    TYRES = "tyres"
    BRAKES = "brakes"
    TRANSMISSION = "transmission"
    WEIGHT_TRANSFER = "weight_transfer"
    ALIGNMENT = "alignment"


class Component(str, Enum):
    # suspension
    SPRINGS_FRONT = "springs_front"
    SPRINGS_REAR = "springs_rear"
    DAMPER_BUMP_FRONT = "damper_bump_front"
    DAMPER_BUMP_REAR = "damper_bump_rear"
    DAMPER_REBOUND_FRONT = "damper_rebound_front"
    DAMPER_REBOUND_REAR = "damper_rebound_rear"
    ARB_FRONT = "arb_front"
    ARB_REAR = "arb_rear"
    RIDE_HEIGHT_FRONT = "ride_height_front"
    RIDE_HEIGHT_REAR = "ride_height_rear"
    # alignment
    CAMBER_FRONT = "camber_front"
    CAMBER_REAR = "camber_rear"
    TOE_FRONT = "toe_front"
    TOE_REAR = "toe_rear"
    # brakes
    BRAKE_BIAS = "brake_bias"
    # differential
    LSD_INITIAL = "lsd_initial"
    LSD_ACCEL = "lsd_accel"
    LSD_DECEL = "lsd_decel"
    # aero
    AERO_FRONT = "aero_front"
    AERO_REAR = "aero_rear"
    # weight transfer / mass
    BALLAST = "ballast"
    WEIGHT_DISTRIBUTION = "weight_distribution"
    FUEL_LOAD = "fuel_load"
    # transmission
    TRANSMISSION = "transmission"
    # tyres
    TYRES = "tyres"


# Canonical Program-1 handling axes (the only sign vocabulary that overlaps the graph).
CANONICAL_AXES = frozenset({
    "entry_rotation", "apex_front_support", "high_speed_stability",
    "power_oversteer_resistance", "exit_traction", "fuel_efficiency",
    "tyre_preservation", "trail_braking_stability", "kerb_compliance",
})


@dataclass(frozen=True)
class EngineeringExplanation:
    """The deterministic mechanism knowledge for ONE component."""

    component: Component
    group: ComponentGroup
    primary_mechanism: str
    secondary_interactions: Tuple[str, ...]
    gt7_limitations: Tuple[str, ...]
    raise_effect: str                   # what RAISING the value does
    lower_effect: str                   # what LOWERING the value does
    # directional axes affected by RAISING the value: {axis: +1/-1}
    axis_effects: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self):
        # Robustly coerce the text-tuple fields: a single sentence written without a
        # trailing comma parses as a str; normalise it to a 1-tuple so callers always
        # receive an iterable of statements (never a char-iterable).
        for name in ("secondary_interactions", "gt7_limitations"):
            v = getattr(self, name)
            if isinstance(v, str):
                object.__setattr__(self, name, (v,))
            elif not isinstance(v, tuple):
                object.__setattr__(self, name, tuple(v or ()))

    def to_dict(self) -> dict:
        return {
            "component": self.component.value, "group": self.group.value,
            "primary_mechanism": self.primary_mechanism,
            "secondary_interactions": list(self.secondary_interactions),
            "gt7_limitations": list(self.gt7_limitations),
            "raise_effect": self.raise_effect, "lower_effect": self.lower_effect,
            "axis_effects": dict(self.axis_effects),
        }


def _axes(field_name: str, extra: Optional[Mapping[str, int]] = None) -> dict:
    """Directional axes for a component: the Program-1 sign graph (when the component is a
    tunable field there) merged with any authored extra axes. Never duplicates the signs —
    it reads them from the single source of truth."""
    out = dict(PARAMETER_INTERACTIONS.get(field_name, {}) or {})
    if extra:
        out.update(extra)
    return out


# --------------------------------------------------------------------------- #
# The curated deterministic knowledge base
# --------------------------------------------------------------------------- #
_KNOWLEDGE: Dict[Component, EngineeringExplanation] = {
    Component.SPRINGS_FRONT: EngineeringExplanation(
        Component.SPRINGS_FRONT, ComponentGroup.SUSPENSION,
        primary_mechanism=(
            "Front spring rate sets how much the front axle compresses under load; a "
            "stiffer front spring resists dive and roll, moving lateral load transfer "
            "forward faster and supporting the front tyres at the apex."),
        secondary_interactions=(
            "Works with front dampers to control the rate of front load build-up.",
            "Trades against front ride height / bump-stop contact and kerb compliance.",
            "Stiffer front vs softer rear moves balance toward understeer."),
        gt7_limitations=(
            "GT7 spring travel is limited; very stiff front springs reach the bump stop and "
            "produce abrupt bottoming rather than a progressive rise in rate."),
        raise_effect="quicker, firmer front support; less dive/roll; more mid-corner understeer risk.",
        lower_effect="more front compliance and mechanical grip; more dive; slower front response.",
        axis_effects=_axes("springs_front")),

    Component.SPRINGS_REAR: EngineeringExplanation(
        Component.SPRINGS_REAR, ComponentGroup.SUSPENSION,
        primary_mechanism=(
            "Rear spring rate controls rear-axle compression and squat under power; a stiffer "
            "rear spring resists squat and roll, shifting lateral load transfer rearward and "
            "reducing rear mechanical grip on exit."),
        secondary_interactions=(
            "Works with rear dampers to control squat rate on throttle application.",
            "Stiffer rear vs softer front moves balance toward oversteer.",
            "Interacts with rear ride height and aero platform under load."),
        gt7_limitations=(
            "GT7 rewards a compliant rear over kerbs; over-stiff rear springs cause the rear to "
            "skip and lose traction on exit more than a real car would."),
        raise_effect="firmer rear platform; less squat; more power-on rotation / exit oversteer risk.",
        lower_effect="more rear mechanical grip and traction; more squat; softer rear response.",
        axis_effects=_axes("springs_rear")),

    Component.DAMPER_BUMP_FRONT: EngineeringExplanation(
        Component.DAMPER_BUMP_FRONT, ComponentGroup.SUSPENSION,
        primary_mechanism=(
            "Front bump (compression) damping controls the RATE at which the front loads on "
            "corner entry and braking — it shapes the transient, not the steady-state load."),
        secondary_interactions=(
            "Pairs with the front spring: the spring sets how much, the damper sets how fast.",
            "Too much front bump makes turn-in sharp but harsh over bumps and kerbs."),
        gt7_limitations=(
            "GT7's damper model is simplified; extreme bump values mostly affect transient feel "
            "and kerb behaviour rather than fine platform control."),
        raise_effect="slower front compression; more stable but less responsive turn-in transient.",
        lower_effect="faster front load build; sharper turn-in; more nervous over bumps.",
        axis_effects={"trail_braking_stability": +1, "kerb_compliance": -1}),

    Component.DAMPER_REBOUND_FRONT: EngineeringExplanation(
        Component.DAMPER_REBOUND_FRONT, ComponentGroup.SUSPENSION,
        primary_mechanism=(
            "Front rebound (extension) damping controls how fast the front returns after "
            "compression — it governs front platform recovery off kerbs and mid-corner."),
        secondary_interactions=(
            "Too much front rebound holds the nose down, keeping front load and adding "
            "mid-corner understeer resistance but reducing compliance."),
        gt7_limitations=(
            "GT7 rebound has a coarse effect; very high rebound can make the front feel 'stuck "
            "down' and unsettle the car over successive bumps."),
        raise_effect="front recovers slowly; nose stays loaded; steadier but less compliant.",
        lower_effect="front recovers quickly; more compliance; less mid-corner front hold.",
        axis_effects={"apex_front_support": +1, "kerb_compliance": -1}),

    Component.DAMPER_BUMP_REAR: EngineeringExplanation(
        Component.DAMPER_BUMP_REAR, ComponentGroup.SUSPENSION,
        primary_mechanism=(
            "Rear bump damping controls the rate of rear compression under squat and over "
            "kerbs; it shapes how progressively the rear takes up load on throttle."),
        secondary_interactions=(
            "Pairs with the rear spring for squat control.",
            "Too much rear bump makes the rear skip over kerbs and lose traction."),
        gt7_limitations=(
            "GT7 rear bump primarily changes kerb behaviour and transient traction rather than "
            "steady platform control."),
        raise_effect="slower rear compression; firmer transient; more kerb skip risk.",
        lower_effect="more rear compliance and traction over bumps; softer transient.",
        axis_effects={"exit_traction": -1, "kerb_compliance": -1}),

    Component.DAMPER_REBOUND_REAR: EngineeringExplanation(
        Component.DAMPER_REBOUND_REAR, ComponentGroup.SUSPENSION,
        primary_mechanism=(
            "Rear rebound damping controls how fast the rear extends after compression — it "
            "governs rear platform recovery and stability on corner exit."),
        secondary_interactions=(
            "Too much rear rebound holds the rear squatted, which can help traction briefly but "
            "then unloads sharply, hurting stability.",
            "Interacts strongly with the rear spring and rear ARB for exit balance."),
        gt7_limitations=(
            "In GT7, lowering rear rebound below its stable range is a common cause of exit "
            "instability — a well-known GT7-specific pitfall."),
        raise_effect="rear recovers slowly; can hold traction then unload; steadier if within range.",
        lower_effect="rear recovers quickly; more compliance but a known GT7 exit-instability risk.",
        axis_effects={"exit_traction": +1, "power_oversteer_resistance": +1}),

    Component.ARB_FRONT: EngineeringExplanation(
        Component.ARB_FRONT, ComponentGroup.SUSPENSION,
        primary_mechanism=(
            "The front anti-roll bar couples the two front wheels in roll, increasing front "
            "roll stiffness. A stiffer front bar takes a larger share of lateral load transfer "
            "at the front, reducing front grip and adding understeer."),
        secondary_interactions=(
            "Front-vs-rear ARB ratio is the primary mechanical-balance lever.",
            "Complements spring stiffness but only in roll (not in pitch/heave)."),
        gt7_limitations=(
            "GT7 ARBs are effective and predictable; the front/rear balance shift is the most "
            "reliable mechanical-balance adjustment in the game."),
        raise_effect="more front roll stiffness; more mid-corner understeer; sharper high-speed stability.",
        lower_effect="less front roll stiffness; more front grip and rotation; softer response.",
        axis_effects=_axes("arb_front")),

    Component.ARB_REAR: EngineeringExplanation(
        Component.ARB_REAR, ComponentGroup.SUSPENSION,
        primary_mechanism=(
            "The rear anti-roll bar increases rear roll stiffness; a stiffer rear bar takes more "
            "lateral load transfer at the rear, reducing rear grip and adding entry rotation and "
            "power-on oversteer."),
        secondary_interactions=(
            "Front-vs-rear ARB ratio sets mechanical balance.",
            "Interacts with LSD and rear springs for exit-traction behaviour."),
        gt7_limitations=(
            "A too-stiff rear ARB in GT7 combines with the LSD to produce snap power-oversteer "
            "on corner exit more readily than in a real car."),
        raise_effect="more rear roll stiffness; more entry rotation and exit-oversteer risk.",
        lower_effect="more rear grip and stability; less rotation; more understeer.",
        axis_effects=_axes("arb_rear")),

    Component.RIDE_HEIGHT_FRONT: EngineeringExplanation(
        Component.RIDE_HEIGHT_FRONT, ComponentGroup.SUSPENSION,
        primary_mechanism=(
            "Front ride height sets the front of the aero platform and the front roll-centre "
            "height. Lower front ride height increases front downforce and lowers the front "
            "roll centre, generally sharpening front response."),
        secondary_interactions=(
            "Front-vs-rear ride-height rake couples directly to aero balance.",
            "Interacts with front springs / bump stops for bottoming."),
        gt7_limitations=(
            "GT7 is highly ride-height sensitive: too low a front triggers bottoming that spikes "
            "stiffness and causes sudden understeer or instability — a key GT7 limitation."),
        raise_effect="raises the front platform; less front aero; more front ride but less response.",
        lower_effect="lowers the front platform; more front aero and rake effect; bottoming risk.",
        axis_effects=_axes("ride_height_front")),

    Component.RIDE_HEIGHT_REAR: EngineeringExplanation(
        Component.RIDE_HEIGHT_REAR, ComponentGroup.SUSPENSION,
        primary_mechanism=(
            "Rear ride height sets the rear platform and rake. Lowering the rear reduces rake, "
            "shifting aero balance rearward-to-forward and lowering the rear roll centre; it "
            "changes high-speed stability and platform behaviour."),
        secondary_interactions=(
            "Rake (front-vs-rear ride height) is the dominant aero-balance mechanism.",
            "Couples with rear springs and diffuser platform behaviour."),
        gt7_limitations=(
            "GT7 rewards a small positive rake; too low a rear ride height reduces rear platform "
            "stability and can make the car nervous at high speed."),
        raise_effect="raises the rear; more rake; more rear aero bias; can add high-speed stability.",
        lower_effect="lowers the rear; less rake; shifts balance forward; less high-speed stability.",
        axis_effects=_axes("ride_height_rear")),

    Component.CAMBER_FRONT: EngineeringExplanation(
        Component.CAMBER_FRONT, ComponentGroup.ALIGNMENT,
        primary_mechanism=(
            "Front negative camber tilts the front tyres so the contact patch is optimised in "
            "roll during cornering, increasing peak lateral front grip at the cost of straight-"
            "line contact and tyre temperature spread."),
        secondary_interactions=(
            "Trades cornering grip against braking/traction and tyre wear.",
            "Interacts with front spring/ARB roll behaviour (how much the tyre leans)."),
        gt7_limitations=(
            "GT7's camber effect is milder and more forgiving than real life; excessive front "
            "camber loses less than expected but still raises inner-shoulder wear."),
        raise_effect="more front peak cornering grip; less braking grip; more inner-edge wear.",
        lower_effect="more even front contact; better braking/straight-line; less peak cornering grip.",
        axis_effects=_axes("camber_front")),

    Component.CAMBER_REAR: EngineeringExplanation(
        Component.CAMBER_REAR, ComponentGroup.ALIGNMENT,
        primary_mechanism=(
            "Rear negative camber optimises the rear contact patch in roll for cornering, "
            "increasing rear lateral grip and power-oversteer resistance at the cost of "
            "straight-line traction and tyre wear."),
        secondary_interactions=(
            "Interacts with LSD and rear springs for exit traction.",
            "Trades cornering grip against tyre preservation."),
        gt7_limitations=(
            "GT7 rewards modest rear camber; too much reduces the straight-line contact patch "
            "and can slightly hurt traction on corner exit."),
        raise_effect="more rear cornering grip and stability; less pure traction; more inner wear.",
        lower_effect="more rear straight-line traction; less peak cornering grip.",
        axis_effects=_axes("camber_rear")),

    Component.TOE_FRONT: EngineeringExplanation(
        Component.TOE_FRONT, ComponentGroup.ALIGNMENT,
        primary_mechanism=(
            "Front toe sets the resting steer angle of the front wheels. Toe-out sharpens "
            "turn-in response and initial rotation; toe-in adds straight-line stability. It "
            "directly trades responsiveness against stability and tyre scrub."),
        secondary_interactions=(
            "Interacts with steering feel and front tyre temperature/wear.",
            "Complements ARB/spring balance for entry behaviour."),
        gt7_limitations=(
            "GT7 front toe is sensitive to tyre wear: aggressive toe accelerates front tyre "
            "degradation noticeably over a stint."),
        raise_effect="(toward toe-in) more straight-line stability; slower turn-in; more scrub.",
        lower_effect="(toward toe-out) sharper turn-in and rotation; less stability; more scrub.",
        axis_effects=_axes("toe_front")),

    Component.TOE_REAR: EngineeringExplanation(
        Component.TOE_REAR, ComponentGroup.ALIGNMENT,
        primary_mechanism=(
            "Rear toe-in increases straight-line and high-speed stability and resistance to "
            "power oversteer by keeping the rear axle pointing forward under load; it trades "
            "against rear tyre scrub/wear and exit rotation."),
        secondary_interactions=(
            "Strongly interacts with LSD and rear ARB for exit stability.",
            "Trades stability against tyre preservation and drag."),
        gt7_limitations=(
            "GT7 rear toe-in is an effective stability aid but adds measurable rear tyre wear "
            "and a small amount of drag over a stint."),
        raise_effect="(toward toe-in) more rear stability and oversteer resistance; more wear.",
        lower_effect="(toward toe-out/zero) more rear rotation and agility; less stability.",
        axis_effects=_axes("toe_rear")),

    Component.BRAKE_BIAS: EngineeringExplanation(
        Component.BRAKE_BIAS, ComponentGroup.BRAKES,
        primary_mechanism=(
            "Brake bias sets the front/rear split of braking torque. Moving bias rearward frees "
            "the front to rotate the car on entry and trail-braking but risks rear lock-up; "
            "moving it forward stabilises braking at the cost of entry rotation."),
        secondary_interactions=(
            "Couples with trail-braking technique and front/rear grip balance.",
            "Interacts with LSD decel and rear stability under braking."),
        gt7_limitations=(
            "GT7 without ABS punishes a rearward brake bias with easy rear lock-up; with ABS the "
            "effect on rotation is muted."),
        raise_effect="(more rearward) more entry rotation via braking; more rear lock-up risk.",
        lower_effect="(more forward) more stable braking; less entry rotation; more front lock risk.",
        axis_effects=_axes("brake_bias")),

    Component.LSD_INITIAL: EngineeringExplanation(
        Component.LSD_INITIAL, ComponentGroup.DIFFERENTIAL,
        primary_mechanism=(
            "LSD initial (preload) torque sets how tightly the differential is locked at low "
            "torque. Higher preload keeps the axle more locked around neutral throttle, adding "
            "mid-corner stability but reducing agility on entry."),
        secondary_interactions=(
            "Sets the baseline the accel/decel ramps build from.",
            "Interacts with rear ARB/toe for apex and exit balance."),
        gt7_limitations=(
            "GT7 preload has a subtle effect versus accel/decel ramps; very high preload makes "
            "the car feel locked and reluctant to rotate at the apex."),
        raise_effect="more baseline lock; more apex stability; less low-throttle rotation.",
        lower_effect="more differential freedom; more agility; less mid-corner stability.",
        axis_effects=_axes("lsd_initial")),

    Component.LSD_ACCEL: EngineeringExplanation(
        Component.LSD_ACCEL, ComponentGroup.DIFFERENTIAL,
        primary_mechanism=(
            "LSD acceleration locking sets how much the diff locks under power. Higher accel "
            "lock ties the rear wheels together on throttle, improving exit traction and "
            "straight-line drive but reducing power-on rotation and adding corner-exit understeer "
            "if excessive."),
        secondary_interactions=(
            "Directly trades exit traction against power-oversteer resistance.",
            "Interacts with rear springs, ARB and camber for exit grip."),
        gt7_limitations=(
            "GT7 high accel lock strongly stabilises exit but can cause corner-exit understeer "
            "and inside-wheel scrub more than expected."),
        raise_effect="more exit traction and drive; less power-on rotation; exit-understeer risk if high.",
        lower_effect="more power-on rotation and agility; less exit traction; wheelspin risk if low.",
        axis_effects=_axes("lsd_accel")),

    Component.LSD_DECEL: EngineeringExplanation(
        Component.LSD_DECEL, ComponentGroup.DIFFERENTIAL,
        primary_mechanism=(
            "LSD deceleration locking sets how much the diff locks off-throttle and under "
            "braking. Higher decel lock stabilises the rear on corner entry and trail-braking "
            "by keeping the rear wheels tied together, at the cost of entry rotation."),
        secondary_interactions=(
            "Couples with brake bias and rear toe for entry/trail-braking stability.",
            "Trades trail-braking stability against initial rotation."),
        gt7_limitations=(
            "GT7 decel lock is the primary cure for lift-off and trail-braking rear instability; "
            "too little decel lock is a common cause of entry snap in GT7."),
        raise_effect="more entry/trail-braking stability; less initial rotation.",
        lower_effect="more entry rotation and agility; more lift-off/trail-braking instability risk.",
        axis_effects=_axes("lsd_decel")),

    Component.AERO_FRONT: EngineeringExplanation(
        Component.AERO_FRONT, ComponentGroup.AERO,
        primary_mechanism=(
            "Front downforce loads the front tyres aerodynamically, increasing front grip that "
            "grows with speed. More front aero adds apex front support and entry rotation, most "
            "strongly in high-speed corners."),
        secondary_interactions=(
            "Front-vs-rear aero split sets aero balance; couples with rake / ride height.",
            "Adds drag, reducing top speed and fuel efficiency."),
        gt7_limitations=(
            "GT7 front aero is ride-height dependent — its benefit falls if the front platform is "
            "too high, and it does little in slow corners."),
        raise_effect="more front high-speed grip; more apex support and rotation; more drag.",
        lower_effect="less front grip at speed; more front push in fast corners; less drag.",
        axis_effects=_axes("aero_front")),

    Component.AERO_REAR: EngineeringExplanation(
        Component.AERO_REAR, ComponentGroup.AERO,
        primary_mechanism=(
            "Rear downforce loads the rear tyres aerodynamically, increasing rear grip that grows "
            "with speed. More rear aero adds exit traction, power-oversteer resistance and high-"
            "speed stability, most strongly in fast corners."),
        secondary_interactions=(
            "Front-vs-rear aero split sets aero balance; couples with rake.",
            "Adds drag, reducing top speed and fuel efficiency."),
        gt7_limitations=(
            "GT7 rewards rear aero for stability but the drag penalty on long straights is "
            "significant; it does little in slow corners."),
        raise_effect="more rear high-speed grip, stability and traction; more drag; less top speed.",
        lower_effect="less rear grip at speed; more high-speed rotation/instability; less drag.",
        axis_effects=_axes("aero_rear")),

    Component.BALLAST: EngineeringExplanation(
        Component.BALLAST, ComponentGroup.WEIGHT_TRANSFER,
        primary_mechanism=(
            "Ballast adds mass at a chosen position. Its position moves the centre of gravity, "
            "changing static weight distribution and therefore the front/rear grip balance and "
            "the magnitude of load transfer; more total mass increases all load transfer."),
        secondary_interactions=(
            "Position interacts with weight distribution and polar moment (rotation inertia).",
            "More mass raises tyre load and wear and reduces acceleration/braking."),
        gt7_limitations=(
            "GT7 ballast is a blunt tool: it adds mass (hurting acceleration and tyre wear) even "
            "as it shifts balance; it cannot be moved during a race."),
        raise_effect="more mass and load transfer; slower accel/braking; balance shifts toward the ballast.",
        lower_effect="less mass; quicker accel/braking; less load transfer.",
        axis_effects={"tyre_preservation": -1}),

    Component.WEIGHT_DISTRIBUTION: EngineeringExplanation(
        Component.WEIGHT_DISTRIBUTION, ComponentGroup.WEIGHT_TRANSFER,
        primary_mechanism=(
            "Front/rear weight distribution sets the static share of load on each axle, which is "
            "the deepest determinant of mechanical balance: a more rearward bias increases rear "
            "traction and entry rotation; a more forward bias increases front grip and stability."),
        secondary_interactions=(
            "Sets the baseline that springs/ARB/aero then fine-tune.",
            "Affects polar moment and therefore rotation speed and stability."),
        gt7_limitations=(
            "In GT7 weight distribution is usually fixed per car or only movable via ballast, so "
            "it is a coarse, mostly-static parameter."),
        raise_effect="(toward rear bias) more rear traction and rotation; less braking stability.",
        lower_effect="(toward front bias) more front grip and stability; less rear traction.",
        axis_effects={"exit_traction": +1, "entry_rotation": +1}),

    Component.FUEL_LOAD: EngineeringExplanation(
        Component.FUEL_LOAD, ComponentGroup.WEIGHT_TRANSFER,
        primary_mechanism=(
            "Fuel load is variable mass, usually carried low and central-rear. A heavy fuel load "
            "raises total mass and load transfer, dulls response and raises tyre wear; the car "
            "gets lighter and more responsive as fuel burns off through a stint."),
        secondary_interactions=(
            "Interacts with weight distribution as its level changes over a stint.",
            "Changes optimal balance between the start and end of a stint."),
        gt7_limitations=(
            "GT7 models a meaningful fuel-mass effect: early-stint balance differs from late-"
            "stint, and a setup tuned on low fuel can feel different when full."),
        raise_effect="more mass and load transfer; more tyre wear; duller response (full tank).",
        lower_effect="less mass; sharper response; less wear (low tank / end of stint).",
        axis_effects={"tyre_preservation": -1, "fuel_efficiency": -1}),

    Component.TRANSMISSION: EngineeringExplanation(
        Component.TRANSMISSION, ComponentGroup.TRANSMISSION,
        primary_mechanism=(
            "Gear ratios and final drive set how engine torque is delivered to the wheels per "
            "gear. Shorter gearing multiplies torque (more acceleration, lower top speed); "
            "longer gearing raises top speed and can tame wheelspin out of slow corners."),
        secondary_interactions=(
            "Interacts with LSD and rear traction: a too-short lowest gear provokes wheelspin.",
            "Sets where each corner's exit falls in the rev/torque band."),
        gt7_limitations=(
            "GT7 lets you tune ratios finely; a mismatched final drive is a common cause of "
            "bogging or wheelspin out of specific corners on a given track."),
        raise_effect="(longer gearing) higher top speed; softer torque delivery; less wheelspin.",
        lower_effect="(shorter gearing) more acceleration and torque multiplication; more wheelspin risk.",
        axis_effects={"exit_traction": +1}),

    Component.TYRES: EngineeringExplanation(
        Component.TYRES, ComponentGroup.TYRES,
        primary_mechanism=(
            "The tyre is the only contact with the road; compound sets the grip-vs-durability "
            "trade, and load/temperature/camber determine how much of the contact patch works. "
            "Every other setup element ultimately acts by changing how the tyre is loaded."),
        secondary_interactions=(
            "Camber, toe, pressures and springs all shape the contact patch and temperature.",
            "Load transfer determines instantaneous per-tyre grip."),
        gt7_limitations=(
            "GT7 tyre wear is compound- and slip-driven: sustained wheelspin, lock-up and "
            "aggressive alignment wear tyres faster; softer compounds grip more but fall off "
            "sooner, and there is a distinct heat-up phase."),
        raise_effect="(softer compound) more peak grip; faster wear and heat-up.",
        lower_effect="(harder compound) less peak grip; longer life and more consistent temperature.",
        axis_effects={"tyre_preservation": -1}),
}


def _group_of(component: Component) -> ComponentGroup:
    return _KNOWLEDGE[component].group


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def all_components() -> Tuple[Component, ...]:
    return tuple(_KNOWLEDGE)


def explain_component(component) -> Optional[EngineeringExplanation]:
    """Return the deterministic mechanism knowledge for a component, or None."""
    try:
        comp = component if isinstance(component, Component) else Component(str(component))
    except (ValueError, TypeError):
        return None
    return _KNOWLEDGE.get(comp)


def explain_change(component, direction: str) -> dict:
    """Explain RAISING or LOWERING a component: primary mechanism, the directional effect,
    the affected axes (from the Program-1 sign graph), secondary interactions and GT7 notes.
    Deterministic; never raises."""
    exp = explain_component(component)
    if exp is None:
        return {"ok": False, "reason": "unknown component"}
    d = str(direction or "").strip().lower()
    raising = d in ("raise", "increase", "up", "higher", "stiffen", "+")
    effect = exp.raise_effect if raising else exp.lower_effect
    sign = 1 if raising else -1
    axes = {ax: sgn * sign for ax, sgn in exp.axis_effects.items()}
    return {
        "ok": True, "component": exp.component.value, "group": exp.group.value,
        "direction": "raise" if raising else "lower",
        "primary_mechanism": exp.primary_mechanism, "effect": effect,
        "axis_effects": axes,
        "secondary_interactions": list(exp.secondary_interactions),
        "gt7_limitations": list(exp.gt7_limitations),
    }


def components_for_group(group) -> Tuple[Component, ...]:
    try:
        grp = group if isinstance(group, ComponentGroup) else ComponentGroup(str(group))
    except (ValueError, TypeError):
        return ()
    return tuple(c for c in _KNOWLEDGE if _KNOWLEDGE[c].group == grp)


def build_knowledge_report() -> dict:
    """The full deterministic knowledge base, grouped for the UI. Regenerable + restart-
    deterministic (a pure function of static knowledge + the Program-1 sign graph)."""
    groups = []
    for grp in ComponentGroup:
        comps = [c for c in _KNOWLEDGE if _KNOWLEDGE[c].group == grp]
        if not comps:
            continue
        groups.append({
            "group": grp.value,
            "components": [_KNOWLEDGE[c].to_dict() for c in comps],
        })
    payload = {"v": VEHICLE_DYNAMICS_VERSION, "groups": groups}
    fp = (f"{VEHICLE_DYNAMICS_VERSION}:"
          + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()[:24])
    return {"ok": True, "version": VEHICLE_DYNAMICS_VERSION, "groups": groups,
            "content_fingerprint": fp}


def build_engineering_knowledge() -> dict:
    """The complete deterministic Vehicle-Dynamics knowledge base: components (grouped) +
    load-transfer + handling-balance + interaction (LSD/aero) models. Single entry point
    for the UI. Deterministic + regenerable + restart-identical; consumes only static
    knowledge + the Program-1 sign graph; makes no decision and mutates nothing."""
    # Lazy imports: the sub-modules import this module (avoid a circular import at load).
    from strategy.load_transfer import build_load_transfer_report
    from strategy.handling_balance import build_handling_report
    from strategy.setup_interactions import build_interactions_report

    components = build_knowledge_report()
    load = build_load_transfer_report()
    handling = build_handling_report()
    interactions = build_interactions_report()
    payload = {
        "v": VEHICLE_DYNAMICS_VERSION,
        "components": components["content_fingerprint"],
        "load": load["content_fingerprint"],
        "handling": handling["content_fingerprint"],
        "interactions": interactions["content_fingerprint"],
    }
    fp = (f"{VEHICLE_DYNAMICS_VERSION}:knowledge:"
          + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()[:24])
    return {
        "ok": True, "version": VEHICLE_DYNAMICS_VERSION,
        "component_groups": components["groups"],
        "load_transfer": load["modes"],
        "handling_phases": handling["phases"],
        "interactions": interactions["interactions"],
        "lsd_model": interactions["lsd_model"],
        "aero_model": interactions["aero_model"],
        "content_fingerprint": fp,
    }
