"""Per-lap and run-level aggregation — the `laps` and `session` sections.

Tyre temperature is the one channel GT7 gives that maps directly onto load
distribution, so it is exported per corner of the car, mean *and* max: the mean
gives the working range, the max shows what is being abused. That pair is the
strongest available evidence for a front-left overload pattern.

Two contract details that are easy to get wrong:

* **Median, not mean, for the representative lap time.** One bad lap should not
  move the number.
* **`fuelCapacityL` of 0 is a real value** — electric cars. Guard the divide;
  do not treat it as missing.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median, pstdev

from pitcrew.analysis import thresholds

# Tyres are freshest at the start of a stint, so the degradation reference is
# taken from the earliest counted laps rather than from the session's best lap,
# which may have come late on worn rubber after the track rubbered in.
GREEN_LAP_WINDOW = 3


@dataclass(frozen=True)
class LapInput:
    """One recorded lap plus its frames, as the export sees it."""
    lap_num: int
    lap_time_ms: int
    fuel_start: float
    fuel_end: float
    compound: str | None = None
    fuel_map: int | None = None
    is_pit_lap: bool = False
    is_out_lap: bool = False
    excluded: bool = False
    exclusion_reason: str | None = None
    wear_front: float | None = None
    wear_rear: float | None = None
    frames: list[dict] | None = None

    @property
    def counted(self) -> bool:
        """Out-laps, in-laps and anything the driver excluded do not count."""
        return not (self.excluded or self.is_out_lap or self.is_pit_lap)

    def reason_not_counted(self) -> str | None:
        if self.counted:
            return None
        if self.exclusion_reason:
            return self.exclusion_reason
        if self.is_out_lap:
            return "out-lap"
        if self.is_pit_lap:
            return "in-lap"
        return "excluded"


def _tyre_temps(frames: list[dict] | None) -> tuple[dict | None, dict | None]:
    if not frames:
        return None, None
    means, maxima = {}, {}
    for wheel in ("fl", "fr", "rl", "rr"):
        values = [f[f"temp_{wheel}"] for f in frames
                  if f.get(f"temp_{wheel}") is not None]
        if not values:
            return None, None
        means[wheel] = round(mean(values), 1)
        maxima[wheel] = round(max(values), 1)
    return means, maxima


def _off_track_count(frames: list[dict] | None) -> int | None:
    """Excursions, not frames — one long off is one event, not two hundred.

    None when no surface channel was captured, because zero excursions and no
    way to tell are different claims.
    """
    if not frames:
        return None
    if all(f.get("surf_fl") is None for f in frames):
        return None
    count = 0
    outside = False
    for frame in frames:
        surfaces = [frame.get(f"surf_{w}") for w in ("fl", "fr", "rl", "rr")]
        surfaces = [s for s in surfaces if s is not None]
        now_outside = any(s not in thresholds.ON_TRACK_SURFACES for s in surfaces)
        if now_outside and not outside:
            count += 1
        outside = now_outside
    return count


def lap_export(lap: LapInput) -> dict:
    """One object of the `laps` array."""
    means, maxima = _tyre_temps(lap.frames)
    return {
        "lap": lap.lap_num,
        "timeMs": lap.lap_time_ms,
        "valid": lap.counted,
        "fuelStartL": round(lap.fuel_start, 2),
        "fuelEndL": round(lap.fuel_end, 2),
        "fuelMap": lap.fuel_map,
        "tyreTempMeanC": means,
        "tyreTempMaxC": maxima,
        "offTrackCount": _off_track_count(lap.frames),
    }


def counted_laps(laps: list[LapInput]) -> list[LapInput]:
    return [lap for lap in laps if lap.counted]


def green_lap_reference_ms(laps: list[LapInput]) -> int | None:
    """The fresh-tyre lap any degradation figure is measured against."""
    counted = counted_laps(laps)
    if not counted:
        return None
    window = counted[:GREEN_LAP_WINDOW]
    return min(lap.lap_time_ms for lap in window)


def session_export(laps: list[LapInput],
                   fuel_capacity_l: float | None = None) -> dict:
    """The `session` object."""
    counted = counted_laps(laps)
    times = [lap.lap_time_ms for lap in counted]

    fuel_per_lap = None
    burns = [lap.fuel_start - lap.fuel_end for lap in counted
             if lap.fuel_start > lap.fuel_end]
    if burns:
        fuel_per_lap = round(median(burns), 3)

    payload = {
        "lapsRun": len(laps),
        "lapsCounted": len(counted),
        "lapsExcluded": [lap.lap_num for lap in laps if not lap.counted],
        "fuelUsedPerLapL": fuel_per_lap,
        "fuelCapacityL": fuel_capacity_l,
        "bestLapMs": min(times) if times else None,
        "medianLapMs": round(median(times)) if times else None,
        "lapTimeStdDevMs": round(pstdev(times)) if len(times) > 1 else None,
        "greenLapRefMs": green_lap_reference_ms(laps),
    }
    return payload


def exclusion_note(laps: list[LapInput]) -> str:
    """Prose for `notes` saying which laps were dropped and why."""
    dropped = [(lap.lap_num, lap.reason_not_counted())
               for lap in laps if not lap.counted]
    if not dropped:
        return ""
    parts = [f"lap {num} {reason}" for num, reason in dropped]
    return "Excluded: " + ", ".join(parts) + "."


def laps_per_stint(laps: list[LapInput]) -> list[list[LapInput]]:
    """Split at every pit lap, so wear is never fitted across a tyre change."""
    stints: list[list[LapInput]] = [[]]
    for lap in laps:
        stints[-1].append(lap)
        if lap.is_pit_lap:
            stints.append([])
    return [stint for stint in stints if stint]
