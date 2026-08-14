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
    # `auto` when the app found the reason itself, `driver` when he struck the
    # lap by hand. Set by `runs.classify_exclusions`, so that a reason the app
    # could have worked out is never left reading as an unexplained strike.
    exclusion_source: str | None = None
    # What the driver actually typed, where the vocabulary cannot hold it.
    # "spun at T4" survives being classified `manual`; "struck by hand" does
    # not, because it says nothing the classification does not.
    driver_note: str | None = None
    # Which recorded session this lap came from. A stop-and-restart means the
    # car went back to the garage, so laps either side are not one stint.
    session_id: int | None = None
    # The driver's declaration that this lap started on a fresh set. `None`
    # means he has not said — never `False`, which would claim the set carried
    # over. His word is primary evidence and outranks everything below it.
    tyres_fresh: bool | None = None
    # **Observed at a stop on this lap**, not declared: all four corners
    # stepped to one temperature in a single frame, which is what GT7 does
    # when it fits a set. `None` where the lap carried no stop — the question
    # was not asked. Kept apart from `tyres_fresh` so that the driver saying
    # one thing and the stream showing another stays a finding rather than
    # one silently overwriting the other.
    tyres_changed: bool | None = None
    # The driver's gauge reading per corner, fraction consumed 0-1. Same
    # vocabulary as the tyre temperatures below, so a wear figure and the
    # temperature that explains it are named the same thing.
    wear_fl: float | None = None
    wear_fr: float | None = None
    wear_rl: float | None = None
    wear_rr: float | None = None
    gear_ratios: list[float] | None = None
    # GT7's clock at the lap's first and last frame. Stored on the lap so the
    # clock can be read across a whole session without decoding a single frame
    # blob — see `analysis/gameclock`.
    tod_start_ms: int | None = None
    tod_end_ms: int | None = None
    # How long the car sat before setting off. Only the session's first lap
    # has anything to say with it: it corroborates which kind of session this
    # was, and it never overrules what the driver declared.
    standing_start_ms: int | None = None
    # `lobby` or `time-trial`, from the session this lap belongs to.
    practice_mode: str | None = None
    # **Something happened on this lap** — it lost time and the frames say
    # why. It leaves the counted set, because a spin averaged into a stint
    # invents degradation that never happened, and it stays in the diagnostic
    # set, because the car is what spun. See `analysis/incidents`.
    incident: bool = False
    incident_note: str | None = None
    # The three numbers `analysis.incidents` needs, taken once at capture so
    # no frame blob has to be decoded to ask whether a lap had an off in it.
    # None where the lap's frames were never captured.
    crawl_s: float | None = None
    off_track_s: float | None = None
    spin_s: float | None = None
    frames: list[dict] | None = None

    @property
    def counted(self) -> bool:
        """What pace, fuel and the strategy model are allowed to read.

        Out-laps, in-laps, anything the driver excluded, and any lap with an
        incident in it. Deliberately narrower than `diagnostic`: a lap with a
        spin in it is worthless as a pace sample and valuable as evidence
        about the car, and those two facts need different sets.
        """
        return not (self.excluded or self.is_out_lap or self.is_pit_lap
                    or self.incident)

    @property
    def diagnostic(self) -> bool:
        """What the corner aggregates are allowed to read.

        Wider than `counted` by exactly the incident laps. He asked for them
        out of strategy and kept for setup advice, and both halves are right:
        the car is what spun, so the lap where it spun is the lap that says
        so.
        """
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


def diagnostic_laps(laps: list[LapInput]) -> list[LapInput]:
    """Laps the corner aggregates may read — `counted` plus the incidents."""
    return [lap for lap in laps if lap.diagnostic]


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
        "lapsExcludedDetail": exclusions_export(laps),
        "fuelUsedPerLapL": fuel_per_lap,
        "fuelCapacityL": fuel_capacity_l,
        "bestLapMs": min(times) if times else None,
        "medianLapMs": round(median(times)) if times else None,
        "lapTimeStdDevMs": round(pstdev(times)) if len(times) > 1 else None,
        "greenLapRefMs": green_lap_reference_ms(laps),
    }
    return payload


def exclusions_export(laps: list[LapInput]) -> list[dict]:
    """Why each dropped lap was dropped, and who worked it out.

    The flat `lapsExcluded` array says which laps went; this says why. Eight
    repetitions of "struck by hand" in `notes` qualified nothing — and half of
    them were out-laps the refuel boundary names for free.
    """
    out = []
    for lap in laps:
        if lap.counted:
            continue
        entry = {
            "lap": lap.lap_num,
            "reason": lap.reason_not_counted(),
            "source": lap.exclusion_source or "driver",
        }
        if lap.driver_note:
            entry["note"] = lap.driver_note
        out.append(entry)
    return out


def exclusion_note(laps: list[LapInput]) -> str:
    """Prose for `notes`, only where the structure cannot carry it.

    `session.lapsExcludedDetail` carries the reason and its source per lap, so
    repeating them here would be eight sentences saying what the structure
    already says. What is left for prose is a driver's own words where they say
    more than the vocabulary does.
    """
    stated = [(lap.lap_num, lap.driver_note.strip())
              for lap in laps
              if not lap.counted and lap.driver_note
              and lap.driver_note.strip()]
    if not stated:
        return ""
    parts = [f"lap {num} {reason}" for num, reason in stated]
    return "Driver's account of the struck laps: " + ", ".join(parts) + "."


def laps_per_stint(laps: list[LapInput]) -> list[list[LapInput]]:
    """Split at every pit lap, so wear is never fitted across a tyre change."""
    stints: list[list[LapInput]] = [[]]
    for lap in laps:
        stints[-1].append(lap)
        if lap.is_pit_lap:
            stints.append([])
    return [stint for stint in stints if stint]
