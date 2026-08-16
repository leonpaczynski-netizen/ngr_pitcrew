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

# How many laps an offer stays open unanswered before it lapses. The driver
# is under a helmet and often cannot answer at all: one measured race had an
# offer voiced two minutes after the green, never answered, and every later
# verdict - including the fuel-drift finding that would have cancelled both
# stops - computed and thrown away for 29 minutes because a pending offer
# blocked the whole loop. Two laps is about four minutes on the league's
# circuits: long enough to answer, short enough that silence cannot gag the
# engineer for a race.
OFFER_EXPIRES_AFTER_LAPS = 2

NONE = "none"
RECOMMENDED = "recommended"
URGENT = "urgent"

# How a pending offer left the desk. Recorded with the revision so the
# post-race audit can tell an offer the driver refused from one he never
# heard the end of.
RESOLVED_ACCEPTED = "accepted"
RESOLVED_KEPT = "explicitly kept"
RESOLVED_EXPIRED = "expired unanswered"
RESOLVED_SUPERSEDED = "superseded by a new offer"
RESOLVED_RACE_ENDED = "race ended unanswered"


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


@dataclass(frozen=True)
class Resolution:
    """How one offer ended: what it was, when, and on whose word."""
    offer: Replan
    lap: int
    accepted: bool
    reason: str


def materially_different(new: Replan, pending: Replan) -> bool:
    """Whether a fresh verdict says something the pending offer does not.

    A different stop count is a different race; an escalation to urgent is
    the model saying the driver can no longer afford to sit on the question.
    Anything less is the same offer restated, and restating an unanswered
    question is noise.
    """
    if not new.offered:
        return False
    if new.stops != pending.stops:
        return True
    return new.verdict == URGENT and pending.verdict != URGENT


class OfferDesk:
    """The one open offer, and the rules that stop it gagging the engineer.

    `controller._check_replan` used to hold the pending offer in a bare
    attribute with one rule: while anything pends, every later verdict is
    discarded. Under a helmet the driver usually cannot answer, so one
    unanswered question at minute two silenced every adaptation for the rest
    of a measured race - the single root cause of "didn't adjust at all".

    Three rules replace it, and "offered, never imposed" survives all three:

    * An offer **lapses** after `OFFER_EXPIRES_AFTER_LAPS` laps unanswered.
      It is recorded as declined with `RESOLVED_EXPIRED` - distinguishable
      from a driver who said "keep" - and expiry never silently adopts
      anything. The old plan simply still stands.
    * A verdict **materially different** from the pending offer replaces it,
      spoken, rather than being discarded: the superseded offer is recorded
      with `RESOLVED_SUPERSEDED`.
    * A lapsed offer is not re-voiced verbatim. Re-asking the identical
      question every two laps is the same defect as the box call that
      repeated nine times; only a materially different verdict reopens the
      conversation.
    """

    def __init__(self, expires_after_laps: int = OFFER_EXPIRES_AFTER_LAPS
                 ) -> None:
        self.expires_after_laps = expires_after_laps
        self.pending: Replan | None = None
        self.pending_since_lap: int | None = None
        self._lapsed: Replan | None = None
        # What the last supersession replaced, so a verdict oscillating
        # across a stops boundary cannot swap the offer back and forth
        # every lap: A superseded by B is fine; B superseded straight back
        # by A is the model dithering out loud, and it waits instead.
        self._last_replaced: Replan | None = None

    def reset(self) -> None:
        self.pending = None
        self.pending_since_lap = None
        self._lapsed = None
        self._last_replaced = None

    def consider(self, verdict: Replan, lap: int
                 ) -> tuple[Replan | None, list[Resolution]]:
        """One lap's verdict in; what to say and what to record out.

        Returns `(offer_to_speak, resolutions)`. The resolutions are offers
        that ended this lap without the driver - expired or superseded - and
        every one must reach the revision record: an offer that vanished
        without trace would make the model look better than it was.
        """
        resolutions: list[Resolution] = []
        if self.pending is not None:
            # Hysteresis on the swap: an escalation to urgent always goes
            # through, but a verdict that merely undoes the last swap -
            # A replaced by B, now A again - is dithering, and it waits for
            # the pending offer to be answered or to lapse.
            supersedes = materially_different(verdict, self.pending) and (
                verdict.verdict == URGENT
                or self._last_replaced is None
                or materially_different(verdict, self._last_replaced))
            if supersedes:
                resolutions.append(Resolution(
                    self.pending, lap, accepted=False,
                    reason=RESOLVED_SUPERSEDED))
                self._last_replaced = self.pending
                self.pending = None
                self.pending_since_lap = None
            elif (self.pending_since_lap is not None
                    and lap - self.pending_since_lap >= self.expires_after_laps):
                resolutions.append(Resolution(
                    self.pending, lap, accepted=False,
                    reason=RESOLVED_EXPIRED))
                self._lapsed = self.pending
                self.pending = None
                self.pending_since_lap = None
                self._last_replaced = None
            else:
                # The question is still open and the verdict adds nothing
                # material - the driver keeps his silence a little longer.
                return None, resolutions

        if not verdict.offered:
            return None, resolutions
        if self._lapsed is not None and not materially_different(
                verdict, self._lapsed):
            # He heard this one already and let it lapse. Only a materially
            # different verdict earns another interruption.
            return None, resolutions
        self.pending = verdict
        self.pending_since_lap = lap
        return verdict, resolutions

    def resolve(self, *, accepted: bool, lap: int) -> Resolution | None:
        """The driver answered. Returns the resolution to record, or None."""
        offer = self.pending
        self.pending = None
        self.pending_since_lap = None
        self._lapsed = None
        self._last_replaced = None
        if offer is None:
            return None
        return Resolution(offer, lap, accepted=accepted,
                          reason=RESOLVED_ACCEPTED if accepted
                          else RESOLVED_KEPT)

    def drain(self, *, lap: int) -> Resolution | None:
        """The race ended with the question still open.

        Called at teardown so an offer voiced in the final laps reaches the
        revision record instead of vanishing - an offer the audit cannot see
        is the exact hole one measured race already fell through. Returns
        the resolution to record, or None when nothing was pending. Draining
        adopts nothing, like expiry.
        """
        offer = self.pending
        self.reset()
        if offer is None:
            return None
        return Resolution(offer, lap, accepted=False,
                          reason=RESOLVED_RACE_ENDED)


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

    `lap_time_ms` is the race's **representative pace** - the coordinator's
    median of the last few representative laps - and None until one exists.
    It was once the just-completed lap, whatever it was, and the very first
    verdict of a measured race was built on the standing-start lap alone:
    "lapping 2% slower than planned" voiced two minutes after the green, on
    the one lap that is slower by construction. None here means the pace is
    unknown, and unknown offers no verdict.
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

    if current is None:
        # Nothing runnable at the stop count he is on, so there is no gain to
        # quote. Saying "0 seconds in it" put a measured-sounding nothing
        # against a plan that cannot be finished.
        detail = (f"{'; '.join(reasons)}; the {current_stops}-stop plan is no "
                  f"longer runnable")
    else:
        detail = f"{'; '.join(reasons)}; {gain:.0f} seconds in it"

    return Replan(
        RECOMMENDED,
        detail,
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

    **A timed race has to have its clock shortened too.** `race_minutes` was
    left at the full limit while the lap count came down, so the model planned
    another whole race inside the remainder of this one: ten laps left came
    back as stints of 14 and 11. Adopted, that put the next stop on lap 29 of
    a 24-lap race and no box call was ever made again. The clock left is the
    laps left at the reference pace - still a timed problem, because a stop in
    one is paid for in laps and not in seconds.
    """
    from dataclasses import replace

    minutes = None
    if inputs.is_timed and inputs.lap_time_ms > 0:
        minutes = laps_left * (inputs.lap_time_ms / 1000.0) / 60.0

    return replace(
        inputs,
        race_laps=laps_left,
        race_minutes=minutes,
        fuel_per_lap_l=observed_fuel or inputs.fuel_per_lap_l,
        fuel_capacity_l=fuel_capacity_l or inputs.fuel_capacity_l,
        mandatory_stops=0,      # already satisfied, or not reachable now
    )
