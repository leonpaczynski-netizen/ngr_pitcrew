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


def gearing_export(laps, sheet_gears=None) -> dict | None:
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
        "finalGearSource": (
            "derived: rpm against wheel speed and tyre radius"
            if final is not None else None),
        "matchesSheet": matches_sheet(laps, sheet_gears),
        "gearboxChangedMidSession": gearbox_changed_mid_session(laps),
        "limiterRpm": limiter,
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
            and fastest.get("rpm") and fastest["rpm"] >= limiter - 100)

    constant = gearing_constant(payload, ratios, final)
    if constant is not None:
        payload["gearingConstantK"] = constant
        payload["gearingConstantSource"] = (
            f"computed: observed speed x ratio x final gear, gear "
            f"{payload.get('maxSpeedGear')}, {payload['samples']} laps")
    return payload


def gearing_constant(payload: dict, ratios, final) -> float | None:
    """K = speed x that gear's ratio x final drive, at the fastest point.

    Only meaningful in top gear at the limiter; anywhere else the car simply
    was not going as fast as that gearing allows, and K would come out low.
    """
    if not ratios or final is None:
        return None
    if not payload.get("topGearReachedLimiter"):
        return None
    gear = payload.get("maxSpeedGear")
    speed = payload.get("maxSpeedKph")
    if not gear or not speed or gear > len(ratios):
        return None
    return round(speed * ratios[gear - 1] * final, 1)
