"""Where in the game day a race is run, and whether practice has been there.

GT7 runs its own clock. A race set to a time multiplier covers far more of the
day than it takes to drive: 50 real minutes at ×6 is five hours of game time,
afternoon into evening, and a two-hour enduro at ×12 is a full day and night.

**The track cools as the day does, and that changes two things at once.** A
colder track wears tyres less, so stints get longer; and it makes a harder
compound harder to light up, so a tyre that worked at noon can be off its
working range at three in the morning. Both are real and they pull opposite
ways, which is why the answer cannot be reasoned out — it has to be driven.

GT7 broadcasts **neither track nor air temperature**, and `CLAUDE.md` §5 is
explicit that inventing a proxy for track temperature is out. But it does
broadcast the time of day, and the app records the tyre temperature and the lap
time. That is the whole chain minus the hidden middle:

    time of day  ->  [track temp, unobservable]  ->  tyre temp  ->  lap time

Both ends are measured, so the hidden variable never has to be modelled. What
this module does is compare **where the race goes** with **where the evidence
has been**, and report the gap. It does not predict a temperature curve: GT7
publishes none, it differs by circuit and weather preset, and a fitted one
would be exactly the invented constant this project exists to avoid.
"""
from __future__ import annotations

from statistics import mean

from pitcrew.analysis.session import LapInput

DAY_MS = 24 * 60 * 60 * 1000

# Practice within this much of a race hour counts as covering it. A little over
# half an hour: track temperature moves slowly enough that this is the same
# conditions, and tighter would call almost everything uncovered.
COVERAGE_TOLERANCE_H = 0.75


def hour_of(time_of_day_ms: float | None) -> float | None:
    """GT7's clock as an hour of the day, 0-24."""
    if time_of_day_ms is None:
        return None
    return (time_of_day_ms % DAY_MS) / 3_600_000.0


def lap_hour(lap: LapInput) -> float | None:
    """When this lap was driven, in game time. None on laps recorded before
    the clock was captured."""
    stamps = [frame.get("time_of_day_ms") for frame in (lap.frames or ())
              if frame.get("time_of_day_ms") is not None]
    return hour_of(mean(stamps)) if stamps else None


def race_span_h(start_hour: float | None, minutes: float | None,
                multiplier: float | None) -> tuple[float, float] | None:
    """The game hours a race passes through, as (start, end).

    The end may exceed 24 - a race that starts at 22:00 and runs eight game
    hours ends at 06:00 the next morning, and saying `30.0` keeps the span
    contiguous where `6.0` would read as an eight-hour race run backwards.
    """
    if start_hour is None or not minutes or not multiplier:
        return None
    return start_hour, start_hour + (minutes * multiplier) / 60.0


def covered_hours(laps: list[LapInput]) -> list[float]:
    """The game hours practice has actually run in."""
    hours = [lap_hour(lap) for lap in laps]
    return sorted({round(hour, 2) for hour in hours if hour is not None})


def coverage(laps: list[LapInput], span: tuple[float, float] | None) -> dict:
    """What the race covers, what practice covers, and the gap between them.

    The gap is the finding. A plan for the closing stints of a night race,
    built entirely on daytime running, is a plan resting on nothing - and
    unlike a missing wear rate it does not announce itself, because every
    number in it looks measured.
    """
    driven = covered_hours(laps)
    if span is None:
        return {
            "raceSpanH": None,
            "practiceHours": driven,
            "covered": None,
            "note": ("The race's time of day is not declared, so nothing can "
                     "be said about whether practice ran in its conditions. "
                     "Set the start time and the time multiplier on the event "
                     "page."),
        }

    start, end = span
    # One check per game hour the race passes through.
    checkpoints = []
    hour = start
    while hour < end:
        checkpoints.append(hour)
        hour += 1.0
    checkpoints.append(end)

    uncovered = [round(point % 24.0, 2) for point in checkpoints
                 if not _is_covered(point, driven)]
    return {
        "raceSpanH": [round(start % 24.0, 2), round(end % 24.0, 2)],
        "raceSpanHours": round(end - start, 2),
        "practiceHours": driven,
        "covered": not uncovered,
        "uncoveredHours": uncovered,
        "note": _note(driven, start, end, uncovered),
    }


def _is_covered(point: float, driven: list[float]) -> bool:
    for hour in driven:
        # Compare around the clock: 23:30 practice covers a 00:00 race hour.
        gap = abs((point % 24.0) - hour)
        if min(gap, 24.0 - gap) <= COVERAGE_TOLERANCE_H:
            return True
    return False


def _note(driven: list[float], start: float, end: float,
          uncovered: list[float]) -> str:
    if not driven:
        return (
            "No lap on record carries a time of day, so none of the race's "
            "conditions have been driven as far as the app can tell. Laps "
            "recorded before the clock was captured cannot be placed in the "
            "day; run a practice session to put evidence on the map.")
    if not uncovered:
        return (f"Practice has run in every game hour the race passes through "
                f"({_clock(start)} to {_clock(end)}).")
    return (
        f"The race runs {_clock(start)} to {_clock(end)} in game time, and "
        f"practice has only run at {', '.join(_clock(h) for h in driven)}. "
        f"{len(uncovered)} of its hours have never been driven - "
        f"{', '.join(_clock(h) for h in uncovered[:6])}"
        f"{'...' if len(uncovered) > 6 else ''}. The track cools through them, "
        f"which lengthens a stint and can leave a harder compound below its "
        f"working range, and the two pull opposite ways. Run a stint at that "
        f"time of day before planning one.")


def sessions_to_run(report: dict, *, preset: str | None = None) -> list[dict]:
    """The practice the race needs and has not had, one entry per gap.

    Contiguous uncovered hours are one session, not one per hour: a stint is
    twenty minutes of game time at a low multiplier and several hours at a
    high one, so a run started anywhere inside a gap covers a good deal of it.
    """
    uncovered = report.get("uncoveredHours") or []
    if not uncovered:
        return []

    blocks: list[list[float]] = []
    for hour in uncovered:
        if blocks and abs(hour - blocks[-1][-1]) <= 1.01:
            blocks[-1].append(hour)
        else:
            blocks.append([hour])

    out = []
    for block in blocks:
        first, last = block[0], block[-1]
        out.append({
            "fromHour": first,
            "toHour": last,
            "hours": len(block),
            "do": (
                f"Run a full stint at race pace from about {_clock(first)}, "
                f"on the compound the race will use - it covers "
                f"{_clock(first)}-{_clock(last)}, which nothing has driven."
                + (f" Reaching that hour may need a lobby setting other than "
                   f"{preset}." if preset else "")),
        })
    return out


def _clock(hour: float) -> str:
    hour = hour % 24.0
    whole = int(hour)
    return f"{whole:02d}:{int(round((hour - whole) * 60)) % 60:02d}"
