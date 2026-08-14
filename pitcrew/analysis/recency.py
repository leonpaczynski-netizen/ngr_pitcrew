"""Later laps count for more, because he got faster and the car changed.

*"As I do more laps and refine the setup and my driving these laps should
carry more weight than the original laps for race strategy."*

Both halves of that are real and they are not the same thing.

**He gets faster.** Pooled across every Monza session the clean-lap median is
109.43 s; the most recent session alone is 109.06 s. That is 0.37 s a lap.
Over roughly 27 laps of a 50-minute race it is about ten seconds of cumulative
error, and because a stint ends where degradation crosses a threshold, a
reference pace that is slow by a third of a second moves the stop lap too.

**The car changes.** A lap run on a superseded setup sheet is describing a car
that no longer exists. That matters more than age: three sessions old on the
current sheet is better evidence than yesterday's on a sheet that has since
been replaced twice, and weighting on time alone gets that backwards.

So both are applied, and they are separate terms.

## What this is not allowed to touch

**Not degradation.** The wear rate is read off the in-game gauge, not fitted
to lap times, and that is what keeps it out of the fuel-load confound — see
the 12 Aug strategy audit. Down-weighting old gauge readings would be
reweighting a measurement rather than an estimate, and there is nothing to
gain: a gauge reading from three weeks ago is exactly as true as one from
today.

**Not the best lap.** A personal best is a fact about a lap, not an average of
several, and there is nothing to weight.

It applies to the two figures a plan is actually built on: the **reference
pace** and the **fuel burn per lap**.

## Weighted, not truncated

Discarding old sessions outright would be simpler and worse. A driver who has
run two sessions this week and eleven over the month has thirteen sessions of
evidence about fuel burn, and throwing eleven away to honour a preference for
recent data would replace a small bias with a large variance. Every lap keeps
a weight; the weights differ.

Everything here is a **choice, not a measurement**, so the half-life and the
superseded-sheet penalty are restated in the export under `derived` — the
same rule as every other threshold in the app.
"""
from __future__ import annotations

from dataclasses import dataclass

# Sessions ago at which a lap counts half as much. Two is deliberately short:
# he is actively changing both the car and how he drives it, which is the
# situation this exists for. It is not a claim that laps decay at this rate,
# it is a statement about how much weight to give a changing driver.
HALF_LIFE_SESSIONS = 2.0

# A lap run on a setup sheet that has since been replaced. It is describing a
# car that no longer exists, and no amount of recency rescues that - which is
# why this is a multiplier on top of the age term rather than part of it.
SUPERSEDED_SHEET_WEIGHT = 0.35

# Nothing is ever weighted to nothing. A lap from six sessions ago on an old
# sheet still happened, and a floor keeps a long history from collapsing to
# the last two runs - which is truncation wearing a decay's clothes.
MINIMUM_WEIGHT = 0.05


@dataclass(frozen=True)
class Weighting:
    """The weights applied, and enough to explain them."""
    half_life_sessions: float
    superseded_sheet_weight: float
    sessions: int
    current_sheet_id: int | None

    def as_export(self) -> dict:
        return {
            "halfLifeSessions": self.half_life_sessions,
            "supersededSheetWeight": self.superseded_sheet_weight,
            "sessionsWeighted": self.sessions,
            "currentSheetId": self.current_sheet_id,
            "appliesTo": ["referenceLapMs", "fuelPerLapL"],
            "excludes": [
                "wear - read off the in-game gauge rather than fitted, so "
                "reweighting it would reweight a measurement",
                "bestLapMs - a fact about one lap, with nothing to average",
            ],
            "source": "derived",
            "note": (
                "Later laps count for more because the driver and the car are "
                "both changing. Measured across the Monza practice set the "
                "difference between the pooled median and the latest session "
                "is 0.37 s a lap."),
        }


def session_order(laps) -> dict:
    """Each session id mapped to how many sessions ago it was, newest = 0.

    Ordered by the sequence the laps arrive in rather than by timestamp: the
    lap list is already in session order, `started_at` is second-resolution,
    and two runs begun in the same second would otherwise tie.
    """
    seen: list = []
    for lap in laps:
        if lap.session_id is not None and lap.session_id not in seen:
            seen.append(lap.session_id)
    return {session_id: len(seen) - 1 - index
            for index, session_id in enumerate(seen)}


def weight_of(lap, ages: dict, current_sheet_id: int | None) -> float:
    """How much this lap counts, between `MINIMUM_WEIGHT` and 1.0."""
    age = ages.get(lap.session_id, 0)
    weight = 0.5 ** (age / HALF_LIFE_SESSIONS) if HALF_LIFE_SESSIONS else 1.0
    # `None` is not a mismatch. A lap with no sheet recorded has not said
    # which car it was describing, and penalising it would be reading silence
    # as a positive claim.
    sheet_id = getattr(lap, "setup_sheet_id", None)
    if (current_sheet_id is not None and sheet_id is not None
            and sheet_id != current_sheet_id):
        weight *= SUPERSEDED_SHEET_WEIGHT
    return max(MINIMUM_WEIGHT, weight)


def weighted_median(pairs: list[tuple[float, float]]) -> float | None:
    """The value at which half the *weight* lies either side.

    Median rather than mean, for the same reason the unweighted figures use
    one: a single bad lap should not move the number, and a weighting scheme
    is not a reason to give one up.
    """
    usable = [(value, weight) for value, weight in pairs if weight > 0]
    if not usable:
        return None
    usable.sort(key=lambda pair: pair[0])
    total = sum(weight for _, weight in usable)
    running = 0.0
    for value, weight in usable:
        running += weight
        if running >= total / 2:
            return value
    return usable[-1][0]


def weighted(laps, value_of, *, current_sheet_id: int | None = None
             ) -> tuple[float | None, Weighting]:
    """The weighted median of `value_of` across these laps, and the weighting.

    Returns `(None, weighting)` where no lap yields a value — never zero. A
    figure that could not be computed and a figure that came out at zero are
    different claims and only one of them is evidence.
    """
    ages = session_order(laps)
    pairs = []
    for lap in laps:
        value = value_of(lap)
        if value is None:
            continue
        pairs.append((value, weight_of(lap, ages, current_sheet_id)))

    weighting = Weighting(
        half_life_sessions=HALF_LIFE_SESSIONS,
        superseded_sheet_weight=SUPERSEDED_SHEET_WEIGHT,
        sessions=len(ages),
        current_sheet_id=current_sheet_id)
    return weighted_median(pairs), weighting
