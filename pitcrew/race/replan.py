"""Re-planning mid-race, when reality stops matching the plan.

The pre-race plan is built on practice evidence. A race then diverges from it
for real reasons — a safety car, traffic, a cooler track, a mistake, or simply
a fuel burn that was measured over six laps and is now measured over twenty.

Three rules keep this honest:

* **Divergence is measured against stated thresholds**, not felt. A plan that
  changes whenever a lap is a tenth slow is noise.
* **A new plan is offered, never imposed.** The driver accepts or keeps, and
  until he answers the old plan stands. Silently switching plans mid-race
  would leave him racing to one the engineer has already abandoned.
* **The old plan is never deleted.** Every offer is recorded, accepted or not,
  because a re-plan the driver refused is evidence about the model.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.strategy.model import (
    RaceInputs,
    StrategyImpossible,
    recommend,
)

# Material change thresholds. Below these the plan stands.
FUEL_DRIFT = 0.05      # 5% off the planned burn rate
PACE_DRIFT = 0.02      # 2% off the reference lap
# A new plan must beat the current one by more than this to be worth the
# disruption of changing strategy mid-race.
WORTH_CHANGING_S = 8.0

NONE = "none"
RECOMMENDED = "recommended"
URGENT = "urgent"


@dataclass(frozen=True)
class Replan:
    """What the model now thinks, and how strongly."""
    verdict: str
    reason: str
    stops: int | None = None
    stint_laps: tuple[int, ...] = ()
    gain_s: float = 0.0
    confidence: str = "medium"

    @property
    def offered(self) -> bool:
        return self.verdict in (RECOMMENDED, URGENT)

    def call(self) -> str:
        """One instruction, in the engineer's register."""
        if not self.offered:
            return ""
        if self.stops == 0:
            return "Recommend running to the flag."
        return f"Recommend {self.stops} stop{'' if self.stops == 1 else 's'}."

    def as_plan(self) -> dict:
        return {
            "verdict": self.verdict,
            "stops": self.stops,
            "stint_laps": list(self.stint_laps),
            "gain_s": round(self.gain_s, 1),
            "reason": self.reason,
            "confidence": self.confidence,
        }


def observed_fuel_per_lap(fuel_used: list[float]) -> float | None:
    """Burn measured this race, not in practice.

    Uses the median so one lap behind a safety car cannot move it.
    """
    burns = sorted(value for value in fuel_used if value > 0)
    if not burns:
        return None
    return burns[len(burns) // 2]


def drift(observed: float | None, planned: float | None) -> float | None:
    """Fractional difference, or None when either side is unknown."""
    if observed is None or not planned:
        return None
    return (observed - planned) / planned


def assess(*, laps_done: int, laps_total: int | None,
           fuel_l: float | None,
           planned_fuel_per_lap: float | None,
           observed_fuel_per_lap_l: float | None,
           lap_time_ms: int | None,
           planned_lap_time_ms: int | None,
           current_stops: int,
           inputs: RaceInputs | None = None,
           fuel_capacity_l: float | None = None) -> Replan:
    """Decide whether the plan still holds.

    Returns a verdict of `none` far more often than not, which is the point:
    the driver should hear from the model when something has changed, and not
    otherwise.
    """
    if laps_total is None or laps_done >= laps_total:
        return Replan(NONE, "race is over or its length is unknown")

    fuel_drift = drift(observed_fuel_per_lap_l, planned_fuel_per_lap)
    pace_drift = drift(
        float(lap_time_ms) if lap_time_ms else None,
        float(planned_lap_time_ms) if planned_lap_time_ms else None)

    reasons = []
    if fuel_drift is not None and abs(fuel_drift) > FUEL_DRIFT:
        reasons.append(
            f"burning {abs(fuel_drift):.0%} "
            f"{'more' if fuel_drift > 0 else 'less'} fuel than planned")
    if pace_drift is not None and abs(pace_drift) > PACE_DRIFT:
        reasons.append(
            f"lapping {abs(pace_drift):.0%} "
            f"{'slower' if pace_drift > 0 else 'faster'} than planned")

    # Running out before the flag is urgent whatever the model prefers.
    laps_left = laps_total - laps_done
    if (fuel_l is not None and observed_fuel_per_lap_l
            and current_stops == 0):
        laps_of_fuel = fuel_l / observed_fuel_per_lap_l
        if laps_of_fuel < laps_left - 0.5:
            short = laps_left - laps_of_fuel
            return Replan(
                URGENT,
                f"{short:.1f} laps short of the flag on current burn",
                stops=1, gain_s=0.0, confidence="high")

    if not reasons:
        return Replan(NONE, "on the plan")

    if inputs is None:
        # Something has changed but there is nothing to re-plan with: say so
        # rather than inventing a stint length.
        return Replan(RECOMMENDED, "; ".join(reasons), confidence="low")

    rest = _remaining_race(inputs, laps_left, observed_fuel_per_lap_l,
                           fuel_capacity_l)
    try:
        plans = recommend(rest, max_stops=3)
    except StrategyImpossible as exc:
        return Replan(RECOMMENDED, f"{'; '.join(reasons)} ({exc})",
                      confidence="low")

    best = plans[0]
    current = next((p for p in plans if p.stops == current_stops), None)
    gain = (current.total_time_s - best.total_time_s) if current else 0.0

    if current is not None and gain <= WORTH_CHANGING_S:
        return Replan(NONE, f"{'; '.join(reasons)}, but the plan still wins")

    return Replan(
        RECOMMENDED,
        f"{'; '.join(reasons)}; {gain:.0f} seconds in it",
        stops=best.stops,
        stint_laps=tuple(stint.laps for stint in best.stints),
        gain_s=gain,
    )


def _remaining_race(inputs: RaceInputs, laps_left: int,
                    observed_fuel: float | None,
                    fuel_capacity_l: float | None) -> RaceInputs:
    """The rest of the race as its own planning problem.

    Re-planning the whole race would recommend a stop already taken. What is
    left is a shorter race starting now, on the fuel rate this race is actually
    showing rather than the one practice suggested.
    """
    from dataclasses import replace

    return replace(
        inputs,
        race_laps=laps_left,
        fuel_per_lap_l=observed_fuel or inputs.fuel_per_lap_l,
        fuel_capacity_l=fuel_capacity_l or inputs.fuel_capacity_l,
        mandatory_stops=0,      # already satisfied, or not reachable now
    )
