"""Group 63 — complete LSD triplet reasoning (pure, Qt-free).

The UAT failure evaluated the differential narrowly: LSD Acceleration only, and
Initial Torque / Braking Sensitivity not at all — even though the driver said the
LSD "is not set how I like … not hooking up on the apex" and "the rear steps out
under braking". This module reasons over ALL THREE LSD fields independently and
jointly, comparing each against the driver's PROVEN same-car values (a strong
prior, never a mandate), and — crucially — prescribes a **controlled test** when
telemetry cannot safely author a change (e.g. an unknown wheelspin subtype, or an
lsd_accel increase that would worsen a rear already loose on throttle).

It authors NO setup values and applies nothing: it produces an assessment the
renderer surfaces and the (unchanged) rule-first engine / Apply gate still govern.
Every recommendation is direction + evidence + confidence + an executable test —
never a fabricated certainty.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Optional

# The three differential levers, in evaluation order.
LSD_FIELDS = ("lsd_initial", "lsd_accel", "lsd_decel")
_LSD_LABELS = {
    "lsd_initial": "LSD Initial Torque (preload)",
    "lsd_accel": "LSD Acceleration Sensitivity",
    "lsd_decel": "LSD Braking Sensitivity",
}

# A move of at least this (absolute) from a strong proven value is "material".
_MATERIAL = {"lsd_initial": 4.0, "lsd_accel": 3.0, "lsd_decel": 4.0}

# Direction labels.
DIR_INCREASE = "increase"
DIR_DECREASE = "decrease"
DIR_TOWARD_PROVEN = "toward_proven"
DIR_TEST = "controlled_test"
DIR_HOLD = "hold"
DIR_UNEVALUATED = "not_evaluated"


@dataclass(frozen=True)
class LsdFieldAssessment:
    field: str
    label: str
    current: Optional[float]
    proven: Optional[float]
    proven_source: str
    proven_confidence: str
    evaluated: bool
    direction: str
    evidence: str
    controlled_test: str
    confidence: str


@dataclass(frozen=True)
class LsdTripletAssessment:
    fields: list                     # list[LsdFieldAssessment]
    controlled_tests: list           # list[str] — executable A/B tests
    summary: str

    def as_json(self) -> dict:
        return {
            "fields": [
                {"field": f.field, "label": f.label, "current": f.current,
                 "proven": f.proven, "proven_source": f.proven_source,
                 "proven_confidence": f.proven_confidence, "evaluated": f.evaluated,
                 "direction": f.direction, "evidence": f.evidence,
                 "controlled_test": f.controlled_test, "confidence": f.confidence}
                for f in self.fields
            ],
            "controlled_tests": list(self.controlled_tests),
            "summary": self.summary,
        }


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _proven(prior: dict, field: str):
    d = (prior or {}).get(field)
    if not isinstance(d, dict):
        return None, "", "none"
    return _num(d.get("value")), str(d.get("source", "")), str(d.get("confidence", "none"))


# Traction wheelspin subtypes for which MORE accel-locking is the textbook fix.
_TRACTION_SUBTYPES = frozenset({"both_rear_spin"})
# Subtypes where the mechanism is not a pure traction deficit → a change is unsafe.
_AMBIGUOUS_SUBTYPES = frozenset({"mixed", "insufficient_data", "kerb_unload_spin",
                                 "aero_instability", "gear_too_short_spin"})


def build_lsd_triplet_assessment(
    diagnosis: dict,
    current_setup: dict,
    history_prior: dict,
) -> LsdTripletAssessment:
    """Evaluate Initial / Acceleration / Braking sensitivity independently.

    ``history_prior`` is ``build_historical_prior``'s field -> {value, source, tier,
    confidence} map (proven same-car values). Values are advisory priors: they
    influence the direction and confidence, never force a value.
    """
    flags = (diagnosis or {}).get("driver_feel_flags", {}) or {}
    ws_band = str((diagnosis or {}).get("wheelspin_band", "low"))
    ws_subtype = str((diagnosis or {}).get("wheelspin_subtype", "insufficient_data"))
    setup = current_setup or {}
    prior = history_prior or {}

    lsd_feel_wrong = bool(flags.get("lsd_feel_wrong"))
    floaty = bool(flags.get("floaty_front"))
    rear_exit = bool(flags.get("rear_loose_on_exit"))
    rear_brake = bool(flags.get("rear_loose_under_braking"))
    entry_us = bool(flags.get("entry_understeer"))
    braking_inst = bool(flags.get("braking_instability"))

    out: list[LsdFieldAssessment] = []
    tests: list[str] = []

    # ---- Initial Torque (preload / apex connection) --------------------------
    cur, (pv, psrc, pconf) = _num(setup.get("lsd_initial")), _proven(prior, "lsd_initial")
    if lsd_feel_wrong or floaty:
        direction, evidence, conf, test = DIR_TEST, "", "low", ""
        gap = (abs(pv - cur) if (pv is not None and cur is not None) else None)
        if pv is not None and cur is not None and gap is not None and gap >= _MATERIAL["lsd_initial"]:
            if cur < pv:
                direction = DIR_INCREASE
                evidence = (f"apex-connection complaint and current preload {cur:g} is well "
                            f"below your proven {pv:g} ({psrc}) — more preload connects the diff "
                            "off the apex")
            else:
                direction = DIR_DECREASE
                evidence = (f"current preload {cur:g} is above your proven {pv:g} ({psrc}); "
                            "excess preload can resist low-speed rotation")
            conf = "medium" if pconf in ("high", "medium") else "low"
            test = (f"A/B Initial Torque: Run A current {cur:g}, Run B {pv:g} (your proven value) — "
                    "compare apex drive, mid-corner rotation and stability over 3 clean laps.")
        else:
            evidence = ("driver reports the LSD does not hook up at the apex; Initial Torque "
                        "governs preload / apex connection but telemetry cannot measure preload "
                        "directly — confirm with a controlled test")
            test = ("A/B Initial Torque: step preload ±2 from current and compare apex drive and "
                    "low-speed rotation; move toward the value that connects the car off the apex"
                    + (f" (your proven same-car value is {pv:g})" if pv is not None else ""))
        tests.append("LSD Initial Torque — " + test)
        out.append(LsdFieldAssessment("lsd_initial", _LSD_LABELS["lsd_initial"], cur, pv,
                                      psrc, pconf, True, direction, evidence, test, conf))
    else:
        out.append(LsdFieldAssessment("lsd_initial", _LSD_LABELS["lsd_initial"], cur, pv,
                                      psrc, pconf, False, DIR_UNEVALUATED,
                                      "no driver LSD/apex complaint — preload left unchanged", "", "n/a"))

    # ---- Acceleration Sensitivity (throttle-side locking) --------------------
    cur, (pv, psrc, pconf) = _num(setup.get("lsd_accel")), _proven(prior, "lsd_accel")
    if rear_exit or ws_band != "low":
        direction, evidence, conf, test = DIR_TEST, "", "low", ""
        if rear_exit and ws_subtype in _TRACTION_SUBTYPES:
            # Genuine both-wheel traction deficit but rear already loose on throttle:
            # increasing lock would worsen power oversteer -> must be tested, not applied.
            direction, conf = DIR_TEST, "low"
            evidence = ("both-rear traction deficit AND rear loose on throttle conflict — "
                        "more accel-lock aids traction but worsens power oversteer; resolve by test")
            test = ("A/B Acceleration Sensitivity: ±2 from current; watch whether traction gain "
                    "outweighs added throttle-on oversteer. Do NOT increase blind.")
        elif ws_subtype in _AMBIGUOUS_SUBTYPES:
            evidence = (f"wheelspin subtype is '{ws_subtype}' — telemetry cannot distinguish "
                        "inside-wheel spin from whole-axle power oversteer, so the correct "
                        "accel-lock direction is unknown")
            test = ("Controlled test: log rear-wheel slip by wheel, gear and throttle position over "
                    "3 clean laps to classify inside-wheel vs whole-axle spin before changing lock.")
        else:
            evidence = "rear looseness on throttle noted; accel-lock direction pending subtype confirmation"
            test = "A/B Acceleration Sensitivity ±2 with the rear-loose symptom watched."
        if pv is not None and cur is not None:
            evidence += f" (your proven same-car value is {pv:g}, {psrc})"
        tests.append("LSD Acceleration Sensitivity — " + test)
        out.append(LsdFieldAssessment("lsd_accel", _LSD_LABELS["lsd_accel"], cur, pv,
                                      psrc, pconf, True, direction, evidence, test, conf))
    else:
        out.append(LsdFieldAssessment("lsd_accel", _LSD_LABELS["lsd_accel"], cur, pv,
                                      psrc, pconf, False, DIR_UNEVALUATED,
                                      "no throttle-exit looseness or meaningful wheelspin", "", "n/a"))

    # ---- Braking Sensitivity (coast / entry stability) -----------------------
    cur, (pv, psrc, pconf) = _num(setup.get("lsd_decel")), _proven(prior, "lsd_decel")
    if rear_brake or entry_us or braking_inst:
        direction, evidence, conf, test = DIR_TEST, "", "low", ""
        if rear_brake or braking_inst:
            # Rear stepping out under braking -> generally MORE braking sensitivity /
            # engine-braking stability (or move toward proven), never throttle-side LSD.
            direction = DIR_INCREASE if (pv is None or cur is None or pv >= cur) else DIR_TOWARD_PROVEN
            evidence = ("rear steps out under braking — a coast/brake-side problem for LSD Braking "
                        "Sensitivity (and brake bias), NOT throttle-side accel lock")
            if pv is not None and cur is not None:
                evidence += f"; your proven same-car value is {pv:g} ({psrc}) vs current {cur:g}"
            conf = "medium" if pconf in ("high", "medium") else "low"
            test = ("A/B Braking Sensitivity: Run A current"
                    + (f" {cur:g}" if cur is not None else "")
                    + (f", Run B {pv:g} (proven)" if pv is not None else ", Run B +2")
                    + " — compare rear stability on entry and trail-braking confidence.")
        else:  # entry understeer
            direction = DIR_DECREASE
            evidence = "entry understeer — less braking sensitivity frees the front on the way in"
            test = "A/B Braking Sensitivity −2 vs current; watch entry rotation vs rear stability."
        tests.append("LSD Braking Sensitivity — " + test)
        out.append(LsdFieldAssessment("lsd_decel", _LSD_LABELS["lsd_decel"], cur, pv,
                                      psrc, pconf, True, direction, evidence, test, conf))
    else:
        out.append(LsdFieldAssessment("lsd_decel", _LSD_LABELS["lsd_decel"], cur, pv,
                                      psrc, pconf, False, DIR_UNEVALUATED,
                                      "no braking-phase rear instability or entry understeer", "", "n/a"))

    evaluated = [f for f in out if f.evaluated]
    if evaluated:
        summary = (f"Evaluated {len(evaluated)} of 3 LSD fields against your proven same-car "
                   "values; direction is confirmed by controlled test before applying "
                   "(differential changes interact and are easy to over-correct).")
    else:
        summary = "No LSD complaint or telemetry trigger — differential left unchanged."
    return LsdTripletAssessment(out, tests, summary)
