"""Laps with an off or a spin in them, and why they need two verdicts.

The driver's requirement, and it has two halves that point opposite ways:
*"note next to laps where I spin off track and again auto remove them from
strat planning but include them for setup advice."*

Both halves are right. A lap with a spin in it says nothing about race pace —
averaged into a stint it invents degradation that never happened. It says a
great deal about the car, because the car is what spun. So an incident lap
leaves the **counted** set, which is what pace, fuel and the strategy model
read, and stays in the **diagnostic** set, which is what the corner
aggregates read.

## Finding them

The obvious signal is the surface channel, and on its own it is useless. A
clean lap of Monza spends one to two seconds with two wheels off tarmac and
kerb — it is the astroturf at the exits, and it is how the lap is supposed to
be driven. Across the capture set the median lap has 0.62 s of it and three
quarters of all laps have over a second. Threshold that and seventy laps in a
hundred and thirty-two are incidents.

What actually separates them is that **the car stops**. Every genuine incident
in the capture set ends with the car at or near a standstill in the middle of
a lap: the 28 s loss at Monza, the 14 s spin that never left the tarmac, the
15 s trip through the gravel. Fourteen laps touch zero mid-lap and every one
of them is an incident, a pit stop or an opening lap out of the box. The other
hundred and eighteen have a tenth-percentile minimum of 30 km/h, against a
slowest corner around 60 — so there is a wide, empty band between the slowest
corner anyone drives and a car that has stopped.

So the rule takes two signals, never one:

1. **The lap lost time** against the clean median of its own run. Against its
   own run, because a stint on old tyres is slower than one on new and neither
   fact is an incident.
2. **Something corroborates it** — the car crawled, or it spent a long
   uninterrupted spell off the road, or it span.

Either alone is noise. Time loss alone is traffic, a lift, a cold set. A
corroborating signal alone is a driver running the kerbs hard and getting away
with it, which is not an incident and must not be struck.

Nothing here is measured; it is all thresholds, and they are restated in the
export under `derived` so that retuning one reads as a change in the detector
rather than a change in the driver.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from pitcrew.analysis import thresholds

# How much slower than its own run's clean median a lap has to be before
# anything else is even considered. Three seconds is a large miss on a 110 s
# circuit and well outside the spread of a consistent stint.
TIME_LOSS_S = 3.0

# **The bar for reporting an unexplained loss, as a FRACTION of the lap.**
#
# Absolute seconds are the wrong unit here and the first attempt used them:
# 6 s is 5% of a 110 s Monza lap and 13% of a 51 s Red Bull Ring lap, and
# those are not the same claim. Traffic and a lift live in the low single
# percent; session 93 lap 3 lost 13.5%, with a minimum speed of 33.8 km/h
# against 89 on every other lap of its run.
#
# Ten percent, and it is a REPORTING bar rather than an exclusion one - see
# `unexplained_losses`.
UNEXPLAINED_FRACTION = 0.10

# The car has effectively stopped. The slowest corner on any circuit in the
# capture set is around 60 km/h and the tenth-percentile lap minimum is 30, so
# this sits in an empty band rather than at the edge of one.
CRAWL_KPH = 15.0
CRAWL_MIN_S = 0.5

# Below this the car has not set off yet, so the opening standstill of a lobby
# session is the grid and not an incident.
LAUNCH_KPH = 30.0

# A single uninterrupted spell with two or more wheels off the road. The 95th
# percentile of all recorded laps is 2.88 s, so this is deliberately at the
# top of what normal driving produces rather than in the middle of it.
OFF_TRACK_MIN_S = 2.5

# Rotation the car is not being steered through, at a speed where it is not a
# fast direction change. Brief by nature — a spin is over in a moment, and the
# car being sideways for a tenth of a second at 80 km/h is not something that
# happens on a clean lap.
#
# **Measured against a real yaw channel, which this detector never had.** It
# ran on `angvel_z`, the roll axis, whose correlation with actual heading rate
# is 0.027 — so `spin` reached its 0.08 s minimum on exactly one of the 132
# recorded laps and every incident the detector reported came from `crawl` or
# `off-track`. Reconstructing yaw from `pos_x`/`pos_z` across all 132 laps and
# taking each lap's strongest sustained 5-frame excursion below
# `SPIN_MAX_SPEED_KPH`: the 113 laps within 3 s of their session median top out
# at 1.83 rad/s (median 0.82, and a slow hairpin alone is worth 0.9), while the
# laps that lost time sit at 2.22 and above. 1.2 sat inside normal driving and
# fired on 6 of those 113; 2.0 is the middle of the empty band between them and
# fires on none, while still catching 8 of the 17 laps that lost time — the
# rest lost it to a crawl or an off, which are the other two signals.
SPIN_YAW_RAD_S = 2.0
SPIN_MAX_SPEED_KPH = 120.0
SPIN_MIN_S = 0.08

CRAWL = "crawl"          # the car came to a stop mid-lap
OFF_TRACK = "off-track"  # a long spell with two wheels or more off the road
SPIN = "spin"            # rotation at a speed that is not a direction change
# **Time lost and nothing on file explains it.**
#
# Found on session 93 lap 3, 6 Sep 2026: 6.9 s off its own run's median with
# a minimum speed of 33.8 km/h against 89 on every clean lap of that run, all
# four wheels on tarmac throughout, and `crawl_s`, `off_track_s` and `spin_s`
# all 0.0. The time-loss gate opened - the detector KNEW the lap was anomalous
# - then found no corroboration and dropped it, so it was counted as clean and
# went into every median, every sector spread and every export that session
# touched. It also drove a 18x sector-spread reading that was very nearly
# diagnosed as a setup problem.
#
# That is absence of evidence rendered as evidence of absence, which is rule 3
# wearing different clothes. A lap that lost six seconds is not a clean lap
# because we cannot say why.
UNEXPLAINED = "unexplained"

REASON_INCIDENT = "incident"


@dataclass(frozen=True)
class Evidence:
    """What one lap's frames show, before any judgement is made.

    Any of the three may be `None`, meaning **the channel it comes from was
    not in the packet**. `off_track_s` is the one that actually happens:
    surface type arrives only in the `~` and `C` formats, and the listener
    falls back to `A` after `FORMAT_PATIENCE_S` without a decode. Every lap of
    that session then has no surface channel at all, and a 0.0 there is stored
    and exported as a measurement that the car never left the road — which is
    exactly what `meta.packet` exists to prevent (`CLAUDE.md` §3.1).
    """
    crawl_s: float | None = 0.0
    off_track_s: float | None = 0.0
    spin_s: float | None = 0.0

    @property
    def signals(self) -> tuple[str, ...]:
        found = []
        if self.crawl_s is not None and self.crawl_s >= CRAWL_MIN_S:
            found.append(CRAWL)
        if self.off_track_s is not None and self.off_track_s >= OFF_TRACK_MIN_S:
            found.append(OFF_TRACK)
        if self.spin_s is not None and self.spin_s >= SPIN_MIN_S:
            found.append(SPIN)
        return tuple(found)


@dataclass(frozen=True)
class Incident:
    """One lap that had something happen in it."""
    lap_num: int
    lost_s: float
    signals: tuple[str, ...]
    evidence: Evidence

    def describe(self) -> str:
        """What to put next to the lap, in the fewest words that are true."""
        parts = []
        if CRAWL in self.signals:
            parts.append("came to a stop")
        if SPIN in self.signals:
            parts.append("spun")
        if OFF_TRACK in self.signals:
            parts.append(f"{self.evidence.off_track_s:.1f} s off the road")
        if UNEXPLAINED in self.signals:
            # Says what is known and what is not, in that order. "Lost time"
            # is the measurement; "nothing on file explains it" is the gap,
            # and a reader must not be able to mistake the second for a
            # diagnosis.
            return (f"lost {self.lost_s:+.1f} s, and nothing on file explains "
                    f"it - the frames show no stop, no spin and no excursion")
        return f"{' and '.join(parts)}, {self.lost_s:+.1f} s"

    def as_export(self) -> dict:
        return {
            "lap": self.lap_num,
            "lostS": round(self.lost_s, 2),
            "signals": list(self.signals),
            "crawlS": _seconds(self.evidence.crawl_s),
            "offTrackS": _seconds(self.evidence.off_track_s),
            "spinS": _seconds(self.evidence.spin_s),
            "note": self.describe(),
        }


def _seconds(value: float | None) -> float | None:
    """Null where the channel was not in the packet, never a rounded zero."""
    return None if value is None else round(value, 2)


def _longest_run_s(flags: list[bool], sample_hz: float) -> float:
    longest = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return longest / (sample_hz or 60.0)


def read_rows(rows: list[list], field_names, sample_hz: float = 60.0) -> Evidence:
    """`read_evidence`, from the recorder's column-array rows.

    The recorder holds a lap as rows plus a field list, and the evidence is
    three numbers taken once while they are still in hand. Reading it here
    rather than decoding the blob again later is what lets the lap rack judge
    a lap without touching a 400 KB compressed buffer per row it draws.
    """
    index = {name: position for position, name in enumerate(field_names)}
    wanted = ("speed_kph", "yaw_rate", "surf_fl", "surf_fr", "surf_rl", "surf_rr")
    return read_evidence(
        [{name: row[index[name]] for name in wanted if name in index}
         for row in rows],
        sample_hz)


def read_evidence(frames: list[dict] | None,
                  sample_hz: float = 60.0) -> Evidence:
    """What one lap's frames show. No verdict, no thresholds applied.

    Everything before the car first reaches `LAUNCH_KPH` is skipped: a lobby
    session opens with the car stationary in the box, which is the grid and
    not an incident, and on the capture set that is up to eighty seconds of
    standing still.
    """
    if not frames:
        return Evidence()

    speeds = [frame.get("speed_kph") or 0.0 for frame in frames]
    launched = next((i for i, speed in enumerate(speeds)
                     if speed > LAUNCH_KPH), len(speeds))
    running = frames[launched:]
    if not running:
        return Evidence()

    speeds = speeds[launched:]
    crawling = [speed < CRAWL_KPH for speed in speeds]

    # Surface type arrives only in the extended packet formats. Where none of
    # the frames carry it there were no excursions *that anything could see*,
    # which is a different claim from none having happened - and a stored 0.0
    # is read downstream as a measurement.
    surfaced = any(frame.get(f"surf_{corner}") is not None
                   for frame in running
                   for corner in ("fl", "fr", "rl", "rr"))
    off = []
    for frame in running:
        surfaces = [frame.get(f"surf_{corner}")
                    for corner in ("fl", "fr", "rl", "rr")]
        wheels_off = sum(1 for surface in surfaces
                         if surface is not None
                         and surface not in thresholds.ON_TRACK_SURFACES)
        # Two wheels, not one. Putting the inside pair on the astroturf at a
        # chicane exit is how the lap is driven, not an excursion.
        off.append(wheels_off >= 2)

    spinning = [
        abs(frame.get("yaw_rate") or 0.0) > SPIN_YAW_RAD_S
        and speed < SPIN_MAX_SPEED_KPH
        for frame, speed in zip(running, speeds)
    ]

    return Evidence(
        crawl_s=_longest_run_s(crawling, sample_hz),
        off_track_s=_longest_run_s(off, sample_hz) if surfaced else None,
        spin_s=_longest_run_s(spinning, sample_hz),
    )


def evidence_of(lap) -> Evidence | None:
    """The stored evidence for a lap, or None if it was never captured.

    `None` and a zeroed `Evidence` are different claims: the first says the
    lap's frames are not on file, the second says they are and nothing
    happened. A lap with no evidence is never an incident, because "not
    measured" must not read as "nothing measured".
    """
    values = (lap.crawl_s, lap.off_track_s, lap.spin_s)
    if all(value is None for value in values):
        return None
    # Each column keeps its own null. A session recorded on packet format A
    # has no surface channel and stores NULL for `off_track_s` alone; filling
    # it with 0.0 here would turn "not offered by this packet" back into "the
    # car never left the road".
    return Evidence(crawl_s=values[0], off_track_s=values[1], spin_s=values[2])


def stored_or_read(lap) -> Evidence:
    """The stored evidence, falling back to reading the frames.

    The fallback covers laps recorded before the columns existed and any path
    that builds a `LapInput` by hand.

    `getattr`, because the lap rack's row objects carry the three evidence
    columns and no frames at all — a `LapRow` with null evidence used to raise
    `AttributeError` here, inside `load_active_event`, which is the app dying
    on launch rather than a bad number.
    """
    stored = evidence_of(lap)
    if stored is not None:
        return stored
    frames = getattr(lap, "frames", None)
    return read_evidence(frames) if frames else Evidence()


def find_incidents(laps, evidence_for) -> dict[int, Incident]:
    """Incidents by lap number, judged inside each run.

    `evidence_for(lap)` returns an `Evidence`, so the caller decides what it
    costs to get one — the frames may not be decoded, and a lap whose frames
    were never captured has no evidence rather than clean evidence.

    A run with fewer than three clean laps produces no verdict at all. The
    median of two laps is not a reference, and half a stint is exactly where a
    confident wrong answer would do most damage.
    """
    # Imported here rather than at module scope: `runs` reads thresholds and
    # this module, and a top-level import would close the loop.
    from pitcrew.analysis.runs import auto_out_laps, split_runs

    laps = list(laps)
    # Asked for directly rather than read off the flag. The flag is set by
    # `classify_exclusions`, which has to run *after* this - it needs to know
    # which laps are incidents in order to name them - and an out-lap left in
    # here would be judged for losing time it is supposed to lose.
    out_laps = auto_out_laps(laps)

    found: dict[int, Incident] = {}
    for run in split_runs(laps):
        candidates = [lap for lap in run.laps
                      if not (lap.is_out_lap or lap.is_pit_lap or lap.excluded
                              or lap.lap_num in out_laps)]
        times = [lap.lap_time_ms for lap in candidates if lap.lap_time_ms > 0]
        if len(times) < 3:
            continue
        reference = median(times)

        for lap in candidates:
            lost_s = (lap.lap_time_ms - reference) / 1000.0
            if lost_s < TIME_LOSS_S:
                continue
            evidence = evidence_for(lap)
            signals = evidence.signals
            if not signals:
                # **Still not an incident, deliberately.** Slow is not the
                # same as something happening, and the app may not invent a
                # cause. `unexplained_losses` reports these separately without
                # changing what counts.
                continue
            found[lap.lap_num] = Incident(
                lap_num=lap.lap_num, lost_s=lost_s,
                signals=signals, evidence=evidence)
    return found


@dataclass(frozen=True)
class UnexplainedLoss:
    """A lap that lost real time with nothing on file to explain it.

    **Not an incident, and it must not be turned into one.** `judge` will not
    have it: slow is not the same as something happening, and the app may not
    invent a cause. So this changes nothing about what counts - it is a
    question raised, in the driver's own words: *don't dismiss as data error,
    ask; the variability of data is data to investigate.*
    """
    lap_num: int
    lost_s: float
    fraction: float
    min_speed_kph: float | None = None

    def describe(self) -> str:
        said = (f"lap {self.lap_num} lost {self.lost_s:.1f} s "
                f"({self.fraction * 100:.0f}% of the lap) and nothing on file "
                f"explains it - no stop, no spin, no excursion")
        if self.min_speed_kph is not None:
            said += f"; slowest point {self.min_speed_kph:.0f} km/h"
        return said + ". Traffic, a lift, or a miss by the detector."


def unexplained_losses(laps, evidence_for) -> list[UnexplainedLoss]:
    """Laps that lost time nobody can account for, worth asking about.

    **The gap this closes.** The time-loss gate opens, the frames are looked
    at, nothing corroborates, and `judge` drops the lap - so it is counted as
    clean and goes into every median of its run with no trace anywhere that a
    question was ever raised. Session 93 lap 3 lost 6.9 s of a 51 s lap that
    way, and it went on to drive an 18x sector-spread reading that was very
    nearly diagnosed as a setup problem.

    Reported, never excluded. A lap with no frames on file is not here
    either: "not measured" is not "unexplained", which is a claim about
    frames that exist and are silent.

    `evidence_for` is injected exactly as `find_incidents` takes it, so both
    read the same laps through the same accessor. Two ways of asking whether
    a lap has evidence would eventually disagree, and the disagreement would
    be that one of them called a lap clean.
    """
    from pitcrew.analysis.runs import auto_out_laps, split_runs

    laps = list(laps)
    out_laps = auto_out_laps(laps)
    found: list[UnexplainedLoss] = []
    for run in split_runs(laps):
        candidates = [lap for lap in run.laps
                      if not (lap.is_out_lap or lap.is_pit_lap or lap.excluded
                              or lap.lap_num in out_laps)]
        times = [lap.lap_time_ms for lap in candidates if lap.lap_time_ms > 0]
        if len(times) < 3:
            continue
        reference = median(times)
        for lap in candidates:
            if lap.lap_time_ms <= 0:
                continue
            lost_s = (lap.lap_time_ms - reference) / 1000.0
            fraction = lost_s / (reference / 1000.0)
            if lost_s < TIME_LOSS_S or fraction < UNEXPLAINED_FRACTION:
                continue
            evidence = evidence_for(lap)
            if evidence is None or evidence.signals:
                # No frames, or the frames DID explain it - `judge` owns that
                # lap and has already called it an incident.
                continue
            found.append(UnexplainedLoss(
                lap_num=lap.lap_num, lost_s=lost_s, fraction=fraction,
                min_speed_kph=getattr(lap, "min_speed_kph", None)))
    return found


def as_export(incidents: dict[int, Incident]) -> list[dict] | None:
    return [incidents[lap].as_export() for lap in sorted(incidents)] or None


def thresholds_export() -> dict:
    """The `derived.thresholds` entries this detector owns."""
    return {
        "incidentTimeLossS": TIME_LOSS_S,
        "incidentCrawlKph": CRAWL_KPH,
        "incidentOffTrackS": OFF_TRACK_MIN_S,
        "incidentSpinYawRadS": SPIN_YAW_RAD_S,
        "incidentUnexplainedFraction": UNEXPLAINED_FRACTION,
        "incidentRule": (
            "a lap counts as an incident only where it lost time against the "
            "clean median of its own run AND the frames corroborate it. The "
            "surface channel alone does not: a clean lap of Monza spends 1-2 s "
            "with two wheels off tarmac and kerb, and thresholding that flags "
            "70 laps in 132. A lap that lost time with its frames on file "
            "and nothing corroborating is NOT an incident - slow is not the "
            "same as something happening - but where the loss exceeds "
            "incidentUnexplainedFraction of the lap it is reported as an "
            "unexplained loss, which is a question rather than a verdict."),
    }
