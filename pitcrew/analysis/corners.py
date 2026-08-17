"""Per-corner aggregation — the section that actually changes setups.

Takes the corner windows from `corner_model` and the 60 Hz frames of the
counted laps, and produces the `corners` array of the export.

Three rules from the contract shape every function here:

* **Missing is null, never zero.** A channel the packet format did not carry
  produces `None` all the way out. A corner with no braking has a `null` brake
  point, not `0`, because zero metres before the apex is a real claim.
* **Every aggregate carries its sample count.** A corner from two laps and one
  from eleven are not the same claim, so `samples` is mandatory — and a mean
  taken over only the laps that carried a channel carries its own count beside
  it, because `upshiftRpm` over two laps published under `samples: 23` is a
  two-lap claim wearing a twenty-three-lap label.
* **Nothing derived is presented as measured.** Bottoming is inferred against
  a stated reference, and the reference travels with it.

Averages are means across counted laps; `consistencyMs` is the spread of the
corner's own time. High spread with a normal average is the signature of a car
the driver cannot trust, and it never shows up in a lap time — which is why it
is here at all.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, median, pstdev

from pitcrew.analysis import thresholds
from pitcrew.analysis.corner_model import Corner, CornerModel

# Sample rate assumed when a lap does not carry its own. The recorder's own
# default; laps recorded by this app all store 60.0.
DEFAULT_SAMPLE_HZ = 60.0


@dataclass(frozen=True)
class CountedLap:
    """One lap that contributes to the aggregate."""
    lap: int
    frames: list[dict]
    # **Which setup sheet was fitted.** Ride height and spring rate are setup
    # values, so the height a wheel bottoms at is a property of the sheet, not
    # of the event. The bottoming reference is keyed on this.
    setup_sheet_id: int | None = None
    # The lap's stored capture rate. Every ms-to-frames window is derived from
    # it rather than re-measured off `t_ms`, which straddles 16.66667 and put
    # two corners of the same session under different rules.
    sample_hz: float | None = None

    @property
    def interval_ms(self) -> float:
        return 1000.0 / (self.sample_hz or DEFAULT_SAMPLE_HZ)


def _defined(values: list) -> list:
    return [v for v in values if v is not None]


def _mean_or_none(values: list) -> float | None:
    present = _defined(values)
    return mean(present) if present else None


def _round_or_none(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


BRAKE_LOOKBACK_M = thresholds.BRAKE_LOOKBACK_M


def _frames_for_ms(duration_ms: float, interval_ms: float) -> int:
    """Frames covering a stated duration, rounded **up**.

    `int()` truncated every one of these, so a 50 ms rule was tested over
    33 ms and a 300 ms one over 283 ms. Worse, `interval_ms` used to be
    re-derived per window from `t_ms`: measured across one session it landed
    either side of 3.0 and gave 2 frames on 254 windows and 3 on 495, so two
    corners of the same circuit were judged by different rules and the export
    declared neither.
    """
    return max(1, math.ceil(duration_ms / interval_ms))


def _slice(frames: list[dict], corner: Corner) -> list[dict]:
    return [f for f in frames
            if f.get("lap_distance_m") is not None
            and corner.contains(f["lap_distance_m"])]


def _approach(frames: list[dict], corner: Corner) -> list[dict]:
    """Frames from the braking zone up to the apex, in distance order.

    Anchored on the apex, which is what `brakePointM` is measured from, so the
    reported distance can never exceed the lookback the export declares.
    """
    low = corner.apex_m - BRAKE_LOOKBACK_M
    picked = [f for f in frames
              if f.get("lap_distance_m") is not None
              and low <= f["lap_distance_m"] <= corner.apex_m]
    return sorted(picked, key=lambda f: f["lap_distance_m"])


def _suspension_by_wheel(frames: list[dict]) -> dict[str, list[float]]:
    seen: dict[str, list[float]] = {"fl": [], "fr": [], "rl": [], "rr": []}
    for frame in frames:
        for wheel in seen:
            value = frame.get(f"susp_mm_{wheel}")
            if value is not None:
                seen[wheel].append(value)
    return seen


def _straight_line_frames(lap: CountedLap,
                          model: CornerModel | None) -> list[dict]:
    """The lap's frames with every corner window held out.

    "Straight-line" is outside every corner window and, where steering is
    available, under a stated fraction of lock. Without the hold-out the
    bottoming reference is the observed minimum of the very frames the flag is
    tested against, so the deepest corner satisfies it by construction.
    """
    out = []
    for frame in lap.frames:
        distance = frame.get("lap_distance_m")
        if distance is None:
            continue
        if model is not None and any(c.contains(distance) for c in model.corners):
            continue
        steering = frame.get("steering_norm")
        if steering is not None and \
                abs(steering) * 100.0 > thresholds.BOTTOMING_REF_MAX_STEER_PCT:
            continue
        out.append(frame)
    return out


# **`susp_mm_*` is COMPRESSION, not height, and everything here read it
# backwards until 17 Aug 2026.** Measured on session 49's own frames, two ways
# that need no sign convention to interpret:
#
# * Under heavy braking against full throttle, the fronts read +6.2 and
#   +7.5 mm and the rears -11.7 and -9.8. A car pitches FORWARD under braking,
#   so the end that reads higher is the end that compressed.
# * Straight-line frames from 120 to 260 km/h: `body_height_mm` falls 61.5 ->
#   50.5 mm as downforce builds, while every `susp_mm_*` RISES, 257 -> 269
#   front and 279 -> 289 rear. Two channels, the same frames, opposite signs.
#   `body_height_mm` is a height. `susp_mm_*` is not.
#
# So the bottoming end of the trace is the MAXIMUM, and taking `min` took the
# most EXTENDED the wheel ever got. The flag fired on a wheel going light and
# called it floor contact - which is exactly why it fired 17 laps out of 17 at
# T4, T7 and T8 on the inside wheels of the same-handed corners, and why
# raising the car 5 mm made the reported depth worse rather than better. A
# contact detector cannot do that. An extension detector must.


def _most_compressed(frames: list[dict]) -> dict[str, float] | None:
    """Per wheel, the most compressed the trace got over these frames."""
    seen = _suspension_by_wheel(frames)
    if not all(seen.values()):
        return None
    return {wheel: round(max(values), 2) for wheel, values in seen.items()}


def observed_minimum(laps: list[CountedLap]) -> dict[str, float] | None:
    """Lowest suspension height seen anywhere, per wheel.

    **Not the bottoming reference.** CLAUDE.md 3.3 fact 3 asks for two
    quantities and the app used to publish one: a steady-state reference, and
    excursions toward the observed minimum. This is the second of them, and it
    is a measurement rather than an inference — which is why it travels
    separately.
    """
    return _most_compressed([f for lap in laps for f in lap.frames])


def bottoming_reference(laps: list[CountedLap],
                        model: CornerModel | None = None
                        ) -> dict[str, float] | None:
    """The steady-state reference bottoming is inferred against.

    Lowest suspension height per wheel over **straight-line frames only** — a
    corner cannot define the floor it is then judged against. GT7 reports
    absolute height, not travel remaining, so there is no measurable "zero
    means bottomed"; stating the reference is what keeps the inference honest.

    Falls back to every frame when nothing is held out, which happens when
    there is no corner model and no steering channel. That is the old,
    circular reference and it is the best available in that case.
    """
    frames = [f for lap in laps for f in _straight_line_frames(lap, model)]
    return _most_compressed(frames) or observed_minimum(laps)


def bottoming_references(laps: list[CountedLap],
                         model: CornerModel | None = None
                         ) -> dict[object, dict[str, float] | None]:
    """One reference per setup sheet.

    Ride height and spring rate are setup values, so a single event-wide
    reference is a reference to one of the sheets that ran. Measured on the
    owner's Monza event, whose two sheets differ by 4.8-13.6 mm against a 3 mm
    band, that silenced `bottoming` on every lap run on the other sheet — all
    545 of them.
    """
    by_sheet: dict[object, list[CountedLap]] = {}
    for lap in laps:
        by_sheet.setdefault(lap.setup_sheet_id, []).append(lap)
    return {sheet: bottoming_reference(group, model)
            for sheet, group in by_sheet.items()}


def bottoming_inferable(laps: list[CountedLap],
                        reference: dict[str, float] | None) -> set[str]:
    """Wheels whose trace actually moves enough to infer bottoming from.

    A suspension trace that never varies sits in the band on every frame of
    every corner. A trace that does not move cannot tell you the car reached
    its bump stops — it tells you nothing.

    Measured from the compressed end, so the test is how far the typical frame
    sits BELOW the reference rather than above it. See `_most_compressed`.
    """
    if not reference:
        return set()
    inferable = set()
    frames = [f for lap in laps for f in lap.frames]
    for wheel, values in _suspension_by_wheel(frames).items():
        limit = reference.get(wheel)
        if limit is None or not values:
            continue
        typical = median(values)
        if limit - typical > thresholds.BOTTOMING_BAND_MM:
            inferable.add(wheel)
    return inferable


def aggregate_corners(model: CornerModel, laps: list[CountedLap],
                      bottoming_ref: dict[str, float] | None = None,
                      *, drivetrain: str | None = None,
                      wheelbase_m: float | None = None) -> list[dict]:
    """The `corners` array. Corners no lap reached are omitted, not zeroed.

    `bottoming_ref` is a fallback applied to any setup sheet whose own
    straight-line reference could not be derived. The per-sheet references come
    from the laps themselves, because a reference passed in from outside cannot
    know which sheet each lap was run on.
    """
    references = bottoming_references(laps, model)
    context: dict[object, tuple[dict | None, set[str]]] = {}
    for sheet, reference in references.items():
        reference = reference or bottoming_ref
        group = [lap for lap in laps if lap.setup_sheet_id == sheet]
        context[sheet] = (reference, bottoming_inferable(group, reference))

    out: list[dict] = []
    for corner in model.corners:
        per_lap = []
        for lap in laps:
            window = _slice(lap.frames, corner)
            if len(window) < 2:
                continue
            approach = _approach(lap.frames, corner)
            reference, inferable = context[lap.setup_sheet_id]
            per_lap.append(
                _measure(window, approach, corner, lap.interval_ms,
                         reference, inferable, drivetrain, wheelbase_m))
        if not per_lap:
            continue
        out.append(_combine(corner, per_lap))
    return out


def _measure(window: list[dict], approach: list[dict], corner: Corner,
             interval_ms: float,
             bottoming_ref: dict[str, float] | None,
             bottoming_wheels: set[str],
             drivetrain: str | None,
             wheelbase_m: float | None) -> dict:
    """Everything measurable about one corner on one lap."""
    speeds = [f["speed_kph"] for f in window]
    brakes = [f["brake_pct"] for f in window]
    throttles = [f["throttle_pct"] for f in window]

    deficit, deficit_frames = yaw_deficit_pct(window, interval_ms, wheelbase_m)
    measurement = {
        "time_ms": window[-1]["t_ms"] - window[0]["t_ms"],
        "entry_kph": speeds[0],
        "min_kph": min(speeds),
        "exit_kph": speeds[-1],
        "brake_peak_pct": max(brakes),
        "brake_point_m": _brake_point_m(approach, corner),
        "throttle_on_pct": _throttle_on_pct(window, corner),
        "steer_peak_deg": _peak_abs(window, "steering_deg"),
        "steer_peak_norm": _peak_signed(window, "steering_norm"),
        "trail_brake_ms": _trail_brake_ms(window, interval_ms),
        "gear_min": _gear_min(window),
        "gear_at_apex": _gear_at(window, _apex_index(window)),
        "gear_at_exit": _gear_at(window, len(window) - 1),
        "shifts": _shift_count(window),
        "upshift_rpm": _first_upshift_rpm(window),
        "susp_min_mm": _suspension_minima(window),
        "surface_counts": _surface_counts(window),
        # A magnitude, and it gates nothing. See `yaw_deficit_pct` for why the
        # boolean it replaced was measuring entry speed.
        "yaw_deficit_pct": deficit,
        "yaw_deficit_frames": deficit_frames,
        "flags": _flags(window, interval_ms, bottoming_ref, bottoming_wheels,
                        drivetrain, wheelbase_m),
    }
    _ = throttles  # read via _throttle_on_pct; kept explicit for clarity
    return measurement


def _brake_point_m(approach: list[dict], corner: Corner) -> float | None:
    """Metres before the apex at which braking began.

    Walks back from the apex to the start of the last continuous braking run,
    so a brake application that began out on the straight is measured from
    where it actually began rather than from where the corner window opens.

    None when the corner was taken without braking — a finding in itself, and
    not the same claim as braking zero metres before the apex. **The run has to
    reach this corner's own window**: without that the search kept walking back
    down the straight and returned the *previous* corner's braking. The shipped
    export said he braked 560 m before T3, a corner he takes flat with a peak
    brake of 2.8%.
    """
    if not approach:
        return None

    index = len(approach) - 1
    while index >= 0 and approach[index]["brake_pct"] <= thresholds.BRAKE_ON_PCT:
        index -= 1
    if index < 0:
        return None
    if approach[index]["lap_distance_m"] < corner.start_m:
        return None

    while index > 0 and approach[index - 1]["brake_pct"] > thresholds.BRAKE_ON_PCT:
        index -= 1
    return round(corner.apex_m - approach[index]["lap_distance_m"], 1)


def _throttle_on_pct(window: list[dict], corner: Corner) -> float | None:
    """How far through the corner the throttle first came on, as a percentage."""
    span = corner.end_m - corner.start_m
    if span <= 0:
        return None
    for frame in window:
        if frame["throttle_pct"] > thresholds.THROTTLE_ON_PCT:
            through = (frame["lap_distance_m"] - corner.start_m) / span
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


def _apex_index(window: list[dict]) -> int:
    """Minimum-speed point, the same apex the brake point is measured from."""
    speeds = [f["speed_kph"] for f in window]
    return speeds.index(min(speeds))


def _gear_min(window: list[dict]) -> int | None:
    gears = [f.get("gear") for f in window if f.get("gear")]
    return min(gears) if gears else None


def _gear_at(window: list[dict], index: int) -> int | None:
    if not 0 <= index < len(window):
        return None
    return window[index].get("gear") or None


def _shift_count(window: list[dict]) -> int:
    """Gear changes inside the corner, which is what answers "does 2nd cover
    all three chicanes without an upshift"."""
    shifts = 0
    previous = None
    for frame in window:
        gear = frame.get("gear")
        if not gear:
            continue
        if previous is not None and gear != previous:
            shifts += 1
        previous = gear
    return shifts


def _first_upshift_rpm(window: list[dict]) -> float | None:
    """Engine speed at the first upshift after the apex.

    This is how short-shifting becomes visible: an upshift well below the
    limiter is a choice, and it costs pace while saving fuel and rear tyre.
    """
    start = _apex_index(window)
    previous = window[start].get("gear")
    for frame in window[start:]:
        gear = frame.get("gear")
        if not gear:
            continue
        if previous and gear > previous:
            return frame.get("rpm")
        previous = gear
    return None


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
           bottoming_wheels: set[str],
           drivetrain: str | None = None,
           wheelbase_m: float | None = None) -> set[str]:
    flags: set[str] = set()

    # Contract 7.1 puts `wheelspin` on the driven wheels and `lockup` on any
    # wheel. GT7 sends no drivetrain channel, so where the caller has not said
    # what drives the car this falls back to all four — and
    # `thresholds.as_export` declares that it did.
    driven = thresholds.wheelspin_wheels(drivetrain)
    wheelspin_ratio = 1.0 + thresholds.WHEELSPIN_PCT / 100.0
    lockup_ratio = 1.0 - thresholds.LOCKUP_PCT / 100.0
    for frame in window:
        if frame["throttle_pct"] > thresholds.THROTTLE_ON_PCT:
            spinning = _defined([frame.get(f"slip_{w}") for w in driven])
            if spinning and max(spinning) > wheelspin_ratio:
                flags.add("wheelspin")
        if frame["brake_pct"] > thresholds.BRAKE_ON_PCT:
            slips = _defined([frame.get(f"slip_{w}")
                              for w in thresholds.ALL_WHEELS])
            if slips and min(slips) < lockup_ratio:
                flags.add("lockup")

    corrections = _countersteered(window, interval_ms)
    if corrections:
        flags.add("countersteer")
        # **The same moment**, not the same corner. Two whole-window tests
        # ANDed together raised this on a correction at the exit and a
        # trail-brake at the entry hundreds of ms apart, which on a driver who
        # trail-brakes deep by design is every corner he takes: 31.2% of
        # windows against 0.5% for the contract's rule.
        if any(_in_trail_brake_window(window[k])
               for start, end in corrections
               for k in range(start, end + 1)):
            flags.add("trail-brake-instability")


    if _off_track(window):
        flags.add("off-track")

    if _bottomed(window, interval_ms, bottoming_ref, bottoming_wheels):
        flags.add("bottoming")

    if _kerb_struck(window, interval_ms):
        flags.add("kerb-strike")

    return flags


def _sign(value: float) -> int:
    return 1 if value > 0 else (-1 if value < 0 else 0)


def _corner_direction(window: list[dict]) -> int:
    """Which way the corner goes, from the steering at the apex frame."""
    steering = window[_apex_index(window)].get("steering_deg")
    return 0 if steering is None else _sign(steering)


def _countersteered(window: list[dict],
                    interval_ms: float) -> list[tuple[int, int]]:
    """Frame pairs where the driver corrected against the corner.

    Returns the reversals' own frame indices rather than a bool, so that
    `trail-brake-instability` can ask whether the correction and the trail
    braking were the same moment.

    A bare sign reversal is not enough. An auto-segmented corner is one speed
    minimum, so a chicane is a single window and its left-right transition
    clears 10° by construction — measured, the bare test marked Monza's three
    chicanes on 82, 76 and 75 laps of 91. So the reversal has to start from the
    corner's own direction, and the opposite lock has to be a dab rather than
    the corner's second direction: either the wheel comes back, or the counter
    lock never approaches the lock used in the corner's own direction.
    """
    direction = _corner_direction(window)
    if direction == 0:
        return []
    span = _frames_for_ms(thresholds.COUNTERSTEER_WINDOW_MS, interval_ms)
    angles = [f.get("steering_deg") for f in window]

    own_peak = max((abs(a) for a in angles
                    if a is not None and _sign(a) == direction), default=0.0)
    counter_peak = max((abs(a) for a in angles
                        if a is not None and _sign(a) == -direction), default=0.0)
    stayed_a_dab = own_peak > 0 and (
        counter_peak / own_peak <= thresholds.COUNTERSTEER_RETURN_FRACTION)

    found: list[tuple[int, int]] = []
    for i, angle in enumerate(angles):
        if angle is None or abs(angle) < thresholds.COUNTERSTEER_DEG:
            continue
        if _sign(angle) != direction:
            continue
        for j in range(i + 1, min(i + span + 1, len(angles))):
            other = angles[j]
            if other is None or abs(other) < thresholds.COUNTERSTEER_DEG:
                continue
            if _sign(other) == direction:
                continue
            if stayed_a_dab or _returns_to(angles, j, direction):
                found.append((i, j))
            break
    return found


def _returns_to(angles: list[float | None], after: int, direction: int) -> bool:
    """Whether the wheel comes back to the corner's own direction."""
    for angle in angles[after + 1:]:
        if angle is not None and abs(angle) >= thresholds.COUNTERSTEER_DEG \
                and _sign(angle) == direction:
            return True
    return False


def _in_trail_brake_window(frame: dict) -> bool:
    steering = frame.get("steering_norm")
    return (steering is not None
            and frame["brake_pct"] > thresholds.TRAIL_BRAKE_MIN_BRAKE_PCT
            and abs(steering) * 100.0 > thresholds.TRAIL_BRAKE_STEER_PCT)


def _expected_yaw_rad_s(frame: dict, wheelbase_m: float) -> float | None:
    """What speed and steering imply the car should be rotating at.

    The kinematic form, carrying a measured gain. Pure Ackermann over-predicts
    a race car at the limit about fivefold, because at the limit most of the
    steer angle is tyre slip angle rather than path curvature — so the gain is
    calibrated on real laps and declared with the threshold it feeds.
    """
    steer = frame.get("steering_deg")
    speed = frame.get("speed_kph")
    if steer is None or speed is None:
        return None
    if speed < thresholds.UNDERSTEER_MIN_SPEED_KPH:
        return None
    if abs(steer) < thresholds.UNDERSTEER_MIN_STEER_DEG:
        return None
    return (thresholds.UNDERSTEER_YAW_GAIN * (speed / 3.6)
            * abs(steer) / 180.0 / wheelbase_m)


def yaw_deficit_pct(window: list[dict], interval_ms: float,
                    wheelbase_m: float | None) -> tuple[float | None, int]:
    """How far short of the lock's implied rotation the car turned, in percent.

    **This replaced the `understeer-mid` flag, which measured entry speed.**
    The rule was: flag when steering rises while yaw sits below
    `UNDERSTEER_YAW_DEFICIT` of `GAIN * speed * steer/180 / wheelbase`. Expected
    yaw in that expression is proportional to speed; achieved yaw for a car at
    its grip limit is `v/R`, and with `v^2/R = mu*g` that is `mu*g/v` -
    INVERSELY proportional. So the achieved/expected ratio falls as 1/v^2 for
    any car driven at the limit, whatever its balance, and unless downforce
    raises mu as fast as v^2 **a perfectly neutral car flags more at speed by
    construction.** The gain was calibrated as a median over 154,714 frames
    across all speeds, so it is right at the median speed and wrong at both
    ends in opposite directions.

    Sorted by entry speed, Watkins over 17 laps: T2 204 km/h 15/17, T8 194
    15/17, T9 170 12/17, T4 153 7/17, T1 144 7/17, T6 134 0/17, T5 133 0/17,
    T7 120 0/17. Near-monotone, switching off entirely below 135 km/h, with
    T3 the lone outlier - and T3 is the one fast corner taken with no brake
    and the least steering. A genuine front-grip fault would track LOAD, not
    raw speed. The driver reported no understeer across four sessions while
    the flag fired at six or seven corners of nine in every one of them.

    So the boolean is gone and the magnitude is exported instead. A lap count
    at six of nine corners is not tunable; "twelve percent short of the lock's
    implied rotation, at 204 km/h entry" is something a reader can weigh
    against the speed beside it and against what the driver actually felt.
    **It gates nothing.** Nothing downstream may turn it back into a flag
    without first removing the speed structure above.

    Returns `(median percent short, qualifying frames)`. Positive is short of
    expectation; negative means the car rotated MORE than the lock implied.
    `(None, 0)` where no frame in the window could be judged - which is not
    zero deficit, and must not be read as one.
    """
    wheelbase_m = wheelbase_m or thresholds.DEFAULT_WHEELBASE_M
    rise_per_frame = thresholds.UNDERSTEER_STEER_RISE_DEG_S * interval_ms / 1000.0

    deficits: list[float] = []
    previous_steer = None
    for frame in window:
        steer = frame.get("steering_deg")
        yaw = frame.get("yaw_rate")
        # A None yaw is "the car was not moving enough to say", not "the car
        # was not rotating" - the second reading would make a standstill the
        # strongest understeer signal there is.
        if steer is not None and yaw is not None and previous_steer is not None:
            expected = _expected_yaw_rad_s(frame, wheelbase_m)
            adding_lock = abs(steer) - abs(previous_steer) >= rise_per_frame
            if expected and adding_lock:
                deficits.append(100.0 * (1.0 - abs(yaw) / expected))
        previous_steer = steer
    if not deficits:
        return None, 0
    return round(median(deficits), 1), len(deficits)


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
    needed = _frames_for_ms(thresholds.BOTTOMING_MIN_MS, interval_ms)
    streak = 0
    for frame in window:
        in_band = False
        for wheel in bottoming_wheels:
            reference = bottoming_ref.get(wheel)
            if reference is None:
                continue
            travel = frame.get(f"susp_mm_{wheel}")
            if travel is not None and travel >= reference - thresholds.BOTTOMING_BAND_MM:
                in_band = True
                break
        streak = streak + 1 if in_band else 0
        if streak >= needed:
            return True
    return False


def _kerb_struck(window: list[dict], interval_ms: float) -> bool:
    span = _frames_for_ms(thresholds.KERB_STRIKE_WINDOW_MS, interval_ms)
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


def _modal(values: list):
    """Most common value, or None. Used where a mean would be nonsense."""
    present = _defined(values)
    if not present:
        return None
    return max(set(present), key=present.count)


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

    # A flag raised on one lap in forty and a flag raised on thirty-eight are
    # not the same claim, and a set union makes them identical: run enough laps
    # and every flag fires somewhere, so every corner ends up carrying every
    # flag and the section stops saying anything. Standing rule 4 - every
    # aggregate carries its sample count - applies to flags too, so each one
    # travels with the number of laps it fired on.
    flag_counts: dict[str, int] = {}
    for measurement in per_lap:
        for flag in measurement["flags"]:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
    flags = sorted(name for name, count in flag_counts.items()
                   if count >= max(1, round(len(per_lap) * thresholds.FLAG_MIN_SHARE)))

    gear_mins = [m["gear_min"] for m in per_lap if m["gear_min"]]

    # **A mean is only over the laps that carried the channel.** `samples`
    # counts the laps that reached the corner, and publishing a sparse mean
    # under it overstates the claim: the shipped export carried
    # `upshiftRpm: 7787` under `samples: 23` beside `shiftsInCorner: 0.09`,
    # which is two laps' evidence presented as twenty-three. Standing rule 4 -
    # every aggregate carries its sample count - is about the aggregate, not
    # about the corner.
    def counted(key: str) -> int:
        return len(_defined([m[key] for m in per_lap]))

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
        "brakePointSamples": counted("brake_point_m"),
        "trailBrakeMs": _round_or_none(
            _mean_or_none([m["trail_brake_ms"] for m in per_lap])),
        "trailBrakeSamples": counted("trail_brake_ms"),
        "steerPeakDeg": _round_or_none(
            _mean_or_none([m["steer_peak_deg"] for m in per_lap]), 2),
        "steerPeakNorm": _round_or_none(
            _mean_or_none([m["steer_peak_norm"] for m in per_lap]), 3),
        "steerPeakSamples": counted("steer_peak_deg"),
        "throttleOnPct": _round_or_none(
            _mean_or_none([m["throttle_on_pct"] for m in per_lap])),
        "throttleOnSamples": counted("throttle_on_pct"),
        # **The rotation shortfall, as a number, gating nothing.** Positive is
        # short of what the lock implied; negative means the car rotated more.
        # Read it beside `entrySpeedKph`, because the expression behind it has
        # a 1/v^2 structure that the flag it replaced could not survive - see
        # `yaw_deficit_pct`. Null where no frame in any lap could be judged,
        # which is not zero deficit.
        "yawDeficitPct": _round_or_none(
            _mean_or_none([m["yaw_deficit_pct"] for m in per_lap]), 1),
        "yawDeficitSamples": counted("yaw_deficit_pct"),
        "yawDeficitFrames": sum(m["yaw_deficit_frames"] for m in per_lap),
        "timeLossVsBestMs": round(mean(times) - best_time),
        "consistencyMs": round(pstdev(times)) if len(times) > 1 else None,
        # Modal, not mean: a mean gear of 2.6 is not a gear.
        "gearMin": _modal(gear_mins),
        "gearAtApex": _modal([m["gear_at_apex"] for m in per_lap]),
        "gearAtExit": _modal([m["gear_at_exit"] for m in per_lap]),
        # A fraction is meaningful here - 0.4 means he shifted on four laps
        # in ten, which is exactly the inconsistency worth seeing.
        "shiftsInCorner": _round_or_none(
            _mean_or_none([m["shifts"] for m in per_lap]), 2),
        "upshiftRpm": _round_or_none(
            _mean_or_none([m["upshift_rpm"] for m in per_lap]), 0),
        "upshiftRpmSamples": counted("upshift_rpm"),
        "suspHeightMinMm": susp_min,
        "surfaceMix": surface_mix,
        # Only the ones that happen often enough to describe the corner rather
        # than one moment in it. `flagLaps` carries every flag seen, with the
        # laps it fired on, so a one-off is still visible - as a one-off.
        "flags": flags,
        "flagLaps": dict(sorted(flag_counts.items())),
        "flagThresholdLaps": max(1, round(len(per_lap) * thresholds.FLAG_MIN_SHARE)),
    }
    return payload
