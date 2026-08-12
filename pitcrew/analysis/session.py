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
    # The driver's gauge reading per corner, fraction consumed 0-1. Same
    # vocabulary as the tyre temperatures below, so a wear figure and the
    # temperature that explains it are named the same thing.
    wear_fl: float | None = None
    wear_fr: float | None = None
    wear_rl: float | None = None
    wear_rr: float | None = None
    gear_ratios: list[float] | None = None
    frames: list[dict] | None = None

    @property
    def counted(self) -> bool:
        """Out-laps, in-laps and anything the driver excluded do not count."""
        return not (self.excluded or self.is_out_lap or self.is_pit_lap)

    @property
    def wear_by_corner(self) -> dict[str, float | None]:
        return {"fl": self.wear_fl, "fr": self.wear_fr,
                "rl": self.wear_rl, "rr": self.wear_rr}

    @property
    def worst_wear(self) -> float | None:
        """The most-consumed corner, or None if he read no corner at all.

        This is the figure a stint is planned against: the tyre that runs out
        first ends the stint, and averaging it against three healthier corners
        is how a plan overshoots the cliff.
        """
        read = [v for v in self.wear_by_corner.values() if v is not None]
        return max(read) if read else None

    @property
    def worst_corner(self) -> str | None:
        """Which corner is going first — the finding, not just the number.

        None when nothing was read, and None when more than one corner shares
        the highest reading. Naming one of a tied pair invents an asymmetry
        the driver never reported, and an invented asymmetry is exactly the
        kind of thing a setup gets built on. The rate is still knowable in
        that case — `worst_wear` — it is only the *which* that is not.
        """
        read = {k: v for k, v in self.wear_by_corner.items() if v is not None}
        if not read:
            return None
        highest = max(read.values())
        tied = [corner for corner, value in read.items() if value == highest]
        return tied[0] if len(tied) == 1 else None

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
