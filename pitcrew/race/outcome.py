"""What actually happened, in one paragraph.

The export contract's `strategy.outcome` is the line that lets a returned setup
know whether the plan held. The example in the contract reads:

    "Stopped lap 11. Fuel to the diamond +1 lap. Tyres had 2 laps left -
     stint was fuel-limited, not tyre-limited."

Only the first clause of that is a fact the app can state. "Tyres had 2 laps
left" is a judgement the driver makes, so this composes the facts and leaves
the judgement to `notes`. An outcome that guessed at the tyre margin would be
the app inventing the very thing the tune builder is trying to learn.
"""
from __future__ import annotations

from pitcrew.analysis.session import LapInput, counted_laps


def _stop_laps(laps: list[LapInput]) -> list[int]:
    return [lap.lap_num for lap in laps if lap.is_pit_lap]


def race_outcome(laps: list[LapInput], *, planned_stops: int | None = None,
                 planned_pit_laps: list[int] | None = None,
                 final_position: int | None = None,
                 binding_constraint: str | None = None,
                 declined_calls: int = 0) -> str:
    """Facts about the race just run. Empty string when nothing was run."""
    if not laps:
        return ""

    parts: list[str] = []
    stops = _stop_laps(laps)
    parts.append(f"{len(laps)} laps run")

    if stops:
        where = ", ".join(f"lap {lap}" for lap in stops)
        parts.append(f"stopped {where}")
    else:
        parts.append("no stops")

    if planned_stops is not None and planned_stops != len(stops):
        parts.append(
            f"the plan called for {planned_stops} "
            f"stop{'' if planned_stops == 1 else 's'}")
    elif (planned_pit_laps and stops
          # **An incomplete plan cannot assert a deviation.** The plan used to
          # travel as a single `pitLap`, so a two-stop race run exactly to its
          # plan compared [11, 22] against [11] and reported the driver off
          # it. Where fewer planned laps are known than stops were made, there
          # is nothing to compare and silence is the honest output.
          and len(planned_pit_laps) >= len(stops)
          and planned_pit_laps[:len(stops)] != stops):
        parts.append(
            "stopped on "
            + ", ".join(f"lap {lap}" for lap in stops)
            + " against a planned "
            + ", ".join(f"lap {lap}" for lap in planned_pit_laps))

    if final_position:
        parts.append(f"finished P{final_position}")

    if binding_constraint and binding_constraint != "unknown":
        parts.append(f"the stint was {binding_constraint}-limited")

    if declined_calls:
        parts.append(
            f"{declined_calls} call{'' if declined_calls == 1 else 's'} "
            "offered and not taken")

    return ". ".join(part[0].upper() + part[1:] for part in parts) + "."


def fuel_left_note(laps: list[LapInput]) -> str:
    """How much fuel was still aboard at the flag, if it can be seen.

    Stated as a fact, not as a verdict on whether the stint was fuel-limited -
    that comparison is the tune builder's to make.
    """
    counted = counted_laps(laps)
    if not counted:
        return ""
    last = counted[-1]
    burns = [lap.fuel_start - lap.fuel_end for lap in counted
             if lap.fuel_start > lap.fuel_end]
    if not burns or last.fuel_end <= 0:
        return ""
    per_lap = sorted(burns)[len(burns) // 2]
    if per_lap <= 0:
        return ""
    return (f"Finished with {last.fuel_end:.1f} litres, "
            f"about {last.fuel_end / per_lap:.1f} laps.")
