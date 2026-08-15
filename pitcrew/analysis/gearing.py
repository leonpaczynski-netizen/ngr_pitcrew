"""The gearbox as actually fitted, read off the stream.

Answers three questions the driver currently answers by hand:

* **Is the gearbox in the car the gearbox on the sheet?** Otherwise invisible
  until a whole test session has been run on the wrong box.
* **What is this car's gearing constant?** One reading makes every future
  gearbox on the car exact instead of iterated.
* **Where is the limiter, really?** Only when the rev-limiter flag actually
  fired — the highest rpm observed is not the limiter, it is just the highest
  rpm observed.

**There is no tow detection and there never will be.** GT7's feed carries no
proximity, no closing speed and no opponent positions, so "top speed in clean
air versus in a tow" is not answerable. This module reports the observed
maximum with its sample count; whether there was a tow is the driver's to say
in `notes`. Any field here named after a tow would be a fabrication.
"""
from __future__ import annotations

import math
from statistics import median

# Ratios agreeing to this many parts in a thousand are the same gearbox. GT7
# shows three decimals and the packet carries float noise below that.
RATIO_TOLERANCE = 0.005

# Within this of the limiter counts as having reached it.
LIMITER_MARGIN_RPM = 100.0

# GT7 broadcasts the tyre radius unloaded. A loaded racing tyre stands a few
# percent shorter, so a final drive derived through the broadcast radius comes
# out high by that few percent — larger than the gap between one final-drive
# setting and the next, which is why the derived figure is reported beside the
# sheet's rather than compared to it.
FINAL_GEAR_SOURCE = (
    "derived: rpm against wheel speed and the broadcast tyre radius. GT7 "
    "broadcasts the unloaded radius, so this reads a few percent high against "
    "the sheet - see rollingRadiusImpliedM")

MATCHES_SHEET_COVERS = (
    "fittedRatios against setup.gears, +-0.005 each. It does NOT cover the "
    "final drive: fittedFinalGear is derived through an unloaded tyre radius "
    "and its bias is larger than one final-drive step, so comparing it would "
    "report a mismatch on a correct gearbox. Read finalGearSheet, "
    "fittedFinalGear and finalGearVsSheetPct together instead")


def _lap_ratios(laps) -> list[list[float]]:
    return [lap.gear_ratios for lap in laps if getattr(lap, "gear_ratios", None)]


def fitted_ratios(laps) -> list[float] | None:
    """The ratios the car actually had, from the most recent lap carrying them."""
    seen = _lap_ratios(laps)
    return list(seen[-1]) if seen else None


def gearbox_changed_mid_session(laps) -> bool:
    """True when not every lap ran the same box.

    A mid-session gearbox change invalidates any aggregate spanning it, the
    same way a setup change does.
    """
    seen = _lap_ratios(laps)
    if len(seen) < 2:
        return False
    first = seen[0]
    return any(not _same_ratios(first, other) for other in seen[1:])


def _same_ratios(left, right) -> bool:
    if left is None or right is None or len(left) != len(right):
        return False
    return all(abs(a - b) <= RATIO_TOLERANCE for a, b in zip(left, right))


def matches_sheet(laps, sheet_gears) -> bool | None:
    """Does the fitted box match the sheet? None when either is unknown."""
    fitted = fitted_ratios(laps)
    if not fitted or not sheet_gears:
        return None
    return _same_ratios(fitted[:len(sheet_gears)], list(sheet_gears))


def _frames(laps):
    for lap in laps:
        for frame in lap.frames or ():
            yield frame


def limiter_rpm(laps) -> float | None:
    """Engine speed where the limiter actually fired, or None.

    Deliberately not "the highest rpm seen": a session that never hit the
    limiter has no limiter reading, and reporting the peak instead would put a
    number in front of the tune builder that means something else entirely.
    """
    hits = [f["rpm"] for f in _frames(laps)
            if f.get("rev_limiter") and f.get("rpm")]
    return round(median(hits), 0) if hits else None


def _fastest_frame(laps) -> dict | None:
    best = None
    for frame in _frames(laps):
        speed = frame.get("speed_kph")
        if speed is None:
            continue
        if best is None or speed > best["speed_kph"]:
            best = frame
    return best


def final_drive(laps, ratios) -> float | None:
    """Final drive, derived from wheel speed against engine speed.

    GT7 sends the eight gear ratios but not the final drive, so this is
    computed rather than read:

        final = (rpm / 60) * 2 * pi * r / (v * gear_ratio)

    using the tyre radius the packet reports. It is derived, and the export
    says so - it is not what the driver typed on the sheet.

    **Orientation.** Engine speed = wheel speed x gear ratio x final drive, so
    the final drive is engine speed over the product of the other two. A car
    turning more engine revs for the same road speed is more heavily geared and
    the figure goes *up*; a car pulling taller gearing for the same revs goes
    *down*. Unit-tested in both directions, because inverting it silently
    produces a plausible number rather than an obviously wrong one.
    """
    if not ratios:
        return None
    candidates = []
    for frame in _frames(laps):
        gear = frame.get("gear")
        rpm = frame.get("rpm")
        speed = frame.get("speed_kph")
        radius = _tyre_radius(frame)
        if not gear or not rpm or not speed or not radius:
            continue
        if gear > len(ratios) or speed < 100.0:
            continue
        wheel_hz = speed / 3.6 / (2 * math.pi * radius)
        if wheel_hz <= 0:
            continue
        candidates.append((rpm / 60.0) / (wheel_hz * ratios[gear - 1]))
    if not candidates:
        return None
    return round(median(candidates), 3)


def _tyre_radius(frame) -> float | None:
    """Driven-wheel radius. Frames carry suspension and slip, not radius, so
    this is only available when the caller supplies it."""
    return frame.get("tyre_radius_m")


def limiter_gear(laps) -> int | None:
    """The gear the limiter actually fired in, modal across the frames.

    Without it, `limiterRpmSource: observed-at-rev-limiter` sitting beside
    `topGearReachedLimiter: false` reads as a contradiction. It is not one —
    the limiter fired in a lower gear — but only this field says so.
    """
    gears = [f.get("gear") for f in _frames(laps)
             if f.get("rev_limiter") and f.get("gear")]
    if not gears:
        return None
    return max(set(gears), key=gears.count)


def gearing_export(laps, sheet_gears=None, *, sheet_final_gear=None) -> dict | None:
    """The `gearing` section, or None when nothing about the box is known."""
    ratios = fitted_ratios(laps)
    fastest = _fastest_frame(laps)
    limiter = limiter_rpm(laps)
    if ratios is None and fastest is None:
        return None

    final = final_drive(laps, ratios)
    payload: dict = {
        "fittedRatios": ratios,
        "fittedFinalGear": final,
        "ratioSource": "telemetry" if ratios else None,
        "finalGearSource": (FINAL_GEAR_SOURCE if final is not None else None),
        "finalGearSheet": sheet_final_gear,
        "finalGearVsSheetPct": _delta_pct(final, sheet_final_gear),
        "rollingRadiusImpliedM": _implied_rolling_radius(laps, final,
                                                         sheet_final_gear),
        "matchesSheet": matches_sheet(laps, sheet_gears),
        # `matchesSheet` answers one question and this says which. The final
        # drive is not in it and cannot be: the derived figure carries a
        # systematic bias of a few percent from the unloaded tyre radius,
        # which is larger than the difference between one final-drive setting
        # and the next, so a comparison would report a mismatch on a correct
        # gearbox. The two figures are given instead, with the gap between
        # them, and the reader judges.
        "matchesSheetCovers": MATCHES_SHEET_COVERS,
        "gearboxChangedMidSession": gearbox_changed_mid_session(laps),
        "limiterRpm": limiter,
        "limiterGear": limiter_gear(laps),
        "limiterRpmSource": (
            "observed-at-rev-limiter" if limiter is not None
            else "limiter never fired in this session"),
        "samples": len([lap for lap in laps if lap.frames]),
    }

    if fastest is not None:
        payload["maxSpeedKph"] = round(fastest["speed_kph"], 1)
        payload["maxSpeedGear"] = fastest.get("gear") or None
        payload["maxSpeedRpm"] = round(fastest["rpm"], 0) if fastest.get("rpm") else None
        payload["topGearReachedLimiter"] = bool(
            ratios and fastest.get("gear") == len(ratios) and limiter is not None
            and fastest.get("rpm") and fastest["rpm"] >= limiter - LIMITER_MARGIN_RPM)

    constant = gearing_constant(payload, ratios, sheet_final_gear, final)
    if constant is not None:
        payload.update(constant)
    return payload


def gearing_constant(payload: dict, ratios, sheet_final_gear,
                     derived_final_gear) -> dict | None:
    """K = speed in top gear at the limiter x that gear's ratio x final drive.

    For a given car this is a constant, and one clean reading makes every
    future gearbox on it exact instead of iterated — which is why it is worth
    extrapolating for rather than only reporting when the limiter happens to
    fire in top.

    Two things it will not do:

    * **It uses the final drive off the sheet, not the derived one.** The sheet
      figure is what the driver typed into the game and is exact; the derived
      one is a few percent high because GT7 broadcasts an unloaded tyre radius.
      A K built on the derived figure would be high by the same few percent and
      would put every future gearbox out by that much.
    * **It says when it extrapolated.** Scaling the observed top-gear speed up
      to the limiter is sound and worth doing, but it is not the same claim as
      having seen the limiter in top gear, and the wording distinguishes them.
    """
    gear = payload.get("maxSpeedGear")
    speed = payload.get("maxSpeedKph")
    rpm = payload.get("maxSpeedRpm")
    limiter = payload.get("limiterRpm")
    if not ratios or not gear or not speed:
        return None
    # Anywhere but top gear the car simply was not going as fast as the gearing
    # allows, and no scaling recovers that.
    if gear != len(ratios):
        return None

    final = sheet_final_gear or derived_final_gear
    if not final:
        return None
    final_source = ("sheet" if sheet_final_gear
                    else "derived, and high by the unloaded-radius bias")

    if payload.get("topGearReachedLimiter"):
        top_speed = speed
        source = (f"computed: observed speed x ratio x final gear, gear "
                  f"{gear} at the limiter, {payload['samples']} laps")
    elif limiter and rpm and rpm > 0:
        top_speed = speed * (limiter / rpm)
        source = (f"extrapolated: top gear observed at {rpm:.0f} rpm, scaled "
                  f"to limiter {limiter:.0f}, {payload['samples']} laps")
    else:
        return None

    return {
        "gearingConstantK": round(top_speed * ratios[gear - 1] * final, 1),
        "gearingConstantSource": source,
        "gearingConstantFinalGear": final,
        "gearingConstantFinalGearSource": final_source,
        "gearingConstantSamples": payload["samples"],
        "topGearSpeedAtLimiterKph": round(top_speed, 1),
    }


def _delta_pct(derived: float | None, sheet: float | None) -> float | None:
    if not derived or not sheet:
        return None
    return round((derived - sheet) / sheet * 100.0, 2)


def _implied_rolling_radius(laps, derived_final: float | None,
                            sheet_final: float | None) -> float | None:
    """What the tyre radius must have been for the sheet's final drive to hold.

    The derived final drive and the broadcast radius are two ways of saying the
    same thing, so where the sheet's figure is known the gap between them is
    better read as tyre deflection than as a gearbox discrepancy: the broadcast
    radius is the unloaded one, and a loaded racing tyre stands a few percent
    shorter. Reporting it that way turns a misleading number into a measured
    one.
    """
    if not derived_final or not sheet_final:
        return None
    broadcast = next((f["tyre_radius_m"] for f in _frames(laps)
                      if f.get("tyre_radius_m")), None)
    if not broadcast:
        return None
    return round(broadcast * sheet_final / derived_final, 4)
