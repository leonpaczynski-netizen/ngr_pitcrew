"""Per-corner aggregation — the section that actually changes setups.

Takes the corner windows from `corner_model` and the 60 Hz frames of the
counted laps, and produces the `corners` array of the export.

Three rules from the contract shape every function here:

* **Missing is null, never zero.** A channel the packet format did not carry
  produces `None` all the way out. A corner with no braking has a `null` brake
  point, not `0`, because zero metres before the apex is a real claim.
* **Every aggregate carries its sample count.** A corner from two laps and one
  from eleven are not the same claim, so `samples` is mandatory.
* **Nothing derived is presented as measured.** Bottoming is inferred against
  a stated reference, and the reference travels with it.

Averages are means across counted laps; `consistencyMs` is the spread of the
corner's own time. High spread with a normal average is the signature of a car
the driver cannot trust, and it never shows up in a lap time — which is why it
is here at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median, pstdev

from pitcrew.analysis import thresholds
from pitcrew.analysis.corner_model import Corner, CornerModel


@dataclass(frozen=True)
class CountedLap:
    """One lap that contributes to the aggregate."""
    lap: int
    frames: list[dict]


def _defined(values: list) -> list:
    return [v for v in values if v is not None]


def _mean_or_none(values: list) -> float | None:
    present = _defined(values)
    return mean(present) if present else None


def _round_or_none(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def _slice(frames: list[dict], corner: Corner) -> list[dict]:
    return [f for f in frames
            if f.get("road_distance_m") is not None
            and corner.contains(f["road_distance_m"])]


def _frame_interval_ms(window: list[dict]) -> float:
    if len(window) < 2:
        return 16.67
    span = window[-1]["t_ms"] - window[0]["t_ms"]
    return span / (len(window) - 1) if span > 0 else 16.67


def _suspension_by_wheel(laps: list[CountedLap]) -> dict[str, list[float]]:
    seen: dict[str, list[float]] = {"fl": [], "fr": [], "rl": [], "rr": []}
    for lap in laps:
        for frame in lap.frames:
            for wheel in seen:
                value = frame.get(f"susp_mm_{wheel}")
                if value is not None:
                    seen[wheel].append(value)
    return seen


def bottoming_reference(laps: list[CountedLap]) -> dict[str, float] | None:
    """Lowest suspension height seen per wheel across the counted laps.

    This is the reference bottoming is inferred against — the contract is
    explicit that GT7 reports absolute height, not travel remaining, so there
    is no measurable "zero means bottomed". Stating the reference is what keeps
    the inference honest.
    """
    seen = _suspension_by_wheel(laps)
    if not all(seen.values()):
        return None
    return {wheel: round(min(values), 2) for wheel, values in seen.items()}


def bottoming_inferable(laps: list[CountedLap],
                        reference: dict[str, float] | None) -> set[str]:
    """Wheels whose trace actually moves enough to infer bottoming from.

    Without this guard the inference is circular: the reference is the observed
    minimum, so a suspension height that never varies sits in the band on every
    frame and every corner reports as bottoming. A trace that does not move
    cannot tell you the car reached its bump stops — it tells you nothing.
    """
    if not reference:
        return set()
    inferable = set()
    for wheel, values in _suspension_by_wheel(laps).items():
        floor = reference.get(wheel)
        if floor is None or not values:
            continue
        typical = median(values)
        if typical - floor > thresholds.BOTTOMING_BAND_MM:
            inferable.add(wheel)
    return inferable


def aggregate_corners(model: CornerModel, laps: list[CountedLap],
                      bottoming_ref: dict[str, float] | None = None) -> list[dict]:
    """The `corners` array. Corners no lap reached are omitted, not zeroed."""
    if bottoming_ref is None:
        bottoming_ref = bottoming_reference(laps)
    inferable = bottoming_inferable(laps, bottoming_ref)

    out: list[dict] = []
    for corner in model.corners:
        per_lap = []
        for lap in laps:
            window = _slice(lap.frames, corner)
            if len(window) < 2:
                continue
            per_lap.append(_measure(window, corner, bottoming_ref, inferable))
        if not per_lap:
            continue
        out.append(_combine(corner, per_lap))
    return out


def _measure(window: list[dict], corner: Corner,
             bottoming_ref: dict[str, float] | None,
             bottoming_wheels: set[str]) -> dict:
    """Everything measurable about one corner on one lap."""
    interval_ms = _frame_interval_ms(window)
    speeds = [f["speed_kph"] for f in window]
    brakes = [f["brake_pct"] for f in window]
    throttles = [f["throttle_pct"] for f in window]

    measurement = {
        "time_ms": window[-1]["t_ms"] - window[0]["t_ms"],
        "entry_kph": speeds[0],
        "min_kph": min(speeds),
        "exit_kph": speeds[-1],
        "brake_peak_pct": max(brakes),
        "brake_point_m": _brake_point_m(window, corner),
        "throttle_on_pct": _throttle_on_pct(window, corner),
        "steer_peak_deg": _peak_abs(window, "steering_deg"),
        "steer_peak_norm": _peak_signed(window, "steering_norm"),
        "trail_brake_ms": _trail_brake_ms(window, interval_ms),
        "susp_min_mm": _suspension_minima(window),
        "surface_counts": _surface_counts(window),
        "flags": _flags(window, interval_ms, bottoming_ref, bottoming_wheels),
    }
    _ = throttles  # read via _throttle_on_pct; kept explicit for clarity
    return measurement


def _brake_point_m(window: list[dict], corner: Corner) -> float | None:
    """Metres before the apex at which braking began.

    None when the corner was taken without braking — which is a finding, and
    is not the same as braking zero metres before the apex.
    """
    for frame in window:
        if frame["brake_pct"] > thresholds.BRAKE_ON_PCT:
            distance = frame["road_distance_m"]
            if distance > corner.apex_m:
                return None
            return round(corner.apex_m - distance, 1)
    return None


def _throttle_on_pct(window: list[dict], corner: Corner) -> float | None:
    """How far through the corner the throttle first came on, as a percentage."""
    span = corner.end_m - corner.start_m
    if span <= 0:
        return None
    for frame in window:
        if frame["throttle_pct"] > thresholds.THROTTLE_ON_PCT:
            through = (frame["road_distance_m"] - corner.start_m) / span
            return round(max(0.0, min(1.0, through)) * 100.0, 1)
    return None


def _peak_abs(window: list[dict], key: str) -> float | None:
    values = _defined([f.get(key) for f in window])
    return round(max(values, key=abs), 2) if values else None


def _peak_signed(window: list[dict], key: str) -> float | None:
    return _peak_abs(window, key)


def _trail_brake_ms(window: list[dict], interval_ms: float) -> float | None:
    """Time braking while the wheel is turned.

    Null rather than zero when steering is unavailable: without steering there
    is no way to tell trail braking from straight-line braking, and reporting
    zero would read as "he does not trail brake".
    """
    if all(f.get("steering_norm") is None for f in window):
        return None
    total = 0.0
    for frame in window:
        steering = frame.get("steering_norm")
        if steering is None:
            continue
        if (frame["brake_pct"] > thresholds.TRAIL_BRAKE_MIN_BRAKE_PCT
                and abs(steering) * 100.0 > thresholds.TRAIL_BRAKE_STEER_PCT):
            total += interval_ms
    return round(total, 1)


def _suspension_minima(window: list[dict]) -> dict[str, float] | None:
    out = {}
    for wheel in ("fl", "fr", "rl", "rr"):
        values = _defined([f.get(f"susp_mm_{wheel}") for f in window])
        if not values:
            return None
        out[wheel] = round(min(values), 2)
    return out


def _surface_counts(window: list[dict]) -> dict[str, int] | None:
    counts: dict[str, int] = {}
    seen_any = False
    for frame in window:
        for wheel in ("fl", "fr", "rl", "rr"):
            surface = frame.get(f"surf_{wheel}")
            if surface is None:
                continue
            seen_any = True
            counts[surface] = counts.get(surface, 0) + 1
    return counts if seen_any else None


def _flags(window: list[dict], interval_ms: float,
           bottoming_ref: dict[str, float] | None,
           bottoming_wheels: set[str]) -> set[str]:
    flags: set[str] = set()

    wheelspin_ratio = 1.0 + thresholds.WHEELSPIN_PCT / 100.0
    lockup_ratio = 1.0 - thresholds.LOCKUP_PCT / 100.0
    for frame in window:
        slips = [frame.get(f"slip_{w}") for w in ("fl", "fr", "rl", "rr")]
        slips = _defined(slips)
        if not slips:
            continue
        if frame["throttle_pct"] > thresholds.THROTTLE_ON_PCT and \
                max(slips) > wheelspin_ratio:
            flags.add("wheelspin")
        if frame["brake_pct"] > thresholds.BRAKE_ON_PCT and \
                min(slips) < lockup_ratio:
            flags.add("lockup")

    if _countersteered(window, interval_ms):
        flags.add("countersteer")
        if _braking_while_turned(window):
            flags.add("trail-brake-instability")

    if _understeers_mid(window):
        flags.add("understeer-mid")

    if _off_track(window):
        flags.add("off-track")

    if _bottomed(window, interval_ms, bottoming_ref, bottoming_wheels):
        flags.add("bottoming")

    if _kerb_struck(window, interval_ms):
        flags.add("kerb-strike")

    return flags


def _countersteered(window: list[dict], interval_ms: float) -> bool:
    """A steering sign reversal of the threshold size inside the time window."""
    span = max(1, int(thresholds.COUNTERSTEER_WINDOW_MS / interval_ms))
    angles = [f.get("steering_deg") for f in window]
    for i, angle in enumerate(angles):
        if angle is None or abs(angle) < thresholds.COUNTERSTEER_DEG:
            continue
        for j in range(i + 1, min(i + span + 1, len(angles))):
            other = angles[j]
            if other is None:
                continue
            if angle > 0 > other and abs(other) >= thresholds.COUNTERSTEER_DEG:
                return True
            if angle < 0 < other and abs(other) >= thresholds.COUNTERSTEER_DEG:
                return True
    return False


def _braking_while_turned(window: list[dict]) -> bool:
    for frame in window:
        steering = frame.get("steering_norm")
        if steering is None:
            continue
        if (frame["brake_pct"] > thresholds.TRAIL_BRAKE_MIN_BRAKE_PCT
                and abs(steering) * 100.0 > thresholds.TRAIL_BRAKE_STEER_PCT):
            return True
    return False


def _understeers_mid(window: list[dict]) -> bool:
    """Steering angle rising while yaw rate is flat or falling."""
    previous_steer = previous_yaw = None
    rising_streak = 0
    for frame in window:
        steer = frame.get("steering_deg")
        yaw = frame.get("yaw_rate")
        if steer is None or yaw is None:
            continue
        if previous_steer is not None:
            more_lock = abs(steer) > abs(previous_steer) + 0.5
            no_more_rotation = abs(yaw) <= abs(previous_yaw)
            rising_streak = rising_streak + 1 if (more_lock and no_more_rotation) else 0
            if rising_streak >= 5:
                return True
        previous_steer, previous_yaw = steer, yaw
    return False


def _off_track(window: list[dict]) -> bool:
    for frame in window:
        for wheel in ("fl", "fr", "rl", "rr"):
            surface = frame.get(f"surf_{wheel}")
            if surface is not None and surface not in thresholds.ON_TRACK_SURFACES:
                return True
    return False


def _bottomed(window: list[dict], interval_ms: float,
              bottoming_ref: dict[str, float] | None,
              bottoming_wheels: set[str]) -> bool:
    if not bottoming_ref or not bottoming_wheels:
        return False
    needed = max(1, int(thresholds.BOTTOMING_MIN_MS / interval_ms))
    streak = 0
    for frame in window:
        in_band = False
        for wheel in bottoming_wheels:
            reference = bottoming_ref.get(wheel)
            if reference is None:
                continue
            height = frame.get(f"susp_mm_{wheel}")
            if height is not None and height <= reference + thresholds.BOTTOMING_BAND_MM:
                in_band = True
                break
        streak = streak + 1 if in_band else 0
        if streak >= needed:
            return True
    return False


def _kerb_struck(window: list[dict], interval_ms: float) -> bool:
    span = max(1, int(thresholds.KERB_STRIKE_WINDOW_MS / interval_ms))
    for wheel in ("fl", "fr", "rl", "rr"):
        heights = [f.get(f"susp_mm_{wheel}") for f in window]
        for i, height in enumerate(heights):
            if height is None:
                continue
            for j in range(i + 1, min(i + span + 1, len(heights))):
                other = heights[j]
                if other is None:
                    continue
                if abs(other - height) > thresholds.KERB_STRIKE_MM:
                    return True
    return False


def _combine(corner: Corner, per_lap: list[dict]) -> dict:
    """Fold the per-lap measurements into one corner object."""
    times = [m["time_ms"] for m in per_lap]
    best_time = min(times)

    surface_mix = None
    merged_counts: dict[str, int] = {}
    for measurement in per_lap:
        counts = measurement["surface_counts"]
        if counts is None:
            continue
        for surface, count in counts.items():
            merged_counts[surface] = merged_counts.get(surface, 0) + count
    if merged_counts:
        total = sum(merged_counts.values())
        surface_mix = {s: round(c / total, 3) for s, c in merged_counts.items()}

    susp_min = None
    wheel_minima = [m["susp_min_mm"] for m in per_lap if m["susp_min_mm"]]
    if wheel_minima:
        susp_min = {
            wheel: round(min(m[wheel] for m in wheel_minima), 2)
            for wheel in ("fl", "fr", "rl", "rr")
        }

    flags: set[str] = set()
    for measurement in per_lap:
        flags |= measurement["flags"]

    payload = {
        "id": corner.id,
        "name": corner.name,
        "samples": len(per_lap),
        "entrySpeedKph": _round_or_none(_mean_or_none([m["entry_kph"] for m in per_lap])),
        "minSpeedKph": _round_or_none(_mean_or_none([m["min_kph"] for m in per_lap])),
        "exitSpeedKph": _round_or_none(_mean_or_none([m["exit_kph"] for m in per_lap])),
        "brakePeakPct": _round_or_none(
            _mean_or_none([m["brake_peak_pct"] for m in per_lap])),
        "brakePointM": _round_or_none(
            _mean_or_none([m["brake_point_m"] for m in per_lap])),
        "trailBrakeMs": _round_or_none(
            _mean_or_none([m["trail_brake_ms"] for m in per_lap])),
        "steerPeakDeg": _round_or_none(
            _mean_or_none([m["steer_peak_deg"] for m in per_lap]), 2),
        "steerPeakNorm": _round_or_none(
            _mean_or_none([m["steer_peak_norm"] for m in per_lap]), 3),
        "throttleOnPct": _round_or_none(
            _mean_or_none([m["throttle_on_pct"] for m in per_lap])),
        "timeLossVsBestMs": round(mean(times) - best_time),
        "consistencyMs": round(pstdev(times)) if len(times) > 1 else None,
        "suspHeightMinMm": susp_min,
        "surfaceMix": surface_mix,
        "flags": sorted(flags),
    }
    return payload
