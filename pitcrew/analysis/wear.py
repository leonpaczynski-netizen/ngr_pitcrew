"""Tyre wear — modelled, never measured.

**GT7 exposes no tyre wear channel in any packet format.** This module exists to
make that explicit rather than to hide it, so every figure it produces carries
its source and its confidence.

Three corroborating sources, in descending reliability:

1. **The driver's gauge reading.** Coarse, but the only number anchored to the
   game's own model. If it is present, it wins.
2. **Lap-time degradation** against a fresh-tyre reference.
3. **Tyre temperature trend** and front/rear asymmetry.

Degradation is **piecewise, not linear** (CLAUDE.md §5.1): near-flat to ~50%
worn, progressive from ~50 to ~90%, then a cliff where the car is undriveable
rather than merely slow. So a rate is never reported without saying which phase
it was fitted in, and stint length is `0.85 / w` — deliberately short of the
cliff, because overshooting costs far more than undershooting.
"""
from __future__ import annotations

from statistics import mean

from pitcrew.analysis.session import LapInput, counted_laps, green_lap_reference_ms

# Stop the stint at 85% of the modelled tyre life. The cliff's onset is sharp
# and the cost is asymmetric, so the margin is deliberate and is stated in
# `modelBasis` on every export.
STINT_SAFETY_FACTOR = 0.85

PHASE_FLAT = "flat"        # 0 - 50% worn
PHASE_LINEAR = "linear"    # 50 - 90%
PHASE_CLIFF = "cliff"      # > 90%


def phase_for(fraction_consumed: float | None) -> str | None:
    if fraction_consumed is None:
        return None
    if fraction_consumed < 0.5:
        return PHASE_FLAT
    if fraction_consumed <= 0.9:
        return PHASE_LINEAR
    return PHASE_CLIFF


def gauge_readings(laps: list[LapInput]) -> list[dict]:
    """The driver's own gauge readings, in lap order."""
    out = []
    for lap in laps:
        if lap.wear_front is None and lap.wear_rear is None:
            continue
        out.append({
            "lap": lap.lap_num,
            "front": lap.wear_front,
            "rear": lap.wear_rear,
            "source": "driver-gauge",
        })
    return out


def wear_per_lap(laps: list[LapInput]) -> float | None:
    """Fraction consumed per lap, from the driver's readings only.

    Uses the worst axle, because the stint ends when either end is done.
    Returns None without at least one reading — this figure drives every stint
    recommendation and must never be invented.
    """
    readings = gauge_readings(laps)
    if not readings:
        return None
    last = readings[-1]
    worst = max(v for v in (last["front"], last["rear"]) if v is not None)
    if worst <= 0:
        return None
    laps_run = max(1, last["lap"])
    return worst / laps_run


def modelled_stint_laps(laps: list[LapInput]) -> int | None:
    per_lap = wear_per_lap(laps)
    if not per_lap:
        return None
    return int(STINT_SAFETY_FACTOR / per_lap)


def degradation_ms_per_lap(laps: list[LapInput]) -> float | None:
    """Lap-time drift across the counted laps, in ms per lap.

    A straight-line fit, which the contract permits only because it is reported
    alongside the phase it was fitted in. It is not a wear model on its own.
    """
    counted = counted_laps(laps)
    if len(counted) < 3:
        return None
    first_half = counted[:len(counted) // 2]
    second_half = counted[len(counted) // 2:]
    gap_laps = mean([lap.lap_num for lap in second_half]) - \
        mean([lap.lap_num for lap in first_half])
    if gap_laps <= 0:
        return None
    drift = mean([lap.lap_time_ms for lap in second_half]) - \
        mean([lap.lap_time_ms for lap in first_half])
    return round(drift / gap_laps, 1)


def temperature_trend(laps: list[LapInput]) -> dict | None:
    """Front/rear asymmetry and drift per lap, degrees C."""
    per_lap = []
    for lap in counted_laps(laps):
        if not lap.frames:
            continue
        fronts, rears = [], []
        for frame in lap.frames:
            for wheel, bucket in (("fl", fronts), ("fr", fronts),
                                  ("rl", rears), ("rr", rears)):
                value = frame.get(f"temp_{wheel}")
                if value is not None:
                    bucket.append(value)
        if fronts and rears:
            per_lap.append((lap.lap_num, mean(fronts), mean(rears)))
    if not per_lap:
        return None

    asymmetry = mean([front - rear for _, front, rear in per_lap])
    trend = None
    if len(per_lap) >= 3:
        half = len(per_lap) // 2
        early = mean([front for _, front, _ in per_lap[:half]])
        late = mean([front for _, front, _ in per_lap[half:]])
        span = per_lap[-1][0] - per_lap[0][0]
        if span > 0:
            trend = round((late - early) / span, 2)

    return {
        "frontRearAsymmetryC": round(asymmetry, 1),
        "trendCPerLap": trend,
        "source": "tyre-temp-trend",
        "confidence": "low",
    }


def wear_export(laps: list[LapInput], *,
                calibrated_at_race_multiplier: bool = True) -> dict:
    """The `wear` object.

    `calibrated_at_race_multiplier` is False when the numbers came from a run at
    a different tyre-wear multiplier. Multiplier linearity is assumed and has
    never been demonstrated, so a converted figure is labelled `converted` and
    must never be presented as measured.
    """
    readings = gauge_readings(laps)
    per_lap = wear_per_lap(laps)
    stint_laps = modelled_stint_laps(laps)

    payload: dict = {
        "channelAvailable": False,
        "byDriverGauge": readings,
        "modelledStintLaps": stint_laps,
    }

    reference = green_lap_reference_ms(laps)
    degradation = degradation_ms_per_lap(laps)
    if reference is not None and degradation is not None:
        final_fraction = None
        if readings:
            values = [v for v in (readings[-1]["front"], readings[-1]["rear"])
                      if v is not None]
            final_fraction = max(values) if values else None
        payload["byLapTime"] = {
            "refLapMs": reference,
            "degradationMsPerLap": degradation,
            "phase": phase_for(final_fraction),
            "estimatedFractionAtEnd": final_fraction,
            "source": "lap-time-model",
            "confidence": "low",
        }

    temps = temperature_trend(laps)
    if temps is not None:
        payload["byTemp"] = temps

    if per_lap is None:
        payload["modelBasis"] = "no gauge reading entered; stint length unknown"
        payload["modelConfidence"] = "assumed"
    elif calibrated_at_race_multiplier:
        payload["modelBasis"] = (
            f"{STINT_SAFETY_FACTOR} / w, w measured in-house at this multiplier")
        payload["modelConfidence"] = "measured"
    else:
        payload["modelBasis"] = (
            f"{STINT_SAFETY_FACTOR} / w, w scaled from a different multiplier "
            "[ASSUMED - multiplier linearity is not demonstrated]")
        payload["modelConfidence"] = "converted"

    return payload
